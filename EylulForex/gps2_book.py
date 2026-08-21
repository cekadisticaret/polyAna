"""GPSUSDT_2 sanal defter — Isolated MARKET $50 × 15x, kasa $160.

Canlı gpsusdt_* dosyalarına dokunmaz. Emir atmaz.
Sinyal / kapı / plan canlı GPS ile aynı (kopya).
Dolum: Binance derinlik VWAP (market_fill). Funding kâğıt işlenir.
"""
from __future__ import annotations

import fcntl
import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_DIR = Path(__file__).resolve().parent / "data"
_STATE = _DIR / "forex_gps2_state.json"
_HIST = _DIR / "forex_gps2_history.json"
_LOCK = _DIR / "forex_gps2.lock"
_PX = 6  # GPSUSDT tick — altın 2 hane değil


def _files(book: str = "gps2") -> tuple[Path, Path, Path]:
    return _STATE, _HIST, _LOCK
_TZ = ZoneInfo("Europe/Istanbul")

INIT_BAL = 160.0
MARGIN = 50.0
LEVERAGE = 15          # Binance USDT-M Isolated
SYMBOL = "GPSUSDT"
VOLUME = 0.10
HIST_MAX = 400
MAX_OPEN = 1           # tek pozisyon — forex gibi anında tersine dönmez
TAKER_FEE = 0.0005     # Binance taker — notional × 0.05%
QTY_STEP = 1.0
MMR = 0.010            # isolated bakım marjı (~%1)
MARGIN_TYPE = "ISOLATED"

# CEM01'de $0.35 pad ≈ 3300$'lık altında %0.0106 — hedef vuruşu için küçük pay
_PAD_FRAC = 0.35 / 3300.0
_LEVEL_PAD = 0.35
_STOP_PAD = 0.35
MAX_RISK_RATIO = 1.00
STOPOUT_RATIO = 1.00
MIN_RR = 1.5
STOP_ATR = 2.0
STOP_PCT_CAP = 0.05
STOP_PCT_FLOOR = 0.008
LOCK_BE_AT = 0.50       # hedefin yarısı görülünce stop başabaşa
LOCK_TRAIL_AT = 0.75    # hedefin 3/4'ünde kârın yarısı kilit
LOCK_BE_USD = 15.0      # +$15 olunca stop başabaşa
LOCK_TRAIL_USD = 25.0   # +$25 olunca zirve kârın yarısı kilit — +$51'in $22'ye inmesi bir daha olmasın
TP_MARGIN_PCT = 0.35    # giriş marjının %35'i kârda otomatik kapat ($50 → +$17.5)
COOLDOWN_WIN = 900      # kârlı kapanış sonrası 15 dk
COOLDOWN_LOSS = 1800    # zararlı kapanış sonrası 30 dk
COOLDOWN_LOSS_A2 = 300  # Algoritma 2 — zarar sonrası 5 dk

# MT5 ECN Raw (IC / Pepperstone tipi). Broker spesifikasyonu gelince burayı değiştir.
# Komisyon: $3.50 / 1.00 lot / taraf → 0.10 lot = $0.35 açılış + $0.35 kapanış.
COMMISSION_PER_LOT_SIDE = 3.50
# Swap: $ / 1.00 lot / gece. Çarşamba ×3, Cmt/Paz yok (hafta Çarşamba'da toplanır).
SWAP_LONG_PER_LOT = -25.00
SWAP_SHORT_PER_LOT = -8.00
SWAP_TRIPLE_WEEKDAY = 2  # 0=Pzt … 2=Çar


def _r(px) -> float:
    try:
        from gps2_binance import round_px
        return round_px(float(px))
    except Exception:
        return round(float(px), _PX)


def _pad(entry: float) -> float:
    return max(_r(float(entry) * _PAD_FRAC), 10 ** (-_PX))


