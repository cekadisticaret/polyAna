"""Süper Lig (1. Lig) — son 10 sezon + 2026/27 fikstür. Emir yok."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

TR = ZoneInfo("Europe/Istanbul")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SEASONS = (
    "1617", "1718", "1819", "1920", "2021",
    "2122", "2223", "2324", "2425", "2526", "2627",
)
SEASON_LABEL = {
    "1617": "2016/17",
    "1718": "2017/18",
    "1819": "2018/19",
    "1920": "2019/20",
    "2021": "2020/21",
    "2122": "2021/22",
    "2223": "2022/23",
    "2324": "2023/24",
    "2425": "2024/25",
    "2526": "2025/26",
    "2627": "2026/27",
}
_SEASON_W = {s: 0.32 + i * 0.068 for i, s in enumerate(SEASONS)}
CURRENT = "2627"

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


def team_info(name: str) -> dict:
    key = team_key(name)
    raw = TEAMS.get(key)
    if raw and len(raw) >= 3:
        label, short, color = raw[0], raw[1], raw[2]
        tid = raw[3] if len(raw) > 3 else 0
    else:
        label, short, color, tid = name, (name or "?")[:3].upper(), "#00df81", 0
    crest = f"https://media.api-sports.io/football/teams/{tid}.png" if tid else ""
    return {"key": key, "name": label, "short": short, "color": color, "crest": crest}


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
    h = _f(row.get("AvgH") or row.get("B365H"))
    d = _f(row.get("AvgD") or row.get("B365D"))
    a = _f(row.get("AvgA") or row.get("B365A"))
    return {"home": h, "draw": d, "away": a}


def _match_id(dt: datetime | None, home: str, away: str) -> str:
    day = dt.strftime("%Y%m%d") if dt else "00000000"
    return f"{day}-{team_key(home)}-{team_key(away)}"


def _from_csv_row(row: dict, season: str) -> dict | None:
    home = (row.get("HomeTeam") or "").strip()
    away = (row.get("AwayTeam") or "").strip()
    if not home or not away:
        return None
    dt = _parse_date(row.get("Date") or "", row.get("Time"))
    hg, ag = _i(row.get("FTHG")), _i(row.get("FTAG"))
    played = hg is not None and ag is not None
    return {
        "id": _match_id(dt, home, away),
        "season": season,
        "season_label": SEASON_LABEL.get(season, season),
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
        "result": (row.get("FTR") or "").strip() or None,
        "played": played,
        "odds": _odds(row),
        "src": "fd",
    }


def _from_fix_row(row: dict) -> dict | None:
    home = (row.get("HomeTeam") or "").strip()
    away = (row.get("AwayTeam") or "").strip()
    if not home or not away:
        return None
    dt = _parse_utc(row.get("DateUtc") or "")
    hg, ag = _i(row.get("HomeTeamScore")), _i(row.get("AwayTeamScore"))
    played = hg is not None and ag is not None
    result = None
    if played:
        result = "H" if hg > ag else ("A" if ag > hg else "D")
    return {
        "id": _match_id(dt, home, away),
        "season": CURRENT,
        "season_label": SEASON_LABEL[CURRENT],
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
    od = out.get("odds") or {}
    if od.get("home") is None:
        out["odds"] = b.get("odds") or od
    for k in ("hthg", "htag", "hc", "ac", "hy", "ay", "hr", "ar", "hs", "as_s", "hst", "ast"):
        if out.get(k) is None and b.get(k) is not None:
            out[k] = b[k]
    return out


def _load_raw() -> list[dict]:
    by_id: dict[str, dict] = {}
    for season in SEASONS:
        path = os.path.join(DATA_DIR, f"T1_{season}.csv")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                m = _from_csv_row(row, season)
                if m:
                    by_id[m["id"]] = m
    fix_csv = os.path.join(DATA_DIR, "fixtures.csv")
    if os.path.isfile(fix_csv):
        with open(fix_csv, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if (row.get("Div") or "").strip() != "T1":
                    continue
                m = _from_csv_row(row, CURRENT)
                if not m:
                    continue
                m["src"] = "fixcsv"
                prev = by_id.get(m["id"])
                by_id[m["id"]] = _merge(prev, m) if prev else m
    fix_json = os.path.join(DATA_DIR, "superlig_2026_fixtures.json")
    if os.path.isfile(fix_json):
        with open(fix_json, encoding="utf-8") as f:
            rows = json.load(f)
        for row in rows:
            m = _from_fix_row(row)
            if not m:
                continue
            prev = by_id.get(m["id"])
            by_id[m["id"]] = _merge(prev, m) if prev else m
    return sorted(
        by_id.values(),
        key=lambda x: x.get("kickoff") or "9999",
    )


@lru_cache(maxsize=1)
def all_matches() -> tuple[dict, ...]:
    return tuple(_load_raw())


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


@lru_cache(maxsize=4)
def _forms(n: int = 5) -> dict[str, tuple[str, ...]]:
    acc: dict[str, list[str]] = {}
    for m in reversed(all_matches()):
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


def form(key: str, n: int = 5) -> list[str]:
    return list(_forms(n).get(team_key(key), ()))


def _form_pts(key: str, n: int = 8) -> float:
    seq = list(_forms(n).get(team_key(key), ()))
    if not seq:
        return 0.42
    pts = sum(3 if x == "W" else 1 if x == "D" else 0 for x in seq)
    return pts / (3 * max(len(seq), 1))


@lru_cache(maxsize=512)
def predict(home: str, away: str) -> dict:
    """10 yıl H2H + form + ev avantajı. Bahis değil, çıkarım."""
    hk, ak = team_key(home), team_key(away)
    hi, ai = team_info(hk), team_info(ak)
    wh = wd = wa = 0.0
    n = 0
    for m in all_matches():
        if not m["played"]:
            continue
        if {m["home"]["key"], m["away"]["key"]} != {hk, ak}:
            continue
        w = _SEASON_W.get(m["season"], 0.5)
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


def _now() -> datetime:
    return datetime.now(TR)


def summary() -> dict:
    ms = all_matches()
    now = _now()
    played = [m for m in ms if m["played"]]
    upcoming = [
        m for m in ms
        if not m["played"] and m.get("kickoff") and m["kickoff"] >= now.isoformat()[:10]
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
        {m["home"]["key"] for m in ms if m["season"] == CURRENT}
        | {m["away"]["key"] for m in ms if m["season"] == CURRENT}
    )
    goals = []
    for s in SEASONS:
        rows = [m for m in played if m["season"] == s]
        g = sum((m.get("hg") or 0) + (m.get("ag") or 0) for m in rows)
        goals.append({"id": s, "label": SEASON_LABEL[s], "n": len(rows), "goals": g})
    latest = [_public(m, extra=False) for m in played[-8:][::-1]]
    return {
        "league": "Trendyol Süper Lig",
        "seasons": [{"id": s, "label": SEASON_LABEL[s]} for s in SEASONS],
        "current": CURRENT,
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
        if status == "upcoming" and (m["played"] or not m.get("kickoff") or m["kickoff"] < now[:10]):
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
    for m in all_matches():
        if m["season"] != CURRENT or m["played"]:
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
