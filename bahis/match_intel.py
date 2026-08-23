"""Poisson + Elo + xG + Monte Carlo + ensemble + Kelly/value. Emir yok."""
from __future__ import annotations

import csv
import math
import os
import random
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from bahis.bankroll_manager import BankrollManager
from bahis.dixon_coles import poisson_pmf, _fitted as _dc_fit, _round_p, _pct, _when
from bahis.elo import _fitted as _elo_fit
from bahis.league import all_matches, team_info, team_key
from bahis import players as bahis_players

TR = ZoneInfo("Europe/Istanbul")
LOG = os.path.join(os.path.dirname(__file__), "data", "preds_log.csv")
MAXG = 8
MC_N = 6000
W_POIS, W_ELO, W_XG = 0.40, 0.30, 0.30
VALUE_EDGE = 0.05
LAST_N = 10
SAMPLE_MIN = 30
SAMPLE_OK = 50
KELLY_FRAC = 0.25  # ¼ Kelly — uyarıdaki yarı Kelly'den temkinli; tam kasa yok


def _avg(xs: list[float], fallback: float) -> float:
    return sum(xs) / len(xs) if xs else fallback


def _blend(n: int, raw: float, league: float, floor: int = 8) -> float:
    w = min(n / floor, 1.0)
    return w * raw + (1 - w) * league


def _sample_pois(lam: float) -> int:
    lam = max(lam, 0.01)
    l = math.exp(-lam)
    k, p = 0, 1.0
    while p > l:
        k += 1
        p *= random.random()
    return k - 1


@lru_cache(maxsize=1)
def _played() -> tuple[dict, ...]:
    return tuple(m for m in all_matches() if m.get("played") and m.get("hg") is not None)


def _league_means() -> dict:
    rows = _played()
    n = max(len(rows), 1)
    def m(k):
        return sum((r.get(k) or 0) for r in rows) / n
    return {
        "gf": (m("hg") + m("ag")) / 2,
        "ht": ((m("hthg") + m("htag")) / 2) if any(r.get("hthg") is not None for r in rows) else 0.55,
        "hc": m("hc") or 5.0,
        "hy": m("hy") or 2.0,
        "hr": m("hr") or 0.08,
        "sot": m("hst") or 4.0,
    }


def _team_last(key: str, n: int = LAST_N) -> dict:
    gf, ga, ht_f, ht_a, c_f, c_a, y_f, r_f, sot = [], [], [], [], [], [], [], [], []
    used = 0
    for m in reversed(_played()):
        hk, ak = m["home"]["key"], m["away"]["key"]
        if key == hk:
            gf.append(m["hg"] or 0); ga.append(m["ag"] or 0)
            if m.get("hthg") is not None:
                ht_f.append(m["hthg"] or 0); ht_a.append(m["htag"] or 0)
            if m.get("hc") is not None:
                c_f.append(m["hc"] or 0); c_a.append(m["ac"] or 0)
            if m.get("hy") is not None:
                y_f.append(m["hy"] or 0); r_f.append(m["hr"] or 0)
            if m.get("hst") is not None:
                sot.append(m["hst"] or 0)
        elif key == ak:
            gf.append(m["ag"] or 0); ga.append(m["hg"] or 0)
            if m.get("htag") is not None:
                ht_f.append(m["htag"] or 0); ht_a.append(m["hthg"] or 0)
            if m.get("ac") is not None:
                c_f.append(m["ac"] or 0); c_a.append(m["hc"] or 0)
            if m.get("ay") is not None:
                y_f.append(m["ay"] or 0); r_f.append(m["ar"] or 0)
            if m.get("ast") is not None:
                sot.append(m["ast"] or 0)
        else:
            continue
        used += 1
        if used >= n:
            break
    lg = _league_means()
    return {
        "n": used,
        "gf": _blend(used, _avg(gf, lg["gf"]), lg["gf"]),
        "ga": _blend(used, _avg(ga, lg["gf"]), lg["gf"]),
        "ht_f": _blend(used, _avg(ht_f, lg["ht"]), lg["ht"]),
        "ht_a": _blend(used, _avg(ht_a, lg["ht"]), lg["ht"]),
        "cf": _blend(used, _avg(c_f, lg["hc"]), lg["hc"]),
        "ca": _blend(used, _avg(c_a, lg["hc"]), lg["hc"]),
        "yf": _blend(used, _avg(y_f, lg["hy"]), lg["hy"]),
        "rf": _blend(used, _avg(r_f, lg["hr"]), lg["hr"]),
        "sot": _blend(used, _avg(sot, lg["sot"]), lg["sot"]),
    }


