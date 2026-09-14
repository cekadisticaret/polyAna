#!/usr/bin/env python3
"""2.Poly — basit işlem dashboard (Flask)."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "algo"))
sys.path.insert(0, str(ROOT / "src" / "trading"))

from bootstrap import DATA, init  # noqa: E402

init()

from flask import Flask, jsonify, redirect, request, send_file, send_from_directory, session, url_for  # noqa: E402

TZ_TR = ZoneInfo("Europe/Istanbul")
DASHBOARD_DIR = Path(__file__).resolve().parent

app = Flask(__name__, static_folder=str(DASHBOARD_DIR / "static"), static_url_path="/static")
app.secret_key = os.getenv("DASHBOARD_SECRET", "poly2-a205-change-me")

DASH_USER = os.getenv("DASHBOARD_USER", "admin")
DASH_PASS = os.getenv("DASHBOARD_PASSWORD", "")


def _authed() -> bool:
    return bool(session.get("authed"))


def _download_token() -> str:
    return hashlib.sha256(f"{app.secret_key}:poly2-project".encode()).hexdigest()[:24]


def _download_allowed() -> bool:
    tok = (request.args.get("t") or "").strip()
    return _authed() or (bool(tok) and tok == _download_token())


@app.before_request
def _require_login():
    if request.endpoint in ("login", "static"):
        return None
    if request.path.startswith("/static/"):
        return None
    if request.endpoint == "download_project" and _download_allowed():
        return None
    if not DASH_PASS:
        return None
    if _authed():
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = (request.form.get("username") or "").strip()
        pw = request.form.get("password") or ""
        if user == DASH_USER and pw == DASH_PASS:
            session["authed"] = True
            session.permanent = True
            return redirect("/")
        error = "Kullanıcı veya şifre hatalı"
    html = (DASHBOARD_DIR / "static" / "login.html").read_text(encoding="utf-8")
    html = html.replace("{% if error %}<div class=\"err\">{{ error }}</div>{% endif %}",
                        f'<div class="err">{error}</div>' if error else "")
    return html


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/logout")
def logout_get():
    session.clear()
    return redirect(url_for("login"))


_CACHE: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl: float, fn):
    """TTL cache — dış API çağrıları her sayfa yenilemede tekrarlanmasın."""
    hit = _CACHE.get(key)
    now = time.time()
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    value = fn()
    _CACHE[key] = (now, value)
    return value


def _read_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _token_price(token_id: str) -> dict:
    """Token'ın anlık order book fiyatı — satışta alınacak (bid) taraf."""
    if not token_id:
        return {"bid": None, "ask": None, "mid": None}

    def fetch():
        url = f"https://clob.polymarket.com/book?token_id={token_id}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "2.Poly", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            book = json.loads(r.read().decode())
        bids = [float(x["price"]) for x in (book.get("bids") or [])]
        asks = [float(x["price"]) for x in (book.get("asks") or [])]
        bid = max(bids) if bids else 0.0
        ask = min(asks) if asks else 0.0
        mid = round((bid + ask) / 2, 4) if (bid or ask) else 0.0
        return {"bid": bid, "ask": ask, "mid": mid}

    try:
        return _cached(f"book:{token_id}", 9.0, fetch)
    except Exception:
        return {"bid": None, "ask": None, "mid": None}


