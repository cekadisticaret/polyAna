"""Lig sonuç + tahmin defteri. Cron: saatlik. Emir yok.

  python3 bahis/results_fetch.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
BOOK = os.path.join(DATA, "results_book.json")
TR = ZoneInfo("Europe/Istanbul")

sys.path.insert(0, os.path.dirname(_DIR))

from bahis.leagues_cfg import LEAGUES, set_league  # noqa: E402
from bahis.fetch_leagues import (  # noqa: E402
    fetch_euro_season,
    fetch_fotmob_payload,
    fotmob_fixture_rows,
    write_fotmob_fixtures,
)


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


def fetch_fd(lg: dict) -> tuple[int, str | None]:
    if lg["kind"] == "bra":
        from bahis.fetch_leagues import fetch_brazil
        n, err = fetch_brazil()
        return n, err
    n, err = fetch_euro_season(lg["fd"], lg["current"])
    if err == "yok":
        return 0, "yok"
    if err:
        return 0, f"fd {lg['id']}: {err}"
    dest = os.path.join(DATA, f"{lg['fd']}_{lg['current']}.csv")
    played = 0
    if os.path.isfile(dest):
        with open(dest, encoding="utf-8-sig", newline="") as f:
            played = sum(
                1 for r in csv.DictReader(f)
                if (r.get("FTHG") or r.get("HG") or "").strip() != ""
            )
    return played, None


def fetch_fotmob(lg: dict) -> tuple[list[dict], str | None]:
    from bahis.league import _match_id, _parse_utc, team_info
    set_league(lg["id"])
    data, err = fetch_fotmob_payload(lg)
    if err or data is None:
        return [], err
    rows = fotmob_fixture_rows(data)
    write_fotmob_fixtures(lg, rows, data)
    out = []
    for row in rows:
        hn = row.get("HomeTeam") or ""
        an = row.get("AwayTeam") or ""
        dt = _parse_utc(row.get("DateUtc") or "")
        hg, ag = row.get("HomeTeamScore"), row.get("AwayTeamScore")
        played = hg is not None and ag is not None
        mid = _match_id(dt, hn, an, lg["id"])
        out.append({
            "id": mid,
            "league": lg["id"],
            "home": team_info(hn)["key"],
            "away": team_info(an)["key"],
            "home_name": team_info(hn)["name"],
            "away_name": team_info(an)["name"],
            "kickoff": dt.isoformat() if dt else None,
            "hg": int(hg) if played else None,
            "ag": int(ag) if played else None,
            "played": played,
            "week": row.get("RoundNumber"),
            "src": "fotmob",
        })
    return out, None


def _patch_fixtures(lg: dict, scores: dict[str, tuple[int, int]]) -> int:
    path = os.path.join(DATA, lg["fix_json"])
    if not os.path.isfile(path) or not scores:
        return 0
    from bahis.league import _match_id, _parse_utc
    set_league(lg["id"])
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    n = 0
    for row in rows:
        dt = _parse_utc(row.get("DateUtc") or "")
        mid = _match_id(dt, row.get("HomeTeam") or "", row.get("AwayTeam") or "", lg["id"])
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
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        os.replace(tmp, path)
    return n


def _actual(hg: int, ag: int) -> str:
    if hg > ag:
        return "1"
    if hg < ag:
        return "2"
    return "X"


def _odds_taken(m: dict | None) -> dict:
    od = (m or {}).get("odds") or {}
    return {
        "home": od.get("home"),
        "draw": od.get("draw"),
        "away": od.get("away"),
    }


def _snapshot(mid: str, hk: str, ak: str, hn: str, an: str,
              m: dict | None = None) -> dict:
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
        "odds_taken": _odds_taken(m),
    }


def refresh_book(lg: dict, extra: list[dict], src: list[str], pack: dict) -> dict:
    from bahis.league import all_matches, reload_matches
    set_league(lg["id"])
    reload_matches()
    book = pack.get("matches") or {}
    now = _now()
    by_extra = {r["id"]: r for r in extra}
    for m in all_matches(lg["id"]):
        if m.get("season") != lg["current"]:
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
            "league": lg["id"],
            "home": hk,
            "away": ak,
            "home_name": hn,
            "away_name": an,
        }
        row.update({
            "league": lg["id"],
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
        horizon = now.isoformat()[:10]
        from datetime import timedelta
        until = (now + timedelta(days=21)).isoformat()
        pre_ok = bool(ko and ko > now.isoformat() and ko <= until)
        if not row.get("pick") and pre_ok:
            snap = _snapshot(mid, hk, ak, hn, an, m)
            row.update(snap)
            row["snap_ts"] = now.isoformat(timespec="seconds")
            row["snap_kind"] = "pre"
        if pre_ok:
            now_od = _odds_taken(m)
            if now_od.get("home"):
                hist = list(row.get("odds_line") or [])
                last = hist[-1] if hist else None
                changed = (not last) or any(
                    last.get(k) != now_od.get(k) for k in ("home", "draw", "away")
                )
                if changed:
                    rec = {"ts": now.isoformat(timespec="seconds"), **now_od}
                    if last and last.get("home") and now_od.get("home"):
                        from bahis.value import implied_raw
                        rec["home_pts"] = round(
                            (implied_raw(now_od["home"]) or 0) - (implied_raw(last["home"]) or 0), 4
                        )
                    hist.append(rec)
                    row["odds_line"] = hist[-24:]
                    row["odds_now"] = now_od
                    if rec.get("home_pts") is not None and abs(rec["home_pts"]) >= 0.03:
                        row["line_move"] = rec
                if not row.get("odds_taken"):
                    row["odds_taken"] = now_od
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
            if row.get("pick") and row.get("odds_taken") and not row.get("clv"):
                from bahis.value import append_clv, clv_1x2
                close = ((m.get("odds") or {}).get("close") or m.get("odds") or {})
                clv = clv_1x2(row["pick"], row.get("odds_taken"), close)
                if clv:
                    row["clv"] = clv
                    append_clv({
                        "id": mid,
                        "league": lg["id"],
                        "pick": row["pick"],
                        "hit": row.get("hit"),
                        **clv,
                    })
        book[mid] = row
    graded = [r for r in book.values() if r.get("hit") is not None]
    hits = sum(1 for r in graded if r.get("hit"))
    from bahis.value import clv_stats
    pack["updated"] = now.isoformat(timespec="seconds")
    pack["src"] = list(dict.fromkeys((pack.get("src") or []) + src))
    pack["matches"] = book
    pack["stats"] = {
        "n": len(graded),
        "hits": hits,
        "wr": round(hits / len(graded) * 100, 1) if graded else None,
    }
    pack["clv"] = clv_stats([
        {"clv": (r.get("clv") or {}).get("clv"), "beat": (r.get("clv") or {}).get("beat")}
        for r in book.values() if r.get("clv")
    ])
    return pack


def main() -> int:
    pack = _load_book()
    notes = []
    for lg in LEAGUES:
        src = []
        n_fd, err = fetch_fd(lg)
        if err == "yok":
            notes.append(f"{lg['id']} fd yok")
        elif err:
            notes.append(err)
        else:
            src.append("football-data")
            notes.append(f"{lg['id']} fd {n_fd}")
        extra, ferr = fetch_fotmob(lg)
        if ferr:
            notes.append(ferr)
            extra = []
        else:
            src.append("fotmob")
            scored = {r["id"]: (r["hg"], r["ag"]) for r in extra if r.get("played")}
            patched = _patch_fixtures(lg, scored)
            notes.append(f"{lg['id']} fotmob {len(extra)} · skor {len(scored)} · +{patched}")
        pack = refresh_book(lg, extra, src, pack)
    _save_book(pack)
    st = pack.get("stats") or {}
    print(" · ".join(notes) or "kaynak yok")
    print(
        f"defter {st.get('n') or 0} not · isabet {st.get('hits') or 0}"
        f" · WR {st.get('wr')} · {pack.get('updated')}"
    )
    from bahis.coupon_book import place_all
    placed = place_all()
    if placed:
        print(f"kupon +{len(placed)}")
    if "--no-tg" not in sys.argv:
        from bahis.leagues_cfg import set_league
        from bahis.notify import alert_value
        sent = 0
        for lg in LEAGUES:
            set_league(lg["id"])
            sent += alert_value()
        if sent:
            print(f"tg {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
