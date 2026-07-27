"""15M 210 gerçek PM — kısmi kar al (max kârın %65'inde %75 sat, %25 devam). A1/A2 saatlik eski düzen."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

_ENV_FILE = os.path.join(_DIR, "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from pm_trader_helpers import (
    pm_get_client,
    pm_stake_fields,
    sanal_pnl,
    tg_send_pm_live,
)

_TZ_TR = ZoneInfo("Europe/Istanbul")
_CTRL_FILE = os.path.join(_DIR, "pm_system_control.json")
_PM_GAMMA = "https://gamma-api.polymarket.com/events"
_PM_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

TRADERS = (
    {
        "key": "210",
        "label": "15M 210 SOL",
        "state_file": "poly_trader_5m_sol_210_state.json",
        "live_env": "PM_5M_210_REAL_ENABLED",
        "live_default": True,
    },
)


def partial_tp_config() -> dict:
    cfg = {
        "enabled": True,
        "profit_pct": 0.65,
        "sell_ratio": 0.75,
        "traders": ["210"],
    }
    if os.path.exists(_CTRL_FILE):
        try:
            with open(_CTRL_FILE) as f:
                c = json.load(f)
            if "pm_partial_tp_enabled" in c:
                cfg["enabled"] = bool(c["pm_partial_tp_enabled"])
            v = c.get("pm_partial_tp_profit_pct")
            if v is not None:
                fv = float(v)
                cfg["profit_pct"] = fv / 100.0 if fv > 1 else fv
            v = c.get("pm_partial_tp_sell_ratio")
            if v is not None:
                fv = float(v)
                cfg["sell_ratio"] = fv / 100.0 if fv > 1 else fv
            keys = c.get("pm_partial_tp_traders")
            if isinstance(keys, list) and keys:
                cfg["traders"] = [str(k).lower() for k in keys]
        except Exception:
            pass
    cfg["enabled"] = os.getenv(
        "PM_PARTIAL_TP_ENABLED", str(cfg["enabled"]).lower()
    ).lower() in ("1", "true", "yes")
    cfg["profit_pct"] = float(os.getenv("PM_PARTIAL_TP_PROFIT_PCT", cfg["profit_pct"]))
    cfg["sell_ratio"] = float(os.getenv("PM_PARTIAL_TP_SELL_RATIO", cfg["sell_ratio"]))
    cfg["profit_pct"] = max(0.05, min(2.0, cfg["profit_pct"]))
    cfg["sell_ratio"] = max(0.05, min(0.95, cfg["sell_ratio"]))
    cfg["traders"] = [str(k).lower() for k in cfg.get("traders") or ["210"]]
    return cfg


def pm_realized_pnl(pos: dict, win: bool) -> float:
    """Kısmi kar al sonrası nihai P&L."""
    partial = float(pos.get("pm_partial_received") or 0)
    spent_orig = float(
        pos.get("pm_spent_original") or pos.get("pm_spent") or pos.get("amount") or 0
    )
    _, size, _ = pm_stake_fields(pos)
    if partial > 0 and spent_orig > 0:
        remainder = size if win else 0.0
        return round(partial + remainder - spent_orig, 2)
    return sanal_pnl(pos, win)


def pm_token_price_gamma(pm_slug: str, token_dir: str) -> float | None:
    if not pm_slug or not token_dir:
        return None
    try:
        req = urllib.request.Request(
            f"{_PM_GAMMA}?slug={pm_slug}", headers=_PM_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
        if not data:
            return None
        m = data[0].get("markets", [{}])[0]
        raw = m.get("outcomePrices")
        op = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if len(op) >= 2:
            return float(op[0]) if token_dir == "UP" else float(op[1])
    except Exception:
        pass
    return None


def _pm_best_bid(client, token_id: str) -> float | None:
    try:
        book = client.get_order_book(token_id)
        bids = book.get("bids") or []
        if bids:
            return max(float(b["price"]) for b in bids)
    except Exception:
        pass
    return None


def _pm_sell_price(
    client, token_id: str, size: float, pm_slug: str = "", token_dir: str = "",
) -> float:
    from py_clob_client_v2 import OrderType

    bid = _pm_best_bid(client, token_id)
    if bid and bid > 0:
        return max(0.02, min(0.98, round(bid, 2)))
    try:
        p = float(client.calculate_market_price(token_id, "SELL", size, OrderType.FAK))
        if p > 0:
            return max(0.02, min(0.98, round(p, 2)))
    except Exception:
        pass
    gp = pm_token_price_gamma(pm_slug, token_dir)
    if gp and gp > 0:
        return max(0.02, min(0.98, round(gp - 0.01, 2)))
    return 0.50


def _pm_sell_ladder_prices(
    client, token_id: str, size: float, pm_slug: str = "", token_dir: str = "",
) -> list[float]:
    from py_clob_client_v2 import OrderType

    candidates: list[float] = []
    bid = _pm_best_bid(client, token_id)
    if bid and bid > 0:
        candidates.append(bid)
    try:
        mp = float(client.calculate_market_price(token_id, "SELL", size, OrderType.FAK))
        if mp > 0:
            candidates.append(mp)
    except Exception:
        pass
    gp = pm_token_price_gamma(pm_slug, token_dir)
    if gp and gp > 0:
        candidates.append(gp - 0.01)

    start = max(candidates) if candidates else 0.50
    start = max(0.02, min(0.98, round(start, 2)))
    prices: list[float] = []
    p = start
    while p >= 0.02 and len(prices) < 20:
        prices.append(round(p, 2))
        p = round(p - 0.03, 2)
    if 0.02 not in prices:
        prices.append(0.02)
    return prices


def _pm_conditional_shares(token_id: str) -> float:
    try:
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
        client = pm_get_client()
        bal = client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
        )
        raw = int(bal.get("balance", 0))
        return float(Decimal(str(raw / 1_000_000)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
    except Exception as e:
        print(f"[partial_tp] conditional balance: {e}", file=sys.stderr)
        return -1.0


def _stake_original(pos: dict) -> tuple[float, float]:
    """(ana_para, max_ödeme) — giriş anı harcama ve kazanınca toplam pay değeri ($1/pay)."""
    spent_orig = float(
        pos.get("pm_spent_original") or pos.get("pm_spent") or pos.get("amount") or 0
    )
    size_orig = float(
        pos.get("pm_size_original") or pos.get("pm_size") or pos.get("to_win") or 0
    )
    if size_orig <= 0 and spent_orig > 0:
        ep = float(pos.get("pm_entry_price") or pos.get("token_price") or 0)
        if ep > 0:
            size_orig = round(spent_orig / ep, 2)
    return spent_orig, size_orig


def pm_estimate_close_value(pos: dict) -> dict:
    """CLOB bid → anlık değer; profit_pct = gerçekleşen kâr / max kâr (kazanınca toplam − ana para)."""
    pm_size = float(pos.get("pm_size") or pos.get("to_win") or 0)
    spent_orig, size_orig = _stake_original(pos)
    if not pm_size or not spent_orig or not size_orig:
        return {
            "close_val": None, "close_pnl": None, "profit_pct": None,
            "max_profit": None, "token_cents": None,
        }
    token_id = pos.get("pm_token_id")
    slug = pos.get("pm_slug", "")
    token_dir = pos.get("pm_token_dir") or pos.get("predicted_dir", "")
    sell_price = None
    if token_id:
        try:
            client = pm_get_client()
            sell_price = _pm_sell_price(client, token_id, pm_size, slug, token_dir)
        except Exception:
            pass
    if not sell_price:
        gp = pm_token_price_gamma(slug, token_dir)
        if gp and gp > 0:
            sell_price = max(0.02, round(gp - 0.01, 2))
    if not sell_price:
        return {
            "close_val": None, "close_pnl": None, "profit_pct": None,
            "max_profit": None, "token_cents": None,
        }
    close_val = round(pm_size * sell_price, 2)
    close_pnl = round(close_val - spent_orig, 2)
    max_profit = round(size_orig - spent_orig, 2)
    profit_pct = round(close_pnl / max_profit, 4) if max_profit > 0 else None
    return {
        "close_val": close_val,
        "close_pnl": close_pnl,
        "profit_pct": profit_pct,
        "max_profit": max_profit,
        "spent_orig": spent_orig,
        "size_orig": size_orig,
        "token_cents": round(sell_price * 100, 1),
    }


def _pm_sell_position(
    token_id: str, size: float, pm_slug: str = "", token_dir: str = "",
) -> dict:
    try:
        from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
        from py_clob_client_v2.order_builder.constants import SELL

        client = pm_get_client()
        size = float(Decimal(str(size)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        if size <= 0:
            return {"ok": False, "error": "geçersiz boyut"}

        last_err = "bilinmeyen hata"
        for price in _pm_sell_ladder_prices(client, token_id, size, pm_slug, token_dir):
            try:
                args = OrderArgs(token_id=token_id, price=price, size=size, side=SELL)
                signed = client.create_order(args, PartialCreateOrderOptions())
                resp = client.post_order(signed, order_type=OrderType.FAK)
                print(f"[partial_tp] PM sell @{price}: {resp}", flush=True)
            except Exception as e:
                last_err = str(e)
                continue

            if not resp:
                last_err = "boş yanıt"
                continue

            status = resp.get("status", "")
            if resp.get("success") and status in ("matched", "live", "delayed"):
                try:
                    received = round(float(resp.get("takingAmount") or 0), 2)
                except (TypeError, ValueError):
                    received = round(size * price, 2)
                if received <= 0:
                    received = round(size * price, 2)
                try:
                    sold = round(float(resp.get("makingAmount") or size), 2)
                except (TypeError, ValueError):
                    sold = size
                return {
                    "ok": True, "price": price, "size": sold,
                    "received": received, "status": status,
                }
            last_err = resp.get("errorMsg") or f"FAK eşleşmedi (status={status})"
        return {"ok": False, "error": last_err}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def pm_sell_shares_retry(
    token_id: str, size: float, pm_slug: str = "", token_dir: str = "",
) -> dict:
    chain = _pm_conditional_shares(token_id)
    req = float(Decimal(str(size)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
    if chain >= 0:
        if chain <= 0.01:
            return {
                "ok": True, "received": 0.0, "size": 0.0, "price": 0.0,
                "reconciled": True, "status": "already_closed",
            }
        req = min(req, chain)

    remaining = req
    total_received = 0.0
    total_sold = 0.0
    last: dict = {"ok": False, "error": "satış başarısız"}
    for _ in range(6):
        if remaining <= 0.01:
            break
        last = _pm_sell_position(token_id, remaining, pm_slug=pm_slug, token_dir=token_dir)
        if not last.get("ok"):
            break
        got = float(last.get("received") or 0)
        sold = float(last.get("size") or remaining)
        total_received += got
        total_sold += sold
        remaining = round(remaining - sold, 2)
        if remaining <= 0.01:
            break

    if total_received > 0 or last.get("reconciled"):
        out = dict(last)
        out["ok"] = True
        out["received"] = round(total_received, 2)
        out["size"] = round(total_sold, 2)
        return out
    return last


def _trader_live(trader: dict) -> bool:
    env_key = trader.get("live_env")
    if env_key:
        return os.getenv(env_key, str(trader.get("live_default", False)).lower()).lower() in (
            "1", "true", "yes",
        )
    return bool(trader.get("live_default", True))


def _load_json(path: str) -> dict | list | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _save_json(path: str, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def maybe_partial_takeprofit(
    pos: dict, *, label: str, cfg: dict | None = None, dry_run: bool | None = None,
) -> dict | None:
    """Eşik aşıldıysa kısmi satış uygular; güncellenmiş pos veya None."""
    if pos.get("pm_partial_tp_done"):
        return None
    if not pos.get("pm_token_id") or not pos.get("pm_slug"):
        return None
    if pos.get("pm_error"):
        return None

    cfg = cfg or partial_tp_config()
    if not cfg.get("enabled"):
        return None

    est = pm_estimate_close_value(pos)
    profit_pct = est.get("profit_pct")
    max_profit = est.get("max_profit")
    if profit_pct is None or max_profit is None or max_profit <= 0:
        return None
    if profit_pct < cfg["profit_pct"]:
        return None

    spent, pm_size, _ = pm_stake_fields(pos)
    if pm_size <= 0 or spent <= 0:
        return None

    sell_ratio = cfg["sell_ratio"]
    sell_size = float(
        Decimal(str(pm_size * sell_ratio)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    )
    keep_ratio = 1.0 - sell_ratio
    keep_size = round(pm_size - sell_size, 2)

    if sell_size < 5.0:
        print(
            f"[partial_tp] {label} — pay çok küçük ({sell_size:.2f}), atlandı",
            file=sys.stderr,
        )
        return None
    if keep_size < 0.01:
        return None

    token_id = pos["pm_token_id"]
    slug = pos.get("pm_slug", "")
    token_dir = pos.get("pm_token_dir") or pos.get("predicted_dir", "")

    use_dry = bool(dry_run)
    if use_dry:
        recv_est = round(est.get("close_val", spent) * sell_ratio, 2)
        close_pnl = est.get("close_pnl") or 0
        print(
            f"[partial_tp DRY] {label} kâr yolu {profit_pct*100:.0f}% "
            f"(${close_pnl:.2f}/${max_profit:.2f}) → "
            f"sell {sell_ratio*100:.0f}% ({sell_size:.2f} pay) ~${recv_est:.2f}",
        )
        return {"dry_run": True, "would_sell": sell_size, "would_receive": recv_est}

    sell_result = pm_sell_shares_retry(token_id, sell_size, pm_slug=slug, token_dir=token_dir)
    if not sell_result.get("ok"):
        print(
            f"[partial_tp] {label} satış hatası: {sell_result.get('error')}",
            file=sys.stderr,
        )
        return None

    received = float(sell_result.get("received") or 0)
    sold = float(sell_result.get("size") or sell_size)
    if sold <= 0:
        return None

    actual_keep = round(pm_size - sold, 2)
    spent_orig = float(pos.get("pm_spent_original") or spent)
    size_orig = float(pos.get("pm_size_original") or pm_size)
    keep_spent = round(spent_orig * (actual_keep / pm_size), 2) if pm_size > 0 else spent

    pos["pm_spent_original"] = spent_orig
    pos["pm_size_original"] = size_orig
    pos["pm_partial_tp_done"] = True
    pos["pm_partial_sold_size"] = round(float(pos.get("pm_partial_sold_size") or 0) + sold, 2)
    pos["pm_partial_received"] = round(float(pos.get("pm_partial_received") or 0) + received, 2)
    pos["pm_partial_tp_tr"] = datetime.now(timezone.utc).astimezone(_TZ_TR).isoformat()
    pos["pm_size"] = actual_keep
    pos["pm_spent"] = keep_spent
    if pos.get("to_win") is not None:
        pos["to_win"] = actual_keep

    sym = pos.get("symbol", "").replace("USDT", "")
    pred = pos.get("predicted_dir") or token_dir
    close_val = est.get("close_val") or spent
    close_pnl = est.get("close_pnl") or 0
    pct_show = round(profit_pct * 100, 1)
    sell_pct_show = int(round(sold / pm_size * 100))
    keep_pct_show = 100 - sell_pct_show

    tg_send_pm_live(
        f"💰 <b>{label} — Kısmi kar al</b>\n"
        f"{sym} {pred}  ${spent_orig:.2f}→${close_val:.2f}\n"
        f"Kâr yolu: <b>{pct_show}%</b> (${close_pnl:.2f} / ${max_profit:.2f} max)\n"
        f"Satıldı: <b>{sell_pct_show}%</b> ({sold:.2f} pay) → ${received:.2f}\n"
        f"Kalan: <b>{keep_pct_show}%</b> ({actual_keep:.2f} pay) açık",
        label=label,
    )
    print(
        f"[partial_tp] {label} {sym} kâr yolu {pct_show}% — "
        f"sold {sold:.2f}@${received:.2f}, keep {actual_keep:.2f}",
    )
    return pos


def run_partial_tp_check(*, dry_run: bool = False) -> None:
    cfg = partial_tp_config()
    if not cfg.get("enabled"):
        print("[partial_tp] devre dışı")
        return

    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    any_change = False

    for trader in TRADERS:
        if trader["key"] not in cfg.get("traders", ["210"]):
            continue
        if not _trader_live(trader):
            continue
        path = os.path.join(_DIR, trader["state_file"])
        state = _load_json(path)
        if not isinstance(state, dict):
            continue
        positions = state.get("open_positions") or []
        if not positions:
            continue

        changed = False
        for pos in list(positions):
            if pos.get("pm_partial_tp_done"):
                continue
            if not (pos.get("pm_slug") and pos.get("pm_token_id")):
                continue
            result = maybe_partial_takeprofit(pos, label=trader["label"], cfg=cfg, dry_run=dry_run)
            if result is not None and not result.get("dry_run"):
                changed = True

        if changed:
            _save_json(path, state)
            any_change = True
            print(f"[partial_tp] {trader['label']} {saat} — state güncellendi")

    if not any_change:
        print(f"[partial_tp] {saat} — eşik yok / işlem yok")


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    run_partial_tp_check(dry_run=dry)
