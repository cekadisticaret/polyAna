"""Walk-forward doğrulama — Brier · log-loss · oranlı P&L. Emir yok.

Zaman sırası: ELO her maçta önce tahmin sonra güncelle (bakış yok).
Dixon-Coles sezon genişleyen pencere — test sezonu eğitimde yok.
İsabet tek başına kâr değildir; P&L açılış oranından.
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_DIR))

from bahis.dixon_coles import DixonColesModel
from bahis.elo import EloModel
from bahis.league import all_matches
from bahis.leagues_cfg import current_league, get as get_league, set_league
from bahis.value import MIN_EDGE, edges, fair_1x2

TR = ZoneInfo("Europe/Istanbul")
DATA = os.path.join(os.path.dirname(__file__), "data")
STAKE_UNIT = 100.0  # kağıt birim; ROI = pnl / staked
_FIELD = {"1": "home", "X": "draw", "2": "away"}


def _parse(ko: str | None) -> datetime:
    if not ko:
        return datetime(2016, 1, 1, tzinfo=TR)
    try:
        dt = datetime.fromisoformat(ko)
        return dt if dt.tzinfo else dt.replace(tzinfo=TR)
    except ValueError:
        return datetime(2016, 1, 1, tzinfo=TR)


def _actual(hg: int, ag: int) -> str:
    if hg > ag:
        return "1"
    if hg < ag:
        return "2"
    return "X"


def _open_odds(m: dict) -> dict | None:
    od = m.get("odds") or {}
    op = od.get("open") or {}
    h = op.get("home") or od.get("home")
    d = op.get("draw") or od.get("draw")
    a = op.get("away") or od.get("away")
    if not h or not d or not a or min(h, d, a) <= 1:
        return None
    return {"home": float(h), "draw": float(d), "away": float(a)}


def _played() -> list[dict]:
    rows = []
    for m in all_matches():
        if not m.get("played"):
            continue
        hg, ag = m.get("hg"), m.get("ag")
        if hg is None or ag is None:
            continue
        odds = _open_odds(m)
        rows.append({
            "id": m.get("id"),
            "season": m.get("season"),
            "home": m["home"]["key"],
            "away": m["away"]["key"],
            "home_name": m["home"]["name"],
            "away_name": m["away"]["name"],
            "homeGoals": int(hg),
            "awayGoals": int(ag),
            "date": _parse(m.get("kickoff")),
            "kickoff": m.get("kickoff"),
            "actual": _actual(int(hg), int(ag)),
            "odds": odds,
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def _brier(p: dict, actual: str) -> float:
    return sum((p[k] - (1.0 if k == actual else 0.0)) ** 2 for k in ("1", "X", "2"))


def _logloss(p: dict, actual: str) -> float:
    q = min(max(float(p.get(actual) or 0), 1e-6), 1 - 1e-6)
    return -math.log(q)


def _probs(p: dict) -> dict:
    return {k: float(p[k]) for k in ("1", "X", "2")}


def _grade(p: dict, actual: str, odds: dict | None) -> dict:
    p = _probs(p)
    pick = max(p, key=p.get)
    hit = pick == actual
    naive = 1.0 if hit else 0.0
    rec = {
        "pick": pick,
        "hit": hit,
        "p": {k: round(float(p[k]), 4) for k in ("1", "X", "2")},
        "brier": round(_brier(p, actual), 4),
        "logloss": round(_logloss(p, actual), 4),
        "naive": naive,
        "value": False,
        "pnl": 0.0,
        "staked": 0.0,
        "odds": None,
    }
    if not odds:
        return rec
    fair = fair_1x2(odds)
    field = _FIELD[pick]
    o = odds[field]
    ev = edges(float(p[pick]), o, (fair or {}).get("fair", {}).get(pick))
    rec["odds"] = ev["odds"]
    rec["edge_fair"] = ev["edgeFair"]
    if ev["isValue"]:
        rec["value"] = True
        rec["staked"] = STAKE_UNIT
        rec["pnl"] = STAKE_UNIT * (o - 1) if hit else -STAKE_UNIT
    return rec


def _bins(rows: list[dict]) -> list[dict]:
    buckets = defaultdict(lambda: {"n": 0, "hits": 0, "sum_p": 0.0})
    for r in rows:
        pick = r["pick"]
        pr = float(r["p"][pick])
        lo = int(pr * 10) / 10
        key = f"{lo:.1f}-{lo+0.1:.1f}"
        b = buckets[key]
        b["n"] += 1
        b["hits"] += 1 if r["hit"] else 0
        b["sum_p"] += pr
    out = []
    for k in sorted(buckets):
        b = buckets[k]
        out.append({
            "bin": k,
            "n": b["n"],
            "pred": round(b["sum_p"] / b["n"], 3),
            "actual": round(b["hits"] / b["n"], 3) if b["n"] else None,
        })
    return out


def _summary(rows: list[dict], model: str) -> dict:
    if not rows:
        return {"model": model, "n": 0}
    n = len(rows)
    hits = sum(1 for r in rows if r["hit"])
    val = [r for r in rows if r["value"]]
    staked = sum(r["staked"] for r in val)
    pnl = sum(r["pnl"] for r in val)
    naive_pnl = sum(r["naive"] for r in rows)  # +1 isabet, oran yok
    return {
        "model": model,
        "n": n,
        "hits": hits,
        "wr": round(100 * hits / n, 1),
        "brier": round(sum(r["brier"] for r in rows) / n, 4),
        "logloss": round(sum(r["logloss"] for r in rows) / n, 4),
        "naive_score": round(naive_pnl / n, 3),
        "naive_note": "oran yok · isabet≠kâr",
        "value_n": len(val),
        "value_pnl": round(pnl, 2),
        "value_staked": round(staked, 2),
        "value_roi": round(100 * pnl / staked, 1) if staked else None,
        "min_edge": MIN_EDGE,
        "bins": _bins(rows),
    }


def elo_walk(rows: list[dict]) -> list[dict]:
    model = EloModel([])
    out = []
    for m in rows:
        pr = model.predict_match(m["home"], m["away"])
        rec = _grade(pr, m["actual"], m["odds"])
        rec.update({
            "id": m["id"], "season": m["season"],
            "home": m["home_name"], "away": m["away_name"],
            "when": m["kickoff"],
        })
        out.append(rec)
        model.apply_match(m)
    return out


def dc_season_walk(rows: list[dict]) -> list[dict]:
    by_sea: dict[str, list] = defaultdict(list)
    for m in rows:
        by_sea[m["season"]].append(m)
    seasons = sorted(by_sea)
    train: list[dict] = []
    out = []
    for i, sea in enumerate(seasons):
        test = by_sea[sea]
        if i == 0 or len(train) < 80:
            train.extend(test)
            continue
        model = DixonColesModel([
            {"home": t["home"], "away": t["away"],
             "homeGoals": t["homeGoals"], "awayGoals": t["awayGoals"],
             "date": t["date"]}
            for t in train
        ])
        model.fit()
        for m in test:
            mk = model.markets(m["home"], m["away"])
            rec = _grade(mk["matchResult"], m["actual"], m["odds"])
            rec.update({
                "id": m["id"], "season": m["season"],
                "home": m["home_name"], "away": m["away_name"],
                "when": m["kickoff"],
            })
            out.append(rec)
        train.extend(test)
    return out


def run(league: str | None = None) -> dict:
    lid = set_league(league) if league else current_league()
    rows = _played()
    elo_rows = elo_walk(rows)
    dc_rows = dc_season_walk(rows)
    pack = {
        "ok": True,
        "league": get_league(lid)["name"],
        "league_id": lid,
        "updated": datetime.now(TR).isoformat(timespec="seconds"),
        "n_matches": len(rows),
        "n_odds": sum(1 for r in rows if r["odds"]),
        "elo": _summary(elo_rows, "elo-wf"),
        "dixon": _summary(dc_rows, "dixon-season-wf"),
        "note": (
            "walk-forward · ELO maç-maç · DC sezon penceresi · "
            "P&L açılış oranı · isabet≠kâr · emir yok"
        ),
        "orders": False,
    }
    path = os.path.join(DATA, f"backtest_{lid}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return pack


def load(league: str | None = None) -> dict:
    lid = league or current_league()
    path = os.path.join(DATA, f"backtest_{lid}.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get("ok"):
                return d
        except (OSError, json.JSONDecodeError):
            pass
    return {"ok": False, "error": "backtest yok · cron veya python3 bahis/calib.py",
            "league_id": lid}


def upcoming_preds(team: str | None = None, limit: int = 24) -> dict:
    """Motor kartı — önbellek özeti. team yok sayılır."""
    d = load()
    if not d.get("ok"):
        return {
            "ok": True, "model": "backtest", "engine": "backtest",
            "note": d.get("error") or "yok", "n": 0, "preds": [], "strengths": [],
            "backtest": d,
        }
    cards = []
    for key, title in (("elo", "ELO walk-forward"), ("dixon", "Dixon sezon WF")):
        s = d.get(key) or {}
        if not s.get("n"):
            continue
        roi = s.get("value_roi")
        cards.append({
            "id": f"bt-{key}",
            "when": d.get("updated") or "",
            "week": s.get("n"),
            "home": {"key": key, "name": title, "short": key.upper()},
            "away": {"key": "mkt", "name": "piyasa oranı", "short": "ODS"},
            "pick": "1" if (roi or 0) >= 0 else "2",
            "text": (
                f"Brier {s.get('brier')} · logloss {s.get('logloss')} · "
                f"WR %{s.get('wr')} · value {s.get('value_n')} · "
                f"ROI {('—%' if roi is None else f'%{roi}')}"
            ),
            "pct": int(round(s.get("wr") or 0)),
            "matchResult": {"1": 0.34, "X": 0.33, "2": 0.33},
            "bins": s.get("bins") or [],
            "stats": s,
        })
    return {
        "ok": True,
        "model": "backtest",
        "engine": "backtest",
        "label": "BACKTEST",
        "note": d.get("note"),
        "updated": d.get("updated"),
        "n": len(cards),
        "preds": cards[:limit],
        "strengths": [],
        "backtest": d,
    }


def main() -> int:
    from bahis.leagues_cfg import LEAGUES
    import sys
    ids = [a for a in sys.argv[1:] if not a.startswith("-")] or [lg["id"] for lg in LEAGUES]
    for lid in ids:
        d = run(lid)
        e, x = d.get("elo") or {}, d.get("dixon") or {}
        print(
            f"{lid} n={d['n_matches']} odds={d['n_odds']} · "
            f"ELO Brier {e.get('brier')} WR {e.get('wr')} valROI {e.get('value_roi')} · "
            f"DC Brier {x.get('brier')} WR {x.get('wr')} valROI {x.get('value_roi')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
