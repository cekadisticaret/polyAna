"""Maç istatistik · oran hareketi · dinlenme · sakatlık. Emir yok."""
from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from bahis.league import all_matches, team_info

TR = ZoneInfo("Europe/Istanbul")
STAT_SEASONS = 5
INJ_TTL = 1800
INJ_CACHE = "/tmp/bahis_injuries.json"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
ELO_BLEND = 0.35
REST_TIRED = 3
INJ_LAM = 0.03
INJ_CAP = 0.12


def clear_caches() -> None:
    _team_shape_for.cache_clear()
    _rest_index_for.cache_clear()


def _parse_ko(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TR)
        return dt
    except ValueError:
        return None


def _imp(odds: float | None) -> float | None:
    if not odds or odds <= 1:
        return None
    return 1.0 / odds


def line_move(odds: dict | None) -> dict | None:
    """Açılış → kapanış: kısalan taraf keskin para."""
    if not odds:
        return None
    op, cl = odds.get("open") or {}, odds.get("close") or {}
    oh, ch = op.get("home"), cl.get("home")
    if not oh or not ch:
        return None
    sides = []
    for key, field in (("1", "home"), ("X", "draw"), ("2", "away")):
        a, b = op.get(field), cl.get(field)
        ia, ib = _imp(a), _imp(b)
        if ia is None or ib is None:
            continue
        sides.append({
            "pick": key,
            "open": round(float(a), 3),
            "close": round(float(b), 3),
            "d_odds": round(float(b) - float(a), 3),
            "d_imp": round(ib - ia, 4),
        })
    if not sides:
        return None
    sharp = max(sides, key=lambda x: x["d_imp"])
    return {
        "sharp": sharp["pick"] if sharp["d_imp"] > 0.005 else None,
        "d_imp": sharp["d_imp"],
        "sides": sides,
    }


@lru_cache(maxsize=8)
def _team_shape_for(league: str) -> dict[str, dict]:
    from bahis.leagues_cfg import get as get_league
    lg = get_league(league)
    seasons = list(lg["seasons"])[-STAT_SEASONS:]
    want = set(seasons)
    acc: dict[str, dict] = {}

    def bucket(k: str) -> dict:
        if k not in acc:
            acc[k] = {
                "n": 0, "gf": 0.0, "ga": 0.0, "xg": 0.0, "xga": 0.0, "xg_n": 0,
                "shots": 0.0, "sot": 0.0, "corners": 0.0, "cards": 0.0,
                "home_n": 0, "away_n": 0, "gf_h": 0.0, "gf_a": 0.0,
            }
        return acc[k]

    for m in all_matches(league):
        if not m.get("played") or m.get("season") not in want:
            continue
        hg, ag = m.get("hg"), m.get("ag")
        if hg is None or ag is None:
            continue
        hk, ak = m["home"]["key"], m["away"]["key"]
        hxg, axg = m.get("hxg"), m.get("axg")
        for key, gf, ga, sh, sot, cr, yel, red, xg_for, xg_ag, home in (
            (hk, hg, ag, m.get("hs"), m.get("hst"), m.get("hc"), m.get("hy"), m.get("hr"), hxg, axg, True),
            (ak, ag, hg, m.get("as_s"), m.get("ast"), m.get("ac"), m.get("ay"), m.get("ar"), axg, hxg, False),
        ):
            b = bucket(key)
            b["n"] += 1
            b["gf"] += gf
            b["ga"] += ga
            if sh is not None:
                b["shots"] += sh
            if sot is not None:
                b["sot"] += sot
            if cr is not None:
                b["corners"] += cr
            b["cards"] += (yel or 0) + 2 * (red or 0)
            if xg_for is not None:
                b["xg"] += xg_for
                b["xg_n"] += 1
            if xg_ag is not None:
                b["xga"] += xg_ag
            if home:
                b["home_n"] += 1
                b["gf_h"] += gf
            else:
                b["away_n"] += 1
                b["gf_a"] += gf
    out = {}
    for k, b in acc.items():
        n = max(b["n"], 1)
        out[k] = {
            "n": b["n"],
            "gf": round(b["gf"] / n, 3),
            "ga": round(b["ga"] / n, 3),
            "xg": round(b["xg"] / b["xg_n"], 3) if b["xg_n"] >= 15 else None,
            "xga": round(b["xga"] / b["xg_n"], 3) if b["xg_n"] >= 15 else None,
            "xg_n": b["xg_n"],
            "shots": round(b["shots"] / n, 2),
            "sot": round(b["sot"] / n, 2),
            "corners": round(b["corners"] / n, 2),
            "cards": round(b["cards"] / n, 2),
            "gf_home": round(b["gf_h"] / b["home_n"], 3) if b["home_n"] else None,
            "gf_away": round(b["gf_a"] / b["away_n"], 3) if b["away_n"] else None,
        }
    return out


