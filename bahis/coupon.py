"""Kâğıt kupon — aynı maç korelasyonu + greedy. Emir yok.

Aynı maçtan 2.5 + KG bağımsız değildir; birleşik olasılık skor
matrisinden gelir, çarpım şişirir. Maçlar arası bağımsızlık makul;
aynı lig+gün için küçük ceza. Ayak arttıkça varyans büyür → Kelly
1/√n. Greedy: max 4 ayak, min fair kenar, oran çarpımı tavanı.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bahis.bankroll_manager import BankrollManager
from bahis import dixon_coles, value
from bahis.leagues_cfg import current_league, get as get_league

TR = ZoneInfo("Europe/Istanbul")
MAX_LEGS = 4
MIN_EDGE = value.MIN_EDGE
HORIZON_DAYS = 5  # siteler uzak fikstüre kupon açmaz
MAX_ODDS_PRODUCT = 18.0
SAME_BUCKET_PENALTY = 0.985  # aynı lig+gün ekstra maç
STARTING = 10000.0
_LABEL = {
    "1": "1 Ev", "X": "X Beraberlik", "2": "2 Dep",
    "over": "2.5 Üst", "under": "2.5 Alt",
    "btts_yes": "KG Var", "btts_no": "KG Yok",
}
_1X2 = {"1", "X", "2"}
_OU = {"over", "under"}
_BTTS = {"btts_yes", "btts_no"}


def _hit(x: int, y: int, sel: str) -> bool:
    if sel == "1":
        return x > y
    if sel == "X":
        return x == y
    if sel == "2":
        return x < y
    if sel == "over":
        return x + y >= 3
    if sel == "under":
        return x + y <= 2
    if sel == "btts_yes":
        return x > 0 and y > 0
    if sel == "btts_no":
        return x == 0 or y == 0
    return False


def matrix_p(matrix: list[list[float]], sels: list[str]) -> float:
    n = len(matrix)
    s = 0.0
    for x in range(n):
        for y in range(n):
            if all(_hit(x, y, sel) for sel in sels):
                s += matrix[x][y]
    return s


def _team_keys(lg: dict) -> set[str]:
    out: set[str] = set()
    for side in ("home", "away"):
        v = lg.get(side)
        if isinstance(v, dict):
            k = v.get("key") or v.get("name") or ""
        else:
            k = v or ""
        if k:
            out.add(str(k).strip().lower())
    return out


def _conflict(a: dict, b: dict) -> bool:
    if _team_keys(a) & _team_keys(b):
        return True
    if a.get("match_id") != b.get("match_id"):
        return False
    if a["sel"] == b["sel"] or a["market"] == b["market"]:
        return True
    if a["sel"] in _1X2 and b["sel"] in _1X2:
        return True
    if a["sel"] in _OU and b["sel"] in _OU:
        return True
    if a["sel"] in _BTTS and b["sel"] in _BTTS:
        return True
    return False


def _day(ko: str | None) -> str:
    return (ko or "")[:10]


def _parse_ko(ko: str | None) -> datetime | None:
    if not ko:
        return None
    try:
        dt = datetime.fromisoformat(ko.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TR)
        return dt.astimezone(TR)
    except ValueError:
        return None


def in_horizon(ko: str | None, now: datetime | None = None) -> bool:
    dt = _parse_ko(ko)
    if not dt:
        return False
    now = now or datetime.now(TR)
    return now <= dt <= now + timedelta(days=HORIZON_DAYS)


def coupon_prob(legs: list[dict]) -> tuple[float, float, str]:
    """(p_joint, p_indep, note). Aynı maç matris; çarpım şişirme ölçülür."""
    if not legs:
        return 0.0, 0.0, ""
    by = defaultdict(list)
    for lg in legs:
        by[lg["match_id"]].append(lg)
    p_j = 1.0
    p_i = 1.0
    same_n = 0
    for group in by.values():
        prod = 1.0
        for lg in group:
            prod *= float(lg["model_p"])
            p_i *= float(lg["model_p"])
        if len(group) == 1:
            p_j *= float(group[0]["model_p"])
            continue
        same_n += 1
        mx = group[0].get("matrix")
        if not mx:
            p_j *= prod
            continue
        p_j *= matrix_p(mx, [lg["sel"] for lg in group])
    buckets: dict[tuple[str, str], int] = defaultdict(int)
    seen = set()
    for lg in legs:
        key = (lg.get("league") or "", _day(lg.get("kickoff")))
        mid = lg["match_id"]
        if mid in seen:
            continue
        seen.add(mid)
        buckets[key] += 1
    extra = sum(max(n - 1, 0) for n in buckets.values())
    if extra:
        p_j *= SAME_BUCKET_PENALTY ** extra
    note = []
    if same_n:
        note.append(f"{same_n} maçta birleşik (matris, çarpım değil)")
    if extra:
        note.append(f"aynı lig+gün ×{extra} · %{round((1-SAME_BUCKET_PENALTY)*100, 1)} ceza")
    if not note:
        note.append("maçlar arası bağımsızlık")
    inflate = (p_i / p_j - 1) if p_j > 0 and p_i > p_j else 0.0
    if inflate > 0.02:
        note.append(f"bağımsız çarpım +{inflate*100:.0f}p şişirirdi")
    return p_j, p_i, " · ".join(note)


def _score_coupon(legs: list[dict]) -> dict | None:
    if not legs:
        return None
    odds_prod = 1.0
    for lg in legs:
        o = float(lg["odds"])
        if o <= 1:
            return None
        odds_prod *= o
    if odds_prod > MAX_ODDS_PRODUCT:
        return None
    p_j, p_i, note = coupon_prob(legs)
    if p_j <= 0:
        return None
    implied = 1.0 / odds_prod
    edge = p_j - implied
    n = len(legs)
    bm = BankrollManager(
        starting_bankroll=STARTING, min_edge=MIN_EDGE,
        max_odds=MAX_ODDS_PRODUCT,
    )
    ev = bm.evaluate_bet(
        match="kupon",
        market="coupon",
        selection="+".join(lg["sel"] for lg in legs),
        model_prob=p_j,
        market_odds=odds_prod,
        fair_implied=implied,
        n_legs=n,
    )
    return {
        "n": n,
        "odds_product": round(odds_prod, 3),
        "p_joint": round(p_j, 4),
        "p_indep": round(p_i, 4),
        "edge": round(edge, 4),
        "kelly": ev.get("kelly_fraction_applied") or 0,
        "stake": ev.get("suggested_stake") or 0,
        "should": bool(ev.get("should_bet")) and edge >= MIN_EDGE,
        "reason": ev.get("reject_reason") or "",
        "corr": note,
        "score": edge / math.sqrt(n),
    }


def _greedy(cands: list[dict], min_edge: float = 0.0) -> list[dict]:
    ordered = sorted(cands, key=lambda c: c.get("edge_fair") or 0, reverse=True)
    chosen: list[dict] = []
    best = None
    for c in ordered:
        if len(chosen) >= MAX_LEGS:
            break
        if any(_conflict(c, x) for x in chosen):
            continue
        trial = chosen + [c]
        ev = _score_coupon(trial)
        if not ev or ev["edge"] < min_edge:
            continue
        if best is None:
            chosen, best = trial, ev
            continue
        grow = ev["n"] > best["n"] and ev["edge"] >= 0
        better = ev["n"] == best["n"] and ev["score"] > best["score"]
        if grow or better:
            chosen, best = trial, ev
    return chosen


def _leg_card(c: dict) -> dict:
    hi, ai = c["home"], c["away"]
    return {
        "id": c["match_id"],
        "week": c.get("week"),
        "kickoff": c.get("kickoff"),
        "when": c.get("when"),
        "venue": c.get("venue"),
        "home": hi,
        "away": ai,
        "odds": c.get("odds_book") or {},
        "pick": c["sel"],
        "text": f"{_LABEL.get(c['sel'], c['sel'])} @ {c['odds']}",
        "pct": int(round(float(c["model_p"]) * 100)),
        "matchResult": c.get("mr") or {},
        "market": c["market"],
        "edge": c.get("edge_fair"),
        "edgeFair": c.get("edge_fair"),
        "stake": {
            "should_bet": True,
            "amount": 0,
            "edge": c.get("edge_fair") or 0,
            "selection": c["sel"],
        },
        "evals": [{
            "selection": c["sel"],
            "label": _LABEL.get(c["sel"], c["sel"]),
            "model_prob": round(float(c["model_p"]), 3),
            "odds": c["odds"],
            "should_bet": True,
            "stake": 0,
            "edge": c.get("edge_fair") or 0,
            "reason": "aday",
        }],
    }


def _scan(team: str | None, limit: int) -> list[dict]:
    dc = dixon_coles.upcoming_preds(team=team, limit=limit)
    model = dixon_coles._fitted()
    lid = current_league()
    out = []
    for src in dc.get("preds") or []:
        xg = src.get("xg") or {}
        lam, mu = xg.get("home"), xg.get("away")
        if lam is None or mu is None:
            continue
        matrix = model.score_matrix(
            src["home"]["key"], src["away"]["key"], lam=float(lam), mu=float(mu),
        )
        mr = src.get("matchResult") or {}
        ou = ((src.get("overUnder") or {}).get("2.5") or {})
        odds = src.get("odds") or {}
        ko = src.get("kickoff")
        if not in_horizon(ko):
            continue
        base = {
            "match_id": src["id"],
            "league": lid,
            "home": src["home"],
            "away": src["away"],
            "week": src.get("week"),
            "kickoff": ko,
            "when": src.get("when"),
            "venue": src.get("venue"),
            "matrix": matrix,
            "mr": mr,
            "odds_book": odds,
            "odds_src": src.get("odds_src"),
        }
        fair = value.fair_1x2(odds)
        added = False
        best = None
        for sel, field in (("1", "home"), ("X", "draw"), ("2", "away")):
            o = odds.get(field)
            if not o or float(o) <= 1:
                continue
            mp = float(mr.get(sel) or 0)
            ev = value.edges(mp, float(o), (fair or {}).get("fair", {}).get(sel))
            row = {
                **base,
                "market": "1X2",
                "sel": sel,
                "odds": ev["odds"],
                "model_p": mp,
                "edge_fair": ev["edgeFair"],
                "edge_raw": ev["edge"],
            }
            if ev["isValue"]:
                out.append(row)
                added = True
            if best is None or (ev["edgeFair"] or -9) > (best.get("edge_fair") or -9):
                best = row
        if not added and best:
            out.append(best)
        fair_ou = value.de_vig(value.book_ou(odds) or {}) if value.book_ou(odds) else None
        for sel, key in (("over", "over"), ("under", "under")):
            o = (odds.get("ou25") or {}).get(sel)
            if not o or float(o) <= 1:
                continue
            mp = float(ou.get(key) or 0)
            ev = value.edges(mp, float(o), (fair_ou or {}).get("fair", {}).get(sel))
            if not ev["isValue"]:
                continue
            out.append({
                **base,
                "market": "2.5",
                "sel": sel,
                "odds": ev["odds"],
                "model_p": mp,
                "edge_fair": ev["edgeFair"],
                "edge_raw": ev["edge"],
            })
    return out


def upcoming_preds(team: str | None = None, limit: int = 24) -> dict:
    cands = _scan(team, limit)
    legs = _greedy(cands, min_edge=0.0)
    ev = _score_coupon(legs) if legs else None
    taken_ids = {id(x) for x in legs}
    leftover = [c for c in cands if id(c) not in taken_ids]
    pub_legs = []
    for lg in legs:
        pub_legs.append({
            "id": lg["match_id"],
            "market": lg["market"],
            "sel": lg["sel"],
            "label": _LABEL.get(lg["sel"], lg["sel"]),
            "home": lg["home"]["name"],
            "away": lg["away"]["name"],
            "when": lg.get("when"),
            "kickoff": lg.get("kickoff"),
            "odds": lg["odds"],
            "model_p": round(float(lg["model_p"]), 3),
            "edge_fair": lg.get("edge_fair"),
            "odds_src": lg.get("odds_src"),
        })
    coupon = None
    if ev:
        coupon = {
            **ev,
            "legs": pub_legs,
            "max_legs": MAX_LEGS,
            "min_edge": MIN_EDGE,
            "orders": False,
        }
    clv = value.clv_stats()
    lg = get_league(current_league())
    n_al = 1 if ev and ev.get("should") else 0
    srcs = {c.get("odds_src") for c in (legs or cands) if c.get("odds_src")}
    note = (
        f"yalnız {HORIZON_DAYS} gün · max {MAX_LEGS} ayak · "
        f"oran football-data B365/Avg, yoksa H2H vekil · emir yok"
    )
    if srcs == {"h2h"} or (srcs and "fd" not in srcs):
        note += " · şu an H2H vekil"
    if ev:
        note += f" · birleşik {ev['odds_product']} · kenar %+{ev['edge']*100:.1f}"
    elif not cands:
        note += " · value bacak yok"
    extra = leftover[:8] if legs else cands[:8]
    preds = []
    for c in extra:
        card = _leg_card(c)
        if legs:
            card["text"] = "kupon dışı · " + card["text"]
            card["stake"]["should_bet"] = False
            if card.get("evals"):
                card["evals"][0]["should_bet"] = False
                card["evals"][0]["reason"] = "greedy seçmedi"
        preds.append(card)
    return {
        "ok": True,
        "model": "coupon",
        "engine": "coupon",
        "label": "KUPON",
        "note": note,
        "league": lg["name"],
        "updated": datetime.now(TR).isoformat(timespec="seconds"),
        "n": len(preds),
        "taken_n": n_al,
        "candidates_n": len(cands),
        "coupon": coupon,
        "clv": clv,
        "preds": preds,
        "strengths": [],
        "leftover_n": len(leftover),
    }
