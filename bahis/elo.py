"""ELO rating — `elo.js` ile aynı aritmetik. Emir yok."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from bahis.dixon_coles import (
    UPCOMING_DAYS,
    UPCOMING_LIMIT,
    _pct,
    _round_p,
    _train_rows,
    _when,
)
from bahis.league import all_matches, team_info

TR = ZoneInfo("Europe/Istanbul")
BASE_ELO = 1500.0
BASE_K = 20.0
HOME_ADV = 65.0
BASE_RD = 350.0
MIN_RD = 60.0


class EloModel:
    def __init__(self, matches: list[dict], opts: dict | None = None):
        opts = opts or {}
        self.matches = sorted(matches, key=lambda m: m["date"])
        self.base_elo = opts.get("baseElo", BASE_ELO)
        self.base_k = opts.get("baseK", BASE_K)
        self.home_adv = opts.get("homeAdv", HOME_ADV)
        self.base_rd = opts.get("baseRD", BASE_RD)
        self.min_rd = opts.get("minRD", MIN_RD)
        self.ratings: dict[str, dict] = {}

    def _get(self, team: str) -> dict:
        if team not in self.ratings:
            self.ratings[team] = {
                "elo": self.base_elo,
                "rd": self.base_rd,
                "matchCount": 0,
            }
        return self.ratings[team]

    @staticmethod
    def expected_score(rating_a: float, rating_b: float) -> float:
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    @staticmethod
    def goal_diff_multiplier(goal_diff: float) -> float:
        return math.sqrt(max(goal_diff, 1))

    def apply_match(self, m: dict) -> None:
        """Tek maçı işler — walk-forward: önce predict, sonra apply."""
        home = self._get(m["home"])
        away = self._get(m["away"])
        if m["homeGoals"] > m["awayGoals"]:
            actual_home = 1.0
        elif m["homeGoals"] == m["awayGoals"]:
            actual_home = 0.5
        else:
            actual_home = 0.0
        expected_home = self.expected_score(home["elo"] + self.home_adv, away["elo"])
        goal_diff = abs(m["homeGoals"] - m["awayGoals"])
        mult = self.goal_diff_multiplier(goal_diff)
        k_home = self.base_k * mult * (home["rd"] / self.base_rd)
        k_away = self.base_k * mult * (away["rd"] / self.base_rd)
        home["elo"] += k_home * (actual_home - expected_home)
        away["elo"] += k_away * ((1 - actual_home) - (1 - expected_home))
        home["matchCount"] += 1
        away["matchCount"] += 1
        home["rd"] = max(self.min_rd, self.base_rd / math.sqrt(home["matchCount"]))
        away["rd"] = max(self.min_rd, self.base_rd / math.sqrt(away["matchCount"]))

    def fit(self) -> dict:
        for m in self.matches:
            self.apply_match(m)
        return self.ratings

    def predict_match(self, home: str, away: str) -> dict:
        h, a = self._get(home), self._get(away)
        p_home_win = self.expected_score(h["elo"] + self.home_adv, a["elo"])
        elo_diff = abs(h["elo"] + self.home_adv - a["elo"])
        p_draw = max(0.18, 0.32 - elo_diff / 1000)
        p_home = max(p_home_win - p_draw / 2, 0.02)
        p_away = max((1 - p_home_win) - p_draw / 2, 0.02)
        total = p_home + p_draw + p_away
        return {
            "1": p_home / total,
            "X": p_draw / total,
            "2": p_away / total,
            "confidence": {
                "home": {"elo": h["elo"], "rd": h["rd"], "matches": h["matchCount"]},
                "away": {"elo": a["elo"], "rd": a["rd"], "matches": a["matchCount"]},
                "reliable": h["rd"] < 150 and a["rd"] < 150,
            },
        }

    @staticmethod
    def agreement_check(elo_probs: dict, dc_probs: dict, threshold: float = 0.15) -> dict:
        diffs = {
            "1": abs(elo_probs["1"] - dc_probs["1"]),
            "X": abs(elo_probs["X"] - dc_probs["X"]),
            "2": abs(elo_probs["2"] - dc_probs["2"]),
        }
        max_diff = max(diffs.values())
        return {"diffs": diffs, "maxDiff": max_diff, "agree": max_diff <= threshold}

    def ranking(self) -> list[dict]:
        return [
            {
                "team": t,
                "elo": round(r["elo"]),
                "rd": round(r["rd"]),
                "matches": r["matchCount"],
            }
            for t, r in sorted(self.ratings.items(), key=lambda kv: kv[1]["elo"], reverse=True)
        ]


@lru_cache(maxsize=8)
def _fitted_for(league: str) -> EloModel:
    from bahis.leagues_cfg import set_league
    set_league(league)
    model = EloModel(_train_rows())
    model.fit()
    return model


def _fitted() -> EloModel:
    from bahis.leagues_cfg import current_league
    return _fitted_for(current_league())


def _card(m: dict, pred: dict) -> dict:
    hi, ai = m["home"], m["away"]
    mr = {k: _round_p(pred[k]) for k in ("1", "X", "2")}
    pick = max(mr, key=mr.get)
    if pick == "1":
        text = f"{hi['name']} kazanır"
    elif pick == "2":
        text = f"{ai['name']} kazanır"
    else:
        text = "Beraberlik"
    conf = pred["confidence"]
    return {
        "id": m["id"],
        "week": m.get("week"),
        "kickoff": m.get("kickoff"),
        "when": _when(m.get("kickoff")),
        "venue": m.get("venue"),
        "home": hi,
        "away": ai,
        "odds": m.get("odds") or {},
        "matchResult": mr,
        "doubleChance": {
            "1X": _round_p(mr["1"] + mr["X"]),
            "12": _round_p(mr["1"] + mr["2"]),
            "X2": _round_p(mr["X"] + mr["2"]),
        },
        "pick": pick,
        "text": text,
        "pct": _pct(mr[pick]),
        "elo": {
            "home": round(conf["home"]["elo"]),
            "away": round(conf["away"]["elo"]),
            "rd_h": round(conf["home"]["rd"]),
            "rd_a": round(conf["away"]["rd"]),
            "n_h": conf["home"]["matches"],
            "n_a": conf["away"]["matches"],
            "reliable": bool(conf["reliable"]),
        },
        "value": [],
    }


def upcoming_preds(team: str | None = None, limit: int = UPCOMING_LIMIT) -> dict:
    now = datetime.now(TR)
    until = now + timedelta(days=UPCOMING_DAYS)
    now_s, until_s = now.isoformat(), until.isoformat()
    model = _fitted()
    rows = []
    for m in all_matches():
        if m.get("played"):
            continue
        ko = m.get("kickoff") or ""
        if ko < now_s[:10] or ko > until_s:
            continue
        if team and team not in (m["home"]["key"], m["away"]["key"]):
            continue
        pred = model.predict_match(m["home"]["key"], m["away"]["key"])
        rows.append(_card(m, pred))
        if len(rows) >= limit:
            break
    used = {r["home"]["key"] for r in rows} | {r["away"]["key"] for r in rows}
    strengths = []
    for r in model.ranking():
        if r["team"] not in used:
            continue
        info = team_info(r["team"])
        strengths.append({
            "key": r["team"],
            **info,
            "attack": r["elo"],
            "defense": r["rd"],
        })
    return {
        "ok": True,
        "model": "elo",
        "note": f"{len(model.matches)} maç · ev +{int(HOME_ADV)} ELO · RD güven",
        "matches_used": len(model.matches),
        "horizon_days": UPCOMING_DAYS,
        "updated": now.isoformat(timespec="seconds"),
        "n": len(rows),
        "preds": rows,
        "strengths": strengths,
    }
