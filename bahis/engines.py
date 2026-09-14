"""Tahmin motorları — her satır /bahis'te ayrı sekme. Yeni algo: dosya + bir satır."""
from __future__ import annotations

from bahis import bankroll_preds, calib, coupon, dixon_coles, elo, match_intel

# Kupon / settle sonra bağlanacak: her motorun preds kartı aynı şema
# (matchResult, pick, text, pct …).


def _wrap(engine: str, label: str, fn, team: str | None, limit: int) -> dict:
    d = fn(team=team, limit=limit)
    d["engine"] = engine
    d["label"] = label
    return d


def _dixon(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("dixon", "DIXON-COLES", dixon_coles.upcoming_preds, team, limit)


def _elo(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("elo", "ELO", elo.upcoming_preds, team, limit)


def _bankroll(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("bankroll", "BANKROLL", bankroll_preds.upcoming_preds, team, limit)


def _coupon(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("coupon", "KUPON", coupon.upcoming_preds, team, limit)


def _backtest(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("backtest", "BACKTEST", calib.upcoming_preds, team, limit)


def _poisson(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("poisson", "POISSON", lambda team=None, limit=24: match_intel.upcoming_kind("poisson", team, limit), team, limit)


def _xg(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("xg", "XG", lambda team=None, limit=24: match_intel.upcoming_kind("xg", team, limit), team, limit)


def _ensemble(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("ensemble", "ENSEMBLE", lambda team=None, limit=24: match_intel.upcoming_kind("ensemble", team, limit), team, limit)


ENGINES = (
    {"id": "dixon", "label": "DIXON-COLES", "title": "Dixon-Coles + ELO λ", "run": _dixon},
    {"id": "poisson", "label": "POISSON", "title": "Son 10 maç λ", "run": _poisson},
    {"id": "elo", "label": "ELO", "title": "ELO rating + RD", "run": _elo},
    {"id": "xg", "label": "XG", "title": "Fotmob xG", "run": _xg},
    {"id": "ensemble", "label": "ENSEMBLE", "title": "DC+ELO λ · 1X2/2.5/KG", "run": _ensemble},
    {"id": "bankroll", "label": "BANKROLL", "title": "¼ Kelly · fair kenar %4", "run": _bankroll},
    {"id": "coupon", "label": "KUPON", "title": "Greedy kâğıt kupon · korelasyon", "run": _coupon},
    {"id": "backtest", "label": "BACKTEST", "title": "Walk-forward · Brier / log-loss", "run": _backtest},
)


def list_engines() -> list[dict]:
    return [{"id": e["id"], "label": e["label"], "title": e["title"]} for e in ENGINES]


def run(engine_id: str | None = None, team: str | None = None, limit: int = 24,
        league: str | None = None) -> dict:
    if league:
        from bahis.leagues_cfg import set_league
        set_league(league)
    if not ENGINES:
        return {"ok": False, "error": "motor yok"}
    e = next((x for x in ENGINES if x["id"] == engine_id), ENGINES[0])
    if engine_id and e["id"] != engine_id:
        return {"ok": False, "error": "motor yok", "engine": engine_id}
    return e["run"](team=team, limit=limit)
