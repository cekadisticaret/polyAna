"""Lig CSV + Fotmob fikstür çekimi. Emir yok.

  python3 bahis/fetch_leagues.py            # tüm ligler
  python3 bahis/fetch_leagues.py epl bra    # seçili
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/csv,*/*",
    "Accept-Encoding": "gzip",
}

sys.path.insert(0, os.path.dirname(_DIR))

from bahis.leagues_cfg import LEAGUES, get  # noqa: E402


def _get(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    os.replace(tmp, path)


def _write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def fetch_euro_season(fd: str, season: str) -> tuple[int, str | None]:
    url = f"https://www.football-data.co.uk/mmz4281/{season}/{fd}.csv"
    path = os.path.join(DATA, f"{fd}_{season}.csv")
    try:
        raw = _get(url)
    except urllib.error.HTTPError as e:
        if e.code in (300, 404, 410):
            return 0, "yok"
        return 0, f"{fd} {season}: HTTP {e.code}"
    except Exception as e:
        return 0, f"{fd} {season}: {e}"
    text = raw.decode("utf-8-sig", errors="replace")
    if "HomeTeam" not in text[:240] and "Home" not in text[:240]:
        return 0, f"{fd} {season}: csv değil"
    _write(path, text)
    n = sum(1 for _ in csv.DictReader(io.StringIO(text)))
    return n, None


def _bra_to_euro(row: dict) -> dict:
    res = (row.get("Res") or "").strip().upper()
    return {
        "Div": "BRA",
        "Date": row.get("Date") or "",
        "Time": row.get("Time") or "",
        "HomeTeam": row.get("Home") or "",
        "AwayTeam": row.get("Away") or "",
        "FTHG": row.get("HG") or "",
        "FTAG": row.get("AG") or "",
        "FTR": res,
        "AvgH": row.get("AvgH") or row.get("PH") or "",
        "AvgD": row.get("AvgD") or row.get("PD") or "",
        "AvgA": row.get("AvgA") or row.get("PA") or "",
        "B365H": row.get("PH") or "",
        "B365D": row.get("PD") or "",
        "B365A": row.get("PA") or "",
        "Season": row.get("Season") or "",
    }


def fetch_brazil() -> tuple[int, str | None]:
    url = "https://www.football-data.co.uk/new/BRA.csv"
    try:
        raw = _get(url)
    except Exception as e:
        return 0, f"BRA: {e}"
    text = raw.decode("utf-8-sig", errors="replace")
    if "Home" not in text[:200]:
        return 0, "BRA: csv değil"
    rows = list(csv.DictReader(io.StringIO(text)))
    by_year: dict[str, list[dict]] = {}
    for row in rows:
        year = str(row.get("Season") or "").strip()
        if len(year) == 2:
            year = "20" + year
        if not year.isdigit():
            continue
        by_year.setdefault(year, []).append(_bra_to_euro(row))
    n = 0
    fields = [
        "Div", "Date", "Time", "HomeTeam", "AwayTeam",
        "FTHG", "FTAG", "FTR", "AvgH", "AvgD", "AvgA", "B365H", "B365D", "B365A",
    ]
    for year, chunk in by_year.items():
        path = os.path.join(DATA, f"BRA_{year}.csv")
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in chunk:
            w.writerow(r)
        _write(path, buf.getvalue())
        n += len(chunk)
    return n, None


def _fotmob_score(m: dict) -> tuple[int | None, int | None]:
    st = m.get("status") or {}
    if st.get("cancelled") or st.get("awarded"):
        return None, None
    hs = st.get("scoreStr") or ""
    if isinstance(hs, str) and "-" in hs and st.get("finished"):
        a, b = hs.split("-", 1)
        try:
            return int(a.strip()), int(b.strip())
        except ValueError:
            pass
    home = (m.get("home") or {}).get("score")
    away = (m.get("away") or {}).get("score")
    if home is not None and away is not None and st.get("finished"):
        try:
            return int(home), int(away)
        except (TypeError, ValueError):
            pass
    return None, None


def fetch_fotmob_payload(lg: dict) -> tuple[dict | None, str | None]:
    url = f"https://www.fotmob.com/api/data/leagues?id={lg['fotmob']}"
    try:
        return json.loads(_get(url)), None
    except Exception as e:
        return None, f"fotmob {lg['id']}: {e}"


def fotmob_fixture_rows(data: dict) -> list[dict]:
    matches = (
        ((data.get("fixtures") or {}).get("allMatches"))
        or ((data.get("overview") or {}).get("matches") or {}).get("allMatches")
        or []
    )
    rows = []
    for i, m in enumerate(matches, 1):
        hn = (m.get("home") or {}).get("name") or ""
        an = (m.get("away") or {}).get("name") or ""
        if not hn or not an:
            continue
        utc = (m.get("status") or {}).get("utcTime") or m.get("utcTime") or ""
        utc = str(utc).replace("Z", "").split(".")[0]
        if utc and "T" in utc:
            utc = utc.replace("T", " ")
        if utc and len(utc) == 16:
            utc = utc + ":00"
        hg, ag = _fotmob_score(m)
        winner = ""
        if hg is not None and ag is not None:
            winner = "Draw" if hg == ag else (hn if hg > ag else an)
        rnd = m.get("round") or (m.get("status") or {}).get("roundName") or ""
        try:
            week = int(str(rnd).split()[-1])
        except (TypeError, ValueError):
            week = None
        rows.append({
            "MatchNumber": i,
            "RoundNumber": week,
            "DateUtc": (utc + "Z") if utc and not utc.endswith("Z") else utc,
            "Location": (m.get("home") or {}).get("stadium") or "",
            "HomeTeam": hn,
            "AwayTeam": an,
            "Group": None,
            "HomeTeamScore": hg,
            "AwayTeamScore": ag,
            "Winner": winner,
            "FotmobId": m.get("id"),
        })
    return rows


def write_fotmob_fixtures(lg: dict, rows: list[dict], data: dict | None = None) -> int:
    """TR fikstürü ayrı kaynak — skor/id birleştir. Diğer ligler her tur yenilenir."""
    path = os.path.join(DATA, lg["fix_json"])
    if lg["id"] != "tr":
        _write_json(path, rows)
    elif not os.path.isfile(path):
        _write_json(path, rows)
    else:
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
        except (OSError, json.JSONDecodeError):
            old = []
        from bahis.league import team_key
        by = {}
        for r in rows:
            key = (
                str(r.get("DateUtc") or "")[:10],
                team_key(r.get("HomeTeam") or ""),
                team_key(r.get("AwayTeam") or ""),
            )
            by[key] = r
        changed = False
        for r in old:
            key = (
                str(r.get("DateUtc") or "")[:10],
                team_key(r.get("HomeTeam") or ""),
                team_key(r.get("AwayTeam") or ""),
            )
            src = by.get(key)
            if not src:
                continue
            if src.get("FotmobId") and r.get("FotmobId") != src.get("FotmobId"):
                r["FotmobId"] = src["FotmobId"]
                changed = True
            if src.get("HomeTeamScore") is not None and r.get("HomeTeamScore") != src.get("HomeTeamScore"):
                r["HomeTeamScore"] = src["HomeTeamScore"]
                r["AwayTeamScore"] = src["AwayTeamScore"]
                r["Winner"] = src.get("Winner")
                changed = True
        if changed:
            _write_json(path, old)
    if data is not None:
        table = []
        try:
            table = data["table"][0]["data"]["table"]["all"]
        except (KeyError, IndexError, TypeError):
            table = []
        teams = {}
        for r in table:
            name = r.get("name") or ""
            tid = r.get("id")
            if not name:
                continue
            teams[name] = {
                "name": name,
                "short": r.get("shortName") or name[:3].upper(),
                "fotmob": tid,
                "crest": f"https://images.fotmob.com/image_resources/logo/teamlogo/{tid}.png" if tid else "",
            }
        if teams:
            _write_json(os.path.join(DATA, f"teams_{lg['id']}.json"), teams)
    ids = {}
    from bahis.league import team_key
    for r in rows:
        hid, aid = team_key(r.get("HomeTeam") or ""), team_key(r.get("AwayTeam") or "")
        if not hid or not aid or not r.get("FotmobId"):
            continue
        day = str(r.get("DateUtc") or "")[:10]
        ids[f"{day}:{hid}:{aid}"] = r["FotmobId"]
        ids[f"{hid}:{aid}"] = r["FotmobId"]
    if ids:
        _write_json(os.path.join(DATA, f"fotmob_ids_{lg['id']}.json"), ids)
    return len(rows)


def fetch_fotmob_fixtures(lg: dict) -> tuple[int, str | None]:
    data, err = fetch_fotmob_payload(lg)
    if err or data is None:
        return 0, err
    rows = fotmob_fixture_rows(data)
    write_fotmob_fixtures(lg, rows, data)
    return len(rows), None


def run(ids: list[str] | None = None) -> int:
    want = [get(x) for x in ids] if ids else list(LEAGUES)
    seen = []
    for lg in want:
        if lg["id"] in seen:
            continue
        seen.append(lg["id"])
        print(f"== {lg['flag']} {lg['name']} ({lg['id']})", flush=True)
        if lg["kind"] == "bra":
            n, err = fetch_brazil()
            print(f"  BRA csv {n if not err else err}", flush=True)
        else:
            ok = 0
            for season in lg["seasons"]:
                n, err = fetch_euro_season(lg["fd"], season)
                if err == "yok":
                    print(f"  skip {season}: henüz yok", flush=True)
                elif err:
                    print(f"  skip {season}: {err}", flush=True)
                else:
                    ok += 1
                    print(f"  {lg['fd']}_{season}.csv {n} satır", flush=True)
                time.sleep(0.08)
            print(f"  {ok}/{len(lg['seasons'])} sezon", flush=True)
        n, err = fetch_fotmob_fixtures(lg)
        print(f"  fikstür {n if not err else err}", flush=True)
        time.sleep(0.2)
    print("bitti", flush=True)
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    raise SystemExit(run(args or None))
