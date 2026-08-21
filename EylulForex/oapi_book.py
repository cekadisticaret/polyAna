"""OPEN API sanal defter — CAPITAL kopyası, bağımsız dosyalar. cem02/forex_book import etmez.

Giriş yalnız Destek/Direnç yapısına yakınken açılır: hedef aynı yöndeki
seviye, stop ters seviyenin öte yanı. Ödül/risk oranı tutmuyorsa ya da stop
marjın kaldıramayacağı kadar uzaksa işlem hiç açılmaz.
"""
from __future__ import annotations

import fcntl
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_DIR = Path(__file__).resolve().parent / "data"
_STATE = _DIR / "oapi_state.json"
_HIST = _DIR / "oapi_history.json"
_LOCK = _DIR / "oapi.lock"


def _files(book: str = "oapi") -> tuple[Path, Path, Path]:
    return _STATE, _HIST, _LOCK
_TZ = ZoneInfo("Europe/Istanbul")

INIT_BAL = 300.0
MARGIN = 100.0
LEVERAGE = 500
BYBIT_LEVERAGE = 500  # /forex/cembybit artık Exness Raw — CEM01 ile aynı 500x
BYBIT_HALT_USD = 10.0  # equity bunun altına inerse işlem durur
SYMBOL = "XAUUSD"
VOLUME = 0.10
HIST_MAX = 400
MAX_OPEN = 2       # bir AL + bir SAT aynı anda olabilir

_LEVEL_PAD = 0.35   # hedefe varmadan kapat (seviyeden dönme riski alma)
_STOP_PAD = 0.35    # stop, ters seviyenin öte yanına
MAX_RISK_RATIO = 1.00   # stop mesafesi marjın en fazla %100'ü ($100)
STOPOUT_RATIO = 1.00    # float zarar marjı yerse zorunlu kapanış
MIN_RR = 1.5            # ödül/risk bunun altındaysa açma
LOCK_BE_AT = 0.50       # hedefin yarısı görülünce stop başabaşa
LOCK_TRAIL_AT = 0.75    # hedefin 3/4'ünde kârın yarısı kilit
LOCK_BE_USD = 15.0      # +$15 olunca stop başabaşa
LOCK_TRAIL_USD = 25.0   # +$25 olunca zirve kârın yarısı kilit — +$51'in $22'ye inmesi bir daha olmasın
TP_MARGIN_PCT = 0.35    # giriş marjının %35'i kârda otomatik kapat ($100 → +$35)
COOLDOWN_WIN = 180      # kârlı kapanış sonrası aynı yöne bekleme (sn)
COOLDOWN_LOSS = 600     # Grafik 1 — zararlı kapanış sonrası bekleme (sn)
COOLDOWN_LOSS_A2 = 300  # Algoritma 2 — zarar sonrası 5 dk

# MT5 ECN Raw (IC / Pepperstone tipi). Broker spesifikasyonu gelince burayı değiştir.
# Komisyon: $3.50 / 1.00 lot / taraf → 0.10 lot = $0.35 açılış + $0.35 kapanış.
COMMISSION_PER_LOT_SIDE = 3.50
# Swap: $ / 1.00 lot / gece. Çarşamba ×3, Cmt/Paz yok (hafta Çarşamba'da toplanır).
SWAP_LONG_PER_LOT = -25.00
SWAP_SHORT_PER_LOT = -8.00
SWAP_TRIPLE_WEEKDAY = 2  # 0=Pzt … 2=Çar


def _now_iso() -> str:
    return datetime.now(_TZ).strftime("%Y.%m.%d %H:%M:%S")


def _empty_state() -> dict:
    return {
        "balance": INIT_BAL,
        "init_balance": INIT_BAL,
        "total_pnl": 0.0,
        "last_dir": "NEUTRAL",
        "position": None,
        "positions": [],
        "cooldown": {"buy": 0.0, "sell": 0.0},
        "last_reject": None,
        "seq": 0,
        "halted": False,
        "halt_reason": None,
    }


