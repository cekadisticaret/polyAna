"""İlk 10'un rejim oyu + coin-en-iyi — $48 sanal Poly dolum. TOP1–4 sayılmaz.

Grup BTC/ETH/SOL'de çoğunluk varsa o yöne $48 girer.
TOP4 her coinde o anki en yüksek WR algoritmanın :05 yönünü izler.
Dolum `pm_sanal_quote` (VWAP + taker ücret); tutarsa `pm_win_profit`,
tutmazsa −(spent+fee). Gerçek emir yok.

Cron: `algo_consensus_log.py run` (:08) kaydeder + kapatır.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
BOOK_FILE = os.path.join(_DIR, "vote_paper.json")
STAKE = 48.0
KEEP_DAYS = 90
REGIMES = ("range", "trend", "live", "symbest")


def _now():
    from algo_consensus_log import _now as _cnow
    return _cnow()


def _atomic_write(path: str, data: dict) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".vote_paper.", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _lock_run(fn):
    os.makedirs(_DIR, exist_ok=True)
    lock_path = BOOK_FILE + ".lock"
    with open(lock_path, "a+", encoding="utf-8") as lk:
        fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(lk.fileno(), fcntl.LOCK_UN)


def load_book() -> dict:
    if not os.path.exists(BOOK_FILE):
        return {"stake": STAKE, "hours": [], "updated_at_tr": None}
    try:
        with open(BOOK_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"stake": STAKE, "hours": [], "updated_at_tr": None}
    data.setdefault("hours", [])
    data.setdefault("stake", STAKE)
    return data


def _prune(hours: list) -> list:
    from algo_consensus_log import _now
    from datetime import timedelta
    cutoff = (_now() - timedelta(days=KEEP_DAYS)).date().isoformat()
    return [h for h in hours if str(h.get("slot_date") or "") >= cutoff]


def _slot_dt(row: dict) -> datetime:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Istanbul")
    day = str(row.get("slot_date") or "")
    hour = int(row.get("slot_hour") or 0)
    return datetime.fromisoformat(f"{day}T{hour:02d}:05:00").replace(tzinfo=tz)


def _pm_quote(symbol: str, direction: str, when: datetime, *, allow_closed: bool = False) -> dict | None:
    """`pm_sanal_quote` ile aynı dolum; kapalı saatte mid yedek."""
    from datetime import timedelta, timezone
    from pm_trader_helpers import pm_find_market, pm_sanal_fill, pm_taker_fee
    when_utc = when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)
    sym = str(symbol or "").upper()
    if not sym.endswith("USDT"):
        sym = f"{sym}USDT"
    et_hour = (when_utc - timedelta(hours=4)).hour
    pm = pm_find_market(sym, et_hour, when_utc)
    if not pm:
        return None
    if pm.get("closed") and not allow_closed:
        return None
    op = pm.get("outcome_prices") or []
    if len(op) < 2:
        return None
    mid = float(op[0]) if direction == "UP" else float(op[1])
    if allow_closed and not (0.08 <= mid <= 0.92):
        return None
    token = pm["up_token"] if direction == "UP" else pm["down_token"]
    fill = pm_sanal_fill(token, STAKE, fallback_price=mid)
    if not fill:
        return None
    tp, size, spent = fill["price"], fill["size"], fill["spent"]
    if not (0.02 <= tp <= 0.98):
        return None
    fee = pm_taker_fee(size, tp)
    return {
        "pm_slug": pm["slug"],
        "pm_title": pm.get("title", ""),
        "pm_token_dir": direction,
        "pm_entry_price": tp,
        "pm_quote_src": fill["src"],
        "pm_fill_vwap": fill["vwap"],
        "pm_mid_price": round(mid, 4),
        "pm_fee": fee,
        "pm_spent": spent,
        "pm_size": size,
        "to_win": size,
        "pm_win_payout": size,
        "pm_win_profit": round(size - spent - fee, 2),
    }


def _apply_quote(t: dict, q: dict) -> None:
    t["pm_slug"] = q.get("pm_slug")
    t["pm_entry_price"] = q.get("pm_entry_price")
    t["pm_quote_src"] = q.get("pm_quote_src")
    t["pm_fill_vwap"] = q.get("pm_fill_vwap")
    t["pm_mid_price"] = q.get("pm_mid_price")
    t["pm_fee"] = q.get("pm_fee")
    t["pm_spent"] = q.get("pm_spent")
    t["pm_size"] = q.get("pm_size")
    t["to_win"] = q.get("to_win")
    t["pm_win_payout"] = q.get("pm_win_payout")
    t["pm_win_profit"] = q.get("pm_win_profit")


def _quote_trade(t: dict, now: datetime, *, allow_closed: bool = False) -> bool:
    """Eksik Poly kotasyonunu doldur. Zaten varsa dokunma."""
    if t.get("pm_spent"):
        return False
    q = _pm_quote(str(t.get("symbol") or ""), str(t.get("dir") or ""), now, allow_closed=allow_closed)
    if not q:
        return False
    _apply_quote(t, q)
    return True


def _recompute_pnl(t: dict) -> bool:
    if t.get("actual") not in ("UP", "DOWN", "FLAT") or not t.get("pm_spent"):
        return False
    from pm_trader_helpers import sanal_pnl
    won = bool(t.get("win"))
    t["pnl"] = sanal_pnl(_trade_pos(t), won)
    return True


def _trade_pos(t: dict) -> dict:
    return {
        "amount": t.get("stake") or STAKE,
        "pm_spent": t.get("pm_spent"),
        "pm_size": t.get("pm_size"),
        "to_win": t.get("to_win"),
        "pm_entry_price": t.get("pm_entry_price"),
        "pm_fee": t.get("pm_fee"),
        "pm_slug": t.get("pm_slug"),
        "pm_win_profit": t.get("pm_win_profit"),
    }


def _trades_from_group(g: dict, now: datetime) -> list[dict]:
    out = []
    for c in g.get("coins") or []:
        winner = c.get("winner")
        if winner not in ("UP", "DOWN"):
            continue
        if int(c.get("n") or 0) <= 0:
            continue
        t = {
            "symbol": c.get("symbol"),
            "dir": winner,
            "up": int(c.get("up") or 0),
            "down": int(c.get("down") or 0),
            "n": int(c.get("n") or 0),
            "stake": STAKE,
            "actual": None,
            "win": None,
            "pnl": None,
            "source_algo": c.get("analiz"),
            "source_short": c.get("analiz_short"),
        }
        _quote_trade(t, now)
        out.append(t)
    return out


def record_from_votes(votes: dict, now: datetime | None = None) -> dict:
    """Bu saatin grup oylarını $48 işlem olarak kilitle. Sonuçlu saate dokunma."""
    if not votes or not votes.get("ok") or not (votes.get("groups") or []):
        return load_book()
    from algo_consensus_log import current_slot
    now = now or _now()
    if now.minute < 5:
        return load_book()
    sid, hour, day = current_slot(now)

    def _write():
        book = load_book()
        hours = list(book.get("hours") or [])
        by_id = {h.get("id"): h for h in hours if h.get("id")}
        prev = by_id.get(sid) or {}
        settled = any(
            t.get("actual") in ("UP", "DOWN", "FLAT")
            for g in (prev.get("groups") or [])
            for t in (g.get("trades") or [])
        )
        if settled:
            return book
        if prev.get("saved_at_tr"):
            filled = False
            have = {g.get("regime"): g for g in (prev.get("groups") or [])}
            for g in votes.get("groups") or []:
                rg = g.get("regime")
                trades = _trades_from_group(g, now)
                if not trades:
                    continue
                old = have.get(rg)
                if old is None:
                    prev.setdefault("groups", []).append({
                        "regime": rg,
                        "label": g.get("label"),
                        "books": int(g.get("books") or 0),
                        "trades": trades,
                    })
                    have[rg] = prev["groups"][-1]
                    filled = True
                    continue
                if not (old.get("trades") or []):
                    old["trades"] = trades
                    old["books"] = int(g.get("books") or old.get("books") or 0)
                    filled = True
            for g in prev.get("groups") or []:
                for t in g.get("trades") or []:
                    if _quote_trade(t, now):
                        filled = True
            if filled:
                book = {
                    "stake": STAKE,
                    "hours": hours,
                    "updated_at_tr": now.isoformat(timespec="seconds"),
                }
                _atomic_write(BOOK_FILE, book)
            return book
        groups = []
        for g in votes.get("groups") or []:
            trades = _trades_from_group(g, now)
            groups.append({
                "regime": g.get("regime"),
                "label": g.get("label"),
                "books": int(g.get("books") or 0),
                "trades": trades,
            })
        if not any(g.get("trades") for g in groups):
            if not prev:
                return book
        row = {
            "id": sid,
            "slot_date": day,
            "slot_hour": hour,
            "slot_open_tr": f"{hour:02d}:05",
            "source": votes.get("source"),
            "source_n": votes.get("source_n"),
            "source_ids": list(votes.get("source_ids") or []),
            "saved_at_tr": now.isoformat(timespec="seconds"),
            "groups": groups,
        }
        by_id[sid] = row
        hours = _prune(sorted(by_id.values(), key=lambda h: h.get("id") or ""))
        book = {
            "stake": STAKE,
            "hours": hours,
            "updated_at_tr": now.isoformat(timespec="seconds"),
        }
        _atomic_write(BOOK_FILE, book)
        return book

    return _lock_run(_write)


def resolve_pending(now: datetime | None = None) -> dict:
    from algo_consensus_log import _actual_dir, _slot_ended
    now = now or _now()

    def _write():
        book = load_book()
        hours = list(book.get("hours") or [])
        changed = False
        for row in hours:
            if not _slot_ended(row, now):
                continue
            for g in row.get("groups") or []:
                trades = list(g.get("trades") or [])
                for t in trades:
                    if t.get("actual") in ("UP", "DOWN", "FLAT"):
                        continue
                    if t.get("dir") not in ("UP", "DOWN"):
                        continue
                    actual = _actual_dir(
                        str(t.get("symbol") or ""),
                        str(row.get("slot_date")),
                        int(row.get("slot_hour")),
                    )
                    if actual is None:
                        continue
                    if not t.get("pm_spent"):
                        _quote_trade(t, _slot_dt(row), allow_closed=True)
                    if not t.get("pm_spent"):
                        continue
                    from pm_trader_helpers import sanal_pnl
                    won = actual == t.get("dir") if actual in ("UP", "DOWN") else False
                    t["actual"] = actual
                    t["win"] = won
                    t["pnl"] = sanal_pnl(_trade_pos(t), won)
                    changed = True
                g["trades"] = trades
        if changed:
            book = {
                "stake": STAKE,
                "hours": _prune(hours),
                "updated_at_tr": now.isoformat(timespec="seconds"),
            }
            _atomic_write(BOOK_FILE, book)
        return book

    return _lock_run(_write)


def _hour_trades(book: dict, regime: str, slot_id: str | None) -> list[dict]:
    out = []
    for row in book.get("hours") or []:
        if slot_id and row.get("id") != slot_id:
            continue
        for g in row.get("groups") or []:
            if (g.get("regime") or "") != regime:
                continue
            out.extend(g.get("trades") or [])
    return out


def _fill_payload(t: dict) -> dict:
    spent = t.get("pm_spent")
    px = t.get("pm_entry_price")
    win_p = t.get("pm_win_profit")
    return {
        "pm_spent": spent,
        "pm_entry_price": px,
        "pm_size": t.get("pm_size"),
        "pm_win_profit": win_p,
        "paper_pnl": t.get("pnl"),
    }


def stats_by_regime(book: dict | None = None, slot_id: str | None = None) -> dict:
    book = book if book is not None else load_book()
    out = {}
    for rg in REGIMES:
        wins = n = 0
        pnl = 0.0
        slot_n = slot_open_n = 0
        slot_pnl = 0.0
        slot_open = False
        trades_now = []
        for row in book.get("hours") or []:
            sid = row.get("id")
            here = sid == slot_id if slot_id else False
            for g in row.get("groups") or []:
                if (g.get("regime") or "") != rg:
                    continue
                for t in g.get("trades") or []:
                    if here:
                        trades_now.append(t)
                    if t.get("pnl") is not None:
                        if t.get("pm_spent") is None:
                            continue
                        n += 1
                        pnl += float(t.get("pnl") or 0)
                        if here:
                            slot_n += 1
                            slot_pnl += float(t.get("pnl") or 0)
                        if t.get("win"):
                            wins += 1
                        continue
                    if here and t.get("pm_spent") is not None:
                        slot_open_n += 1
                        slot_open = True
        wr = round(100.0 * wins / n, 1) if n else None
        out[rg] = {
            "ok": True,
            "scored": n,
            "wins": wins,
            "wr": wr,
            "pnl": round(pnl, 2),
            "slot_pnl": round(slot_pnl, 2) if slot_n else None,
            "slot_n": slot_n,
            "slot_open_n": slot_open_n,
            "slot_open": slot_open,
            "fills": [_fill_payload(t) | {"symbol": t.get("symbol")} for t in trades_now],
            "stake": STAKE,
            "label": (f"%{wr:g} başarılı".replace(".", ",") if wr is not None else "henüz sonuç yok"),
            "detail": f"{wins}/{n} işlem · ${STAKE:g}" if n else "işlem yok",
        }
    return out


def attach_paper(votes: dict, *, persist: bool = False) -> dict:
    """Grup istatistiğini $48 oy defterinden yaz. persist=True cron / ilk kayıt."""
    votes = dict(votes or {})
    try:
        if persist:
            record_from_votes(votes)
            repair_quotes()
            book = resolve_pending()
        else:
            book = load_book()
        from algo_consensus_log import current_slot
        sid, _, _ = current_slot()
        by_rg = stats_by_regime(book, slot_id=sid)
        groups = []
        for g in votes.get("groups") or []:
            g = dict(g)
            st = dict(g.get("stats") or {})
            paper = by_rg.get(g.get("regime")) or {}
            st["pnl"] = paper.get("pnl")
            st["pnl_cum"] = paper.get("pnl")
            st["slot_pnl"] = paper.get("slot_pnl")
            st["slot_n"] = paper.get("slot_n")
            st["slot_open_n"] = paper.get("slot_open_n")
            st["slot_open"] = paper.get("slot_open")
            st["stake"] = STAKE
            st["paper_n"] = paper.get("scored")
            st["paper_wr"] = paper.get("wr")
            fills = {str(f.get("symbol") or ""): f for f in (paper.get("fills") or [])}
            coins = []
            for c in g.get("coins") or []:
                c = dict(c)
                f = fills.get(str(c.get("symbol") or ""))
                if f:
                    c.update({k: f.get(k) for k in (
                        "pm_spent", "pm_entry_price", "pm_size", "pm_win_profit", "paper_pnl",
                    )})
                coins.append(c)
            g["coins"] = coins
            g["stats"] = st
            groups.append(g)
        votes["groups"] = groups
        votes["paper"] = {"stake": STAKE, "ok": True, "slot_id": sid}
    except Exception as e:
        votes["paper"] = {"ok": False, "error": str(e)}
    return votes


def repair_quotes(now: datetime | None = None) -> dict:
    """Kotasyonsuz (eski ±$48) satırları slot saatinin Poly dolumuyla yeniden yaz."""
    now = now or _now()

    def _write():
        book = load_book()
        hours = list(book.get("hours") or [])
        changed = False
        for row in hours:
            when = _slot_dt(row)
            for g in row.get("groups") or []:
                for t in g.get("trades") or []:
                    if t.get("dir") not in ("UP", "DOWN"):
                        continue
                    if _quote_trade(t, when, allow_closed=True):
                        changed = True
                    if t.get("pm_spent") and t.get("actual") in ("UP", "DOWN", "FLAT"):
                        old = t.get("pnl")
                        if _recompute_pnl(t) and t.get("pnl") != old:
                            changed = True
        if changed:
            book = {
                "stake": STAKE,
                "hours": hours,
                "updated_at_tr": now.isoformat(timespec="seconds"),
            }
            _atomic_write(BOOK_FILE, book)
        return book

    return _lock_run(_write)


def run_from_votes(votes: dict) -> dict:
    record_from_votes(votes)
    repair_quotes()
    book = resolve_pending()
    return {"ok": True, "stats": stats_by_regime(book)}


TOP_KEYS = {
    "top1": ("range", "TOP1 · Durgun", "İlk 10 durgun oyu · $48 Poly dolum"),
    "top2": ("trend", "TOP2 · Trend", "İlk 10 trend oyu · $48 Poly dolum"),
    "top3": ("live", "TOP3 · Canlı", "İlk 10 canlı oyu · $48 Poly dolum"),
    "top4": ("symbest", "TOP4 · Sembol", "Coin başına en iyi · $48 Poly dolum"),
}
TOP_ALIASES = {
    "top1": "top1", "top1-durgun": "top1", "top1_durgun": "top1",
    "top2": "top2", "top2-trend": "top2", "top2_trend": "top2",
    "top3": "top3", "top3-canli": "top3", "top3_canli": "top3", "top3-canlı": "top3",
    "top4": "top4", "top4-sembol": "top4", "top4_sembol": "top4",
}


def is_top_key(key: str) -> bool:
    return TOP_ALIASES.get((key or "").lower().strip()) in TOP_KEYS


def normalize_top_key(key: str) -> str | None:
    return TOP_ALIASES.get((key or "").lower().strip())


def build_top_book(key: str, *, include_history: bool = False) -> dict | None:
    """Liste + detay — $48 oy grubunu sanal defter gibi."""
    kid = normalize_top_key(key)
    spec = TOP_KEYS.get(kid or "")
    if not spec:
        return None
    rg, name, title = spec
    book = load_book()
    from algo_consensus_log import current_slot
    sid, _, _ = current_slot()
    st = stats_by_regime(book, slot_id=sid).get(rg) or {}
    pnl = float(st.get("pnl") or 0)
    n = int(st.get("scored") or 0)
    wins = int(st.get("wins") or 0)
    wr = st.get("wr")
    cards = []
    recent = []
    for row in book.get("hours") or []:
        for g in row.get("groups") or []:
            if (g.get("regime") or "") != rg:
                continue
            slot_lbl = row.get("slot_open_tr") or ""
            day = row.get("slot_date") or ""
            for t in g.get("trades") or []:
                if t.get("pm_spent") is None:
                    continue
                up = t.get("dir") == "UP"
                src = t.get("source_short") or ""
                shown = f"{t.get('symbol')} · {src}" if src else t.get("symbol")
                if t.get("pnl") is None:
                    cards.append({
                        "name": shown,
                        "symbol": t.get("symbol"),
                        "side": "LONG" if up else "SHORT",
                        "dir_tr": "YÜKSELİR" if up else "DÜŞER",
                        "pm_entry_price": t.get("pm_entry_price"),
                        "pm_spent": t.get("pm_spent"),
                        "pm_size": t.get("pm_size"),
                        "to_win": t.get("to_win"),
                        "win_profit": t.get("pm_win_profit"),
                        "amount": t.get("pm_spent") or STAKE,
                        "slot_label": slot_lbl,
                    })
                    continue
                recent.append({
                    "symbol": t.get("symbol"),
                    "dir": t.get("dir"),
                    "dir_tr": "YÜKSELİR" if up else "DÜŞER",
                    "win": bool(t.get("win")),
                    "pnl": float(t.get("pnl") or 0),
                    "spent": float(t.get("pm_spent") or 0),
                    "pm_entry_price": t.get("pm_entry_price"),
                    "exit_time_tr": f"{day}T{slot_lbl}:00+03:00" if day and slot_lbl else "",
                    "slot_label": f"{day} {slot_lbl}".strip(),
                })
    recent.reverse()
    recent = recent[:100]
    init = 1000.0
    return {
        "id": kid,
        "key": kid,
        "open_minute": 5,
        "best_slot": 5,
        "mirror_slot": 5,
        "name": name,
        "label": name,
        "title": title,
        "category": "Oy defteri · $48",
        "panel": "vote_paper",
        "vote_paper": True,
        "featured": False,
        "balance": round(init + pnl, 2),
        "init_bal": init,
        "equity": round(init + pnl, 2),
        "total_pnl": round(pnl, 2),
        "unrealized_pnl": 0.0,
        "wr": wr,
        "history_n": n,
        "wins": wins,
        "open_count": len(cards),
        "cards": cards,
        "regime": rg,
        "regime_label": {"range": "Durgun", "trend": "Trend", "live": "Canlı", "symbest": "Sembol"}.get(rg, rg),
        "started_at_label": "26.08.2026",
        "margin_usd": STAKE,
        "leverage": 1,
        "slots": {s: {"slot": s, "wr": wr, "history_n": n, "wins": wins,
                      "balance": round(init + pnl, 2), "total_pnl": round(pnl, 2),
                      "open_count": len(cards), "best": s == 5} for s in (2, 5, 7)},
        "recent_history": recent if include_history else [],
        "no_home": True,
    }


def list_top_books() -> list[dict]:
    out = []
    for k in ("top1", "top2", "top3", "top4"):
        b = build_top_book(k)
        if b:
            out.append(b)
    return out
