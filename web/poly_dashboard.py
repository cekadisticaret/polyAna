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

    # Özet istatistikler
    total   = len(hist_f := [t for t in hist if sym_filter == "ALL" or t.get("symbol","").replace("USDT","") == sym_filter])
    wins    = sum(1 for t in hist_f if t.get("win"))
    pnl     = round(sum(t.get("pnl", 0) for t in hist_f), 2)
    spent   = round(sum(t.get("pm_spent") or t.get("amount", 0) for t in hist_f), 2)
    wr_all  = round(wins / total * 100, 1) if total else 0

    # Sembol kırılımı (ALL modunda)
    sym_breakdown = []
    if sym_filter == "ALL":
        for s in ["BTC", "ETH", "SOL"]:
            sub  = [t for t in hist if t.get("symbol","").replace("USDT","") == s]
            sw   = sum(1 for t in sub if t.get("win"))
            spnl = round(sum(t.get("pnl",0) for t in sub), 2)
            ssp  = round(sum(t.get("pm_spent") or t.get("amount",0) for t in sub), 2)
            swr  = round(sw/len(sub)*100,1) if sub else 0
            sym_breakdown.append({"sym":s,"t":len(sub),"w":sw,"wr":swr,"pnl":spnl,"spent":ssp})

    return jsonify({
        "cells": cells,
        "summary": {"total": total, "wins": wins, "losses": total-wins,
                    "wr": wr_all, "pnl": pnl, "spent": spent},
        "sym_breakdown": sym_breakdown,
    })