def team_shape(key: str) -> dict:
    from bahis.leagues_cfg import current_league
    return _team_shape_for(current_league()).get(key) or {"n": 0}


@lru_cache(maxsize=8)
def _rest_index_for(league: str) -> dict[str, list[str]]:
    by: dict[str, list[str]] = {}
    for m in all_matches(league):
        ko = m.get("kickoff")
        if not ko:
            continue
        for side in ("home", "away"):
            k = m[side]["key"]
            by.setdefault(k, []).append(ko)
    for k in by:
        by[k].sort()
    return by


def rest_days(key: str, before: str | None) -> int | None:
    if not before:
        return None
    from bahis.leagues_cfg import current_league
    prev = None
    for ko in _rest_index_for(current_league()).get(key) or []:
        if ko >= before:
            break
        prev = ko
    if not prev:
        return None
    a, b = _parse_ko(prev), _parse_ko(before)
    if not a or not b:
        return None
    return max(int((b - a).total_seconds() // 86400), 0)


def _inj_disk() -> dict:
    if not os.path.isfile(INJ_CACHE):
        return {}
    try:
        with open(INJ_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _inj_save(pack: dict) -> None:
    tmp = INJ_CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False)
    os.replace(tmp, INJ_CACHE)


def _unavail_rows(team: dict | None) -> list[dict]:
    out = []
    for p in (team or {}).get("unavailable") or []:
        u = p.get("unavailability") or {}
        out.append({
            "name": p.get("name") or p.get("lastName") or "?",
            "type": u.get("type") or "injury",
            "until": u.get("expectedReturn"),
        })
    return out


def resolve_fotmob_id(m: dict) -> str | None:
    if m.get("fotmob_id"):
        return str(m["fotmob_id"])
    from bahis.leagues_cfg import current_league
    path = os.path.join(os.path.dirname(__file__), "data", f"fotmob_ids_{current_league()}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            ids = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    hk, ak = m["home"]["key"], m["away"]["key"]
    day = str(m.get("kickoff") or "")[:10]
    return ids.get(f"{day}:{hk}:{ak}") or ids.get(f"{hk}:{ak}")


def injuries(fotmob_id) -> dict:
    """Fotmob kadro dışı — 30 dk önbellek. Yoksa boş."""
    empty = {"home": [], "away": [], "n_h": 0, "n_a": 0, "ok": False}
    if not fotmob_id:
        return empty
    sid = str(fotmob_id)
    now = time.time()
    disk = _inj_disk()
    hit = disk.get(sid)
    if hit and now - float(hit.get("ts") or 0) < INJ_TTL:
        return hit.get("data") or empty
    url = f"https://www.fotmob.com/api/data/matchDetails?matchId={sid}"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        lu = ((data.get("content") or {}).get("lineup")) or {}
        home = _unavail_rows(lu.get("homeTeam"))
        away = _unavail_rows(lu.get("awayTeam"))
        pack = {"home": home, "away": away, "n_h": len(home), "n_a": len(away), "ok": True}
    except Exception:
        pack = empty
    disk[sid] = {"ts": now, "data": pack}
    if len(disk) > 80:
        old = sorted(disk.items(), key=lambda kv: float((kv[1] or {}).get("ts") or 0))
        disk = dict(old[-60:])
    try:
        _inj_save(disk)
    except OSError:
        pass
    return pack


def context(m: dict, *, fetch_inj: bool = True) -> dict:
    hk, ak = m["home"]["key"], m["away"]["key"]
    ko = m.get("kickoff")
    rh, ra = rest_days(hk, ko), rest_days(ak, ko)
    inj = injuries(resolve_fotmob_id(m)) if fetch_inj else {"home": [], "away": [], "n_h": 0, "n_a": 0, "ok": False}
    return {
        "rest_h": rh,
        "rest_a": ra,
        "home": True,
        "away_travel": True,
        "shape_h": team_shape(hk),
        "shape_a": team_shape(ak),
        "line": line_move(m.get("odds")),
        "injuries": inj,
    }


def _elo_mult(elo_h: float, elo_a: float, avg: float, home_adv: float) -> tuple[float, float]:
    mh = 10 ** ((elo_h - 1500.0) / 800.0)
    ma = 10 ** ((elo_a - 1500.0) / 800.0)
    lam = (mh / max(ma, 1e-6)) * math.exp(home_adv) * avg
    mu = (ma / max(mh, 1e-6)) * avg
    return lam, mu


def pair_lambda(home: str, away: str, match: dict | None = None, *, fetch_inj: bool = True) -> tuple[float, float, dict]:
    """Dixon-Coles λ + ELO güç + dinlenme/sakatlık. Poisson tek başına değil."""
    from bahis.dixon_coles import HOME_ADV, _fitted as dc_fit
    from bahis.elo import _fitted as elo_fit
    from bahis.league import team_key

    hk, ak = team_key(home), team_key(away)
    dc = dc_fit()
    xg = dc.expected_goals(hk, ak)
    lam_d, mu_d = float(xg["lambda"]), float(xg["mu"])
    elo = elo_fit()
    eh = float((elo._get(hk) or {}).get("elo") or 1500)
    ea = float((elo._get(ak) or {}).get("elo") or 1500)
    lam_e, mu_e = _elo_mult(eh, ea, dc.avg_goals, HOME_ADV)
    w = ELO_BLEND
    lam = (1 - w) * lam_d + w * lam_e
    mu = (1 - w) * mu_d + w * mu_e
    notes = [f"dc+elo {int(w*100)}/{int((1-w)*100)}"]
    ctx = context(match, fetch_inj=fetch_inj) if match else None
    if ctx:
        if ctx["rest_h"] is not None and ctx["rest_h"] < REST_TIRED:
            lam *= 0.95
            notes.append(f"ev dinlenme {ctx['rest_h']}g")
        if ctx["rest_a"] is not None and ctx["rest_a"] < REST_TIRED:
            mu *= 0.95
            notes.append(f"dep dinlenme {ctx['rest_a']}g")
        if ctx["rest_h"] is not None and ctx["rest_a"] is not None:
            if ctx["rest_h"] >= 6 and ctx["rest_a"] <= REST_TIRED:
                lam *= 1.03
                notes.append("ev taze")
            if ctx["rest_a"] >= 6 and ctx["rest_h"] <= REST_TIRED:
                mu *= 1.03
                notes.append("dep taze")
        inj = ctx["injuries"]
        if inj.get("ok"):
            dh = min(INJ_CAP, INJ_LAM * int(inj.get("n_h") or 0))
            da = min(INJ_CAP, INJ_LAM * int(inj.get("n_a") or 0))
            if dh:
                lam *= (1 - dh)
                notes.append(f"ev sakat {inj['n_h']}")
            if da:
                mu *= (1 - da)
                notes.append(f"dep sakat {inj['n_a']}")
        sh, sa = ctx["shape_h"], ctx["shape_a"]
        if sh.get("xg") and sa.get("xga"):
            lam = 0.85 * lam + 0.15 * ((sh["xg"] + sa["xga"]) / 2)
            notes.append("xG şekil")
        if sa.get("xg") and sh.get("xga"):
            mu = 0.85 * mu + 0.15 * ((sa["xg"] + sh["xga"]) / 2)
    lam, mu = max(lam, 0.15), max(mu, 0.15)
    meta = {
        "lam_dc": round(lam_d, 3),
        "mu_dc": round(mu_d, 3),
        "lam_elo": round(lam_e, 3),
        "mu_elo": round(mu_e, 3),
        "elo_h": round(eh),
        "elo_a": round(ea),
        "blend": ELO_BLEND,
        "notes": notes,
        "ctx": ctx,
    }
    return lam, mu, meta
