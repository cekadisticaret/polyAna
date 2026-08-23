"""Tahmin motorları — her satır /bahis'te ayrı sekme. Yeni algo: dosya + bir satır."""
from __future__ import annotations

from bahis import bankroll_preds, dixon_coles, elo, match_intel

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


def _poisson(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("poisson", "POISSON", lambda t, l: match_intel.upcoming_kind("poisson", t, l), team, limit)


def _xg(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("xg", "XG", lambda t, l: match_intel.upcoming_kind("xg", t, l), team, limit)


def _ensemble(team: str | None = None, limit: int = 24) -> dict:
    return _wrap("ensemble", "ENSEMBLE", lambda t, l: match_intel.upcoming_kind("ensemble", t, l), team, limit)


ENGINES = (
    {"id": "dixon", "label": "DIXON-COLES", "title": "Dixon-Coles Poisson", "run": _dixon},
    {"id": "poisson", "label": "POISSON", "title": "Son 10 maç λ", "run": _poisson},
    {"id": "elo", "label": "ELO", "title": "ELO rating + RD", "run": _elo},
    {"id": "xg", "label": "XG", "title": "Fotmob xG", "run": _xg},
    {"id": "ensemble", "label": "ENSEMBLE", "title": "Poisson+Elo+xG", "run": _ensemble},
    {"id": "bankroll", "label": "BANKROLL", "title": "¼ Kelly value stake", "run": _bankroll},
)


def list_engines() -> list[dict]:
    return [{"id": e["id"], "label": e["label"], "title": e["title"]} for e in ENGINES]


def run(engine_id: str | None = None, team: str | None = None, limit: int = 24) -> dict:
    if not ENGINES:
        return {"ok": False, "error": "motor yok"}
    e = next((x for x in ENGINES if x["id"] == engine_id), ENGINES[0])
    if engine_id and e["id"] != engine_id:
        return {"ok": False, "error": "motor yok", "engine": engine_id}
    return e["run"](team=team, limit=limit)