def _atomic_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _load_state(book: str = "c2") -> dict:
    state, _, _ = _files(book)
    if not state.exists():
        return _empty_state()
    try:
        st = json.loads(state.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_state()
    base = _empty_state()
    for k, v in base.items():
        st.setdefault(k, v)
    if not isinstance(st.get("cooldown"), dict):
        st["cooldown"] = {"buy": 0.0, "sell": 0.0}
    if st.get("position") and not st["positions"]:
        st["positions"] = [st["position"]]
    return st


def _plist(st: dict) -> list:
    rows = st.get("positions")
    if not isinstance(rows, list):
        rows = []
    if not rows and st.get("position"):
        rows = [st["position"]]
    st["positions"] = rows
    st["position"] = rows[0] if rows else None
    return rows


def _load_hist(book: str = "c2") -> list:
    _, hist, _ = _files(book)
    if not hist.exists():
        return []
    try:
        rows = json.loads(hist.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _lev(book: str = "c2", pos: dict | None = None) -> float:
    if pos is not None:
        try:
            lv = float(pos.get("leverage") or 0)
            if lv > 0:
                return lv
        except (TypeError, ValueError):
            pass
    return float(BYBIT_LEVERAGE if book == "bybit" else LEVERAGE)


def _usd(entry: float, dist: float, book: str = "c2", pos: dict | None = None) -> float:
    """Fiyat mesafesini $ karşılığına çevirir."""
    return dist / float(entry) * MARGIN * _lev(book, pos)


def _pnl(side: str, entry: float, exit_px: float, book: str = "c2", pos: dict | None = None) -> float:
    sign = 1.0 if side == "buy" else -1.0
    return sign * _usd(entry, exit_px - entry, book=book, pos=pos)


def _exit_px(side: str, bid: float, ask: float) -> float:
    return bid if side == "buy" else ask


def _open_px(side: str, bid: float, ask: float) -> float:
    return ask if side == "buy" else bid


def _commission_side(book: str = "c2") -> float:
    """Exness Raw / MT5 ECN: $3.50 / 1.00 lot / taraf → 0.10 lot = $0.35."""
    return round(COMMISSION_PER_LOT_SIDE * VOLUME, 2)


def _equity_now(st: dict, bid: float | None, ask: float | None) -> float:
    eq = float(st.get("balance") or 0)
    for pos in _plist(st):
        n = _net_float(pos, bid, ask)
        if n is not None:
            eq += n
    return round(eq, 2)


def _xau_qty(entry: float, book: str = "bybit") -> float:
    if entry <= 0:
        return 0.0
    return round(MARGIN * _lev(book) / float(entry), 3)


def _swap_rate(side: str) -> float:
    return SWAP_LONG_PER_LOT if side == "buy" else SWAP_SHORT_PER_LOT


def _float_pnl(pos: dict, bid: float | None, ask: float | None) -> float | None:
    """MT5 Profit sütunu — yalnız fiyat; komisyon/swap ayrı."""
    if not pos or bid is None or ask is None:
        return None
    return round(_pnl(pos["side"], pos["entry"], _exit_px(pos["side"], bid, ask), pos=pos), 2)


def _net_float(pos: dict, bid: float | None, ask: float | None) -> float | None:
    """Kapanış komisyonu düşülmüş yüzer net (açılış komisyonu ve swap bakiyede)."""
    fp = _float_pnl(pos, bid, ask)
    if fp is None:
        return None
    return round(fp - _commission_side(str(pos.get("book") or "g1")), 2)


# ---------------------------------------------------------------- seviye planı

def _level_price(lv) -> float | None:
    if not lv:
        return None
    px = lv.get("price") if isinstance(lv, dict) else lv
    try:
        return float(px)
    except (TypeError, ValueError):
        return None


def _plan(side: str, entry: float, levels: dict | None, book: str = "c2") -> dict | None:
    """Hedef = aynı yöndeki seviye, stop = ters seviyenin öte yanı."""
    sup = _level_price((levels or {}).get("nearest_support"))
    res = _level_price((levels or {}).get("nearest_resistance"))
    if sup is None or res is None:
        return None
    entry = float(entry)
    if side == "buy":
        if res <= entry or sup >= entry:
            return None
        target, stop = res, round(sup - _STOP_PAD, 2)
        reward = _usd(entry, (res - _LEVEL_PAD) - entry, book=book)
        risk = _usd(entry, entry - stop, book=book)
        kind = "Direnç"
    else:
        if sup >= entry or res <= entry:
            return None
        target, stop = sup, round(res + _STOP_PAD, 2)
        reward = _usd(entry, entry - (sup + _LEVEL_PAD), book=book)
        risk = _usd(entry, stop - entry, book=book)
        kind = "Destek"
    if risk <= 0 or reward <= 0:
        return None
    return {
        "target": round(target, 2),
        "target_kind": kind,
        "stop": stop,
        "risk_usd": round(risk, 2),
        "reward_usd": round(reward, 2),
        "rr": round(reward / risk, 2),
    }


def _plan_reject(plan: dict | None) -> str | None:
    if not plan:
        return "seviye_yok"
    if plan["risk_usd"] > MARGIN * MAX_RISK_RATIO:
        return "stop_uzak"
    if plan["rr"] < MIN_RR:
        return "rr_dusuk"
    return None


def _apply_plan(pos: dict, plan: dict) -> None:
    pos["target"] = plan["target"]
    pos["target_kind"] = plan["target_kind"]
    pos["stop"] = plan["stop"]
    pos["stop_init"] = plan["stop"]
    pos["risk_usd"] = plan["risk_usd"]
    pos["reward_usd"] = plan["reward_usd"]
    pos["rr"] = plan["rr"]
    pos["peak_progress"] = 0.0
    pos["lock_stage"] = 0


# ------------------------------------------------------------------- çıkışlar

def _progress(pos: dict, mark: float) -> float:
    """Girişten hedefe yolun ne kadarı alındı (0..1+)."""
    tgt = pos.get("target")
    if tgt is None:
        return 0.0
    entry, tgt = float(pos["entry"]), float(tgt)
    span = (tgt - entry) if pos["side"] == "buy" else (entry - tgt)
    if span <= 0:
        return 0.0
    got = (mark - entry) if pos["side"] == "buy" else (entry - mark)
    return max(0.0, got / span)


def _px_of_usd(entry: float, usd: float, pos: dict | None = None) -> float:
    return float(usd) / (MARGIN * _lev(pos=pos)) * float(entry)


def _update_lock(pos: dict, mark: float) -> None:
    """Kâr kilidi — hangisi önce gelirse: dolar eşiği veya hedef yüzdesi."""
    if pos.get("stop") is None:
        return
    entry = float(pos["entry"])
    peak_usd = max(float(pos.get("peak_usd") or 0.0), _pnl(pos["side"], entry, mark, pos=pos))
    pos["peak_usd"] = round(peak_usd, 2)
    peak = 0.0
    if pos.get("target") is not None:
        peak = max(float(pos.get("peak_progress") or 0.0), _progress(pos, mark))
        pos["peak_progress"] = round(peak, 3)

    keep_px = None
    stage = 0
    if peak_usd >= LOCK_TRAIL_USD:
        keep_px = _px_of_usd(entry, peak_usd * 0.5, pos=pos)
        stage = 2
    elif peak_usd >= LOCK_BE_USD:
        keep_px = 0.0
        stage = 1
    if pos.get("target") is not None:
        span = (float(pos["target"]) - entry) if pos["side"] == "buy" else (entry - float(pos["target"]))
        if peak >= LOCK_TRAIL_AT:
            alt = span * peak * 0.5
            if keep_px is None or alt > keep_px:
                keep_px, stage = alt, 2
        elif peak >= LOCK_BE_AT and keep_px is None:
            keep_px, stage = 0.0, 1
    if keep_px is None:
        return
    lock = entry + keep_px if pos["side"] == "buy" else entry - keep_px
    stop = float(pos["stop"])
    pos["stop"] = round(max(stop, lock) if pos["side"] == "buy" else min(stop, lock), 2)
    pos["lock_stage"] = max(int(pos.get("lock_stage") or 0), stage)


def _hit_target(pos: dict, mark: float) -> bool:
    tgt = pos.get("target")
    if tgt is None:
        return False
    tgt = float(tgt)
    if pos["side"] == "sell":
        return mark <= tgt + _LEVEL_PAD and mark < float(pos["entry"])
    return mark >= tgt - _LEVEL_PAD and mark > float(pos["entry"])


def _hit_stop(pos: dict, mark: float) -> bool:
    stop = pos.get("stop")
    if stop is None:
        return False
    stop = float(stop)
    return mark <= stop if pos["side"] == "buy" else mark >= stop


def _m5_against(pos: dict, rail: dict | None) -> bool:
    """Yalnız kapanmış M5 mumu — oluşan mumun salınımı pozisyon kapatmasın."""
    m5 = (rail or {}).get("5m") or {}
    d = m5.get("closed_direction") or m5.get("direction")
    if pos["side"] == "sell" and d == "UP":
        return True
    if pos["side"] == "buy" and d == "DOWN":
        return True
    return False


def _accrue_swap(st: dict, pos: dict, book: str = "c2") -> bool:
    """00:00 İST rollover. Çarşamba ×3; Cmt/Paz atlanır. Exness CFD de swap alır."""
    now = datetime.now(_TZ)
    last = pos.get("swap_date")
    if last:
        try:
            last_d = datetime.strptime(str(last)[:10], "%Y-%m-%d").date()
        except ValueError:
            last_d = now.date()
    else:
        try:
            last_d = datetime.strptime(pos["open_time"], "%Y.%m.%d %H:%M:%S").date()
        except (KeyError, ValueError, TypeError):
            last_d = now.date()
    charged = False
    d = last_d + timedelta(days=1)
    while d <= now.date():
        pos["swap_date"] = d.isoformat()
        if d.weekday() < 5:
            nights = 3 if d.weekday() == SWAP_TRIPLE_WEEKDAY else 1
            amt = round(_swap_rate(pos["side"]) * VOLUME * nights, 2)
            pos["swap"] = round(float(pos.get("swap") or 0) + amt, 2)
            st["balance"] = round(float(st["balance"]) + amt, 2)
            st["total_pnl"] = round(float(st["total_pnl"]) + amt, 2)
            charged = True
        d += timedelta(days=1)
    return charged


def _loss_cooldown(book: str = "c2") -> float:
    return COOLDOWN_LOSS_A2 if book == "a2" else COOLDOWN_LOSS


def _close_one(st: dict, hist: list, pos: dict, bid: float, ask: float, reason: str, book: str = "c2") -> dict | None:
    rows = _plist(st)
    if not any(p.get("id") == pos.get("id") for p in rows):
        return None
    exit_px = _exit_px(pos["side"], bid, ask)
    gross = round(_pnl(pos["side"], pos["entry"], exit_px, book=book, pos=pos), 2)
    comm_close = _commission_side(book)
    comm_open = round(float(pos.get("commission") or 0), 2)
    commission = round(comm_open + comm_close, 2)
    swap = round(float(pos.get("swap") or 0), 2)
    net = round(gross - commission + swap, 2)
    # açılış komisyonu ve swap bakiyede; kapanışta yalnız fiyat + kapanış komisyonu
    st["balance"] = round(float(st["balance"]) + gross - comm_close, 2)
    st["total_pnl"] = round(float(st["total_pnl"]) + gross - comm_close, 2)
    hist.append({
        "id": pos["id"],
        "symbol": SYMBOL,
        "side": pos["side"],
        "volume": pos.get("volume") or VOLUME,
        "entry": pos["entry"],
        "exit": round(exit_px, 2),
        "open_time": pos["open_time"],
        "close_time": _now_iso(),
        "gross": gross,
        "commission": commission,
        "commission_open": comm_open,
        "commission_close": comm_close,
        "swap": swap,
        "pnl": net,
        "balance_after": st["balance"],
        "reason": reason,
        "target": pos.get("target"),
        "stop": pos.get("stop"),
        "rr": pos.get("rr"),
        "margin": MARGIN,
        "leverage": pos.get("leverage") or _lev(book),
    })
    del hist[:-HIST_MAX]
    st["positions"] = [p for p in rows if p.get("id") != pos.get("id")]
    st["position"] = st["positions"][0] if st["positions"] else None
    cd = st.setdefault("cooldown", {})
    cd[pos["side"]] = time.time() + (COOLDOWN_WIN if net >= 0 else _loss_cooldown(book))
    return hist[-1]


def _protect(st: dict, hist: list, bid: float, ask: float, rail=None, levels=None, book: str = "c2") -> bool:
    """Sıra: zorunlu kapanış → stop → hedef → M5 tersi."""
    closed = False
    stopout = -MARGIN * STOPOUT_RATIO
    for pos in list(_plist(st)):
        if (pos.get("target") is None or pos.get("stop") is None) and levels:
            plan = _plan(pos["side"], float(pos["entry"]), levels, book=book)
            if plan:
                _apply_plan(pos, plan)
        mark = _exit_px(pos["side"], bid, ask)
        _update_lock(pos, mark)
        if _net_float(pos, bid, ask) is not None and _net_float(pos, bid, ask) <= stopout:
            reason = "stopout"
        elif _hit_stop(pos, mark):
            reason = "lock" if int(pos.get("lock_stage") or 0) else "stop"
        elif _float_pnl(pos, bid, ask) is not None and _float_pnl(pos, bid, ask) >= MARGIN * TP_MARGIN_PCT:
            reason = "tp35"
        elif _hit_target(pos, mark):
            reason = "sr"
        elif _m5_against(pos, rail):
            reason = "m5"
        else:
            continue
        _close_one(st, hist, pos, bid, ask, reason, book=book)
        closed = True
    return closed


# --------------------------------------------------------------------- giriş

def _has_side(st: dict, side: str) -> bool:
    return any(p.get("side") == side for p in _plist(st))


def _cooling(st: dict, side: str) -> float:
    left = float((st.get("cooldown") or {}).get(side) or 0.0) - time.time()
    return max(0.0, left)


def _open(st: dict, side: str, bid: float, ask: float, signal: str, plan: dict, book: str = "c2") -> dict | None:
    rows = _plist(st)
    if book == "bybit" and st.get("halted"):
        return None
    if _has_side(st, side) or len(rows) >= MAX_OPEN:
        return None
    if float(st["balance"]) - MARGIN * len(rows) < MARGIN:
        return None
    st["seq"] = int(st.get("seq") or 0) + 1
    entry = round(_open_px(side, bid, ask), 2)
    pos = {
        "id": f"fx-{st['seq']}-{int(time.time())}",
        "book": book,
        "symbol": SYMBOL,
        "side": side,
        "volume": VOLUME,
        "entry": entry,
        "open_time": _now_iso(),
        "signal": signal,
        "margin": MARGIN,
        "leverage": _lev(book),
        "commission": _commission_side(book),
        "commission_open": _commission_side(book),
        "commission_close": _commission_side(book),
        "swap": 0.0,
        "swap_date": None,
        "fill_src": "exness" if book == "bybit" else "paper",
    }
    _apply_plan(pos, plan)
    comm = pos["commission"]
    st["balance"] = round(float(st["balance"]) - comm, 2)
    st["total_pnl"] = round(float(st["total_pnl"]) - comm, 2)
    rows.append(pos)
    st["positions"] = rows
    st["position"] = rows[0]
    return pos


def apply_signal(
    signal: dict | None,
    bid: float | None,
    ask: float | None,
    rail: dict | None = None,
    levels: dict | None = None,
    book: str = "c2",
) -> dict:
    """UP → AL, DOWN → SAT. Short açıkken long da açılır (en fazla 1+1)."""
    direction = str((signal or {}).get("direction") or "NEUTRAL").upper()
    if book == "bybit":
        try:
            from bybit_xau import ticker
            t = ticker(force=True)
            bid, ask = float(t["bid"]), float(t["ask"])
        except Exception:
            pass
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return snapshot(bid, ask, book=book)

    state_p, hist_p, lock_p = _files(book)
    _DIR.mkdir(parents=True, exist_ok=True)
    with open(lock_p, "a+", encoding="utf-8") as lk:
        fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
        st = _load_state(book)
        hist = _load_hist(book)
        want = "buy" if direction == "UP" else "sell" if direction == "DOWN" else None
        dirty = False
        for pos in _plist(st):
            if _accrue_swap(st, pos, book=book):
                dirty = True
        if _protect(st, hist, bid, ask, rail=rail, levels=levels, book=book):
            dirty = True

        if book == "bybit":
            eq_now = _equity_now(st, bid, ask)
            if st.get("halted") or eq_now < BYBIT_HALT_USD:
                if not st.get("halted"):
                    for pos in list(_plist(st)):
                        _close_one(st, hist, pos, bid, ask, "para_bitti", book=book)
                    st["halted"] = True
                    st["halt_reason"] = "para_bitti"
                    st["halt_at"] = _now_iso()
                    dirty = True
                want = None

        if direction != (st.get("last_dir") or "NEUTRAL"):
            st["last_dir"] = direction
            dirty = True

        if want and not _has_side(st, want):
            wait = _cooling(st, want)
            plan = None if wait else _plan(want, _open_px(want, bid, ask), levels, book=book)
            why = "bekleme" if wait else _plan_reject(plan)
            if why:
                prev = st.get("last_reject") or {}
                if prev.get("reason") != why or prev.get("side") != want:
                    dirty = True
                st["last_reject"] = {
                    "side": want,
                    "reason": why,
                    "wait": int(wait),
                    "rr": (plan or {}).get("rr"),
                    "risk_usd": (plan or {}).get("risk_usd"),
                    "reward_usd": (plan or {}).get("reward_usd"),
                    "at": _now_iso(),
                }
            elif _open(st, want, bid, ask, direction, plan, book=book):
                st["last_reject"] = None
                dirty = True

        if dirty or _plist(st):
            _atomic_write(state_p, st)
            _atomic_write(hist_p, hist)

    return snapshot(bid, ask, book=book)


def snapshot(bid: float | None = None, ask: float | None = None, book: str = "c2") -> dict:
    st = _load_state(book)
    hist = _load_hist(book)
    rows = []
    float_sum = 0.0
    net_sum = 0.0
    for pos in _plist(st):
        fpnl = _float_pnl(pos, bid, ask)
        net = _net_float(pos, bid, ask)
        item = dict(pos)
        item["float_pnl"] = fpnl
        item["float_net"] = net
        item["commission"] = round(float(pos.get("commission") or 0), 2)
        item["swap"] = round(float(pos.get("swap") or 0), 2)
        if bid is not None and ask is not None:
            mark = _exit_px(pos["side"], bid, ask)
            item["mark"] = round(mark, 2)
            item["progress"] = round(min(1.0, _progress(pos, mark)) * 100, 1)
        rows.append(item)
        if fpnl is not None:
            float_sum += fpnl
        if net is not None:
            net_sum += net
    out = {
        "ok": True,
        "book": book,
        "symbol": SYMBOL,
        "balance": round(float(st["balance"]), 2),
        "equity": round(float(st["balance"]) + net_sum, 2) if rows else round(float(st["balance"]), 2),
        "init_balance": INIT_BAL,
        "total_pnl": round(float(st["total_pnl"]), 2),
        "float_pnl": round(float_sum, 2) if rows else None,
        "open_count": len(rows),
        "trade_count": int(st.get("seq") or 0) or (len(hist) + len(rows)),
        "position": rows[0] if rows else None,
        "positions": rows,
        "history": list(reversed(hist[-200:])),
        "margin": MARGIN,
        "leverage": _lev(book),
        "last_dir": st.get("last_dir"),
        "last_reject": st.get("last_reject"),
        "halted": bool(st.get("halted")),
        "halt_reason": st.get("halt_reason"),
        "costs": {
            "commission_side": _commission_side(book),
            "commission_open": _commission_side(book),
            "commission_close": _commission_side(book),
            "commission_rt": round(_commission_side(book) * 2, 2),
            "swap_long": round(SWAP_LONG_PER_LOT * VOLUME, 2),
            "swap_short": round(SWAP_SHORT_PER_LOT * VOLUME, 2),
            "volume": VOLUME,
            "notional": MARGIN * _lev(book),
            "fee_model": "exness_raw" if book == "bybit" else "mt5",
        },
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        from desk_meta import attach
        attach(out, "oapi", hist=hist, state_path=_files(book)[0], init=out.get("init_balance"))
    except Exception:
        pass
    return out


def reset_book(book: str) -> dict:
    """Yalnız verilen defteri $300'e çeker. CEM01 (g1) için çağırma."""
    if book not in ("bybit", "a2"):
        raise ValueError("reset_book: g1 yasak")
    state_p, hist_p, lock_p = _files(book)
    _DIR.mkdir(parents=True, exist_ok=True)
    with open(lock_p, "a+", encoding="utf-8") as lk:
        fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
        st = _empty_state()
        _atomic_write(state_p, st)
        _atomic_write(hist_p, [])
    return snapshot(book=book)
