"""Manuel PM — slot bitince otomatik settle (dashboard state + history).

Cron: her dakika close (bitmemiş slotlar atlanır)
  * * * * * cd /root/aiProject && python3 temmuzPoly/poly_trader_manual.py close
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pm_manual_sync import _desk_timeframe
from pm_trader_helpers import (
    pm_5m_history_extras,
    pm_fetch_resolution,
    pm_realized_pnl,
    pm_stake_fields,
    tg_send_pm_live,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE = os.path.join(_DIR, "poly_trader_manual_state.json")
_HISTORY = os.path.join(_DIR, "poly_trader_manual_history.json")
_TZ = ZoneInfo("Europe/Istanbul")
_LABEL = "MANUEL PM"
_BINANCE = "https://fapi.binance.com"


def _load(path: str, default):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _slot_seconds(pos: dict) -> int:
    tf = pos.get("timeframe") or _desk_timeframe(pos.get("pm_slug") or "") or "1h"
    if tf == "5m":
        return 300
    if tf == "15m":
        return 900
    return 3600


def _fetch_period_candle(symbol: str, ts_period: int, interval: str) -> dict | None:
    """Slot başlangıç mumunun open/close (tamamlanmış mum)."""
    try:
        start_ms = int(ts_period) * 1000
        root = os.path.dirname(_DIR)
        if root not in sys.path:
            sys.path.insert(0, root)
        from binance_fapi_guard import public_klines
        rows = public_klines(symbol, interval, 1, start_time_ms=start_ms)
        if not rows:
            return None
        k = rows[0]
        return {
            "open": float(k[1]),
            "close": float(k[4]),
            "open_time": int(k[0]) // 1000,
        }
    except Exception as e:
        print(f"[{_LABEL}] kline {symbol}@{ts_period}: {e}", file=sys.stderr)
        return None


def _interval_for(pos: dict) -> str:
    tf = pos.get("timeframe") or _desk_timeframe(pos.get("pm_slug") or "") or "1h"
    return {"5m": "5m", "15m": "15m"}.get(tf, "1h")


def _resolution(pos: dict, period_ended: bool) -> dict | None:
    slug = pos.get("pm_slug") or ""
    if not slug:
        return None
    thr = 0.90 if period_ended else 0.99
    for _ in range(4 if period_ended else 1):
        res = pm_fetch_resolution(slug, min_decisive=thr)
        if res is not None:
            return res
        if not period_ended:
            break
        time.sleep(2)
    return None


def _tg_line(pos: dict, win: bool, pnl: float, actual: str, source: str) -> str:
    sym = (pos.get("symbol") or "").replace("USDT", "")
    pred = pos.get("predicted_dir") or pos.get("pm_token_dir") or "?"
    spent, size, _ = pm_stake_fields(pos)
    icon = "✅" if win else "❌"
    return (
        f"{icon} <b>{sym}</b> {pred}→{actual}  "
        f"${spent:.2f}→{'${:.2f}'.format(size) if win else '$0'}  "
        f"net {'+' if pnl >= 0 else ''}{pnl:.2f}$  ({source})"
    )


def run_close(*, force: bool = False) -> dict:
    """Bitmiş manuel slotları PM settle ile kapat."""
    now_tr = datetime.now(timezone.utc).astimezone(_TZ)
    now_ts = time.time()
    state = _load(_STATE, {"open_positions": [], "total_pnl": 0.0, "balance": 0})
    history = _load(_HISTORY, [])
    opens = list(state.get("open_positions") or [])
    if not opens:
        print(f"[{_LABEL} close] açık pozisyon yok")
        return {"ok": True, "closed": 0, "kept": 0}

    kept: list[dict] = []
    closed_rows: list[dict] = []
    lines: list[str] = []
    tur_pnl = 0.0

    for pos in opens:
        sym = (pos.get("symbol") or "").upper()
        if not sym.endswith("USDT"):
            sym = sym + "USDT"
        pos_ts = int(pos.get("ts_period") or 0)
        dur = _slot_seconds(pos)
        period_ended = bool(pos_ts) and now_ts >= pos_ts + dur
        if pos_ts and not period_ended and not force:
            kept.append(pos)
            print(f"[{_LABEL} close] {sym.replace('USDT','')} slot devam")
            continue

        candle = _fetch_period_candle(sym, pos_ts, _interval_for(pos)) if pos_ts else None
        if candle is None and not force:
            # Mum yoksa biraz bekle; force değilse tut
            kept.append(pos)
            print(f"[{_LABEL} close] {sym}: mum yok — bekleniyor", file=sys.stderr)
            continue

        ref_open = float(candle["open"]) if candle else float(pos.get("entry_price") or 0)
        prev_close = float(candle["close"]) if candle else ref_open
        pred = pos.get("predicted_dir") or pos.get("pm_token_dir") or ""
        binance_actual = "UP" if prev_close >= ref_open else "DOWN"
        amount = float(pos.get("pm_spent") or pos.get("amount") or 0)

        has_pm = bool(pos.get("pm_slug") and pos.get("pm_order_id"))
        pm_source = False
        if has_pm:
            res = _resolution(pos, period_ended=period_ended or force)
            if res is None:
                print(
                    f"[{_LABEL} close] {sym.replace('USDT','')} PM sonuç yok — Binance",
                    file=sys.stderr,
                )
                win = pred == binance_actual
                actual = binance_actual
                pnl = pm_realized_pnl(pos, win)
            else:
                token_dir = pos.get("pm_token_dir") or pred
                win = (token_dir == "UP" and res["up_won"]) or (
                    token_dir == "DOWN" and not res["up_won"]
                )
                actual = "UP" if res["up_won"] else "DOWN"
                pnl = pm_realized_pnl(pos, win)
                pm_source = True
        else:
            win = pred == binance_actual
            actual = binance_actual
            pnl = pm_realized_pnl(pos, win)

        tur_pnl += pnl
        state["total_pnl"] = round(float(state.get("total_pnl") or 0) + pnl, 2)
        row = {
            "symbol": sym,
            "predicted_dir": pred,
            "actual_dir": actual,
            "binance_actual": binance_actual,
            "win": win,
            "entry_price": ref_open,
            "exit_price": prev_close,
            "amount": amount,
            "pnl": pnl,
            "entry_time_tr": pos.get("entry_time_tr"),
            "entry_period_min": pos.get("entry_period_min") or (dur // 60),
            "entry_dow": pos.get("entry_dow"),
            "entry_hour_tr": pos.get("entry_hour_tr"),
            "exit_time_tr": now_tr.isoformat(),
            "timeframe": pos.get("timeframe") or _desk_timeframe(pos.get("pm_slug") or ""),
            "manual": True,
            "settle_source": "pm" if pm_source else "binance",
            "ts_period": pos.get("ts_period"),
            "note": "manuel otomatik settle",
            **pm_5m_history_extras(pos),
        }
        history.append(row)
        closed_rows.append(row)
        lines.append(_tg_line(pos, win, pnl, actual, "pm" if pm_source else "bn"))
        print(
            f"[{_LABEL} close] {sym.replace('USDT','')} {pred}→{actual} "
            f"{'W' if win else 'L'} pnl={pnl:+.2f} ({row['settle_source']})"
        )

    state["open_positions"] = kept
    _save(_STATE, state)
    _save(_HISTORY, history[-2000:])

    if lines:
        sep = "━" * 26
        try:
            tg_send_pm_live(
                f"{sep}\n"
                f"⏹ <b>{_LABEL} — Slot Settle</b>  🔴 GERÇEK PM\n"
                + "\n".join(lines)
                + f"\nΣ tur {'+' if tur_pnl >= 0 else ''}{tur_pnl:.2f}$\n"
                f"{sep}",
                label=_LABEL,
            )
        except Exception as e:
            print(f"[{_LABEL}] tg: {e}", file=sys.stderr)

    return {
        "ok": True,
        "closed": len(closed_rows),
        "kept": len(kept),
        "tur_pnl": round(tur_pnl, 2),
        "closed_rows": [
            {
                "sym": r["symbol"].replace("USDT", ""),
                "dir": r["predicted_dir"],
                "win": r["win"],
                "pnl": r["pnl"],
            }
            for r in closed_rows
        ],
    }


def main() -> None:
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "close").strip().lower()
    force = "--force" in sys.argv
    if cmd in ("close", "settle"):
        out = run_close(force=force)
        print(json.dumps({k: v for k, v in out.items() if k != "closed_rows"}, ensure_ascii=False))
        for r in out.get("closed_rows") or []:
            print(f"  {r['sym']} {r['dir']} {'W' if r['win'] else 'L'} {r['pnl']:+.2f}")
        return
    print("kullanım: poly_trader_manual.py close [--force]", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
