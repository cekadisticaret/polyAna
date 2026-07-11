"""
PolyMarket Dashboard — bursaapp.com/poly
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template_string, request, session, redirect, url_for

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "temmuzPoly"))

_DIR_POLY = os.path.join(os.path.dirname(__file__), "..", "temmuzPoly")
_TZ_TR    = ZoneInfo("Europe/Istanbul")
_BINANCE  = "https://fapi.binance.com"
_PM_GAMMA = "https://gamma-api.polymarket.com"

app = Flask(__name__)
app.secret_key = "pk_bursaapp_x9f2k7m3"
app.config["SESSION_COOKIE_SECURE"]   = False  # nginx HTTP proxy üzerinden geldiği için
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# nginx reverse proxy arkasında çalışırken URL scheme ve host'u düzelt
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

_USERNAME = "cem"
_PASSWORD = "cem332020"

LOGIN_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Giriş — PolyMarket</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0d0d0d; color:#fff; font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif;
         min-height:100vh; display:flex; align-items:center; justify-content:center; }
  .card { background:#141414; border-radius:24px; padding:40px 32px; width:100%; max-width:360px; }
  .logo { font-size:22px; font-weight:800; color:#c8f135; margin-bottom:8px; }
  .sub  { font-size:13px; color:#555; margin-bottom:32px; }
  label { font-size:12px; color:#555; text-transform:uppercase; letter-spacing:.5px; display:block; margin-bottom:6px; }
  input { width:100%; background:#1c1c1e; border:none; border-radius:12px; padding:14px 16px;
          color:#fff; font-size:15px; margin-bottom:16px; outline:none; }
  input:focus { box-shadow:0 0 0 2px #c8f135; }
  button { width:100%; background:#c8f135; border:none; border-radius:14px; padding:14px;
           color:#111; font-size:15px; font-weight:800; cursor:pointer; margin-top:4px; }
  button:active { transform:scale(.98); }
  .err { background:#450a0a; color:#f87171; border-radius:12px; padding:12px 16px;
         font-size:13px; margin-bottom:16px; display:{% if error %}block{% else %}none{% endif %}; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">PolyMarket</div>
  <div class="sub">Dashboard'a erişmek için giriş yap</div>
  <div class="err">Kullanıcı adı veya şifre hatalı</div>
  <form method="POST">
    <label>Kullanıcı Adı</label>
    <input type="text" name="username" autocomplete="username" autofocus>
    <label>Şifre</label>
    <input type="password" name="password" autocomplete="current-password">
    <button type="submit">Giriş Yap</button>
  </form>
</div>
</body>
</html>"""