def _pm_positions() -> dict:
    """Cüzdandaki PM hisseleri — redeem bekleyen kazançlar nakitte görünmüyor."""

    def fetch():
        funder = os.getenv("POLY_FUNDER", "")
        if not funder:
            return {"redeemable": 0.0, "holding": 0.0, "items": []}
        url = f"https://data-api.polymarket.com/positions?sizeThreshold=0.1&user={funder}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "2.Poly", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            rows = json.loads(r.read().decode())
        redeemable = holding = 0.0
        items = []
        for p in rows if isinstance(rows, list) else []:
            value = float(p.get("currentValue") or 0)
            if value <= 0.01:
                continue
            if p.get("redeemable"):
                redeemable += value
                items.append({
                    "title": p.get("title", ""),
                    "value": round(value, 2),
                    "size": round(float(p.get("size") or 0), 2),
                })
            else:
                holding += value
        items.sort(key=lambda x: x["value"], reverse=True)
        return {
            "redeemable": round(redeemable, 2),
            "holding": round(holding, 2),
            "items": items,
        }

    try:
        return _cached("pm_positions", 25.0, fetch)
    except Exception:
        return {"redeemable": 0.0, "holding": 0.0, "items": []}


def _chain_ledger() -> dict:
    """Zincirdeki gerçek para akışı — bot defteri yerine tek doğru kaynak."""

    def fetch():
        funder = os.getenv("POLY_FUNDER", "")
        if not funder:
            return {}
        url = f"https://data-api.polymarket.com/activity?user={funder}&limit=500"
        req = urllib.request.Request(
            url, headers={"User-Agent": "2.Poly", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read().decode())
        buys = sells = redeems = 0.0
        n_buy = n_sell = 0
        per_slug: dict[str, dict] = {}
        for a in rows if isinstance(rows, list) else []:
            value = float(a.get("usdcSize") or 0)
            kind = a.get("type")
            slug = a.get("slug") or ""
            row = per_slug.setdefault(slug, {"spent": 0.0, "size": 0.0})
            if kind == "TRADE":
                if a.get("side") == "SELL":
                    sells += value
                    n_sell += 1
                else:
                    buys += value
                    n_buy += 1
                    row["spent"] += value
                    row["size"] += float(a.get("size") or 0)
            elif kind == "REDEEM":
                redeems += value
        return {
            "per_slug": {
                s: {"spent": round(v["spent"], 2), "size": round(v["size"], 2)}
                for s, v in per_slug.items()
                if v["spent"] > 0
            },
            "buys": round(buys, 2),
            "sells": round(sells, 2),
            "redeems": round(redeems, 2),
            "manual_sells": n_sell,
            "trades": n_buy,
            "net_flow": round(sells + redeems - buys, 2),
        }

    try:
        return _cached("chain_ledger", 60.0, fetch)
    except Exception:
        return {}


def _spot_prices(symbols: list[str]) -> dict:
    """Sembollerin anlık fiyatı (Binance futures ticker)."""

    def fetch():
        out = {}
        for pair in symbols:
            try:
                url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={pair}"
                req = urllib.request.Request(url, headers={"User-Agent": "2.Poly"})
                with urllib.request.urlopen(req, timeout=6) as r:
                    out[pair] = float(json.loads(r.read().decode())["price"])
            except Exception:
                out[pair] = None
        return out

    try:
        return _cached("spot:" + ",".join(sorted(symbols)), 5.0, fetch)
    except Exception:
        return {p: None for p in symbols}


def _sym_short(symbol: str) -> str:
    return (symbol or "").replace("USDT", "")


def _wr_pct(wins: int, total: int) -> float | None:
    return round(wins / total * 100, 1) if total else None


def _stats(history: list) -> dict:
    total = len(history)
    wins = sum(1 for t in history if t.get("win"))
    pnl = round(sum(float(t.get("pnl") or 0) for t in history), 2)
    return {
        "trades": total,
        "wins": wins,
        "losses": total - wins,
        "wr_pct": _wr_pct(wins, total),
        "pnl": pnl,
    }


def _format_pos(
    pos: dict, kind: str, spot: dict | None = None, chain: dict | None = None
) -> dict:
    sym = _sym_short(pos.get("symbol", ""))
    pair = pos.get("symbol") or ""
    direction = pos.get("predicted_dir") or pos.get("pm_token_dir") or "—"
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    size = float(pos.get("pm_size") or pos.get("to_win") or 0)
    # Aynı pm_slug'ta birden fazla pozisyon varsa zincir toplamı tüm kartlara yazılır — kullanma
    entry = float(pos.get("entry_price") or 0)
    hour = pos.get("entry_hour_tr")

    now_spot = (spot or {}).get(pair)
    spot_diff = spot_pct = None
    winning = None
    if now_spot and entry:
        spot_diff = round(now_spot - entry, 2)
        spot_pct = round((now_spot - entry) / entry * 100, 2)
        winning = (now_spot > entry) if direction == "UP" else (now_spot < entry)

    book = _token_price(pos.get("pm_token_id") or "")
    exit_price = book.get("bid")
    if not exit_price:
        exit_price = book.get("mid") or 0.0
    close_value = round(size * float(exit_price or 0), 2)
    pnl_now = round(close_value - spent, 2) if spent else 0.0
    pnl_pct = round(pnl_now / spent * 100, 1) if spent else None

    return {
        "kind": kind,
        "symbol": sym,
        "pair": pair,
        "direction": direction,
        "amount": round(spent, 2),
        "entry_price": round(entry, 2) if entry else None,
        "hour_tr": hour,
        "to_win": round(size, 2) if size else None,
        "win_profit": round(size - spent, 2) if size and spent else None,
        "pm_slug": pos.get("pm_slug"),
        "pm_entry_price": pos.get("pm_entry_price"),
        "entry_time_tr": pos.get("entry_time_tr"),
        "spot_now": round(now_spot, 2) if now_spot else None,
        "spot_diff": spot_diff,
        "spot_pct": spot_pct,
        "winning": winning,
        "token_bid": book.get("bid"),
        "token_ask": book.get("ask"),
        "close_value": close_value,
        "pnl_now": pnl_now,
        "pnl_pct": pnl_pct,
    }


def _recent_trades(history: list, limit: int = 30) -> list:
    rows = []
    for t in reversed(history[-limit:]):
        rows.append({
            "symbol": _sym_short(t.get("symbol", "")),
            "direction": t.get("predicted_dir"),
            "actual": t.get("actual_dir"),
            "win": bool(t.get("win")),
            "pnl": round(float(t.get("pnl") or 0), 2),
            "amount": round(float(t.get("amount") or 0), 2),
            "entry_time_tr": t.get("entry_time_tr"),
            "exit_time_tr": t.get("exit_time_tr"),
            "live": bool(t.get("pm_live")),
        })
    return rows


def _symbol_stats(history: list, symbol: str) -> dict:
    sym = f"{symbol}USDT" if not symbol.endswith("USDT") else symbol
    trades = [t for t in history if t.get("symbol") == sym or _sym_short(t.get("symbol", "")) == _sym_short(sym)]
    wins = sum(1 for t in trades if t.get("win"))
    total = len(trades)
    return {
        "trades": total,
        "wins": wins,
        "losses": total - wins,
        "wr_pct": _wr_pct(wins, total),
    }


def _hour_stats(history: list) -> list[dict]:
    buckets: dict[int, list] = {}
    for t in history:
        h = t.get("entry_hour_tr")
        if h is None:
            continue
        buckets.setdefault(int(h), []).append(t)
    rows = []
    for h in range(24):
        trades = buckets.get(h, [])
        wins = sum(1 for t in trades if t.get("win"))
        total = len(trades)
        rows.append({
            "hour": h,
            "trades": total,
            "wins": wins,
            "wr_pct": _wr_pct(wins, total),
        })
    return rows


def build_a205() -> dict:
    from mean_reversion import SYMBOLS, fetch_klines, mean_reversion_detail
    from balance_guard import get_system_control, get_usdc_balance, is_group_paused

    now_tr = datetime.now(timezone.utc).astimezone(TZ_TR)
    hour_tr = now_tr.hour
    settings = _read_json(ROOT / "config" / "trade_settings.json", {})

    sanal_state = _read_json(DATA / "paper_state.json", {})
    sanal_history = _read_json(DATA / "paper_history.json", [])
    live_state = _read_json(DATA / "live_state.json", {})
    live_history = _read_json(DATA / "live_history.json", [])
    signals_raw = _read_json(DATA / "signals.json", {})
    control = get_system_control()

    sanal_stats = _stats(sanal_history)
    live_stats = _stats(live_history)
    sanal_open = sanal_state.get("open_positions") or []
    live_open_all = live_state.get("open_positions") or []
    live_open = live_open_all

    def build_symbols():
        rows = []
        for sym, pair in SYMBOLS.items():
            detail = {"signal": "NEUTRAL", "z": 0.0, "mean": 0.0, "std": 0.0, "close": 0.0}
            try:
                kl = fetch_klines(pair, "1h", 200)
                if kl:
                    detail = mean_reversion_detail(kl)
            except Exception:
                pass
            rows.append({"symbol": sym, "pair": pair, **detail})
        return rows

    symbols = [
        {**row, **_symbol_stats(live_history, row["symbol"])}
        for row in _cached("zscore", 25.0, build_symbols)
    ]

    spot = _spot_prices([p.get("symbol") for p in live_open if p.get("symbol")])
    for row in symbols:
        live_now = spot.get(row["pair"])
        if live_now:
            row["close"] = round(live_now, 2)

    usdc = _cached("usdc", 20.0, get_usdc_balance)
    usdc_ok = usdc < 9000
    wallet = _pm_positions()
    chain = _chain_ledger()

    open_positions = [
        {
            ** _format_pos(p, "live", spot),
            "is_stale": int(p.get("entry_hour_tr", -1)) != hour_tr,
        }
        for p in live_open
    ]
    risk_live = sum(p["amount"] for p in open_positions)
    to_win_total = sum(p["to_win"] or 0 for p in open_positions)
    close_total = sum(p["close_value"] for p in open_positions)
    pnl_open = sum(p["pnl_now"] for p in open_positions)

    all_recent = _recent_trades(live_history, 40)
    all_recent.sort(key=lambda x: x.get("exit_time_tr") or x.get("entry_time_tr") or "", reverse=True)

    sig_entry = (signals_raw.get("signals") or {}).get("5") or {}

    return {
        "algo": "A2#05",
        "name": "Mean Reversion (Z-Score)",
        "updated_at_tr": now_tr.strftime("%H:%M:%S"),
        "signal_cached_at": signals_raw.get("generated_at"),
        "signal_cached": {
            "BTC": sig_entry.get("BTC"),
            "ETH": sig_entry.get("ETH"),
            "SOL": sig_entry.get("SOL"),
        },
        "symbols": symbols,
        "sanal": {
            **sanal_stats,
            "balance": round(float(sanal_state.get("balance") or 300), 2),
            "open_count": len(sanal_open),
            "pnl": round(float(sanal_state.get("total_pnl") or sanal_stats["pnl"]), 2),
        },
        "live": {
            **live_stats,
            "open_count": len(live_open_all),
            "pnl": round(live_stats["pnl"], 2),
        },
        "cash_usdc": round(usdc, 2) if usdc_ok else None,
        "usdc_error": not usdc_ok,
        "usdc_error_reason": (
            ".env eksik (POLY_PRIVATE_KEY)"
            if not os.getenv("POLY_PRIVATE_KEY")
            else "PM bakiye okunamadı"
            if not usdc_ok
            else None
        ),
        "risk_total": round(risk_live, 2),
        "to_win_total": round(to_win_total, 2),
        "close_total": round(close_total, 2),
        "pnl_open": round(pnl_open, 2),
        "redeemable": wallet["redeemable"],
        "redeemable_items": wallet["items"],
        "holding": wallet["holding"],
        # Cüzdandaki her şey: nakit + elde tutulan hisse + redeem bekleyen
        "equity": round(usdc + wallet["holding"] + wallet["redeemable"], 2) if usdc_ok else None,
        "chain": chain,
        "start_balance": round(float(os.getenv("POLY_START_BALANCE", "381.89")), 2),
        "open_count": len(open_positions),
        "stale_open_count": sum(1 for p in open_positions if p.get("is_stale")),
        "open_positions": open_positions,
        "recent_trades": all_recent[:30],
        "hour_stats": _hour_stats(live_history),
        "amounts": {
            "sanal_low": settings.get("sanal_a2_05_amount_low", 12),
            "sanal_mid": settings.get("sanal_a2_05_amount_mid", 16),
            "sanal_high": settings.get("sanal_a2_05_amount_high", 20),
            "live_low": settings.get("a2_05_amount_low", 2.5),
            "live_mid": settings.get("a2_05_amount_mid", 2.5),
            "live_high": settings.get("a2_05_amount_high", 2.5),
        },
        "cron": [
            {"time": ":01:30", "label": "Sinyal üret"},
            {"time": ":02", "label": "Kapat + aç"},
            {"time": ":02:10", "label": "Açılış retry"},
            {"time": ":03", "label": "Redeem"},
        ],
        "mode": "live_only",
        "control": {
            "a2_05_live_paused": control.get("a2_05_live_paused", True),
            "updated_at_tr": control.get("updated_at_tr"),
            "updated_by": control.get("updated_by"),
        },
    }


def build_status() -> dict:
    from balance_guard import get_system_control, get_usdc_balance, is_group_paused

    now_tr = datetime.now(timezone.utc).astimezone(TZ_TR)

    sanal_state = _read_json(DATA / "paper_state.json", {})
    sanal_history = _read_json(DATA / "paper_history.json", [])
    live_state = _read_json(DATA / "live_state.json", {})
    live_history = _read_json(DATA / "live_history.json", [])
    signals_raw = _read_json(DATA / "signals.json", {})
    control = get_system_control()

    sig_entry = (signals_raw.get("signals") or {}).get("5") or {}
    signals = {
        "BTC": sig_entry.get("BTC", "—"),
        "ETH": sig_entry.get("ETH", "—"),
        "SOL": sig_entry.get("SOL", "—"),
        "name": sig_entry.get("name", "Mean Reversion"),
        "generated_at": signals_raw.get("generated_at"),
    }

    sanal_stats = _stats(sanal_history)
    live_stats = _stats(live_history)

    sanal_balance = round(float(sanal_state.get("balance") or 300), 2)
    sanal_open = sanal_state.get("open_positions") or []
    live_open = live_state.get("open_positions") or []

    risk_sanal = sum(float(p.get("amount") or 0) for p in sanal_open)
    risk_live = sum(float(p.get("amount") or p.get("pm_spent") or 0) for p in live_open)
    to_win_total = sum(float(p.get("to_win") or 0) for p in sanal_open + live_open)

    usdc = get_usdc_balance()
    usdc_ok = usdc < 9000
    cash = round(usdc, 2) if usdc_ok else None

    portfolio = cash if cash is not None else sanal_balance

    open_positions = [_format_pos(p, "sanal") for p in sanal_open] + [
        _format_pos(p, "live") for p in live_open
    ]

    strategies = [
        {
            "id": "a2_05_sanal",
            "label": "A2#05 Sanal",
            "kind": "sanal",
            "open": True,
            "wr_pct": sanal_stats["wr_pct"],
            "wins": sanal_stats["wins"],
            "losses": sanal_stats["losses"],
            "pnl": sanal_stats["pnl"],
            "open_count": len(sanal_open),
        },
        {
            "id": "a2_05_live",
            "label": "A2#05 Mean Rev Live",
            "kind": "live",
            "open": not is_group_paused("a2_05_live"),
            "wr_pct": live_stats["wr_pct"],
            "wins": live_stats["wins"],
            "losses": live_stats["losses"],
            "pnl": live_stats["pnl"],
            "open_count": len(live_open),
        },
    ]

    all_recent = _recent_trades(sanal_history, 20) + _recent_trades(live_history, 20)
    all_recent.sort(key=lambda x: x.get("exit_time_tr") or x.get("entry_time_tr") or "", reverse=True)

    return {
        "updated_at_tr": now_tr.strftime("%H:%M:%S"),
        "updated_at_iso": now_tr.isoformat(),
        "portfolio": portfolio,
        "cash_usdc": cash,
        "usdc_error": not usdc_ok,
        "sanal_balance": sanal_balance,
        "risk_total": round(risk_sanal + risk_live, 2),
        "to_win_total": round(to_win_total, 2),
        "open_count": len(open_positions),
        "signals": signals,
        "strategies": strategies,
        "sanal_stats": sanal_stats,
        "live_stats": live_stats,
        "open_positions": open_positions,
        "recent_trades": all_recent[:25],
        "control": {
            "a2_05_live_paused": control.get("a2_05_live_paused", True),
            "updated_at_tr": control.get("updated_at_tr"),
            "updated_by": control.get("updated_by"),
        },
    }


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(DASHBOARD_DIR / "static", "favicon.svg", mimetype="image/svg+xml")


@app.get("/")
def index():
    return send_from_directory(DASHBOARD_DIR / "static", "main.html")


@app.get("/legacy")
def legacy():
    return send_from_directory(DASHBOARD_DIR / "static", "index.html")


@app.get("/api/a205")
def api_a205():
    return jsonify(build_a205())


@app.post("/api/a205/amounts")
def api_a205_amounts():
    from helpers import save_pm_live_amounts

    data = request.get_json(silent=True) or {}
    try:
        low = float(data.get("low", data.get("live_low", 2.5)))
        mid = float(data.get("mid", data.get("live_mid", 2.5)))
        high = float(data.get("high", data.get("live_high", 2.5)))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "geçersiz tutar"}), 400
    saved = save_pm_live_amounts("a2_05", low, mid, high)
    return jsonify({
        "ok": True,
        "amounts": {"live_low": saved[0], "live_mid": saved[1], "live_high": saved[2]},
    })


