"""Algoritma-islemler :05 ortak oy — saatlik kayıt + Binance 1h sonuç.

Emir açmaz. Cron: `run` (:08) mevcut saati kaydeder, bitmiş saatleri doldurur.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_TZ = ZoneInfo("Europe/Istanbul")
LOG_FILE = os.path.join(_DIR, "algo_consensus.json")
COINS = ("BTC", "ETH", "SOL")
KEEP_DAYS = 90


def _now() -> datetime:
    return datetime.now(_TZ)


def current_slot(now: datetime | None = None) -> tuple[str, int, str]:
    """(id, hour, date_iso) — :05 öncesi önceki saat."""
    now = now or _now()
    if now.minute >= 5:
        slot = now.replace(minute=5, second=0, microsecond=0)
    else:
        slot = (now - timedelta(hours=1)).replace(minute=5, second=0, microsecond=0)
    return f"{slot.date().isoformat()}T{slot.hour:02d}", slot.hour, slot.date().isoformat()


def _atomic_write(path: str, data: dict) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".consensus.", dir=d)
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


def load_store() -> dict:
    if not os.path.exists(LOG_FILE):
        return {"hours": [], "updated_at_tr": None}
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"hours": [], "updated_at_tr": None}
    if isinstance(data, list):
        return {"hours": data, "updated_at_tr": None}
    data.setdefault("hours", [])
    return data


def _prune(hours: list) -> list:
    cutoff = (_now() - timedelta(days=KEEP_DAYS)).date().isoformat()
    return [h for h in hours if str(h.get("slot_date") or "") >= cutoff]


def _lock_run(fn):
    os.makedirs(_DIR, exist_ok=True)
    lock_path = LOG_FILE + ".lock"
    with open(lock_path, "a+", encoding="utf-8") as lk:
        fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(lk.fileno(), fcntl.LOCK_UN)


def _coins_payload(votes: dict) -> list[dict]:
    out = []
    for c in votes.get("coins") or []:
        out.append({
            "symbol": c.get("symbol"),
            "winner": c.get("winner"),
            "label": c.get("label"),
            "up": int(c.get("up") or 0),
            "down": int(c.get("down") or 0),
            "n": int(c.get("n") or 0),
            "votes": int(c.get("votes") or 0),
            "actual": c.get("actual"),
            "win": c.get("win"),
        })
    return out


def record_votes(votes: dict, now: datetime | None = None) -> dict:
    """Bu saatin :05 oyunu kaydet. Sonuçlu saate dokunma."""
    if not votes or not votes.get("ok"):
        return load_store()
    now = now or _now()
    sid, hour, day = current_slot(now)
    if now.minute < 5:
        return load_store()

    def _write():
        store = load_store()
        hours = list(store.get("hours") or [])
        by_id = {h.get("id"): h for h in hours if h.get("id")}
        prev = by_id.get(sid) or {}
        if any(c.get("actual") in ("UP", "DOWN") for c in (prev.get("coins") or [])):
            return store
        coins = _coins_payload(votes)
        if not any(int(c.get("n") or 0) > 0 for c in coins):
            return store
        row = {
            "id": sid,
            "slot_date": day,
            "slot_hour": hour,
            "slot_open_tr": f"{hour:02d}:05",
            "books": int(votes.get("books") or 0),
            "saved_at_tr": now.isoformat(timespec="seconds"),
            "coins": coins,
        }
        same = (
            prev.get("id") == sid
            and [(c.get("symbol"), c.get("winner"), c.get("up"), c.get("down"))
                 for c in (prev.get("coins") or [])]
            == [(c.get("symbol"), c.get("winner"), c.get("up"), c.get("down"))
                for c in coins]
        )
        if same:
            return store
        by_id[sid] = row
        hours = _prune(sorted(by_id.values(), key=lambda h: h.get("id") or ""))
        store = {"hours": hours, "updated_at_tr": now.isoformat(timespec="seconds")}
        _atomic_write(LOG_FILE, store)
        return store

    return _lock_run(_write)


def _slot_ended(row: dict, now: datetime) -> bool:
    try:
        day = datetime.fromisoformat(str(row.get("slot_date"))).date()
        hour = int(row.get("slot_hour"))
    except Exception:
        return False
    end = datetime(day.year, day.month, day.day, hour, 0, tzinfo=_TZ) + timedelta(hours=1)
    return now >= end


def _actual_dir(symbol: str, slot_date: str, slot_hour: int) -> str | None:
    sys.path.insert(0, _DIR)
    from pm_trader_helpers import pm_sanal_slot_candle
    entry = f"{slot_date}T{int(slot_hour):02d}:05:00+03:00"
    candle = pm_sanal_slot_candle(f"{symbol}USDT", entry)
    if not candle:
        return None
    o, c = candle
    if c > o:
        return "UP"
    if c < o:
        return "DOWN"
    return "FLAT"


def resolve_pending(now: datetime | None = None) -> dict:
    now = now or _now()

    def _write():
        store = load_store()
        hours = list(store.get("hours") or [])
        changed = False
        for row in hours:
            if not _slot_ended(row, now):
                continue
            coins = list(row.get("coins") or [])
            for c in coins:
                if c.get("actual") in ("UP", "DOWN", "FLAT"):
                    continue
                winner = c.get("winner")
                if winner not in ("UP", "DOWN"):
                    c["actual"] = None
                    c["win"] = None
                    continue
                actual = _actual_dir(str(c.get("symbol") or ""), str(row.get("slot_date")), int(row.get("slot_hour")))
                if actual is None:
                    continue
                c["actual"] = actual
                c["win"] = actual == winner if actual in ("UP", "DOWN") else False
                changed = True
            row["coins"] = coins
        if changed:
            store = {
                "hours": _prune(hours),
                "updated_at_tr": now.isoformat(timespec="seconds"),
            }
            _atomic_write(LOG_FILE, store)
        return store

    return _lock_run(_write)


def stats_from_store(store: dict | None = None) -> dict:
    store = store if store is not None else load_store()
    scored = wins = 0
    per = {s: {"scored": 0, "wins": 0} for s in COINS}
    for row in store.get("hours") or []:
        for c in row.get("coins") or []:
            if c.get("winner") not in ("UP", "DOWN"):
                continue
            if c.get("actual") not in ("UP", "DOWN"):
                continue
            scored += 1
            w = bool(c.get("win"))
            if w:
                wins += 1
            sym = str(c.get("symbol") or "")
            if sym in per:
                per[sym]["scored"] += 1
                if w:
                    per[sym]["wins"] += 1
    wr = round(100.0 * wins / scored, 1) if scored else None
    return {
        "ok": True,
        "scored": scored,
        "wins": wins,
        "wr": wr,
        "label": (f"%{wr:g} başarılı".replace(".", ",") if wr is not None else "henüz sonuç yok"),
        "detail": f"{wins}/{scored} saat-coin" if scored else "kapanan saat bekleniyor",
        "coins": {
            s: {
                "scored": per[s]["scored"],
                "wins": per[s]["wins"],
                "wr": round(100.0 * per[s]["wins"] / per[s]["scored"], 1) if per[s]["scored"] else None,
            }
            for s in COINS
        },
        "hours": len(store.get("hours") or []),
    }


def attach_to_votes(votes: dict, *, persist: bool = False) -> dict:
    """Liste/API — başarı ekle. persist=True yalnız cron: kaydet + Binance sonuç."""
    votes = dict(votes or {})
    try:
        if persist:
            record_votes(votes)
            store = resolve_pending()
        else:
            store = load_store()
        votes["stats"] = stats_from_store(store)
    except Exception as e:
        votes["stats"] = {"ok": False, "error": str(e), "scored": 0, "wr": None,
                          "label": "kayıt yok", "detail": ""}
    return votes


def tally_from_t05_states() -> dict:
    """Cron — dashboard'suz :05 state oyları."""
    tallies = {c: {"up": 0, "down": 0} for c in COINS}
    n_books = 0
    for name in os.listdir(_DIR):
        if not name.endswith("_t05_state.json"):
            continue
        path = os.path.join(_DIR, name)
        try:
            state = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        n_books += 1
        seen: set[str] = set()
        for p in state.get("open_positions") or []:
            name_c = str(p.get("symbol") or "").replace("USDT", "").upper()
            if name_c not in tallies or name_c in seen:
                continue
            seen.add(name_c)
            side = str(p.get("predicted_dir") or p.get("pm_token_dir") or "").upper()
            up = side in ("UP", "LONG")
            if up:
                tallies[name_c]["up"] += 1
            else:
                tallies[name_c]["down"] += 1
    coins = []
    for sym in COINS:
        up, down = tallies[sym]["up"], tallies[sym]["down"]
        n = up + down
        if n == 0:
            winner, label, votes = None, "oy yok", 0
        elif up > down:
            winner, label, votes = "UP", "yükselir", up
        elif down > up:
            winner, label, votes = "DOWN", "düşer", down
        else:
            winner, label, votes = "TIE", "berabere", up
        coins.append({
            "symbol": sym, "up": up, "down": down, "n": n,
            "winner": winner, "label": label, "votes": votes,
        })
    sid, hour, _day = current_slot()
    return {
        "ok": True,
        "slot": 5,
        "slot_open_tr": f"{hour:02d}:05",
        "books": n_books,
        "coins": coins,
        "id": sid,
    }


def run() -> dict:
    votes = tally_from_t05_states()
    record_votes(votes)
    store = resolve_pending()
    paper = {}
    try:
        root = os.path.dirname(_DIR)
        if root not in sys.path:
            sys.path.insert(0, root)
        from web.poly_dashboard import _build_a2_poly_books
        from vote_paper import run_from_votes
        data = _build_a2_poly_books()
        paper = run_from_votes(data.get("votes") or {})
    except Exception as e:
        paper = {"ok": False, "error": str(e)}
    return {"ok": True, "votes": votes, "stats": stats_from_store(store), "paper": paper}


if __name__ == "__main__":
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "run").strip().lower()
    if cmd == "stats":
        print(json.dumps(stats_from_store(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(run(), ensure_ascii=False, indent=2))
