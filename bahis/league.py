"""Lig maçları — TR + 6 lig, son 10 sezon + güncel fikstür. Emir yok."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from bahis.leagues_cfg import (
    EXTRA_ALIAS,
    current_league,
    get as get_league,
    list_public,
    season_label,
    season_weights,
    set_league,
)

TR = ZoneInfo("Europe/Istanbul")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SEASONS = get_league("tr")["seasons"]
SEASON_LABEL = dict(get_league("tr")["labels"])
_SEASON_W = season_weights("tr")
CURRENT = get_league("tr")["current"]

# folded key → (görünen ad, kısa, renk, api-sports id)
TEAMS = {
    "galatasaray": ("Galatasaray", "GS", "#fdb913", 645),
    "fenerbahce": ("Fenerbahçe", "FB", "#002d72", 611),
    "besiktas": ("Beşiktaş", "BJK", "#111111", 549),
    "trabzonspor": ("Trabzonspor", "TS", "#83051a", 998),
    "basaksehir": ("Başakşehir", "BŞK", "#f47920", 564),
    "alanyaspor": ("Alanyaspor", "ALA", "#f47920", 996),
    "konyaspor": ("Konyaspor", "KON", "#007a33", 607),
    "kasimpasa": ("Kasımpaşa", "KAS", "#ffffff", 1004),
    "gaziantep": ("Gaziantep", "GZT", "#c8102e", 3573),
    "rizespor": ("Rizespor", "RZE", "#00783e", 1007),
    "samsunspor": ("Samsunspor", "SAM", "#d50032", 3603),
    "goztepe": ("Göztepe", "GÖZ", "#c8102e", 994),
    "eyupspor": ("Eyüpspor", "EYÜ", "#6d1a36", 3588),
    "genclerbirligi": ("Gençlerbirliği", "GEN", "#c8102e", 997),
    "kocaelispor": ("Kocaelispor", "KOC", "#007a33", 7411),
    "amedspor": ("Amedspor", "AMD", "#d50032", 3579),
    "erzurumspor": ("Erzurumspor", "ERZ", "#0033a0", 1009),
    "corum": ("Çorum FK", "ÇOR", "#e30613", 6343),
    "antalyaspor": ("Antalyaspor", "ANT", "#c8102e", 1005),
    "kayserispor": ("Kayserispor", "KAY", "#c8102e", 1001),
    "sivasspor": ("Sivasspor", "SİV", "#c8102e", 1002),
    "hatayspor": ("Hatayspor", "HTY", "#6d1a36", 3575),
    "adanaspor": ("Adana Demirspor", "ADS", "#0033a0", 3563),
    "karagumruk": ("F. Karagümrük", "KRG", "#c8102e", 3589),
    "ankaragucu": ("Ankaragücü", "AGÜ", "#0033a0", 1010),
    "giresunspor": ("Giresunspor", "GRS", "#007a33", 3574),
    "istanbulspor": ("İstanbulspor", "İST", "#c8102e", 3578),
    "pendikspor": ("Pendikspor", "PEN", "#c8102e", 3601),
    "umraniyespor": ("Ümraniyespor", "ÜMR", "#c8102e", 3577),
    "bodrumspor": ("Bodrum FK", "BOD", "#0033a0", 3583),
    "altay": ("Altay", "ALT", "#000000", 1000),
    "yenimalatyaspor": ("Y. Malatyaspor", "MLT", "#c8102e", 999),
}

_ALIAS = {
    "buyuksehyr": "basaksehir",
    "istanbulbasaksehir": "basaksehir",
    "caykurrizespor": "rizespor",
    "rizespor": "rizespor",
    "goztep": "goztepe",
    "eyupspor": "eyupspor",
    "addemirspor": "adanaspor",
    "adanademirspor": "adanaspor",
    "fenerbahce": "fenerbahce",
    "genclerbirligi": "genclerbirligi",
    "corumfk": "corum",
    "amedsportif": "amedspor",
    "amedsk": "amedspor",
    "gaziantepfk": "gaziantep",
    "gazisehirgaziantep": "gaziantep",
    "erzurumsporfk": "erzurumspor",
    **EXTRA_ALIAS,
}


def _fold(name: str) -> str:
    s = (name or "").strip().lower()
    for a, b in (
        ("ç", "c"), ("ğ", "g"), ("ı", "i"), ("ö", "o"), ("ş", "s"), ("ü", "u"),
        ("â", "a"), ("î", "i"), ("û", "u"), (".", ""), (" ", ""), ("-", ""),
        ("'", ""),
    ):
        s = s.replace(a, b)
    return s


def team_key(name: str) -> str:
    folded = _fold(name)
    return _ALIAS.get(folded, folded)


@lru_cache(maxsize=16)
def _overlay(league: str) -> dict[str, dict]:
    path = os.path.join(DATA_DIR, f"teams_{league}.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict] = {}
    for name, info in (raw or {}).items():
        if not isinstance(info, dict):
            continue
        out[team_key(name)] = info
        if info.get("name"):
            out[team_key(info["name"])] = info
    return out


def team_info(name: str) -> dict:
    key = team_key(name)
    raw = TEAMS.get(key)
    ov = _overlay(current_league()).get(key)
    if raw and len(raw) >= 3:
        label, short, color = raw[0], raw[1], raw[2]
        tid = raw[3] if len(raw) > 3 else 0
        crest = f"https://media.api-sports.io/football/teams/{tid}.png" if tid else ""
        if ov and ov.get("crest"):
            crest = ov["crest"]
        return {"key": key, "name": label, "short": short, "color": color, "crest": crest}
    if ov:
        label = ov.get("name") or name
        short = ov.get("short") or (label or "?")[:3].upper()
        return {
            "key": key,
            "name": label,
            "short": short,
            "color": "#00df81",
            "crest": ov.get("crest") or "",
        }
    label, short, color = name, (name or "?")[:3].upper(), "#00df81"
    return {"key": key, "name": label, "short": short, "color": color, "crest": ""}


def _f(v):
    try:
        if v in (None, "", "-"):
            return None
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        if v in (None, ""):
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _parse_date(date_s: str, time_s: str | None = None) -> datetime | None:
    date_s = (date_s or "").strip()
    time_s = (time_s or "00:00").strip() or "00:00"
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            d = datetime.strptime(f"{date_s} {time_s}", f"{fmt} %H:%M")
            return d.replace(tzinfo=TR)
        except ValueError:
            continue
    return None


def _parse_utc(s: str) -> datetime | None:
    s = (s or "").strip().replace("Z", "")
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc).astimezone(TR)
        except ValueError:
            continue
    return None


def _odds(row: dict) -> dict:
    open_h = _f(row.get("B365H") or row.get("AvgH") or row.get("PSH"))
    open_d = _f(row.get("B365D") or row.get("AvgD") or row.get("PSD"))
    open_a = _f(row.get("B365A") or row.get("AvgA") or row.get("PSA"))
    close_h = _f(row.get("B365CH") or row.get("AvgCH") or row.get("PSCH"))
    close_d = _f(row.get("B365CD") or row.get("AvgCD") or row.get("PSCD"))
    close_a = _f(row.get("B365CA") or row.get("AvgCA") or row.get("PSCA"))
    h = close_h or open_h
    d = close_d or open_d
    a = close_a or open_a
    ou_o = _f(row.get("Avg>2.5") or row.get("B365>2.5"))
    ou_u = _f(row.get("Avg<2.5") or row.get("B365<2.5"))
    ou_co = _f(row.get("AvgC>2.5") or row.get("B365C>2.5"))
    ou_cu = _f(row.get("AvgC<2.5") or row.get("B365C<2.5"))
    return {
        "home": h, "draw": d, "away": a,
        "open": {"home": open_h, "draw": open_d, "away": open_a},
        "close": {"home": close_h, "draw": close_d, "away": close_a},
        "avg": {
            "home": _f(row.get("AvgH")),
            "draw": _f(row.get("AvgD")),
            "away": _f(row.get("AvgA")),
        },
        "max": {
            "home": _f(row.get("MaxH")),
            "draw": _f(row.get("MaxD")),
            "away": _f(row.get("MaxA")),
        },
        "ou25": {
            "over": ou_co or ou_o,
            "under": ou_cu or ou_u,
            "open": {"over": ou_o, "under": ou_u},
            "close": {"over": ou_co, "under": ou_cu},
        },
    }


def _match_id(dt: datetime | None, home: str, away: str, league: str | None = None) -> str:
    lid = league or current_league()
    day = dt.strftime("%Y%m%d") if dt else "00000000"
    body = f"{day}-{team_key(home)}-{team_key(away)}"
    if lid == "tr":
        return body
    return f"{lid}-{body}"


def _from_csv_row(row: dict, season: str, league: str | None = None) -> dict | None:
    home = (row.get("HomeTeam") or row.get("Home") or "").strip()
    away = (row.get("AwayTeam") or row.get("Away") or "").strip()
    if not home or not away:
        return None
    lid = league or current_league()
    dt = _parse_date(row.get("Date") or "", row.get("Time"))
    hg, ag = _i(row.get("FTHG") or row.get("HG")), _i(row.get("FTAG") or row.get("AG"))
    played = hg is not None and ag is not None
    return {
        "id": _match_id(dt, home, away, lid),
        "league": lid,
        "season": season,
        "season_label": season_label(lid, season),
        "week": None,
        "kickoff": dt.isoformat() if dt else None,
        "venue": None,
        "home": team_info(home),
        "away": team_info(away),
        "hg": hg,
        "ag": ag,
        "hthg": _i(row.get("HTHG")),
        "htag": _i(row.get("HTAG")),
        "hc": _i(row.get("HC")),
        "ac": _i(row.get("AC")),
        "hy": _i(row.get("HY")),
        "ay": _i(row.get("AY")),
        "hr": _i(row.get("HR")),
        "ar": _i(row.get("AR")),
        "hs": _i(row.get("HS")),
        "as_s": _i(row.get("AS")),
        "hst": _i(row.get("HST")),
        "ast": _i(row.get("AST")),
        "hxg": _f(row.get("HxG") or row.get("HomeXG")),
        "axg": _f(row.get("AxG") or row.get("AwayXG")),
        "result": (row.get("FTR") or "").strip() or None,
        "played": played,
        "odds": _odds(row),
        "src": "fd",
    }


def _from_fix_row(row: dict, league: str | None = None) -> dict | None:
    home = (row.get("HomeTeam") or "").strip()
    away = (row.get("AwayTeam") or "").strip()
    if not home or not away:
        return None
    lid = league or current_league()
    lg = get_league(lid)
    dt = _parse_utc(row.get("DateUtc") or "")
    hg, ag = _i(row.get("HomeTeamScore")), _i(row.get("AwayTeamScore"))
    played = hg is not None and ag is not None
    result = None
    if played:
        result = "H" if hg > ag else ("A" if ag > hg else "D")
    return {
        "id": _match_id(dt, home, away, lid),
        "league": lid,
        "season": lg["current"],
        "season_label": season_label(lid, lg["current"]),
        "week": _i(row.get("RoundNumber")),
        "kickoff": dt.isoformat() if dt else None,
        "venue": (row.get("Location") or "").strip() or None,
        "home": team_info(home),
        "away": team_info(away),
        "hg": hg,
        "ag": ag,
        "result": result,
        "played": played,
        "odds": {"home": None, "draw": None, "away": None},
        "fotmob_id": row.get("FotmobId") or row.get("fotmob_id"),
        "src": "fix",
    }


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k in ("week", "venue"):
        if not out.get(k) and b.get(k):
            out[k] = b[k]
    if not out.get("played") and b.get("played"):
        out["played"] = True
        out["hg"] = b.get("hg")
        out["ag"] = b.get("ag")
        out["result"] = b.get("result")
    if not out.get("kickoff") and b.get("kickoff"):
        out["kickoff"] = b["kickoff"]
    if not out.get("fotmob_id") and b.get("fotmob_id"):
        out["fotmob_id"] = b["fotmob_id"]
    for k in ("hxg", "axg"):
        if out.get(k) is None and b.get(k) is not None:
            out[k] = b[k]
    od = out.get("odds") or {}
    if od.get("home") is None:
        out["odds"] = b.get("odds") or od
    for k in ("hthg", "htag", "hc", "ac", "hy", "ay", "hr", "ar", "hs", "as_s", "hst", "ast"):
        if out.get(k) is None and b.get(k) is not None:
            out[k] = b[k]
    return out


def _load_raw(league: str | None = None) -> list[dict]:
    lg = get_league(league)
    lid = lg["id"]
    set_league(lid)
    by_id: dict[str, dict] = {}
    for season in lg["seasons"]:
        path = os.path.join(DATA_DIR, f"{lg['fd']}_{season}.csv")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                m = _from_csv_row(row, season, lid)
                if not m:
                    continue
                if not m["played"] and season != lg["current"]:
                    continue
                by_id[m["id"]] = m
    if lid == "tr":
        fix_csv = os.path.join(DATA_DIR, "fixtures.csv")
        if os.path.isfile(fix_csv):
            with open(fix_csv, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    if (row.get("Div") or "").strip() != "T1":
                        continue
                    m = _from_csv_row(row, lg["current"], lid)
                    if not m:
                        continue
                    m["src"] = "fixcsv"
                    prev = by_id.get(m["id"])
                    by_id[m["id"]] = _merge(prev, m) if prev else m
    fix_json = os.path.join(DATA_DIR, lg["fix_json"])
    if os.path.isfile(fix_json):
        with open(fix_json, encoding="utf-8") as f:
            rows = json.load(f)
        for row in rows:
            m = _from_fix_row(row, lid)
            if not m:
                continue
            prev = by_id.get(m["id"])
            by_id[m["id"]] = _merge(prev, m) if prev else m
    return sorted(
        by_id.values(),
        key=lambda x: x.get("kickoff") or "9999",
    )


@lru_cache(maxsize=8)
def _all_matches_cached(league: str) -> tuple[dict, ...]:
    return tuple(_load_raw(league))


def all_matches(league: str | None = None) -> tuple[dict, ...]:
    lid = get_league(league)["id"] if league else current_league()
    return _all_matches_cached(lid)


def reload_matches() -> None:
    _all_matches_cached.cache_clear()
    _overlay.cache_clear()
    _forms_for.cache_clear()
    _predict_for.cache_clear()
    try:
        from bahis.dixon_coles import _fitted_for
        _fitted_for.cache_clear()
    except Exception:
        pass
    try:
        from bahis.elo import _fitted_for as _elo_fit_for
        _elo_fit_for.cache_clear()
    except Exception:
        pass
    try:
        from bahis.match_intel import _played_for
        _played_for.cache_clear()
    except Exception:
        pass
    try:
        from bahis.features import clear_caches
        clear_caches()
    except Exception:
        pass


def _implied(h2h: dict) -> dict:
    hw, d, aw = h2h["home_w"], h2h["draw"], h2h["away_w"]
    n = hw + d + aw
    if n < 2:
        return {"home": 2.2, "draw": 3.3, "away": 3.2}
    # Laplace + ev avantajı
    ph = (hw + 1.2) / (n + 3)
    pd = (d + 1.0) / (n + 3)
    pa = (aw + 0.8) / (n + 3)
    s = ph + pd + pa
    ph, pd, pa = ph / s, pd / s, pa / s
    margin = 1.06
    return {
        "home": round(margin / ph, 2),
        "draw": round(margin / pd, 2),
        "away": round(margin / pa, 2),
    }


def _fill_odds(m: dict, h2h_fn) -> dict:
    od = m.get("odds") or {}
    if od.get("home") and od.get("draw") and od.get("away"):
        return od
    return h2h_fn(m["home"]["key"], m["away"]["key"])["odds"]


def h2h(a: str, b: str) -> dict:
    ka, kb = team_key(a), team_key(b)
    rows = []
    hw = dw = aw = 0
    gf_a = ga_a = 0
    for m in all_matches():
        if not m["played"]:
            continue
        keys = {m["home"]["key"], m["away"]["key"]}
        if keys != {ka, kb}:
            continue
        rows.append(m)
        if m["home"]["key"] == ka:
            gf_a += m["hg"] or 0
            ga_a += m["ag"] or 0
            if m["result"] == "H":
                hw += 1
            elif m["result"] == "A":
                aw += 1
            else:
                dw += 1
        else:
            gf_a += m["ag"] or 0
            ga_a += m["hg"] or 0
            if m["result"] == "A":
                hw += 1
            elif m["result"] == "H":
                aw += 1
            else:
                dw += 1
    rows.sort(key=lambda x: x.get("kickoff") or "", reverse=True)
    pack = {
        "a": team_info(ka),
        "b": team_info(kb),
        "n": len(rows),
        "home_w": hw,
        "draw": dw,
        "away_w": aw,
        "gf": gf_a,
        "ga": ga_a,
        "matches": rows[:20],
    }
    pack["odds"] = _implied(pack)
    return pack


@lru_cache(maxsize=32)
def _forms_for(league: str, n: int = 5) -> dict[str, tuple[str, ...]]:
    acc: dict[str, list[str]] = {}
    for m in reversed(all_matches(league)):
        if not m["played"]:
            continue
        hk, ak = m["home"]["key"], m["away"]["key"]
        if m["result"] == "H":
            hr, ar = "W", "L"
        elif m["result"] == "A":
            hr, ar = "L", "W"
        else:
            hr = ar = "D"
        if len(acc.get(hk, [])) < n:
            acc.setdefault(hk, []).append(hr)
        if len(acc.get(ak, [])) < n:
            acc.setdefault(ak, []).append(ar)
    return {k: tuple(v) for k, v in acc.items()}


def _forms(n: int = 5) -> dict[str, tuple[str, ...]]:
    return _forms_for(current_league(), n)


def form(key: str, n: int = 5) -> list[str]:
    return list(_forms(n).get(team_key(key), ()))


def _form_pts(key: str, n: int = 8) -> float:
    seq = list(_forms(n).get(team_key(key), ()))
    if not seq:
        return 0.42
    pts = sum(3 if x == "W" else 1 if x == "D" else 0 for x in seq)
    return pts / (3 * max(len(seq), 1))


@lru_cache(maxsize=2048)
def _predict_for(league: str, home: str, away: str) -> dict:
    """10 yıl H2H + form + ev avantajı. Bahis değil, çıkarım."""
    hk, ak = team_key(home), team_key(away)
    hi, ai = team_info(hk), team_info(ak)
    wh = wd = wa = 0.0
    n = 0
    weights = season_weights(league)
    for m in all_matches(league):
        if not m["played"]:
            continue
        if {m["home"]["key"], m["away"]["key"]} != {hk, ak}:
            continue
        w = weights.get(m["season"], 0.5)
        n += 1
        home_won = (
            (m["home"]["key"] == hk and m["result"] == "H")
            or (m["away"]["key"] == hk and m["result"] == "A")
        )
        away_won = (
            (m["home"]["key"] == ak and m["result"] == "H")
            or (m["away"]["key"] == ak and m["result"] == "A")
        )
        if home_won:
            wh += w
        elif away_won:
            wa += w
        else:
            wd += w
    tot = wh + wd + wa
    if tot < 0.01:
        h2h_h = h2h_d = h2h_a = 1 / 3
    else:
        h2h_h, h2h_d, h2h_a = wh / tot, wd / tot, wa / tot
    fh, fa = _form_pts(hk), _form_pts(ak)
    # Süper Lig taban: ev ~%45 · X ~%28 · deplasman ~%27 + form
    ph = 0.16 + 0.38 * h2h_h + 0.20 * fh + 0.10
    pd = 0.10 + 0.38 * h2h_d + 0.12 * (1 - abs(fh - fa))
    pa = 0.12 + 0.38 * h2h_a + 0.20 * fa
    s = ph + pd + pa
    ph, pd, pa = ph / s, pd / s, pa / s
    if ph >= pd and ph >= pa:
        pick, p = "H", ph
        text = f"Bence {hi['name']} kazanır"
    elif pa >= pd:
        pick, p = "A", pa
        text = f"Bence {ai['name']} kazanır"
    else:
        pick, p = "D", pd
        text = "Bence beraberlik"
    return {
        "pick": pick,
        "p": round(p, 3),
        "pct": int(round(p * 100)),
        "probs": {"H": round(ph, 3), "D": round(pd, 3), "A": round(pa, 3)},
        "text": text,
        "why": f"10 yıl {n} H2H · form {hi['short']} {int(fh*100)}/{ai['short']} {int(fa*100)}",
        "h2h_n": n,
    }


def predict(home: str, away: str) -> dict:
    return _predict_for(current_league(), team_key(home), team_key(away))


def _now() -> datetime:
    return datetime.now(TR)


def summary() -> dict:
    lg = get_league()
    ms = all_matches(lg["id"])
    now = _now()
    played = [m for m in ms if m["played"]]
    upcoming = [
        m for m in ms
        if m["season"] == lg["current"]
        and not m["played"]
        and m.get("kickoff")
        and m["kickoff"] >= now.isoformat()[:10]
    ]
    today = now.date().isoformat()
    live = []
    for m in ms:
        ko = m.get("kickoff")
        if not ko:
            continue
        d = ko[:10]
        if d == today:
            live.append(m)
    current_teams = sorted(
        {m["home"]["key"] for m in ms if m["season"] == lg["current"]}
        | {m["away"]["key"] for m in ms if m["season"] == lg["current"]}
    )
    goals = []
    for s in lg["seasons"]:
        rows = [m for m in played if m["season"] == s]
        g = sum((m.get("hg") or 0) + (m.get("ag") or 0) for m in rows)
        goals.append({"id": s, "label": season_label(lg["id"], s), "n": len(rows), "goals": g})
    latest = [_public(m, extra=False) for m in played[-8:][::-1]]
    return {
        "league": lg["name"],
        "league_id": lg["id"],
        "leagues": list_public(),
        "seasons": [{"id": s, "label": season_label(lg["id"], s)} for s in lg["seasons"]],
        "current": lg["current"],
        "teams": [team_info(k) for k in current_teams],
        "played_n": len(played),
        "upcoming_n": len(upcoming),
        "today": [_public(m) for m in live],
        "next": [_public(m) for m in upcoming[:12]],
        "latest": latest,
        "goals_by_season": goals,
        "updated": now.isoformat(timespec="seconds"),
    }


def _public(m: dict, extra: bool = True) -> dict:
    od = m.get("odds") or {}
    h = None
    if extra and not (od.get("home") and od.get("draw") and od.get("away")):
        h = h2h(m["home"]["key"], m["away"]["key"])
        od = h["odds"]
    ko = m.get("kickoff")
    when = ""
    if ko:
        try:
            dt = datetime.fromisoformat(ko)
            when = dt.strftime("%d.%m %H:%M")
        except ValueError:
            when = ko
    out = {**m, "odds": od, "when": when}
    if extra:
        out["form_h"] = form(m["home"]["key"])
        out["form_a"] = form(m["away"]["key"])
        out["h2h_n"] = h["n"] if h else None
        out["tip"] = predict(m["home"]["key"], m["away"]["key"])
    return out


def list_matches(season: str | None = None, team: str | None = None, status: str = "all") -> list[dict]:
    tk = team_key(team) if team else None
    out = []
    now = _now().isoformat()
    for m in all_matches():
        if season and m["season"] != season:
            continue
        if tk and tk not in (m["home"]["key"], m["away"]["key"]):
            continue
        if status == "played" and not m["played"]:
            continue
        if status == "upcoming":
            if m["played"] or not m.get("kickoff") or m["kickoff"] < now[:10]:
                continue
            if not season and m["season"] != get_league()["current"]:
                continue
        out.append(_public(m, extra=(status != "played")))
    if status == "played":
        out.reverse()
    return out


def pair_h2h(a: str, b: str) -> dict:
    pack = h2h(a, b)
    pack["form_a"] = form(pack["a"]["key"])
    pack["form_b"] = form(pack["b"]["key"])
    pack["matches"] = [_public(m) for m in pack["matches"]]
    # bu sezon kim kiminle oynayacak
    ka, kb = pack["a"]["key"], pack["b"]["key"]
    future = []
    cur = get_league()["current"]
    for m in all_matches():
        if m["season"] != cur or m["played"]:
            continue
        if {m["home"]["key"], m["away"]["key"]} == {ka, kb}:
            future.append(_public(m))
    pack["upcoming"] = future
    pack["tip"] = predict(ka, kb)
    try:
        from bahis.players import pair_scorers
        pack["scorers"] = pair_scorers(ka, kb)
    except Exception:
        pack["scorers"] = {"a": [], "b": []}
    return pack


def find_match(mid: str) -> dict | None:
    from bahis.leagues_cfg import league_from_id
    lid = league_from_id(mid)
    set_league(lid)
    for m in all_matches(lid):
        if m["id"] == mid:
            return m
    if lid != "tr":
        set_league("tr")
        for m in all_matches("tr"):
            if m["id"] == mid:
                return m
    return None