def _liq_price(side: str, entry: float, lev: float = LEVERAGE) -> float:
    """Isolated tasfiye — Binance sade formül (MMR dahil)."""
    entry = float(entry)
    imr = 1.0 / float(lev)
    if side == "buy":
        return _r(entry * (1.0 - imr + MMR))
    return _r(entry * (1.0 + imr - MMR))


def _binance_qty(entry: float) -> float:
    try:
        from gps2_binance import size_from_margin
        return float(size_from_margin(MARGIN, LEVERAGE, entry))
    except Exception:
        if entry <= 0:
            return 0.0
        raw = MARGIN * LEVERAGE / float(entry)
        step = QTY_STEP
        qty = math.floor(raw / step) * step
        return round(qty, 3)


def _atr5() -> float:
    try:
        from gps2_data import gps_klines
        rows = gps_klines("5m", 20)
    except Exception:
        return 0.0
    if len(rows) < 8:
        return 0.0
    n = min(14, len(rows) - 1)
    s = 0.0
    for i in range(-n, 0):
        s += float(rows[i]["high"]) - float(rows[i]["low"])
    return s / n


def _binance_plan(side: str, entry: float, atr: float | None = None) -> dict:
    """Binance market — ATR/% stop, RR 1.5 hedef. Altın S/R yok."""
    entry = float(entry)
    atr = float(atr or 0)
    stop_dist = atr * STOP_ATR if atr > 0 else entry * 0.02
    stop_dist = min(max(stop_dist, entry * STOP_PCT_FLOOR), entry * STOP_PCT_CAP)
    target_dist = stop_dist * MIN_RR
    if side == "buy":
        stop, target, kind = entry - stop_dist, entry + target_dist, "ATR"
    else:
        stop, target, kind = entry + stop_dist, entry - target_dist, "ATR"
    risk = _usd(entry, stop_dist)
    reward = _usd(entry, target_dist)
    return {
        "target": _r(target),
        "target_kind": kind,
        "stop": _r(stop),
        "risk_usd": round(risk, 2),
        "reward_usd": round(reward, 2),
        "rr": round(reward / risk, 2) if risk else 0,
        "fill": "binance_usdm",
    }


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


def _load_state(book: str = "gps2") -> dict:
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


