"""Süper Lig sonuç + tahmin defteri. Cron: saatlik. Emir yok.

  python3 bahis/results_fetch.py
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
BOOK = os.path.join(DATA, "results_book.json")
FIX_JSON = os.path.join(DATA, "superlig_2026_fixtures.json")
T1 = os.path.join(DATA, "T1_2627.csv")
FD_URL = "https://www.football-data.co.uk/mmz4281/2627/T1.csv"
FOTMOB = "https://www.fotmob.com/api/data/leagues?id=71"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/csv,*/*",
    "Accept-Encoding": "gzip",
}
TR = ZoneInfo("Europe/Istanbul")

sys.path.insert(0, os.path.dirname(_DIR))


def _get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def _now() -> datetime:
    return datetime.now(TR)


def _load_book() -> dict:
    if os.path.isfile(BOOK):
        try:
            with open(BOOK, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"updated": None, "src": [], "matches": {}}


def _save_book(pack: dict) -> None:
    tmp = BOOK + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)
    os.replace(tmp, BOOK)


def fetch_fd() -> tuple[int, str | None]:
    try:
        raw = _get(FD_URL)
    except Exception as e:
        return 0, f"fd: {e}"
    text = raw.decode("utf-8-sig", errors="replace")
    if "HomeTeam" not in text[:200]:
        return 0, "fd: csv değil"
    rows = list(csv.DictReader(io.StringIO(text)))
    played = sum(1 for r in rows if (r.get("FTHG") or "").strip() != "")
    with open(T1, "w", encoding="utf-8", newline="") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    return played, None


def _fotmob_score(m: dict) -> tuple[int | None, int | None]:
    st = m.get("status") or {}
    if st.get("cancelled") or st.get("awarded"):
        return None, None
    hs = st.get("scoreStr") or m.get("score") or ""
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


def fetch_fotmob() -> tuple[list[dict], str | None]:
    from bahis.league import _match_id, _parse_utc, team_info, team_key
    try:
        data = json.loads(_get(FOTMOB))
    except Exception as e:
        return [], f"fotmob: {e}"
    matches = (
        ((data.get("fixtures") or {}).get("allMatches"))
        or ((data.get("overview") or {}).get("matches") or {}).get("allMatches")
        or []
    )
    out = []
    for m in matches:
        hn = (m.get("home") or {}).get("name") or ""
        an = (m.get("away") or {}).get("name") or ""
        if not hn or not an:
            continue
        utc = (m.get("status") or {}).get("utcTime") or m.get("utcTime") or ""
        utc = str(utc).replace("Z", "").split(".")[0]
        dt = _parse_utc(utc)
        hg, ag = _fotmob_score(m)
        mid = _match_id(dt, hn, an)
        out.append({
            "id": mid,
            "home": team_info(hn)["key"],
            "away": team_info(an)["key"],
            "home_name": team_info(hn)["name"],
            "away_name": team_info(an)["name"],
            "kickoff": dt.isoformat() if dt else None,
            "hg": hg,
            "ag": ag,
            "played": hg is not None and ag is not None,
            "week": None,
            "src": "fotmob",
        })
        _ = team_key
    return out, None


def _patch_fixtures(scores: dict[str, tuple[int, int]]) -> int:
    if not os.path.isfile(FIX_JSON) or not scores:
        return 0
    from bahis.league import _match_id, _parse_utc
    with open(FIX_JSON, encoding="utf-8") as f:
        rows = json.load(f)
    n = 0
    for row in rows:
        dt = _parse_utc(row.get("DateUtc") or "")
        mid = _match_id(dt, row.get("HomeTeam") or "", row.get("AwayTeam") or "")
        sc = scores.get(mid)
        if not sc:
            continue
        if row.get("HomeTeamScore") == sc[0] and row.get("AwayTeamScore") == sc[1]:
            continue
        row["HomeTeamScore"] = sc[0]
        row["AwayTeamScore"] = sc[1]
        row["Winner"] = "Draw" if sc[0] == sc[1] else (
            row.get("HomeTeam") if sc[0] > sc[1] else row.get("AwayTeam")
        )
        n += 1
    if n:
        tmp = FIX_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        os.replace(tmp, FIX_JSON)
    return n


def _actual(hg: int, ag: int) -> str:
    if hg > ag:
        return "1"
    if hg < ag:
        return "2"
    return "X"


def _snapshot(mid: str, hk: str, ak: str, hn: str, an: str) -> dict:
    from bahis.match_intel import _pick, _quick_models
    md = _quick_models(hk, ak)
    ens = md["ensemble"]
    pick, text, pct = _pick(ens, hn, an)
    return {
        "pick": pick,
        "text": text,
        "pct": pct,
        "p1": ens["1"],
        "px": ens["X"],
        "p2": ens["2"],
        "models": {
            "poisson": md["poisson"],
            "xg": md["xg"],
            "ensemble": ens,
        },
        "xg": md["xg_n"],
    }


def refresh_book(extra: list[dict], src: list[str]) -> dict:
    from bahis.league import all_matches, team_info
    all_matches.cache_clear()
    try:
        from bahis.match_intel import _played
        _played.cache_clear()
    except Exception:
        pass
    pack = _load_book()
    book = pack.get("matches") or {}
    now = _now()
    by_extra = {r["id"]: r for r in extra}
    for m in all_matches():
        if m.get("season") != "2627":
            continue
        mid = m["id"]
        hk, ak = m["home"]["key"], m["away"]["key"]
        hn, an = m["home"]["name"], m["away"]["name"]
        ex = by_extra.get(mid) or {}
        hg = ex.get("hg") if ex.get("played") else m.get("hg")
        ag = ex.get("ag") if ex.get("played") else m.get("ag")
        played = hg is not None and ag is not None
        row = book.get(mid) or {
            "id": mid,
            "home": hk,
            "away": ak,
            "home_name": hn,
            "away_name": an,
        }
        row.update({
            "home": hk, "away": ak,
            "home_name": hn, "away_name": an,
            "when": m.get("kickoff"),
            "kickoff": m.get("kickoff"),
            "week": m.get("week"),
            "venue": m.get("venue"),
            "hg": hg, "ag": ag,
            "played": played,
        })
        ko = m.get("kickoff") or ""
        pre_ok = bool(ko and ko > now.isoformat())
        # Maç başladıktan sonra çekilen ensemble geriye dönük uydurma —
        # yalnız kickoff öncesi ilk snap kilitlenir ve notlanır.
        if not row.get("pick") and pre_ok:
            snap = _snapshot(mid, hk, ak, hn, an)
            row.update(snap)
            row["snap_ts"] = now.isoformat(timespec="seconds")
            row["snap_kind"] = "pre"
        if row.get("snap_kind") == "post":
            for k in ("pick", "text", "pct", "p1", "px", "p2", "models",
                      "xg", "snap_ts", "snap_kind", "hit", "result"):
                row.pop(k, None)
        if played:
            actual = _actual(int(hg), int(ag))
            row["result"] = actual
            if row.get("pick") and row.get("snap_kind") == "pre":
                row["hit"] = row.get("pick") == actual
            else:
                row["hit"] = None
        book[mid] = row
        _ = team_info
    graded = [r for r in book.values() if r.get("hit") is not None]
    hits = sum(1 for r in graded if r.get("hit"))
    pack = {
        "updated": now.isoformat(timespec="seconds"),
        "src": src,
        "matches": book,
        "stats": {
            "n": len(graded),
            "hits": hits,
            "wr": round(hits / len(graded) * 100, 1) if graded else None,
        },
    }
    _save_book(pack)
    return pack


def main() -> int:
    src, notes = [], []
    n_fd, err = fetch_fd()
    if err:
        notes.append(err)
    else:
        src.append("football-data")
        notes.append(f"fd {n_fd} skorlu satır")
    extra, ferr = fetch_fotmob()
    if ferr:
        notes.append(ferr)
    else:
        src.append("fotmob")
        scored = {r["id"]: (r["hg"], r["ag"]) for r in extra if r.get("played")}
        patched = _patch_fixtures(scored)
        notes.append(f"fotmob {len(extra)} maç · {len(scored)} skor · fikstür +{patched}")
    pack = refresh_book(extra, src)
    st = pack.get("stats") or {}
    print(" · ".join(notes) or "kaynak yok")
    print(
        f"defter {st.get('n') or 0} not · isabet {st.get('hits') or 0}"
        f" · WR {st.get('wr')} · {pack.get('updated')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
