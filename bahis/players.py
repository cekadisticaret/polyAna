"""Süper Lig oyuncu istatistikleri — `bahis/data/players.json` (Fotmob)."""
from __future__ import annotations

import json
import os
from functools import lru_cache

from bahis.league import team_info, team_key
from bahis.leagues_cfg import current_league, get as get_league

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data", "players.json")

STAT_LABELS = {
    "goals": "Gol",
    "assists": "Asist",
    "ga": "Gol+Asist",
    "rating": "Puan",
    "minutes": "Dakika",
    "xg": "xG",
    "xa": "xA",
    "xg90": "xG/90",
    "xa90": "xA/90",
    "shots90": "Şut/90",
    "sot90": "İsabet/90",
    "big_chances": "Büyük şans",
    "chances": "Pozisyon",
    "yellow": "Sarı",
    "red": "Kırmızı",
    "clean_sheets": "Clean sheet",
    "saves90": "Kurtarış/90",
    "goals_prevented": "Engellenen gol",
    "tackles90": "Müdahale/90",
    "int90": "Kesme/90",
    "dribbles90": "Dribling/90",
    "pens_won": "Penaltı kazandı",
}

LEADER_STATS = [
    "goals", "assists", "ga", "xg", "xa", "rating",
    "yellow", "red", "clean_sheets", "saves90", "goals_prevented",
    "big_chances", "minutes",
]


def _players_path(league: str | None = None) -> str:
    lg = get_league(league)
    return os.path.join(_DIR, "data", lg["players"])


@lru_cache(maxsize=8)
def _load_for(league: str) -> dict:
    path = _players_path(league)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load(league: str | None = None) -> dict:
    lid = get_league(league)["id"] if league else current_league()
    return _load_for(lid)


def reload() -> None:
    _load_for.cache_clear()


def _pub_player(p: dict, *, stats: bool = True) -> dict:
    info = team_info(p.get("team") or "")
    out = {
        "id": p.get("id"),
        "name": p.get("name"),
        "team": info["name"],
        "team_key": info["key"],
        "team_short": info["short"],
        "team_color": info["color"],
        "crest": info["crest"],
        "ccode": p.get("ccode") or "",
        "minutes": p.get("minutes"),
        "matches": p.get("matches"),
        "photo": p.get("photo") or "",
    }
    if stats:
        out["stats"] = p.get("stats") or {}
    return out


def seasons() -> list[dict]:
    pack = load()
    return [
        {"id": s["id"], "label": s["label"], "n": s.get("n_players") or 0}
        for s in pack.get("seasons") or []
    ]


def _season(sid: str | None) -> dict | None:
    pack = load()
    rows = pack.get("seasons") or []
    if not rows:
        return None
    if not sid or sid == "current":
        return rows[0]
    for s in rows:
        if s.get("id") == sid or s.get("label") == sid:
            return s
    return rows[0]


def list_players(
    season: str | None = None,
    team: str | None = None,
    q: str | None = None,
    sort: str = "goals",
    limit: int = 80,
) -> dict:
    s = _season(season)
    if not s:
        return {"ok": False, "error": "veri yok", "players": []}
    tk = team_key(team) if team else None
    qn = (q or "").strip().lower()
    rows = []
    for p in s.get("players") or []:
        info = team_info(p.get("team") or "")
        if tk and info["key"] != tk:
            continue
        if qn and qn not in (p.get("name") or "").lower() and qn not in info["name"].lower():
            continue
        rows.append(_pub_player(p))
    def _sv(p):
        st = p.get("stats") or {}
        v = st.get(sort)
        if v is None and sort == "minutes":
            v = p.get("minutes")
        return float(v) if v is not None else -1
    rows.sort(key=_sv, reverse=True)
    if limit and limit > 0:
        rows = rows[: min(int(limit), 400)]
    return {
        "ok": True,
        "season": {"id": s["id"], "label": s["label"], "n": s.get("n_players") or 0},
        "sort": sort,
        "count": len(rows),
        "players": rows,
    }


def leaders(season: str | None = None, stat: str = "goals", limit: int = 25) -> dict:
    s = _season(season)
    if not s:
        return {"ok": False, "leaders": []}
    stat = stat if stat in STAT_LABELS else "goals"
    raw = (s.get("leaders") or {}).get(stat) or []
    out = []
    for r in raw[: max(1, min(int(limit), 80))]:
        info = team_info(r.get("team") or "")
        out.append({
            **r,
            "team": info["name"],
            "team_key": info["key"],
            "team_short": info["short"],
            "crest": info["crest"],
            "photo": f"https://images.fotmob.com/image_resources/playerimages/{r.get('id')}.png" if r.get("id") else "",
        })
    return {
        "ok": True,
        "season": {"id": s["id"], "label": s["label"]},
        "stat": stat,
        "label": STAT_LABELS.get(stat, stat),
        "leaders": out,
    }


