"""
PolyMarket Dashboard — bursaapp.com/poly
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template_string, request, session, redirect, url_for

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "temmuzPoly"))

_DIR_POLY = os.path.join(os.path.dirname(__file__), "..", "temmuzPoly")
_ACTIVE_SYMS = ["BTC", "ETH", "SOL"]

# Sıcaklık haritası: analiz bazlı aktif semboller
_HEATMAP_SYMS = {
    "analiz1":  ["BTC", "SOL"],
    "analiz4":  ["BTC", "ETH"],
    "analiz5":  ["BTC", "SOL"],
    "analiz6":  ["BTC", "SOL"],
    "analiz9":  ["BTC", "SOL"],
    "analiz10": ["BTC", "SOL"],
    "karisim1": ["BTC", "SOL"],
}
_DISABLED_SYMS = frozenset({"XRP", "DOGE", "BNB", "HYPE"})

# ── Analiz kayıt defteri (harita + heatmap API tek kaynak) ─────
# Yeni analiz: isteğe bağlı özel isim için _ANALYSIS_LABELS'a ekle.
# Eklenmezse poly_trader_analiz7_history.json → otomatik "7. Analiz" sekmesi açılır.
_ANALYSIS_ORDER = [
    "analiz5", "analiz6", "analiz1", "analiz4", "analiz9", "analiz10", "karisim1",
    "15m_btc", "5m_btc_102", "5m_btc_103", "5m_btc_104", "5m_btc_105",
]
_HISTORY_ORDER = [
    "analiz1", "analiz3", "analiz4", "analiz5", "analiz6", "analiz9",
    "analiz10", "karisim1", "15m_btc", "5m_btc_102", "5m_btc_103", "5m_btc_104", "5m_btc_105",
]
_ANALYSIS_LABELS: dict[str, str] = {
    "analiz1":    "1. Analiz",
    "analiz3":    "3. Analiz",
    "analiz4":    "4. Analiz",
    "analiz5":    "5. Analiz",
    "analiz6":    "6. Analiz BTC-SOL",
    "analiz9":    "9. Analiz",
    "analiz10":   "10. Analiz",
    "karisim1":   "11. Analiz",
    "15m_btc":    "5M 101 BTC",
    "5m_btc_102": "5M 102 BTC",
    "5m_btc_103": "5M 103 BTC/SOL",
    "5m_btc_104": "5M 104 BTC",
    "5m_btc_105": "5M 105 BTC",
}


def _discover_trader_keys() -> set[str]:
    keys: set[str] = set()
    if not os.path.isdir(_DIR_POLY):
        return keys
    for fn in os.listdir(_DIR_POLY):
        if fn.startswith("poly_trader_") and fn.endswith("_history.json"):
            keys.add(fn[len("poly_trader_"):-len("_history.json")])
    return keys


def _trader_exists(key: str, on_disk: set[str]) -> bool:
    if key in on_disk:
        return True
    return os.path.exists(os.path.join(_DIR_POLY, f"poly_trader_{key}_state.json"))


def _auto_label(key: str) -> str:
    if key in _ANALYSIS_LABELS:
        return _ANALYSIS_LABELS[key]
    m = re.match(r"^analiz(\d+)$", key)
    if m:
        return f"{m.group(1)}. Analiz"
    if key == "karisim1":
        return "11. Analiz"
    if key == "15m_btc":
        return "5M 101 BTC"
    if key.startswith("5m_btc_"):
        n = key.replace("5m_btc_", "")
        if n == "real":
            return "5M 201 BTC"
        return f"5M {n.upper()} BTC"
    return key.replace("_", " ").title()


def _build_system_list(order: list[str]) -> list[tuple[str, str]]:
    on_disk = _discover_trader_keys()
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for key in order:
        if not _trader_exists(key, on_disk) and key not in _ANALYSIS_LABELS:
            continue
        out.append((key, _ANALYSIS_LABELS.get(key, _auto_label(key))))
        seen.add(key)
    for key in sorted(on_disk - seen):
        out.append((key, _ANALYSIS_LABELS.get(key, _auto_label(key))))
    return out


_ANALYSIS_SYSTEMS = _build_system_list(_ANALYSIS_ORDER)
_HEATMAP_ANALYSES = dict(_ANALYSIS_SYSTEMS)
_HARITA_TAB_ANALYSES = list(_ANALYSIS_SYSTEMS)
_HISTORY_SYSTEMS = _build_system_list(_HISTORY_ORDER)
_TZ_TR    = ZoneInfo("Europe/Istanbul")
_BINANCE  = "https://fapi.binance.com"
_PM_GAMMA = "https://gamma-api.polymarket.com"

app = Flask(__name__)
app.secret_key = "pk_bursaapp_x9f2k7m3"
app.config["SESSION_COOKIE_SECURE"]   = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_PATH"]     = "/"

# nginx reverse proxy arkasında çalışırken URL scheme ve host'u düzelt
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

_USERNAME = "cem"
_PASSWORD = "cem332020"

LOGIN_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%23c8f135'/><text y='72' x='50' text-anchor='middle' font-size='62' font-family='system-ui,sans-serif' font-weight='900' fill='%230d0d0d'>P</text></svg>">
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
    <input type="hidden" name="next" value="{{ next_url }}">
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

# Gerçek Polymarket işlem açan sistemler (Açık Pozisyonlar paneli)
_PM_POSITION_SOURCES = [
    ("5m_btc_102", "5M 102 BTC"),
    ("analiz5",    "5. Analiz"),
    ("analiz10",   "10. Analiz"),
]

def _position_visible(_key: str, pos: dict) -> bool:
    """Yalnızca gerçek PM pozisyonları (slug/token + harcanan tutar)."""
    spent = pos.get("pm_spent") or pos.get("amount")
    if not spent:
        return False
    return bool(pos.get("pm_slug") or pos.get("pm_token_id"))

def collect_positions() -> list:
    """Gerçek Polymarket açık pozisyonları (tüm aktif PM trader'lar)."""
    positions = []
    for key, label in _PM_POSITION_SOURCES:
        state = load_state(key)
        for pos in state.get("open_positions", []):
            if not _position_visible(key, pos):
                continue
            positions.append({**pos, "_analiz": key, "_analiz_label": label})
    return positions

def _auth_required():
    return session.get("logged_in") is not True


def _safe_next_url(path: str | None) -> str:
    if not path or not path.startswith("/") or path.startswith("//"):
        return "/poly"
    return path


def _login_redirect():
    return redirect(f"/poly/login?next={request.path}")


# ── Login ─────────────────────────────────────────────────────
@app.route("/poly/login", methods=["GET", "POST"])
def login():
    error = False
    next_url = _safe_next_url(request.args.get("next") or request.form.get("next"))
    if request.method == "POST":
        if (request.form.get("username") == _USERNAME and
                request.form.get("password") == _PASSWORD):
            session["logged_in"] = True
            return redirect(next_url)
        error = True
    return render_template_string(LOGIN_HTML, error=error, next_url=next_url)

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
            "analiz":       pos.get("_analiz_label", pos["_analiz"]),
            "analiz_key":   pos["_analiz"],
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
            "closable":     bool(pos.get("pm_token_id") and pm_size),
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


def _allowed_syms_for(key: str) -> list[str]:
    return _HEATMAP_SYMS.get(key, _ACTIVE_SYMS)


def _filter_hist_for(key: str, hist: list) -> list:
    allowed = set(_allowed_syms_for(key))
    return [t for t in hist if t.get("symbol", "").replace("USDT", "") in allowed]


def _harita_tabs_html() -> str:
    parts = []
    for i, (key, label) in enumerate(_HARITA_TAB_ANALYSES):
        active = " active" if i == 0 else ""
        parts.append(
            f'<button class="hm-analiz-tab{active}" '
            f'onclick="setAnaliz(this,\'{key}\')">{label}</button>'
        )
    return "\n    ".join(parts)


def _trade_sort_ts(t: dict) -> str:
    return t.get("exit_time_tr") or t.get("entry_time_tr") or ""


def _format_history_trade(t: dict, key: str, label: str) -> dict:
    sym   = t.get("symbol", "").replace("USDT", "")
    spent = t.get("pm_spent") or t.get("amount") or 0
    pnl   = t.get("pnl", 0)
    ts    = _trade_sort_ts(t)
    entry = t.get("entry_price")
    exit_p = t.get("exit_price")
    return {
        "key":    key,
        "analiz": label,
        "sym":    sym,
        "dir":    t.get("predicted_dir", ""),
        "win":    t.get("win"),
        "entry":  round(entry, 4) if entry is not None else None,
        "exit":   round(exit_p, 4) if exit_p is not None else None,
        "spent":  round(spent, 2),
        "pnl":    round(pnl, 2),
        "time":   ts[:16].replace("T", " ") if ts else "—",
        "sort_ts": ts,
    }


@app.route("/poly/api/history")
def api_history():
    if _auth_required(): return jsonify({"error": "unauthorized"}), 401
    try:
        limit = min(max(int(request.args.get("limit", 15)), 1), 50)
    except ValueError:
        limit = 15
    analiz_filter = request.args.get("analiz", "ALL")

    groups   = []
    all_flat = []

    for key, label in _HISTORY_SYSTEMS:
        if analiz_filter != "ALL" and key != analiz_filter:
            continue
        path = os.path.join(_DIR_POLY, f"poly_trader_{key}_history.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                hist = json.load(f)
        except Exception:
            continue
        hist = _filter_hist_for(key, hist)
        resolved = [t for t in hist if t.get("win") is not None]
        recent = list(reversed(resolved[-limit:])) if resolved else []
        trades = [_format_history_trade(t, key, label) for t in recent]
        groups.append({
            "key": key, "label": label,
            "total": len(hist), "resolved": len(resolved),
            "trades": trades,
        })
        all_flat.extend(trades)

    all_flat.sort(key=lambda x: x["sort_ts"], reverse=True)

    return jsonify({
        "groups": groups,
        "all":    all_flat,
        "limit":  limit,
        "systems": [{"key": k, "label": l} for k, l in _HISTORY_SYSTEMS],
    })

@app.route("/poly/api/heatmap")
def api_heatmap():
    if _auth_required(): return redirect("/poly/login")
    from collections import defaultdict
    sym_filter  = request.args.get("sym", "ALL").upper()
    analiz_key  = request.args.get("analiz", "analiz5")
    if analiz_key not in _HEATMAP_ANALYSES:
        analiz_key = "analiz5"
    allowed_syms = _HEATMAP_SYMS.get(analiz_key, _ACTIVE_SYMS)
    if sym_filter != "ALL" and sym_filter not in allowed_syms:
        sym_filter = "ALL"
    path = os.path.join(_DIR_POLY, f"poly_trader_{analiz_key}_history.json")
    if not os.path.exists(path):
        return jsonify({"cells": []})
    with open(path) as f:
        hist = json.load(f)
    hist = [t for t in hist if t.get("symbol", "").replace("USDT", "") in allowed_syms]
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
        for s in allowed_syms:
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
        "allowed_syms": allowed_syms,
    })

