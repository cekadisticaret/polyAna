"""Süper Lig oyuncu + kadro — Fotmob (lig 71). Emir yok, yalnız veri.

  python3 bahis/players_fetch.py
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_DIR))
DATA_DIR = os.path.join(_DIR, "data")
OUT = os.path.join(DATA_DIR, "players.json")
LEAGUE_ID = 71
ACTIVE = None
UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Encoding": "gzip",
}
TR = ZoneInfo("Europe/Istanbul")
SLEEP = 0.12

# Fotmob StatName → kısa anahtar (hepsi stats'ta durur, bunlar özet)
STAT_KEY = {
    "goals": "goals",
    "goal_assist": "assists",
    "_goals_and_goal_assist": "ga",
    "rating": "rating",
    "mins_played": "minutes",
    "goals_per_90": "goals90",
    "expected_goals": "xg",
    "expected_goals_per_90": "xg90",
    "expected_goalsontarget": "xgot",
    "ontarget_scoring_att": "sot90",
    "total_scoring_att": "shots90",
    "accurate_pass": "pass90",
    "big_chance_created": "big_chances",
    "total_att_assist": "chances",
    "accurate_long_balls": "long90",
    "expected_assists": "xa",
    "expected_assists_per_90": "xa90",
    "_expected_goals_and_expected_assists_per_90": "xgxa90",
    "won_contest": "dribbles90",
    "big_chance_missed": "big_missed",
    "penalty_won": "pens_won",
    "defensive_contributions": "def90",
    "total_tackle": "tackles90",
    "interception": "int90",
    "effective_clearance": "clr90",
    "outfielder_block": "blocks90",
    "ball_recovery": "rec90",
    "penalty_conceded": "pens_con",
    "poss_won_att_3rd": "poss3rd90",
    "clean_sheet": "clean_sheets",
    "_save_percentage": "save_pct",
    "saves": "saves90",
    "_goals_prevented": "goals_prevented",
    "goals_conceded": "gc90",
    "fouls": "fouls90",
    "yellow_card": "yellow",
    "red_card": "red",
}


def _get(url: str, timeout: int = 40) -> dict | list:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def _season_id(name: str) -> str:
    # "2025/2026" → "2526"
    a, _, b = (name or "").partition("/")
    return (a[-2:] + b[-2:]) if a and b else name.replace("/", "")


def _num(v):
    if v in (None, "", "-"):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return int(f) if f == int(f) else round(f, 3)


def fetch_league() -> dict:
    return _get(f"https://www.fotmob.com/api/data/leagues?id={LEAGUE_ID}")


def fetch_stat(season_tid: int, stat_name: str) -> list[dict]:
    lid = LEAGUE_ID
    url = f"https://data.fotmob.com/stats/{lid}/season/{season_tid}/{stat_name}.json"
    data = _get(url)
    lists = data.get("TopLists") or []
    if not lists:
        return []
    return lists[0].get("StatList") or []


def _merge_row(acc: dict, row: dict, stat_name: str) -> None:
    pid = row.get("ParticiantId") or row.get("ParticipantId")
    if not pid:
        return
    pid = int(pid)
    p = acc.get(pid)
    if not p:
        p = {
            "id": pid,
            "name": row.get("ParticipantName") or "",
            "team": row.get("TeamName") or "",
            "team_id": row.get("TeamId"),
            "ccode": row.get("ParticipantCountryCode") or "",
            "minutes": None,
            "matches": None,
            "positions": row.get("Positions") or [],
            "photo": f"https://images.fotmob.com/image_resources/playerimages/{pid}.png",
            "stats": {},
        }
        acc[pid] = p
    if row.get("TeamName"):
        p["team"] = row["TeamName"]
        p["team_id"] = row.get("TeamId")
    mins = _num(row.get("MinutesPlayed"))
    mp = _num(row.get("MatchesPlayed"))
    if mins is not None:
        p["minutes"] = mins
    if mp is not None:
        p["matches"] = mp
    if row.get("Positions"):
        p["positions"] = row["Positions"]
    key = STAT_KEY.get(stat_name, stat_name)
    val = _num(row.get("StatValue"))
    sub = _num(row.get("SubStatValue"))
    p["stats"][key] = val
    if stat_name == "goals" and sub is not None:
        p["stats"]["goals_pen"] = sub
    if stat_name == "goal_assist" and sub is not None:
        p["stats"]["assists_second"] = sub


def _leaders(rows: list[dict], stat_name: str, n: int = 40) -> list[dict]:
    key = STAT_KEY.get(stat_name, stat_name)
    out = []
    for r in rows[:n]:
        out.append({
            "id": r.get("ParticiantId") or r.get("ParticipantId"),
            "name": r.get("ParticipantName"),
            "team": r.get("TeamName"),
            "team_id": r.get("TeamId"),
            "ccode": r.get("ParticipantCountryCode"),
            "value": _num(r.get("StatValue")),
            "sub": _num(r.get("SubStatValue")),
            "minutes": _num(r.get("MinutesPlayed")),
            "matches": _num(r.get("MatchesPlayed")),
            "stat": key,
        })
    return out


def fetch_season(link: dict, player_stats: list[str]) -> dict:
    name = link["Name"]
    tid = int(link["TournamentId"])
    print(f"  sezon {name} ({tid})", flush=True)
    acc: dict[int, dict] = {}
    leaders: dict[str, list] = {}
    for i, stat in enumerate(player_stats):
        try:
            rows = fetch_stat(tid, stat)
        except Exception as e:
            print(f"    skip {stat}: {e}", flush=True)
            time.sleep(SLEEP)
            continue
        key = STAT_KEY.get(stat, stat)
        leaders[key] = _leaders(rows, stat)
        for row in rows:
            _merge_row(acc, row, stat)
        if i % 8 == 0:
            print(f"    {i+1}/{len(player_stats)} {stat} n={len(rows)}", flush=True)
        time.sleep(SLEEP)
    players = sorted(
        acc.values(),
        key=lambda p: (-((p.get("stats") or {}).get("goals") or 0), p.get("name") or ""),
    )
    return {
        "id": _season_id(name),
        "label": name,
        "fotmob_id": tid,
        "n_players": len(players),
        "players": players,
        "leaders": leaders,
    }


def fetch_squads(teams: list[dict]) -> dict:
    out = {}
    for t in teams:
        tid = t.get("id")
        name = t.get("name") or ""
        print(f"  kadro {name} ({tid})", flush=True)
        try:
            raw = _get(f"https://www.fotmob.com/api/data/teams?id={tid}")
        except Exception as e:
            print(f"    skip: {e}", flush=True)
            time.sleep(SLEEP)
            continue
        groups = []
        for g in ((raw.get("squad") or {}).get("squad") or []):
            role = (g.get("title") or "").strip()
            members = []
            for m in g.get("members") or []:
                pid = m.get("id")
                members.append({
                    "id": pid,
                    "name": m.get("name"),
                    "age": m.get("age"),
                    "height": m.get("height"),
                    "born": m.get("dateOfBirth"),
                    "ccode": m.get("ccode"),
                    "country": m.get("cname"),
                    "shirt": m.get("shirt") or m.get("number"),
                    "role": ((m.get("role") or {}).get("key") or role),
                    "photo": f"https://images.fotmob.com/image_resources/playerimages/{pid}.png" if pid else "",
                })
            groups.append({"role": role, "players": members})
        out[str(tid)] = {
            "team_id": tid,
            "name": name,
            "short": t.get("shortName") or name,
            "groups": groups,
            "n": sum(len(g["players"]) for g in groups),
        }
        time.sleep(SLEEP)
    return out


def _table_rows(league: dict) -> list[dict]:
    try:
        rows = league["table"][0]["data"]["table"]["all"]
    except (KeyError, IndexError, TypeError):
        return []
    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "short": r.get("shortName"),
            "played": r.get("played"),
            "w": r.get("wins"),
            "d": r.get("draws"),
            "l": r.get("losses"),
            "gf_ga": r.get("scoresStr"),
            "gd": r.get("goalConDiff"),
            "pts": r.get("pts"),
            "idx": r.get("idx"),
        })
    return out


def fetch_one(lg: dict) -> int:
    global LEAGUE_ID, OUT
    LEAGUE_ID = lg["fotmob"]
    OUT = os.path.join(DATA_DIR, lg["players"])
    print(f"Fotmob {lg['flag']} {lg['name']} oyuncu verisi…", flush=True)
    league = fetch_league()
    links = league.get("stats", {}).get("seasonStatLinks") or []
    player_stats = [
        p.get("name") for p in (league.get("stats", {}).get("players") or [])
        if p.get("name") and not str(p.get("name")).endswith("_team")
    ]
    if not player_stats:
        player_stats = list(STAT_KEY.keys())
    print(f"  {len(links)} sezon · {len(player_stats)} oyuncu istatistiği", flush=True)
    seasons = []
    for link in links:
        seasons.append(fetch_season(link, player_stats))
    table = _table_rows(league)
    squads = fetch_squads(table)
    pack = {
        "src": "fotmob",
        "league": lg["name"],
        "league_id": LEAGUE_ID,
        "updated": datetime.now(TR).isoformat(timespec="seconds"),
        "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seasons": seasons,
        "squads": squads,
        "table": table,
        "stat_keys": STAT_KEY,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT)
    n = sum(s["n_players"] for s in seasons)
    print(f"yazıldı {OUT} · {len(seasons)} sezon · {n} oyuncu-satır · {len(squads)} kadro", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    from bahis.leagues_cfg import LEAGUES, get
    args = [a for a in (argv if argv is not None else sys.argv[1:]) if not a.startswith("-")]
    want = [get(x) for x in args] if args else list(LEAGUES)
    seen = []
    for lg in want:
        if lg["id"] in seen:
            continue
        seen.append(lg["id"])
        fetch_one(lg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