def player(pid: int) -> dict:
    pack = load()
    seasons_out = []
    name = ""
    photo = ""
    ccode = ""
    for s in pack.get("seasons") or []:
        for p in s.get("players") or []:
            if int(p.get("id") or 0) != int(pid):
                continue
            name = p.get("name") or name
            photo = p.get("photo") or photo
            ccode = p.get("ccode") or ccode
            seasons_out.append({
                "season": s["id"],
                "label": s["label"],
                **_pub_player(p),
            })
            break
    if not seasons_out:
        # kadroda olabilir, istatistik yok
        for sq in (pack.get("squads") or {}).values():
            for g in sq.get("groups") or []:
                for m in g.get("players") or []:
                    if int(m.get("id") or 0) == int(pid):
                        info = team_info(sq.get("name") or "")
                        return {
                            "ok": True,
                            "id": pid,
                            "name": m.get("name"),
                            "photo": m.get("photo"),
                            "ccode": m.get("ccode"),
                            "team": info,
                            "squad": m,
                            "seasons": [],
                            "career": {},
                        }
        return {"ok": False, "error": "oyuncu yok"}
    career = {"matches": 0, "minutes": 0, "goals": 0, "assists": 0, "xg": 0.0, "xa": 0.0, "yellow": 0, "red": 0}
    for row in seasons_out:
        career["matches"] += row.get("matches") or 0
        career["minutes"] += row.get("minutes") or 0
        st = row.get("stats") or {}
        for k in ("goals", "assists", "yellow", "red"):
            career[k] += st.get(k) or 0
        for k in ("xg", "xa"):
            career[k] += float(st.get(k) or 0)
    career["xg"] = round(career["xg"], 2)
    career["xa"] = round(career["xa"], 2)
    return {
        "ok": True,
        "id": pid,
        "name": name,
        "photo": photo,
        "ccode": ccode,
        "career": career,
        "seasons": seasons_out,
        "n": len(seasons_out),
    }


def squad(team: str | None = None) -> dict:
    pack = load()
    squads = pack.get("squads") or {}
    by_key = {}
    for sq in squads.values():
        info = team_info(sq.get("name") or "")
        by_key[info["key"]] = {**sq, "team": info}
    if team:
        tk = team_key(team)
        one = by_key.get(tk)
        if not one:
            return {"ok": False, "error": "kadro yok"}
        return {"ok": True, "squad": one}
    return {
        "ok": True,
        "squads": [
            {"team": v["team"], "n": v.get("n") or 0, "team_id": v.get("team_id")}
            for v in by_key.values()
        ],
    }


def pair_scorers(a: str, b: str, season: str | None = None, n: int = 5) -> dict:
    """İki takımın bu sezon gol/asist liderleri — H2H kartı için."""
    s = _season(season)
    if not s:
        return {"a": [], "b": []}
    ka, kb = team_key(a), team_key(b)
    def top(tk):
        rows = []
        for p in s.get("players") or []:
            if team_info(p.get("team") or "")["key"] != tk:
                continue
            g = (p.get("stats") or {}).get("goals") or 0
            a_ = (p.get("stats") or {}).get("assists") or 0
            if not g and not a_:
                continue
            rows.append(_pub_player(p))
        rows.sort(key=lambda x: ((x.get("stats") or {}).get("goals") or 0, (x.get("stats") or {}).get("assists") or 0), reverse=True)
        return rows[:n]
    return {"a": top(ka), "b": top(kb), "season": s["id"], "label": s["label"]}


def summary(season: str | None = None) -> dict:
    pack = load()
    s = _season(season)
    if not s:
        return {"ok": False, "error": "oyuncu verisi yok — python3 bahis/players_fetch.py"}
    chips = {}
    for stat in LEADER_STATS:
        chips[stat] = leaders(s["id"], stat, 8)["leaders"]
    return {
        "ok": True,
        "updated": pack.get("updated"),
        "src": pack.get("src"),
        "league": pack.get("league"),
        "seasons": seasons(),
        "season": {"id": s["id"], "label": s["label"], "n": s.get("n_players") or 0},
        "table": pack.get("table") or [],
        "leaders": chips,
        "stat_labels": STAT_LABELS,
        "squad_n": sum(v.get("n") or 0 for v in (pack.get("squads") or {}).values()),
        "team_n": len(pack.get("squads") or {}),
    }
