"""Bankroll Kelly katmanı — `bankroll_manager.py`. Dixon olasılığı × oran. Emir yok."""
from __future__ import annotations

from bahis.bankroll_manager import BankrollManager
from bahis import dixon_coles
from bahis.value import fair_1x2

STARTING = 10000.0
_SEL = {"1": "1 Ev", "X": "X Beraberlik", "2": "2 Dep"}


def upcoming_preds(team: str | None = None, limit: int = 24) -> dict:
    dc = dixon_coles.upcoming_preds(team=team, limit=limit)
    bm = BankrollManager(starting_bankroll=STARTING)
    rows = []
    taken_n = 0
    for src in dc.get("preds") or []:
        mr = src.get("matchResult") or {}
        odds = src.get("odds") or {}
        evals = []
        fair = (fair_1x2(odds) or {}).get("fair") or {}
        for sel, field in (("1", "home"), ("X", "draw"), ("2", "away")):
            o = odds.get(field)
            if not o or o <= 1:
                continue
            ev = bm.evaluate_bet(
                match=f"{src['home']['name']} - {src['away']['name']}",
                market="1X2",
                selection=sel,
                model_prob=float(mr.get(sel) or 0),
                market_odds=float(o),
                fair_implied=fair.get(sel),
            )
            evals.append({
                "selection": sel,
                "label": _SEL[sel],
                "model_prob": round(float(mr.get(sel) or 0), 3),
                "odds": float(o),
                "should_bet": bool(ev.get("should_bet")),
                "stake": ev.get("suggested_stake") or 0,
                "edge": round(float(ev.get("edge") or 0), 3),
                "kelly": ev.get("kelly_fraction_applied") or 0,
                "reason": ev.get("reject_reason") or "",
            })
        yes = [e for e in evals if e["should_bet"]]
        yes.sort(key=lambda e: e["stake"], reverse=True)
        best = yes[0] if yes else (max(evals, key=lambda e: e["edge"]) if evals else None)
        if yes:
            taken_n += 1
            pick, text, pct = best["selection"], f"AL · {_SEL[best['selection']]} · {best['stake']} birim", int(round(best["model_prob"] * 100))
        elif best:
            pick, text, pct = best["selection"], f"PAS · {best['reason'] or 'edge yok'}", int(round(best["model_prob"] * 100))
        else:
            pick, text, pct = "", "PAS · oran yok", 0
        rows.append({
            "id": src["id"],
            "week": src.get("week"),
            "kickoff": src.get("kickoff"),
            "when": src.get("when"),
            "venue": src.get("venue"),
            "home": src["home"],
            "away": src["away"],
            "odds": odds,
            "matchResult": mr,
            "pick": pick,
            "text": text,
            "pct": pct,
            "evals": evals,
            "stake": {
                "should_bet": bool(yes),
                "amount": (best or {}).get("stake") or 0,
                "edge": (best or {}).get("edge") or 0,
                "selection": (best or {}).get("selection"),
                "reason": (best or {}).get("reason") or "",
            },
        })
    rows.sort(key=lambda r: (not r["stake"]["should_bet"], -(r["stake"]["edge"] or 0)))
    return {
        "ok": True,
        "model": "bankroll",
        "note": f"kasa {int(STARTING)} · ¼ Kelly · fair kenar ≥%4 · {taken_n} AL",
        "matches_used": dc.get("matches_used"),
        "horizon_days": dc.get("horizon_days"),
        "updated": dc.get("updated"),
        "n": len(rows),
        "taken_n": taken_n,
        "preds": rows,
        "strengths": [],
        "bankroll": bm.stats(),
    }