@app.route("/poly/api/heatmap/detail")
def api_heatmap_detail():
    if _auth_required(): return redirect("/poly/login")
    days_tr = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    try:
        dow  = request.args.get("dow", None)
        dow  = int(dow) if dow is not None else None
        hour = int(request.args.get("hour", -1))
        sym  = request.args.get("sym", "ALL").upper()
    except ValueError:
        return jsonify({"error": "bad params"}), 400

    analiz_key = request.args.get("analiz", "analiz5")
    if analiz_key not in _HEATMAP_ANALYSES:
        analiz_key = "analiz5"
    allowed_syms = _HEATMAP_SYMS.get(analiz_key, _ACTIVE_SYMS)
    if sym != "ALL" and sym not in allowed_syms:
        sym = "ALL"
    path = os.path.join(_DIR_POLY, f"poly_trader_{analiz_key}_history.json")
    if not os.path.exists(path):
        return jsonify({"trades": []})
    with open(path) as f:
        hist = json.load(f)
    hist = [t for t in hist if t.get("symbol", "").replace("USDT", "") in allowed_syms]

    trades = []
    for t in hist:
        if t.get("entry_hour_tr") != hour:
            continue
        if dow is not None and t.get("entry_dow") != dow:
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
    hist = _filter_hist_for("analiz5", hist)

    # Sembol bazlı WR
    sym_stat = defaultdict(lambda: {"w": 0, "t": 0})
    for t in hist:
        sym = t.get("symbol", "").replace("USDT", "")
        sym_stat[sym]["t"] += 1
        if t.get("win"):
            sym_stat[sym]["w"] += 1
    sym_wr = []
    for sym in _allowed_syms_for("analiz5"):
        v = sym_stat.get(sym, {"w": 0, "t": 0})
        if not v["t"]:
            continue
        wr = round(v["w"] / v["t"] * 100, 1)
        sym_wr.append({"sym": sym, "wr": wr, "w": v["w"], "t": v["t"]})
    sym_wr.sort(key=lambda x: x["wr"], reverse=True)

    # Saat bazlı, birden fazla günde tutarlı başarı — multi-day consistency
    days_tr = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    hour_day: dict = {}
    for t in hist:
        dow  = t.get("entry_dow")
        hour = t.get("entry_hour_tr")
        if dow is None or hour is None:
            continue
        if hour not in hour_day:
            hour_day[hour] = {}
        if dow not in hour_day[hour]:
            hour_day[hour][dow] = {"w": 0, "t": 0}
        hour_day[hour][dow]["t"] += 1
        if t.get("win"):
            hour_day[hour][dow]["w"] += 1

    top_slots = []
    for h, day_data in hour_day.items():
        good_days = [(d, v) for d, v in day_data.items() if v["t"] >= 1 and v["w"] / v["t"] > 0.5]
        all_w = sum(v["w"] for v in day_data.values())
        all_t = sum(v["t"] for v in day_data.values())
        if not good_days or all_t < 3:
            continue
        wr = round(all_w / all_t * 100, 1)
        day_names = [days_tr[d] for d, _ in sorted(good_days)]
        top_slots.append({
            "hour":      f"{h:02d}:00",
            "hour_int":  h,
            "good_days": len(good_days),
            "day_names": day_names,
            "wr":        wr,
            "w":         all_w,
            "t":         all_t,
        })
    top_slots.sort(key=lambda x: (x["good_days"], x["wr"]), reverse=True)
    return jsonify({"sym_wr": sym_wr, "top_slots": top_slots[:3]})

@app.route("/poly/api/analizler")
def api_analizler():
    if _auth_required(): return jsonify({"error": "unauthorized"}), 401
    _SYSTEMS = [
        ("analiz1",    "1. Analiz",             300,  "RSI+MACD+EMA"),
        ("analiz3",    "3. Analiz (Stoch ETH)", 300,  "Stochastic RSI / ETH"),
        ("analiz4",    "4. Analiz",             300,  "Trend+MR+OF+Fund"),
        ("analiz5",    "5. Analiz",             None, "A1 Motoru Gerçek PM"),
        ("analiz6",    "6. Analiz BTC-SOL",     500,  "RSI Div (Katı)"),
        ("analiz9",    "9. Analiz",             300,  "Çoklu Algo Sanal"),
        ("analiz10",   "10. Analiz",            None, "Çift Konsensüs Gerçek PM"),
        ("karisim1",   "11. Analiz",            300,  "A1+A4 Meta"),
        ("15m_btc",     "5M 101 BTC",            200,  "4-Algo Sanal $3"),
        ("5m_btc_102",  "5M 102 BTC",            200,  "101 + Momentum + KALEM Sanal"),
        ("5m_btc_103",  "5M 103 BTC/SOL",        200,  "A10 Çift Konsensüs"),
        ("5m_btc_104",  "5M 104 BTC",            200,  "5-Algo Enhanced Sanal"),
        ("5m_btc_105",  "5M 105 BTC",            200,  "102 + MR veto Sanal"),
    ]
    results = []
    for key, label, init_bal, desc in _SYSTEMS:
        hpath = os.path.join(_DIR_POLY, f"poly_trader_{key}_history.json")
        spath = os.path.join(_DIR_POLY, f"poly_trader_{key}_state.json")
        if not os.path.exists(hpath):
            continue
        try:
            hist  = json.load(open(hpath))
            state = json.load(open(spath)) if os.path.exists(spath) else {}
        except Exception:
            continue
        hist = _filter_hist_for(key, hist)
        total = len(hist)
        wins  = sum(1 for t in hist if t.get("win"))
        wr    = round(wins / total * 100, 1) if total else 0
        bal   = state.get("balance", 0)
        # P&L = bakiye - başlangıç (reset sonrası kayıtları da doğru yansıtır)
        pnl   = round(bal - init_bal, 2) if init_bal else round(sum(t.get("pnl", 0) for t in hist), 2)
        allowed = _allowed_syms_for(key)
        open_cnt = len([
            p for p in state.get("open_positions", [])
            if p.get("symbol", "").replace("USDT", "") in allowed
        ])
        # Sembol bazlı
        sym_stats = {}
        for t in hist:
            sym = t.get("symbol", "").replace("USDT", "")
            if sym not in allowed:
                continue
            if sym not in sym_stats:
                sym_stats[sym] = {"w": 0, "t": 0}
            sym_stats[sym]["t"] += 1
            if t.get("win"):
                sym_stats[sym]["w"] += 1
        sym_list = []
        syms_for = allowed
        for sym in syms_for:
            v = sym_stats.get(sym)
            if v and v["t"]:
                sym_list.append({"sym": sym, "w": v["w"], "t": v["t"],
                                  "wr": round(v["w"]/v["t"]*100, 1)})
        results.append({
            "key": key, "label": label, "desc": desc,
            "init_bal": init_bal, "balance": round(bal, 2),
            "total": total, "wins": wins, "wr": wr, "pnl": pnl,
            "open": open_cnt, "sym_stats": sym_list,
        })
    results.sort(key=lambda x: (x["wr"], x["total"]), reverse=True)
    return jsonify(results)


@app.route("/analizler")
def page_analizler():
    if _auth_required(): return redirect("/poly/login")
    return ANALIZLER_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}