@app.route("/poly/api/heatmap/detail")
def api_heatmap_detail():
    if _auth_required(): return redirect("/poly/login")
    days_tr = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    try:
        dow  = int(request.args.get("dow", -1))
        hour = int(request.args.get("hour", -1))
        sym  = request.args.get("sym", "ALL").upper()
    except ValueError:
        return jsonify({"error": "bad params"}), 400

    path = os.path.join(_DIR_POLY, "poly_trader_analiz5_history.json")
    if not os.path.exists(path):
        return jsonify({"trades": []})
    with open(path) as f:
        hist = json.load(f)

    trades = []
    for t in hist:
        if t.get("entry_dow") != dow or t.get("entry_hour_tr") != hour:
            continue
        s = t.get("symbol", "").replace("USDT", "")
        if sym != "ALL" and s != sym:
            continue
        trades.append({
            "sym":   s,
            "dir":   t.get("predicted_dir", ""),
            "win":   t.get("win"),
            "spent": round(t.get("pm_spent") or t.get("amount", 0), 2),
            "pnl":   round(t.get("pnl", 0), 2),
            "entry": t.get("entry_price", 0),
            "exit":  t.get("exit_price", 0),
            "time":  (t.get("entry_time_tr") or "")[:16].replace("T", " "),
        })

    total  = len(trades)
    wins   = sum(1 for t in trades if t["win"])
    pnl    = round(sum(t["pnl"] for t in trades), 2)
    spent  = round(sum(t["spent"] for t in trades), 2)
    return jsonify({
        "dow": dow, "hour": hour,
        "day_name": days_tr[dow] if 0 <= dow <= 6 else "?",
        "total": total, "wins": wins, "losses": total - wins,
        "wr": round(wins / total * 100, 1) if total else 0,
        "pnl": pnl, "spent": spent,
        "trades": trades,
    })

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
AYARLAR_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ayarlar — PolyMarket</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0d0d0d; color:#fff; font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif; min-height:100vh; }
  .app { display:flex; min-height:100vh; }
  .sidebar { width:220px; background:#0a0f0a; padding:24px 16px; display:flex; flex-direction:column;
             position:fixed; top:0; left:0; bottom:0; z-index:10; border-right:1px solid #1a2a1a; }
  .logo { font-size:17px; font-weight:800; color:#c8f135; margin-bottom:32px; }
  .logo span { color:#fff; font-weight:400; }
  .nav-label { font-size:10px; color:#444; text-transform:uppercase; letter-spacing:.8px; margin:20px 0 8px; }
  .nav-item { display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:12px;
              font-size:13px; font-weight:600; color:#555; cursor:pointer; margin-bottom:2px; text-decoration:none; }
  .nav-item.active { background:#1c1c1e; color:#fff; }
  .nav-item:hover { background:#1c1c1e; color:#aaa; }
  .nav-dot { width:8px; height:8px; border-radius:50%; background:#333; flex-shrink:0; }
  .nav-item.active .nav-dot { background:#c8f135; }
  .sidebar-footer { margin-top:auto; font-size:12px; color:#333; padding:8px 12px; }
  .dot { width:6px; height:6px; background:#4ade80; border-radius:50%; display:inline-block; margin-right:5px; animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  .main { margin-left:220px; padding:36px 40px; max-width:700px; }
  .page-title { font-size:22px; font-weight:800; margin-bottom:6px; }
  .page-sub { font-size:13px; color:#666; margin-bottom:32px; }

  .settings-card { background:#1a1a1a; border-radius:20px; padding:28px; margin-bottom:20px; }
  .settings-card h3 { font-size:13px; font-weight:700; color:#888; text-transform:uppercase;
                      letter-spacing:.5px; margin-bottom:20px; }
  .setting-row { display:flex; align-items:center; justify-content:space-between;
                 padding:14px 0; border-bottom:1px solid #222; }
  .setting-row:last-child { border:none; padding-bottom:0; }
  .setting-left { flex:1; }
  .setting-label { font-size:14px; font-weight:600; color:#ddd; margin-bottom:3px; }
  .setting-desc  { font-size:12px; color:#555; }
  .setting-right { display:flex; align-items:center; gap:12px; }
  .setting-unit  { font-size:13px; color:#666; min-width:16px; }
  .setting-input { background:#111; border:1.5px solid #2a2a2a; border-radius:10px;
                   color:#fff; font-size:16px; font-weight:700; width:80px; text-align:center;
                   padding:8px 10px; outline:none; transition:.2s; }
  .setting-input:focus { border-color:#c8f135; }
  .setting-val   { font-size:20px; font-weight:800; color:#c8f135; min-width:60px; text-align:right; }

  .save-btn { background:#c8f135; border:none; color:#111; font-size:14px; font-weight:800;
              padding:14px 32px; border-radius:14px; cursor:pointer; transition:.2s;
              margin-top:8px; width:100%; }
  .save-btn:hover { background:#d4ff3a; }
  .save-btn:active { transform:scale(.98); }
  .save-btn.loading { opacity:.5; pointer-events:none; }

  .toast { position:fixed; bottom:24px; left:50%; transform:translateX(-50%);
           background:#1a1a1a; border:1px solid #333; color:#fff; padding:12px 24px;
           border-radius:14px; font-size:13px; font-weight:600; opacity:0;
           transition:opacity .3s; pointer-events:none; }
  .toast.show { opacity:1; }
</style>
</head>
<body>
<div class="app">
<div class="sidebar">
  <div class="logo">Poly<span>Market</span></div>
  <div class="nav-label">Ana Menü</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="#"><span class="nav-dot"></span>Geçmiş</a>
  <div class="nav-label">Hesap</div>
  <a class="nav-item active" href="/ayarlar"><span class="nav-dot"></span>Ayarlar</a>
  <a class="nav-item" href="/poly/logout"><span class="nav-dot"></span>Çıkış</a>
  <div class="sidebar-footer"><span class="dot"></span>Canlı</div>
</div>

<div class="main">
  <div class="page-title">Ayarlar</div>
  <div class="page-sub">5. Analiz — işlem miktarları anlık güncellenir, bir sonraki saatte devreye girer</div>

  <div class="settings-card">
    <h3>İşlem Miktarları</h3>

    <div class="setting-row">
      <div class="setting-left">
        <div class="setting-label">A9 + A5 Aynı Yön</div>
        <div class="setting-desc">İki sistem hemfikir olduğunda açılan işlem miktarı</div>
      </div>
      <div class="setting-right">
        <span class="setting-unit">$</span>
        <input class="setting-input" id="amount_agree" type="number" step="0.5" min="1" max="100">
      </div>
    </div>

    <div class="setting-row">
      <div class="setting-left">
        <div class="setting-label">A9 Sessiz — A5 Var</div>
        <div class="setting-desc">Sadece A5 sinyal ürettiğinde açılan işlem miktarı</div>
      </div>
      <div class="setting-right">
        <span class="setting-unit">$</span>
        <input class="setting-input" id="amount_a5_only" type="number" step="0.5" min="1" max="100">
      </div>
    </div>

    <div class="setting-row">
      <div class="setting-left">
        <div class="setting-label">A9 Var — A5 Sessiz</div>
        <div class="setting-desc">Sadece A9 sinyal ürettiğinde açılan işlem miktarı</div>
      </div>
      <div class="setting-right">
        <span class="setting-unit">$</span>
        <input class="setting-input" id="amount_a9_only" type="number" step="0.5" min="1" max="100">
      </div>
    </div>
  </div>

  <div class="settings-card">
    <h3>ETH Ayarları</h3>
    <div class="setting-row">
      <div class="setting-left">
        <div class="setting-label">ETH Çarpanı</div>
        <div class="setting-desc">ETH işlemlerine uygulanır (ör: 0.7 → A9+A5 hemfikirde $15 × 0.7 = $10.50)</div>
      </div>
      <div class="setting-right">
        <span class="setting-unit">×</span>
        <input class="setting-input" id="eth_multiplier" type="number" step="0.05" min="0.1" max="1">
      </div>
    </div>
  </div>

  <button class="save-btn" id="save-btn" onclick="save()">Kaydet</button>
</div>
</div>

<div class="toast" id="toast"></div>

<script>
async function load() {
  const r = await fetch('/poly/api/settings');
  const d = await r.json();
  document.getElementById('amount_agree').value   = d.amount_agree;
  document.getElementById('amount_a5_only').value = d.amount_a5_only;
  document.getElementById('amount_a9_only').value = d.amount_a9_only;
  document.getElementById('eth_multiplier').value = d.eth_multiplier;
}

async function save() {
  const btn = document.getElementById('save-btn');
  btn.classList.add('loading'); btn.textContent = 'Kaydediliyor...';
  const body = {
    amount_agree:    parseFloat(document.getElementById('amount_agree').value),
    amount_a5_only:  parseFloat(document.getElementById('amount_a5_only').value),
    amount_a9_only:  parseFloat(document.getElementById('amount_a9_only').value),
    eth_multiplier:  parseFloat(document.getElementById('eth_multiplier').value),
  };
  const r = await fetch('/poly/api/settings', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(body),
  });
  const d = await r.json();
  btn.classList.remove('loading'); btn.textContent = 'Kaydet';
  showToast(d.ok ? '✅ Ayarlar kaydedildi' : '⚠️ Hata oluştu');
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

load();
</script>
</body>
</html>"""

HARITA_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sıcaklık Haritası — PolyMarket</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0d0d0d; color:#fff; font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif; min-height:100vh; }
  .app { display:flex; min-height:100vh; }
  .sidebar { width:220px; background:#0a0f0a; padding:24px 16px; display:flex; flex-direction:column;
             position:fixed; top:0; left:0; bottom:0; z-index:10; border-right:1px solid #1a2a1a; }
  .logo { font-size:17px; font-weight:800; color:#c8f135; margin-bottom:32px; }
  .logo span { color:#fff; font-weight:400; }
  .nav-label { font-size:10px; color:#444; text-transform:uppercase; letter-spacing:.8px; margin:20px 0 8px; }
  .nav-item { display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:12px;
              font-size:13px; font-weight:600; color:#555; cursor:pointer; margin-bottom:2px; text-decoration:none; }
  .nav-item.active { background:#1c1c1e; color:#fff; }
  .nav-item:hover { background:#1c1c1e; color:#aaa; }
  .nav-dot { width:8px; height:8px; border-radius:50%; background:#333; flex-shrink:0; }
  .nav-item.active .nav-dot { background:#c8f135; }
  .sidebar-footer { margin-top:auto; font-size:12px; color:#333; padding:8px 12px; }
  .dot { width:6px; height:6px; background:#4ade80; border-radius:50%; display:inline-block;
         margin-right:5px; animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  .main { margin-left:220px; flex:1; padding:28px 32px; }
  .page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; flex-wrap:wrap; gap:10px; }
  .page-title { font-size:22px; font-weight:800; }
  .page-sub { font-size:13px; color:#666; margin-bottom:20px; }

  .hm-filter { background:#1a1a1a; border:none; color:#666; font-size:12px; font-weight:700;
               padding:6px 14px; border-radius:12px; cursor:pointer; transition:.2s; }
  .hm-filter.active { background:#c8f135; color:#111; }

  .section-wrap { background:#1f1f1f; border-radius:20px; padding:20px; margin-bottom:16px; }
  .stat-label { font-size:10px; color:#666; text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }

  .hm-table { border-collapse:separate; border-spacing:3px; width:100%; }
  .hm-table th { font-size:10px; color:#666; font-weight:600; padding:3px 2px; text-align:center; }
  .hm-table td { width:44px; height:44px; border-radius:7px; text-align:center; vertical-align:middle;
                 font-size:10px; font-weight:700; cursor:default; position:relative; }
  .hm-table td:hover::after { content:attr(data-tip); position:absolute; bottom:110%; left:50%;
    transform:translateX(-50%); background:#222; color:#fff; padding:5px 10px; border-radius:8px;
    font-size:11px; white-space:nowrap; pointer-events:none; z-index:99; border:1px solid #333; }
  .hm-day { font-size:11px; font-weight:700; color:#888; padding:4px 12px 4px 0; text-align:right; white-space:nowrap; }
</style>
</head>
<body>
<div class="app">
<div class="sidebar">
  <div class="logo">Poly<span>Market</span></div>
  <div class="nav-label">Ana Menü</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item active" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="#"><span class="nav-dot"></span>Geçmiş</a>
  <div class="nav-label">Hesap</div>
  <a class="nav-item" href="/ayarlar"><span class="nav-dot"></span>Ayarlar</a>
  <a class="nav-item" href="/poly/logout"><span class="nav-dot"></span>Çıkış</a>
  <div class="sidebar-footer"><span class="dot"></span>Canlı</div>
</div>

<div class="main">
  <div class="page-header">
    <div class="page-title">Sıcaklık Haritası</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="hm-filter active" onclick="setFilter(this,'ALL')">Tümü</button>
      <button class="hm-filter" onclick="setFilter(this,'BTC')">BTC</button>
      <button class="hm-filter" onclick="setFilter(this,'ETH')">ETH</button>
      <button class="hm-filter" onclick="setFilter(this,'SOL')">SOL</button>
    </div>
  </div>
  <div class="page-sub">5. Analiz — gün × saat kazanma oranı</div>

  <div id="hm-top" style="display:grid;grid-template-columns:200px 1fr;gap:14px;margin-bottom:16px;align-items:start">
    <div id="hm-summary" style="display:flex;flex-direction:column;gap:12px"></div>
    <div id="hm-breakdown"></div>
  </div>

  <div class="section-wrap" style="overflow-x:auto;padding:20px 16px">
    <div id="heatmap-grid" style="min-width:700px"></div>
  </div>

  <div style="display:flex;gap:20px;margin-top:14px;font-size:12px;color:#555;flex-wrap:wrap;align-items:center">
    <span>Kazanma oranı:</span>
    <span style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;background:#166534;border-radius:3px;display:inline-block"></span>≥70%</span>
    <span style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;background:#14532d;border-radius:3px;display:inline-block"></span>55–70%</span>
    <span style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;background:#365314;border-radius:3px;display:inline-block"></span>50–55%</span>
    <span style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;background:#78350f;border-radius:3px;display:inline-block"></span>40–50%</span>
    <span style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;background:#450a0a;border-radius:3px;display:inline-block"></span>&lt;40%</span>
    <span style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;background:#1a1a1a;border-radius:3px;display:inline-block;border:1px solid #333"></span>Veri yok</span>
  </div>
</div>
</div>

<!-- Popup Modal -->
<div id="popup-overlay" onclick="closePopup()" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;backdrop-filter:blur(4px)"></div>
<div id="popup" style="display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
  z-index:101;background:#141414;border:1px solid #2a2a2a;border-radius:20px;
  padding:28px;min-width:360px;max-width:560px;width:90%;max-height:80vh;overflow-y:auto">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <div id="popup-title" style="font-size:17px;font-weight:800"></div>
    <button onclick="closePopup()" style="background:none;border:none;color:#555;font-size:20px;cursor:pointer;padding:4px 8px">✕</button>
  </div>
  <div id="popup-summary" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px"></div>
  <div id="popup-trades"></div>
</div>

<script>
let _data = null, _sym = 'ALL';

function hmColor(wr,t){ if(!t)return'#1a1a1a'; if(wr>=70)return'#166534'; if(wr>=55)return'#14532d'; if(wr>=50)return'#365314'; if(wr>=40)return'#78350f'; return'#450a0a'; }
function hmTxt(wr,t){ if(!t)return'#333'; if(wr>=55)return'#4ade80'; if(wr>=50)return'#c8f135'; if(wr>=40)return'#fbbf24'; return'#f87171'; }

async function load() {
  const r = await fetch('/poly/api/heatmap?sym=' + _sym);
  const d = await r.json();
  _data   = d.cells;
  renderSummary(d.summary, d.sym_breakdown || []);
  renderGrid(_data);
}

function setFilter(btn, sym) {
  document.querySelectorAll('.hm-filter').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _sym = sym; _data = null;
  load();
}

function renderSummary(s, bd) {
  const pc = s.pnl>=0?'#4ade80':'#f87171';
  const wc = s.wr>=55?'#4ade80':s.wr>=50?'#a3e635':'#f87171';
  document.getElementById('hm-summary').innerHTML = `
    <div class="section-wrap" style="margin:0;padding:14px 16px">
      <div style="display:flex;flex-direction:column;gap:14px">
        <div>
          <div style="font-size:10px;color:#666;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">Toplam İşlem</div>
          <div style="font-size:22px;font-weight:800;line-height:1">${s.total}</div>
          <div style="font-size:11px;color:#666;margin-top:2px">${s.wins}K / ${s.losses}K</div>
        </div>
        <div style="border-top:1px solid #2a2a2a;padding-top:14px">
          <div style="font-size:10px;color:#666;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">Kazanma Oranı</div>
          <div style="font-size:22px;font-weight:800;color:${wc};line-height:1">${s.wr}%</div>
          <div style="font-size:11px;color:#666;margin-top:2px">${s.wins}W · ${s.losses}L</div>
        </div>
        <div style="border-top:1px solid #2a2a2a;padding-top:14px">
          <div style="font-size:10px;color:#666;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">Net Kazanç</div>
          <div style="font-size:22px;font-weight:800;color:${pc};line-height:1">${s.pnl>=0?'+':''}$${s.pnl.toFixed(2)}</div>
          <div style="font-size:11px;color:#666;margin-top:2px">Yatırılan: $${s.spent.toFixed(2)}</div>
        </div>
      </div>
    </div>`;
  const bdEl = document.getElementById('hm-breakdown');
  if (!bd.length) { bdEl.innerHTML=''; return; }
  bdEl.innerHTML = `<div class="section-wrap" style="margin:0;overflow-x:auto;padding:0">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="color:#555;font-size:11px;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #2a2a2a">
        <th style="text-align:left;padding:12px 16px">Sembol</th>
        <th style="text-align:center;padding:12px 10px">İşlem</th>
        <th style="text-align:center;padding:12px 10px">Kazanma</th>
        <th style="text-align:center;padding:12px 10px">W / L</th>
        <th style="text-align:right;padding:12px 10px">Risk</th>
        <th style="text-align:right;padding:12px 16px">P&L</th>
      </tr></thead><tbody>
      ${bd.map((b,i) => {
        const pc=b.pnl>=0?'#4ade80':'#f87171'; const wc=b.wr>=55?'#4ade80':b.wr>=50?'#a3e635':'#f87171';
        return `<tr style="${i>0?'border-top:1px solid #1e1e1e':''}">
          <td style="padding:14px 16px;font-weight:800;font-size:16px">${b.sym}</td>
          <td style="text-align:center;padding:14px 10px;color:#aaa">${b.t}</td>
          <td style="text-align:center;padding:14px 10px;font-weight:700;color:${wc}">${b.wr}%</td>
          <td style="text-align:center;padding:14px 10px;color:#666">${b.w}W·${b.t-b.w}L</td>
          <td style="text-align:right;padding:14px 10px;color:#666">$${b.spent.toFixed(0)}</td>
          <td style="text-align:right;padding:14px 16px;font-weight:700;color:${pc}">${b.pnl>=0?'+':''}$${b.pnl.toFixed(2)}</td>
        </tr>`;}).join('')}
      </tbody>
    </table></div>`;
}

function renderGrid(cells) {
  const days=['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'];
  const hours=Array.from({length:24},(_,i)=>i);
  const lk={};
  cells.forEach(c=>{lk[`${c.dow}_${c.hour}`]=c;});
  let h='<table class="hm-table"><thead><tr><th></th>';
  hours.forEach(hr=>{h+=`<th>${hr.toString().padStart(2,'0')}</th>`;});
  h+='</tr></thead><tbody>';
  days.forEach((day,dow)=>{
    h+=`<tr><td class="hm-day">${day}</td>`;
    hours.forEach(hr=>{
      const c=lk[`${dow}_${hr}`]; const wr=c?c.wr:0; const t=c?c.t:0;
      const tip=t?`${day} ${hr.toString().padStart(2,'0')}:00 — ${wr}% (${c.w}/${t})`:'Veri yok';
      const txt=t?`${wr}%<br><span style="font-size:8px;opacity:.7">${t}</span>`:'';
      const clickable = t ? `onclick="openPopup(${dow},${hr})" style="cursor:pointer;` : 'style="';
      h+=`<td ${clickable}background:${hmColor(wr,t)};color:${hmTxt(wr,t)};border:2px solid #0d0d0d" data-tip="${tip}">${txt}</td>`;
    });
    h+='</tr>';
  });
  h+='</tbody></table>';
  document.getElementById('heatmap-grid').innerHTML=h;
}

async function openPopup(dow, hour) {
  const days=['Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi','Pazar'];
  document.getElementById('popup-title').textContent = `${days[dow]} ${String(hour).padStart(2,'0')}:00 — ${String(hour).padStart(2,'0')}:00 işlemleri`;
  document.getElementById('popup-summary').innerHTML = '<div style="color:#555;font-size:13px;grid-column:span 3">Yükleniyor...</div>';
  document.getElementById('popup-trades').innerHTML = '';
  document.getElementById('popup-overlay').style.display = 'block';
  document.getElementById('popup').style.display = 'block';

  const r = await fetch(`/poly/api/heatmap/detail?dow=${dow}&hour=${hour}&sym=${_sym}`);
  const d = await r.json();

  const pc = d.pnl >= 0 ? '#4ade80' : '#f87171';
  const wc = d.wr >= 55 ? '#4ade80' : d.wr >= 50 ? '#a3e635' : '#f87171';
  const totalReturn = (d.spent + d.pnl).toFixed(2);
  document.getElementById('popup-summary').innerHTML = `
    <div style="background:#1a1a1a;border-radius:12px;padding:12px;text-align:center">
      <div style="font-size:10px;color:#555;text-transform:uppercase;margin-bottom:4px">İşlem</div>
      <div style="font-size:22px;font-weight:800">${d.total}</div>
      <div style="font-size:11px;color:#666">${d.wins}W / ${d.losses}L</div>
    </div>
    <div style="background:#1a1a1a;border-radius:12px;padding:12px;text-align:center">
      <div style="font-size:10px;color:#555;text-transform:uppercase;margin-bottom:4px">Kazanma</div>
      <div style="font-size:22px;font-weight:800;color:${wc}">${d.wr}%</div>
      <div style="font-size:11px;color:#666">Yatırılan: $${d.spent.toFixed(2)}</div>
    </div>
    <div style="background:#1a1a1a;border-radius:12px;padding:12px;text-align:center">
      <div style="font-size:10px;color:#555;text-transform:uppercase;margin-bottom:4px">Net Kazanç</div>
      <div style="font-size:22px;font-weight:800;color:${pc}">${d.pnl>=0?'+':''}$${d.pnl.toFixed(2)}</div>
      <div style="font-size:11px;color:#666">Toplam alınan: $${totalReturn}</div>
    </div>`;

  if (!d.trades.length) {
    document.getElementById('popup-trades').innerHTML = '<div style="color:#555;font-size:13px;padding:16px 0">Bu saatte işlem yok</div>';
    return;
  }

  document.getElementById('popup-trades').innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="color:#555;font-size:11px;text-transform:uppercase;border-bottom:1px solid #2a2a2a">
        <th style="text-align:left;padding:8px 0">Sembol</th>
        <th style="text-align:center;padding:8px 4px">Yön</th>
        <th style="text-align:center;padding:8px 4px">Sonuç</th>
        <th style="text-align:right;padding:8px 4px">Risk</th>
        <th style="text-align:right;padding:8px 0">P&L</th>
        <th style="text-align:right;padding:8px 0 8px 8px">Tarih</th>
      </tr></thead>
      <tbody>
      ${d.trades.map((t,i) => {
        const pc = t.pnl >= 0 ? '#4ade80' : '#f87171';
        const icon = t.win === true ? '✅' : t.win === false ? '❌' : '⏳';
        const dir = t.dir === 'UP' ? '📈' : '📉';
        return `<tr style="${i>0?'border-top:1px solid #1e1e1e':''}">
          <td style="padding:10px 0;font-weight:700;font-size:14px">${t.sym}</td>
          <td style="text-align:center;padding:10px 4px">${dir}</td>
          <td style="text-align:center;padding:10px 4px">${icon}</td>
          <td style="text-align:right;padding:10px 4px;color:#777">$${t.spent}</td>
          <td style="text-align:right;padding:10px 4px;font-weight:700;color:${pc}">${t.pnl>=0?'+':''}$${t.pnl.toFixed(2)}</td>
          <td style="text-align:right;padding:10px 0 10px 8px;color:#555;font-size:11px">${t.time}</td>
        </tr>`;
      }).join('')}
      </tbody>
    </table>`;
}

function closePopup() {
  document.getElementById('popup-overlay').style.display = 'none';
  document.getElementById('popup').style.display = 'none';
}
document.addEventListener('keydown', e => { if(e.key==='Escape') closePopup(); });

load();
</script>
</body>
</html>"""

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
  .sidebar { width:220px; min-height:100vh; background:#0a0f0a; padding:24px 16px;
             display:flex; flex-direction:column; position:fixed; top:0; left:0; bottom:0; z-index:10;
             border-right:1px solid #1a2a1a; }
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

  /* Overview 2-sütun grid */
  .overview-grid { display:grid; grid-template-columns:1fr 340px; gap:20px; align-items:start; }
  .overview-left  { min-width:0; }
  .overview-right { min-width:0; }

  /* Stats kartları */
  .stats-row { display:grid; gap:14px; margin-bottom:14px; }
  .top-stats    { grid-template-columns:1fr 1fr; }
  .bottom-stats { grid-template-columns:1fr 1fr; }
  .stat-card { background:#141414; border-radius:16px; padding:16px 18px; }
  .stat-label { font-size:11px; color:#555; text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px; }
  .stat-val { font-size:24px; font-weight:700; letter-spacing:-.5px; }
  .stat-val.green { color:#a3e635; font-size:32px; font-weight:800; }
  .stat-val.bright-green { color:#4ade80; font-size:32px; font-weight:800; }
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
  .positions { display:flex; flex-direction:column; gap:12px; }
  .pos-card { background:#141414; border-radius:18px; padding:18px; border-left:4px solid #333; }
  .pos-card.dir-up   { border-left-color:#4ade80; }
  .pos-card.dir-down { border-left-color:#f87171; }
  .pos-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
  .pos-name { font-size:20px; font-weight:800; color:#fff; }
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
  .hm-table { border-collapse:separate; border-spacing:3px; width:100%; }
  .hm-table th { font-size:10px; color:#666; font-weight:600; padding:3px 2px; text-align:center; }
  .hm-table td { width:44px; height:44px; border-radius:7px; text-align:center; vertical-align:middle;
                 font-size:10px; font-weight:700; cursor:default; position:relative; }
  .hm-table td:hover::after { content:attr(data-tip); position:absolute; bottom:110%; left:50%;
    transform:translateX(-50%); background:#222; color:#fff; padding:5px 10px; border-radius:8px;
    font-size:11px; white-space:nowrap; pointer-events:none; z-index:99; border:1px solid #333; }
  .hm-day { font-size:11px; font-weight:700; color:#888; padding:4px 12px 4px 0; text-align:right; white-space:nowrap; }

  /* ── Mobile ── */
  @media (max-width: 768px) {
    .sidebar { display:none; }
    .right-panel { display:none; }
    .main { margin-left:0; padding:16px; }
    .overview-grid { grid-template-columns:1fr; }
    .overview-right { display:none; }
    .top-stats { grid-template-columns:1fr 1fr; }
    .bottom-stats { display:none; }
    .stat-val { font-size:20px; }
    .stat-val.green { font-size:34px; }
    .stat-val.bright-green { font-size:34px; }
    #chart { height:200px; }
    .mobile-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
    .mobile-logo { font-size:16px; font-weight:800; color:#c8f135; }
    .mobile-logout { font-size:12px; color:#555; text-decoration:none; }

    /* Mobilde pozisyonlar ana içerik altına gelsin */
    .mobile-positions { display:block; margin-top:16px; }
  }
  @media (min-width: 769px) {
    .mobile-header { display:none; }
    .main { margin-right:300px; }
    .mobile-positions { display:none; }
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
  <a class="nav-item" id="nav-heatmap" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="#"><span class="nav-dot"></span>Geçmiş</a>
  <div class="nav-label">Hesap</div>
  <a class="nav-item" href="/ayarlar"><span class="nav-dot"></span>Ayarlar</a>
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

  <!-- Desktop: 2 sütun | Mobil: tek sütun -->
  <div class="overview-grid">

    <!-- SOL: stats + grafik -->
    <div class="overview-left">
      <!-- Üst 2 kart: Portfolio + Cash -->
      <div class="stats-row top-stats">
        <div class="stat-card">
          <div class="stat-label">Portfolio</div>
          <div class="stat-val green" id="portfolio">$—</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Cash</div>
          <div class="stat-val bright-green" id="cash">$—</div>
        </div>
      </div>
      <!-- Alt 2 kart: WR + PnL -->
      <div class="stats-row bottom-stats">
        <div class="stat-card">
          <div class="stat-label">Kazanma Oranı</div>
          <div class="stat-val" id="wr-stat">—</div>
          <div class="stat-sub" id="wr-sub">—</div>
        </div>
        <div class="stat-card">
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

      <div class="updated-bar"><span class="dot"></span>Her 30 saniyede güncellenir — <span id="updated">—</span></div>

      <!-- Mobil pozisyonlar (desktop'ta gizli) -->
      <div class="mobile-positions">
        <div class="risk-banner" style="margin-top:16px">
          <span class="risk-label">Toplam Riskteki</span>
          <span class="risk-val" id="total-risk-mob">$—</span>
        </div>
        <div class="section-title" style="margin:16px 0 12px">Açık Pozisyonlar</div>
        <div class="positions" id="positions-mob">
          <div class="empty">Yükleniyor...</div>
        </div>
      </div>
    </div>

    <!-- SAĞ: risk + açık pozisyonlar -->
    <div class="overview-right">
      <div class="risk-banner">
        <div>
          <span class="risk-label">Toplam Riskteki</span>
          <div style="font-size:11px;color:#5a6e00;margin-top:2px">Kazanılacak: <span id="total-towin">$—</span></div>
        </div>
        <span class="risk-val" id="total-risk">$—</span>
      </div>
      <div class="section-title" style="margin-bottom:12px">Açık Pozisyonlar</div>
      <div class="positions" id="positions">
        <div class="empty">Yükleniyor...</div>
      </div>
    </div>

  </div><!-- .overview-grid -->
</div><!-- .main overview -->

<!-- Heatmap view -->
<div id="view-heatmap" style="display:none;margin-left:220px;margin-right:300px;padding:28px 24px 28px 28px;min-width:0">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;flex-wrap:wrap;gap:10px">
    <div style="font-size:20px;font-weight:800">Sıcaklık Haritası</div>
    <!-- Filtre -->
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="hm-filter active" data-sym="ALL" onclick="setHmFilter(this,'ALL')">Tümü</button>
      <button class="hm-filter" data-sym="BTC"  onclick="setHmFilter(this,'BTC')">BTC</button>
      <button class="hm-filter" data-sym="ETH"  onclick="setHmFilter(this,'ETH')">ETH</button>
      <button class="hm-filter" data-sym="SOL"  onclick="setHmFilter(this,'SOL')">SOL</button>
    </div>
  </div>
  <div style="font-size:13px;color:#666;margin-bottom:20px">5. Analiz — gün × saat kazanma oranı</div>

  <!-- Özet stat kartları -->
  <div id="hm-top" style="display:grid;grid-template-columns:200px 1fr;gap:14px;margin-bottom:20px;align-items:start">
    <div id="hm-summary" style="display:flex;flex-direction:column;gap:12px"></div>
    <div id="hm-breakdown"></div>
  </div>

  <div class="section-wrap" style="overflow-x:auto;padding:20px 16px">
    <div id="heatmap-grid" style="min-width:700px"></div>
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

<!-- Slot Popup -->
<div id="slot-overlay" onclick="closeSlotPopup()" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:200;backdrop-filter:blur(4px)"></div>
<div id="slot-popup" style="display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
  z-index:201;background:#141414;border:1px solid #2a2a2a;border-radius:20px;
  padding:28px;min-width:360px;max-width:520px;width:92%;max-height:80vh;overflow-y:auto">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <div>
      <div style="font-size:11px;color:#555;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">En Etkili Zaman</div>
      <div id="slot-title" style="font-size:20px;font-weight:800"></div>
    </div>
    <button onclick="closeSlotPopup()" style="background:#1a1a1a;border:none;color:#888;font-size:16px;cursor:pointer;padding:8px 12px;border-radius:10px">✕</button>
  </div>
  <div id="slot-body"></div>
</div>

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
    const trMob = document.getElementById('total-risk-mob');
    if (trMob) trMob.textContent = '$' + totalRisk.toFixed(2);
    const totalToWin = d.positions.reduce((acc, p) => acc + (p.pm_size || 0), 0);
    const twEl = document.getElementById('total-towin');
    if (twEl) twEl.textContent = totalToWin > 0 ? '$' + totalToWin.toFixed(2) : '—';

    // Grafik tabları
    const syms = [...new Set(d.positions.map(p => p.name))];
    buildTabs(syms.length ? syms : ['BTC','ETH','SOL']);
    if (!currentSym) loadChart(syms.length ? syms[0] : 'BTC');

    // Pozisyonlar
    const pc    = document.getElementById('positions');
    const pcMob = document.getElementById('positions-mob');
    const posHTML = !d.positions.length
      ? '<div class="empty">Şu an açık pozisyon yok</div>'
      : d.positions.map(p => {
        const dirClass = p.dir==='UP' ? 'dir-up' : 'dir-down';
        const dc = p.dir==='UP'?'up':'down';
        const pctStr = (p.pct>=0?'+':'') + p.pct.toFixed(2)+'%';
        const time   = p.entry_time ? p.entry_time.substring(11,16)+' İST' : '';
        const cvColor = p.close_val !== null ? (parseFloat(p.close_val)>=parseFloat(p.pm_spent)?'#4ade80':'#f87171') : '#555';
        const cvStr  = p.close_val !== null ? ` <span style="color:${cvColor};font-weight:700">→ $${p.close_val}</span>` : '';
        return `<div class="pos-card ${dirClass}">
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
    pc.innerHTML    = posHTML;
    if (pcMob) pcMob.innerHTML = posHTML;

    // Sembol WR kartları
    const symEl = document.getElementById('sym-wr');
    symEl.innerHTML = (ss.sym_wr || []).map(sv => {
      const color = sv.wr >= 55 ? '#4ade80' : sv.wr >= 50 ? '#a3e635' : '#f87171';
      return `<div style="flex:1;background:#1c1c1e;border-radius:12px;padding:10px 8px;text-align:center;">
        <div style="font-size:11px;color:#ccc;margin-bottom:4px;font-weight:700">${sv.sym}</div>
        <div style="font-size:18px;font-weight:800;color:${color}">${sv.wr}%</div>
        <div style="font-size:10px;color:#888">${sv.w}/${sv.t}</div>
      </div>`;
    }).join('') || '<div style="color:#666;font-size:13px">Veri yok</div>';

    // En etkili gün+saat top 3
    const slotEl = document.getElementById('top-slots');
    const days_dow = {'Pzt':0,'Sal':1,'Çar':2,'Per':3,'Cum':4,'Cmt':5,'Paz':6};
    slotEl.innerHTML = (ss.top_slots || []).map((sl, i) => {
      const medals = ['🥇','🥈','🥉'];
      const barW   = Math.round(sl.wr);
      const dow    = days_dow[sl.day] ?? 0;
      const hour   = parseInt(sl.hour);
      const wrColor = sl.wr >= 70 ? '#4ade80' : sl.wr >= 55 ? '#a3e635' : '#c8f135';
      return `<div onclick="openSlotPopup(${dow},${hour})"
        style="padding:12px;margin-bottom:8px;background:#111;border-radius:14px;
               cursor:pointer;transition:.15s;border:1px solid #1f1f1f"
        onmouseover="this.style.borderColor='#c8f135'" onmouseout="this.style.borderColor='#1f1f1f'">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <span style="font-size:13px;font-weight:800">${medals[i]} ${sl.day} ${sl.hour}</span>
          <span style="font-size:16px;font-weight:800;color:${wrColor}">${sl.wr}%</span>
        </div>
        <div style="height:4px;background:#1c1c1e;border-radius:4px;margin-bottom:8px">
          <div style="height:100%;width:${barW}%;background:${wrColor};border-radius:4px"></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:11px;color:#666">${sl.w} kazanç / ${sl.t} işlem</span>
          <span style="font-size:10px;color:#444;background:#1c1c1e;padding:2px 8px;border-radius:6px">detay →</span>
        </div>
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

// ── Slot Popup ──────────────────────────────────────────
const _dayNames = ['Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi','Pazar'];

async function openSlotPopup(dow, hour) {
  const overlay = document.getElementById('slot-overlay');
  const popup   = document.getElementById('slot-popup');
  overlay.style.display = 'block';
  popup.style.display   = 'block';
  document.getElementById('slot-title').textContent = `${_dayNames[dow]} ${String(hour).padStart(2,'0')}:00`;
  document.getElementById('slot-body').innerHTML = '<div style="color:#555;text-align:center;padding:24px">Yükleniyor...</div>';

  const r = await fetch(`/poly/api/heatmap/detail?dow=${dow}&hour=${hour}&sym=ALL`);
  const d = await r.json();

  const pc = d.pnl >= 0 ? '#4ade80' : '#f87171';
  const wc = d.wr >= 55 ? '#4ade80' : d.wr >= 50 ? '#a3e635' : '#f87171';
  const totalReturn = (d.spent + d.pnl).toFixed(2);

  document.getElementById('slot-body').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px">
      <div style="background:#111;border-radius:12px;padding:12px;text-align:center">
        <div style="font-size:10px;color:#555;text-transform:uppercase;margin-bottom:4px">İşlem</div>
        <div style="font-size:22px;font-weight:800">${d.total}</div>
        <div style="font-size:11px;color:#666">${d.wins}W / ${d.losses}L</div>
      </div>
      <div style="background:#111;border-radius:12px;padding:12px;text-align:center">
        <div style="font-size:10px;color:#555;text-transform:uppercase;margin-bottom:4px">Kazanma</div>
        <div style="font-size:22px;font-weight:800;color:${wc}">${d.wr}%</div>
        <div style="font-size:11px;color:#666">Yatırılan: $${d.spent.toFixed(2)}</div>
      </div>
      <div style="background:#111;border-radius:12px;padding:12px;text-align:center">
        <div style="font-size:10px;color:#555;text-transform:uppercase;margin-bottom:4px">Net Kazanç</div>
        <div style="font-size:22px;font-weight:800;color:${pc}">${d.pnl>=0?'+':''}$${d.pnl.toFixed(2)}</div>
        <div style="font-size:11px;color:#666">Toplam: $${totalReturn}</div>
      </div>
    </div>
    ${!d.trades.length ? '<div style="color:#555;text-align:center;padding:16px">Bu saatte işlem yok</div>' :
    `<table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="color:#555;font-size:11px;text-transform:uppercase;border-bottom:1px solid #222">
        <th style="text-align:left;padding:8px 0">Sembol</th>
        <th style="text-align:center;padding:8px 4px">Yön</th>
        <th style="text-align:center;padding:8px 4px">Sonuç</th>
        <th style="text-align:right;padding:8px 4px">Risk</th>
        <th style="text-align:right;padding:8px 0">Kazanç</th>
        <th style="text-align:right;padding:8px 0 8px 8px;font-size:10px">Tarih</th>
      </tr></thead><tbody>
      ${d.trades.map((t,i)=>{
        const pc=t.pnl>=0?'#4ade80':'#f87171';
        return `<tr style="${i>0?'border-top:1px solid #1e1e1e':''}">
          <td style="padding:10px 0;font-weight:700;font-size:14px">${t.sym}</td>
          <td style="text-align:center">${t.dir==='UP'?'📈':'📉'}</td>
          <td style="text-align:center">${t.win===true?'✅':t.win===false?'❌':'⏳'}</td>
          <td style="text-align:right;color:#777">$${t.spent}</td>
          <td style="text-align:right;font-weight:700;color:${pc}">${t.pnl>=0?'+':''}$${t.pnl.toFixed(2)}</td>
          <td style="text-align:right;color:#444;font-size:11px;padding-left:8px">${t.time}</td>
        </tr>`;
      }).join('')}
      </tbody></table>`}`;
}

function closeSlotPopup() {
  document.getElementById('slot-overlay').style.display = 'none';
  document.getElementById('slot-popup').style.display   = 'none';
}
document.addEventListener('keydown', e => { if(e.key==='Escape') closeSlotPopup(); });

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
    const r   = await fetch('/poly/api/heatmap?sym=' + _hmSym);
    const d   = await r.json();
    _hmData   = d.cells;
    renderSummary(d.summary, d.sym_breakdown || []);
  }
  renderHeatmap(_hmData);
}

function renderSummary(s, breakdown) {
  const pc = s.pnl >= 0 ? '#4ade80' : '#f87171';
  const wc = s.wr >= 55 ? '#4ade80' : s.wr >= 50 ? '#a3e635' : '#f87171';
  document.getElementById('hm-summary').innerHTML = `
    <div class="section-wrap" style="margin:0;padding:14px 16px">
      <div style="display:flex;flex-direction:column;gap:14px">
        <div>
          <div style="font-size:10px;color:#666;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">Toplam İşlem</div>
          <div style="font-size:22px;font-weight:800;line-height:1">${s.total}</div>
          <div style="font-size:11px;color:#666;margin-top:2px">${s.wins}K / ${s.losses}K</div>
        </div>
        <div style="border-top:1px solid #2a2a2a;padding-top:14px">
          <div style="font-size:10px;color:#666;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">Kazanma Oranı</div>
          <div style="font-size:22px;font-weight:800;color:${wc};line-height:1">${s.wr}%</div>
          <div style="font-size:11px;color:#666;margin-top:2px">${s.wins}W · ${s.losses}L</div>
        </div>
        <div style="border-top:1px solid #2a2a2a;padding-top:14px">
          <div style="font-size:10px;color:#666;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">Net Kazanç</div>
          <div style="font-size:22px;font-weight:800;color:${pc};line-height:1">${s.pnl>=0?'+':''}$${s.pnl.toFixed(2)}</div>
          <div style="font-size:11px;color:#666;margin-top:2px">Yatırılan: $${s.spent.toFixed(2)}</div>
        </div>
      </div>
    </div>`;

  const bdEl = document.getElementById('hm-breakdown');
  if (!breakdown.length) { bdEl.innerHTML = ''; return; }
  bdEl.innerHTML = `<div class="section-wrap" style="margin:0;overflow-x:auto;padding:0">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="color:#555;font-size:11px;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #2a2a2a">
        <th style="text-align:left;padding:12px 16px">Sembol</th>
        <th style="text-align:center;padding:12px 10px">İşlem</th>
        <th style="text-align:center;padding:12px 10px">Kazanma</th>
        <th style="text-align:center;padding:12px 10px">W / L</th>
        <th style="text-align:right;padding:12px 10px">Risk</th>
        <th style="text-align:right;padding:12px 16px">P&L</th>
      </tr></thead><tbody>
      ${breakdown.map((b,i) => {
        const pc=b.pnl>=0?'#4ade80':'#f87171'; const wc=b.wr>=55?'#4ade80':b.wr>=50?'#a3e635':'#f87171';
        return `<tr style="${i>0?'border-top:1px solid #1e1e1e':''}">
          <td style="padding:14px 16px;font-weight:800;font-size:16px">${b.sym}</td>
          <td style="text-align:center;padding:14px 10px;color:#aaa">${b.t}</td>
          <td style="text-align:center;padding:14px 10px;font-weight:700;color:${wc}">${b.wr}%</td>
          <td style="text-align:center;padding:14px 10px;color:#666">${b.w}W·${b.t-b.w}L</td>
          <td style="text-align:right;padding:14px 10px;color:#666">$${b.spent.toFixed(0)}</td>
          <td style="text-align:right;padding:14px 16px;font-weight:700;color:${pc}">${b.pnl>=0?'+':''}$${b.pnl.toFixed(2)}</td>
        </tr>`;}).join('')}
      </tbody>
    </table></div>`;
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

_SETTINGS_FILE = os.path.join(_DIR_POLY, "analiz5_settings.json")
_SETTINGS_LABELS = {
    "amount_agree":    {"label": "A9 + A5 aynı yön", "unit": "$", "min": 1, "max": 100, "step": 0.5},
    "amount_a5_only":  {"label": "A9 sessiz, A5 var", "unit": "$", "min": 1, "max": 100, "step": 0.5},
    "amount_a9_only":  {"label": "A9 var, A5 sessiz", "unit": "$", "min": 1, "max": 100, "step": 0.5},
    "eth_multiplier":  {"label": "ETH çarpanı", "unit": "×", "min": 0.1, "max": 1.0, "step": 0.05},
}

def _read_settings() -> dict:
    defaults = {"amount_agree": 15.0, "amount_a5_only": 8.0, "amount_a9_only": 6.0, "eth_multiplier": 0.7}
    if os.path.exists(_SETTINGS_FILE):
        with open(_SETTINGS_FILE) as f:
            data = json.load(f)
        defaults.update({k: data[k] for k in defaults if k in data})
    return defaults

@app.route("/poly/api/settings", methods=["GET"])
def api_settings_get():
    if _auth_required(): return jsonify({"ok": False}), 401
    return jsonify(_read_settings())

@app.route("/poly/api/settings", methods=["POST"])
def api_settings_post():
    if _auth_required(): return jsonify({"ok": False}), 401
    body = request.get_json(force=True)
    current = _read_settings()
    for k in _SETTINGS_LABELS:
        if k in body:
            try:
                val = float(body[k])
                meta = _SETTINGS_LABELS[k]
                val = max(meta["min"], min(meta["max"], val))
                current[k] = round(val, 4)
            except (ValueError, TypeError):
                pass
    if os.path.exists(_SETTINGS_FILE):
        with open(_SETTINGS_FILE) as f:
            full = json.load(f)
    else:
        full = {}
    full.update(current)
    with open(_SETTINGS_FILE, "w") as f:
        json.dump(full, f, indent=2, ensure_ascii=False)
    return jsonify({"ok": True, "settings": current})

@app.route("/ayarlar")
@app.route("/ayarlar/")
def ayarlar():
    if _auth_required(): return redirect("/poly/login")
    return render_template_string(AYARLAR_HTML)

@app.route("/poly")
@app.route("/poly/")
def dashboard():
    if _auth_required(): return redirect("/poly/login")
    return render_template_string(HTML)

@app.route("/harita")
@app.route("/harita/")
def harita():
    if _auth_required(): return redirect("/poly/login")
    return render_template_string(HARITA_HTML)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