# ── Yardımcı fonksiyonlar ──────────────────────────────────────
def _binance(path, params=None):
    qs  = ("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else ""
    req = urllib.request.Request(_BINANCE + path + qs, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)

def get_price(symbol: str) -> float:
    return float(_binance("/fapi/v1/ticker/price", {"symbol": symbol})["price"])

def get_klines(symbol: str, interval="15m", limit=80):
    raw = _binance("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    return [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
             "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in raw]

def load_state(name: str) -> dict:
    path = os.path.join(_DIR_POLY, f"poly_trader_{name}_state.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def save_state(name: str, state: dict):
    path = os.path.join(_DIR_POLY, f"poly_trader_{name}_state.json")
    with open(path, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_pm_balance() -> float:
    try:
        sys.path.insert(0, _DIR_POLY)
        from poly_trader_analiz5 import _pm_get_balance
        return _pm_get_balance()
    except Exception:
        return -1.0

def get_pm_token_price(pm_slug: str, token_dir: str) -> float | None:
    """Polymarket'tan anlık token fiyatını çeker (0-1 arası)."""
    try:
        url = f"{_PM_GAMMA}/events?slug={pm_slug}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.load(r)
        if not data:
            return None
        m = data[0].get("markets", [{}])[0]
        raw = m.get("outcomePrices")
        op  = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if len(op) >= 2:
            return float(op[0]) if token_dir == "UP" else float(op[1])
    except Exception:
        pass
    return None

def collect_positions() -> list:
    """Analiz5'in gerçek Polymarket pozisyonlarını döndürür."""
    state = load_state("analiz5")
    positions = []
    for pos in state.get("open_positions", []):
        # Sadece gerçek Polymarket orderı olanlar
        if not pos.get("pm_slug") or not pos.get("pm_spent"):
            continue
        positions.append({**pos, "_analiz": "analiz5"})
    return positions

def _auth_required():
    return session.get("logged_in") is not True

# ── Login ─────────────────────────────────────────────────────
@app.route("/poly/login", methods=["GET", "POST"])
def login():
    error = False
    if request.method == "POST":
        if (request.form.get("username") == _USERNAME and
                request.form.get("password") == _PASSWORD):
            session["logged_in"] = True
            return redirect("/poly")
        error = True
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/poly/logout")
def logout():
    session.clear()
    return redirect("/poly/login")

# ── API ───────────────────────────────────────────────────────
@app.route("/poly/api/data")
def api_data():
    if _auth_required(): return redirect("/poly/login")
    positions = collect_positions()
    symbols   = list({p["symbol"] for p in positions})

    prices = {}
    for sym in symbols:
        try:
            prices[sym] = get_price(sym)
        except Exception:
            prices[sym] = None

    enriched = []
    total_pos_value = 0.0
    for pos in positions:
        sym      = pos["symbol"]
        current_p = prices.get(sym)
        entry_p  = pos.get("entry_price", 0)
        pred     = pos.get("predicted_dir", "")
        pm_spent = pos.get("pm_spent", 0)
        pm_size  = pos.get("pm_size", 0)
        token_dir = pos.get("pm_token_dir", pred)

        # Anlık yön
        if current_p and entry_p:
            actual  = "UP" if current_p >= entry_p else "DOWN"
            winning = (actual == pred)
            pct     = (current_p - entry_p) / entry_p * 100
        else:
            winning, pct = None, 0.0

        # Polymarket'tan anlık token fiyatı → kapama değeri
        token_price   = get_pm_token_price(pos.get("pm_slug", ""), token_dir)
        close_val     = round(pm_size * token_price, 2) if token_price and pm_size else None
        total_pos_value += close_val if close_val else pm_spent

        enriched.append({
            "analiz":       pos["_analiz"],
            "symbol":       sym,
            "name":         sym.replace("USDT", ""),
            "dir":          pred,
            "dir_tr":       "YÜKSELİR" if pred == "UP" else "DÜŞER",
            "entry":        round(entry_p, 4),
            "current":      round(current_p, 4) if current_p else None,
            "pct":          round(pct, 2),
            "winning":      winning,
            "pm_spent":     round(pm_spent, 2),
            "pm_size":      pm_size,
            "close_val":    close_val,
            "entry_time":   pos.get("entry_time_tr", ""),
            "pm_slug":      pos.get("pm_slug", ""),
        })

    cash      = get_pm_balance()
    portfolio = round(cash + total_pos_value, 2) if cash >= 0 else -1

    return jsonify({
        "cash":      round(cash, 2),
        "portfolio": portfolio,
        "positions": enriched,
        "updated":   datetime.now(_TZ_TR).strftime("%H:%M:%S"),
    })

@app.route("/poly/api/klines/<symbol>")
def api_klines(symbol):
    if _auth_required(): return redirect("/poly/login")
    try:
        data = get_klines(symbol.upper() + "USDT" if not symbol.endswith("USDT") else symbol.upper(),
                          interval="15m", limit=80)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/poly/api/heatmap")
def api_heatmap():
    if _auth_required(): return redirect("/poly/login")
    from collections import defaultdict
    sym_filter = request.args.get("sym", "ALL").upper()
    path = os.path.join(_DIR_POLY, "poly_trader_analiz5_history.json")
    if not os.path.exists(path):
        return jsonify({"cells": []})
    with open(path) as f:
        hist = json.load(f)
    days_tr = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    grid = defaultdict(lambda: {"w": 0, "t": 0})
    for t in hist:
        if sym_filter != "ALL" and t.get("symbol", "").replace("USDT", "") != sym_filter:
            continue
        dow  = t.get("entry_dow")
        hour = t.get("entry_hour_tr")
        if dow is None or hour is None:
            continue
        grid[(dow, hour)]["t"] += 1
        if t.get("win"):
            grid[(dow, hour)]["w"] += 1
    cells = []
    for (dow, hour), v in grid.items():
        wr = round(v["w"] / v["t"] * 100, 1) if v["t"] else 0
        cells.append({"dow": dow, "day": days_tr[dow], "hour": hour, "w": v["w"], "t": v["t"], "wr": wr})
    return jsonify({"cells": cells})

@app.route("/poly/api/symbol_stats")
def api_symbol_stats():
    if _auth_required(): return redirect("/poly/login")
    from collections import defaultdict
    path = os.path.join(_DIR_POLY, "poly_trader_analiz5_history.json")
    if not os.path.exists(path):
        return jsonify({"sym_wr": [], "top_slots": []})
    with open(path) as f:
        hist = json.load(f)

    # Sembol bazlı WR (BTC/ETH/SOL)
    sym_stat = defaultdict(lambda: {"w": 0, "t": 0})
    for t in hist:
        sym = t.get("symbol", "").replace("USDT", "")
        sym_stat[sym]["t"] += 1
        if t.get("win"):
            sym_stat[sym]["w"] += 1
    sym_wr = []
    for sym in ["BTC", "ETH", "SOL"]:
        v = sym_stat.get(sym, {"w": 0, "t": 0})
        wr = round(v["w"] / v["t"] * 100, 1) if v["t"] else 0
        sym_wr.append({"sym": sym, "wr": wr, "w": v["w"], "t": v["t"]})
    sym_wr.sort(key=lambda x: x["wr"], reverse=True)

    # Gün + saat bazlı top 3 (min 3 işlem)
    dh_stat = defaultdict(lambda: {"w": 0, "t": 0})
    for t in hist:
        dow  = t.get("entry_dow")
        hour = t.get("entry_hour_tr")
        if dow is not None and hour is not None:
            dh_stat[(dow, hour)]["t"] += 1
            if t.get("win"):
                dh_stat[(dow, hour)]["w"] += 1
    days = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    combos = [
        {"day": days[dow], "hour": f"{hour:02d}:00",
         "wr": round(v["w"] / v["t"] * 100, 1), "w": v["w"], "t": v["t"]}
        for (dow, hour), v in dh_stat.items() if v["t"] >= 3
    ]
    combos.sort(key=lambda x: (x["wr"], x["t"]), reverse=True)
    return jsonify({"sym_wr": sym_wr, "top_slots": combos[:3]})

@app.route("/poly/api/stats")
def api_stats():
    if _auth_required(): return redirect("/poly/login")
    analyses = {
        "analiz1": "1. Analiz", "analiz2": "2. Analiz",
        "analiz4": "4. Analiz", "analiz5": "5. Analiz",
        "analiz10": "10. Analiz",
    }
    algo_stats = []
    all_history = []

    for key, label in analyses.items():
        path = os.path.join(_DIR_POLY, f"poly_trader_{key}_history.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            hist = json.load(f)
        total = len(hist)
        wins  = sum(1 for t in hist if t.get("win"))
        pnl   = sum(t.get("pnl", 0) for t in hist)
        wr    = round(wins / total * 100, 1) if total else 0
        algo_stats.append({
            "key": key, "label": label,
            "total": total, "wins": wins,
            "wr": wr, "pnl": round(pnl, 2),
        })
        # Son işlemlere analiz adını ekle
        for t in hist[-5:]:
            all_history.append({**t, "_analiz": label})

    # Son 20 işlem (tüm analizlerden karışık, en yeni önce)
    all_history.sort(key=lambda x: x.get("exit_time_tr", ""), reverse=True)
    recent = []
    for t in all_history[:20]:
        sym     = t.get("symbol", "").replace("USDT", "")
        pred    = t.get("predicted_dir", "")
        win     = t.get("win", False)
        spent   = t.get("pm_spent") or t.get("amount", 0)
        pnl_val = t.get("pnl", 0)
        etime   = t.get("exit_time_tr", "")[:16].replace("T", " ")
        recent.append({
            "sym": sym, "dir": pred, "win": win,
            "spent": round(spent, 2) if spent else 0,
            "pnl":   round(pnl_val, 2),
            "time":  etime,
            "analiz": t.get("_analiz", ""),
        })

    algo_stats.sort(key=lambda x: x["wr"], reverse=True)
    return jsonify({"algo_stats": algo_stats, "recent": recent})

def _pm_sell_position(token_id: str, size: float) -> dict:
    """Polymarket'ta token sat (pozisyonu kapat)."""
    import importlib.util
    from decimal import Decimal, ROUND_DOWN

    try:
        spec = importlib.util.spec_from_file_location(
            "a5", os.path.join(_DIR_POLY, "poly_trader_analiz5.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        client = mod._pm_get_client()
    except Exception as e:
        return {"ok": False, "error": f"client init hatası: {e}"}

    try:
        from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
        from py_clob_client_v2.order_builder.constants import SELL

        price = float(client.calculate_market_price(token_id, "SELL", size, OrderType.FAK))
        price = max(0.02, min(0.98, round(price, 2)))
        size  = float(Decimal(str(size)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))

        args   = OrderArgs(token_id=token_id, price=price, size=size, side=SELL)
        signed = client.create_order(args, PartialCreateOrderOptions())
        resp   = client.post_order(signed, order_type=OrderType.FAK)

        print(f"[dashboard] PM sell response: {resp}", flush=True)

        if not resp:
            return {"ok": False, "error": "boş yanıt"}

        # success=True ama status kontrolü — FAK eşleşmeyebilir
        status = resp.get("status", "")
        if resp.get("success") and status not in ("canceled", "unmatched"):
            return {"ok": True, "price": price, "size": size,
                    "received": round(size * price, 2), "status": status}

        return {"ok": False, "error": f"FAK eşleşmedi (status={status})", "resp": str(resp)}

    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.route("/poly/api/close/<analiz>/<symbol>", methods=["POST"])
def api_close(analiz, symbol):
    if _auth_required(): return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        state  = load_state(analiz)
        symbol = symbol.upper()
        pos    = next((p for p in state.get("open_positions", [])
                       if p.get("symbol") == symbol), None)
        if not pos:
            return jsonify({"ok": False, "error": "pozisyon bulunamadı"}), 404

        token_id = pos.get("pm_token_id")
        pm_size  = pos.get("pm_size", 0)

        if not token_id or not pm_size:
            return jsonify({"ok": False, "error": f"token_id veya pm_size eksik ({token_id=}, {pm_size=})"}), 400

        # Gerçek PM satış emri
        sell_result = _pm_sell_position(token_id, pm_size)

        # Sadece PM satışı başarılıysa state'ten kaldır
        if sell_result.get("ok"):
            state["open_positions"] = [
                p for p in state["open_positions"] if p.get("symbol") != symbol
            ]
            save_state(analiz, state)

        return jsonify({
            "ok":    True,
            "sell":  sell_result,
            "symbol": symbol,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ── HTML ──────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PolyMarket Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0d0d0d; color:#fff; font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif; min-height:100vh; overflow-x:hidden; }

  /* ── Desktop layout ── */
  .app { display:flex; min-height:100vh; }

  /* Sol sidebar */
  .sidebar { width:220px; min-height:100vh; background:#111; padding:24px 16px;
             display:flex; flex-direction:column; position:fixed; top:0; left:0; bottom:0; z-index:10; }
  .logo { font-size:17px; font-weight:800; color:#c8f135; margin-bottom:32px; letter-spacing:-.3px; }
  .logo span { color:#fff; font-weight:400; }
  .nav-label { font-size:10px; color:#444; text-transform:uppercase; letter-spacing:.8px; margin:20px 0 8px; }
  .nav-item { display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:12px;
              font-size:13px; font-weight:600; color:#555; cursor:pointer; margin-bottom:2px; text-decoration:none; }
  .nav-item.active { background:#1c1c1e; color:#fff; }
  .nav-item:hover { background:#1c1c1e; color:#aaa; }
  .nav-dot { width:8px; height:8px; border-radius:50%; background:#333; flex-shrink:0; }
  .nav-item.active .nav-dot { background:#c8f135; }
  .sidebar-footer { margin-top:auto; font-size:12px; color:#333; padding:8px 12px; cursor:pointer; }
  .sidebar-footer:hover { color:#555; }

  /* Ana içerik */
  .main { margin-left:220px; flex:1; padding:28px 24px 28px 28px; min-width:0; }
  .right-panel { width:300px; min-height:100vh; background:#111; padding:24px 16px;
                 position:fixed; top:0; right:0; bottom:0; overflow-y:auto; }

  /* Stats kartları */
  .stats-row { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:24px; }
  .stat-card { background:#141414; border-radius:16px; padding:16px 18px; }
  .stat-label { font-size:11px; color:#555; text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px; }
  .stat-val { font-size:24px; font-weight:700; letter-spacing:-.5px; }
  .stat-val.green { color:#a3e635; }
  .stat-val.bright-green { color:#4ade80; }
  .stat-val.up { color:#4ade80; }
  .stat-val.down { color:#f87171; }
  .stat-sub { font-size:12px; color:#777; margin-top:4px; }
  .stat-sub.pos { color:#4ade80; }
  .stat-sub.neg { color:#f87171; }

  /* Grafik */
  .chart-wrap { background:#141414; border-radius:20px; overflow:hidden; margin-bottom:24px; }
  .chart-head { display:flex; align-items:center; justify-content:space-between; padding:16px 18px 0; }
  .chart-title { font-size:15px; font-weight:700; }
  .chart-tabs { display:flex; gap:6px; }
  .chart-tab { padding:5px 12px; border-radius:16px; font-size:12px; font-weight:700;
               cursor:pointer; color:#555; transition:.2s; border:none; background:transparent; }
  .chart-tab.active { background:#c8f135; color:#111; }
  #chart { height:240px; }

  /* Açık pozisyonlar */
  .section-title { font-size:13px; font-weight:700; color:#888; text-transform:uppercase;
                   letter-spacing:.5px; margin-bottom:14px; }
  .positions { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:14px; }
  .pos-card { background:#141414; border-radius:18px; padding:18px; border-left:3px solid #333; }
  .pos-card.winning { border-left-color:#4ade80; }
  .pos-card.losing  { border-left-color:#f87171; }
  .pos-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
  .pos-name { font-size:20px; font-weight:800; }
  .pos-dir  { font-size:12px; font-weight:700; padding:4px 10px; border-radius:10px; }
  .pos-dir.up   { background:#14532d; color:#4ade80; }
  .pos-dir.down { background:#450a0a; color:#f87171; }
  .pos-price-row { display:flex; align-items:baseline; gap:8px; margin:2px 0; }
  .pos-current { font-size:22px; font-weight:700; }
  .pos-pct { font-size:13px; font-weight:600; }
  .pos-pct.pos { color:#4ade80; } .pos-pct.neg { color:#f87171; }
  .pos-entry { font-size:12px; color:#555; margin-bottom:10px; }
  .pos-risk-row { font-size:12px; color:#666; margin-top:8px; }
  .pos-analiz-tag { display:inline-block; background:#1c1c1e; color:#555; font-size:10px;
                    padding:2px 7px; border-radius:6px; margin-left:6px; }
  .close-btn-wrap { display:flex; justify-content:flex-end; margin-top:12px; }
  .close-btn { background:#c8f135; border:none; color:#111; font-size:12px; font-weight:800;
               padding:8px 18px; border-radius:12px; cursor:pointer; white-space:nowrap; transition:.2s; }
  .close-btn:hover { background:#d4ff3a; }
  .close-btn.loading { opacity:.5; pointer-events:none; }
  .empty { color:#333; font-size:14px; padding:32px 0; }

  /* Toplam risk */
  .risk-banner { background:#c8f135; border-radius:16px; padding:14px 18px;
                 display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
  /* Bölüm ayraçları */
  .section-wrap { background:#1f1f1f; border-radius:20px; padding:20px; margin-bottom:24px; }
  .risk-label { font-size:12px; font-weight:700; color:#111; }
  .risk-val   { font-size:18px; font-weight:800; color:#111; }

  /* Sağ panel */
  .rp-section { background:#1f1f1f; border-radius:16px; padding:16px 14px; margin-bottom:14px; }
  .rp-title { font-size:11px; font-weight:700; color:#666; text-transform:uppercase;
              letter-spacing:.6px; margin-bottom:12px; }
  .trade-item { display:flex; justify-content:space-between; align-items:center;
                padding:10px 0; border-bottom:1px solid #1c1c1e; }
  .trade-item:last-child { border:none; }
  .trade-left { display:flex; flex-direction:column; gap:3px; }
  .trade-sym { font-size:13px; font-weight:700; }
  .trade-meta { font-size:11px; color:#777; }
  .trade-pnl { font-size:14px; font-weight:800; }
  .trade-pnl.pos { color:#4ade80; } .trade-pnl.neg { color:#f87171; }

  .algo-item { display:flex; align-items:center; justify-content:space-between;
               padding:8px 0; border-bottom:1px solid #1c1c1e; }
  .algo-item:last-child { border:none; }
  .algo-name { font-size:12px; font-weight:600; color:#ccc; }
  .algo-wr   { font-size:12px; font-weight:700; }
  .algo-bar  { height:4px; background:#1c1c1e; border-radius:4px; margin:0 10px; flex:1; }
  .algo-bar-fill { height:100%; border-radius:4px; background:#c8f135; }

  .dot { width:6px; height:6px; background:#4ade80; border-radius:50%; display:inline-block;
         margin-right:5px; animation:pulse 2s infinite; }
  .updated-bar { font-size:11px; color:#333; margin-top:16px; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  /* Heatmap */
  .hm-filter { background:#1a1a1a; border:none; color:#666; font-size:12px; font-weight:700;
               padding:6px 14px; border-radius:12px; cursor:pointer; transition:.2s; }
  .hm-filter.active { background:#c8f135; color:#111; }
  .hm-table { border-collapse:collapse; min-width:600px; }
  .hm-table th { font-size:10px; color:#555; font-weight:600; padding:4px 6px; text-align:center; }
  .hm-table td { width:38px; height:38px; border-radius:6px; text-align:center; vertical-align:middle;
                 font-size:10px; font-weight:700; cursor:default; position:relative; }
  .hm-table td:hover::after { content:attr(data-tip); position:absolute; bottom:110%; left:50%;
    transform:translateX(-50%); background:#222; color:#fff; padding:4px 8px; border-radius:6px;
    font-size:10px; white-space:nowrap; pointer-events:none; z-index:99; }
  .hm-day { font-size:11px; font-weight:700; color:#888; padding:4px 10px; text-align:right; white-space:nowrap; }

  /* ── Mobile ── */
  @media (max-width: 768px) {
    .sidebar { display:none; }
    .right-panel { display:none; }
    .main { margin-left:0; padding:16px; }
    .stats-row { grid-template-columns:1fr 1fr; gap:10px; }
    .stat-card.hide-mobile { display:none; }
    .stat-val { font-size:20px; }
    .stat-val.green { font-size:34px; }
    .stat-val.bright-green { font-size:34px; }
    .positions { grid-template-columns:1fr; }
    #chart { height:200px; }
    .mobile-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
    .mobile-logo { font-size:16px; font-weight:800; color:#c8f135; }
    .mobile-logout { font-size:12px; color:#555; text-decoration:none; }
  }
  @media (min-width: 769px) {
    .mobile-header { display:none; }
    .main { margin-right:300px; }
  }
</style>
</head>
<body>
<div class="app">

<!-- Sol Sidebar (desktop) -->
<div class="sidebar">
  <div class="logo">Poly<span>Market</span></div>
  <div class="nav-label">Ana Menü</div>
  <a class="nav-item active" id="nav-overview" onclick="showView('overview')" href="#"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item" id="nav-heatmap" onclick="showView('heatmap')" href="#"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="#"><span class="nav-dot"></span>Geçmiş</a>
  <div class="nav-label">Hesap</div>
  <a class="nav-item" href="/poly/logout"><span class="nav-dot"></span>Çıkış</a>
  <div class="sidebar-footer"><span class="dot"></span>Canlı</div>
</div>

<!-- Ana içerik -->
<div class="main">
  <!-- Mobil header -->
  <div class="mobile-header">
    <div class="mobile-logo">PolyMarket</div>
    <a class="mobile-logout" href="/poly/logout">Çıkış</a>
  </div>

  <!-- Stats kartları -->
  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-label">Portfolio</div>
      <div class="stat-val green" id="portfolio">$—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Cash</div>
      <div class="stat-val bright-green" id="cash">$—</div>
    </div>
    <div class="stat-card hide-mobile">
      <div class="stat-label">Kazanma Oranı</div>
      <div class="stat-val" id="wr-stat">—</div>
      <div class="stat-sub" id="wr-sub">—</div>
    </div>
    <div class="stat-card hide-mobile">
      <div class="stat-label">Toplam P&amp;L</div>
      <div class="stat-val" id="pnl-stat">—</div>
    </div>
  </div>

  <!-- Grafik -->
  <div class="chart-wrap">
    <div class="chart-head">
      <div class="chart-title">Grafik</div>
      <div class="chart-tabs" id="chart-tabs"></div>
    </div>
    <div id="chart"></div>
  </div>

  <!-- Toplam risk -->
  <div class="risk-banner">
    <span class="risk-label">Toplam Riskteki</span>
    <span class="risk-val" id="total-risk">$—</span>
  </div>

  <!-- Açık pozisyonlar -->
  <div class="section-wrap">
    <div class="section-title" style="margin-bottom:16px">Açık Pozisyonlar</div>
    <div class="positions" id="positions">
      <div class="empty">Yükleniyor...</div>
    </div>
  </div>

  <div class="updated-bar" style="margin-top:20px"><span class="dot"></span>Her 30 saniyede güncellenir — <span id="updated">—</span></div>
</div><!-- .main overview -->

<!-- Heatmap view -->
<div id="view-heatmap" style="display:none;margin-left:220px;margin-right:300px;padding:28px 24px 28px 28px;min-width:0">
  <div style="font-size:20px;font-weight:800;margin-bottom:6px">Sıcaklık Haritası</div>
  <div style="font-size:13px;color:#555;margin-bottom:24px">5. Analiz — gün × saat kazanma oranı</div>

  <!-- Filtre -->
  <div style="display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap">
    <button class="hm-filter active" data-sym="ALL" onclick="setHmFilter(this,'ALL')">Tümü</button>
    <button class="hm-filter" data-sym="BTC"  onclick="setHmFilter(this,'BTC')">BTC</button>
    <button class="hm-filter" data-sym="ETH"  onclick="setHmFilter(this,'ETH')">ETH</button>
    <button class="hm-filter" data-sym="SOL"  onclick="setHmFilter(this,'SOL')">SOL</button>
  </div>

  <div class="section-wrap" style="overflow-x:auto">
    <div id="heatmap-grid"></div>
  </div>

  <div style="display:flex;gap:24px;margin-top:16px;font-size:12px;color:#555;align-items:center">
    <span>Kazanma oranı:</span>
    <span style="display:flex;align-items:center;gap:6px">
      <span style="width:14px;height:14px;background:#4ade80;border-radius:3px;display:inline-block"></span>≥70%
    </span>
    <span style="display:flex;align-items:center;gap:6px">
      <span style="width:14px;height:14px;background:#a3e635;border-radius:3px;display:inline-block"></span>55–70%
    </span>
    <span style="display:flex;align-items:center;gap:6px">
      <span style="width:14px;height:14px;background:#c8f135;border-radius:3px;display:inline-block"></span>50–55%
    </span>
    <span style="display:flex;align-items:center;gap:6px">
      <span style="width:14px;height:14px;background:#ca8a04;border-radius:3px;display:inline-block"></span>40–50%
    </span>
    <span style="display:flex;align-items:center;gap:6px">
      <span style="width:14px;height:14px;background:#7f1d1d;border-radius:3px;display:inline-block"></span>&lt;40%
    </span>
    <span style="display:flex;align-items:center;gap:6px">
      <span style="width:14px;height:14px;background:#1a1a1a;border-radius:3px;display:inline-block;border:1px solid #333"></span>Veri yok
    </span>
  </div>
</div>

<!-- Sağ Panel (desktop) -->
<div class="right-panel">
  <!-- Sembol WR -->
  <div class="rp-section">
    <div class="rp-title">Sembol Başarı Oranı</div>
    <div id="sym-wr" style="display:flex;gap:8px">
      <div style="color:#666;font-size:13px">Yükleniyor...</div>
    </div>
  </div>

  <!-- En iyi gün/saat -->
  <div class="rp-section">
    <div class="rp-title">En Etkili Zaman</div>
    <div id="top-slots">
      <div style="color:#666;font-size:13px">Yükleniyor...</div>
    </div>
  </div>

  <!-- Son işlemler -->
  <div class="rp-section">
    <div class="rp-title">Son İşlemler</div>
    <div id="recent-trades"><div style="color:#666;font-size:13px">Yükleniyor...</div></div>
  </div>

  <!-- Algoritma performansı -->
  <div class="rp-section">
    <div class="rp-title">Algoritma Performansı</div>
    <div id="algo-stats"><div style="color:#666;font-size:13px">Yükleniyor...</div></div>
  </div>

</div>

</div><!-- .app -->

<script>
let chartInstance = null, seriesInstance = null, currentSym = null;

function initChart(container) {
  if (chartInstance) chartInstance.remove();
  chartInstance = LightweightCharts.createChart(container, {
    width: container.clientWidth, height: 240,
    layout: { background:{color:'#141414'}, textColor:'#666' },
    grid: { vertLines:{color:'#1c1c1e'}, horzLines:{color:'#1c1c1e'} },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    timeScale: { borderColor:'#1c1c1e', timeVisible:true },
    rightPriceScale: { borderColor:'#1c1c1e' },
  });
  seriesInstance = chartInstance.addCandlestickSeries({
    upColor:'#4ade80', downColor:'#f87171',
    borderUpColor:'#4ade80', borderDownColor:'#f87171',
    wickUpColor:'#4ade80', wickDownColor:'#f87171',
  });
}

async function loadChart(sym) {
  currentSym = sym;
  document.querySelectorAll('.chart-tab').forEach(t => t.classList.toggle('active', t.dataset.sym === sym));
  const c = document.getElementById('chart');
  initChart(c);
  try {
    const r = await fetch('/poly/api/klines/' + sym);
    const d = await r.json();
    seriesInstance.setData(d.map(k => ({ time: Math.floor(k.t/1000), open:k.o, high:k.h, low:k.l, close:k.c })));
  } catch(e) { console.error(e); }
}

function buildTabs(syms) {
  const tabs = document.getElementById('chart-tabs');
  tabs.innerHTML = '';
  if (!syms.length) { syms = ['BTC','ETH','SOL']; }
  syms.forEach(sym => {
    const b = document.createElement('button');
    b.className = 'chart-tab' + (sym === currentSym ? ' active' : '');
    b.textContent = sym; b.dataset.sym = sym;
    b.onclick = () => loadChart(sym);
    tabs.appendChild(b);
  });
}

async function closePosition(analiz, symbol, btn) {
  btn.classList.add('loading'); btn.textContent = 'Kapatılıyor...';
  try {
    const r = await fetch('/poly/api/close/' + analiz + '/' + symbol, {method:'POST'});
    const d = await r.json();
    if (!d.ok) {
      btn.textContent = '⚠️ ' + (d.error || 'API hatası');
      btn.style.background = '#f87171'; btn.classList.remove('loading'); return;
    }
    const s = d.sell;
    if (s && s.ok) {
      btn.style.background = '#4ade80';
      btn.textContent = '✅ Kapatıldı · $' + s.received;
      setTimeout(refresh, 2000);
    } else {
      // PM satışı başarısız — pozisyon state'te kaldı
      btn.style.background = '#f87171';
      btn.textContent = '⚠️ PM: ' + (s ? s.error : 'bilinmeyen hata');
      btn.classList.remove('loading');
    }
  } catch(e) { btn.textContent = '⚠️ ' + e.message; btn.classList.remove('loading'); }
}

async function refresh() {
  try {
    const [rd, rs, rss] = await Promise.all([
      fetch('/poly/api/data'), fetch('/poly/api/stats'), fetch('/poly/api/symbol_stats')
    ]);
    const d  = await rd.json();
    const s  = await rs.json();
    const ss = await rss.json();

    // Header stats
    document.getElementById('portfolio').textContent = d.portfolio >= 0 ? '$'+d.portfolio.toFixed(2) : '?';
    document.getElementById('cash').textContent      = d.cash >= 0 ? '$'+d.cash.toFixed(2) : '?';
    document.getElementById('updated').textContent   = d.updated;

    // WR & PnL from analiz5 stats
    const a5 = s.algo_stats.find(a => a.key === 'analiz5');
    if (a5) {
      const wrEl = document.getElementById('wr-stat');
      wrEl.textContent = a5.wr + '%';
      wrEl.className = 'stat-val ' + (a5.wr >= 50 ? 'up' : 'down');
      document.getElementById('wr-sub').textContent = a5.wins + 'W / ' + (a5.total-a5.wins) + 'L';
      const pnlEl = document.getElementById('pnl-stat');
      pnlEl.textContent = (a5.pnl >= 0 ? '+' : '') + '$' + a5.pnl.toFixed(2);
      pnlEl.className = 'stat-val ' + (a5.pnl >= 0 ? 'up' : 'down');
    }

    // Risk banner
    const totalRisk = d.positions.reduce((acc, p) => acc + (p.pm_spent||0), 0);
    document.getElementById('total-risk').textContent = '$' + totalRisk.toFixed(2);

    // Grafik tabları
    const syms = [...new Set(d.positions.map(p => p.name))];
    buildTabs(syms.length ? syms : ['BTC','ETH','SOL']);
    if (!currentSym) loadChart(syms.length ? syms[0] : 'BTC');

    // Pozisyonlar
    const pc = document.getElementById('positions');
    if (!d.positions.length) {
      pc.innerHTML = '<div class="empty">Şu an açık pozisyon yok</div>';
    } else {
      pc.innerHTML = d.positions.map(p => {
        const wc = p.winning===true?'winning':p.winning===false?'losing':'';
        const dc = p.dir==='UP'?'up':'down';
        const pctStr = (p.pct>=0?'+':'') + p.pct.toFixed(2)+'%';
        const time   = p.entry_time ? p.entry_time.substring(11,16)+' İST' : '';
        const cvColor = p.close_val !== null ? (parseFloat(p.close_val)>=parseFloat(p.pm_spent)?'#4ade80':'#f87171') : '#555';
        const cvStr  = p.close_val !== null ? ` <span style="color:${cvColor};font-weight:700">→ $${p.close_val}</span>` : '';
        return `<div class="pos-card ${wc}">
          <div class="pos-top">
            <div class="pos-name">${p.name}</div>
            <div class="pos-dir ${dc}">${p.dir_tr}</div>
          </div>
          <div class="pos-price-row">
            <span class="pos-current">${p.current?'$'+p.current:'—'}</span>
            <span class="pos-pct ${p.pct>=0?'pos':'neg'}">${p.current?pctStr:''}</span>
          </div>
          <div class="pos-entry">Giriş: $${p.entry} · ${time}</div>
          <div class="pos-risk-row">Riskteki: $${p.pm_spent}${cvStr}
            <span class="pos-analiz-tag">${p.analiz}</span>
          </div>
          <div class="close-btn-wrap">
            <button class="close-btn" onclick="closePosition('${p.analiz}','${p.symbol}',this)">Pozisyonu Kapat</button>
          </div>
        </div>`;
      }).join('');
    }

    // Sembol WR kartları
    const symEl = document.getElementById('sym-wr');
    symEl.innerHTML = (ss.sym_wr || []).map(sv => {
      const color = sv.wr >= 55 ? '#4ade80' : sv.wr >= 50 ? '#a3e635' : '#f87171';
      return `<div style="flex:1;background:#1c1c1e;border-radius:12px;padding:10px 8px;text-align:center;">
        <div style="font-size:11px;color:#555;margin-bottom:4px">${sv.sym}</div>
        <div style="font-size:18px;font-weight:800;color:${color}">${sv.wr}%</div>
        <div style="font-size:10px;color:#888">${sv.w}/${sv.t}</div>
      </div>`;
    }).join('') || '<div style="color:#666;font-size:13px">Veri yok</div>';

    // En etkili gün+saat top 3
    const slotEl = document.getElementById('top-slots');
    slotEl.innerHTML = (ss.top_slots || []).map((sl, i) => {
      const medals = ['🥇','🥈','🥉'];
      const barW = Math.round(sl.wr);
      return `<div style="padding:8px 0;border-bottom:1px solid #1c1c1e">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <span style="font-size:12px;font-weight:700">${medals[i]} ${sl.day} ${sl.hour}</span>
          <span style="font-size:13px;font-weight:800;color:#c8f135">${sl.wr}%</span>
        </div>
        <div style="height:3px;background:#1c1c1e;border-radius:3px">
          <div style="height:100%;width:${barW}%;background:#c8f135;border-radius:3px"></div>
        </div>
        <div style="font-size:10px;color:#888;margin-top:3px">${sl.w} kazanç / ${sl.t} işlem</div>
      </div>`;
    }).join('') || '<div style="color:#666;font-size:13px">Veri yok</div>';

    // Son işlemler (sağ panel)
    const rt = document.getElementById('recent-trades');
    rt.innerHTML = s.recent.map(t => {
      const pnlC = t.pnl >= 0 ? 'pos' : 'neg';
      const pnlStr = (t.pnl>=0?'+':'')+'$'+Math.abs(t.pnl).toFixed(2);
      const dirIcon = t.dir==='UP' ? '📈' : '📉';
      return `<div class="trade-item">
        <div class="trade-left">
          <div class="trade-sym">${dirIcon} ${t.sym} <span style="font-size:10px;color:#555">${t.analiz}</span></div>
          <div class="trade-meta" style="color:#777">${t.time} · $${t.spent}</div>
        </div>
        <div class="trade-pnl ${pnlC}">${pnlStr}</div>
      </div>`;
    }).join('') || '<div style="color:#666;font-size:13px">Henüz işlem yok</div>';

    // Algoritma performansı
    const as = document.getElementById('algo-stats');
    as.innerHTML = s.algo_stats.map(a => `
      <div class="algo-item">
        <div class="algo-name">${a.label}</div>
        <div class="algo-bar"><div class="algo-bar-fill" style="width:${a.wr}%"></div></div>
        <div class="algo-wr" style="color:${a.wr>=55?'#4ade80':a.wr>=50?'#a3e635':'#f87171'}">${a.wr}%</div>
      </div>`).join('') || '<div style="color:#666;font-size:13px">Veri yok</div>';

  } catch(e) { console.error(e); }
}

refresh();
setInterval(refresh, 30000);
window.addEventListener('resize', () => {
  if (chartInstance) chartInstance.applyOptions({width: document.getElementById('chart').clientWidth});
});

// ── View yönetimi ──────────────────────────────────────
let _hmData = null;
let _hmSym  = 'ALL';

function showView(v) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.getElementById('nav-' + v)?.classList.add('active');

  const main = document.querySelector('.main');
  const hm   = document.getElementById('view-heatmap');
  const rp   = document.querySelector('.right-panel');

  if (v === 'heatmap') {
    main.style.display = 'none';
    hm.style.display   = 'block';
    rp.style.display   = 'none';
    loadHeatmap();
  } else {
    main.style.display = 'block';
    hm.style.display   = 'none';
    rp.style.display   = 'block';
  }
  return false;
}

function hmColor(wr, t) {
  if (!t) return '#1a1a1a';
  if (wr >= 70) return '#166534';
  if (wr >= 55) return '#14532d';
  if (wr >= 50) return '#365314';
  if (wr >= 40) return '#78350f';
  return '#450a0a';
}
function hmTextColor(wr, t) {
  if (!t) return '#333';
  if (wr >= 55) return '#4ade80';
  if (wr >= 50) return '#c8f135';
  if (wr >= 40) return '#fbbf24';
  return '#f87171';
}

async function loadHeatmap() {
  if (!_hmData) {
    const r = await fetch('/poly/api/heatmap?sym=' + _hmSym);
    _hmData = (await r.json()).cells;
  }
  renderHeatmap(_hmData);
}

function setHmFilter(btn, sym) {
  document.querySelectorAll('.hm-filter').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _hmSym  = sym;
  _hmData = null;
  loadHeatmap();
}

function renderHeatmap(cells) {
  const days  = ['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'];
  const hours = Array.from({length:24}, (_,i) => i);
  const lookup = {};
  cells.forEach(c => { lookup[`${c.dow}_${c.hour}`] = c; });

  let html = '<table class="hm-table"><thead><tr><th></th>';
  hours.forEach(h => { html += `<th>${h.toString().padStart(2,'0')}</th>`; });
  html += '</tr></thead><tbody>';

  days.forEach((day, dow) => {
    html += `<tr><td class="hm-day">${day}</td>`;
    hours.forEach(h => {
      const c  = lookup[`${dow}_${h}`];
      const wr = c ? c.wr : 0;
      const t  = c ? c.t  : 0;
      const bg = hmColor(wr, t);
      const fg = hmTextColor(wr, t);
      const tip = t ? `${day} ${h.toString().padStart(2,'0')}:00 — ${wr}% (${c.w}/${t})` : 'Veri yok';
      const txt = t ? `${wr}%<br><span style="font-size:8px;opacity:.7">${t}</span>` : '';
      html += `<td style="background:${bg};color:${fg};margin:2px;border:2px solid #0d0d0d" data-tip="${tip}">${txt}</td>`;
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById('heatmap-grid').innerHTML = html;
}
</script>
</body>
</html>"""

@app.route("/poly")
@app.route("/poly/")
def dashboard():
    if _auth_required(): return redirect("/poly/login")
    return render_template_string(HTML)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