def simple_lambda(home: str, away: str) -> tuple[float, float]:
    h, a = _team_last(team_key(home)), _team_last(team_key(away))
    return (h["gf"] + a["ga"]) / 2, (a["gf"] + h["ga"]) / 2


def xg_lambda(home: str, away: str) -> tuple[float, float]:
    def team_xg(k: str) -> float:
        pack = bahis_players.summary()
        if not pack.get("ok"):
            return _team_last(k)["sot"] * 0.32
        s = None
        for row in pack.get("seasons") or []:
            s = row["id"]
            break
        from bahis.players import _season
        sea = _season(s)
        tot = 0.0
        mx = 0
        if sea:
            for p in sea.get("players") or []:
                if team_info(p.get("team") or "")["key"] != k:
                    continue
                tot += float((p.get("stats") or {}).get("xg") or 0)
                mx = max(mx, int(p.get("matches") or 0))
        if tot > 0 and mx > 0:
            return tot / mx
        return _team_last(k)["sot"] * 0.32
    hk, ak = team_key(home), team_key(away)
    hf, af = team_xg(hk), team_xg(ak)
    # rakip yiyen ≈ kendi yediği; xG ev/dep karışımı
    h, a = _team_last(hk), _team_last(ak)
    lam = 0.55 * hf + 0.45 * a["ga"]
    mu = 0.55 * af + 0.45 * h["ga"]
    return max(lam, 0.2), max(mu, 0.2)


def _matrix(lam: float, mu: float, maxg: int = MAXG) -> list[list[float]]:
    m = [[poisson_pmf(lam, x) * poisson_pmf(mu, y) for y in range(maxg + 1)] for x in range(maxg + 1)]
    tot = sum(p for row in m for p in row) or 1.0
    return [[p / tot for p in row] for row in m]


def _from_matrix(M: list[list[float]]) -> dict:
    n = len(M)
    p1 = px = p2 = btts = 0.0
    tot = {}
    scores = []
    for x in range(n):
        for y in range(n):
            p = M[x][y]
            if x > y:
                p1 += p
            elif x == y:
                px += p
            else:
                p2 += p
            if x and y:
                btts += p
            tot[x + y] = tot.get(x + y, 0.0) + p
            scores.append((f"{x}-{y}", p))
    scores.sort(key=lambda r: r[1], reverse=True)
    ou = {}
    for line in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
        under = sum(tot.get(g, 0.0) for g in range(int(math.floor(line)) + 1))
        ou[str(line)] = {"under": under, "over": 1 - under}
    return {
        "1": p1, "X": px, "2": p2,
        "bttsYes": btts, "bttsNo": 1 - btts,
        "ou": ou, "scores": scores, "tot": tot,
    }


def _mix_1x2(a: dict, b: dict, c: dict) -> dict:
    return {
        k: W_POIS * a[k] + W_ELO * b[k] + W_XG * c[k]
        for k in ("1", "X", "2")
    }


def _norm(d: dict) -> dict:
    s = sum(d.values()) or 1.0
    return {k: v / s for k, v in d.items()}


def _pick(p: dict, h: str, a: str) -> tuple[str, str, int]:
    k = max(p, key=p.get)
    if k == "1":
        return k, f"{h} kazanır", _pct(p[k])
    if k == "2":
        return k, f"{a} kazanır", _pct(p[k])
    return k, "Beraberlik", _pct(p[k])


def _overround(odds: dict | None) -> dict | None:
    raw = {}
    for sel, field in (("1", "home"), ("X", "draw"), ("2", "away")):
        o = (odds or {}).get(field)
        if not o or o <= 1:
            return None
        raw[sel] = 1 / float(o)
    tot = sum(raw.values())
    if tot <= 0:
        return None
    return {
        "sum": _round_p(tot),
        "overround": _round_p(tot - 1),
        "pct": round((tot - 1) * 100, 1),
        "raw": {k: _round_p(v) for k, v in raw.items()},
        "fair": {k: _round_p(v / tot) for k, v in raw.items()},
    }


def _log_n() -> int:
    if not os.path.isfile(LOG):
        return 0
    try:
        with open(LOG, encoding="utf-8") as f:
            return max(sum(1 for _ in f) - 1, 0)
    except OSError:
        return 0