@app.get("/api/status")
def api_status():
    return jsonify(build_status())


@app.post("/api/toggle/a2_05_live")
def toggle_live():
    from balance_guard import toggle_group_paused

    result = toggle_group_paused("a2_05_live", source="dashboard")
    return jsonify({"ok": True, "control": result})


@app.post("/api/refresh_signals")
def refresh_signals():
    try:
        import signals as sig_mod

        sig_mod.run()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/redeem")
def api_redeem():
    """Kazanan pozisyonları nakde çevir (Polymarket redeem)."""
    from redeem import redeem_all

    result = redeem_all()
    return jsonify(result), (200 if result.get("ok") else 500)


@app.get("/download/project")
def download_project():
    """Proje arşivi — oturum veya ?t= token ile."""
    if not _download_allowed():
        return redirect(url_for("login"))
    path = ROOT / "exports" / "2.Poly.zip"
    if not path.is_file():
        return jsonify({"ok": False, "error": "arşiv bulunamadı"}), 404
    resp = send_file(
        path,
        as_attachment=True,
        download_name="2.Poly.zip",
        mimetype="application/octet-stream",
        max_age=0,
    )
    resp.headers["Content-Disposition"] = 'attachment; filename="2.Poly.zip"'
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.get("/api/download/project")
def api_download_project():
    """Tarayıcı blob indirmesi için güvenli URL."""
    base = request.host_url.rstrip("/")
    url = f"{base}/download/project?t={_download_token()}"
    return jsonify({"ok": True, "url": url, "filename": "2.Poly.zip"})


def main():
    port = int(os.getenv("POLY2_DASHBOARD_PORT", "5080"))
    host = os.getenv("POLY2_DASHBOARD_HOST", "0.0.0.0")
    print(f"[A2#05 Dashboard] http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