def _load_hist(book: str = "gps2") -> list:
    _, hist, _ = _files(book)
    if not hist.exists():
        return []
    try:
        rows = json.loads(hist.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _lev(book: str = "gps2", pos: dict | None = None) -> float:
    if pos is not None:
        try:
            lv = float(pos.get("leverage") or 0)
            if lv > 0:
                return lv
        except (TypeError, ValueError):
            pass
    return float(LEVERAGE)


def _qty(pos: dict | None) -> float:
    if not pos:
        return 0.0
    try:
        return float(pos.get("qty") or pos.get("volume") or 0)
    except (TypeError, ValueError):
        return 0.0


def _taker() -> float:
    try:
        from gps2_binance import taker_rate
        return float(taker_rate())
    except Exception:
        return float(TAKER_FEE)


def _fee(qty: float, price: float, rate: float | None = None) -> float:
    r = _taker() if rate is None else float(rate)
    return round(abs(float(qty) * float(price)) * r, 6)


def _usd(entry: float, dist: float, book: str = "gps2", pos: dict | None = None) -> float:
    """Fiyat mesafesini $ karşılığına çevirir — Binance: qty × dist."""
    q = _qty(pos)
    if q > 0:
        return abs(q * float(dist))
    return dist / float(entry) * MARGIN * _lev(book, pos)


def _pnl(side: str, entry: float, exit_px: float, book: str = "gps2", pos: dict | None = None) -> float:
    q = _qty(pos)
    sign = 1.0 if side == "buy" else -1.0
    if q > 0:
        return sign * q * (float(exit_px) - float(entry))
    return sign * _usd(entry, exit_px - entry, book=book, pos=pos)


def _exit_px(side: str, bid: float, ask: float) -> float:
    return bid if side == "buy" else ask


def _open_px(side: str, bid: float, ask: float) -> float:
    return ask if side == "buy" else bid


def _notional(pos: dict | None = None) -> float:
    if pos and pos.get("notional"):
        return float(pos["notional"])
    return MARGIN * LEVERAGE


def _commission_side(book: str = "gps2", pos: dict | None = None, *, exit_px: float | None = None) -> float:
    """Taker — kapanışta çıkış notional, açıkken kayıtlı açılış ücreti."""
    if exit_px is not None and pos is not None:
        return _fee(_qty(pos), exit_px, pos.get("taker_rate"))
    if pos and pos.get("commission_open") is not None:
        try:
            return round(float(pos["commission_open"]), 6)
        except (TypeError, ValueError):
            pass
    q = _qty(pos)
    px = float(pos.get("entry") or 0) if pos else 0
    if q > 0 and px > 0:
        return _fee(q, px)
    return round(_notional(pos) * _taker(), 6)


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
    """Kapanış komisyonu düşülmüş yüzer net (açılış komisyonu ve funding bakiyede)."""
    fp = _float_pnl(pos, bid, ask)
    if fp is None:
        return None
    exit_px = _exit_px(pos["side"], bid, ask)
    return round(fp - _commission_side("gps", pos, exit_px=exit_px), 6)


# ---------------------------------------------------------------- seviye planı

def _level_price(lv) -> float | None:
    if not lv:
        return None
    px = lv.get("price") if isinstance(lv, dict) else lv
    try:
        return float(px)
    except (TypeError, ValueError):
        return None


def _plan(side: str, entry: float, levels: dict | None, book: str = "gps2") -> dict | None:
    """Hedef = aynı yöndeki seviye, stop = ters seviyenin öte yanı."""
    sup = _level_price((levels or {}).get("nearest_support"))
    res = _level_price((levels or {}).get("nearest_resistance"))
    if sup is None or res is None:
        return None
    entry = float(entry)
    pad = _pad(entry)
    if side == "buy":
        if res <= entry or sup >= entry:
            return None
        target, stop = res, _r(sup - pad)
        reward = _usd(entry, (res - pad) - entry, book=book)
        risk = _usd(entry, entry - stop, book=book)
        kind = "Direnç"
    else:
        if sup >= entry or res <= entry:
            return None
        target, stop = sup, _r(res + pad)
        reward = _usd(entry, entry - (sup + pad), book=book)
        risk = _usd(entry, stop - entry, book=book)
        kind = "Destek"
    if risk <= 0 or reward <= 0:
        return None
    return {
        "target": _r(target),
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
    pos["stop"] = _r(max(stop, lock) if pos["side"] == "buy" else min(stop, lock))
    pos["lock_stage"] = max(int(pos.get("lock_stage") or 0), stage)


def _hit_target(pos: dict, mark: float) -> bool:
    tgt = pos.get("target")
    if tgt is None:
        return False
    tgt = float(tgt)
    pad = _pad(float(pos["entry"]))
    if pos["side"] == "sell":
        return mark <= tgt + pad and mark < float(pos["entry"])
    return mark >= tgt - pad and mark > float(pos["entry"])


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


def _accrue_swap(st: dict, pos: dict, book: str = "gps2") -> bool:
    """Binance funding — açık pozisyona geçmiş settlement'ları işle."""
    try:
        from gps2_binance import funding_events
        events = funding_events(12)
    except Exception:
        return False
    opened = pos.get("open_ms")
    try:
        opened = int(opened or 0)
    except (TypeError, ValueError):
        opened = 0
    if opened <= 0:
        # iso → ms kabaca
        opened = int(time.time() * 1000) - 60_000
    paid_until = int(pos.get("funded_until") or 0)
    q = _qty(pos)
    if q <= 0:
        return False
    signed = q if pos.get("side") == "buy" else -q
    dirty = False
    now_ms = int(time.time() * 1000)
    for ev in events:
        ts = int(ev.get("time") or 0)
        if ts <= opened or ts <= paid_until or ts > now_ms:
            continue
        mark = float(ev.get("mark") or 0) or float(pos.get("entry") or 0)
        rate = float(ev.get("rate") or 0)
        pay = round(signed * mark * rate, 6)  # + = bakiyeden çıkar (long, pozitif funding)
        st["balance"] = round(float(st["balance"]) - pay, 6)
        st["total_pnl"] = round(float(st["total_pnl"]) - pay, 6)
        pos["swap"] = round(float(pos.get("swap") or 0) - pay, 6)
        pos["funded_until"] = ts
        pos["funding_last"] = {"time": ts, "rate": rate, "pay": pay}
        dirty = True
    return dirty


def _loss_cooldown(book: str = "gps2") -> float:
    return COOLDOWN_LOSS


def _close_fill_px(pos: dict, bid: float, ask: float) -> float:
    """Kâğıt artık — long kapanışı bid merdiveni, short ask merdiveni."""
    try:
        from gps2_binance import market_fill
        close_side = "sell" if pos.get("side") == "buy" else "buy"
        fill = market_fill(close_side, _qty(pos))
        if fill.get("ok") and fill.get("price"):
            return float(fill["price"])
    except Exception:
        pass
    return _exit_px(pos["side"], bid, ask)


def _close_one(
    st: dict,
    hist: list,
    pos: dict,
    bid: float,
    ask: float,
    reason: str,
    book: str = "gps2",
    *,
    skip_exchange: bool = False,
) -> dict | None:
    rows = _plist(st)
    if not any(p.get("id") == pos.get("id") for p in rows):
        return None
    exit_px = _close_fill_px(pos, bid, ask)
    comm_close = _commission_side(book, pos, exit_px=exit_px)
    fill_src = "binance_usdm_vwap"
    close_oid = None
    gross = round(_pnl(pos["side"], pos["entry"], exit_px, book=book, pos=pos), 6)
    comm_open = round(float(pos.get("commission_open") or pos.get("commission") or 0), 6)
    commission = round(comm_open + comm_close, 6)
    swap = round(float(pos.get("swap") or 0), 6)
    net = round(gross - commission + swap, 6)
    st["balance"] = round(float(st["balance"]) + gross - comm_close, 6)
    st["total_pnl"] = round(float(st["total_pnl"]) + gross - comm_close, 6)
    hist.append({
        "id": pos["id"],
        "symbol": SYMBOL,
        "side": pos["side"],
        "volume": pos.get("volume") or VOLUME,
        "entry": pos["entry"],
        "exit": _r(exit_px),
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
        "margin": pos.get("margin") or MARGIN,
        "leverage": pos.get("leverage") or _lev(book),
        "qty": _qty(pos),
        "fill_src": fill_src,
        "venue": "binance_usdm",
        "taker_rate": pos.get("taker_rate") or _taker(),
        "order_id": pos.get("order_id"),
        "close_order_id": close_oid,
    })
    del hist[:-HIST_MAX]
    st["positions"] = [p for p in rows if p.get("id") != pos.get("id")]
    st["position"] = st["positions"][0] if st["positions"] else None
    cd = st.setdefault("cooldown", {})
    cd[pos["side"]] = time.time() + (COOLDOWN_WIN if net >= 0 else _loss_cooldown(book))
    return hist[-1]


def _protect(st: dict, hist: list, bid: float, ask: float, rail=None, levels=None, book: str = "gps2", mark: float | None = None) -> bool:
    """Tetik: mark (Binance isolated). Dolum: MARKET VWAP."""
    closed = False
    stopout = -MARGIN * STOPOUT_RATIO
    for pos in list(_plist(st)):
        if (pos.get("target") is None or pos.get("stop") is None) and levels:
            plan = _plan(pos["side"], float(pos["entry"]), levels, book=book)
            if plan:
                _apply_plan(pos, plan)
        trig = float(mark) if mark else _exit_px(pos["side"], bid, ask)
        _update_lock(pos, trig)
        if _net_float(pos, bid, ask) is not None and _net_float(pos, bid, ask) <= stopout:
            reason = "stopout"
        elif pos.get("liq_price") is not None and (
            (pos["side"] == "buy" and trig <= float(pos["liq_price"]))
            or (pos["side"] == "sell" and trig >= float(pos["liq_price"]))
        ):
            reason = "liq"
        elif _hit_stop(pos, trig):
            reason = "lock" if int(pos.get("lock_stage") or 0) else "stop"
        elif _hit_target(pos, trig):
            reason = "tp"
        else:
            continue
        if _close_one(st, hist, pos, bid, ask, reason, book=book):
            closed = True
    return closed


# --------------------------------------------------------------------- giriş

def _has_side(st: dict, side: str) -> bool:
    return any(p.get("side") == side for p in _plist(st))


def _cooling(st: dict, side: str) -> float:
    left = float((st.get("cooldown") or {}).get(side) or 0.0) - time.time()
    return max(0.0, left)


def _open(st: dict, side: str, bid: float, ask: float, signal: str, plan: dict, book: str = "gps2") -> dict | None:
    rows = _plist(st)
    if _has_side(st, side) or len(rows) >= MAX_OPEN:
        return None
    if float(st["balance"]) - MARGIN * len(rows) < MARGIN:
        return None
    hint = _open_px(side, bid, ask)
    qty = _binance_qty(hint)
    if qty <= 0:
        st["last_reject"] = {"side": side, "reason": "qty_min", "at": _now_iso()}
        return None
    try:
        from gps2_binance import market_fill
        fill = market_fill("buy" if side == "buy" else "sell", qty)
    except Exception as e:
        st["last_reject"] = {"side": side, "reason": "fill_err", "detail": str(e)[:80], "at": _now_iso()}
        return None
    if not fill.get("ok"):
        st["last_reject"] = {"side": side, "reason": fill.get("error") or "fill_fail", "at": _now_iso()}
        return None
    entry = float(fill["price"])
    qty = float(fill["qty"])
    notional = float(fill["notional"])
    rate = _taker()
    fee = _fee(qty, entry, rate)
    st["seq"] = int(st.get("seq") or 0) + 1
    pos = {
        "id": f"gps2-{st['seq']}-{int(time.time())}",
        "book": book,
        "symbol": SYMBOL,
        "side": side,
        "volume": qty,
        "qty": qty,
        "entry": entry,
        "open_time": _now_iso(),
        "open_ms": int(time.time() * 1000),
        "signal": signal,
        "margin": MARGIN,
        "leverage": LEVERAGE,
        "notional": notional,
        "commission": fee,
        "commission_open": fee,
        "taker_rate": rate,
        "swap": 0.0,
        "funded_until": 0,
        "fill_src": "binance_usdm_vwap",
        "venue": "binance_usdm",
        "margin_type": MARGIN_TYPE,
        "order_type": "MARKET",
        "order_status": "FILLED",
        "reduce_only": False,
        "fill_levels": fill.get("levels"),
        "liq_price": _liq_price(side, entry),
        "order_id": f"GPS2-{st['seq']}-{int(time.time())}",
        "live": False,
    }
    _apply_plan(pos, plan)
    print(
        f"[GPSUSDT_2] PAPER {MARGIN_TYPE} MARKET {side.upper()} qty={qty} @{entry} "
        f"margin=${MARGIN:.0f} lev={LEVERAGE}x notional=${notional:.2f} "
        f"taker ${fee:.4f} ({rate*100:.4f}%)",
        flush=True,
    )
    st["balance"] = round(float(st["balance"]) - fee, 6)
    st["total_pnl"] = round(float(st["total_pnl"]) - fee, 6)
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
    book: str = "gps2",
) -> dict:
    """UP → AL, DOWN → SAT. Tek Isolated pozisyon."""
    direction = str((signal or {}).get("direction") or "NEUTRAL").upper()
    book = "gps2"
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return snapshot(bid, ask, book=book)

    _mark = None
    try:
        from gps2_binance import premium
        _mark = float(premium().get("mark") or 0) or None
    except Exception:
        _mark = None

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
        if _protect(st, hist, bid, ask, rail=rail, levels=levels, book=book, mark=_mark):
            dirty = True

        if direction != (st.get("last_dir") or "NEUTRAL"):
            st["last_dir"] = direction
            dirty = True

        if want and not _plist(st) and bool((signal or {}).get("is_stable")):
            wait = _cooling(st, want)
            plan = None if wait else _binance_plan(want, _open_px(want, bid, ask), _atr5())
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


def snapshot(bid: float | None = None, ask: float | None = None, book: str = "gps2") -> dict:
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
            item["mark"] = _r(mark)
            item["progress"] = round(min(1.0, _progress(pos, mark)) * 100, 1)
            mg = float(pos.get("margin") or MARGIN)
            item["roe"] = round((fpnl or 0) / mg * 100.0, 2) if mg else None
            item["liq_price"] = pos.get("liq_price") or _liq_price(pos["side"], pos["entry"], _lev(pos=pos))
            item["margin_type"] = pos.get("margin_type") or MARGIN_TYPE
            item["order_status"] = pos.get("order_status") or "FILLED"
        rows.append(item)
        if fpnl is not None:
            float_sum += fpnl
        if net is not None:
            net_sum += net
    out = {
        "ok": True,
        "book": "gps2",
        "symbol": SYMBOL,
        "dec": _PX,
        "balance": round(float(st["balance"]), 2),
        "wallet": round(float(st["balance"]), 2),
        "used_margin": round(MARGIN * len(rows), 2),
        "available": round(float(st["balance"]) - MARGIN * len(rows), 2),
        "equity": round(float(st["balance"]) + net_sum, 2) if rows else round(float(st["balance"]), 2),
        "init_balance": INIT_BAL,
        "margin_type": MARGIN_TYPE,
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
        "live": {
            "enabled": False,
            "paused": True,
            "paper": True,
            "venue": "binance_usdm",
            "margin": MARGIN,
            "leverage": LEVERAGE,
            "margin_type": MARGIN_TYPE,
        },
        "costs": {
            "commission_side": _commission_side(book),
            "commission_open": _commission_side(book),
            "commission_close": _commission_side(book),
            "commission_rt": round(_commission_side(book) * 2, 4),
            "taker": TAKER_FEE,
            "volume": (rows[0].get("qty") if rows else None) or _binance_qty(bid or 0.01),
            "notional": MARGIN * LEVERAGE,
            "fee_model": "binance_taker",
            "taker_pct": TAKER_FEE * 100.0,
            "note": "GPSUSDT_2 sanal Isolated MARKET $50×15x · kasa $160 · emir yok",
            "venue": "binance_usdm",
            "dec": _PX,
        },
        "venue": "binance_usdm",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        from desk_meta import attach
        attach(out, "gps2", hist=hist, positions=rows, state_path=_files(book)[0], init=out.get("init_balance"))
    except Exception:
        pass
    return out


def reset_book(book: str = "gps2") -> dict:
    """GPSUSDT_2 defterini $160'a çeker. Canlı GPSUSDT'ye dokunmaz."""
    book = "gps2"
    state_p, hist_p, lock_p = _files(book)
    _DIR.mkdir(parents=True, exist_ok=True)
    with open(lock_p, "a+", encoding="utf-8") as lk:
        fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
        st = _empty_state()
        _atomic_write(state_p, st)
        _atomic_write(hist_p, [])
    return snapshot(book=book)