def _value(probs: dict, odds: dict) -> list[dict]:
    out = []
    ov = _overround(odds)
    bm = BankrollManager(
        starting_bankroll=10000,
        min_edge=VALUE_EDGE,
        kelly_multiplier=KELLY_FRAC,
        max_stake_pct=0.03,
    )
    for sel, field in (("1", "home"), ("X", "draw"), ("2", "away")):
        o = (odds or {}).get(field)
        if not o or o <= 1:
            continue
        implied = 1 / float(o)
        fair = (ov["fair"][sel] if ov else implied)
        edge = probs[sel] - implied
        ev = bm.evaluate_bet("m", "1X2", sel, probs[sel], float(o))
        out.append({
            "sel": sel,
            "odds": round(float(o), 2),
            "model": _round_p(probs[sel]),
            "implied": _round_p(implied),
            "impliedFair": _round_p(fair),
            "edge": _round_p(edge),
            "edgeFair": _round_p(probs[sel] - fair),
            "isValue": edge >= VALUE_EDGE,
            "stake": ev.get("suggested_stake") or 0,
            "kelly": ev.get("kelly_fraction_applied") or 0,
            "reason": ev.get("reject_reason") or "",
        })
    return out


def _log(row: dict) -> None:
    exists = os.path.isfile(LOG)
    try:
        with open(LOG, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            if not exists:
                w.writeheader()
            w.writerow(row)
    except OSError:
        pass


def _find(mid: str) -> dict | None:
    for m in all_matches():
        if m["id"] == mid:
            return m
    return None


def _ht_lambda(home: str, away: str) -> tuple[float, float, float, float]:
    h, a = _team_last(home), _team_last(away)
    ht_h = (h["ht_f"] + a["ht_a"]) / 2
    ht_a = (a["ht_f"] + h["ht_a"]) / 2
    ft_h, ft_a = simple_lambda(home, away)
    sh_h = max(ft_h - ht_h, 0.15)
    sh_a = max(ft_a - ht_a, 0.15)
    return ht_h, ht_a, sh_h, sh_a


def _mc_bundle(lam: float, mu: float, ht_h: float, ht_a: float, sh_h: float, sh_a: float,
               c_h: float, c_a: float, y_h: float, y_a: float, r_h: float, r_a: float) -> dict:
    random.seed(42)
    p1 = px = p2 = 0
    first_h = first_a = nog = 0
    ht1 = htx = ht2 = 0
    sh1 = shx = sh2 = 0
    half_h = half_a = half_d = 0
    ht_btts = 0
    odd = 0
    win1 = win2p = aw1 = aw2p = 0
    corners = {k: 0 for k in ("le8", "9_11", "ge12")}
    red_yes = 0
    more_c_h = more_c_a = c_eq = 0
    card_h_more = card_a_more = card_eq = 0
    n = MC_N
    for _ in range(n):
        h1, a1 = _sample_pois(ht_h), _sample_pois(ht_a)
        h2, a2 = _sample_pois(sh_h), _sample_pois(sh_a)
        hg, ag = h1 + h2, a1 + a2
        if hg > ag:
            p1 += 1
            if hg - ag == 1:
                win1 += 1
            else:
                win2p += 1
        elif hg == ag:
            px += 1
        else:
            p2 += 1
            if ag - hg == 1:
                aw1 += 1
            else:
                aw2p += 1
        if hg + ag == 0:
            nog += 1
        elif random.random() < (hg / (hg + ag)):
            first_h += 1
        else:
            first_a += 1
        if h1 > a1:
            ht1 += 1
        elif h1 == a1:
            htx += 1
        else:
            ht2 += 1
        if h2 > a2:
            sh1 += 1
        elif h2 == a2:
            shx += 1
        else:
            sh2 += 1
        if (h1 + a1) > (h2 + a2):
            half_h += 1
        elif (h1 + a1) < (h2 + a2):
            half_a += 1
        else:
            half_d += 1
        if h1 and a1:
            ht_btts += 1
        if (hg + ag) % 2:
            odd += 1
        ch, ca = _sample_pois(c_h), _sample_pois(c_a)
        totc = ch + ca
        if totc <= 8:
            corners["le8"] += 1
        elif totc <= 11:
            corners["9_11"] += 1
        else:
            corners["ge12"] += 1
        if ch > ca:
            more_c_h += 1
        elif ch < ca:
            more_c_a += 1
        else:
            c_eq += 1
        yh, ya = _sample_pois(y_h), _sample_pois(y_a)
        rh, ra = _sample_pois(r_h), _sample_pois(r_a)
        if rh + ra > 0:
            red_yes += 1
        ph, pa = yh + 2 * rh, ya + 2 * ra
        if ph > pa:
            card_h_more += 1
        elif ph < pa:
            card_a_more += 1
        else:
            card_eq += 1
    f = lambda x: x / n
    return {
        "mc_1x2": {"1": f(p1), "X": f(px), "2": f(p2)},
        "first_goal": {"home": f(first_h), "away": f(first_a), "none": f(nog)},
        "ht": {"1": f(ht1), "X": f(htx), "2": f(ht2)},
        "sh": {"1": f(sh1), "X": f(shx), "2": f(sh2)},
        "half_more": {"first": f(half_h), "second": f(half_a), "eq": f(half_d)},
        "ht_btts": f(ht_btts),
        "odd": f(odd), "even": 1 - f(odd),
        "margin": {"h1": f(win1), "h2p": f(win2p), "a1": f(aw1), "a2p": f(aw2p)},
        "corners_bucket": {k: f(v) for k, v in corners.items()},
        "corner_more": {"home": f(more_c_h), "away": f(more_c_a), "eq": f(c_eq)},
        "red_yes": f(red_yes),
        "card_more": {"home": f(card_h_more), "away": f(card_a_more), "eq": f(card_eq)},
    }


def _line(p: dict) -> list[dict]:
    return [{"k": k, "p": _round_p(v), "pct": _pct(v)} for k, v in p.items()]


def detail(mid: str) -> dict:
    m = _find(mid)
    if not m:
        return {"ok": False, "error": "maç yok"}
    hk, ak = m["home"]["key"], m["away"]["key"]
    hn, an = m["home"]["name"], m["away"]["name"]
    odds = m.get("odds") or {}
    if not (odds.get("home") and odds.get("draw") and odds.get("away")):
        from bahis.league import h2h
        odds = h2h(hk, ak).get("odds") or odds
    lam_p, mu_p = simple_lambda(hk, ak)
    try:
        xg = _dc_fit().expected_goals(hk, ak)
        lam_d, mu_d = xg["lambda"], xg["mu"]
    except Exception:
        lam_d, mu_d = lam_p, mu_p
    lam_x, mu_x = xg_lambda(hk, ak)
    lam = 0.40 * lam_p + 0.35 * lam_d + 0.25 * lam_x
    mu = 0.40 * mu_p + 0.35 * mu_d + 0.25 * mu_x
    Mp, Mx = _matrix(lam_p, mu_p), _matrix(lam_x, mu_x)
    Me = _matrix(lam, mu)
    pp, pxg, pe = _from_matrix(Mp), _from_matrix(Mx), _from_matrix(Me)
    elo_p = _elo_fit().predict_match(hk, ak)
    ens = _norm(_mix_1x2(
        {"1": pp["1"], "X": pp["X"], "2": pp["2"]},
        {"1": elo_p["1"], "X": elo_p["X"], "2": elo_p["2"]},
        {"1": pxg["1"], "X": pxg["X"], "2": pxg["2"]},
    ))
    ht_h, ht_a, sh_h, sh_a = _ht_lambda(hk, ak)
    hs, aws = _team_last(hk), _team_last(ak)
    c_h, c_a = (hs["cf"] + aws["ca"]) / 2, (aws["cf"] + hs["ca"]) / 2
    y_h, y_a = hs["yf"], aws["yf"]
    r_h, r_a = hs["rf"], aws["rf"]
    mc = _mc_bundle(lam, mu, ht_h, ht_a, sh_h, sh_a, c_h, c_a, y_h, y_a, r_h, r_a)
    values = _value(ens, odds)
    ov = _overround(odds)
    fit_n = len(_played())
    log_n = _log_n()
    pick, text, pct = _pick(ens, hn, an)
    htM = _from_matrix(_matrix(ht_h, ht_a, 5))
    # İY/MS yaklaşık: HT bağımsız × FT yön (MC daha doğru ama 9 hücre için HT×kalan)
    iy_ms = {}
    for a, b in (("1", "1"), ("1", "X"), ("1", "2"), ("X", "1"), ("X", "X"), ("X", "2"), ("2", "1"), ("2", "X"), ("2", "2")):
        iy_ms[f"{a}/{b}"] = _round_p(mc["ht"].get(a, 0) * ens.get(b, 0) * 1.15)
    s = sum(iy_ms.values()) or 1
    iy_ms = {k: _round_p(v / s) for k, v in iy_ms.items()}
    windows = []
    rate = (lam + mu) / 90
    for lo, hi in ((0, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 90)):
        p = 1 - math.exp(-rate * (hi - lo + 1))
        windows.append({"k": f"{lo}-{hi}", "p": _round_p(p), "pct": _pct(p)})
    try:
        scorers = bahis_players.pair_scorers(hk, ak, n=6)
    except Exception:
        scorers = {"a": [], "b": []}
    p_h_score = 1 - poisson_pmf(lam, 0)
    p_a_score = 1 - poisson_pmf(mu, 0)

    def _annotate(rows, team_lam, p_team, p_first):
        xs = [float((p.get("stats") or {}).get("xg") or 0) or float((p.get("stats") or {}).get("goals") or 0) for p in rows]
        tot = sum(xs) or 1.0
        out = []
        for p, x in zip(rows, xs):
            share = x / tot
            any_g = 1 - math.exp(-share * team_lam)
            st = p.get("stats") or {}
            out.append({
                **p,
                "share": _round_p(share),
                "anyGoal": _round_p(any_g),
                "firstGoal": _round_p(share * p_first),
                "lastGoal": _round_p(share * p_team),
                "nextGoal": _round_p(share * p_first),
                "pen": int(st.get("pens_won") or 0),
                "yellow": int(st.get("yellow") or 0),
                "red": int(st.get("red") or 0),
            })
        return out

    scorers = {
        **scorers,
        "a": _annotate(scorers.get("a") or [], lam, p_h_score, mc["first_goal"]["home"]),
        "b": _annotate(scorers.get("b") or [], mu, p_a_score, mc["first_goal"]["away"]),
    }
    home_ou = {}
    for line in (0.5, 1.5, 2.5):
        under = sum(poisson_pmf(lam, k) for k in range(int(math.floor(line)) + 1))
        home_ou[str(line)] = {"under": _round_p(under), "over": _round_p(1 - under)}
    away_ou = {}
    for line in (0.5, 1.5, 2.5):
        under = sum(poisson_pmf(mu, k) for k in range(int(math.floor(line)) + 1))
        away_ou[str(line)] = {"under": _round_p(under), "over": _round_p(1 - under)}
    # AH 0:1 away starts +1 → home -1
    ah01 = {"1": 0.0, "X": 0.0, "2": 0.0}  # home -1
    ah10 = {"1": 0.0, "X": 0.0, "2": 0.0}  # away -1
    n = len(Me)
    for x in range(n):
        for y in range(n):
            p = Me[x][y]
            dh, da = x - y, y - x
            if dh >= 2:
                ah01["1"] += p
            elif dh == 1:
                ah01["X"] += p
            else:
                ah01["2"] += p
            if da >= 2:
                ah10["2"] += p
            elif da == 1:
                ah10["X"] += p
            else:
                ah10["1"] += p
    ms25 = {
        "1_over": ens["1"] * pe["ou"]["2.5"]["over"],
        "1_under": ens["1"] * pe["ou"]["2.5"]["under"],
        "X_over": ens["X"] * pe["ou"]["2.5"]["over"],
        "X_under": ens["X"] * pe["ou"]["2.5"]["under"],
        "2_over": ens["2"] * pe["ou"]["2.5"]["over"],
        "2_under": ens["2"] * pe["ou"]["2.5"]["under"],
    }
    s25 = sum(ms25.values()) or 1
    ms25 = {k: _round_p(v / s25) for k, v in ms25.items()}
    kg25 = {
        "yes_over": pe["bttsYes"] * pe["ou"]["2.5"]["over"],
        "yes_under": pe["bttsYes"] * pe["ou"]["2.5"]["under"],
        "no_over": pe["bttsNo"] * pe["ou"]["2.5"]["over"],
        "no_under": pe["bttsNo"] * pe["ou"]["2.5"]["under"],
    }
    sk = sum(kg25.values()) or 1
    kg25 = {k: _round_p(v / sk) for k, v in kg25.items()}
    c_tot = c_h + c_a
    corner_ou = {}
    for line in (8.5, 9.5, 10.5, 11.5):
        under = sum(poisson_pmf(c_tot, k) for k in range(int(math.floor(line)) + 1))
        corner_ou[str(line)] = {"under": _round_p(under), "over": _round_p(1 - under)}
    ht_c = c_tot * 0.45
    ht_c_ou = {}
    for line in (4.5, 5.5):
        under = sum(poisson_pmf(ht_c, k) for k in range(int(math.floor(line)) + 1))
        ht_c_ou[str(line)] = {"under": _round_p(under), "over": _round_p(1 - under)}
    pts_h, pts_a = y_h + 2 * r_h, y_a + 2 * r_a
    card_ou = {}
    for line in (3.5, 4.5, 5.5):
        under = sum(poisson_pmf(pts_h + pts_a, k) for k in range(int(math.floor(line)) + 1))
        card_ou[str(line)] = {"under": _round_p(under), "over": _round_p(1 - under)}
    started = False
    ko = m.get("kickoff")
    if ko:
        try:
            started = datetime.fromisoformat(ko) <= datetime.now(TR)
        except ValueError:
            started = False
    out = {
        "ok": True,
        "match": {
            "id": m["id"],
            "when": _when(m.get("kickoff")),
            "kickoff": m.get("kickoff"),
            "week": m.get("week"),
            "venue": m.get("venue"),
            "played": bool(m.get("played")),
            "hg": m.get("hg"),
            "ag": m.get("ag"),
            "home": m["home"],
            "away": m["away"],
            "odds": odds,
            "form_h": m.get("form_h"),
            "form_a": m.get("form_a"),
        },
        "models": {
            "poisson": {"lam": _round_p(lam_p), "mu": _round_p(mu_p), **{k: _round_p(pp[k]) for k in ("1", "X", "2")}},
            "dixon": {"lam": _round_p(lam_d), "mu": _round_p(mu_d)},
            "xg": {"lam": _round_p(lam_x), "mu": _round_p(mu_x), **{k: _round_p(pxg[k]) for k in ("1", "X", "2")}},
            "elo": {k: _round_p(elo_p[k]) for k in ("1", "X", "2")},
            "ensemble": {k: _round_p(ens[k]) for k in ("1", "X", "2")},
            "monteCarlo": {k: _round_p(mc["mc_1x2"][k]) for k in ("1", "X", "2")},
            "n_last": LAST_N,
            "mc_n": MC_N,
            "weights": {"poisson": W_POIS, "elo": W_ELO, "xg": W_XG},
        },
        "xg": {"home": _round_p(lam), "away": _round_p(mu)},
        "pick": pick, "text": text, "pct": pct,
        "value": values,
        "overround": ov,
        "sample": {
            "fit_n": fit_n,
            "form_n": LAST_N,
            "home_n": hs["n"],
            "away_n": aws["n"],
            "log_n": log_n,
            "min": SAMPLE_MIN,
            "ok_at": SAMPLE_OK,
        },
        "warnings": [
            {
                "id": "overround",
                "ok": bool(ov and ov["pct"] <= 12),
                "title": "Overround",
                "text": (
                    f"Piyasa toplamı %{ov['sum']*100:.1f} (marj %{ov['pct']}). "
                    "Bookmaker %100'ün üstünü açar (genelde %105–110). Bu marjı yenmek zor."
                    if ov else
                    "Oran yok — overround ölçülemedi. Bookmaker genelde %105–110 açar."
                ),
            },
            {
                "id": "sample",
                "ok": fit_n >= SAMPLE_OK and log_n >= SAMPLE_MIN,
                "title": "Örneklem",
                "text": (
                    f"Lig fit {fit_n} maç · form ev {hs['n']}/dep {aws['n']} (son {LAST_N}) · "
                    f"ileriye dönük log {log_n}. Model en az {SAMPLE_MIN}–{SAMPLE_OK} maçla test edilmeli."
                ),
            },
            {
                "id": "kelly",
                "ok": True,
                "title": "Disiplin",
                "text": "¼ Kelly · tek bahis tavanı kasanın %3'ü. Uyarı: Kelly'nin en fazla yarısı; tüm kasa tek maça yasak.",
            },
            {
                "id": "live",
                "ok": not started,
                "title": "Canlı bahis",
                "text": (
                    "Maç başladı — gördüğün sayılar pre-match. Maç içi xG, kırmızı kart ve momentum güncellenmiyor."
                    if started else
                    "Canlıda pre-match model yetmez: maç içi xG, kırmızı kart ve momentum ile güncelle."
                ),
            },
        ],
        "markets": {
            "result": {k: _round_p(ens[k]) for k in ("1", "X", "2")},
            "doubleChance": {"1X": _round_p(ens["1"] + ens["X"]), "12": _round_p(ens["1"] + ens["2"]), "X2": _round_p(ens["X"] + ens["2"])},
            "ah01": {k: _round_p(v) for k, v in ah01.items()},
            "ah10": {k: _round_p(v) for k, v in ah10.items()},
            "correctScore": [{"score": s, "p": _round_p(p), "pct": _pct(p)} for s, p in pe["scores"][:8]],
            "margin": {k: _round_p(v) for k, v in mc["margin"].items()},
            "qualify": None,
            "ou": {k: {"under": _round_p(v["under"]), "over": _round_p(v["over"])} for k, v in pe["ou"].items()},
            "btts": {"yes": _round_p(pe["bttsYes"]), "no": _round_p(pe["bttsNo"])},
            "ms25": ms25,
            "kg25": kg25,
            "homeOu": home_ou,
            "awayOu": away_ou,
            "oddEven": {"odd": _round_p(mc["odd"]), "even": _round_p(mc["even"])},
            "firstGoal": {k: _round_p(v) for k, v in mc["first_goal"].items()},
            "goalWindows": windows,
            "ht": {k: _round_p(v) for k, v in mc["ht"].items()},
            "sh": {k: _round_p(v) for k, v in mc["sh"].items()},
            "htOu15": {"under": _round_p(htM["ou"]["1.5"]["under"]), "over": _round_p(htM["ou"]["1.5"]["over"])},
            "iyMs": iy_ms,
            "halfMore": {k: _round_p(v) for k, v in mc["half_more"].items()},
            "htBtts": _round_p(mc["ht_btts"]),
            "htScores": [{"score": s, "p": _round_p(p), "pct": _pct(p)} for s, p in htM["scores"][:5]],
            "cornersBucket": {k: _round_p(v) for k, v in mc["corners_bucket"].items()},
            "cornerOu": corner_ou,
            "htCornerOu": ht_c_ou,
            "cornerMore": {k: _round_p(v) for k, v in mc["corner_more"].items()},
            "firstCorner": {
                "home": _round_p(c_h / (c_h + c_a)),
                "away": _round_p(c_a / (c_h + c_a)),
            },
            "homeCornerOu": {
                "8.5": {
                    "under": _round_p(sum(poisson_pmf(c_h, k) for k in range(9))),
                    "over": _round_p(1 - sum(poisson_pmf(c_h, k) for k in range(9))),
                }
            },
            "awayCornerOu": {
                "8.5": {
                    "under": _round_p(sum(poisson_pmf(c_a, k) for k in range(9))),
                    "over": _round_p(1 - sum(poisson_pmf(c_a, k) for k in range(9))),
                }
            },
            "redYes": _round_p(mc["red_yes"]),
            "cardOu": card_ou,
            "homeCardOu": {
                "1.5": {
                    "under": _round_p(sum(poisson_pmf(pts_h, k) for k in range(2))),
                    "over": _round_p(1 - sum(poisson_pmf(pts_h, k) for k in range(2))),
                },
                "2.5": {
                    "under": _round_p(sum(poisson_pmf(pts_h, k) for k in range(3))),
                    "over": _round_p(1 - sum(poisson_pmf(pts_h, k) for k in range(3))),
                },
            },
            "awayCardOu": {
                "1.5": {
                    "under": _round_p(sum(poisson_pmf(pts_a, k) for k in range(2))),
                    "over": _round_p(1 - sum(poisson_pmf(pts_a, k) for k in range(2))),
                },
                "2.5": {
                    "under": _round_p(sum(poisson_pmf(pts_a, k) for k in range(3))),
                    "over": _round_p(1 - sum(poisson_pmf(pts_a, k) for k in range(3))),
                },
            },
            "cardMore": {k: _round_p(v) for k, v in mc["card_more"].items()},
            "live": {
                "started": started,
                "remainWinner": None if not started else {k: _round_p(ens[k]) for k in ("1", "X", "2")},
                "tenMin": {
                    "goal": _round_p(1 - math.exp(-(lam + mu) * 10 / 90)),
                    "corner": _round_p(1 - math.exp(-c_tot * 10 / 90)),
                    "card": _round_p(1 - math.exp(-(pts_h + pts_a) * 10 / 90)),
                },
                "extra": None,
            },
        },
        "scorers": scorers,
        "note": "Nesine / Bilyoner / Misli / Tuttur / Birebin / Oley — İddaa planı. Kupon açılmaz.",
        "grade": None,
    }
    try:
        from bahis.results import grade_of
        g = grade_of(m["id"])
        if g:
            out["grade"] = {
                "played": bool(g.get("played")),
                "hg": g.get("hg"),
                "ag": g.get("ag"),
                "result": g.get("result"),
                "pick": g.get("pick"),
                "hit": g.get("hit"),
                "snap_kind": g.get("snap_kind"),
            }
    except Exception:
        pass
    if not m.get("form_h"):
        from bahis.league import form
        out["match"]["form_h"] = form(hk)
        out["match"]["form_a"] = form(ak)
    _log({
        "ts": datetime.now(TR).isoformat(timespec="seconds"),
        "id": m["id"],
        "home": hn,
        "away": an,
        "pick": pick,
        "p1": ens["1"],
        "px": ens["X"],
        "p2": ens["2"],
        "lam": lam,
        "mu": mu,
    })
    return out


def _quick_models(hk: str, ak: str) -> dict:
    lam_p, mu_p = simple_lambda(hk, ak)
    try:
        xg = _dc_fit().expected_goals(hk, ak)
        lam_d, mu_d = xg["lambda"], xg["mu"]
    except Exception:
        lam_d, mu_d = lam_p, mu_p
    lam_x, mu_x = xg_lambda(hk, ak)
    pp, pxg = _from_matrix(_matrix(lam_p, mu_p)), _from_matrix(_matrix(lam_x, mu_x))
    elo_p = _elo_fit().predict_match(hk, ak)
    ens = _norm(_mix_1x2(
        {"1": pp["1"], "X": pp["X"], "2": pp["2"]},
        {"1": elo_p["1"], "X": elo_p["X"], "2": elo_p["2"]},
        {"1": pxg["1"], "X": pxg["X"], "2": pxg["2"]},
    ))
    lam = 0.40 * lam_p + 0.35 * lam_d + 0.25 * lam_x
    mu = 0.40 * mu_p + 0.35 * mu_d + 0.25 * mu_x
    return {
        "poisson": {**{k: _round_p(pp[k]) for k in ("1", "X", "2")}},
        "xg": {**{k: _round_p(pxg[k]) for k in ("1", "X", "2")}},
        "ensemble": {k: _round_p(ens[k]) for k in ("1", "X", "2")},
        "xg_n": {"home": _round_p(lam), "away": _round_p(mu)},
    }


def upcoming_kind(kind: str, team: str | None = None, limit: int = 24) -> dict:
    from datetime import timedelta
    now = datetime.now(TR)
    until = (now + timedelta(days=21)).isoformat()
    now_s = now.isoformat()
    rows = []
    for m in all_matches():
        if m.get("played"):
            continue
        ko = m.get("kickoff") or ""
        if ko < now_s[:10] or ko > until:
            continue
        if team and team not in (m["home"]["key"], m["away"]["key"]):
            continue
        md = _quick_models(m["home"]["key"], m["away"]["key"])
        if kind == "poisson":
            mr = md["poisson"]
        elif kind == "xg":
            mr = md["xg"]
        else:
            mr = md["ensemble"]
        pick, text, pct = _pick(mr, m["home"]["name"], m["away"]["name"])
        rows.append({
            "id": m["id"],
            "when": _when(m.get("kickoff")),
            "week": m.get("week"),
            "venue": m.get("venue"),
            "home": m["home"],
            "away": m["away"],
            "odds": m.get("odds") or {},
            "matchResult": mr,
            "pick": pick,
            "text": text,
            "pct": pct,
            "xg": md["xg_n"],
        })
        if len(rows) >= limit:
            break
    return {
        "ok": True,
        "model": kind,
        "note": f"{kind} · son {LAST_N} maç · ağırlık {int(W_POIS*100)}/{int(W_ELO*100)}/{int(W_XG*100)}",
        "n": len(rows),
        "preds": rows,
        "strengths": [],
    }