ANALIZLER_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Analizler — PolyMarket</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%2316a34a'/><text x='50%25' y='50%25' font-size='20' text-anchor='middle' dominant-baseline='central' fill='white' font-family='Arial' font-weight='bold'>P</text></svg>">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;color:#e0e0e0;font-family:'Inter',system-ui,sans-serif;min-height:100vh;display:flex}
.sidebar{width:220px;background:#0a0f0a;padding:24px 16px;display:flex;flex-direction:column;gap:4px;flex-shrink:0;position:sticky;top:0;height:100vh;overflow-y:auto}
.logo{font-size:20px;font-weight:800;color:#fff;margin-bottom:20px;letter-spacing:-0.5px}
.logo span{color:#c8f135}
.nav-label{font-size:10px;color:#444;text-transform:uppercase;letter-spacing:1px;padding:12px 12px 4px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;color:#888;text-decoration:none;font-size:14px;transition:.15s}
.nav-item:hover{background:#1a1a1a;color:#fff}
.nav-item.active{background:#1a2e1a;color:#c8f135;font-weight:600}
.nav-dot{width:6px;height:6px;border-radius:50%;background:#333;flex-shrink:0}
.nav-item.active .nav-dot,.nav-item:hover .nav-dot{background:#c8f135}
.sidebar-footer{margin-top:auto;font-size:12px;color:#333;padding:8px 12px;display:flex;align-items:center;gap:6px}
.live-dot{width:6px;height:6px;border-radius:50%;background:#22c55e;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.main{flex:1;padding:28px;max-width:1200px}
h1{font-size:22px;font-weight:800;margin-bottom:6px}
.subtitle{font-size:13px;color:#555;margin-bottom:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.card{background:#111;border:1px solid #1e1e1e;border-radius:16px;padding:20px;display:flex;gap:16px;align-items:center;transition:.2s}
.card:hover{border-color:#2a2a2a;background:#151515}
.donut-wrap{position:relative;width:80px;height:80px;flex-shrink:0}
.donut-wrap svg{transform:rotate(-90deg)}
.donut-center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.donut-pct{font-size:16px;font-weight:800;line-height:1}
.donut-lbl{font-size:9px;color:#555;margin-top:2px}
.card-info{flex:1;min-width:0}
.card-label{font-size:15px;font-weight:700;margin-bottom:2px}
.card-desc{font-size:11px;color:#555;margin-bottom:10px}
.card-row{display:flex;justify-content:space-between;margin-bottom:4px}
.card-key{font-size:12px;color:#666}
.card-val{font-size:12px;font-weight:600}
.pnl-pos{color:#4ade80}
.pnl-neg{color:#f87171}
.pnl-neu{color:#888}
.sym-pills{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}
.sym-pill{font-size:10px;padding:2px 7px;border-radius:20px;background:#1a1a1a;color:#888}
.sym-pill.good{background:#14291e;color:#4ade80}
.sym-pill.ok{background:#1e1e14;color:#a3e635}
.sym-pill.bad{background:#291414;color:#f87171}
.rank-badge{position:absolute;top:-6px;right:-6px;width:20px;height:20px;border-radius:50%;background:#c8f135;color:#000;font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center}
.card-wrap{position:relative}
#loading{text-align:center;color:#555;padding:60px;font-size:14px}
</style>
</head>
<body>
<div class="sidebar">
  <div class="logo">Poly<span>Market</span></div>
  <div class="nav-label">Ana Menü</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item" href="/algoritma"><span class="nav-dot"></span>Algoritma</a>
  <a class="nav-item" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item active" href="/analizler"><span class="nav-dot"></span>Analizler</a>
  <a class="nav-item" href="/poly/gecmis"><span class="nav-dot"></span>Geçmiş</a>
  <div class="nav-label">Hesap</div>
  <a class="nav-item" href="/ayarlar"><span class="nav-dot"></span>Ayarlar</a>
  <a class="nav-item" href="/poly/logout"><span class="nav-dot"></span>Çıkış</a>
  <div class="sidebar-footer"><span class="live-dot"></span>Canlı</div>
</div>
<div class="main">
  <h1>📊 Analizler</h1>
  <div class="subtitle" id="subtitle">Yükleniyor…</div>
  <div id="grid" class="grid"><div id="loading">Veriler yükleniyor…</div></div>
</div>
<script>
function donutSVG(pct, color){
  const r=28, cx=40, cy=40, circ=2*Math.PI*r;
  const fill = circ*(pct/100);
  const bg   = circ - fill;
  return `<svg width="80" height="80" viewBox="0 0 80 80">
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#1e1e1e" stroke-width="9"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="9"
      stroke-dasharray="${fill} ${bg}" stroke-linecap="round"/>
  </svg>`;
}

function pctColor(wr){
  if(wr>=60) return '#4ade80';
  if(wr>=55) return '#a3e635';
  if(wr>=50) return '#c8f135';
  if(wr>=45) return '#fb923c';
  return '#f87171';
}

function symClass(wr){
  if(wr>=60) return 'good';
  if(wr>=50) return 'ok';
  return 'bad';
}

async function load(){
  try{
  const r = await fetch('/poly/api/analizler');
  if(!r.ok){ document.getElementById('loading').textContent = 'API hatası: ' + r.status; return; }
  const data = await r.json();
  if(data.error){ document.getElementById('loading').textContent = 'Oturum hatası: ' + data.error; return; }
  document.getElementById('subtitle').textContent =
    `${data.length} sistem \u00b7 WR\u2019ye g\u00f6re s\u0131ral\u0131 \u00b7 Otomatik g\u00fcncellenir`;

  const grid = document.getElementById('grid');
  grid.innerHTML = data.map((a, i) => {
    const color  = pctColor(a.wr);
    const pnlCls = a.pnl > 0 ? 'pnl-pos' : a.pnl < 0 ? 'pnl-neg' : 'pnl-neu';
    const pnlStr = (a.pnl >= 0 ? '+' : '') + '$' + Math.abs(a.pnl).toFixed(2);
    const balStr = '$' + a.balance.toFixed(2);
    const rank   = i < 3 ? ['🥇','🥈','🥉'][i] : '';
    const symHtml = a.sym_stats.map(s =>
      `<span class="sym-pill ${symClass(s.wr)}">${s.sym} %${s.wr}</span>`
    ).join('');

    return `<div class="card-wrap">
      ${rank ? `<div class="rank-badge">${rank}</div>` : ''}
      <div class="card">
        <div class="donut-wrap">
          ${donutSVG(a.wr, color)}
          <div class="donut-center">
            <div class="donut-pct" style="color:${color}">${a.total ? a.wr+'%' : '—'}</div>
            <div class="donut-lbl">WR</div>
          </div>
        </div>
        <div class="card-info">
          <div class="card-label">${a.label}</div>
          <div class="card-desc">${a.desc}</div>
          <div class="card-row">
            <span class="card-key">Bakiye</span>
            <span class="card-val">${balStr}</span>
          </div>
          <div class="card-row">
            <span class="card-key">P&L</span>
            <span class="card-val ${pnlCls}">${pnlStr}</span>
          </div>
          <div class="card-row">
            <span class="card-key">İşlem</span>
            <span class="card-val">${a.wins}/${a.total}</span>
          </div>
          ${a.open ? `<div class="card-row"><span class="card-key">Açık</span><span class="card-val" style="color:#c8f135">${a.open} poz</span></div>` : ''}
          <div class="sym-pills">${symHtml}</div>
        </div>
      </div>
    </div>`;
  }).join('');
  }catch(e){
    document.getElementById('loading').textContent = 'JS hatası: ' + e.message;
    console.error(e);
  }
}

load();
setInterval(load, 60000);
</script>
</body>
</html>"""


GECMIS_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Geçmiş — PolyMarket</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%2316a34a'/><text x='50%25' y='50%25' font-size='20' text-anchor='middle' dominant-baseline='central' fill='white' font-family='Arial' font-weight='bold'>P</text></svg>">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;color:#e0e0e0;font-family:'Inter',system-ui,sans-serif;min-height:100vh;display:flex}
.sidebar{width:220px;background:#0a0f0a;padding:24px 16px;display:flex;flex-direction:column;gap:4px;flex-shrink:0;position:sticky;top:0;height:100vh;overflow-y:auto}
.logo{font-size:20px;font-weight:800;color:#fff;margin-bottom:20px;letter-spacing:-0.5px}
.logo span{color:#c8f135}
.nav-label{font-size:10px;color:#444;text-transform:uppercase;letter-spacing:1px;padding:12px 12px 4px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;color:#888;text-decoration:none;font-size:14px;transition:.15s}
.nav-item:hover{background:#1a1a1a;color:#fff}
.nav-item.active{background:#1a2e1a;color:#c8f135;font-weight:600}
.nav-dot{width:6px;height:6px;border-radius:50%;background:#333;flex-shrink:0}
.nav-item.active .nav-dot,.nav-item:hover .nav-dot{background:#c8f135}
.sidebar-footer{margin-top:auto;font-size:12px;color:#333;padding:8px 12px;display:flex;align-items:center;gap:6px}
.live-dot{width:6px;height:6px;border-radius:50%;background:#22c55e;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.main{flex:1;padding:28px;max-width:1400px}
h1{font-size:22px;font-weight:800;margin-bottom:6px}
.subtitle{font-size:13px;color:#555;margin-bottom:20px}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}
.fbtn{background:#111;border:1px solid #2a2a2a;color:#888;font-size:12px;font-weight:600;padding:8px 14px;border-radius:20px;cursor:pointer;transition:.15s}
.fbtn:hover{border-color:#444;color:#ccc}
.fbtn.active{background:#1a2e1a;border-color:#4ade80;color:#4ade80}
.group{margin-bottom:28px}
.group-head{display:flex;align-items:baseline;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.group-title{font-size:16px;font-weight:800}
.group-meta{font-size:12px;color:#555}
.tbl-wrap{background:#111;border:1px solid #1e1e1e;border-radius:14px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px;min-width:720px}
th{text-align:left;padding:12px 14px;font-size:10px;color:#555;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #1e1e1e;background:#0d0d0d}
td{padding:12px 14px;border-top:1px solid #161616}
tr:hover td{background:#141414}
.sym{font-weight:800;font-size:14px}
.win-yes{color:#4ade80;font-weight:700}
.win-no{color:#f87171;font-weight:700}
.pnl-pos{color:#4ade80;font-weight:700}
.pnl-neg{color:#f87171;font-weight:700}
.empty{color:#555;padding:40px;text-align:center;font-size:14px}
#loading{color:#555;padding:60px;text-align:center}
@media(max-width:800px){.sidebar{display:none}.main{padding:16px}}
</style>
</head>
<body>
<div class="sidebar">
  <div class="logo">Poly<span>Market</span></div>
  <div class="nav-label">Ana Menü</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item" href="/algoritma"><span class="nav-dot"></span>Algoritma</a>
  <a class="nav-item" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="/analizler"><span class="nav-dot"></span>Analizler</a>
  <a class="nav-item active" href="/poly/gecmis"><span class="nav-dot"></span>Geçmiş</a>
  <div class="nav-label">Hesap</div>
  <a class="nav-item" href="/ayarlar"><span class="nav-dot"></span>Ayarlar</a>
  <a class="nav-item" href="/poly/logout"><span class="nav-dot"></span>Çıkış</a>
  <div class="sidebar-footer"><span class="live-dot"></span>Canlı</div>
</div>
<div class="main">
  <h1>📜 Geçmiş İşlemler</h1>
  <div class="subtitle" id="subtitle">Tüm analizlerin son kapanan işlemleri</div>
  <div class="filters" id="filters"></div>
  <div id="content"><div id="loading">Yükleniyor…</div></div>
</div>
<script>
let _filter = 'ALL';
let _data = null;

function tradeRows(trades){
  if(!trades.length) return '<div class="empty">Bu analizde henüz kapanmış işlem yok</div>';
  return `<div class="tbl-wrap"><table>
    <thead><tr>
      <th>Sembol</th><th>Yön</th><th>Sonuç</th><th>Giriş</th><th>Çıkış</th>
      <th>Risk</th><th>P&amp;L</th><th>Tarih</th>
    </tr></thead><tbody>
    ${trades.map(t=>{
      const w = t.win===true?'win-yes':t.win===false?'win-no':'';
      const wTxt = t.win===true?'✅':t.win===false?'❌':'⏳';
      const pnlC = t.pnl>=0?'pnl-pos':'pnl-neg';
      const dir = t.dir==='UP'?'📈 UP':'📉 DOWN';
      const ent = t.entry!=null?t.entry:'—';
      const ext = t.exit!=null?t.exit:'—';
      return `<tr>
        <td class="sym">${t.sym}</td>
        <td>${dir}</td>
        <td class="${w}">${wTxt}</td>
        <td>${ent}</td>
        <td>${ext}</td>
        <td>$${t.spent.toFixed(2)}</td>
        <td class="${pnlC}">${t.pnl>=0?'+':''}$${t.pnl.toFixed(2)}</td>
        <td style="color:#666;font-size:12px">${t.time}</td>
      </tr>`;
    }).join('')}
    </tbody></table></div>`;
}

function render(){
  const el = document.getElementById('content');
  if(!_data || !_data.groups.length){
    el.innerHTML = '<div class="empty">Henüz geçmiş işlem verisi yok</div>';
    return;
  }
  if(_filter === 'ALL'){
    const merged = [..._data.all];
    el.innerHTML = `<div class="group">
      <div class="group-head">
        <div class="group-title">Tüm Analizler</div>
        <div class="group-meta">${merged.length} son işlem (yeniden eskiye)</div>
      </div>
      ${tradeRows(merged)}
    </div>`;
    return;
  }
  const g = _data.groups.find(x=>x.key===_filter);
  if(!g){ el.innerHTML='<div class="empty">Veri yok</div>'; return; }
  el.innerHTML = `<div class="group">
    <div class="group-head">
      <div class="group-title">${g.label}</div>
      <div class="group-meta">${g.trades.length} son işlem · toplam ${g.total} kayıt</div>
    </div>
    ${tradeRows(g.trades)}
  </div>`;
}

function setFilter(key, btn){
  _filter = key;
  document.querySelectorAll('.fbtn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  render();
}

async function load(){
  try{
    const r = await fetch('/poly/api/history?limit=15');
    if(!r.ok) throw new Error('API '+r.status);
    _data = await r.json();
    const filters = document.getElementById('filters');
    const active = [{key:'ALL',label:'Tümü'}].concat(
      _data.groups.map(g=>({key:g.key,label:g.label}))
    );
    filters.innerHTML = active.map((a,i)=>
      `<button class="fbtn${i===0?' active':''}" onclick="setFilter('${a.key}',this)">${a.label}</button>`
    ).join('');
    document.getElementById('subtitle').textContent =
      `${_data.groups.length} analiz · analiz başına son ${_data.limit} işlem`;
    render();
  }catch(e){
    document.getElementById('content').innerHTML =
      '<div class="empty">Yüklenemedi: '+e.message+'</div>';
  }
}

load();
setInterval(load, 60000);
</script>
</body>
</html>"""


@app.route("/poly/gecmis")
@app.route("/poly/gecmis/")
@app.route("/gecmis")
@app.route("/gecmis/")
def page_gecmis():
    if request.path.rstrip("/") == "/gecmis":
        return redirect("/poly/gecmis")
    if _auth_required():
        return _login_redirect()
    return GECMIS_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/poly/api/stats")
def api_stats():
    if _auth_required(): return redirect("/poly/login")
    analyses = dict(_HISTORY_SYSTEMS)
    algo_stats = []
    all_history = []

    for key, label in analyses.items():
        path = os.path.join(_DIR_POLY, f"poly_trader_{key}_history.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            hist = json.load(f)
        hist = _filter_hist_for(key, hist)
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
ALGORITMA_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%23c8f135'/><text y='72' x='50' text-anchor='middle' font-size='62' font-family='system-ui,sans-serif' font-weight='900' fill='%230d0d0d'>P</text></svg>">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Algoritma — PolyMarket</title>
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
  .live-dot { width:6px; height:6px; background:#4ade80; border-radius:50%; display:inline-block;
              margin-right:5px; animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  .main       { flex:1; min-width:0; margin-left:220px; margin-right:286px; padding:24px 20px 24px 24px; }
  .main-inner { display:block; }
  .main-left  { width:100%; }
  .main-right { position:fixed; right:0; top:0; bottom:0; width:270px;
                background:#0a0a0a; border-left:1px solid #1a1a1a;
                padding:24px 16px; overflow-y:auto; z-index:5; }

  /* ── Üst başlık + consensus ── */
  .top-bar { display:flex; align-items:flex-start; justify-content:flex-start; margin-bottom:24px; gap:24px; }
  .page-title { font-size:22px; font-weight:800; }
  .page-sub   { font-size:13px; color:#666; margin-top:4px; }

  .consensus-box {
    background:#111; border:1px solid #1e1e1e; border-radius:16px;
    padding:14px 20px; min-width:280px; flex-shrink:0;
  }
  .cb-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }
  .cb-title  { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.8px; color:#666; }
  .cb-time   { font-size:11px; color:#444; }
  .cb-rows   { display:flex; flex-direction:column; gap:8px; }
  .cb-row    { display:flex; align-items:center; gap:10px; }
  .cb-sym    { font-size:12px; font-weight:700; color:#fff; width:32px; }
  .cb-bar-wrap { flex:1; background:#1a1a1a; border-radius:6px; height:8px; overflow:hidden; }
  .cb-bar-up   { height:100%; background:#4ade80; border-radius:6px; transition:width .5s; }
  .cb-bar-dn   { height:100%; background:#f87171; border-radius:6px; border-radius:0 6px 6px 0; }
  .cb-label  { font-size:11px; font-weight:700; min-width:80px; text-align:right; }
  .lbl-up    { color:#4ade80; }
  .lbl-dn    { color:#f87171; }
  .lbl-neu   { color:#666; }
  .cb-detail { font-size:10px; color:#555; margin-top:2px; }
  .cb-next   { font-size:10px; color:#444; margin-top:10px; text-align:right; }

  /* ── Kartlar ── */
  .section-title {
    font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px;
    color:#c8f135; margin:28px 0 12px; padding-left:2px;
    display:flex; align-items:center; gap:8px;
  }
  .section-title::after { content:""; flex:1; height:1px; background:#1e1e1e; }
  .grid { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }
  @media(max-width:700px){ .grid { grid-template-columns:1fr; } }

  /* ── Kartlar — yeni kompakt tasarım ── */
  .card {
    background:#111; border:1px solid #1e1e1e; border-radius:16px;
    padding:14px 14px 12px; transition:border-color .2s;
    display:flex; flex-direction:column; gap:0;
  }
  .card:hover { border-color:#2e3a2e; }

  /* Üst satır: numara + isim + başarı */
  .card-top { display:flex; align-items:center; gap:8px; margin-bottom:10px; }
  .card-num {
    width:22px; height:22px; border-radius:6px; background:#1c1c1e; flex-shrink:0;
    display:flex; align-items:center; justify-content:center;
    font-size:10px; font-weight:800; color:#c8f135;
  }
  .card-name {
    flex:1; font-size:13px; font-weight:700; color:#fff; line-height:1.3;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
  }

  /* Sinyal hap'ları */
  .card-signals { display:flex; gap:5px; margin-bottom:10px; }
  .sig-pill {
    flex:1; text-align:center; padding:6px 2px; border-radius:9px;
    font-size:11px; font-weight:700; line-height:1.25; letter-spacing:.1px;
  }
  .sig-up      { background:#0e2a12; color:#4ade80; }
  .sig-down    { background:#2a0e0e; color:#f87171; }
  .sig-neutral { background:#1c1c1e; color:#555; }
  .sig-na      { background:#1c1c1e; color:#333; }
  .sig-loading { background:#1c1c1e; color:#444; animation:shimmer 1.5s infinite; }
  @keyframes shimmer { 0%,100%{opacity:.4} 50%{opacity:1} }

  /* Alt kısım: mini bar chart + başarı rakamı */
  .card-footer {
    display:flex; align-items:flex-end; justify-content:space-between; gap:10px;
    min-height:34px;
  }
  .mini-chart { display:flex; align-items:flex-end; gap:2px; flex:1; height:28px; }
  .mini-bar { flex:1; border-radius:3px 3px 0 0; min-height:3px; transition:height .4s; }
  .bar-win   { background:#4ade80; opacity:.8; }
  .bar-loss  { background:#f87171; opacity:.8; }
  .bar-empty { background:#1e1e1e; }
  .card-acc { text-align:right; flex-shrink:0; }
  .acc-pct   { font-size:18px; font-weight:800; line-height:1; }
  .acc-cnt   { font-size:10px; color:#555; margin-top:3px; }
  .acc-none  { font-size:11px; color:#333; }
  .pct-good  { color:#c8f135; }
  .pct-ok    { color:#fbbf24; }
  .pct-bad   { color:#f87171; }
  .pct-none  { color:#444; }

  /* ── Sağ kolon: Performans sıralaması ── */
  .rank-box { background:#111; border:1px solid #1e1e1e; border-radius:16px; padding:16px 18px; }
  .rank-title { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.8px;
                color:#c8f135; margin-bottom:14px; }
  .rank-item { display:flex; align-items:center; gap:10px; padding:8px 0;
               border-bottom:1px solid #1a1a1a; }
  .rank-item:last-child { border-bottom:none; }
  .rank-pos { width:20px; font-size:11px; font-weight:800; color:#444; text-align:center; flex-shrink:0; }
  .rank-pos.top1 { color:#fbbf24; }
  .rank-pos.top2 { color:#888; }
  .rank-pos.top3 { color:#b45309; }
  .rank-info { flex:1; min-width:0; }
  .rank-name { font-size:12px; font-weight:600; color:#ddd; line-height:1.3;
               display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
               overflow:hidden; }
  .rank-sub  { font-size:10px; color:#555; margin-top:1px; }
  .rank-wr   { font-size:13px; font-weight:800; min-width:38px; text-align:right; flex-shrink:0; }
  .wr-good  { color:#4ade80; }
  .wr-ok    { color:#fbbf24; }
  .wr-bad   { color:#f87171; }
  .rank-bar-wrap { height:3px; background:#1a1a1a; border-radius:2px; margin-top:4px; }
  .rank-bar-fill { height:100%; border-radius:2px; background:#c8f135; transition:width .5s; }
  .rank-empty { font-size:12px; color:#444; text-align:center; padding:20px 0; }

  /* Sembol en iyi algo şeridi */
  .sym-best { display:flex; flex-direction:column; align-items:flex-start;
              background:#111; border:1px solid #1e1e1e; border-radius:12px;
              padding:6px 12px; min-width:0; }
  .sym-best-sym  { font-size:11px; font-weight:800; color:#c8f135; line-height:1.2; }
  .sym-best-algo { font-size:11px; color:#aaa; white-space:nowrap; }
  .sym-best-stat { font-size:11px; color:#4ade80; font-weight:700; margin-left:4px; }

  /* Kart başarı rozeti — tag'lerin altında, sinyal pillerin üstünde */
  .card-acc  { display:flex; align-items:center; justify-content:space-between;
               margin:8px 0 6px; min-height:18px; }
  .acc-badge { font-size:11px; font-weight:700; padding:3px 10px; border-radius:20px; }
  .acc-good  { background:#1a3a1a; color:#4ade80; }
  .acc-mid   { background:#2e2a1a; color:#fbbf24; }
  .acc-bad   { background:#3a1a1a; color:#f87171; }
  .acc-none  { display:none; }
  .acc-rank  { font-size:11px; color:#555; }

  @media(max-width:860px){ .main-right { display:none; } }
  @media(max-width:900px){
    .top-bar { flex-direction:column; }
    .consensus-box { min-width:0; width:100%; }
  }
  @media(max-width:768px){
    .main { margin-left:0; padding:20px 12px; }
    .main-inner { flex-direction:column; }
    .sidebar { display:none; }
  }
</style>
</head>
<body>
<div class="app">
<div class="sidebar">
  <div class="logo">Poly<span>Market</span></div>
  <div class="nav-label">Ana Menü</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item active" href="/algoritma"><span class="nav-dot"></span>Algoritma</a>
  <a class="nav-item" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="/analizler"><span class="nav-dot"></span>Analizler</a>
  <a class="nav-item" href="/poly/gecmis"><span class="nav-dot"></span>Geçmiş</a>
  <div class="nav-label">Hesap</div>
  <a class="nav-item" href="/ayarlar"><span class="nav-dot"></span>Ayarlar</a>
  <a class="nav-item" href="/poly/logout"><span class="nav-dot"></span>Çıkış</a>
  <div class="sidebar-footer"><span class="live-dot"></span>Canlı</div>
</div>

<div class="main">
<div class="main-inner">
<div class="main-left">

  <!-- Üst bar -->
  <div class="top-bar">
    <div>
      <div class="page-title">Algoritma Analizi</div>
      <div class="page-sub">39 algoritma — BTC / ETH / SOL — 1 saatlik</div>
      <div id="top-sym-algos" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;"></div>
    </div>
    <!-- Consensus kutusu -->
    <div class="consensus-box">
      <div class="cb-header">
        <span class="cb-title">Genel Konsensüs</span>
        <span class="cb-time" id="cb-updated">Yükleniyor…</span>
      </div>
      <div id="cb-period" style="font-size:11px;color:#555;margin-bottom:4px;"></div>
      <div id="cb-total" style="font-size:11px;color:#888;margin-bottom:8px;"></div>
      <div class="cb-rows" id="cb-rows">
        <div class="sig-loading" style="height:32px;border-radius:8px;"></div>
      </div>
      <div class="cb-next" id="cb-next"></div>
    </div>
  </div>

  <!-- TREND -->
  <div class="section-title">📈 Trend Takip</div>
  <div class="grid">
    <div class="card" data-algo="1">
      <div class="card-top"><div class="card-num">1</div><div class="card-name">EMA Crossover</div></div>
      <div class="card-signals" id="sigs-1"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-1"></div><div class="card-acc" id="acc-1"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="2">
      <div class="card-top"><div class="card-num">2</div><div class="card-name">MACD + Divergence</div></div>
      <div class="card-signals" id="sigs-2"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-2"></div><div class="card-acc" id="acc-2"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="3">
      <div class="card-top"><div class="card-num">3</div><div class="card-name">Supertrend</div></div>
      <div class="card-signals" id="sigs-3"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-3"></div><div class="card-acc" id="acc-3"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="4">
      <div class="card-top"><div class="card-num">4</div><div class="card-name">Ichimoku Cloud</div></div>
      <div class="card-signals" id="sigs-4"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-4"></div><div class="card-acc" id="acc-4"><span class="acc-none pct-none">—</span></div></div>
    </div>
  </div>

  <!-- MOMENTUM -->
  <div class="section-title">⚡ Momentum / Osilatör</div>
  <div class="grid">
    <div class="card" data-algo="5">
      <div class="card-top"><div class="card-num">5</div><div class="card-name">RSI + Divergence</div></div>
      <div class="card-signals" id="sigs-5"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-5"></div><div class="card-acc" id="acc-5"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="6">
      <div class="card-top"><div class="card-num">6</div><div class="card-name">Stochastic RSI</div></div>
      <div class="card-signals" id="sigs-6"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-6"></div><div class="card-acc" id="acc-6"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="7">
      <div class="card-top"><div class="card-num">7</div><div class="card-name">Bollinger Bands</div></div>
      <div class="card-signals" id="sigs-7"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-7"></div><div class="card-acc" id="acc-7"><span class="acc-none pct-none">—</span></div></div>
    </div>
  </div>

  <!-- HACİM -->
  <div class="section-title">📊 Hacim Bazlı</div>
  <div class="grid">
    <div class="card" data-algo="8">
      <div class="card-top"><div class="card-num">8</div><div class="card-name">VWAP</div></div>
      <div class="card-signals" id="sigs-8"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-8"></div><div class="card-acc" id="acc-8"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="9">
      <div class="card-top"><div class="card-num">9</div><div class="card-name">OBV</div></div>
      <div class="card-signals" id="sigs-9"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-9"></div><div class="card-acc" id="acc-9"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="10">
      <div class="card-top"><div class="card-num">10</div><div class="card-name">Volume Profile (POC)</div></div>
      <div class="card-signals" id="sigs-10"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-10"></div><div class="card-acc" id="acc-10"><span class="acc-none pct-none">—</span></div></div>
    </div>
  </div>

  <!-- QUANT -->
  <div class="section-title">📐 Quant / İstatistiksel</div>
  <div class="grid">
    <div class="card" data-algo="11">
      <div class="card-top"><div class="card-num">11</div><div class="card-name">Mean Reversion</div></div>
      <div class="card-signals" id="sigs-11"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-11"></div><div class="card-acc" id="acc-11"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="12">
      <div class="card-top"><div class="card-num">12</div><div class="card-name">Pairs Trading</div></div>
      <div class="card-signals" id="sigs-12"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-12"></div><div class="card-acc" id="acc-12"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="13">
      <div class="card-top"><div class="card-num">13</div><div class="card-name">Grid Trading Bot</div></div>
      <div class="card-signals" id="sigs-13"><div class="sig-na sig-pill">BTC —</div><div class="sig-na sig-pill">ETH —</div><div class="sig-na sig-pill">SOL —</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-13"></div><div class="card-acc" id="acc-13"><span class="acc-none pct-none">Nötr</span></div></div>
    </div>
  </div>

  <!-- ML -->
  <div class="section-title">🤖 ML / Hibrit</div>
  <div class="grid">
    <div class="card" data-algo="14">
      <div class="card-top"><div class="card-num">14</div><div class="card-name">LSTM Zaman Serisi</div></div>
      <div class="card-signals" id="sigs-14"><div class="sig-na sig-pill" style="flex:3">— model yok —</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-14"></div><div class="card-acc" id="acc-14"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="15">
      <div class="card-top"><div class="card-num">15</div><div class="card-name">Multi-TF Confluence</div></div>
      <div class="card-signals" id="sigs-15"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-15"></div><div class="card-acc" id="acc-15"><span class="acc-none pct-none">—</span></div></div>
    </div>
  </div>

  <!-- VOLATİLİTE -->
  <div class="section-title">💥 Volatilite / Breakout</div>
  <div class="grid">
    <div class="card" data-algo="16">
      <div class="card-top"><div class="card-num">16</div><div class="card-name">ATR Breakout</div></div>
      <div class="card-signals" id="sigs-16"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-16"></div><div class="card-acc" id="acc-16"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="17">
      <div class="card-top"><div class="card-num">17</div><div class="card-name">Heikin Ashi Trend</div></div>
      <div class="card-signals" id="sigs-17"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-17"></div><div class="card-acc" id="acc-17"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="18">
      <div class="card-top"><div class="card-num">18</div><div class="card-name">TEMA Crossover</div></div>
      <div class="card-signals" id="sigs-18"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-18"></div><div class="card-acc" id="acc-18"><span class="acc-none pct-none">—</span></div></div>
    </div>
  </div>

  <!-- PİYASA YAPISI -->
  <div class="section-title">🏗 Piyasa Yapısı</div>
  <div class="grid">
    <div class="card" data-algo="19">
      <div class="card-top"><div class="card-num">19</div><div class="card-name">ADX Market Regime</div></div>
      <div class="card-signals" id="sigs-19"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-19"></div><div class="card-acc" id="acc-19"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="20">
      <div class="card-top"><div class="card-num">20</div><div class="card-name">Open Interest Div.</div></div>
      <div class="card-signals" id="sigs-20"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-20"></div><div class="card-acc" id="acc-20"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="21">
      <div class="card-top"><div class="card-num">21</div><div class="card-name">Fear &amp; Greed</div></div>
      <div class="card-signals" id="sigs-21"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-21"></div><div class="card-acc" id="acc-21"><span class="acc-none pct-none">—</span></div></div>
    </div>
  </div>

  <!-- ANALİZ SİSTEMLERİ -->
  <div class="section-title">🤝 Aktif Sistem Algoritmaları</div>
  <div class="grid">
    <div class="card" data-algo="22">
      <div class="card-top"><div class="card-num">22</div><div class="card-name">Analiz-1 (RSI+MACD+EMA)</div></div>
      <div class="card-signals" id="sigs-22"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-22"></div><div class="card-acc" id="acc-22"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="23">
      <div class="card-top"><div class="card-num">23</div><div class="card-name">Analiz-9 (Trend+MR+OF+Fund)</div></div>
      <div class="card-signals" id="sigs-23"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-23"></div><div class="card-acc" id="acc-23"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="24">
      <div class="card-top"><div class="card-num">24</div><div class="card-name">Analiz-10 (A1+A9 Konsensüs)</div></div>
      <div class="card-signals" id="sigs-24"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-24"></div><div class="card-acc" id="acc-24"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="25">
      <div class="card-top"><div class="card-num">25</div><div class="card-name">Parabolic SAR + ADX</div></div>
      <div class="card-signals" id="sigs-25"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-25"></div><div class="card-acc" id="acc-25"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="26">
      <div class="card-top"><div class="card-num">26</div><div class="card-name">MACD Histogram Diverjansı</div></div>
      <div class="card-signals" id="sigs-26"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-26"></div><div class="card-acc" id="acc-26"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="27">
      <div class="card-top"><div class="card-num">27</div><div class="card-name">Stochastic RSI (14) K/D</div></div>
      <div class="card-signals" id="sigs-27"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-27"></div><div class="card-acc" id="acc-27"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="28">
      <div class="card-top"><div class="card-num">28</div><div class="card-name">Triple EMA (8-21-55)</div></div>
      <div class="card-signals" id="sigs-28"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-28"></div><div class="card-acc" id="acc-28"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="29">
      <div class="card-top"><div class="card-num">29</div><div class="card-name">Hull Moving Average (HMA)</div></div>
      <div class="card-signals" id="sigs-29"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-29"></div><div class="card-acc" id="acc-29"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="30">
      <div class="card-top"><div class="card-num">30</div><div class="card-name">Keltner Kanalı (20,2)</div></div>
      <div class="card-signals" id="sigs-30"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-30"></div><div class="card-acc" id="acc-30"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="31">
      <div class="card-top"><div class="card-num">31</div><div class="card-name">Donchian Kanalı (20)</div></div>
      <div class="card-signals" id="sigs-31"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-31"></div><div class="card-acc" id="acc-31"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="32">
      <div class="card-top"><div class="card-num">32</div><div class="card-name">VWAP + Hacim Profili</div></div>
      <div class="card-signals" id="sigs-32"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-32"></div><div class="card-acc" id="acc-32"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="33">
      <div class="card-top"><div class="card-num">33</div><div class="card-name">Money Flow Index (MFI)</div></div>
      <div class="card-signals" id="sigs-33"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-33"></div><div class="card-acc" id="acc-33"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="34">
      <div class="card-top"><div class="card-num">34</div><div class="card-name">Random Forest Classifier</div></div>
      <div class="card-signals" id="sigs-34"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-34"></div><div class="card-acc" id="acc-34"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="35">
      <div class="card-top"><div class="card-num">35</div><div class="card-name">Markov Zinciri Modeli</div></div>
      <div class="card-signals" id="sigs-35"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-35"></div><div class="card-acc" id="acc-35"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="36">
      <div class="card-top"><div class="card-num">36</div><div class="card-name">SuperTrend v2 (7,2.0)</div></div>
      <div class="card-signals" id="sigs-36"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-36"></div><div class="card-acc" id="acc-36"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="37">
      <div class="card-top"><div class="card-num">37</div><div class="card-name">Ichimoku Cloud v2 (TK+Bulut)</div></div>
      <div class="card-signals" id="sigs-37"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-37"></div><div class="card-acc" id="acc-37"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="38">
      <div class="card-top"><div class="card-num">38</div><div class="card-name">RSI Diverjansı (14) Katı</div></div>
      <div class="card-signals" id="sigs-38"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-38"></div><div class="card-acc" id="acc-38"><span class="acc-none pct-none">—</span></div></div>
    </div>
    <div class="card" data-algo="39">
      <div class="card-top"><div class="card-num">39</div><div class="card-name">H1 Profesyonel Kombinasyon</div></div>
      <div class="card-signals" id="sigs-39"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">ETH</div><div class="sig-loading sig-pill">SOL</div></div>
      <div class="card-footer"><div class="mini-chart" id="chart-39"></div><div class="card-acc" id="acc-39"><span class="acc-none pct-none">—</span></div></div>
    </div>
  </div>

</div><!-- /main-left -->

<!-- Sağ kolon -->
<div class="main-right">
  <div class="rank-box">
    <div class="rank-title">🏆 Algoritma Başarısı</div>
    <div id="rank-list"><div class="rank-empty">İlk işlemler kapandıktan sonra burada görünecek</div></div>
  </div>

  <!-- Sembol bazlı breakdown -->
  <div class="rank-box" style="margin-top:14px">
    <div class="rank-title" style="margin-bottom:10px">📊 Sembol Bazlı</div>
    <!-- Filtre tabs -->
    <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:12px">
      <button id="sym-tab-BTC" onclick="setSym('BTC')"
        style="flex:1;min-width:36px;padding:4px 0;border-radius:8px;border:none;cursor:pointer;font-size:10px;font-weight:700;
               background:#c8f135;color:#0d0d0d">BTC</button>
      <button id="sym-tab-ETH" onclick="setSym('ETH')"
        style="flex:1;min-width:36px;padding:4px 0;border-radius:8px;border:none;cursor:pointer;font-size:10px;font-weight:700;
               background:#1c1c1e;color:#555">ETH</button>
      <button id="sym-tab-SOL" onclick="setSym('SOL')"
        style="flex:1;min-width:36px;padding:4px 0;border-radius:8px;border:none;cursor:pointer;font-size:10px;font-weight:700;
               background:#1c1c1e;color:#555">SOL</button>
    </div>
    <div id="sym-rank-list"><div class="rank-empty">Veri bekleniyor…</div></div>
  </div>
</div><!-- /main-right -->

</div><!-- /main-inner -->
</div><!-- /main -->
</div><!-- /app -->

<script>
const SYMS = ["BTC","ETH","SOL"];

function pillClass(sig){
  if(sig==="UP")      return "sig-up";
  if(sig==="DOWN")    return "sig-down";
  if(sig==="NEUTRAL") return "sig-neutral";
  return "sig-na";
}
function pillLabel(sym, sig){
  if(sig==="UP")      return sym+" ▲ Artar";
  if(sig==="DOWN")    return sym+" ▼ Düşer";
  if(sig==="NEUTRAL") return sym+" → Nötr";
  return sym+" —";
}

function renderSignals(data){
  const sigs = data.signals || {};
  // 13,14 sabit (yön yok); diğerleri güncellenir
  const dynamic = [1,2,3,4,5,6,7,8,9,10,11,12,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39];
  for(const n of dynamic){
    const el = document.getElementById("sigs-"+n);
    if(!el) continue;
    const entry = sigs[String(n)];
    if(!entry){ el.innerHTML = '<div class="sig-na sig-pill">Veri yok</div>'; continue; }
    el.innerHTML = SYMS.map(s=>`<div class="sig-pill ${pillClass(entry[s])}">${pillLabel(s,entry[s])}</div>`).join("");
  }
}

function renderConsensus(data){
  const con = data.consensus || {};
  const rows = document.getElementById("cb-rows");
  const upd  = document.getElementById("cb-updated");
  const nxt  = document.getElementById("cb-next");
  const per  = document.getElementById("cb-period");
  upd.textContent = data.updated ? "🕐 "+data.updated+" güncellendi" : "";
  nxt.textContent = "";
  if(per && data.period_start && data.period_end)
    per.textContent = "📅 "+data.period_start+" → "+data.period_end+" analizi";

  rows.innerHTML = SYMS.map(sym=>{
    const c = con[sym] || {UP:0,DOWN:0,NEUTRAL:0,total:13};
    const tot = c.total || 13;
    const upPct  = Math.round(c.UP/tot*100);
    const dnPct  = Math.round(c.DOWN/tot*100);
    const dom    = c.UP > c.DOWN ? "UP" : c.DOWN > c.UP ? "DOWN" : "NEUTRAL";
    const lbl    = dom==="UP" ? `<span class="cb-label lbl-up">${c.UP}/${tot} ▲ Artar</span>`
                 : dom==="DOWN" ? `<span class="cb-label lbl-dn">${c.DOWN}/${tot} ▼ Düşer</span>`
                 : `<span class="cb-label lbl-neu">= Nötr</span>`;
    return `<div class="cb-row">
      <span class="cb-sym">${sym}</span>
      <div class="cb-bar-wrap">
        <div style="display:flex;height:100%;">
          <div class="cb-bar-up" style="width:${upPct}%"></div>
          <div class="cb-bar-dn" style="width:${dnPct}%"></div>
        </div>
      </div>
      ${lbl}
    </div>
    <div class="cb-detail">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;▲${c.UP} ▼${c.DOWN} =${c.NEUTRAL}</div>`;
  }).join("");
}

function renderRanking(acc){
  const el = document.getElementById("rank-list");
  const entries = Object.entries(acc)
    .filter(([k,v]) => v.total > 0)
    .map(([k,v]) => ({
      num: k,
      name: ALGO_NAMES[k] || "Algo "+k,
      total: v.total,
      correct: v.correct,
      wr: Math.round(v.correct / v.total * 100)
    }))
    .sort((a,b) => b.wr - a.wr || b.total - a.total);

  if(!entries.length){
    el.innerHTML = '<div class="rank-empty">İlk işlemler kapandıktan sonra burada görünecek</div>';
    return;
  }

  el.innerHTML = entries.map((e,i) => {
    const posClass = i===0?"top1":i===1?"top2":i===2?"top3":"";
    const wrClass  = e.wr>=60?"wr-good":e.wr>=50?"wr-ok":"wr-bad";
    const medal    = i===0?"🥇":i===1?"🥈":i===2?"🥉":i+1;
    return `<div class="rank-item">
      <span class="rank-pos ${posClass}">${medal}</span>
      <div class="rank-info">
        <div class="rank-name">${e.name}</div>
        <div class="rank-sub">${e.correct}/${e.total} işlem</div>
        <div class="rank-bar-wrap"><div class="rank-bar-fill" style="width:${e.wr}%"></div></div>
      </div>
      <span class="rank-wr ${wrClass}">%${e.wr}</span>
    </div>`;
  }).join("");
}

let _accData = {};
let _activeSym = "BTC";

function setSym(sym){
  _activeSym = sym;
  ["BTC","ETH","SOL"].forEach(s => {
    const btn = document.getElementById("sym-tab-"+s);
    if(!btn) return;
    btn.style.background = s===sym ? "#c8f135" : "#1c1c1e";
    btn.style.color       = s===sym ? "#0d0d0d" : "#555";
  });
  renderSymRanking(_accData, sym);
}

function renderSymRanking(acc, sym){
  const el = document.getElementById("sym-rank-list");
  if(!el) return;
  const entries = Object.entries(acc)
    .filter(([k,v]) => v.by_sym && v.by_sym[sym] && v.by_sym[sym].total > 0)
    .map(([k,v]) => ({
      name: ALGO_NAMES[k] || "Algo "+k,
      total: v.by_sym[sym].total,
      correct: v.by_sym[sym].correct,
      wr: Math.round(v.by_sym[sym].correct / v.by_sym[sym].total * 100)
    }))
    .sort((a,b) => b.wr - a.wr || b.total - a.total);

  if(!entries.length){
    el.innerHTML = '<div class="rank-empty">Henüz '+sym+' verisi yok</div>';
    return;
  }
  el.innerHTML = entries.map((e,i) => {
    const wrClass = e.wr>=60?"wr-good":e.wr>=50?"wr-ok":"wr-bad";
    return `<div class="rank-item">
      <span class="rank-pos" style="color:#555">${i+1}</span>
      <div class="rank-info">
        <div class="rank-name">${e.name}</div>
        <div class="rank-sub">${e.correct}/${e.total} doğru</div>
        <div class="rank-bar-wrap"><div class="rank-bar-fill" style="width:${e.wr}%"></div></div>
      </div>
      <span class="rank-wr ${wrClass}">%${e.wr}</span>
    </div>`;
  }).join("");
}

const ALGO_NAMES = {
  "1":"EMA Crossover","2":"MACD Divergence","3":"Supertrend","4":"Ichimoku","5":"RSI Divergence",
  "6":"Stochastic RSI","7":"Bollinger Bands","8":"VWAP","9":"OBV","10":"Volume Profile",
  "11":"Mean Reversion","12":"Pairs Trading","13":"Grid Bot","14":"LSTM","15":"Multi-TF",
  "16":"ATR Breakout","17":"Heikin Ashi","18":"TEMA Crossover","19":"ADX Regime",
  "20":"OI Divergence","21":"Fear & Greed","22":"Analiz-1","23":"Analiz-9","24":"Analiz-10",
  "25":"Parabolic SAR+ADX","26":"MACD Hist. Div","27":"Stoch RSI K/D","28":"Triple EMA",
  "29":"Hull MA","30":"Keltner Kanal","31":"Donchian Kanal","32":"VWAP+Vol Profile",
  "33":"Money Flow (MFI)","34":"Random Forest","35":"Markov Zinciri","36":"SuperTrend v2",
  "37":"Ichimoku v2","38":"RSI Div (Katı)","39":"H1 Kombinasyon"
};

function renderTopSymAlgos(acc){
  const el = document.getElementById("top-sym-algos");
  if(!el) return;
  const SYMS = ["BTC","ETH","SOL"];
  const MIN_TRADES = 1;
  const items = [];

  for(const sym of SYMS){
    let best = null, bestWr = -1, bestStat = "", bestSym = false;

    for(const [num, data] of Object.entries(acc)){
      // Önce sembol-bazlı bak
      const sd = data.by_sym && data.by_sym[sym];
      if(sd && sd.total >= MIN_TRADES){
        const wr = sd.correct / sd.total;
        if(wr > bestWr || (wr === bestWr && !bestSym)){
          bestWr = wr; best = num;
          bestStat = `${sd.correct}/${sd.total}`; bestSym = true;
        }
        continue;
      }
      // Sembol verisi yoksa genel veriye bak (daha düşük öncelik)
      if(!bestSym && data.total >= MIN_TRADES){
        const wr = data.correct / data.total;
        if(wr > bestWr){ bestWr = wr; best = num; bestStat = `${data.correct}/${data.total}`; }
      }
    }
    if(best !== null && bestWr >= 0){
      const pct = Math.round(bestWr * 100);
      items.push(`<div class="sym-best">
        <span class="sym-best-sym">${sym}</span>
        <span><span class="sym-best-algo">${ALGO_NAMES[best] || "Algo "+best}</span><span class="sym-best-stat">%${pct} · ${bestStat}</span></span>
      </div>`);
    }
  }
  el.innerHTML = items.length ? items.join("") : '<span style="font-size:12px;color:#444">Veri birikmesi bekleniyor…</span>';
}

function updateCardAccBadges(acc){
  for(let n=1; n<=24; n++){
    const accEl   = document.getElementById("acc-"+n);
    const chartEl = document.getElementById("chart-"+n);
    if(!accEl) continue;

    const data = acc[String(n)];
    if(!data || !data.total){
      accEl.innerHTML = '<span class="acc-none pct-none">—</span>';
      if(chartEl) chartEl.innerHTML = Array(6).fill('<div class="mini-bar bar-empty" style="height:100%"></div>').join('');
      continue;
    }

    const wr  = data.correct / data.total;
    const pct = Math.round(wr * 100);
    const pctCls = wr >= 0.6 ? "pct-good" : wr >= 0.45 ? "pct-ok" : "pct-bad";
    accEl.innerHTML = `<div class="acc-pct ${pctCls}">%${pct}</div><div class="acc-cnt">${data.correct}/${data.total} işlem</div>`;

    // Mini bar chart — her bar 1 işlemi temsil eder (max 8 bar)
    if(chartEl){
      const total = Math.min(data.total, 8);
      const wins  = Math.round(wr * total);
      const maxH  = 24;
      let bars = '';
      for(let i=0; i<total; i++){
        const isWin = i < wins;
        const h = maxH * (0.3 + 0.7 * (i + 1) / total);
        bars += `<div class="mini-bar ${isWin?'bar-win':'bar-loss'}" style="height:${h.toFixed(0)}px"></div>`;
      }
      // Boş yerler dolduralım
      for(let i=total; i<6; i++){
        bars += `<div class="mini-bar bar-empty" style="height:${(maxH*0.2).toFixed(0)}px"></div>`;
      }
      chartEl.innerHTML = bars;
    }
  }
}

function sortCardsByAccuracy(acc){
  // Tüm kartları topla
  const allCards = Array.from(document.querySelectorAll('.main-left .card'));
  if(!allCards.length) return;

  // Başarı oranını hesapla
  const wr = n => {
    const d = acc[String(n)];
    if(!d || !d.total) return -1;
    return d.correct / d.total;
  };

  // Sırala: başarısı olanlar önce (desc), sonra veri olmayanlar
  allCards.sort((a, b) => {
    const na = parseInt(a.dataset.algo), nb = parseInt(b.dataset.algo);
    const wa = wr(na), wb = wr(nb);
    if(wa < 0 && wb < 0) return na - nb; // her ikisi de veri yok → numara sırasıyla
    if(wa < 0) return 1;
    if(wb < 0) return -1;
    return wb - wa;
  });

  // Mevcut section-title ve grid'leri kaldır, tek grid oluştur
  const mainLeft = document.querySelector('.main-left');
  mainLeft.querySelectorAll('.section-title').forEach(el => el.remove());
  mainLeft.querySelectorAll('.grid').forEach(el => el.remove());

  const secEl = document.createElement('div');
  secEl.className = 'section-title';
  secEl.innerHTML = '🏆 Başarı Sıralaması';
  mainLeft.appendChild(secEl);

  const grid = document.createElement('div');
  grid.className = 'grid';
  allCards.forEach(c => grid.appendChild(c));
  mainLeft.appendChild(grid);
}

async function loadAccuracy(){
  try{
    const r = await fetch("/poly/api/algo_accuracy");
    const d = await r.json();
    _accData = d;
    renderRanking(d);
    renderSymRanking(d, _activeSym);
    updateCardAccBadges(d);
    sortCardsByAccuracy(d);
    renderTopSymAlgos(d);
    // Toplam işlem sayısı (en yüksek totalli algo baz alınır)
    const totEl = document.getElementById("cb-total");
    if(totEl){
      const maxTotal = Math.max(...Object.values(d).map(x => x.total || 0));
      if(maxTotal > 0){
        const hours = Math.round(maxTotal / 3);
        totEl.textContent = `📊 ${maxTotal} ölçüm · ${hours} saatlik veri`;
      }
    }
  }catch(e){ console.error(e); }
}

async function load(){
  try{
    const r = await fetch("/poly/api/algo_signals");
    const d = await r.json();
    renderConsensus(d);
    renderSignals(d);
  }catch(e){ console.error(e); }
}
load();
loadAccuracy();
// Her 5 dakikada yenile
setInterval(load, 5*60*1000);
setInterval(loadAccuracy, 10*60*1000);
</script>
</body>
</html>"""

AYARLAR_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%23c8f135'/><text y='72' x='50' text-anchor='middle' font-size='62' font-family='system-ui,sans-serif' font-weight='900' fill='%230d0d0d'>P</text></svg>">
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
  <a class="nav-item" href="/algoritma"><span class="nav-dot"></span>Algoritma</a>
  <a class="nav-item" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="/analizler"><span class="nav-dot"></span>Analizler</a>
  <a class="nav-item" href="/poly/gecmis"><span class="nav-dot"></span>Geçmiş</a>
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
}

async function save() {
  const btn = document.getElementById('save-btn');
  btn.classList.add('loading'); btn.textContent = 'Kaydediliyor...';
  const body = {
    amount_agree:    parseFloat(document.getElementById('amount_agree').value),
    amount_a5_only:  parseFloat(document.getElementById('amount_a5_only').value),
    amount_a9_only:  parseFloat(document.getElementById('amount_a9_only').value),
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
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%23c8f135'/><text y='72' x='50' text-anchor='middle' font-size='62' font-family='system-ui,sans-serif' font-weight='900' fill='%230d0d0d'>P</text></svg>">
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
  .hm-analiz-tab { background:#111; border:1px solid #2a2a2a; color:#555; font-size:12px; font-weight:600;
                   padding:5px 13px; border-radius:20px; cursor:pointer; transition:.2s; }
  .hm-analiz-tab:hover { border-color:#444; color:#ccc; }
  .hm-analiz-tab.active { background:#1a2e1a; border-color:#4ade80; color:#4ade80; }

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
  <a class="nav-item" href="/algoritma"><span class="nav-dot"></span>Algoritma</a>
  <a class="nav-item active" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="/analizler"><span class="nav-dot"></span>Analizler</a>
  <a class="nav-item" href="/poly/gecmis"><span class="nav-dot"></span>Geçmiş</a>
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
      <button class="hm-filter" id="hm-btc-btn" onclick="setFilter(this,'BTC')">BTC</button>
      <button class="hm-filter" id="hm-eth-btn" onclick="setFilter(this,'ETH')">ETH</button>
      <button class="hm-filter" id="hm-sol-btn" onclick="setFilter(this,'SOL')">SOL</button>
    </div>
  </div>
  <!-- Analiz sekmeleri -->
  <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px">
    {{ harita_tabs|safe }}
  </div>
  <div class="page-sub" id="hm-subtitle">5. Analiz — gün × saat kazanma oranı</div>

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
const _ANALIZ_LABELS = {{ harita_labels|safe }};
const _HEATMAP_SYMS_MAP = {{ harita_heatmap_syms|safe }};
let _data = null, _sym = 'ALL', _analiz = 'analiz5';

function hmColor(wr,t){ if(!t)return'#1a1a1a'; if(wr>=70)return'#166534'; if(wr>=55)return'#14532d'; if(wr>=50)return'#365314'; if(wr>=40)return'#78350f'; return'#450a0a'; }
function hmTxt(wr,t){ if(!t)return'#333'; if(wr>=55)return'#4ade80'; if(wr>=50)return'#c8f135'; if(wr>=40)return'#fbbf24'; return'#f87171'; }

async function load() {
  const r = await fetch(`/poly/api/heatmap?sym=${_sym}&analiz=${_analiz}`);
  const d = await r.json();
  _data   = d.cells;
  renderSummary(d.summary, d.sym_breakdown || []);
  renderGrid(_data);
  const lbl = _ANALIZ_LABELS[_analiz] || _analiz;
  document.getElementById('hm-subtitle').textContent = `${lbl} — gün × saat kazanma oranı`;
}

function setAnaliz(btn, key) {
  document.querySelectorAll('.hm-analiz-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _analiz = key; _data = null;
  updateHmSymFilters();
  load();
}

function updateHmSymFilters() {
  const allowed = _HEATMAP_SYMS_MAP[_analiz] || ['BTC', 'ETH', 'SOL'];
  ['BTC', 'ETH', 'SOL'].forEach(s => {
    const btn = document.getElementById('hm-' + s.toLowerCase() + '-btn');
    if (btn) btn.style.display = allowed.includes(s) ? '' : 'none';
  });
  if (_sym !== 'ALL' && !allowed.includes(_sym)) {
    _sym = 'ALL';
    document.querySelectorAll('.hm-filter').forEach(b => {
      b.classList.toggle('active', b.textContent.trim() === 'Tümü');
    });
  }
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

  const r = await fetch(`/poly/api/heatmap/detail?dow=${dow}&hour=${hour}&sym=${_sym}&analiz=${_analiz}`);
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

updateHmSymFilters();
load();
</script>
</body>
</html>"""

HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%23c8f135'/><text y='72' x='50' text-anchor='middle' font-size='62' font-family='system-ui,sans-serif' font-weight='900' fill='%230d0d0d'>P</text></svg>">
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

  /* Top3 analiz kartları */
  .top3-card { background:#111; border:1px solid #1e1e1e; border-radius:14px; padding:16px; display:flex; gap:12px; align-items:flex-start; }
  .top3-divider { height:1px; background:#1e1e1e; margin:6px 0 7px; }
  .top3-donut { position:relative; width:64px; height:64px; flex-shrink:0; }
  .top3-donut svg { transform:rotate(-90deg); }
  .top3-donut-center { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }
  .top3-wr { font-size:13px; font-weight:800; line-height:1; }
  .top3-wrlbl { font-size:8px; color:#555; margin-top:1px; }
  .top3-info { flex:1; min-width:0; }
  .top3-label { font-size:13px; font-weight:700; margin-bottom:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .top3-row { display:flex; justify-content:space-between; margin-bottom:2px; }
  .top3-key { font-size:11px; color:#666; }
  .top3-val { font-size:11px; font-weight:600; }
  .top3-pills { display:flex; gap:3px; margin-top:6px; flex-wrap:wrap; }
  .top3-pill { font-size:9px; padding:1px 5px; border-radius:12px; background:#1a1a1a; color:#888; }
  .top3-pill.good { background:#14291e; color:#4ade80; }
  .top3-pill.ok   { background:#1e1e14; color:#a3e635; }
  .top3-pill.bad  { background:#291414; color:#f87171; }
  @media(max-width:700px){ .top3-desktop-only { display:none !important; } }

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
  <a class="nav-item" href="/algoritma"><span class="nav-dot"></span>Algoritma</a>
  <a class="nav-item" id="nav-heatmap" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="/analizler"><span class="nav-dot"></span>Analizler</a>
  <a class="nav-item" href="/poly/gecmis"><span class="nav-dot"></span>Geçmiş</a>
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

      <!-- En İyi 3 Analiz (sadece desktop) -->
      <div class="section-title top3-desktop-only" style="margin:20px 0 12px">🏆 En Başarılı Analizler</div>
      <div id="top3-analizler" class="top3-desktop-only" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px">
        <div style="color:#555;font-size:13px;padding:16px">Yükleniyor…</div>
      </div>

      <!-- Mobil pozisyonlar (desktop'ta gizli) -->
      <div class="mobile-positions">
        <div class="risk-banner" style="margin-top:16px">
          <div>
            <span class="risk-label">Toplam Riskteki</span>
            <div style="font-size:14px;font-weight:700;color:#3d4d00;margin-top:3px">Kazanılacak: <span id="total-towin-mob">$—</span></div>
          </div>
          <span class="risk-val" id="total-risk-mob">$—</span>
        </div>
        <div class="section-title" style="margin:16px 0 12px">Açık Pozisyonlar</div>
        <div class="positions" id="positions-mob">
          <div class="empty">Yükleniyor...</div>
        </div>
        <div class="section-title" style="margin:20px 0 12px">Son İşlemler</div>
        <div id="recent-trades-mob"><div style="color:#666;font-size:13px">Yükleniyor...</div></div>
      </div>

    </div>

    <!-- SAĞ: risk + açık pozisyonlar -->
    <div class="overview-right">
      <div class="risk-banner">
        <div>
          <span class="risk-label">Toplam Riskteki</span>
          <div style="font-size:14px;font-weight:700;color:#3d4d00;margin-top:3px">Kazanılacak: <span id="total-towin">$—</span></div>
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
  <!-- Algoritma performansı -->
  <div class="rp-section">
    <div class="rp-title">Algoritma Performansı</div>
    <div id="algo-stats"><div style="color:#666;font-size:13px">Yükleniyor...</div></div>
  </div>

  <div class="rp-section">
    <div class="rp-title">Son İşlemler</div>
    <div id="recent-trades"><div style="color:#666;font-size:13px">Yükleniyor...</div></div>
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
    const twVal = totalToWin > 0 ? '$' + totalToWin.toFixed(2) : '—';
    const twEl = document.getElementById('total-towin');
    if (twEl) twEl.textContent = twVal;
    const twMob = document.getElementById('total-towin-mob');
    if (twMob) twMob.textContent = twVal;

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
          ${p.closable ? `<div class="close-btn-wrap">
            <button class="close-btn" onclick="closePosition('${p.analiz_key}','${p.symbol}',this)">Pozisyonu Kapat</button>
          </div>` : ''}
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
    slotEl.innerHTML = (ss.top_slots || []).map((sl, i) => {
      const medals  = ['🥇','🥈','🥉'];
      const barW    = Math.round(sl.wr);
      const hour    = sl.hour_int;
      const wrColor = sl.wr >= 80 ? '#4ade80' : sl.wr >= 60 ? '#a3e635' : '#c8f135';
      const dayTags = (sl.day_names || []).map(d =>
        `<span style="background:#1c1c1e;color:#aaa;font-size:10px;padding:2px 7px;border-radius:6px;font-weight:600">${d}</span>`
      ).join(' ');
      const dayCountStr = sl.good_days > 1
        ? `<span style="color:#c8f135;font-weight:700">${sl.good_days} farklı gün</span>`
        : `<span style="color:#666">1 gün</span>`;
      return `<div onclick="openSlotPopup(-1,${hour})"
        style="padding:8px 10px;margin-bottom:6px;background:#111;border-radius:10px;
               cursor:pointer;transition:.15s;border:1px solid #1f1f1f"
        onmouseover="this.style.borderColor='#c8f135'" onmouseout="this.style.borderColor='#1f1f1f'">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <span style="font-size:12px;font-weight:800">${medals[i]} ${sl.hour}</span>
          <span style="font-size:13px;font-weight:800;color:${wrColor}">${sl.wr}%</span>
        </div>
        <div style="display:flex;gap:3px;flex-wrap:wrap;margin-bottom:5px">${dayTags}</div>
        <div style="height:2px;background:#1c1c1e;border-radius:4px;margin-bottom:5px">
          <div style="height:100%;width:${barW}%;background:${wrColor};border-radius:4px"></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:10px;color:#666">${sl.w}K / ${sl.t} işlem · ${dayCountStr}</span>
          <span style="font-size:10px;color:#444;background:#1c1c1e;padding:1px 6px;border-radius:5px">detay →</span>
        </div>
      </div>`;
    }).join('') || '<div style="color:#666;font-size:13px">Veri yok</div>';

    // Son işlemler (sağ panel + mobil)
    const rt = document.getElementById('recent-trades');
    const recentHTML = s.recent.map(t => {
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
    if (rt) rt.innerHTML = recentHTML;
    const rtMob = document.getElementById('recent-trades-mob');
    if (rtMob) rtMob.innerHTML = recentHTML;

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

// ── Top 3 Analizler ──────────────────────────────────────
function top3DonutSVG(pct, color){
  const r=22,cx=32,cy=32,circ=2*Math.PI*r;
  const fill=circ*(pct/100), bg=circ-fill;
  return `<svg width="64" height="64" viewBox="0 0 64 64">
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#1e1e1e" stroke-width="8"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="8"
      stroke-dasharray="${fill} ${bg}" stroke-linecap="round"/>
  </svg>`;
}
function top3PillClass(wr){ return wr>=60?'good':wr>=50?'ok':'bad'; }
function top3Color(wr){ return wr>=60?'#4ade80':wr>=55?'#a3e635':wr>=50?'#c8f135':wr>=45?'#fb923c':'#f87171'; }

async function loadTop3(){
  try{
    const r = await fetch('/poly/api/analizler');
    if(!r.ok) return;
    const data = await r.json();
    if(!Array.isArray(data)) return;
    const top3 = data.slice(0,3);
    document.getElementById('top3-analizler').innerHTML = top3.map((a,i) => {
      const color  = top3Color(a.wr);
      const pnlCls = a.pnl>0?'color:#4ade80':a.pnl<0?'color:#f87171':'color:#888';
      const pnlStr = (a.pnl>=0?'+':'')+'$'+Math.abs(a.pnl).toFixed(2);
      const medals = ['🥇','🥈','🥉'];
      const balStr = '$'+a.balance.toFixed(2);
      const loss   = a.total - a.wins;
      const openTxt = a.open ? `<div class="top3-row"><span class="top3-key">Açık Poz</span><span class="top3-val" style="color:#c8f135">${a.open}</span></div>` : '';
      const pills  = a.sym_stats.map(s=>
        `<span class="top3-pill ${top3PillClass(s.wr)}">${s.sym} %${s.wr}</span>`
      ).join('');
      return `<div class="top3-card">
        <div class="top3-donut">
          ${top3DonutSVG(a.wr, color)}
          <div class="top3-donut-center">
            <div class="top3-wr" style="color:${color}">${a.total?a.wr+'%':'—'}</div>
            <div class="top3-wrlbl">WR</div>
          </div>
        </div>
        <div class="top3-info">
          <div class="top3-label">${medals[i]} ${a.label}</div>
          <div class="top3-divider"></div>
          <div class="top3-row">
            <span class="top3-key">Toplam İşlem</span>
            <span class="top3-val">${a.total}</span>
          </div>
          <div class="top3-row">
            <span class="top3-key">Kazanan / Kaybeden</span>
            <span class="top3-val"><span style="color:#4ade80">${a.wins}W</span> / <span style="color:#f87171">${loss}L</span></span>
          </div>
          <div class="top3-row">
            <span class="top3-key">P&amp;L</span>
            <span class="top3-val" style="${pnlCls}">${pnlStr}</span>
          </div>
          <div class="top3-row">
            <span class="top3-key">Bakiye</span>
            <span class="top3-val">${balStr}</span>
          </div>
          ${openTxt}
          <div class="top3-pills">${pills}</div>
        </div>
      </div>`;
    }).join('');
  }catch(e){ console.error('top3',e); }
}

loadTop3();
setInterval(loadTop3, 60000);

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
  const title = dow >= 0
    ? `${_dayNames[dow]} ${String(hour).padStart(2,'0')}:00`
    : `${String(hour).padStart(2,'0')}:00 — Tüm Günler`;
  document.getElementById('slot-title').textContent = title;
  document.getElementById('slot-body').innerHTML = '<div style="color:#555;text-align:center;padding:24px">Yükleniyor...</div>';

  const url = dow >= 0
    ? `/poly/api/heatmap/detail?dow=${dow}&hour=${hour}&sym=ALL`
    : `/poly/api/heatmap/detail?hour=${hour}&sym=ALL`;
  const r = await fetch(url);
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
}

def _read_settings() -> dict:
    defaults = {
        "amount_agree": 15.0, "amount_a5_only": 8.0, "amount_a9_only": 6.0,
    }
    if os.path.exists(_SETTINGS_FILE):
        with open(_SETTINGS_FILE) as f:
            data = json.load(f)
        for k in defaults:
            if k in data:
                defaults[k] = data[k]
    return defaults

@app.route("/poly/api/algo_signals")
def api_algo_signals():
    if _auth_required(): return jsonify({"error": "unauthorized"}), 401
    path = "/tmp/algo_signals.json"
    if not os.path.exists(path):
        return jsonify({"error": "no data", "signals": {}, "consensus": {}})
    with open(path) as f:
        data = json.load(f)
    # Pasif coinler — eski cache'ten gelen veriyi temizle
    for sym in _DISABLED_SYMS:
        if isinstance(data.get("consensus"), dict):
            data["consensus"].pop(sym, None)
    for entry in (data.get("signals") or {}).values():
        if isinstance(entry, dict):
            for sym in _DISABLED_SYMS:
                entry.pop(sym, None)
            entry.pop("HYPE", None)
    if isinstance(data.get("consensus"), dict):
        data["consensus"].pop("HYPE", None)
    return jsonify(data)

@app.route("/poly/api/algo_accuracy")
def api_algo_accuracy():
    if _auth_required(): return jsonify({"error": "unauthorized"}), 401
    path = os.path.join(_DIR_POLY, "algo_accuracy.json")
    if not os.path.exists(path):
        return jsonify({})
    with open(path) as f:
        return jsonify(json.load(f))

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

@app.route("/algoritma")
@app.route("/algoritma/")
def algoritma():
    if _auth_required(): return redirect("/poly/login")
    return render_template_string(ALGORITMA_HTML)

@app.route("/poly")
@app.route("/poly/")
def dashboard():
    if _auth_required(): return redirect("/poly/login")
    return render_template_string(HTML)

@app.route("/harita")
@app.route("/harita/")
def harita():
    if _auth_required(): return redirect("/poly/login")
    labels = {k: v for k, v in _HARITA_TAB_ANALYSES}
    return render_template_string(
        HARITA_HTML,
        harita_tabs=_harita_tabs_html(),
        harita_labels=json.dumps(labels, ensure_ascii=False),
        harita_heatmap_syms=json.dumps(_HEATMAP_SYMS, ensure_ascii=False),
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
