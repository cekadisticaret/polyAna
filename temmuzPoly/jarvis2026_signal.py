"""JARVIS2026 — evrilen fikir + ders.

2 saatte bir Claude kendi işlemlerinden / yol kaydından kural üretir
(`ideas` in `jarvis2026_policy.json`). Saatlik open o kuralları uygular.
Kaynak defter yalnızca follow/fade fikrinde yön verir — tek başına politika değil.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_DIR = Path(__file__).resolve().parent
_TZ = ZoneInfo("Europe/Istanbul")

POLICY_FILE = _DIR / "jarvis2026_policy.json"
PATH_LATEST = _DIR / "hourly_path" / "latest.json"
PATH_DIR = _DIR / "hourly_path"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
COINS = ("BTC", "ETH", "SOL")
DIR_MODES = frozenset({"follow", "fade", "path_reversion", "path_trend"})
# Evrim ask_max'ı 0.36'ya, path eşiğini 12'ye çekip neredeyse hiç açmıyordu.
# Taban/tavan: fikir sıkılaştırabilir ama bu sınırların dışına çıkamaz.
_PATH_FLAT_BPS = 6.0
ASK_MAX_FLOOR = 0.50
PATH_ABS_CEIL = 6.0

_HISTORY_ALIASES = {"melez": "analiz6_v4"}
_EXCLUDE_FOLLOW = frozenset({
    "jarvis2026", "analiz2",
    "b1_01", "b1_02", "b1_04", "b1_05",
    "combo", "combo2",
    "ref01",
})
_PRIMARY_NAMED = (
    "analiz1", "analiz6", "analiz6_v2", "analiz6_v3", "analiz15",
    "melez", "b1_mum", "c101", "c101_v2", "x101", "f16v2", "a2_05_v2",
)
_LABELS = {
    "analiz1": "F16", "analiz6": "A6", "analiz6_v2": "A6V2",
    "analiz6_v3": "A6V3", "analiz15": "A15", "melez": "MELEZ",
    "b1_mum": "B1#03 MUM", "c101": "C1#01", "c101_v2": "C1#01 V2",
    "x101": "X1#01", "f16v2": "F16V2", "a2_05_v2": "A2#05 V2",
}


def now_tr() -> datetime:
    return datetime.now(_TZ)


def norm_symbol(sym: str) -> str:
    s = str(sym or "").upper().replace("/", "").replace("-", "")
    if s in ("BTC", "ETH", "SOL"):
        return f"{s}USDT"
    if s.endswith("USDT"):
        return s
    return s


def coin_of(sym: str) -> str:
    return norm_symbol(sym).replace("USDT", "")


def book_key(name: str) -> str:
    """'A2#14' / 'a2_14' / 'A6V3' → defter anahtarı."""
    s = str(name or "").strip()
    if not s:
        return ""
    low = s.lower().replace(" ", "").replace("-", "_")
    m = re.match(r"^a2#?0*(\d+)$", low.replace("_", ""))
    if m:
        return f"a2_{int(m.group(1)):02d}"
    m = re.match(r"^a1#?0*(\d+)$", low.replace("_", ""))
    if m:
        return f"a1_{int(m.group(1)):02d}"
    m = re.match(r"^f1#?0*(\d+)$", low.replace("_", ""))
    if m:
        return f"f1_{int(m.group(1)):02d}"
    aliases = {
        "a6v3": "analiz6_v3", "analiz6v3": "analiz6_v3",
        "a6v2": "analiz6_v2", "analiz6v2": "analiz6_v2",
        "a6": "analiz6", "f16": "analiz1", "f16v2": "f16v2",
        "melez": "melez", "a15": "analiz15", "c101": "c101",
        "c101v2": "c101_v2", "c1#01v2": "c101_v2", "x101": "x101",
        "b1#03mum": "b1_mum", "b1mum": "b1_mum",
        "a2#05v2": "a2_05_v2", "a205v2": "a2_05_v2",
    }
    if low in aliases:
        return aliases[low]
    if low in follow_keys():
        return low
    return s


def book_label(key: str) -> str:
    if m := re.match(r"^a2_(\d+)$", key or ""):
        return f"A2#{int(m.group(1)):02d}"
    if m := re.match(r"^a1_(\d+)$", key or ""):
        return f"A1#{int(m.group(1)):02d}"
    if m := re.match(r"^f1_(\d+)$", key or ""):
        return f"F1#{int(m.group(1)):02d}"
    return _LABELS.get(key, key or "?")


def follow_keys() -> list[str]:
    keys = list(_PRIMARY_NAMED)
    try:
        from algo_signals_v2 import ALGO_V2_META
        keys.extend(f"a2_{n:02d}" for n, *_ in ALGO_V2_META)
    except Exception:
        keys.extend(f"a2_{i:02d}" for i in range(1, 18))
    try:
        from algo_signals import ALGO_META, SKIP
        keys.extend(f"a1_{n:02d}" for n, _ in ALGO_META if n not in SKIP)
    except Exception:
        pass
    try:
        from f1_signal import F1_META
        keys.extend(f"f1_{n:02d}" for n, *_ in F1_META)
    except Exception:
        keys.extend(f"f1_{i:02d}" for i in range(1, 8))
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        if k in _EXCLUDE_FOLLOW or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def history_path(key: str) -> Path:
    stem = _HISTORY_ALIASES.get(key, key)
    return _DIR / f"poly_trader_{stem}_history.json"


def state_path(key: str) -> Path:
    stem = _HISTORY_ALIASES.get(key, key)
    return _DIR / f"poly_trader_{stem}_state.json"


def load_json(path: Path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if data is not None else default
    except Exception:
        return default


def load_history(key: str) -> list:
    data = load_json(history_path(key), [])
    return data if isinstance(data, list) else []


def load_state(key: str) -> dict:
    data = load_json(state_path(key), {})
    return data if isinstance(data, dict) else {}


def _dir_of(pos: dict) -> str | None:
    raw = (
        pos.get("predicted_dir")
        or pos.get("pm_token_dir")
        or pos.get("algo_signal")
        or ""
    )
    d = str(raw).upper()
    if d in ("UP", "LONG", "BUY"):
        return "UP"
    if d in ("DOWN", "SHORT", "SELL"):
        return "DOWN"
    return None


def source_dir(book: str, symbol: str, hour_tr: int) -> str | None:
    st = load_state(book)
    want = norm_symbol(symbol)
    for pos in st.get("open_positions") or []:
        if int(pos.get("entry_hour_tr") or -1) != int(hour_tr):
            continue
        if norm_symbol(pos.get("symbol") or "") != want:
            continue
        d = _dir_of(pos)
        if d:
            return d
    return None


def _reset_cut(key: str, hist: list) -> list:
    reset = (load_state(key).get("balance_reset_at_tr") or "")
    if not reset:
        return [t for t in hist if t.get("win") is not None]
    return [
        t for t in hist
        if t.get("win") is not None and (t.get("exit_time_tr") or "") >= reset
    ]


def book_coin_stats(key: str, hours: float | None = None) -> dict[str, dict]:
    """Coin → {n, wins, wr, pnl} — sıfırlama sonrası, isteğe bağlı zaman penceresi."""
    hist = _reset_cut(key, load_history(key))
    if hours is not None:
        cut = now_tr().timestamp() - hours * 3600
        kept = []
        for t in hist:
            raw = t.get("exit_time_tr") or ""
            try:
                dt = datetime.fromisoformat(str(raw))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_TZ)
                if dt.timestamp() >= cut:
                    kept.append(t)
            except Exception:
                continue
        hist = kept
    by: dict[str, list] = defaultdict(list)
    for t in hist:
        coin = coin_of(t.get("symbol") or "")
        if coin in COINS:
            by[coin].append(t)
    out = {}
    for coin in COINS:
        rows = by.get(coin) or []
        n = len(rows)
        wins = sum(1 for t in rows if t.get("win"))
        pnl = round(sum(float(t.get("pnl") or 0) for t in rows), 2)
        out[coin] = {
            "n": n,
            "wins": wins,
            "wr": round(100.0 * wins / n, 1) if n else None,
            "pnl": pnl,
        }
    return out


def fallback_mapping(min_trades: int = 5) -> dict[str, dict]:
    """Coin başına en yüksek WR (eşitlikte PnL). Claude yoksa / parse bozulursa."""
    best: dict[str, tuple] = {}
    for key in follow_keys():
        stats = book_coin_stats(key)
        for coin, row in stats.items():
            if (row.get("n") or 0) < min_trades or row.get("wr") is None:
                continue
            score = (float(row["wr"]), float(row["pnl"]), int(row["n"]))
            prev = best.get(coin)
            if prev is None or score > prev[0]:
                best[coin] = (score, key, row)
    sources = {}
    for coin in COINS:
        hit = best.get(coin)
        if not hit:
            continue
        _sc, key, row = hit
        sources[f"{coin}USDT"] = {
            "book": key,
            "why": f"yedek WR {row['wr']}% · n={row['n']} · {row['pnl']:+.1f}$",
        }
    return sources


def empty_policy() -> dict:
    return {
        "updated_at_tr": "",
        "generation": 0,
        "source": "empty",
        "note": "",
        "sources": {},
    }


def load_policy() -> dict:
    data = load_json(POLICY_FILE, None)
    if isinstance(data, dict) and isinstance(data.get("sources"), dict):
        return data
    sources = fallback_mapping()
    pol = {
        "updated_at_tr": now_tr().isoformat(),
        "generation": 0,
        "source": "fallback_wr",
        "note": "ilk politika — WR yedeği",
        "sources": sources,
    }
    save_policy(pol)
    return pol


def save_policy(policy: dict) -> None:
    POLICY_FILE.write_text(
        json.dumps(policy, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _num(v, default=None):
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _minute(v):
    n = _num(v)
    if n is None:
        return None
    i = int(n)
    if i < 0 or i > 59:
        return None
    return i


def current_path(symbol: str) -> dict:
    """Bu saatin yol özeti — referans = 1h açılış."""
    coin = coin_of(symbol)
    data = load_json(PATH_LATEST, {})
    if not isinstance(data, dict):
        data = {}
    row = (data.get("coins") or {}).get(coin) or {}
    if not isinstance(row, dict):
        row = {}
    mins = row.get("minutes") or []
    return {
        "hour_key": data.get("hour_key"),
        "ref": _num(row.get("ref")),
        "last": _num(row.get("last")),
        "bps": _num(row.get("now_vs_ref_bps")),
        "max_up_bps": _num(row.get("max_up_bps"), 0.0) or 0.0,
        "max_dn_bps": _num(row.get("max_dn_bps"), 0.0) or 0.0,
        "n": len(mins) if isinstance(mins, list) else 0,
    }


def path_hour_summaries(limit: int = 12) -> list[dict]:
    files = sorted(PATH_DIR.glob("20*.json"))[-limit:]
    out = []
    for fp in files:
        data = load_json(fp, {})
        coins = data.get("coins") or {}
        rec = {"hour": data.get("hour_key") or fp.stem, "coins": {}}
        for coin in COINS:
            row = coins.get(coin) or {}
            rec["coins"][coin] = {
                "bps": _num(row.get("now_vs_ref_bps")),
                "max_up": _num(row.get("max_up_bps")),
                "max_dn": _num(row.get("max_dn_bps")),
                "winner": row.get("winner"),
            }
        out.append(rec)
    return out


def normalize_idea(raw: dict, idx: int = 0) -> dict | None:
    if not isinstance(raw, dict):
        return None
    sym = norm_symbol(raw.get("symbol") or "")
    if sym not in SYMBOLS:
        return None
    mode = str(raw.get("dir_mode") or raw.get("mode") or "").strip().lower()
    if mode not in DIR_MODES:
        return None
    book = book_key(raw.get("book") or "")
    if mode in ("follow", "fade") and book not in follow_keys():
        return None
    iid = re.sub(r"[^a-zA-Z0-9_-]", "", str(raw.get("id") or f"i{idx + 1}"))[:28] or f"i{idx + 1}"
    ask_max = _num(raw.get("ask_max"))
    if ask_max is not None:
        ask_max = max(float(ask_max), ASK_MAX_FLOOR)
    path_abs = _num(raw.get("path_abs_bps"), _PATH_FLAT_BPS)
    if path_abs is not None:
        path_abs = min(float(path_abs), PATH_ABS_CEIL)
    return {
        "id": iid,
        "symbol": sym,
        "dir_mode": mode,
        "book": book or None,
        "ask_min": _num(raw.get("ask_min")),
        "ask_max": ask_max,
        "path_bps_min": _num(raw.get("path_bps_min")),
        "path_bps_max": _num(raw.get("path_bps_max")),
        "path_abs_bps": path_abs,
        "entry_min": _minute(raw.get("entry_min")),
        "entry_max": _minute(raw.get("entry_max")),
        "why": str(raw.get("why") or "")[:200],
        "lesson": str(raw.get("lesson") or "")[:200],
    }


def policy_ideas(pol: dict | None = None) -> list[dict]:
    pol = pol or load_policy()
    out = []
    for i, raw in enumerate(pol.get("ideas") or []):
        idea = normalize_idea(raw, i)
        if idea:
            out.append(idea)
    return out


def idea_scorecard(hist: list, limit: int = 80) -> list[dict]:
    by: dict[str, list] = defaultdict(list)
    for t in hist[-limit:]:
        iid = str(t.get("jarvis_idea") or "").strip()
        if not iid or t.get("win") is None:
            continue
        by[iid].append(t)
    rows = []
    for iid, rows_t in by.items():
        n = len(rows_t)
        wins = sum(1 for t in rows_t if t.get("win"))
        pnl = round(sum(float(t.get("pnl") or 0) for t in rows_t), 2)
        last = rows_t[-1]
        rows.append({
            "id": iid,
            "n": n,
            "wins": wins,
            "wr": round(100.0 * wins / n, 1) if n else None,
            "pnl": pnl,
            "last_win": bool(last.get("win")),
            "last_pnl": round(float(last.get("pnl") or 0), 2),
            "mode": last.get("jarvis_mode"),
        })
    rows.sort(key=lambda r: r["pnl"])
    return rows


def _path_ok(idea: dict, path: dict) -> tuple[bool, str]:
    bps = path.get("bps")
    lo, hi = idea.get("path_bps_min"), idea.get("path_bps_max")
    if lo is not None:
        if bps is None or bps < lo:
            return False, f"yol {bps} < {lo} bps"
    if hi is not None:
        if bps is None or bps > hi:
            return False, f"yol {bps} > {hi} bps"
    return True, ""


def _dir_from_idea(idea: dict, hour_tr: int, path: dict) -> tuple[str | None, str]:
    mode = idea["dir_mode"]
    book = idea.get("book") or ""
    if mode in ("follow", "fade"):
        d = source_dir(book, idea["symbol"], hour_tr)
        if not d:
            return None, f"{book_label(book)} sessiz"
        if mode == "fade":
            d = "DOWN" if d == "UP" else "UP"
        return d, f"{mode} {book_label(book)}"
    bps = path.get("bps")
    need = float(idea.get("path_abs_bps") or _PATH_FLAT_BPS)
    if bps is None:
        return None, "yol yok"
    if abs(bps) < need:
        return None, f"yol düz ({bps:+.1f} bps)"
    if mode == "path_reversion":
        return ("UP" if bps < 0 else "DOWN"), f"reversion {bps:+.1f}bps"
    return ("DOWN" if bps < 0 else "UP"), f"trend {bps:+.1f}bps"


def _follow_book(pol: dict, sym: str, hour_tr: int) -> dict:
    src = (pol.get("sources") or {}).get(sym) or {}
    book = str(src.get("book") or "").strip()
    if book not in follow_keys():
        return {
            "allow": False,
            "symbol": sym,
            "direction": None,
            "book": book or None,
            "reason": "politika yok",
            "detail": f"{sym} için fikir/motor yok",
        }
    d = source_dir(book, sym, hour_tr)
    lab = book_label(book)
    if not d:
        return {
            "allow": False,
            "symbol": sym,
            "direction": None,
            "book": book,
            "reason": "kaynak sessiz",
            "detail": f"{lab} bu saatte {coin_of(sym)} açmamış",
        }
    return {
        "allow": True,
        "symbol": sym,
        "direction": d,
        "book": book,
        "idea_id": None,
        "dir_mode": "follow",
        "ask_min": None,
        "ask_max": None,
        "lesson": "",
        "reason": "yedek takip",
        "detail": f"{lab} {d} · {src.get('why') or pol.get('note') or ''}".strip(" ·"),
    }


def decide(symbol: str, hour_tr: int, minute: int | None = None) -> dict:
    sym = norm_symbol(symbol)
    pol = load_policy()
    ideas = [x for x in policy_ideas(pol) if x["symbol"] == sym]
    path = current_path(sym)
    rejects = []
    for idea in ideas:
        lo, hi = idea.get("entry_min"), idea.get("entry_max")
        if minute is not None:
            if lo is not None and minute < lo:
                rejects.append(f"{idea['id']}: dk {minute} < :{lo:02d}")
                continue
            if hi is not None and minute > hi:
                rejects.append(f"{idea['id']}: dk {minute} > :{hi:02d}")
                continue
        ok, why_not = _path_ok(idea, path)
        if not ok:
            rejects.append(f"{idea['id']}: {why_not}")
            continue
        d, how = _dir_from_idea(idea, hour_tr, path)
        if not d:
            rejects.append(f"{idea['id']}: {how}")
            continue
        return {
            "allow": True,
            "symbol": sym,
            "direction": d,
            "book": idea.get("book"),
            "idea_id": idea["id"],
            "dir_mode": idea["dir_mode"],
            "ask_min": idea.get("ask_min"),
            "ask_max": idea.get("ask_max"),
            "lesson": idea.get("lesson") or "",
            "path_bps": path.get("bps"),
            "reason": "fikir",
            "detail": (
                f"{idea['id']} {how} {d}"
                + (f" · {idea['why']}" if idea.get("why") else "")
            ).strip(" ·"),
        }
    if ideas:
        return {
            "allow": False,
            "symbol": sym,
            "direction": None,
            "book": ideas[0].get("book"),
            "idea_id": ideas[0]["id"],
            "reason": "fikir kapalı",
            "detail": "; ".join(rejects[:3]) or "hiçbir fikir uymadı",
        }
    return _follow_book(pol, sym, hour_tr)
