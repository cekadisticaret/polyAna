"""Dixon-Coles Poisson — `dixonColes.js` ile aynı aritmetik. Emir yok."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from bahis.league import all_matches, team_info

TR = ZoneInfo("Europe/Istanbul")
HALF_LIFE_DAYS = 180
MAX_ITER = 300
HOME_ADV = 0.25
RHO = -0.05
MAX_GOALS = 8
MIN_EDGE = 0.03
UPCOMING_DAYS = 21
UPCOMING_LIMIT = 24


def _factorial(n: int) -> float:
    r = 1.0
    for i in range(2, n + 1):
        r *= i
    return r


def poisson_pmf(lam: float, k: int) -> float:
    return (math.exp(-lam) * (lam ** k)) / _factorial(k)


def tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    if x == 0 and y == 1:
        return 1 + lam * rho
    if x == 1 and y == 0:
        return 1 + mu * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1


def _time_weight(match_date: datetime, ref: datetime, half_life: float) -> float:
    days = (ref - match_date).total_seconds() / 86400
    lam = math.log(2) / half_life
    return math.exp(-lam * max(days, 0))


def _parse_ko(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TR)
        return dt
    except ValueError:
        return None


class DixonColesModel:
    def __init__(self, matches: list[dict], half_life_days: float = HALF_LIFE_DAYS, max_iter: int = MAX_ITER):
        self.matches = matches
        self.half_life_days = half_life_days
        self.max_iter = max_iter
        teams: set[str] = set()
        for m in matches:
            teams.add(m["home"])
            teams.add(m["away"])
        self.teams = list(teams)
        self.params: dict[str, dict[str, float]] = {}
        self.home_adv = HOME_ADV
        self.rho = RHO
        self.avg_goals = 1.2

    def fit(self) -> dict[str, dict[str, float]]:
        teams = self.teams
        att = {t: 1.0 for t in teams}
        deff = {t: 1.0 for t in teams}
        n = max(len(self.matches), 1)
        avg = sum(m["homeGoals"] + m["awayGoals"] for m in self.matches) / (n * 2)
        ref = datetime.now(TR)
        exp_h = math.exp(self.home_adv)

        for _ in range(self.max_iter):
            att_num = {t: 0.0 for t in teams}
            att_den = {t: 0.0 for t in teams}
            def_num = {t: 0.0 for t in teams}
            def_den = {t: 0.0 for t in teams}
            for m in self.matches:
                w = _time_weight(m["date"], ref, self.half_life_days)
                att_num[m["home"]] += w * m["homeGoals"]
                att_den[m["home"]] += w * (deff[m["away"]] * exp_h * avg)
                def_num[m["away"]] += w * m["homeGoals"]
                def_den[m["away"]] += w * (att[m["home"]] * exp_h * avg)
                att_num[m["away"]] += w * m["awayGoals"]
                att_den[m["away"]] += w * (deff[m["home"]] * avg)
                def_num[m["home"]] += w * m["awayGoals"]
                def_den[m["home"]] += w * (att[m["away"]] * avg)
            for t in teams:
                if att_den[t] > 0:
                    att[t] = att_num[t] / att_den[t]
                if def_den[t] > 0:
                    deff[t] = def_num[t] / def_den[t]
            mean_att = sum(att.values()) / len(teams)
            mean_def = sum(deff.values()) / len(teams)
            for t in teams:
                att[t] /= mean_att
                deff[t] /= mean_def

        # Az maçlı (yeni yükselen) takım MM'de 0'a yapışır — 1.0'a doğru çek
        seen = {t: 0 for t in teams}
        for m in self.matches:
            seen[m["home"]] += 1
            seen[m["away"]] += 1
        for t in teams:
            n = seen[t]
            if n < 10:
                w = n / 10
                att[t] = w * att[t] + (1 - w)
                deff[t] = w * deff[t] + (1 - w)
        mean_att = sum(att.values()) / len(teams)
        mean_def = sum(deff.values()) / len(teams)
        for t in teams:
            att[t] /= mean_att
            deff[t] /= mean_def

        self.params = {t: {"attack": att[t], "defense": deff[t]} for t in teams}
        self.avg_goals = avg
        return self.params

    def _strength(self, key: str) -> dict[str, float]:
        return self.params.get(key) or {"attack": 1.0, "defense": 1.0}

    def expected_goals(self, home: str, away: str) -> dict[str, float]:
        h, a = self._strength(home), self._strength(away)
        lam = h["attack"] * a["defense"] * math.exp(self.home_adv) * self.avg_goals
        mu = a["attack"] * h["defense"] * self.avg_goals
        return {"lambda": lam, "mu": mu}

    def score_matrix(self, home: str, away: str, max_goals: int = MAX_GOALS) -> list[list[float]]:
        xg = self.expected_goals(home, away)
        lam, mu = xg["lambda"], xg["mu"]
        matrix = []
        for x in range(max_goals + 1):
            row = []
            for y in range(max_goals + 1):
                p = poisson_pmf(lam, x) * poisson_pmf(mu, y) * tau(x, y, lam, mu, self.rho)
                row.append(max(p, 0.0))
            matrix.append(row)
        total = sum(p for row in matrix for p in row) or 1.0
        return [[p / total for p in row] for row in matrix]

    def markets(self, home: str, away: str, max_goals: int = MAX_GOALS) -> dict:
        m = self.score_matrix(home, away, max_goals)
        n = len(m)
        p_home = p_draw = p_away = btts = 0.0
        tot_dist: dict[int, float] = {}
        scores: list[dict] = []
        for x in range(n):
            for y in range(n):
                p = m[x][y]
                if x > y:
                    p_home += p
                elif x == y:
                    p_draw += p
                else:
                    p_away += p
                if x > 0 and y > 0:
                    btts += p
                tot = x + y
                tot_dist[tot] = tot_dist.get(tot, 0.0) + p
                scores.append({"score": f"{x}-{y}", "p": p})
        scores.sort(key=lambda r: r["p"], reverse=True)
        over_under = {}
        for line in (0.5, 1.5, 2.5, 3.5, 4.5):
            under = sum(tot_dist.get(g, 0.0) for g in range(int(math.floor(line)) + 1))
            over_under[str(line)] = {"under": under, "over": 1 - under}
        xg = self.expected_goals(home, away)
        return {
            "matchResult": {"1": p_home, "X": p_draw, "2": p_away},
            "doubleChance": {
                "1X": p_home + p_draw,
                "12": p_home + p_away,
                "X2": p_draw + p_away,
            },
            "bttsYes": btts,
            "bttsNo": 1 - btts,
            "overUnder": over_under,
            "correctScoreTop5": scores[:5],
            "expectedGoals": xg,
        }

    @staticmethod
    def find_value(model_prob: float, market_odds: float, min_edge: float = MIN_EDGE) -> dict:
        implied = 1 / market_odds
        edge = model_prob - implied
        return {
            "edge": edge,
            "isValue": edge >= min_edge,
            "kellyFraction": (edge / (market_odds - 1)) if edge > 0 else 0.0,
        }


def _train_rows() -> list[dict]:
    rows = []
    for m in all_matches():
        if not m.get("played"):
            continue
        hg, ag = m.get("hg"), m.get("ag")
        if hg is None or ag is None:
            continue
        dt = _parse_ko(m.get("kickoff")) or datetime(2016, 1, 1, tzinfo=TR)
        rows.append({
            "home": m["home"]["key"],
            "away": m["away"]["key"],
            "homeGoals": int(hg),
            "awayGoals": int(ag),
            "date": dt,
        })
    return rows


@lru_cache(maxsize=1)
def _fitted() -> DixonColesModel:
    model = DixonColesModel(_train_rows())
    model.fit()
    return model


def _round_p(p: float) -> float:
    return round(float(p), 3)


def _pct(p: float) -> int:
    return int(round(p * 100))


def _value_pack(mr: dict, odds: dict | None) -> list[dict]:
    if not odds:
        return []
    out = []
    for key, field in (("1", "home"), ("X", "draw"), ("2", "away")):
        o = odds.get(field)
        if not o or o <= 1:
            continue
        v = DixonColesModel.find_value(mr[key], float(o))
        if v["isValue"]:
            out.append({
                "pick": key,
                "odds": round(float(o), 2),
                "edge": _round_p(v["edge"]),
                "kelly": _round_p(v["kellyFraction"]),
            })
    return out


def _when(ko: str | None) -> str:
    dt = _parse_ko(ko)
    if not dt:
        return ko or ""
    return dt.strftime("%d.%m %H:%M")


def _card(m: dict, mk: dict) -> dict:
    hi, ai = m["home"], m["away"]
    mr = mk["matchResult"]
    pick = max(mr, key=mr.get)
    if pick == "1":
        text = f"{hi['name']} kazanır"
    elif pick == "2":
        text = f"{ai['name']} kazanır"
    else:
        text = "Beraberlik"
    ou = {k: {"under": _round_p(v["under"]), "over": _round_p(v["over"])} for k, v in mk["overUnder"].items()}
    xg = mk["expectedGoals"]
    return {
        "id": m["id"],
        "week": m.get("week"),
        "kickoff": m.get("kickoff"),
        "when": _when(m.get("kickoff")),
        "venue": m.get("venue"),
        "home": hi,
        "away": ai,
        "odds": m.get("odds") or {},
        "xg": {"home": _round_p(xg["lambda"]), "away": _round_p(xg["mu"])},
        "matchResult": {k: _round_p(v) for k, v in mr.items()},
        "doubleChance": {k: _round_p(v) for k, v in mk["doubleChance"].items()},
        "bttsYes": _round_p(mk["bttsYes"]),
        "bttsNo": _round_p(mk["bttsNo"]),
        "overUnder": ou,
        "correctScoreTop5": [
            {"score": s["score"], "p": _round_p(s["p"]), "pct": _pct(s["p"])}
            for s in mk["correctScoreTop5"]
        ],
        "pick": pick,
        "text": text,
        "pct": _pct(mr[pick]),
        "value": _value_pack(mr, m.get("odds")),
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
        mk = model.markets(m["home"]["key"], m["away"]["key"])
        rows.append(_card(m, mk))
        if len(rows) >= limit:
            break
    strengths = [
        {
            "key": k,
            **team_info(k),
            "attack": _round_p(v["attack"]),
            "defense": _round_p(v["defense"]),
        }
        for k, v in sorted(model.params.items(), key=lambda kv: kv[1]["attack"], reverse=True)
        if k in {r["home"]["key"] for r in rows} | {r["away"]["key"] for r in rows}
    ]
    return {
        "ok": True,
        "model": "dixon-coles",
        "note": f"{len(model.matches)} maç · {HALF_LIFE_DAYS} gün yarı ömür",
        "half_life_days": HALF_LIFE_DAYS,
        "matches_used": len(model.matches),
        "horizon_days": UPCOMING_DAYS,
        "updated": now.isoformat(timespec="seconds"),
        "n": len(rows),
        "preds": rows,
        "strengths": strengths,
    }
