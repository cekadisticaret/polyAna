"""Sanal kupon defteri — algoritma üretir, skorla kapanır. Canlı bahis yok."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_DIR))

from bahis.coupon import _hit  # noqa: E402
from bahis.leagues_cfg import LEAGUES, current_league, get as get_league, set_league  # noqa: E402

TR = ZoneInfo("Europe/Istanbul")
PATH = os.path.join(_DIR, "data", "coupons.json")
STARTING = 10000.0
STAKE = 200.0
_MARKET = {
    "1X2": "Maç Sonucu 1X2",
    "2.5": "Toplam Gol 2.5",
    "KG": "Karşılıklı Gol",
}
_SEL = {
    "1": "1", "X": "X", "2": "2",
    "over": "Üst", "under": "Alt",
    "btts_yes": "Var", "btts_no": "Yok",
}
_GUN = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")


def when_tr(ko: str | None) -> str:
    """Kickoff → Türkiye saati (dd.mm Gün HH:MM)."""
    if not ko:
        return ""
    try:
        dt = datetime.fromisoformat(ko.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TR)
        else:
            dt = dt.astimezone(TR)
        return f"{dt.strftime('%d.%m')} {_GUN[dt.weekday()]} {dt.strftime('%H:%M')}"
    except ValueError:
        return ko


def _now() -> datetime:
    return datetime.now(TR)


def _empty() -> dict:
    return {"updated": None, "coupons": [], "stats": {}}


def load() -> dict:
    if os.path.isfile(PATH):
        try:
            with open(PATH, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("coupons"), list):
                return d
        except (OSError, json.JSONDecodeError):
            pass
    return _empty()


def save(pack: dict) -> None:
    pack["stats"] = _stats(pack.get("coupons") or [])
    pack["updated"] = _now().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def _fp(league: str, legs: list[dict]) -> str:
    parts = sorted(f"{x.get('id')}:{x.get('sel')}" for x in legs)
    return league + "|" + "+".join(parts)


def _monday(d: datetime) -> datetime:
    return (d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=TR)
    except ValueError:
        return None


def _week_stats(rows: list[dict]) -> dict:
    start = _monday(_now())
    week = []
    for r in rows:
        dt = _parse_ts(r.get("placed_at"))
        if dt and dt >= start:
            week.append(r)
    won = [r for r in week if r.get("status") == "won"]
    lost = [r for r in week if r.get("status") == "lost"]
    opened = [r for r in week if r.get("status") == "open"]
    pnl = sum(float(r.get("pnl") or 0) for r in week if r.get("status") in ("won", "lost"))
    return {
        "start": start.date().isoformat(),
        "n": len(week),
        "open": len(opened),
        "won": len(won),
        "lost": len(lost),
        "pnl": round(pnl, 2),
        "verdict": "kâr" if pnl > 0 else ("zarar" if pnl < 0 else "beraber"),
    }


def _stats(rows: list[dict]) -> dict:
    won = [r for r in rows if r.get("status") == "won"]
    lost = [r for r in rows if r.get("status") == "lost"]
    opened = [r for r in rows if r.get("status") == "open"]
    pnl = sum(float(r.get("pnl") or 0) for r in rows if r.get("status") in ("won", "lost"))
    staked = sum(float(r.get("stake") or STAKE) for r in rows if r.get("status") in ("won", "lost"))
    locked = STAKE * len(opened)
    return {
        "n": len(rows),
        "open": len(opened),
        "won": len(won),
        "lost": len(lost),
        "pnl": round(pnl, 2),
        "staked": round(staked, 2),
        "roi": round(100 * pnl / staked, 1) if staked else None,
        "starting": STARTING,
        "stake": STAKE,
        "equity": round(STARTING + pnl, 2),
        "balance": round(STARTING + pnl - locked, 2),
        "locked": round(locked, 2),
        "week": _week_stats(rows),
    }


def _enrich_leg(lg: dict, league: str) -> dict:
    from bahis.league import team_info
    set_league(league)
    h = team_info(lg.get("home") or "")
    a = team_info(lg.get("away") or "")
    mk = lg.get("market") or "1X2"
    sel = lg.get("sel") or ""
    out = dict(lg)
    out["market_label"] = _MARKET.get(mk, mk)
    out["sel_box"] = _SEL.get(sel, sel)
    out["home_crest"] = h.get("crest") or ""
    out["away_crest"] = a.get("crest") or ""
    out["home_short"] = h.get("short") or (lg.get("home") or "?")[:3]
    out["away_short"] = a.get("short") or (lg.get("away") or "?")[:3]
    out["home_color"] = h.get("color") or "#333"
    out["away_color"] = a.get("color") or "#333"
    ko = lg.get("kickoff")
    if not ko or ko.endswith("T00:00:00+03:00") or ko.endswith("T00:00:00"):
        from bahis.league import all_matches
        mid = lg.get("id")
        hk, ak = h.get("key"), a.get("key")
        for m in all_matches():
            if mid and m.get("id") == mid and m.get("kickoff"):
                ko = m["kickoff"]
                break
            if {m["home"]["key"], m["away"]["key"]} == {hk, ak} and m.get("kickoff"):
                if not m.get("played"):
                    ko = m["kickoff"]
                    break
    out["kickoff"] = ko
    out["when_tr"] = when_tr(ko) or lg.get("when") or ""
    dt = None
    try:
        if ko:
            dt = datetime.fromisoformat(ko.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TR)
            else:
                dt = dt.astimezone(TR)
    except ValueError:
        dt = None
    now = _now()
    if out.get("hit") is True or out.get("hit") is False:
        out["phase"] = "done"
    elif dt and now >= dt:
        out["phase"] = "live"
    else:
        out["phase"] = "soon"
    return out


def _migrate(pack: dict) -> bool:
    changed = False
    for c in pack.get("coupons") or []:
        if float(c.get("stake") or 0) != STAKE:
            c["stake"] = STAKE
            if c.get("status") == "won":
                c["pnl"] = round(STAKE * (float(c.get("odds_product") or 1) - 1), 2)
            elif c.get("status") == "lost":
                c["pnl"] = -STAKE
            changed = True
        c["potential"] = round(STAKE * float(c.get("odds_product") or 1), 2)
    return changed


def _score(mid: str, league: str) -> tuple[int | None, int | None]:
    from bahis.results import grade_of
    from bahis.league import all_matches
    row = grade_of(mid)
    if row and row.get("played") and row.get("hg") is not None:
        return int(row["hg"]), int(row["ag"])
    set_league(league)
    for m in all_matches():
        if m.get("id") != mid:
            continue
        if m.get("played") and m.get("hg") is not None:
            return int(m["hg"]), int(m["ag"])
    return None, None


def settle(pack: dict | None = None) -> dict:
    pack = pack or load()
    changed = _migrate(pack)
    for c in pack.get("coupons") or []:
        if c.get("status") != "open":
            continue
        lid = c.get("league") or "tr"
        done = 0
        hits = 0
        for lg in c.get("legs") or []:
            hg, ag = _score(lg.get("id") or "", lid)
            if hg is None:
                continue
            lg["hg"], lg["ag"] = hg, ag
            lg["hit"] = _hit(hg, ag, lg.get("sel") or "")
            done += 1
            hits += 1 if lg["hit"] else 0
        n = len(c.get("legs") or [])
        if n and done == n:
            won = hits == n
            c["status"] = "won" if won else "lost"
            stake = STAKE
            c["stake"] = stake
            odds = float(c.get("odds_product") or 1)
            c["potential"] = round(stake * odds, 2)
            c["pnl"] = round(stake * (odds - 1), 2) if won else round(-stake, 2)
            c["settled_at"] = _now().isoformat(timespec="seconds")
            changed = True
        elif done:
            c["partial"] = f"{hits}/{done} ayardandı"
            changed = True
    if changed:
        save(pack)
    else:
        pack["stats"] = _stats(pack.get("coupons") or [])
    return pack


def _far_open(c: dict) -> bool:
    from bahis.coupon import in_horizon
    legs = c.get("legs") or []
    if not legs:
        return True
    return any(not in_horizon(lg.get("kickoff")) for lg in legs)


def _dup_teams(c: dict) -> bool:
    from bahis.coupon import _team_keys
    seen: set[str] = set()
    for lg in c.get("legs") or []:
        keys = _team_keys(lg)
        if keys & seen:
            return True
        seen |= keys
    return False


def void_bad_open() -> int:
    pack = load()
    n = 0
    for c in pack.get("coupons") or []:
        if c.get("status") != "open":
            continue
        why = None
        if _far_open(c):
            why = "uzak maç · haftalık kilit"
        elif _dup_teams(c):
            why = "aynı takım iki kez"
        if not why:
            continue
        c["status"] = "void"
        c["void_reason"] = why
        c["pnl"] = 0.0
        n += 1
    if n:
        save(pack)
    return n


def void_far_open(reason: str = "uzak maç · haftalık kilit") -> int:
    pack = load()
    n = 0
    for c in pack.get("coupons") or []:
        if c.get("status") != "open":
            continue
        if not _far_open(c):
            continue
        c["status"] = "void"
        c["void_reason"] = reason
        c["pnl"] = 0.0
        n += 1
    if n:
        save(pack)
    return n


def place_league(lid: str) -> dict | None:
    from bahis import coupon as coupon_mod
    set_league(lid)
    d = coupon_mod.upcoming_preds(limit=32)
    raw = d.get("coupon")
    if not raw or not raw.get("legs"):
        return None
    legs = raw["legs"]
    fp = _fp(lid, legs)
    pack = load()
    if any(x.get("fp") == fp and x.get("status") == "open" for x in pack["coupons"]):
        return None
    day = _now().date().isoformat()
    if any(
        x.get("league") == lid and x.get("day") == day and x.get("status") == "open"
        for x in pack["coupons"]
    ):
        return None
    lg = get_league(lid)
    rec = {
        "id": f"c-{lid}-{day}-{len(pack['coupons'])+1}",
        "fp": fp,
        "day": day,
        "league": lid,
        "league_name": lg["name"],
        "league_short": lg["short"],
        "placed_at": _now().isoformat(timespec="seconds"),
        "status": "open",
        "engines": ["dixon-coles", "fair-value", "greedy"],
        "odds_product": raw.get("odds_product"),
        "p_joint": raw.get("p_joint"),
        "p_indep": raw.get("p_indep"),
        "edge": raw.get("edge"),
        "stake": STAKE,
        "potential": round(STAKE * float(raw.get("odds_product") or 1), 2),
        "kelly": raw.get("kelly"),
        "corr": raw.get("corr"),
        "legs": [{**lg, "hit": None, "hg": None, "ag": None} for lg in legs],
        "pnl": 0.0,
        "orders": False,
        "paper": True,
        "odds_src": next((lg.get("odds_src") for lg in legs if lg.get("odds_src")), None)
        or ("h2h" if any(True for _ in legs) else None),
        "horizon_days": coupon_mod.HORIZON_DAYS,
    }
    pack["coupons"].append(rec)
    save(pack)
    return rec


def place_all() -> list[dict]:
    void_bad_open()
    out = []
    for lg in LEAGUES:
        rec = place_league(lg["id"])
        if rec:
            out.append(rec)
    settle()
    return out


def listing(league: str | None = None, limit: int = 80, tab: str = "open") -> dict:
    pack = settle()
    rows = list(pack.get("coupons") or [])
    if league and league != "all":
        rows = [r for r in rows if r.get("league") == league]
    tab = (tab or "open").lower()
    if tab == "done":
        rows = [r for r in rows if r.get("status") in ("won", "lost")]
    else:
        rows = [r for r in rows if r.get("status") == "open"]
    rows.sort(key=lambda r: r.get("placed_at") or "", reverse=True)
    pub = []
    for c in rows[:limit]:
        lid_c = c.get("league") or "tr"
        rec = dict(c)
        rec["legs"] = [_enrich_leg(lg, lid_c) for lg in (c.get("legs") or [])]
        rec["stake"] = STAKE
        rec["potential"] = round(STAKE * float(c.get("odds_product") or 1), 2)
        pub.append(rec)
    lid = league or current_league()
    name = get_league(lid)["name"] if lid != "all" else "Tüm ligler"
    st = pack.get("stats") or _stats(pack.get("coupons") or [])
    return {
        "ok": True,
        "league": name,
        "league_id": lid,
        "updated": pack.get("updated"),
        "stats": st,
        "n": len(rows),
        "coupons": pub,
        "note": (
            f"Sanal · {int(STAKE)} TL/kupon · kasa nakit (açık kupon düşülür) · "
            f"yalnız 5 gün · oran football-data (B365/Avg), yoksa H2H · "
            f"Nesine/Misli emri yok"
        ),
        "orders": False,
    }


def main() -> int:
    placed = place_all()
    pack = load()
    st = pack.get("stats") or {}
    print(f"yeni {len(placed)} · açık {st.get('open')} · kazandı {st.get('won')} · kaybetti {st.get('lost')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
