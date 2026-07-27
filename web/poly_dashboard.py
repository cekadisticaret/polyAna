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

from flask import Flask, jsonify, make_response, render_template_string, request, session, redirect, url_for

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "temmuzPoly"))

_DIR_POLY = os.path.join(os.path.dirname(__file__), "..", "temmuzPoly")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PANEL_STATS_ANALIZ = "analiz1"  # sağ panel: sembol WR + en etkili zaman
_ACTIVE_SYMS = ["BTC", "ETH", "SOL"]

# Sıcaklık haritası: analiz bazlı aktif semboller
_HEATMAP_SYMS = {
    "analiz1":  ["BTC", "SOL"],
    "analiz6":  ["BTC", "SOL"],
    "analiz2":  ["SOL"],
    "analiz2_live": ["SOL"],
    "analiz3":  ["BTC", "SOL", "ETH"],
    "analiz4":  ["BTC", "ETH"],
    "analiz5":  ["BTC", "SOL"],
    "analiz8":  ["BTC", "SOL", "ETH"],
    "analiz10": ["BTC", "SOL"],
    "5m_sol_110": ["SOL"],
    "5m_sol_109": ["SOL"],
    "5m_sol_111": ["SOL"],
    "5m_sol_210": ["SOL"],
    "alfa":       ["BTC", "SOL"],
}
# Sıcaklık haritası sekmesinde birleşik gösterilecek ek history kaynakları
_HEATMAP_MERGE: dict[str, list[str]] = {}
# poly_trader_* dışındaki analiz dosyaları (history, state) — mutlak yol
_CUSTOM_TRADER_FILES: dict[str, tuple[str, str]] = {
    "analiz3": (
        os.path.join(_ROOT, "freqtrade/user_data/analiz3_freqtrade_history.json"),
        os.path.join(_ROOT, "freqtrade/user_data/analiz3_freqtrade_state.json"),
    ),
    "analiz8": (
        os.path.join(_ROOT, "jesse/storage/analiz8_jesse_history.json"),
        os.path.join(_ROOT, "jesse/storage/analiz8_jesse_state.json"),
    ),
}
_DISABLED_SYMS = frozenset({"XRP", "DOGE", "BNB", "HYPE"})
# Algoritma performansı panelinde gösterilmez
_ALGO_STATS_EXCLUDE = frozenset({"manual", "5m_sol_111_shadow"})
# Kaldırılmış trader'lar — diskte history kalsa bile listelenmez
_REMOVED_ANALYSES = frozenset({
    "analiz7", "analiz9", "analiz13", "analiz21", "analiz23", "analiz31", "analiz32",
    "5m_btc_107",
})

# ── Analiz kayıt defteri (harita + heatmap API tek kaynak) ─────
_ANALYSIS_ORDER = [
    "analiz1", "analiz2", "analiz2_live", "analiz5", "analiz3", "analiz8", "analiz4", "analiz6", "analiz10",
    "5m_sol_109", "5m_sol_110", "5m_sol_111", "5m_sol_210",
]
# Sıcaklık haritası sekmeleri — yalnızca bu liste (auto-discover yok)
_HEATMAP_ORDER = [
    "analiz1", "analiz2", "analiz2_live", "analiz5", "analiz3", "analiz8", "analiz4", "analiz6", "analiz10",
    "alfa",
    "5m_sol_109", "5m_sol_110", "5m_sol_111", "5m_sol_210",
]
_HISTORY_ORDER = [
    "analiz2", "analiz1", "analiz4", "analiz6", "analiz5", "analiz3", "analiz8",
    "analiz10", "5m_sol_109", "5m_sol_110", "5m_sol_111", "5m_sol_210",
]
_ANALYSIS_LABELS: dict[str, str] = {
    "analiz1":    "1. Analiz",
    "analiz2":    "2. Analiz (SOL)",
    "analiz3":    "3. Analiz Freqtrade",
    "analiz4":    "4. Analiz",
    "analiz6":    "6. Analiz",
    "analiz5":    "A1 Live",
    "analiz8":    "8. Analiz Jesse",
    "analiz10":   "10. Analiz",
    "5m_sol_109": "15M 109 SOL",
    "5m_sol_110": "15M 110 SOL",
    "5m_sol_111": "15M 111 SOL",
    "5m_sol_210": "15M 210 SOL",
    "alfa":       "ALFA",
    "analiz2_live": "A2 Live",
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
    if key in _CUSTOM_TRADER_FILES:
        return os.path.exists(_CUSTOM_TRADER_FILES[key][0])
    return os.path.exists(os.path.join(_DIR_POLY, f"poly_trader_{key}_state.json"))


def _trader_history_path(key: str) -> str:
    if key in _CUSTOM_TRADER_FILES:
        return _CUSTOM_TRADER_FILES[key][0]
    return os.path.join(_DIR_POLY, f"poly_trader_{key}_history.json")


def _trader_state_path(key: str) -> str:
    if key in _CUSTOM_TRADER_FILES:
        return _CUSTOM_TRADER_FILES[key][1]
    return os.path.join(_DIR_POLY, f"poly_trader_{key}_state.json")


def _enrich_entry_time_fields(t: dict) -> dict:
    if t.get("entry_dow") is not None and t.get("entry_hour_tr") is not None:
        return t
    out = dict(t)
    ts = out.get("entry_time_tr") or out.get("exit_time_tr")
    if ts:
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_TZ_TR)
            else:
                dt = dt.astimezone(_TZ_TR)
            if out.get("entry_dow") is None:
                out["entry_dow"] = dt.weekday()
            if out.get("entry_hour_tr") is None:
                out["entry_hour_tr"] = dt.hour
        except (ValueError, TypeError):
            pass
    elif out.get("entry_hour_tr") is None:
        m = re.match(r"(\d{1,2}):", out.get("hour_label", ""))
        if m:
            out["entry_hour_tr"] = int(m.group(1))
    return out


def _load_trader_history(key: str) -> list:
    path = _trader_history_path(key)
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            hist = json.load(f)
    except Exception:
        return []
    hist = [_enrich_entry_time_fields(t) for t in hist]
    return _filter_hist_for(key, hist)


def _auto_label(key: str) -> str:
    if key in _ANALYSIS_LABELS:
        return _ANALYSIS_LABELS[key]
    m = re.match(r"^analiz(\d+)$", key)
    if m:
        return f"{m.group(1)}. Analiz"
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
        if key in _REMOVED_ANALYSES:
            continue
        if not _trader_exists(key, on_disk) and key not in _ANALYSIS_LABELS:
            continue
        out.append((key, _ANALYSIS_LABELS.get(key, _auto_label(key))))
        seen.add(key)
    for key in sorted(on_disk - seen):
        if key in _REMOVED_ANALYSES:
            continue
        out.append((key, _ANALYSIS_LABELS.get(key, _auto_label(key))))
    return out


def _build_harita_tabs() -> list[tuple[str, str]]:
    on_disk = _discover_trader_keys()
    merged_extra = {k for extras in _HEATMAP_MERGE.values() for k in extras}
    skip_tabs = _REMOVED_ANALYSES | _ALGO_STATS_EXCLUDE | frozenset({"manual"}) | merged_extra
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key in _HEATMAP_ORDER:
        if key in _REMOVED_ANALYSES:
            continue
        if not _trader_exists(key, on_disk) and key not in _ANALYSIS_LABELS:
            continue
        out.append((key, _ANALYSIS_LABELS.get(key, _auto_label(key))))
        seen.add(key)
    for key in sorted(on_disk - seen):
        if key in skip_tabs:
            continue
        out.append((key, _ANALYSIS_LABELS.get(key, _auto_label(key))))
    return out


def _heatmap_history_keys(key: str) -> list[str]:
    keys = [key]
    for extra in _HEATMAP_MERGE.get(key, []):
        if extra not in keys:
            keys.append(extra)
    return keys


def _load_heatmap_history(key: str) -> list:
    """Harita API — birleşik kaynaklar + sembol filtresi."""
    allowed = set(_allowed_syms_for(key))
    hist: list = []
    for k in _heatmap_history_keys(key):
        path = _trader_history_path(k)
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                raw = json.load(f)
        except Exception:
            continue
        for t in raw:
            row = _enrich_entry_time_fields(t)
            sym = row.get("symbol", "").replace("USDT", "")
            if sym in allowed:
                hist.append(row)
    return hist


_ANALYSIS_SYSTEMS = _build_system_list(_ANALYSIS_ORDER)
_HARITA_TAB_ANALYSES = _build_harita_tabs()
_HEATMAP_ANALYSES = dict(_HARITA_TAB_ANALYSES)
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

@app.after_request
def _no_cache_api(response):
    if request.path.startswith("/poly/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response

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

def get_klines(symbol: str, interval="15m", limit=80, start_time_ms: int | None = None):
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time_ms is not None:
        params["startTime"] = int(start_time_ms)
    raw = _binance("/fapi/v1/klines", params)
    return [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]),
             "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in raw]


_trade_chart_cache: dict[tuple, tuple[float, dict]] = {}
_TRADE_CHART_CACHE_TTL = 2.0

def load_state(name: str) -> dict:
    path = _trader_state_path(name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_state(name: str, state: dict):
    path = _trader_state_path(name)
    with open(path, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _save_trader_history(key: str, history: list) -> None:
    path = _trader_history_path(key)
    with open(path, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_pm_balance() -> float:
    try:
        sys.path.insert(0, _DIR_POLY)
        from poly_trader_analiz5 import _pm_get_balance
        return _pm_get_balance()
    except Exception:
        return -1.0


# Gerçek PM trader'lar — sidebar kar donut
_PM_LIVE_PROFIT_SOURCES = [
    ("analiz5", "A1 Live", "#a855f7"),
    ("5m_sol_210", "210", "#c8f135"),
    ("analiz2_live", "A2", "#2dd4bf"),
]


def _read_trader_total_pnl(key: str) -> float:
    path = _trader_state_path(key)
    if not os.path.isfile(path):
        return 0.0
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        return round(float(state.get("total_pnl") or 0), 2)
    except Exception:
        return 0.0


def get_pm_profit_breakdown() -> dict:
    items = []
    for key, label, color in _PM_LIVE_PROFIT_SOURCES:
        pnl = _read_trader_total_pnl(key)
        items.append({"key": key, "label": label, "pnl": pnl, "color": color})
    total = round(sum(i["pnl"] for i in items), 2)
    return {"total": total, "items": items}


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


def get_pm_hourly_quotes(only_names: set[str] | None = None) -> list[dict]:
    """Aktif 1h PM marketleri — BTC/SOL UP/DOWN anlık fiyat (A1 Live ile aynı slug)."""
    from datetime import timedelta

    if only_names is not None and not only_names:
        return []

    try:
        sys.path.insert(0, _DIR_POLY)
        from poly_trader_analiz5 import _pm_find_market
    except Exception:
        return []

    now_utc = datetime.now(timezone.utc)
    et_hour = (now_utc - timedelta(hours=4)).hour
    out: list[dict] = []

    for sym in ("BTCUSDT", "SOLUSDT"):
        name = sym.replace("USDT", "")
        if only_names is not None and name not in only_names:
            continue
        row: dict = {"symbol": sym, "name": name}
        try:
            row["binance"] = round(get_price(sym), 2 if name == "BTC" else 4)
        except Exception:
            row["binance"] = None

        try:
            pm = _pm_find_market(sym, et_hour, now_utc)
        except Exception:
            pm = None

        if not pm:
            row["error"] = "market yok"
            out.append(row)
            continue

        op = pm.get("outcome_prices") or []
        up_p = float(op[0]) if len(op) > 0 else None
        down_p = float(op[1]) if len(op) > 1 else None
        title = pm.get("title") or ""
        # "Bitcoin Up or Down - July 21, 10AM ET" → "10AM ET"
        hour_lbl = title.split(",")[-1].strip() if "," in title else title

        row.update({
            "title": title,
            "hour_et": hour_lbl,
            "slug": pm.get("slug", ""),
            "up": round(up_p, 3) if up_p is not None else None,
            "down": round(down_p, 3) if down_p is not None else None,
            "up_cents": round(up_p * 100, 1) if up_p is not None else None,
            "down_cents": round(down_p * 100, 1) if down_p is not None else None,
            "closed": bool(pm.get("closed")),
        })
        out.append(row)

    return out


def get_pm_15m_quotes(only_names: set[str] | None = None) -> list[dict]:
    """Aktif 15m PM up/down — BTC/SOL (110/210 ile aynı slug)."""
    import time

    if only_names is not None and not only_names:
        return []

    try:
        sys.path.insert(0, _DIR_POLY)
        from pm_trader_helpers import pm_15m_find_market
    except Exception:
        return []

    now = int(time.time())
    ts_period = now - (now % 900)
    period_tr = datetime.fromtimestamp(ts_period, _TZ_TR).strftime("%H:%M")
    out: list[dict] = []

    for sym in ("BTCUSDT", "SOLUSDT"):
        name = sym.replace("USDT", "")
        if only_names is not None and name not in only_names:
            continue
        row: dict = {"symbol": sym, "name": name}
        try:
            row["binance"] = round(get_price(sym), 2 if name == "BTC" else 4)
        except Exception:
            row["binance"] = None

        try:
            pm = pm_15m_find_market(ts_period, sym)
        except Exception:
            pm = None

        if not pm:
            row["error"] = "market yok"
            out.append(row)
            continue

        up_p = float(pm.get("up_price", 0))
        down_p = float(pm.get("down_price", 0))
        title = pm.get("title") or ""
        period_lbl = title.split(",")[-1].strip() if "," in title else f"{period_tr} İST"

        row.update({
            "title": title,
            "period_lbl": period_lbl,
            "period_tr": period_tr,
            "slug": pm.get("slug", ""),
            "up": round(up_p, 3),
            "down": round(down_p, 3),
            "up_cents": round(up_p * 100, 1),
            "down_cents": round(down_p * 100, 1),
            "closed": bool(pm.get("closed")),
        })
        out.append(row)

    return out

# Gerçek Polymarket işlem açan sistemler (Açık Pozisyonlar paneli)
_PM_POSITION_SOURCES = [
    ("analiz5", "A1 Live"),
    ("analiz2_live", "A2 Live"),
    ("manual", "Manuel"),
    ("5m_sol_110", "15M 110 SOL"),
    ("5m_sol_111", "15M 111 SOL"),
    ("5m_sol_210", "15M 210 SOL"),
]
_HOURLY_PM_ANALYSES = frozenset({"analiz5", "analiz2_live", "manual"})
_15M_PM_ANALYSES = frozenset({"5m_sol_110", "5m_sol_111", "5m_sol_210"})


def _manual_timeframe(pos: dict) -> str:
    tf = pos.get("timeframe")
    if tf in ("5m", "15m", "1h"):
        return tf
    ep = pos.get("entry_period_min")
    if ep == 5:
        return "5m"
    if pos.get("ts_period") or ep == 15:
        return "15m"
    return "1h"


def _trade_desk_slot_ref(symbol: str, timeframe: str, ts_period: int | None = None) -> float | None:
    """PM price-to-beat — slot başlangıç mum açılışı (Binance)."""
    if not symbol:
        return None
    name = symbol.replace("USDT", "")
    dec = 1 if name == "BTC" else 2
    interval = {"5m": "5m", "15m": "15m", "1h": "1h"}.get(timeframe)
    if not interval:
        return None
    mod = {"5m": 300, "15m": 900, "1h": 3600}[timeframe]
    try:
        import time
        ts = int(ts_period if ts_period is not None else time.time() - (int(time.time()) % mod))
        target_ms = ts * 1000
        for k in get_klines(symbol, interval, 12):
            if k["t"] == target_ms:
                return round(float(k["o"]), dec)
        kl = get_klines(symbol, interval, 3)
        if kl:
            return round(float(kl[-1]["o"]), dec)
    except Exception:
        pass
    return None


def _manual_slot_ref_price(pos: dict) -> float | None:
    sym = pos.get("symbol") or ""
    ts = pos.get("ts_period") or pos.get("ts_5m")
    if not sym or not ts:
        return None
    return _trade_desk_slot_ref(sym, _manual_timeframe(pos), int(ts))


def _effective_entry_price(pos: dict, analiz_key: str) -> float:
    """Manuel PM — giriş = slot açılışı (price to beat); botlar ham entry_price."""
    if analiz_key == "manual":
        slot_ref = _manual_slot_ref_price(pos)
        if slot_ref is not None:
            return slot_ref
    return float(pos.get("entry_price") or 0)


def _manual_pos_id(pos: dict) -> str:
    oid = pos.get("pm_order_id")
    if oid and str(oid) not in ("DRY_RUN", ""):
        return str(oid)
    slug = pos.get("pm_slug") or ""
    et = pos.get("entry_time_tr") or ""
    return f"{slug}:{et}"


def _manual_pos_match(
    pos: dict,
    req_sym: str,
    *,
    timeframe: str | None = None,
    order_id: str | None = None,
) -> bool:
    if pos.get("symbol", "").upper() != req_sym:
        return False
    if order_id:
        return _manual_pos_id(pos) == order_id or str(pos.get("pm_order_id") or "") == order_id
    if timeframe in ("5m", "15m", "1h"):
        return _manual_timeframe(pos) == timeframe
    return True


def _is_15m_analiz_pos(analiz_key: str, pos: dict) -> bool:
    if analiz_key in _15M_PM_ANALYSES:
        return True
    return analiz_key == "manual" and _manual_timeframe(pos) == "15m"


def _position_slot_range(pos: dict, analiz_key: str) -> str | None:
    """Pozisyonun PM slot aralığı — 15dk: 13:45-14:00, saatlik: 12:00-13:00."""
    from datetime import timedelta

    if _is_15m_analiz_pos(analiz_key, pos):
        ts = pos.get("ts_period") or pos.get("ts_5m")
        if ts:
            start = datetime.fromtimestamp(int(ts), _TZ_TR)
            end = start + timedelta(minutes=15)
            return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
        period_min = pos.get("entry_period_min")
        if period_min is not None:
            h, m = divmod(int(period_min), 60)
            end_min = int(period_min) + 15
            eh, em = divmod(end_min, 60)
            return f"{h:02d}:{m:02d}-{eh % 24:02d}:{em:02d}"
        return None

    if analiz_key == "manual" and _manual_timeframe(pos) == "5m":
        ts = pos.get("ts_period") or pos.get("ts_5m")
        if ts:
            start = datetime.fromtimestamp(int(ts), _TZ_TR)
            end = start + timedelta(minutes=5)
            return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
        return None

    if analiz_key in _HOURLY_PM_ANALYSES:
        h = pos.get("entry_hour_tr")
        if h is None:
            ts = pos.get("entry_time_tr", "")
            if ts:
                try:
                    h = datetime.fromisoformat(ts).astimezone(_TZ_TR).hour
                except (ValueError, TypeError):
                    h = None
        if h is not None:
            return f"{int(h):02d}:00-{(int(h) + 1) % 24:02d}:00"
    return None


def _attach_live_position_to_quotes(
    quotes: list[dict], positions: list[dict], allowed_keys: frozenset,
) -> None:
    """PM kotasyon kartına açık pozisyon giriş + anlık kapanış değeri ekle."""
    by_name: dict[str, list[dict]] = {}
    for p in positions:
        if p.get("analiz_key") not in allowed_keys:
            continue
        by_name.setdefault(p.get("name", ""), []).append(p)

    for q in quotes:
        ps = by_name.get(q.get("name", ""), [])
        if not ps:
            continue
        q["pos_entry"] = ps[0].get("entry")
        q["pos_live"] = round(sum(p.get("close_val") or 0 for p in ps), 2) or None
        q["pos_risk"] = round(sum(p.get("pm_spent") or 0 for p in ps), 2)
        dirs = {p.get("dir") for p in ps}
        q["pos_dir"] = next(iter(dirs)) if len(dirs) == 1 else None


def _pm_quote_symbol_sets(positions: list) -> tuple[set[str], set[str]]:
    """Açık pozisyonlara göre saatlik / 15dk kotasyon sembolleri."""
    hourly: set[str] = set()
    m15: set[str] = set()
    for pos in positions:
        key = pos.get("_analiz") or pos.get("analiz_key", "")
        sym = pos.get("symbol", "").replace("USDT", "")
        if not sym:
            continue
        if key in _HOURLY_PM_ANALYSES:
            if _is_15m_analiz_pos(key, pos):
                m15.add(sym)
            else:
                hourly.add(sym)
        elif key in _15M_PM_ANALYSES:
            m15.add(sym)
    return hourly, m15

def _position_visible(_key: str, pos: dict) -> bool:
    """Yalnızca gerçek PM emri (token_id); sanal kotasyonları gösterme."""
    if pos.get("virtual") is True or pos.get("pm_dry_run") is True:
        return False
    if not pos.get("pm_token_id"):
        return False
    spent = pos.get("pm_spent") or pos.get("amount")
    return bool(spent)


def _is_live_pm_trade(t: dict) -> bool:
    """Geçmiş kaydında gerçek Polymarket emri (sanal simülasyon değil)."""
    if t.get("virtual") or t.get("pm_dry_run") is True:
        return False
    oid = t.get("pm_order_id")
    if oid and str(oid) not in ("DRY_RUN", ""):
        return True
    if t.get("pm_token_id"):
        return True
    return False


def _format_local_pm_trade(t: dict, label: str) -> dict | None:
    """Trader history kaydını Son İşlemler satırına çevir."""
    if not _is_live_pm_trade(t):
        return None
    slug = t.get("pm_slug") or ""
    exit_tr = t.get("exit_time_tr") or t.get("entry_time_tr") or ""
    if not exit_tr:
        return None
    spent = float(t.get("pm_spent") or t.get("amount") or 0)
    pnl_val = t.get("pnl")
    if pnl_val is None:
        return None
    win = t.get("win")
    if win is None:
        win = float(pnl_val) >= 0
    return {
        "sym": (t.get("symbol") or "").replace("USDT", "") or "?",
        "dir": t.get("predicted_dir") or t.get("pm_token_dir") or "?",
        "spent": round(spent, 2),
        "pnl": round(float(pnl_val), 2),
        "win": bool(win),
        "time": exit_tr[:16].replace("T", " "),
        "analiz": label,
        "source": "local",
        "pending": False,
        "slug": slug,
    }


def _local_pm_closed_by_slug() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, label in _PM_POSITION_SOURCES:
        for t in _load_trader_history(key):
            row = _format_local_pm_trade(t, label)
            if not row or not row["slug"]:
                continue
            prev = out.get(row["slug"])
            if not prev or row["time"] > prev["time"]:
                out[row["slug"]] = row
    return out


def _local_pm_open_slugs() -> set[str]:
    slugs: set[str] = set()
    for key, _label in _PM_POSITION_SOURCES:
        state = load_state(key)
        for pos in state.get("open_positions", []):
            if not _position_visible(key, pos):
                continue
            slug = pos.get("pm_slug")
            if slug:
                slugs.add(str(slug))
    return slugs


def _merge_pm_recent_trades(pending: list[dict], recent: list[dict]) -> tuple[list[dict], list[dict]]:
    """Poly data-api + yerel kapanış — zincir gecikince BEKLİYOR takılmasın."""
    local_closed = _local_pm_closed_by_slug()
    local_open = _local_pm_open_slugs()

    pending_out: list[dict] = []
    for p in pending:
        slug = str(p.get("slug") or "")
        if slug and slug in local_closed:
            continue
        if slug and slug not in local_open:
            # Zincirde açık görünüp yerelde iz yok — eski orphan; listeleme
            continue
        pending_out.append(p)

    recent_out: list[dict] = []
    seen_slugs: set[str] = set()
    for r in recent:
        slug = str(r.get("slug") or "")
        if slug and slug in local_closed:
            recent_out.append(local_closed[slug])
            seen_slugs.add(slug)
        else:
            recent_out.append(r)
            if slug:
                seen_slugs.add(slug)

    for slug, row in local_closed.items():
        if slug not in seen_slugs:
            recent_out.append(row)
            seen_slugs.add(slug)

    recent_out.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
    pending_out.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
    return pending_out[:10], recent_out[:20]

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
        entry_p  = _effective_entry_price(pos, pos["_analiz"])
        pred     = pos.get("predicted_dir", "")
        pm_spent = pos.get("pm_spent", 0)
        pm_size  = pos.get("pm_size", 0)
        token_dir = pos.get("pm_token_dir", pred)

        # Anlık yön
        if current_p and entry_p:
            actual  = "UP" if current_p >= entry_p else "DOWN"
            winning = (actual == pred)
            pct     = (current_p - entry_p) / entry_p * 100
            delta   = current_p - entry_p
        else:
            winning, pct, delta = None, 0.0, None

        name = sym.replace("USDT", "")
        delta_round = round(delta, 1 if name == "BTC" else 2) if delta is not None else None

        # Polymarket'tan anlık token fiyatı → kapama değeri
        est = _estimate_close_value(pos)
        close_val     = est["close_val"]
        close_pnl     = est["close_pnl"]
        token_cents   = est["token_cents"]
        win_payout    = round(float(pm_size), 2) if pm_size else None
        win_profit    = round(float(pm_size) - float(pm_spent), 2) if pm_size and pm_spent else None
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
            "delta":        delta_round,
            "winning":      winning,
            "pm_spent":     round(pm_spent, 2),
            "pm_size":      pm_size,
            "close_val":    close_val,
            "close_pnl":    close_pnl,
            "token_cents":  token_cents,
            "win_payout":   win_payout,
            "win_profit":   win_profit,
            "entry_time":   pos.get("entry_time_tr", ""),
            "slot_range":   _position_slot_range(pos, pos["_analiz"]),
            "is_15m":       _is_15m_analiz_pos(pos["_analiz"], pos),
            "pm_slug":      pos.get("pm_slug", ""),
            "pm_order_id":  pos.get("pm_order_id", ""),
            "pos_id":       _manual_pos_id(pos) if pos["_analiz"] == "manual" else "",
            "closable":     bool(pos.get("pm_token_id") and pm_size),
        })

    cash      = get_pm_balance()
    portfolio = round(cash + total_pos_value, 2) if cash >= 0 else -1

    hourly_syms, m15_syms = _pm_quote_symbol_sets(positions)

    pm_hourly = get_pm_hourly_quotes(hourly_syms)
    pm_15m = get_pm_15m_quotes(m15_syms)
    _attach_live_position_to_quotes(pm_hourly, enriched, _HOURLY_PM_ANALYSES)
    _attach_live_position_to_quotes(pm_15m, enriched, _15M_PM_ANALYSES)

    sys.path.insert(0, _DIR_POLY)
    from pm_balance_guard import get_pm_system_control

    return jsonify({
        "cash":      round(cash, 2),
        "portfolio": portfolio,
        "positions": enriched,
        "pm_hourly": pm_hourly,
        "pm_15m":    pm_15m,
        "updated":   datetime.now(_TZ_TR).strftime("%H:%M:%S"),
        **get_pm_system_control(),
    })


@app.route("/poly/api/positions-live")
def api_positions_live():
    """Açık pozisyonlar — anlık kapatma (CLOB bid, hafif endpoint)."""
    if _auth_required():
        return jsonify({"error": "unauthorized"}), 401
    out = []
    for pos in collect_positions():
        sym = pos["symbol"]
        try:
            current_p = get_price(sym)
        except Exception:
            current_p = None
        entry_p = float(pos.get("entry_price") or 0)
        pred = pos.get("predicted_dir", "")
        est = _estimate_close_value(pos)
        winning = delta = None
        if current_p and entry_p:
            actual = "UP" if current_p >= entry_p else "DOWN"
            winning = actual == pred
            delta = current_p - entry_p
        name = sym.replace("USDT", "")
        out.append({
            "analiz_key": pos["_analiz"],
            "name": name,
            "current": round(current_p, 4) if current_p else None,
            "delta": round(delta, 1 if name == "BTC" else 2) if delta is not None else None,
            "winning": winning,
            **est,
        })
    return jsonify({
        "positions": out,
        "updated": datetime.now(_TZ_TR).strftime("%H:%M:%S"),
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
        hist = _load_trader_history(key)
        if not hist and not os.path.exists(_trader_history_path(key)):
            continue
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
    hist = _load_heatmap_history(analiz_key)
    if not hist:
        return jsonify({"cells": []})
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
    hist = _load_heatmap_history(analiz_key)
    if not hist:
        return jsonify({"trades": []})

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
    analiz_key = request.args.get("analiz", _PANEL_STATS_ANALIZ)
    if analiz_key not in _HEATMAP_ANALYSES:
        analiz_key = _PANEL_STATS_ANALIZ
    hist = _load_heatmap_history(analiz_key)
    if not hist:
        return jsonify({"analiz": analiz_key, "analiz_label": _ANALYSIS_LABELS.get(analiz_key, analiz_key),
                        "total": 0, "total_wins": 0, "total_wr": 0.0, "sym_wr": [], "top_slots": []})

    # Sembol bazlı WR
    sym_stat = defaultdict(lambda: {"w": 0, "t": 0})
    for t in hist:
        sym = t.get("symbol", "").replace("USDT", "")
        sym_stat[sym]["t"] += 1
        if t.get("win"):
            sym_stat[sym]["w"] += 1
    sym_wr = []
    for sym in _allowed_syms_for(analiz_key):
        v = sym_stat.get(sym, {"w": 0, "t": 0})
        if not v["t"]:
            continue
        wr = round(v["w"] / v["t"] * 100, 1)
        sym_wr.append({"sym": sym, "wr": wr, "w": v["w"], "t": v["t"]})
    sym_wr.sort(key=lambda x: x["wr"], reverse=True)

    total      = len(hist)
    total_wins = sum(1 for t in hist if t.get("win"))
    total_wr   = round(total_wins / total * 100, 1) if total else 0.0

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
    label = _ANALYSIS_LABELS.get(analiz_key, analiz_key)
    return jsonify({
        "analiz": analiz_key,
        "analiz_label": label,
        "total": total,
        "total_wins": total_wins,
        "total_wr": total_wr,
        "sym_wr": sym_wr,
        "top_slots": top_slots[:3],
    })

@app.route("/poly/api/analizler")
def api_analizler():
    if _auth_required(): return jsonify({"error": "unauthorized"}), 401
    _SYSTEMS = [
        ("analiz1",    "1. Analiz",             300,  "RSI+MACD+EMA"),
        ("analiz2",    "2. Analiz (SOL)",       300,  "A1 motoru SOL only $10-15-20"),
        ("analiz3",    "3. Analiz Freqtrade",   300,  "SampleStrategy TA sanal PM BTC+SOL+ETH"),
        ("analiz4",    "4. Analiz",             300,  "Trend+MR+OF+Fund"),
        ("analiz6",    "6. Analiz",             300,  "MACD Hist. Div #26"),
        ("analiz5",    "A1 Live",             None, "A1 Motoru Gerçek PM $6–8 WR"),
        ("analiz8",    "8. Analiz Jesse",       300,  "GoldenCross EMA8/21 sanal PM BTC+SOL+ETH"),
        ("analiz10",   "10. Analiz",            300,  "Çift Konsensüs Sanal $10"),
        ("5m_sol_109",  "15M 109 SOL",           300,  "110 clone 7/24 sanal $8-10-12"),
        ("5m_sol_110",  "15M 110 SOL",           300,  "5M110Analiz 15m SOL sanal $8-10-12"),
        ("5m_sol_111",  "15M 111 SOL",           300,  "A32 15m filtreli sanal $8-10-12"),
        ("5m_sol_210",  "15M 210 SOL",           300,  "110 snapshot gerçek PM $4-5-6"),
    ]
    results = []
    for key, label, init_bal, desc in _SYSTEMS:
        hpath = _trader_history_path(key)
        spath = _trader_state_path(key)
        if not os.path.exists(hpath):
            continue
        try:
            hist  = _load_trader_history(key)
            state = json.load(open(spath)) if os.path.exists(spath) else {}
        except Exception:
            continue
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


_SIDEBAR_PROFIT_CSS = """
  /* pm-kar-donut */
  .sidebar-profit { margin:10px 0 4px; padding:14px 10px 12px; background:#0f140f;
    border:1px solid #1a2218; border-radius:18px; box-sizing:border-box; }
  .sidebar-profit .sp-title { font-size:10px; color:#666; text-transform:uppercase; letter-spacing:.4px; margin-bottom:12px; }
  .sidebar-profit .sp-inner { display:flex; flex-direction:column; align-items:center; gap:14px; width:100%; }
  .sidebar-profit .sp-chart { position:relative; width:132px; height:132px; flex-shrink:0; }
  .sidebar-profit .sp-chart svg { width:132px; height:132px; display:block; }
  .sidebar-profit .sp-center { position:absolute; top:0; left:0; width:132px; height:132px; z-index:2;
    display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:none; }
  .sidebar-profit .sp-total { font-size:17px; font-weight:800; color:#fff; line-height:1.1; }
  .sidebar-profit .sp-sub { font-size:9px; color:#555; margin-top:3px; text-align:center; }
  .sidebar-profit .sp-legend { width:100%; flex-shrink:0; display:flex; justify-content:space-between; gap:6px; }
  .sidebar-profit .sp-leg-item { flex:1; min-width:0; display:flex; flex-direction:column; align-items:center; text-align:center; gap:2px; }
  .sidebar-profit .sp-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; margin-bottom:2px; }
  .sidebar-profit .sp-leg-lbl { font-size:10px; color:#888; line-height:1.2; font-weight:600; }
  .sidebar-profit .sp-leg-val { font-size:12px; font-weight:700; color:#ddd; line-height:1.2; }
"""

_SIDEBAR_PROFIT_HTML = """
  <div class="sidebar-profit" id="sidebar-profit">
    <div class="sp-title">PM Kar</div>
    <div class="sp-inner">
      <div class="sp-chart">
        <svg id="sp-donut" viewBox="0 0 132 132"></svg>
        <div class="sp-center">
          <div class="sp-total" id="sp-total">$—</div>
          <div class="sp-sub">Toplam Kar</div>
        </div>
      </div>
      <div class="sp-legend" id="sp-legend"></div>
    </div>
  </div>"""

_SIDEBAR_PROFIT_JS = """
<script>
window._renderPmProfitTo = function(d, ids) {
  const totalEl = document.getElementById(ids.total);
  const legendEl = document.getElementById(ids.legend);
  const svgEl = document.getElementById(ids.svg);
  if (!totalEl || !legendEl || !svgEl) return;
  const total = d.total || 0;
  const items = d.items || [];
  const sign = total >= 0 ? '+' : '';
  totalEl.textContent = sign + '$' + Math.abs(total).toFixed(0);
  totalEl.style.color = total >= 0 ? '#4ade80' : '#f87171';
  const cx=66, cy=66, r0=48, sw=11, circ=2*Math.PI*r0;
  let arcs = '<circle cx="'+cx+'" cy="'+cy+'" r="'+r0+'" fill="none" stroke="#1a1a1a" stroke-width="'+sw+'"/>';
  const pos = items.filter(i => i.pnl > 0);
  const sum = pos.reduce((a,b)=>a+b.pnl,0);
  if (sum > 0) {
    let rot = -90;
    pos.forEach(item => {
      const angle = (item.pnl / sum) * 360;
      if (angle < 0.5) return;
      const len = circ * (item.pnl / sum);
      arcs += '<circle cx="'+cx+'" cy="'+cy+'" r="'+r0+'" fill="none" stroke="'+item.color+'" stroke-width="'+sw+'" stroke-dasharray="'+len+' '+(circ-len)+'" stroke-linecap="round" transform="rotate('+rot+' '+cx+' '+cy+')"/>';
      rot += angle;
    });
  }
  svgEl.innerHTML = arcs;
  legendEl.innerHTML = items.map(item => {
    const v = item.pnl || 0;
    const vs = (v>=0?'+':'')+'$'+Math.abs(v).toFixed(0);
    const vc = v>=0?'#4ade80':'#f87171';
    return '<div class="sp-leg-item"><span class="sp-dot" style="background:'+item.color+'"></span><div class="sp-leg-lbl">'+item.label+'</div><div class="sp-leg-val" style="color:'+vc+'">'+vs+'</div></div>';
  }).join('');
};
window.renderSidebarProfit = async function() {
  try {
    const r = await fetch('/poly/api/pm-profit', {cache:'no-store'});
    const d = await r.json();
    _renderPmProfitTo(d, {total:'sp-total', legend:'sp-legend', svg:'sp-donut'});
    _renderPmProfitTo(d, {total:'sp-mob-total', legend:'sp-mob-legend', svg:'sp-mob-donut'});
  } catch(e) { console.error('sidebar profit', e); }
};
if (!window._spBoot) {
  window._spBoot = true;
  document.addEventListener('DOMContentLoaded', () => {
    renderSidebarProfit();
    setInterval(renderSidebarProfit, 60000);
  });
}
</script>"""

_SIDEBAR_PROFIT_BLOCK = _SIDEBAR_PROFIT_HTML + _SIDEBAR_PROFIT_JS


def _patch_sidebar_cleanup(html: str) -> str:
    html = html.replace('  <div class="nav-label">Hesap</div>\n', '')
    html = html.replace('  <a class="nav-item" href="/poly/logout"><span class="nav-dot"></span>Çıkış</a>\n', '')
    return html


def _patch_sidebar_profit(html: str) -> str:
    if _SIDEBAR_PROFIT_BLOCK in html:
        return html
    markers = (
        '  <a class="nav-item" href="/ayarlar"><span class="nav-dot"></span>Ayarlar</a>\n  <div class="sidebar-footer"',
        '  <div class="sidebar-footer"><span class="dot"></span>Canlı</div>',
        '  <div class="sidebar-footer"><span class="live-dot"></span>Canlı</div>',
        '  <div class="sidebar-footer"',
    )
    for marker in markers:
        if marker not in html:
            continue
        if marker.startswith('  <a class="nav-item" href="/ayarlar"'):
            html = html.replace(
                marker,
                '  <a class="nav-item" href="/ayarlar"><span class="nav-dot"></span>Ayarlar</a>\n'
                + _SIDEBAR_PROFIT_BLOCK
                + '\n  <div class="sidebar-footer"',
                1,
            )
        else:
            html = html.replace(marker, _SIDEBAR_PROFIT_BLOCK + '\n  ' + marker, 1)
        break
    if '/* pm-kar-donut */' not in html:
        html = html.replace('</style>', _SIDEBAR_PROFIT_CSS + '\n</style>', 1)
    return html


def _patch_nav_islemler(html: str) -> str:
    grafik_link = '<a class="nav-item" href="/poly/grafik"><span class="nav-dot"></span>Grafik</a>\n  '
    islemler_link = '<a class="nav-item" href="/poly/islemler"><span class="nav-dot"></span>İşlemler</a>\n  '
    if 'href="/poly/grafik"' not in html and 'href="/poly/islemler"' in html:
        html = html.replace(
            '<a class="nav-item" href="/poly/islemler"><span class="nav-dot"></span>İşlemler</a>\n',
            islemler_link + grafik_link,
            1,
        )
    if 'href="/poly/islemler"' in html:
        return html
    link_block = islemler_link + grafik_link
    for needle in (
        '<a class="nav-item active" href="/poly/gecmis">',
        '<a class="nav-item" href="/poly/gecmis">',
    ):
        if needle in html:
            return html.replace(needle, link_block + needle, 1)
    return html


ISLEMLER_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>İşlemler — PolyMarket</title>
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%2316a34a'/><text x='50%25' y='50%25' font-size='20' text-anchor='middle' dominant-baseline='central' fill='white' font-family='Arial' font-weight='bold'>P</text></svg>">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;color:#e0e0e0;font-family:'Inter',system-ui,sans-serif;min-height:100vh;display:flex}
.sidebar{width:220px;background:#0a0f0a;padding:24px 16px;display:flex;flex-direction:column;gap:4px;flex-shrink:0;position:sticky;top:0;height:100vh;overflow-y:auto}
.logo{font-size:20px;font-weight:800;color:#fff;margin-bottom:8px;letter-spacing:-0.5px}
.logo span{color:#c8f135}
.sidebar-cash{display:block;background:#111;border:1px solid #2a2a2a;border-radius:12px;padding:8px 12px;font-size:13px;color:#9ae66e;font-weight:700;margin-bottom:16px;width:100%;text-align:center}
.nav-label{font-size:10px;color:#444;text-transform:uppercase;letter-spacing:1px;padding:12px 12px 4px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;color:#888;text-decoration:none;font-size:14px;transition:.15s}
.nav-item:hover{background:#1a1a1a;color:#fff}
.nav-item.active{background:#1a2e1a;color:#c8f135;font-weight:600}
.nav-dot{width:6px;height:6px;border-radius:50%;background:#333;flex-shrink:0}
.nav-item.active .nav-dot,.nav-item:hover .nav-dot{background:#c8f135}
.sidebar-footer{margin-top:auto;font-size:11px;color:#444;padding:12px;display:flex;align-items:center;gap:6px}
.sidebar-footer .dot{width:6px;height:6px;border-radius:50%;background:#4ade80}
.main{flex:1;padding:28px 32px;max-width:560px;min-width:0}
.content-wrap{display:flex;flex:1;min-width:0;align-items:flex-start}
.chart-panel{flex:1;min-width:340px;padding:20px 24px 20px 0;border-left:1px solid #1e1e1e;display:flex;flex-direction:column;align-self:flex-start;position:sticky;top:0;gap:12px}
.chart-pos-card{margin:0;width:100%}
.chart-panel-inner{background:#111;border:1px solid #1e1e1e;border-radius:12px;padding:8px 10px;display:flex;flex-direction:column;width:100%}
.chart-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:nowrap}
.chart-title{font-size:12px;font-weight:800;color:#fff;white-space:nowrap}
.chart-meta{font-size:9px;color:#555;margin-top:1px}
.chart-ref{display:flex;flex-direction:column;align-items:flex-end;gap:1px;flex-shrink:0}
.chart-head-right{display:flex;flex-direction:column;align-items:flex-end;gap:6px;flex-shrink:0}
.live-clock{font-size:13px;font-weight:700;color:#9ae66e;font-variant-numeric:tabular-nums;letter-spacing:.04em;font-family:ui-monospace,'SF Mono',Consolas,monospace;white-space:nowrap}
.chart-ref-lbl{font-size:8px;color:#555;text-transform:uppercase;letter-spacing:.3px;font-weight:700}
.chart-ref-val{font-size:12px;font-weight:800;color:#fbbf24}
.chart-signals{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px;min-height:18px}
.chart-px-tabs{display:flex;gap:5px;margin-top:6px;flex-wrap:wrap}
.tab-px{background:#111;border:1px solid #2a2a2a;color:#777;font-size:10px;font-weight:800;padding:4px 10px;border-radius:8px;cursor:pointer;min-width:36px;text-align:center}
.tab-px:hover:not(.active){border-color:#5a4a18;color:#ca8a04}
.tab-px.active{background:#2a2410;border-color:#fbbf24;color:#fbbf24;box-shadow:0 0 0 1px rgba(251,191,36,.15)}
.sig-pill{font-size:9px;font-weight:800;padding:2px 7px;border-radius:6px;letter-spacing:.3px}
.sig-pill.a1{background:#2a1a3a;color:#c084fc;border:1px solid #6b21a8}
.sig-pill.a3{background:#0f2a24;color:#2dd4bf;border:1px solid #0d9488}
.sig-pill.a8{background:#0c2340;color:#38bdf8;border:1px solid #0369a1}
.sig-pill.alfa{background:#2a1f0a;color:#fbbf24;border:1px solid #f59e0b}
.sig-pill.a112{background:#0c2340;color:#38bdf8;border:1px solid #0369a1}
.sig-pill.a113{background:#0f2a24;color:#2dd4bf;border:1px solid #0d9488}
.sig-pill.m110{background:#1a2410;color:#c8f135;border:1px solid #4d7c0f}
#trade-chart{height:263px;min-height:263px;max-height:263px;width:100%;flex:none}
.chart-empty{color:#555;font-size:13px;padding:40px 12px;text-align:center}
.page-title{font-size:22px;font-weight:800;margin-bottom:6px}
.page-sub{font-size:13px;color:#666;margin-bottom:24px}
.tabs{display:flex;gap:6px;margin-bottom:16px;margin-top:0;flex-wrap:wrap}
.tab{background:#111;border:1px solid #2a2a2a;color:#888;font-size:12px;font-weight:700;padding:10px 14px;border-radius:12px;cursor:pointer;flex:1;min-width:0;text-align:center}
.tab.active{background:#1a2e1a;border-color:#4ade80;color:#4ade80}
.card{background:#111;border:1px solid #1e1e1e;border-radius:16px;padding:20px;margin-bottom:16px}
.card-title{font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px;font-weight:700}
.quote-row{display:flex;justify-content:space-between;align-items:center;padding:10px 10px;border-bottom:1px solid #1a1a1a;font-size:13px;cursor:pointer;border-radius:12px;margin:0 -6px;transition:.15s}
.quote-row:last-child{border-bottom:none}
.quote-row:hover{background:#141414}
.quote-row.selected{background:#1a2e1a;outline:1px solid #2a4a2a}
.sym{font-weight:800;font-size:16px}
.slot{color:#666;font-size:12px;margin-top:2px}
.prices{display:flex;gap:10px;margin-top:8px}
.price-pill{padding:6px 12px;border-radius:8px;font-size:12px;font-weight:700}
.price-up{background:#142814;color:#4ade80}
.price-down{background:#2a1414;color:#f87171}
.form-row{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start;margin-top:16px}
.field-amt{flex:1 1 100%;width:100%}
.amt-row{display:flex;align-items:center;gap:10px;width:100%}
.amt-row .amt-input{flex:0 0 100px;width:100px}
.amt-row .open-btn{flex:1;min-width:120px;padding:12px 16px}
.field-dir{flex:1 1 100%;width:100%}
.lbl{font-size:11px;color:#666;margin-bottom:6px;font-weight:600}
.field{display:flex;flex-direction:column}
.dir-btns{display:flex;gap:8px;width:100%}
.dir-btn{flex:1;padding:12px 18px;border-radius:10px;border:1.5px solid #2a2a2a;background:#0d0d0d;color:#888;font-size:13px;font-weight:700;cursor:pointer;text-align:center}
.dir-btn.up.active{background:#142814;border-color:#4ade80;color:#4ade80}
.dir-btn.down.active{background:#2a1414;border-color:#f87171;color:#f87171}
.amt-input{background:#0d0d0d;border:1.5px solid #2a2a2a;border-radius:10px;color:#fff;font-size:18px;font-weight:800;padding:10px 14px;width:120px}
.amt-input:focus{outline:none;border-color:#c8f135}
.open-btn{background:#c8f135;border:none;color:#111;font-size:14px;font-weight:800;padding:12px 24px;border-radius:12px;cursor:pointer}
.open-btn:hover{opacity:.92}
.payout-preview{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px;width:100%;flex:1 1 100%;padding:10px 0 0;background:none;border:none;border-radius:0;font-size:13px;line-height:1.4}
.payout-preview .profit{font-size:18px;font-weight:800;color:#4ade80}
.payout-preview .sub{color:#aaa;font-size:15px;font-weight:600}
.payout-preview.warn{padding:10px 14px;background:#1a1408;border:1px solid #78350f;border-radius:10px;flex-direction:column;align-items:flex-start;gap:4px}
.payout-preview.warn .profit{color:#fbbf24}
.spot-strip{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin-bottom:14px;padding:12px 14px;background:#0d100d;border:1px solid #1e2a1e;border-radius:12px}
.spot-tf{margin-left:auto;font-size:11px;color:#555;font-weight:700}
.spot-item{display:flex;align-items:baseline;gap:8px;font-size:13px}
.spot-lbl{color:#666;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.3px}
.spot-val{font-size:18px;font-weight:800;color:#fff}
.spot-delta{font-size:13px;font-weight:700;margin-left:4px}
.spot-delta.up{color:#4ade80}
.spot-delta.down{color:#f87171}
.msg{margin-top:12px;font-size:13px;padding:10px 14px;border-radius:10px;display:none}
.msg.ok{display:block;background:#142814;color:#4ade80;border:1px solid #2a4a2a}
.msg.err{display:block;background:#2a1414;color:#f87171;border:1px solid #5a2a2a}
.pos-table{width:100%;border-collapse:collapse;font-size:13px}
.pos-table th{text-align:left;color:#555;font-size:11px;text-transform:uppercase;padding:10px 8px;border-bottom:1px solid #2a2a2a}
.pos-table td{padding:12px 8px;border-bottom:1px solid #1a1a1a}
.close-sm{background:#2a1414;border:1px solid #5a2a2a;color:#f87171;font-size:11px;font-weight:700;padding:6px 12px;border-radius:8px;cursor:pointer}
.sync-btn{background:#1a2e1a;border:1px solid #4ade80;color:#4ade80;font-size:12px;font-weight:700;padding:8px 14px;border-radius:10px;cursor:pointer;white-space:nowrap}
.sync-btn:hover{background:#243824}
.sync-btn:disabled{opacity:.55;cursor:wait}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}
.card-head .card-title{margin-bottom:0}
.empty{color:#555;font-size:13px;padding:8px 0}
@media(max-width:1100px){.content-wrap{flex-direction:column}.chart-panel{border-left:none;border-top:1px solid #1e1e1e;padding:20px 16px;min-width:0}.main{max-width:none;padding-bottom:12px}}
@media(max-width:768px){body{flex-direction:column}.sidebar{width:100%;height:auto;position:relative}.main{padding:20px 16px}.chart-panel{padding:16px}}
</style>
</head>
<body>
<div class="sidebar">
  <div class="logo">Poly<span>Market</span></div>
  <div class="sidebar-cash" id="cash">USDC …</div>
  <div class="nav-label">Ana Menü</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item" href="/algoritma"><span class="nav-dot"></span>Algoritma</a>
  <a class="nav-item" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="/analizler"><span class="nav-dot"></span>Analizler</a>
  <a class="nav-item active" href="/poly/islemler"><span class="nav-dot"></span>İşlemler</a>
  <a class="nav-item" href="/poly/grafik"><span class="nav-dot"></span>Grafik</a>
  <a class="nav-item" href="/poly/gecmis"><span class="nav-dot"></span>Geçmiş</a>
  <a class="nav-item" href="/ayarlar"><span class="nav-dot"></span>Ayarlar</a>
  <div class="sidebar-footer"><span class="dot"></span>Canlı</div>
</div>
<div class="content-wrap">
<div class="main">
  <div class="tabs">
    <button type="button" class="tab" id="tab-5m" onclick="setTf('5m')">5 Dakika</button>
    <button type="button" class="tab active" id="tab-15m" onclick="setTf('15m')">15 Dakika</button>
    <button type="button" class="tab" id="tab-1h" onclick="setTf('1h')">1 Saat</button>
  </div>

  <div class="card" id="quote-card">
    <div class="card-title">Aktif market</div>
    <div id="quotes"><div class="empty">Yükleniyor…</div></div>
  </div>

  <div class="card">
    <div class="card-title">Yeni işlem</div>
    <div class="spot-strip" id="spot-strip">
      <div class="spot-item">
        <span class="spot-lbl">Başlangıç</span>
        <span class="spot-val" id="spot-ref">—</span>
      </div>
      <div class="spot-item">
        <span class="spot-lbl">Anlık</span>
        <span class="spot-val" id="spot-live">—</span>
        <span class="spot-delta" id="spot-delta"></span>
      </div>
      <span class="spot-tf" id="spot-tf"></span>
    </div>
    <div class="form-row">
      <div class="field field-dir">
        <div class="dir-btns">
          <button type="button" class="dir-btn up active" id="btn-up" onclick="setDir('UP')">📈 Yükselir</button>
          <button type="button" class="dir-btn down" id="btn-down" onclick="setDir('DOWN')">📉 Düşer</button>
        </div>
      </div>
      <div class="field field-amt">
        <div class="lbl">Tutar ($)</div>
        <div class="amt-row">
          <input type="number" id="amount" class="amt-input" min="1" max="500" step="1" value="7" oninput="updatePreview()" onchange="updatePreview()">
          <button type="button" class="open-btn" id="open-btn" onclick="openTrade()">İşlem Aç</button>
        </div>
      </div>
      <div class="payout-preview" id="payout-preview">
        <div class="profit">—</div>
        <div class="sub">Kazanırsan net</div>
      </div>
    </div>
    <div class="msg" id="msg"></div>
  </div>

  <div class="card" id="open-pos-card">
    <div class="card-head">
      <div class="card-title">Açık manuel pozisyonlar</div>
      <button type="button" class="sync-btn" id="sync-btn" onclick="syncManual()">↻ Senkron Et</button>
    </div>
    <div id="open-pos"><div class="empty">Yükleniyor…</div></div>
  </div>
</div>
<div class="chart-panel" id="chart-panel">
  <div class="chart-panel-inner">
    <div class="chart-head">
      <div>
        <div class="chart-title" id="chart-title">Grafik</div>
        <div class="chart-meta" id="chart-meta">Market seç · 1m · 110 motor</div>
        <div class="chart-px-tabs">
          <button type="button" class="tab-px active" id="tab-px-1m" onclick="setPriceTf('1m')">1m</button>
          <button type="button" class="tab-px" id="tab-px-5m" onclick="setPriceTf('5m')">5m</button>
          <button type="button" class="tab-px" id="tab-px-15m" onclick="setPriceTf('15m')">15m</button>
          <button type="button" class="tab-px" id="tab-px-1h" onclick="setPriceTf('1h')">1h</button>
        </div>
        <div class="chart-signals" id="chart-signals"></div>
      </div>
      <div class="chart-head-right">
        <div class="live-clock" id="live-clock">—</div>
        <div class="chart-ref">
          <span class="chart-ref-lbl">Başlangıç (price to beat)</span>
          <span class="chart-ref-val" id="chart-ref-lbl">—</span>
        </div>
      </div>
    </div>
    <div id="trade-chart"></div>
  </div>
</div>
</div>
<script>
let _tf = '15m';
let _priceTf = '1m';
let _dir = 'UP';
let _deskSymPref = 'SOLUSDT';
let _quotes5 = [];
let _quotes15 = [];
let _quotes1h = [];
let _selectedIdx = 0;
let _chart = null;
let _candleSeries = null;
let _priceLine = null;
let _emaFastSeries = null;
let _emaSlowSeries = null;
let _volumeSeries = null;
let _chartSym = null;
let _chartTf = null;
let _chartPx = null;
let _chartReq = 0;
let _estSeq = 0;
let _deskInit = false;

const _CHART_TZ = 'Europe/Istanbul';
function utcToIstChartTime(utcSec) {
  if (utcSec == null) return utcSec;
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: _CHART_TZ,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(new Date(utcSec * 1000));
  const g = (t) => parseInt(parts.find(p => p.type === t).value, 10);
  return Date.UTC(g('year'), g('month') - 1, g('day'), g('hour'), g('minute'), g('second')) / 1000;
}
function shiftSeriesTimes(arr) {
  return (arr || []).map(p => Object.assign({}, p, { time: utcToIstChartTime(p.time) }));
}
function shiftSignalTimes(arr) {
  return (arr || []).map(s => Object.assign({}, s, { time: utcToIstChartTime(s.time) }));
}
function prepareChartPayload(raw) {
  const d = Object.assign({}, raw);
  d.candles = shiftSeriesTimes(raw.candles);
  if (raw.window_start != null) d.window_start = utcToIstChartTime(raw.window_start);
  if (raw.window_end != null) d.window_end = utcToIstChartTime(raw.window_end);
  if (raw.algo_overlay) {
    const ov = Object.assign({}, raw.algo_overlay);
    if (ov.overlays) {
      ov.overlays = Object.assign({}, ov.overlays, {
        ema_fast: shiftSeriesTimes(ov.overlays.ema_fast),
        ema_slow: shiftSeriesTimes(ov.overlays.ema_slow),
      });
    }
    ov.signals = shiftSignalTimes(ov.signals);
    d.algo_overlay = ov;
  }
  d.hourly_signals = shiftSignalTimes(raw.hourly_signals);
  return d;
}
const _chartLoc = {
  locale: 'tr-TR',
  timeFormatter: (t) => {
    const p = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit', hour12: false })
      .formatToParts(new Date(t * 1000));
    return p.find(x => x.type === 'hour').value + ':' + p.find(x => x.type === 'minute').value;
  },
};

function saveDeskPrefs() {
  try {
    sessionStorage.setItem('islemler_sym', selectedSymbol());
    sessionStorage.setItem('islemler_tf', _tf);
    sessionStorage.setItem('islemler_price_tf', _priceTf);
  } catch (e) {}
}

function syncPxTabs() {
  ['1m', '5m', '15m', '1h'].forEach(px => {
    const el = document.getElementById('tab-px-' + px);
    if (el) el.classList.toggle('active', _priceTf === px);
  });
}

function tfLabel(tf) {
  return tf === '5m' ? '5dk' : tf === '15m' ? '15dk' : '1saat';
}

function syncTfTabs() {
  ['5m', '15m', '1h'].forEach(t => {
    const el = document.getElementById('tab-' + t);
    if (el) el.classList.toggle('active', _tf === t);
  });
}

function loadDeskPrefs() {
  try {
    const sym = sessionStorage.getItem('islemler_sym');
    const tf = sessionStorage.getItem('islemler_tf');
    const px = sessionStorage.getItem('islemler_price_tf');
    _deskSymPref = sym || 'SOLUSDT';
    _tf = (tf === '1h' || tf === '5m') ? tf : '15m';
    if (px === '1m' || px === '5m' || px === '15m' || px === '1h') _priceTf = px;
  } catch (e) {
    _deskSymPref = 'SOLUSDT';
    _tf = '15m';
    _priceTf = '1m';
  }
  syncTfTabs();
  syncPxTabs();
}

function setPriceTf(px) {
  _priceTf = px;
  syncPxTabs();
  saveDeskPrefs();
  resetTradeChart();
  _chartSym = null;
  _chartTf = null;
  _chartPx = null;
  loadTradeChart();
}

function setTf(tf) {
  _tf = tf;
  syncTfTabs();
  saveDeskPrefs();
  resetTradeChart();
  _chartSym = null;
  _chartTf = null;
  _chartPx = null;
  refreshSpot();
  updatePreview();
  loadDesk();
}

function quoteList() {
  if (_tf === '5m') return _quotes5;
  if (_tf === '1h') return _quotes1h;
  return _quotes15;
}

function selectedQuote() {
  const list = quoteList();
  return list[_selectedIdx] || list[0] || null;
}

function selectedSymbol() {
  const q = selectedQuote();
  return q ? q.symbol : 'SOLUSDT';
}

function setDir(d) {
  _dir = d;
  document.getElementById('btn-up').classList.toggle('active', d === 'UP');
  document.getElementById('btn-down').classList.toggle('active', d === 'DOWN');
  updatePreview();
}

function currentQuote() {
  return selectedQuote();
}

function buyPlanLocal(amount, price) {
  price = Math.max(0.02, Math.min(0.98, Math.round(price * 100) / 100));
  let size = Math.max(5, Math.floor(amount / price * 100) / 100);
  for (let i = 0; i < 10000; i++) {
    const spent = size * price;
    if (Math.abs(spent * 100 - Math.floor(spent * 100)) < 1e-9) {
      const spentR = Math.round(spent * 100) / 100;
      let minSize = 5;
      for (let j = 0; j < 10000; j++) {
        const minSpent = minSize * price;
        if (Math.abs(minSpent * 100 - Math.floor(minSpent * 100)) < 1e-9) {
          const minAmount = Math.round(minSpent * 100) / 100;
          return {
            price: price,
            size: size,
            spent: spentR,
            profit: Math.round((size - spentR) * 100) / 100,
            min_amount: minAmount,
            allowed: amount + 0.01 >= minAmount,
          };
        }
        minSize = Math.round((minSize + 0.01) * 100) / 100;
      }
      return null;
    }
    size = Math.round((size + 0.01) * 100) / 100;
  }
  return null;
}

function renderPreviewPlan(el, p, amount) {
  if (!el) return;
  if (!p) {
    el.className = 'payout-preview';
    el.innerHTML = '<div class="profit">—</div><div class="sub">Kazanırsan net</div>';
    return;
  }
  if (!p.allowed) {
    el.className = 'payout-preview warn';
    el.innerHTML =
      '<div class="profit">Min ~$' + p.min_amount.toFixed(2) + '</div>' +
      '<div class="sub">⚠️ $' + amount.toFixed(2) + ' ile ~$' + p.spent.toFixed(2) + ' açılır (min 5 pay)</div>';
    return;
  }
  el.className = 'payout-preview';
  el.innerHTML =
    '<div class="profit">+$' + p.profit.toFixed(2) + '</div>' +
    '<div class="sub">🏆 $' + p.size.toFixed(2) + ' to win · gerçek risk ~$' + p.spent.toFixed(2) + '</div>';
}

function updatePreview() {
  const el = document.getElementById('payout-preview');
  if (!el) return;
  const amount = parseFloat(document.getElementById('amount').value) || 0;
  if (amount < 0.01) {
    el.className = 'payout-preview';
    el.innerHTML = '<div class="profit">—</div><div class="sub">Kazanırsan net</div>';
    return;
  }
  const q = selectedQuote();
  const quotePrice = q ? (_dir === 'UP' ? q.up : q.down) : null;
  if (quotePrice != null) {
    renderPreviewPlan(el, buyPlanLocal(amount, quotePrice), amount);
  }
  clearTimeout(window._estTimer);
  const seq = ++_estSeq;
  window._estTimer = setTimeout(async () => {
    const reqAmount = parseFloat(document.getElementById('amount').value) || 0;
    if (reqAmount < 0.01) return;
    try {
      const r = await fetch('/poly/api/trade-desk/estimate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          timeframe: _tf,
          symbol: selectedSymbol(),
          direction: _dir,
          amount: reqAmount,
        }),
      });
      if (seq !== _estSeq) return;
      const d = await r.json();
      if (seq !== _estSeq) return;
      renderPreviewPlan(el, d.plan, reqAmount);
    } catch (e) {
      console.error(e);
    }
  }, 280);
}

function applySpot(q) {
  const refEl = document.getElementById('spot-ref');
  const liveEl = document.getElementById('spot-live');
  const deltaEl = document.getElementById('spot-delta');
  const tfEl = document.getElementById('spot-tf');
  if (!refEl || !liveEl || !deltaEl) return;
  if (tfEl) {
    const slot = q && q.slot_label ? q.slot_label + ' İST' : '';
    tfEl.textContent = slot ? slot + ' · ' + tfLabel(_tf) : '';
  }
  if (!q || q.ref_price == null) {
    refEl.textContent = '—';
    liveEl.textContent = '—';
    deltaEl.textContent = '';
    deltaEl.className = 'spot-delta';
    return;
  }
  const dec = q.dec != null ? q.dec : 2;
  refEl.textContent = '$' + Number(q.ref_price).toFixed(dec);
  if (q.live_price != null) {
    liveEl.textContent = '$' + Number(q.live_price).toFixed(dec);
    if (_lastCandles.length && _candleSeries) {
      const c = Object.assign({}, _lastCandles[_lastCandles.length - 1]);
      const lp = Number(Number(q.live_price).toFixed(dec));
      c.close = lp; c.high = Math.max(c.high, lp); c.low = Math.min(c.low, lp);
      _lastCandles[_lastCandles.length - 1] = c;
      _candleSeries.update(c);
    }
    if (q.delta != null) {
      const cls = q.delta >= 0 ? 'up' : 'down';
      const sign = q.delta >= 0 ? '+' : '-';
      deltaEl.className = 'spot-delta ' + cls;
      deltaEl.textContent = sign + '$' + Math.abs(q.delta).toFixed(dec);
    } else {
      deltaEl.textContent = '';
      deltaEl.className = 'spot-delta';
    }
  } else {
    liveEl.textContent = '—';
    deltaEl.textContent = '';
    deltaEl.className = 'spot-delta';
  }
}

async function refreshSpot() {
  const sym = selectedSymbol();
  const tf = _tf;
  try {
    const r = await fetch('/poly/api/trade-desk/spot?timeframe=' + tf + '&symbol=' + sym, {cache: 'no-store'});
    const spot = await r.json();
    if (tf !== _tf || sym !== selectedSymbol()) return;
    applySpot(spot);
  } catch (e) { console.error(e); }
}

function showMsg(text, ok) {
  const el = document.getElementById('msg');
  el.textContent = text;
  el.className = 'msg ' + (ok ? 'ok' : 'err');
}

function renderQuotes(quotes) {
  const box = document.getElementById('quotes');
  if (!quotes.length) {
    box.innerHTML = '<div class="empty">Market bulunamadı</div>';
    return;
  }
  if (_selectedIdx >= quotes.length) _selectedIdx = 0;
  box.innerHTML = quotes.map((q, i) => `
    <div class="quote-row${i === _selectedIdx ? ' selected' : ''}" onclick="selectQuote(${i})" role="button" tabindex="0">
      <div>
        <div class="sym">${q.name}</div>
        <div class="slot">${q.slot || ''} · ${q.title || q.slug || ''}</div>
        <div class="prices">
          <span class="price-pill price-up">UP ${(q.up*100).toFixed(0)}¢</span>
          <span class="price-pill price-down">DOWN ${(q.down*100).toFixed(0)}¢</span>
        </div>
      </div>
      ${q.closed ? '<span style="color:#f87171;font-size:12px">Kapalı</span>' : '<span style="color:#4ade80;font-size:12px">Açık</span>'}
    </div>`).join('');
}

function selectQuote(idx) {
  const quotes = quoteList();
  const q = quotes[idx];
  if (!q) return;
  _selectedIdx = idx;
  _deskSymPref = q.symbol;
  document.querySelectorAll('.quote-row').forEach((row, i) => {
    row.classList.toggle('selected', i === idx);
  });
  saveDeskPrefs();
  refreshSpot();
  updatePreview();
  loadTradeChart();
}

let _chartScaleMin = null;
let _chartScaleMax = null;
let _lastCandles = [];

function calcTightScale(candles, refPrice) {
  if (!candles.length) return null;
  let lo = Math.min(...candles.map(c => c.low));
  let hi = Math.max(...candles.map(c => c.high));
  if (refPrice != null) {
    lo = Math.min(lo, refPrice);
    hi = Math.max(hi, refPrice);
  }
  const span = Math.max(hi - lo, 0.0001);
  const pad = Math.max(span * 0.06, span * 0.015);
  return { lo: lo - pad, hi: hi + pad };
}

function applyChartPriceScale(candles, refPrice) {
  const tight = calcTightScale(candles, refPrice);
  if (!tight) {
    _chartScaleMin = null;
    _chartScaleMax = null;
    return;
  }
  _chartScaleMin = tight.lo;
  _chartScaleMax = tight.hi;
  if (_candleSeries) {
    _candleSeries.applyOptions({
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: _chartScaleMin, maxValue: _chartScaleMax },
      }),
    });
  }
}

function fitBarDensity(count) {
  const container = document.getElementById('trade-chart');
  if (!container || !count) return 3;
  const w = Math.max(200, container.clientWidth - 52);
  return Math.max(2, Math.min(7, Math.floor((w / count) * 0.82)));
}

function focusDeskCandleWindow(candles) {
  if (!_chart || !candles || candles.length < 2) return;
  const barSec = priceBarSeconds();
  _chart.timeScale().setVisibleRange({
    from: candles[0].time - barSec * 2,
    to: candles[candles.length - 1].time + barSec * 12,
  });
}

function priceBarSeconds() {
  if (_priceTf === '1h') return 3600;
  if (_priceTf === '15m') return 900;
  if (_priceTf === '5m') return 300;
  return 60;
}

function candleLimitForView() {
  if (_priceTf === '1h') {
    if (_tf === '1h') return 48;
    if (_tf === '5m') return 12;
    return 24;
  }
  if (_priceTf === '15m') {
    if (_tf === '1h') return 48;
    if (_tf === '5m') return 12;
    return 16;
  }
  if (_priceTf === '5m') {
    if (_tf === '1h') return 24;
    if (_tf === '5m') return 12;
    return 12;
  }
  if (_tf === '1h') return 120;
  if (_tf === '5m') return 36;
  return 60;
}

function volumeHistogramData(candles) {
  return (candles || []).map(c => ({
    time: c.time,
    value: Number(c.volume) || 0,
    color: c.close >= c.open ? 'rgba(38,166,154,0.55)' : 'rgba(239,83,80,0.55)',
  }));
}

function applyChartVolumeLayout() {
  if (!_chart) return;
  _chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.05, bottom: 0.28 } });
  if (_chart.priceScale('vol')) {
    _chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.72, bottom: 0 } });
  }
}

function resetTradeChart() {
  if (_chart) {
    _chart.remove();
    _chart = null;
    _candleSeries = null;
    _priceLine = null;
    _emaFastSeries = null;
    _emaSlowSeries = null;
    _volumeSeries = null;
  }
  _chartScaleMin = null;
  _chartScaleMax = null;
}

function chartAlgoParam(tf) {
  return tf === '1h' ? 'off' : '110';
}

function clipOverlayToCandles(ov, candles) {
  if (!ov || !ov.overlays || !candles.length) return ov;
  const t0 = candles[0].time, t1 = candles[candles.length - 1].time;
  const clip = (arr) => (arr || []).filter(p => p.time >= t0 && p.time <= t1);
  return Object.assign({}, ov, {
    overlays: Object.assign({}, ov.overlays, {
      ema_fast: clip(ov.overlays.ema_fast),
      ema_slow: clip(ov.overlays.ema_slow),
    }),
    signals: (ov.signals || []).filter(s => s.time >= t0 && s.time <= t1),
  });
}

function motorSlotDir(ov, ws) {
  if (!ov || !ov.ok) return null;
  const cur = ov.current;
  if (cur && (cur.direction === 'UP' || cur.direction === 'DOWN')) {
    return cur.direction;
  }
  const sigs = ov.signals || [];
  for (let i = sigs.length - 1; i >= 0; i--) {
    if (sigs[i].time === ws) return sigs[i].dir;
  }
  let last = null;
  for (const s of sigs) {
    if (ws == null || s.time <= ws) last = s.dir;
  }
  return last;
}

function appendMotorSlotMarkers(markers, d, candles, ov) {
  const ws = d.window_start;
  if (!ws || !candles.some(c => c.time === ws)) return;
  const dir = motorSlotDir(ov, ws);
  if (!dir) {
    markers.push({
      time: ws,
      position: 'aboveBar',
      color: '#888',
      shape: 'circle',
      text: '110',
    });
    return;
  }
  markers.push({
    time: ws,
    position: dir === 'UP' ? 'belowBar' : 'aboveBar',
    color: dir === 'UP' ? '#4ade80' : '#c8f135',
    shape: dir === 'UP' ? 'arrowUp' : 'arrowDown',
    text: '110',
  });
}

function addMotorMarkers(markers, ov, skipTime) {
  if (!ov || !ov.ok) return;
  (ov.signals || []).forEach(s => {
    if (skipTime != null && s.time === skipTime) return;
    markers.push({
      time: s.time,
      position: s.dir === 'UP' ? 'belowBar' : 'aboveBar',
      color: s.dir === 'UP' ? '#4ade80' : '#f87171',
      shape: s.dir === 'UP' ? 'arrowUp' : 'arrowDown',
      text: s.dir,
    });
  });
}

function applyMotorEma(ov) {
  if (!_emaFastSeries || !_emaSlowSeries) return;
  if (ov && ov.ok && ov.overlays) {
    _emaFastSeries.setData(ov.overlays.ema_fast || []);
    _emaSlowSeries.setData(ov.overlays.ema_slow || []);
  } else {
    _emaFastSeries.setData([]);
    _emaSlowSeries.setData([]);
  }
}

function updateChartGuideLegend(d, tf) {
  const el = document.getElementById('chart-signals');
  if (!el) return;
  if (tf === '1h') {
    updateHourlyLegend(d.hourly_current);
    return;
  }
  if (tf === '15m') {
    updateFifteenMotorLegend(d);
    return;
  }
  const ov = d.algo_overlay;
  const cur = ov && ov.ok ? ov.current : null;
  const dir = cur && cur.direction;
  if (dir === 'UP' || dir === 'DOWN') {
    el.innerHTML = '<span class="sig-pill m110">110 · ' + dir + '</span>'
      + (cur.label ? ' <span style="color:#666;font-size:9px">' + cur.label + '</span>' : '');
  } else if (ov && ov.error) {
    el.innerHTML = '<span class="sig-pill m110">110 · —</span>';
  } else if (cur && cur.label) {
    el.innerHTML = '<span class="sig-pill m110">110 · ' + cur.label + '</span>';
  } else {
    el.innerHTML = '<span class="sig-pill m110">110 · gate altı</span>';
  }
}

function updateFifteenMotorLegend(d) {
  const el = document.getElementById('chart-signals');
  if (!el) return;
  let html = '';
  const ov = d.algo_overlay;
  const cur = ov && ov.ok ? ov.current : null;
  const dir = cur && cur.direction;
  if (dir === 'UP' || dir === 'DOWN') {
    html += '<span class="sig-pill m110">110 · ' + dir + '</span>';
  } else if (cur && cur.label) {
    html += '<span class="sig-pill m110">110 · ' + cur.label + '</span>';
  } else {
    html += '<span class="sig-pill m110">110 · —</span>';
  }
  const fc = d.fifteen_current || {};
  html += hourlyPillHtml(fc, 'a112', '112', 'a112');
  html += hourlyPillHtml(fc, 'a113', '113', 'a113');
  el.innerHTML = html;
}

function fifteenTagColor(tag) {
  if (tag === '112') return '#38bdf8';
  if (tag === '113') return '#2dd4bf';
  return '#888';
}

function fifteenMarker(s) {
  const tag = s.tag || '?';
  return {
    time: s.time,
    position: s.dir === 'UP' ? 'belowBar' : 'aboveBar',
    color: fifteenTagColor(tag),
    shape: s.dir === 'UP' ? 'arrowUp' : 'arrowDown',
    text: tag,
  };
}

function appendFifteenSlotMarkers(markers, d, candles) {
  const ws = d.window_start;
  if (!ws || !candles.some(c => c.time === ws)) return;
  const fc = d.fifteen_current || {};
  appendHourlySlotMarker(markers, ws, fc.a112, '112', '#38bdf8');
  appendHourlySlotMarker(markers, ws, fc.a113, '113', '#2dd4bf');
}

function addFifteenMarkers(markers, signals, ws) {
  (signals || []).forEach(s => {
    if (ws && s.time === ws && (s.tag === '112' || s.tag === '113')) return;
    markers.push(fifteenMarker(s));
  });
}

function ensureTradeChart() {
  const container = document.getElementById('trade-chart');
  if (!container) return false;
  const sym = selectedSymbol();
  if (_chart && (_chartSym !== sym || _chartTf !== _tf || _chartPx !== _priceTf)) {
    resetTradeChart();
  }
  if (!_chart) {
    _chartSym = sym;
    _chartTf = _tf;
    _chartPx = _priceTf;
    _chart = LightweightCharts.createChart(container, {
      width: container.clientWidth,
      height: Math.max(225, container.clientHeight || 263),
      layout: { background: { color: '#0a0a0a' }, textColor: '#555' },
      grid: { vertLines: { color: '#121212' }, horzLines: { color: '#121212' } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      localization: _chartLoc,
      timeScale: {
        borderColor: '#1a1a1a',
        timeVisible: true,
        secondsVisible: false,
        barSpacing: 3,
        minBarSpacing: 1,
        rightOffset: 12,
        fixRightEdge: false,
      },
      rightPriceScale: {
        borderColor: '#1a1a1a',
        autoScale: true,
        scaleMargins: { top: 0.01, bottom: 0.01 },
      },
    });
    _candleSeries = _chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350',
      borderUpColor: '#26a69a', borderDownColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
      autoscaleInfoProvider: () => {
        if (_chartScaleMin != null && _chartScaleMax != null) {
          return { priceRange: { minValue: _chartScaleMin, maxValue: _chartScaleMax } };
        }
        return null;
      },
    });
    _emaFastSeries = _chart.addLineSeries({
      color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
    });
    _emaSlowSeries = _chart.addLineSeries({
      color: '#818cf8', lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
    });
    _volumeSeries = _chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
      lastValueVisible: false,
      priceLineVisible: false,
    });
    _chart.priceScale('vol').applyOptions({ borderColor: '#1a1a1a' });
    applyChartVolumeLayout();
    if (!window._tradeChartResize) {
      window._tradeChartResize = true;
      window.addEventListener('resize', () => {
        const c = document.getElementById('trade-chart');
        if (_chart && c) {
          _chart.applyOptions({
            width: c.clientWidth,
            height: Math.max(225, c.clientHeight || 263),
          });
        }
      });
    }
  }
  return true;
}

function chartLimitForTf(tf) {
  return candleLimitForView();
}

function deskChartUrl(tf, sym) {
  return '/poly/api/trade-desk/chart?timeframe=' + tf + '&symbol=' + sym
    + '&price_tf=' + _priceTf + '&limit=' + candleLimitForView()
    + '&algo=' + chartAlgoParam(tf) + '&gate=15&_=' + Date.now();
}

function hourlyTagColor(tag) {
  if (tag === 'A1') return '#a855f7';
  if (tag === 'A3') return '#2dd4bf';
  if (tag === 'ALFA') return '#f59e0b';
  return '#38bdf8';
}

function hourlyMarker(s) {
  const tag = s.tag || '?';
  return {
    time: s.time,
    position: s.dir === 'UP' ? 'belowBar' : 'aboveBar',
    color: hourlyTagColor(tag),
    shape: s.dir === 'UP' ? 'arrowUp' : 'arrowDown',
    text: tag,
  };
}

function appendHourlySlotMarker(markers, ws, cur, tag, color) {
  if (!cur || !cur.dir) return;
  markers.push({
    time: ws,
    position: cur.dir === 'UP' ? 'belowBar' : 'aboveBar',
    color: color,
    shape: cur.dir === 'UP' ? 'arrowUp' : 'arrowDown',
    text: tag,
  });
}

function appendSlotMarkers(markers, d, candles) {
  const ws = d.window_start;
  const hasWs = ws && candles.some(c => c.time === ws);
  if (!hasWs) return;
  const hc = d.hourly_current || {};
  markers.push({
    time: ws,
    position: 'aboveBar',
    color: '#fbbf24',
    shape: 'arrowDown',
    text: 'A1',
  });
  appendHourlySlotMarker(markers, ws, hc.a1, 'A1', '#a855f7');
  appendHourlySlotMarker(markers, ws, hc.a3, 'A3', '#2dd4bf');
  appendHourlySlotMarker(markers, ws, hc.a8, 'A8', '#38bdf8');
  appendHourlySlotMarker(markers, ws, hc.alfa, 'ALFA', '#f59e0b');
}

function hourlyPillHtml(hc, key, tag, cls) {
  const cur = hc && hc[key];
  if (cur) {
    const det = cur.detail ? ' title="' + String(cur.detail).replace(/"/g, '&quot;') + '"' : '';
    return '<span class="sig-pill ' + cls + '"' + det + '>' + (cur.label || tag) + '</span>';
  }
  return '<span class="sig-pill ' + cls + '">' + tag + ' —</span>';
}

function updateHourlyLegend(hc) {
  const el = document.getElementById('chart-signals');
  if (!el) return;
  if (!hc || (!hc.a1 && !hc.a3 && !hc.a8 && !hc.alfa)) { el.innerHTML = ''; return; }
  el.innerHTML =
    hourlyPillHtml(hc, 'a1', 'A1', 'a1') +
    hourlyPillHtml(hc, 'a3', 'A3', 'a3') +
    hourlyPillHtml(hc, 'a8', 'A8', 'a8') +
    hourlyPillHtml(hc, 'alfa', 'ALFA', 'alfa');
}

async function loadTradeChart() {
  const reqId = ++_chartReq;
  const sym = selectedSymbol();
  const tf = _tf;
  if (!ensureTradeChart()) return;
  try {
    const r = await fetch(deskChartUrl(tf, sym), { cache: 'no-store' });
    const d = prepareChartPayload(await r.json());
    if (reqId !== _chartReq) return;
    if (tf !== _tf || sym !== selectedSymbol()) return;
    const dec = d.dec != null ? d.dec : 2;
    const name = d.name || sym.replace('USDT', '');
    const slotLbl = tf === '5m' ? '5dk' : tf === '15m' ? '15dk' : '1saat';
    const pxLbl = d.price_tf === '1h' ? '1h' : (d.price_tf === '15m' ? '15m' : (d.price_tf === '5m' ? '5m' : '1m'));
    document.getElementById('chart-title').textContent = name + ' · ' + pxLbl;
    document.getElementById('chart-meta').textContent =
      (d.slot_label ? d.slot_label + ' İST · ' : '') + slotLbl + ' slot · '
      + (tf === '1h'
        ? 'A1+A3+A8+ALFA saatlik · A3/A8 ' + (d.a3a8_signal_mode_label || 'sıkı')
        : tf === '15m' ? '110+112+113' : '110 motor UP/DOWN')
      + ' · ' + pxLbl + ' mum';
    updateChartGuideLegend(d, tf);
    document.getElementById('chart-ref-lbl').textContent =
      d.ref_price != null ? '$' + Number(d.ref_price).toFixed(dec) : '—';
    if (_priceLine) {
      _candleSeries.removePriceLine(_priceLine);
      _priceLine = null;
    }
    if (!d.candles || !d.candles.length) {
      _candleSeries.setData([]);
      _candleSeries.setMarkers([]);
      if (_volumeSeries) _volumeSeries.setData([]);
      _chartScaleMin = null;
      _chartScaleMax = null;
      _chart.priceScale('right').applyOptions({ autoScale: true });
      return;
    }
    const candles = d.candles;
    _lastCandles = candles.slice();
    applyChartPriceScale(candles, d.ref_price);
    _candleSeries.setData(candles);
    if (_volumeSeries) _volumeSeries.setData(volumeHistogramData(candles));
    applyChartVolumeLayout();
    const barSp = fitBarDensity(candles.length);
    _chart.timeScale().applyOptions({ barSpacing: barSp, minBarSpacing: 1, fixRightEdge: false, rightOffset: 12 });
    focusDeskCandleWindow(candles);
    _chart.priceScale('right').applyOptions({ autoScale: true });
    if (d.ref_price != null) {
      _priceLine = _candleSeries.createPriceLine({
        price: d.ref_price,
        color: '#fbbf24',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: tf === '1h' ? 'A1' : 'Ref',
      });
    }
    const markers = [];
    const ov = tf !== '1h' && d.algo_overlay ? clipOverlayToCandles(d.algo_overlay, candles) : null;
    if (tf === '1h') {
      appendSlotMarkers(markers, d, candles);
      (d.hourly_signals || []).forEach(s => {
        const ws = d.window_start;
        if (s.time === ws && (s.tag === 'A1' || s.tag === 'A3' || s.tag === 'A8' || s.tag === 'ALFA')) return;
        markers.push(hourlyMarker(s));
      });
      applyMotorEma(null);
    } else {
      appendMotorSlotMarkers(markers, d, candles, ov);
      addMotorMarkers(markers, ov, d.window_start);
      if (tf === '15m') {
        appendFifteenSlotMarkers(markers, d, candles);
        addFifteenMarkers(markers, d.fifteen_signals, d.window_start);
      }
      applyMotorEma(ov);
    }
    _candleSeries.setMarkers(markers);
  } catch (e) {
    console.error(e);
  }
}

function renderOpen(rows) {
  const box = document.getElementById('open-pos');
  if (!rows.length) {
    box.innerHTML = '<div class="empty">Açık manuel pozisyon yok</div>';
    return;
  }
  box.innerHTML = `<table class="pos-table"><thead><tr>
    <th>TF</th><th>Sembol</th><th>Yön</th><th>Slot</th><th>Risk</th><th></th>
  </tr></thead><tbody>${rows.map(r => `
    <tr>
      <td>${r.timeframe === '5m' ? '5dk' : r.timeframe === '15m' ? '15dk' : '1saat'}</td>
      <td><b>${r.symbol}</b></td>
      <td>${r.dir_tr}</td>
      <td>${r.slot || '—'}</td>
      <td>$${r.spent.toFixed(2)}</td>
      <td><button type="button" class="close-sm" onclick="closePos('${r.symbol_full}','${r.timeframe}','${r.order_id || ''}')">Kapat</button></td>
    </tr>`).join('')}</tbody></table>`;
}

function applyCash(cash) {
  const el = document.getElementById('cash');
  if (el) el.textContent = 'USDC $' + (cash >= 0 ? cash.toFixed(2) : '?');
}

async function refreshCash() {
  try {
    const r = await fetch('/poly/api/trade-desk', { cache: 'no-store' });
    const d = await r.json();
    if (r.ok && d.cash != null) applyCash(d.cash);
  } catch (e) { console.error(e); }
}

async function loadDesk() {
  try {
    const symBefore = selectedSymbol();
    const idxBefore = _selectedIdx;
    const r = await fetch('/poly/api/trade-desk', {cache: 'no-store'});
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
    applyCash(d.cash);
    _quotes5 = d.quotes_5m || [];
    _quotes15 = d.quotes_15m || [];
    _quotes1h = d.quotes_1h || [];
    const quotes = quoteList();
    const want = _deskSymPref || 'SOLUSDT';
    let idx = quotes.findIndex(q => q.symbol === want);
    if (idx < 0) idx = quotes.findIndex(q => q.symbol === 'SOLUSDT');
    if (idx < 0) idx = 0;
    _selectedIdx = idx;
    renderQuotes(quotes);
    renderOpen(d.open_positions || []);
    saveDeskPrefs();
    const needPreview = !_deskInit || idxBefore !== _selectedIdx || symBefore !== selectedSymbol();
    _deskInit = true;
    if (needPreview) {
      refreshSpot();
      updatePreview();
    }
    loadTradeChart();
  } catch (e) {
    console.error(e);
    document.getElementById('quotes').innerHTML = '<div class="empty" style="color:#f87171">Yüklenemedi: ' + e.message + '</div>';
    document.getElementById('open-pos').innerHTML = '<div class="empty">—</div>';
  }
}

async function openTrade() {
  const btn = document.getElementById('open-btn');
  const amount = parseFloat(document.getElementById('amount').value);
  if (!amount || amount < 1) { showMsg('Min $1', false); return; }
  btn.disabled = true;
  showMsg('Emir gönderiliyor…', true);
  try {
    const estR = await fetch('/poly/api/trade-desk/estimate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        timeframe: _tf,
        symbol: selectedSymbol(),
        direction: _dir,
        amount: amount,
      }),
    });
    const estD = await estR.json();
    if (estD.plan && !estD.plan.allowed) {
      showMsg('❌ Min ~$' + estD.plan.min_amount.toFixed(2) + ' gerekir (5 pay kuralı)', false);
      btn.disabled = false;
      return;
    }
    const r = await fetch('/poly/api/trade-desk/open', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        timeframe: _tf,
        symbol: selectedSymbol(),
        direction: _dir,
        amount: amount,
      }),
    });
    const d = await r.json();
    if (d.ok) {
      showMsg('✅ ' + (d.message || 'Açıldı'), true);
      loadDesk();
    } else {
      showMsg('❌ ' + (d.error || 'Başarısız'), false);
    }
  } catch (e) {
    showMsg('❌ ' + e.message, false);
  }
  btn.disabled = false;
}

async function syncManual() {
  const btn = document.getElementById('sync-btn');
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  const prev = btn.textContent;
  btn.textContent = 'Senkron…';
  try {
    const r = await fetch('/poly/api/trade-desk/sync', { method: 'POST' });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Senkron başarısız');
    const n = d.added_count || 0;
    showMsg(n ? ('✅ Zincirden ' + n + ' pozisyon eklendi') : '✅ Yeni pozisyon yok — liste güncel', true);
    loadDesk();
  } catch (e) {
    showMsg('❌ ' + e.message, false);
  }
  btn.disabled = false;
  btn.textContent = prev;
}

async function closePos(sym, tf, orderId) {
  if (!confirm(sym.replace('USDT','') + ' ' + tfLabel(tf) + ' pozisyonu kapatılsın mı?')) return;
  try {
    let url = '/poly/api/close/manual/' + sym.replace('USDT','') + '?timeframe=' + encodeURIComponent(tf);
    if (orderId) url += '&order_id=' + encodeURIComponent(orderId);
    const r = await fetch(url, {method: 'POST'});
    const d = await r.json();
    if (d.ok) { loadDesk(); showMsg('Pozisyon kapatıldı', true); }
    else showMsg(d.error || 'Kapatılamadı', false);
  } catch (e) { showMsg(e.message, false); }
}

loadDeskPrefs();
loadDesk();
refreshCash();
setInterval(loadDesk, 15000);
setInterval(refreshCash, 10000);
setInterval(refreshSpot, 10000);
setInterval(loadTradeChart, 5000);

function tickLiveClock() {
  const el = document.getElementById('live-clock');
  if (!el) return;
  const parts = new Intl.DateTimeFormat('tr-TR', {
    timeZone: 'Europe/Istanbul',
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  }).formatToParts(new Date());
  const g = t => parts.find(p => p.type === t)?.value || '';
  el.textContent = g('day') + '.' + g('month') + '.' + g('year') + ' '
    + g('hour') + ':' + g('minute') + ':' + g('second') + ' İST';
}
tickLiveClock();
setInterval(tickLiveClock, 1000);
</script>
</body>
</html>"""


GRAFIK_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grafik — A1+A3+A8 — PolyMarket</title>
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%2316a34a'/><text x='50%25' y='50%25' font-size='20' text-anchor='middle' dominant-baseline='central' fill='white' font-family='Arial' font-weight='bold'>P</text></svg>">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;color:#e0e0e0;font-family:'Inter',system-ui,sans-serif;min-height:100vh;display:flex;overflow:hidden}
.sidebar{width:220px;background:#0a0f0a;padding:24px 16px;display:flex;flex-direction:column;gap:4px;flex-shrink:0;height:100vh;overflow-y:auto}
.logo{font-size:20px;font-weight:800;color:#fff;margin-bottom:8px;letter-spacing:-0.5px}
.logo span{color:#c8f135}
.sidebar-cash{display:block;background:#111;border:1px solid #2a2a2a;border-radius:12px;padding:8px 12px;font-size:13px;color:#9ae66e;font-weight:700;margin-bottom:16px;width:100%;text-align:center}
.nav-label{font-size:10px;color:#444;text-transform:uppercase;letter-spacing:1px;padding:12px 12px 4px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;color:#888;text-decoration:none;font-size:14px;transition:.15s}
.nav-item:hover{background:#1a1a1a;color:#fff}
.nav-item.active{background:#1a2e1a;color:#c8f135;font-weight:600}
.nav-dot{width:6px;height:6px;border-radius:50%;background:#333;flex-shrink:0}
.nav-item.active .nav-dot,.nav-item:hover .nav-dot{background:#c8f135}
.sidebar-footer{margin-top:auto;font-size:11px;color:#444;padding:12px;display:flex;align-items:center;gap:6px}
.sidebar-footer .dot{width:6px;height:6px;border-radius:50%;background:#4ade80}
.chart-full{flex:1;display:flex;flex-direction:column;min-width:0;padding:16px 20px 16px 0;height:100vh}
.chart-toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px;align-items:center;width:100%}
.params-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center;font-size:12px;color:#666}
.param-inp{width:52px;background:#0d0d0d;border:1px solid #2a2a2a;border-radius:8px;color:#fff;padding:6px 8px;font-size:12px;font-weight:700}
.param-lbl{font-size:10px;color:#555;text-transform:uppercase;font-weight:700}
.tabs{display:flex;gap:8px;flex-wrap:wrap}
.tab{background:#111;border:1px solid #2a2a2a;color:#888;font-size:13px;font-weight:700;padding:8px 16px;border-radius:12px;cursor:pointer}
.tab.active{background:#1a2e1a;border-color:#4ade80;color:#4ade80}
.tabs-px{margin-left:auto;display:flex;gap:6px;flex-shrink:0;align-items:center}
.tab-px{background:#111;border:1px solid #2a2a2a;color:#777;font-size:12px;font-weight:800;padding:6px 14px;border-radius:10px;cursor:pointer;min-width:42px;text-align:center}
.tab-px:hover:not(.active){border-color:#5a4a18;color:#ca8a04}
.tab-px.active{background:#2a2410;border-color:#fbbf24;color:#fbbf24;box-shadow:0 0 0 1px rgba(251,191,36,.15)}
.chart-panel-full{flex:1;background:#111;border:1px solid #1e1e1e;border-radius:16px;padding:14px 16px;display:flex;flex-direction:column;min-height:0}
.chart-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:8px;flex-wrap:wrap}
.chart-title{font-size:16px;font-weight:800;color:#fff}
.chart-meta{font-size:11px;color:#666;margin-top:2px}
.chart-ref{display:flex;flex-direction:column;align-items:flex-end;gap:2px}
.chart-ref-lbl{font-size:9px;color:#666;text-transform:uppercase;letter-spacing:.3px;font-weight:700}
.chart-ref-val{font-size:16px;font-weight:800;color:#fbbf24}
.spot-inline{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;margin-bottom:8px}
.spot-lbl{color:#666;font-size:10px;font-weight:700;text-transform:uppercase}
.spot-val{font-size:16px;font-weight:800;color:#fff;margin-left:6px}
.spot-delta{font-size:13px;font-weight:700;margin-left:6px}
.spot-delta.up{color:#4ade80}
.spot-delta.down{color:#f87171}
.algo-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
.algo-badge{display:inline-block;padding:6px 12px;border-radius:10px;font-size:13px;font-weight:800}
.algo-badge.up{background:#142814;color:#4ade80;border:1px solid #2a4a2a}
.algo-badge.down{background:#2a1414;color:#f87171;border:1px solid #5a2a2a}
.algo-badge.neutral{background:#1a1a1a;color:#888;border:1px solid #333}
.algo-badge.a1.up{background:#2a1a3a;color:#c084fc;border:1px solid #6b21a8}
.algo-badge.a1.down{background:#2a1420;color:#f0abfc;border:1px solid #6b21a8}
.algo-badge.a3.up{background:#0f2a24;color:#2dd4bf;border:1px solid #0d9488}
.algo-badge.a3.down{background:#2a1418;color:#5eead4;border:1px solid #0d9488}
.algo-badge.a8.up{background:#142814;color:#4ade80;border:1px solid #2a4a2a}
.algo-badge.a8.down{background:#2a1414;color:#f87171;border:1px solid #5a2a2a}
.algo-badge.alfa.up{background:#2a1f0a;color:#fbbf24;border:1px solid #f59e0b}
.algo-badge.alfa.down{background:#2a1410;color:#fb923c;border:1px solid #f59e0b}
.algo-badge.a112.up{background:#0c2340;color:#38bdf8;border:1px solid #0369a1}
.algo-badge.a112.down{background:#2a1414;color:#f87171;border:1px solid #0369a1}
.algo-badge.a113.up{background:#0f2a24;color:#2dd4bf;border:1px solid #0d9488}
.algo-badge.a113.down{background:#2a1418;color:#5eead4;border:1px solid #0d9488}
.algo-badge.m110.up{background:#1a2410;color:#c8f135;border:1px solid #4d7c0f}
.algo-badge.m110.down{background:#2a1418;color:#f87171;border:1px solid #5a2a2a}
.composite-wrap{margin-top:8px;border-top:1px solid #1a1a1a;padding-top:8px;flex-shrink:0}
.composite-lbl{font-size:10px;color:#555;text-transform:uppercase;font-weight:700;margin-bottom:4px}
#composite-chart{height:96px;width:100%}
.chart-split{flex:1;display:flex;flex-direction:column;min-height:0}
#trade-chart{flex:1;min-height:340px;width:100%}
@media(max-width:768px){body{flex-direction:column;overflow:auto}.sidebar{width:100%;height:auto}.chart-full{height:auto;padding:16px}}
</style>
</head>
<body>
<div class="sidebar">
  <div class="logo">Poly<span>Market</span></div>
  <div class="sidebar-cash" id="cash">USDC …</div>
  <div class="nav-label">Ana Menü</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item" href="/algoritma"><span class="nav-dot"></span>Algoritma</a>
  <a class="nav-item" href="/harita"><span class="nav-dot"></span>Sıcaklık Haritası</a>
  <a class="nav-item" href="/analizler"><span class="nav-dot"></span>Analizler</a>
  <a class="nav-item" href="/poly/islemler"><span class="nav-dot"></span>İşlemler</a>
  <a class="nav-item active" href="/poly/grafik"><span class="nav-dot"></span>Grafik</a>
  <a class="nav-item" href="/poly/gecmis"><span class="nav-dot"></span>Geçmiş</a>
  <a class="nav-item" href="/ayarlar"><span class="nav-dot"></span>Ayarlar</a>
  <div class="sidebar-footer"><span class="dot"></span>Canlı</div>
</div>
<div class="chart-full">
  <div class="chart-toolbar">
    <div class="tabs">
      <button type="button" class="tab active" id="tab-sol" onclick="setSym('SOLUSDT')">SOL</button>
      <button type="button" class="tab" id="tab-btc" onclick="setSym('BTCUSDT')">BTC</button>
    </div>
    <div class="tabs">
      <button type="button" class="tab" id="tab-5m" onclick="setTf('5m')">5 Dakika</button>
      <button type="button" class="tab active" id="tab-15m" onclick="setTf('15m')">15 Dakika</button>
      <button type="button" class="tab" id="tab-1h" onclick="setTf('1h')">1 Saat</button>
    </div>
    <div class="tabs tabs-px">
      <button type="button" class="tab-px active" id="tab-px-1m" onclick="setPriceTf('1m')">1m</button>
      <button type="button" class="tab-px" id="tab-px-5m" onclick="setPriceTf('5m')">5m</button>
      <button type="button" class="tab-px" id="tab-px-15m" onclick="setPriceTf('15m')">15m</button>
      <button type="button" class="tab-px" id="tab-px-1h" onclick="setPriceTf('1h')">1h</button>
    </div>
  </div>
  <div class="chart-panel-full">
    <div class="chart-head">
      <div>
        <div class="chart-title" id="chart-title">Grafik</div>
        <div class="chart-meta" id="chart-meta">110 motor UP/DOWN · 1m fiyat</div>
        <div class="algo-badges" id="algo-badges"><span class="algo-badge neutral">—</span></div>
      </div>
      <div class="chart-ref">
        <span class="chart-ref-lbl">Başlangıç (price to beat)</span>
        <span class="chart-ref-val" id="chart-ref-lbl">—</span>
      </div>
    </div>
    <div class="spot-inline">
      <div><span class="spot-lbl">Başlangıç</span><span class="spot-val" id="spot-ref">—</span></div>
      <div><span class="spot-lbl">Anlık</span><span class="spot-val" id="spot-live">—</span><span class="spot-delta" id="spot-delta"></span></div>
      <div style="margin-left:auto;font-size:11px;color:#555" id="spot-tf"></div>
    </div>
    <div class="chart-split">
      <div id="trade-chart"></div>
    </div>
  </div>
</div>
<script>
let _tf = '15m', _sym = 'SOLUSDT', _priceTf = '1m', _gate = 15;
let _chart = null, _candleSeries = null, _priceLine = null;
let _emaFastSeries = null, _emaSlowSeries = null, _volumeSeries = null;
let _chartSym = null, _chartTf = null, _chartReq = 0;
let _chartScaleMin = null, _chartScaleMax = null, _lastCandles = [];

const _CHART_TZ = 'Europe/Istanbul';
function utcToIstChartTime(utcSec) {
  if (utcSec == null) return utcSec;
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: _CHART_TZ,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(new Date(utcSec * 1000));
  const g = (t) => parseInt(parts.find(p => p.type === t).value, 10);
  return Date.UTC(g('year'), g('month') - 1, g('day'), g('hour'), g('minute'), g('second')) / 1000;
}
function shiftSeriesTimes(arr) {
  return (arr || []).map(p => Object.assign({}, p, { time: utcToIstChartTime(p.time) }));
}
function shiftSignalTimes(arr) {
  return (arr || []).map(s => Object.assign({}, s, { time: utcToIstChartTime(s.time) }));
}
function prepareChartPayload(raw) {
  const d = Object.assign({}, raw);
  d.candles = shiftSeriesTimes(raw.candles);
  if (raw.window_start != null) d.window_start = utcToIstChartTime(raw.window_start);
  if (raw.window_end != null) d.window_end = utcToIstChartTime(raw.window_end);
  if (raw.algo_overlay) {
    const ov = Object.assign({}, raw.algo_overlay);
    if (ov.overlays) {
      ov.overlays = Object.assign({}, ov.overlays, {
        ema_fast: shiftSeriesTimes(ov.overlays.ema_fast),
        ema_slow: shiftSeriesTimes(ov.overlays.ema_slow),
      });
    }
    ov.signals = shiftSignalTimes(ov.signals);
    d.algo_overlay = ov;
  }
  d.hourly_signals = shiftSignalTimes(raw.hourly_signals);
  return d;
}
const _chartLoc = {
  locale: 'tr-TR',
  timeFormatter: (t) => {
    const p = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit', hour12: false })
      .formatToParts(new Date(t * 1000));
    return p.find(x => x.type === 'hour').value + ':' + p.find(x => x.type === 'minute').value;
  },
};

function loadPrefs() {
  try {
    if (sessionStorage.getItem('desk_sym')) _sym = sessionStorage.getItem('desk_sym');
    if (sessionStorage.getItem('desk_tf')) _tf = sessionStorage.getItem('desk_tf');
    const px = sessionStorage.getItem('desk_price_tf');
    if (px === '1m' || px === '5m' || px === '15m' || px === '1h') _priceTf = px;
  } catch (e) {}
}
function savePrefs() {
  try {
    sessionStorage.setItem('desk_sym', _sym);
    sessionStorage.setItem('desk_tf', _tf);
    sessionStorage.setItem('desk_price_tf', _priceTf);
  } catch (e) {}
}
loadPrefs();
function selectedSymbol() { return _sym; }

function syncTabs() {
  document.getElementById('tab-sol').classList.toggle('active', _sym === 'SOLUSDT');
  document.getElementById('tab-btc').classList.toggle('active', _sym === 'BTCUSDT');
  document.getElementById('tab-5m').classList.toggle('active', _tf === '5m');
  document.getElementById('tab-15m').classList.toggle('active', _tf === '15m');
  document.getElementById('tab-1h').classList.toggle('active', _tf === '1h');
  document.getElementById('tab-px-1m').classList.toggle('active', _priceTf === '1m');
  document.getElementById('tab-px-5m').classList.toggle('active', _priceTf === '5m');
  document.getElementById('tab-px-15m').classList.toggle('active', _priceTf === '15m');
  document.getElementById('tab-px-1h').classList.toggle('active', _priceTf === '1h');
}

function setSym(sym) { _sym = sym; savePrefs(); resetAllCharts(); refreshSpot(); loadTradeChart(); syncTabs(); }
function setTf(tf) { _tf = tf; savePrefs(); resetAllCharts(); refreshSpot(); loadTradeChart(); syncTabs(); }
function setPriceTf(px) { _priceTf = px; savePrefs(); resetAllCharts(); loadTradeChart(); syncTabs(); }

function chartH() {
  return Math.max(420, window.innerHeight - 180);
}

function candleLimitForView() {
  if (_priceTf === '1h') {
    if (_tf === '1h') return 48;
    if (_tf === '5m') return 12;
    return 24;
  }
  if (_priceTf === '15m') {
    if (_tf === '1h') return 48;
    if (_tf === '5m') return 12;
    return 16;
  }
  if (_priceTf === '5m') {
    if (_tf === '1h') return 24;
    if (_tf === '5m') return 12;
    return 12;
  }
  if (_tf === '1h') return 120;
  if (_tf === '5m') return 36;
  return 60;
}

function priceBarSeconds() {
  if (_priceTf === '1h') return 3600;
  if (_priceTf === '15m') return 900;
  if (_priceTf === '5m') return 300;
  return 60;
}

function calcTightScale(candles, refPrice) {
  if (!candles.length) return null;
  let lo = Math.min(...candles.map(c => c.low)), hi = Math.max(...candles.map(c => c.high));
  if (refPrice != null) { lo = Math.min(lo, refPrice); hi = Math.max(hi, refPrice); }
  const span = Math.max(hi - lo, 0.0001), pad = Math.max(span * 0.06, span * 0.015);
  return { lo: lo - pad, hi: hi + pad };
}
function applyChartPriceScale(candles, refPrice) {
  const tight = calcTightScale(candles, refPrice);
  if (!tight) { _chartScaleMin = _chartScaleMax = null; return; }
  _chartScaleMin = tight.lo; _chartScaleMax = tight.hi;
  if (_candleSeries) _candleSeries.applyOptions({ autoscaleInfoProvider: () => ({ priceRange: { minValue: _chartScaleMin, maxValue: _chartScaleMax } }) });
}
function fitBarDensity(count) {
  const c = document.getElementById('trade-chart');
  if (!c || !count) return 8;
  const w = Math.max(400, c.clientWidth - 64);
  return Math.max(8, Math.min(18, Math.floor((w / count) * 0.95)));
}

function focusCandleWindow(candles) {
  if (!_chart || !candles || candles.length < 2) return;
  const barSec = priceBarSeconds();
  _chart.timeScale().setVisibleRange({
    from: candles[0].time - barSec * 2,
    to: candles[candles.length - 1].time + barSec * 20,
  });
}

function resetAllCharts() {
  if (_chart) { _chart.remove(); _chart = null; }
  _candleSeries = _priceLine = _emaFastSeries = _emaSlowSeries = _volumeSeries = null;
  _chartScaleMin = _chartScaleMax = null; _chartSym = null;
}

function volumeHistogramData(candles) {
  return (candles || []).map(c => ({
    time: c.time,
    value: Number(c.volume) || 0,
    color: c.close >= c.open ? 'rgba(38,166,154,0.55)' : 'rgba(239,83,80,0.55)',
  }));
}

function applyChartVolumeLayout() {
  if (!_chart) return;
  _chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.05, bottom: 0.28 } });
  if (_chart.priceScale('vol')) {
    _chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.72, bottom: 0 } });
  }
}

function chartAlgoParam(tf) {
  return tf === '1h' ? 'off' : '110';
}

function clipOverlayToCandles(ov, candles) {
  if (!ov || !ov.overlays || !candles.length) return ov;
  const t0 = candles[0].time, t1 = candles[candles.length - 1].time;
  const clip = (arr) => (arr || []).filter(p => p.time >= t0 && p.time <= t1);
  return Object.assign({}, ov, {
    overlays: Object.assign({}, ov.overlays, {
      ema_fast: clip(ov.overlays.ema_fast),
      ema_slow: clip(ov.overlays.ema_slow),
    }),
    signals: (ov.signals || []).filter(s => s.time >= t0 && s.time <= t1),
  });
}

function motorSlotDir(ov, ws) {
  if (!ov || !ov.ok) return null;
  const cur = ov.current;
  if (cur && (cur.direction === 'UP' || cur.direction === 'DOWN')) {
    return cur.direction;
  }
  const sigs = ov.signals || [];
  for (let i = sigs.length - 1; i >= 0; i--) {
    if (sigs[i].time === ws) return sigs[i].dir;
  }
  let last = null;
  for (const s of sigs) {
    if (ws == null || s.time <= ws) last = s.dir;
  }
  return last;
}

function appendMotorSlotMarkers(markers, d, candles, ov) {
  const ws = d.window_start;
  if (!ws || !candles.some(c => c.time === ws)) return;
  const dir = motorSlotDir(ov, ws);
  if (!dir) {
    markers.push({
      time: ws,
      position: 'aboveBar',
      color: '#888',
      shape: 'circle',
      text: '110',
    });
    return;
  }
  markers.push({
    time: ws,
    position: dir === 'UP' ? 'belowBar' : 'aboveBar',
    color: dir === 'UP' ? '#4ade80' : '#c8f135',
    shape: dir === 'UP' ? 'arrowUp' : 'arrowDown',
    text: '110',
  });
}

function addMotorMarkers(markers, ov, skipTime) {
  if (!ov || !ov.ok) return;
  (ov.signals || []).forEach(s => {
    if (skipTime != null && s.time === skipTime) return;
    markers.push({
      time: s.time,
      position: s.dir === 'UP' ? 'belowBar' : 'aboveBar',
      color: s.dir === 'UP' ? '#4ade80' : '#f87171',
      shape: s.dir === 'UP' ? 'arrowUp' : 'arrowDown',
      text: s.dir,
    });
  });
}

function ensureTradeChart() {
  const container = document.getElementById('trade-chart');
  if (!container) return false;
  const sym = selectedSymbol();
  if (_chart && (_chartSym !== sym + _priceTf || _chartTf !== _tf)) resetAllCharts();
  if (!_chart) {
    _chartSym = sym + _priceTf; _chartTf = _tf;
    _chart = LightweightCharts.createChart(container, {
      width: container.clientWidth, height: chartH(),
      layout: { background: { color: '#0a0a0a' }, textColor: '#555' },
      grid: { vertLines: { color: '#121212' }, horzLines: { color: '#121212' } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      localization: _chartLoc,
      timeScale: { borderColor: '#1a1a1a', timeVisible: true, secondsVisible: false, barSpacing: 4, minBarSpacing: 1, rightOffset: 20, fixRightEdge: false },
      rightPriceScale: { borderColor: '#1a1a1a', autoScale: true, scaleMargins: { top: 0.01, bottom: 0.01 } },
    });
    _candleSeries = _chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350', borderUpColor: '#26a69a', borderDownColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
      autoscaleInfoProvider: () => (_chartScaleMin != null) ? { priceRange: { minValue: _chartScaleMin, maxValue: _chartScaleMax } } : null,
    });
    _emaFastSeries = _chart.addLineSeries({
      color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      autoscaleInfoProvider: () => (_chartScaleMin != null) ? { priceRange: { minValue: _chartScaleMin, maxValue: _chartScaleMax } } : null,
    });
    _emaSlowSeries = _chart.addLineSeries({
      color: '#818cf8', lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      autoscaleInfoProvider: () => (_chartScaleMin != null) ? { priceRange: { minValue: _chartScaleMin, maxValue: _chartScaleMax } } : null,
    });
    _volumeSeries = _chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
      lastValueVisible: false,
      priceLineVisible: false,
    });
    _chart.priceScale('vol').applyOptions({ borderColor: '#1a1a1a' });
    applyChartVolumeLayout();
    window.addEventListener('resize', () => {
      const c = document.getElementById('trade-chart');
      if (_chart && c) _chart.applyOptions({ width: c.clientWidth, height: chartH() });
    });
  }
  return true;
}

function renderHourlyBadges(hc) {
  const el = document.getElementById('algo-badges');
  if (!el) return;
  const items = [
    { key: 'a1', tag: 'A1', cls: 'a1' },
    { key: 'a3', tag: 'A3', cls: 'a3' },
    { key: 'a8', tag: 'A8', cls: 'a8' },
    { key: 'alfa', tag: 'ALFA', cls: 'alfa' },
  ];
  el.innerHTML = items.map(({ key, tag, cls }) => {
    const cur = hc && hc[key];
    const det = cur && cur.detail ? ' title="' + String(cur.detail).replace(/"/g, '&quot;') + '"' : '';
    if (!cur || !cur.dir) {
      return '<span class="algo-badge neutral ' + cls + '"' + det + '>' + (cur && cur.label ? cur.label : tag + ' —') + '</span>';
    }
    const up = cur.dir === 'UP';
    return '<span class="algo-badge ' + cls + ' ' + (up ? 'up' : 'down') + '"' + det + '>' + (cur.label || tag) + '</span>';
  }).join('');
}

function updateMotorBadge(ov) {
  const el = document.getElementById('algo-badges');
  if (!el) return;
  if (!ov || !ov.ok || !ov.current) {
    el.innerHTML = '<span class="algo-badge neutral m110">110 · —</span>';
    return;
  }
  const cur = ov.current;
  const dir = cur.direction;
  if (dir === 'UP' || dir === 'DOWN') {
    const cls = dir === 'UP' ? 'up' : 'down';
    el.innerHTML = '<span class="algo-badge m110 ' + cls + '">110 · ' + dir + '</span>';
    return;
  }
  el.innerHTML = '<span class="algo-badge neutral m110">110 · ' + (cur.label || '—') + '</span>';
}

function renderFifteenBadges(d, ov) {
  const el = document.getElementById('algo-badges');
  if (!el) return;
  let html = '';
  if (!ov || !ov.ok || !ov.current) {
    html += '<span class="algo-badge neutral m110">110 · —</span>';
  } else {
    const cur = ov.current;
    const dir = cur.direction;
    if (dir === 'UP' || dir === 'DOWN') {
      html += '<span class="algo-badge m110 ' + (dir === 'UP' ? 'up' : 'down') + '">110 · ' + dir + '</span>';
    } else {
      html += '<span class="algo-badge neutral m110">110 · ' + (cur.label || '—') + '</span>';
    }
  }
  const fc = d.fifteen_current || {};
  [{ key: 'a112', tag: '112', cls: 'a112' }, { key: 'a113', tag: '113', cls: 'a113' }].forEach(({ key, tag, cls }) => {
    const cur = fc[key];
    if (!cur || !cur.dir) {
      html += '<span class="algo-badge neutral ' + cls + '">' + (cur && cur.label ? cur.label : tag + ' —') + '</span>';
      return;
    }
    const up = cur.dir === 'UP';
    html += '<span class="algo-badge ' + cls + ' ' + (up ? 'up' : 'down') + '">' + (cur.label || tag) + '</span>';
  });
  el.innerHTML = html;
}

function fifteenTagColor(tag) {
  if (tag === '112') return '#38bdf8';
  if (tag === '113') return '#2dd4bf';
  return '#888';
}

function fifteenMarker(s) {
  const tag = s.tag || '?';
  return {
    time: s.time,
    position: s.dir === 'UP' ? 'belowBar' : 'aboveBar',
    color: fifteenTagColor(tag),
    shape: s.dir === 'UP' ? 'arrowUp' : 'arrowDown',
    text: tag,
  };
}

function appendFifteenSlotMarkers(markers, d, candles) {
  const ws = d.window_start;
  if (!ws || !candles.some(c => c.time === ws)) return;
  const fc = d.fifteen_current || {};
  appendHourlySlotMarker(markers, ws, fc.a112, '112', '#38bdf8');
  appendHourlySlotMarker(markers, ws, fc.a113, '113', '#2dd4bf');
}

function addFifteenMarkers(markers, signals, ws) {
  (signals || []).forEach(s => {
    if (ws && s.time === ws && (s.tag === '112' || s.tag === '113')) return;
    markers.push(fifteenMarker(s));
  });
}

function hourlyTagColor(tag) {
  if (tag === 'A1') return '#a855f7';
  if (tag === 'A3') return '#2dd4bf';
  if (tag === 'ALFA') return '#f59e0b';
  return '#38bdf8';
}

function hourlyMarker(s) {
  const tag = s.tag || '?';
  return {
    time: s.time,
    position: s.dir === 'UP' ? 'belowBar' : 'aboveBar',
    color: hourlyTagColor(tag),
    shape: s.dir === 'UP' ? 'arrowUp' : 'arrowDown',
    text: tag,
  };
}

function appendHourlySlotMarker(markers, ws, cur, tag, color) {
  if (!cur || !cur.dir) return;
  markers.push({
    time: ws,
    position: cur.dir === 'UP' ? 'belowBar' : 'aboveBar',
    color: color,
    shape: cur.dir === 'UP' ? 'arrowUp' : 'arrowDown',
    text: tag,
  });
}

function addHourlyMarkers(markers, hourly, d) {
  const ws = d && d.window_start;
  (hourly || []).forEach(s => {
    if (s.tag === 'A1' && ws && s.time === ws) return;
    if (s.tag === 'A3' && ws && s.time === ws) return;
    if (s.tag === 'A8' && ws && s.time === ws) return;
    if (s.tag === 'ALFA' && ws && s.time === ws) return;
    markers.push(hourlyMarker(s));
  });
}

function appendSlotMarkers(markers, d, candles) {
  const ws = d.window_start;
  const hasWs = ws && candles.some(c => c.time === ws);
  if (!hasWs) return;
  const hc = d.hourly_current || {};
  markers.push({
    time: ws,
    position: 'aboveBar',
    color: '#fbbf24',
    shape: 'arrowDown',
    text: 'A1',
  });
  appendHourlySlotMarker(markers, ws, hc.a1, 'A1', '#a855f7');
  appendHourlySlotMarker(markers, ws, hc.a3, 'A3', '#2dd4bf');
  appendHourlySlotMarker(markers, ws, hc.a8, 'A8', '#38bdf8');
  appendHourlySlotMarker(markers, ws, hc.alfa, 'ALFA', '#f59e0b');
}

function patchLastCandle(price, dec) {
  if (!_lastCandles.length || price == null) return;
  const c = Object.assign({}, _lastCandles[_lastCandles.length - 1]);
  c.close = Number(price.toFixed(dec != null ? dec : 2));
  c.high = Math.max(c.high, c.close); c.low = Math.min(c.low, c.close);
  _lastCandles[_lastCandles.length - 1] = c;
  if (_candleSeries) _candleSeries.update(c);
}

async function refreshSpot() {
  const sym = selectedSymbol(), tf = _tf;
  try {
    const r = await fetch('/poly/api/trade-desk/spot?timeframe=' + tf + '&symbol=' + sym, { cache: 'no-store' });
    const q = await r.json();
    if (tf !== _tf || sym !== selectedSymbol()) return;
    const refEl = document.getElementById('spot-ref'), liveEl = document.getElementById('spot-live');
    const deltaEl = document.getElementById('spot-delta'), tfEl = document.getElementById('spot-tf');
    if (tfEl) tfEl.textContent = q && q.slot_label ? q.slot_label + ' İST · ' + (tf === '15m' ? '15dk' : '1saat') : '';
    if (!q || q.ref_price == null) { refEl.textContent = liveEl.textContent = '—'; deltaEl.textContent = ''; return; }
    const dec = q.dec != null ? q.dec : 2;
    refEl.textContent = '$' + Number(q.ref_price).toFixed(dec);
    liveEl.textContent = q.live_price != null ? '$' + Number(q.live_price).toFixed(dec) : '—';
    if (q.delta != null) {
      deltaEl.className = 'spot-delta ' + (q.delta >= 0 ? 'up' : 'down');
      deltaEl.textContent = (q.delta >= 0 ? '+' : '-') + '$' + Math.abs(q.delta).toFixed(dec);
    } else { deltaEl.textContent = ''; deltaEl.className = 'spot-delta'; }
    if (q.live_price != null) patchLastCandle(Number(q.live_price), dec);
  } catch (e) { console.error(e); }
}

function chartUrl() {
  return '/poly/api/trade-desk/chart?timeframe=' + _tf + '&symbol=' + selectedSymbol()
    + '&algo=' + chartAlgoParam(_tf) + '&gate=' + _gate
    + '&price_tf=' + _priceTf + '&limit=' + candleLimitForView()
    + '&_=' + Date.now();
}

async function loadTradeChart() {
  const reqId = ++_chartReq;
  const sym = selectedSymbol(), tf = _tf;
  if (!ensureTradeChart()) return;
  try {
    const r = await fetch(chartUrl(), { cache: 'no-store' });
    const d = prepareChartPayload(await r.json());
    if (reqId !== _chartReq || tf !== _tf || sym !== selectedSymbol()) return;
    const dec = d.dec != null ? d.dec : 2;
    const pxLbl = d.price_tf === '1h' ? '1h' : (d.price_tf === '15m' ? '15m' : (d.price_tf === '5m' ? '5m' : '1m'));
    document.getElementById('chart-title').textContent = (d.name || sym.replace('USDT','')) + ' · ' + pxLbl;
    document.getElementById('chart-meta').textContent =
      (_tf === '1h' ? 'A1 + A3 + A8 + ALFA saatlik · A3/A8 ' + (d.a3a8_signal_mode_label || 'sıkı') : _tf === '15m' ? '110 + 112 + 113' : '110 motor UP/DOWN') + ' · ' + pxLbl + ' mum · ' + (d.slot_label || '') + ' İST';
    document.getElementById('chart-ref-lbl').textContent = d.ref_price != null ? '$' + Number(d.ref_price).toFixed(dec) : '—';
    if (_priceLine) { _candleSeries.removePriceLine(_priceLine); _priceLine = null; }
    if (!d.candles || !d.candles.length) {
      _candleSeries.setData([]); _candleSeries.setMarkers([]);
      if (_volumeSeries) _volumeSeries.setData([]);
      return;
    }
    _lastCandles = d.candles.slice();
    applyChartPriceScale(d.candles, d.ref_price);
    _candleSeries.setData(d.candles);
    if (_volumeSeries) _volumeSeries.setData(volumeHistogramData(d.candles));
    applyChartVolumeLayout();
    const barSp = fitBarDensity(d.candles.length);
    _chart.applyOptions({ width: document.getElementById('trade-chart').clientWidth, height: chartH() });
    _chart.timeScale().applyOptions({ barSpacing: barSp, minBarSpacing: 4, fixRightEdge: false, rightOffset: 20 });
    if (d.ref_price != null) {
      _priceLine = _candleSeries.createPriceLine({
        price: d.ref_price, color: '#fbbf24', lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true,
        title: _tf === '1h' ? 'A1' : 'Ref',
      });
    }
    const markers = [];
    const ov = _tf !== '1h' && d.algo_overlay ? clipOverlayToCandles(d.algo_overlay, d.candles) : null;
    if (_tf === '1h') {
      renderHourlyBadges(d.hourly_current);
      appendSlotMarkers(markers, d, d.candles);
      addHourlyMarkers(markers, d.hourly_signals, d);
      if (_emaFastSeries) { _emaFastSeries.setData([]); _emaSlowSeries.setData([]); }
    } else {
      if (_tf === '15m') renderFifteenBadges(d, ov);
      else updateMotorBadge(ov);
      appendMotorSlotMarkers(markers, d, d.candles, ov);
      addMotorMarkers(markers, ov, d.window_start);
      if (_tf === '15m') {
        appendFifteenSlotMarkers(markers, d, d.candles);
        addFifteenMarkers(markers, d.fifteen_signals, d.window_start);
      }
      if (_emaFastSeries && ov && ov.overlays) {
        _emaFastSeries.setData(ov.overlays.ema_fast || []);
        _emaSlowSeries.setData(ov.overlays.ema_slow || []);
      }
    }
    focusCandleWindow(d.candles);
    _candleSeries.setMarkers(markers);
  } catch (e) { console.error(e); }
}

async function refreshCash() {
  try {
    const r = await fetch('/poly/api/trade-desk', { cache: 'no-store' });
    const d = await r.json();
    if (r.ok && d.cash != null) {
      const el = document.getElementById('cash');
      if (el) el.textContent = 'USDC $' + (d.cash >= 0 ? d.cash.toFixed(2) : '?');
    }
  } catch (e) {}
}

syncTabs(); refreshCash(); refreshSpot(); loadTradeChart();
setInterval(refreshCash, 10000);
setInterval(refreshSpot, 3000);
setInterval(loadTradeChart, 5000);
</script>
</body>
</html>"""


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

    for key, label in analyses.items():
        if key in _ALGO_STATS_EXCLUDE:
            continue
        hist = _load_trader_history(key)
        if not hist and not os.path.exists(_trader_history_path(key)):
            continue
        total = len(hist)
        wins  = sum(1 for t in hist if t.get("win"))
        pnl   = sum(t.get("pnl", 0) for t in hist)
        wr    = round(wins / total * 100, 1) if total else 0
        algo_stats.append({
            "key": key, "label": label,
            "total": total, "wins": wins,
            "wr": wr, "pnl": round(pnl, 2),
        })

    # Son işlemler: Polymarket data-api (gerçek on-chain activity)
    slug_labels: dict[str, str] = {}
    for key, label in _PM_POSITION_SOURCES:
        for t in _load_trader_history(key):
            if not _is_live_pm_trade(t):
                continue
            slug = t.get("pm_slug")
            if slug:
                slug_labels[slug] = label
    for pos in collect_positions():
        slug = pos.get("pm_slug")
        if slug:
            slug_labels[slug] = pos.get("_analiz_label") or slug_labels.get(slug, "PM")

    sys.path.insert(0, _DIR_POLY)
    pending: list[dict] = []
    try:
        from pm_poly_history import get_open_pm_trades, get_recent_pm_trades
        recent = get_recent_pm_trades(limit=20, slug_labels=slug_labels)
        pending = get_open_pm_trades(limit=10, slug_labels=slug_labels)
        pending, recent = _merge_pm_recent_trades(pending, recent)
    except Exception as e:
        print(f"[dashboard] pm_poly_history: {e}", file=sys.stderr)
        live_history = []
        for key, label in _PM_POSITION_SOURCES:
            for t in _load_trader_history(key):
                if t.get("win") is None or not _is_live_pm_trade(t):
                    continue
                live_history.append({**t, "_analiz": label})
        live_history.sort(key=lambda x: x.get("exit_time_tr", ""), reverse=True)
        recent = []
        for t in live_history[:20]:
            sym = t.get("symbol", "").replace("USDT", "")
            spent = t.get("pm_spent") or t.get("amount", 0)
            pnl_val = t.get("pnl", 0)
            etime = t.get("exit_time_tr", "")[:16].replace("T", " ")
            recent.append({
                "sym": sym, "dir": t.get("predicted_dir", ""), "win": t.get("win", False),
                "spent": round(spent, 2) if spent else 0,
                "pnl": round(pnl_val, 2),
                "time": etime,
                "analiz": t.get("_analiz", ""),
            })
        pending = []

    algo_stats.sort(key=lambda x: x["wr"], reverse=True)
    return jsonify({"algo_stats": algo_stats, "recent": recent, "pending": pending})


@app.route("/poly/api/pm-profit")
def api_pm_profit():
    if _auth_required():
        return redirect("/poly/login")
    return jsonify(get_pm_profit_breakdown())


@app.route("/poly/api/pm-system", methods=["GET"])
def api_pm_system_get():
    if _auth_required():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    sys.path.insert(0, _DIR_POLY)
    from pm_balance_guard import get_pm_system_control
    return jsonify({"ok": True, **get_pm_system_control()})


@app.route("/poly/api/pm-system", methods=["POST"])
def api_pm_system_post():
    if _auth_required():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    sys.path.insert(0, _DIR_POLY)
    from pm_balance_guard import (
        get_pm_system_control,
        set_a3a8_signal_strict,
        set_group_paused,
        set_pm_open_paused,
        toggle_group_paused,
        toggle_pm_open_paused,
    )
    body = request.get_json(force=True) if request.is_json else {}
    if "a3a8_signal_strict" in body:
        state = set_a3a8_signal_strict(bool(body["a3a8_signal_strict"]), source="dashboard")
        return jsonify({"ok": True, **state})
    group = body.get("group")
    if group in ("analiz5", "analiz2", "m15_210", "hourly"):
        if group == "hourly":
            if "paused" in body:
                paused = bool(body["paused"])
            else:
                cur = get_pm_system_control()
                paused = not (cur["analiz5_paused"] and cur["analiz2_paused"])
            set_group_paused("analiz5", paused, source="dashboard")
            state = set_group_paused("analiz2", paused, source="dashboard")
        elif "paused" in body:
            state = set_group_paused(group, bool(body["paused"]), source="dashboard")
        else:
            state = toggle_group_paused(group, source="dashboard")
    elif "paused" in body:
        state = set_pm_open_paused(bool(body["paused"]), source="dashboard")
    else:
        state = toggle_pm_open_paused(source="dashboard")
    return jsonify({"ok": True, **state})


def _pm_get_clob_client():
    from pm_trader_helpers import pm_get_client
    return pm_get_client()


def _pm_conditional_shares(token_id: str) -> float:
    """Zincirdeki gerçek conditional token adedi (-1 = okunamadı)."""
    from decimal import Decimal, ROUND_DOWN
    try:
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
        client = _pm_get_clob_client()
        bal = client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
        )
        raw = int(bal.get("balance", 0))
        return float(Decimal(str(raw / 1_000_000)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
    except Exception as e:
        print(f"[dashboard] conditional balance: {e}", flush=True)
        return -1.0


def _pm_best_bid(client, token_id: str) -> float | None:
    """Satış için en yüksek bid — orderbook yoksa None."""
    try:
        book = client.get_order_book(token_id)
        bids = book.get("bids") or []
        if bids:
            return max(float(b["price"]) for b in bids)
    except Exception:
        pass
    return None


def _pm_sell_price(client, token_id: str, size: float, pm_slug: str = "", token_dir: str = "") -> float:
    """Satış fiyatı: orderbook bid → market price → gamma fiyat."""
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

    if pm_slug and token_dir:
        gp = get_pm_token_price(pm_slug, token_dir)
        if gp and gp > 0:
            return max(0.02, min(0.98, round(gp - 0.01, 2)))

    return 0.50


def _pm_sell_ladder_prices(client, token_id: str, size: float, pm_slug: str = "", token_dir: str = "") -> list[float]:
    """FAK satış için azalan fiyat listesi (gamma → bid → piyasa)."""
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
    if pm_slug and token_dir:
        gp = get_pm_token_price(pm_slug, token_dir)
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


def _estimate_close_value(pos: dict) -> dict:
    """CLOB satış bid → gerçekçi anlık kapatma tutarı."""
    pm_size = float(pos.get("pm_size") or 0)
    pm_spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    if not pm_size:
        return {"close_val": None, "close_pnl": None, "token_cents": None}
    token_id = pos.get("pm_token_id")
    slug = pos.get("pm_slug", "")
    token_dir = pos.get("pm_token_dir") or pos.get("predicted_dir", "")
    sell_price = None
    if token_id:
        try:
            client = _pm_get_clob_client()
            sell_price = _pm_sell_price(client, token_id, pm_size, slug, token_dir)
        except Exception:
            pass
    if not sell_price:
        gp = get_pm_token_price(slug, token_dir)
        if gp and gp > 0:
            sell_price = max(0.02, round(gp - 0.01, 2))
    if not sell_price:
        return {"close_val": None, "close_pnl": None, "token_cents": None}
    close_val = round(pm_size * sell_price, 2)
    return {
        "close_val": close_val,
        "close_pnl": round(close_val - pm_spent, 2),
        "token_cents": round(sell_price * 100, 1),
    }


def _pm_sell_position(token_id: str, size: float, pm_slug: str = "", token_dir: str = "") -> dict:
    """Polymarket'ta token sat (pozisyonu kapat)."""
    from decimal import Decimal, ROUND_DOWN

    try:
        client = _pm_get_clob_client()
    except Exception as e:
        return {"ok": False, "error": f"client init hatası: {e}"}

    try:
        from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
        from py_clob_client_v2.order_builder.constants import SELL

        size = float(Decimal(str(size)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        if size <= 0:
            return {"ok": False, "error": "geçersiz boyut"}

        last_err = "bilinmeyen hata"
        for price in _pm_sell_ladder_prices(client, token_id, size, pm_slug, token_dir):
            try:
                args = OrderArgs(token_id=token_id, price=price, size=size, side=SELL)
                signed = client.create_order(args, PartialCreateOrderOptions())
                resp = client.post_order(signed, order_type=OrderType.FAK)
                print(f"[dashboard] PM sell @{price}: {resp}", flush=True)
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


def _pm_sell_position_retry(
    token_id: str, size: float, pm_slug: str = "", token_dir: str = "",
) -> dict:
    """Zincir bakiyesine göre sat; kısmi dolumda tekrar dene."""
    from decimal import Decimal, ROUND_DOWN

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
        remaining = round(remaining - sold, 2)
        if remaining <= 0.01:
            break

    if total_received > 0 or last.get("reconciled"):
        out = dict(last)
        out["ok"] = True
        out["received"] = round(total_received, 2)
        out["size"] = round(req - remaining, 2)
        return out
    return last


def _pm_fetch_outcome_prices(slug: str) -> tuple[float, float] | None:
    """Gamma outcome fiyatları (UP, DOWN)."""
    if not slug:
        return None
    try:
        req = urllib.request.Request(
            f"https://gamma-api.polymarket.com/events?slug={slug}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        if not data:
            return None
        m = data[0].get("markets", [{}])[0]
        raw_op = m.get("outcomePrices")
        op = json.loads(raw_op) if isinstance(raw_op, str) else (raw_op or [])
        if len(op) < 2:
            return None
        return float(op[0]), float(op[1])
    except Exception:
        return None


def _pm_try_worthless_reconcile(pos: dict) -> dict | None:
    """Token ~$0 (karşı taraf kazandı) — satış yok, kayıp olarak kapat."""
    prices = _pm_fetch_outcome_prices(pos.get("pm_slug", ""))
    if not prices:
        return None
    up_p, down_p = prices
    token_dir = (pos.get("pm_token_dir") or pos.get("predicted_dir") or "").upper()
    lost = (token_dir == "UP" and up_p <= 0.05) or (token_dir == "DOWN" and down_p <= 0.05)
    if not lost:
        return None
    return {
        "ok": True,
        "reconciled": True,
        "worthless": True,
        "received": 0.0,
        "size": float(pos.get("pm_size") or 0),
        "price": 0.0,
        "status": "settled_loss",
    }


def _short_pm_error(err: str) -> str:
    """UI için kısa Türkçe hata."""
    s = str(err or "")
    low = s.lower()
    if "no orders found" in low or "fak" in low:
        return "Likidite yok — slot sonunda otomatik kapanır"
    if "invalid token" in low or "orderbook" in low:
        return "Piyasa kapandı — settle bekleniyor"
    if "unauthorized" in low:
        return "Oturum gerekli — yeniden giriş yap"
    if len(s) > 72:
        return s[:69] + "…"
    return s or "PM satış başarısız"


_PM_TG_LABELS = {
    "analiz5": "A1 LIVE",
    "analiz2_live": "2. ANALİZ LIVE",
    "manual": "MANUEL PM",
}


def _tg_notify_pm_early_close(analiz: str, pos: dict, sell_result: dict) -> None:
    """Dashboard erken PM satışı — PolyAktif kanalına bildirim."""
    if analiz not in _HOURLY_PM_ANALYSES:
        return
    label = _PM_TG_LABELS.get(analiz, analiz.upper())
    try:
        from pm_trader_helpers import tg_send_pm_live, pm_get_balance, pm_tg_stake
    except ImportError:
        return

    sym = pos.get("symbol", "")
    name = sym.replace("USDT", "")
    pred = pos.get("predicted_dir") or pos.get("pm_token_dir", "")
    entry = float(pos.get("entry_price") or 0)
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    received = float(sell_result.get("received") or 0)
    pnl = round(received - spent, 2)
    icon = "✅" if pnl >= 0 else "❌"
    stake = pm_tg_stake(pos) or f"💵 ${spent:.2f}"
    hour = pos.get("entry_hour_tr")
    slot = f"{int(hour):02d}:00" if hour is not None else "—"
    bal = pm_get_balance()
    bal_line = f"💰 PM Bakiye: ${bal:.2f}" if bal >= 0 else "💰 PM Bakiye: ?"
    sep = "━" * 26
    tg_send_pm_live(
        f"{sep}\n"
        f"⏹ <b>{label} — {slot} Erken Kapatma</b>  🔴 GERÇEK PM\n"
        f"{icon} <b>{name}</b>  {pred}  giriş:{entry:.2f}\n"
        f"   {stake}  alınan ${received:.2f}  net {'+' if pnl >= 0 else ''}{pnl:.2f}$\n"
        f"{bal_line}\n"
        f"{sep}",
        label=label,
    )


_PM_CLOSE_ANALYSES = _HOURLY_PM_ANALYSES | _15M_PM_ANALYSES


def _pm_close_pnl_delta(pos: dict, sell_result: dict) -> float:
    """Erken kapatma net PnL — zincirde zaten kapalıysa tahmin etme."""
    if sell_result.get("worthless"):
        spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
        return round(-spent, 2)
    if sell_result.get("reconciled"):
        return 0.0
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    received = float(sell_result.get("received") or 0)
    return round(received - spent, 2)


def _record_dashboard_close(analiz: str, pos: dict, sell_result: dict) -> None:
    """Dashboard erken PM satışını history'ye yaz."""
    if analiz not in _PM_CLOSE_ANALYSES:
        return
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    sym = pos.get("symbol", "")
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    received = float(sell_result.get("received") or 0)
    reconciled = bool(sell_result.get("reconciled"))
    worthless = bool(sell_result.get("worthless"))
    if worthless:
        pnl = round(-spent, 2)
        win = False
    elif reconciled:
        pnl = 0.0
        win = None
    else:
        pnl = round(received - spent, 2)
        win = pnl > 0
    pred = pos.get("predicted_dir", "") or pos.get("pm_token_dir", "")
    entry = float(pos.get("entry_price") or 0)

    try:
        current = get_price(sym) if sym else entry
    except Exception:
        current = entry

    actual = "UP" if current >= entry else "DOWN"
    history = _load_trader_history(analiz)
    row = {
        "symbol": sym,
        "predicted_dir": pred,
        "actual_dir": actual,
        "binance_actual": actual,
        "win": win,
        "pm_win": None,
        "settle_source": "worthless" if worthless else ("reconciled" if reconciled else "manual_sell"),
        "entry_price": entry,
        "exit_price": current,
        "entry_time_tr": pos.get("entry_time_tr"),
        "entry_hour_tr": pos.get("entry_hour_tr"),
        "entry_dow": pos.get("entry_dow"),
        "entry_is_weekend": pos.get("entry_is_weekend"),
        "score": pos.get("score", 0),
        "amount": pos.get("amount"),
        "pm_spent": pos.get("pm_spent"),
        "pm_size": pos.get("pm_size"),
        "pm_entry_price": pos.get("pm_entry_price"),
        "pm_order_id": pos.get("pm_order_id"),
        "pm_slug": pos.get("pm_slug"),
        "pm_token_dir": pos.get("pm_token_dir"),
        "exit_time_tr": now_tr.isoformat(),
        "pnl": pnl,
        "pm_live": True,
    }
    if analiz in _15M_PM_ANALYSES:
        row["ts_period"] = pos.get("ts_period") or pos.get("ts_5m")
        row["entry_period_min"] = pos.get("entry_period_min")
    history.append(row)
    _save_trader_history(analiz, history)


# ── İşlem masası (manuel PM açılış) ─────────────────────────────
_TRADE_DESK_5M_SYMS = ("BTCUSDT", "SOLUSDT")
_TRADE_DESK_15M_SYMS = ("BTCUSDT", "SOLUSDT")
_TRADE_DESK_1H_SYMS = ("BTCUSDT", "SOLUSDT")


def _trade_desk_short_syms(timeframe: str) -> tuple[str, ...]:
    if timeframe == "1h":
        return _TRADE_DESK_1H_SYMS
    return _TRADE_DESK_15M_SYMS


def _trade_desk_spot(symbol: str, timeframe: str) -> dict:
    """Slot başlangıç (price to beat) + Binance anlık fiyat."""
    name = symbol.replace("USDT", "")
    dec = 1 if name == "BTC" else 2
    live = ref = None
    slot_label = ""
    try:
        live = get_price(symbol)
    except Exception:
        pass
    try:
        if timeframe == "5m":
            _, slot_label = _trade_desk_period_5m()
        elif timeframe == "15m":
            _, slot_label = _trade_desk_period_15m()
        else:
            h = datetime.now(_TZ_TR).hour
            slot_label = f"{h:02d}:00-{(h + 1) % 24:02d}:00"
        ref = _trade_desk_slot_ref(symbol, timeframe)
    except Exception:
        pass
    delta = (live - ref) if ref is not None and live is not None else None
    return {
        "timeframe": timeframe,
        "slot_label": slot_label,
        "ref_price": round(ref, dec) if ref is not None else None,
        "live_price": round(live, dec) if live is not None else None,
        "delta": round(delta, dec) if delta is not None else None,
        "dec": dec,
    }


def _trade_desk_period_5m() -> tuple[int, str]:
    import time
    ts = int(time.time()) - (int(time.time()) % 300)
    lbl = datetime.fromtimestamp(ts, _TZ_TR).strftime("%H:%M")
    end = datetime.fromtimestamp(ts + 300, _TZ_TR).strftime("%H:%M")
    return ts, f"{lbl}-{end}"


def _trade_desk_period_15m() -> tuple[int, str]:
    import time
    ts = int(time.time()) - (int(time.time()) % 900)
    lbl = datetime.fromtimestamp(ts, _TZ_TR).strftime("%H:%M")
    end = datetime.fromtimestamp(ts + 900, _TZ_TR).strftime("%H:%M")
    return ts, f"{lbl}-{end}"


def _trade_desk_quote_5m(symbol: str) -> dict | None:
    sys.path.insert(0, _DIR_POLY)
    import poly_trader_5m_common as pm_common
    ts, slot = _trade_desk_period_5m()
    m = pm_common._pm_find_5m_market(ts, symbol)
    if not m:
        return None
    spot = _trade_desk_spot(symbol, "5m")
    return {
        "timeframe": "5m",
        "symbol": symbol,
        "name": symbol.replace("USDT", ""),
        "ts_period": ts,
        "slot": slot,
        "slug": m.get("slug", ""),
        "title": m.get("title", ""),
        "closed": bool(m.get("closed")),
        "up": round(float(m.get("up_price", 0.5)), 3),
        "down": round(float(m.get("down_price", 0.5)), 3),
        **spot,
    }


def _trade_desk_quote_15m(symbol: str) -> dict | None:
    sys.path.insert(0, _DIR_POLY)
    import poly_trader_5m_common as pm_common
    ts, slot = _trade_desk_period_15m()
    m = pm_common._pm_find_15m_market(ts, symbol)
    if not m:
        return None
    spot = _trade_desk_spot(symbol, "15m")
    return {
        "timeframe": "15m",
        "symbol": symbol,
        "name": symbol.replace("USDT", ""),
        "ts_period": ts,
        "slot": slot,
        "slug": m.get("slug", ""),
        "title": m.get("title", ""),
        "closed": bool(m.get("closed")),
        "up": round(float(m.get("up_price", 0.5)), 3),
        "down": round(float(m.get("down_price", 0.5)), 3),
        **spot,
    }


def _trade_desk_quote_1h(symbol: str) -> dict | None:
    from datetime import timedelta
    sys.path.insert(0, _DIR_POLY)
    from pm_trader_helpers import pm_find_market
    now = datetime.now(timezone.utc)
    et_hour = (now - timedelta(hours=4)).hour
    m = pm_find_market(symbol, et_hour, now)
    if not m:
        return None
    op = m.get("outcome_prices") or []
    up = float(op[0]) if len(op) >= 2 else 0.5
    down = float(op[1]) if len(op) >= 2 else 0.5
    h = datetime.now(_TZ_TR).hour
    hour_start = datetime.now(_TZ_TR).replace(minute=0, second=0, microsecond=0)
    spot = _trade_desk_spot(symbol, "1h")
    return {
        "timeframe": "1h",
        "symbol": symbol,
        "name": symbol.replace("USDT", ""),
        "ts_period": int(hour_start.timestamp()),
        "slot": f"{h:02d}:00-{(h + 1) % 24:02d}:00",
        "slug": m.get("slug", ""),
        "title": m.get("title", ""),
        "closed": bool(m.get("closed")),
        "up": round(up, 3),
        "down": round(down, 3),
        **spot,
    }


def _pm_buy_plan(amount: float, price: float) -> dict:
    """PM min 5 pay — gerçek harcama tahmini (pm_place_order ile aynı mantık)."""
    from decimal import Decimal, ROUND_DOWN
    sys.path.insert(0, _DIR_POLY)
    from pm_trader_helpers import pm_fit_buy
    price = max(0.02, min(0.98, round(float(price), 2)))
    raw_sz = float(Decimal(str(amount / price)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
    size, price = pm_fit_buy(max(5.0, raw_sz), price)
    spent = round(size * price, 2)
    min_size, min_p = pm_fit_buy(5.0, price)
    min_amount = round(min_size * min_p, 2)
    return {
        "price": price,
        "size": size,
        "spent": spent,
        "profit": round(size - spent, 2),
        "min_amount": min_amount,
        "allowed": amount + 0.01 >= min_amount,
    }


def _trade_desk_resolve_pm(timeframe: str, symbol: str) -> tuple[dict | None, int | None]:
    ts_period = None
    sys.path.insert(0, _DIR_POLY)
    if timeframe == "5m":
        import poly_trader_5m_common as pm_common
        ts_period, _ = _trade_desk_period_5m()
        pm = pm_common._pm_find_5m_market(ts_period, symbol)
    elif timeframe == "15m":
        import poly_trader_5m_common as pm_common
        ts_period, _ = _trade_desk_period_15m()
        pm = pm_common._pm_find_15m_market(ts_period, symbol)
    else:
        from datetime import timedelta
        from pm_trader_helpers import pm_find_market
        now = datetime.now(timezone.utc)
        et_hour = (now - timedelta(hours=4)).hour
        pm = pm_find_market(symbol, et_hour, now)
    return pm, ts_period


def _trade_desk_live_price(token_id: str, amount: float, fallback: float) -> float:
    try:
        sys.path.insert(0, _DIR_POLY)
        from pm_trader_helpers import pm_get_client
        from py_clob_client_v2 import OrderType
        client = pm_get_client()
        price = float(client.calculate_market_price(token_id, "BUY", amount, OrderType.FAK))
        return max(0.02, min(0.98, round(price, 2)))
    except Exception:
        return max(0.02, min(0.98, round(float(fallback), 2)))


def _trade_desk_open(timeframe: str, symbol: str, direction: str, amount: float) -> dict:
    symbol = symbol.upper()
    direction = direction.upper()
    if timeframe not in ("5m", "15m", "1h"):
        return {"ok": False, "error": "timeframe 5m, 15m veya 1h olmalı"}
    if direction not in ("UP", "DOWN"):
        return {"ok": False, "error": "yön UP veya DOWN olmalı"}
    if symbol not in _trade_desk_short_syms(timeframe):
        return {"ok": False, "error": f"{symbol} bu timeframe için desteklenmiyor"}
    if amount < 1 or amount > 500:
        return {"ok": False, "error": "tutar $1–500 arası olmalı"}

    sys.path.insert(0, _DIR_POLY)
    from pm_trader_helpers import pm_place_order

    pm, ts_period = _trade_desk_resolve_pm(timeframe, symbol)
    if not pm or pm.get("closed"):
        return {"ok": False, "error": "PM market bulunamadı veya kapalı"}

    quote_p = float(pm["up_price"] if direction == "UP" else pm["down_price"])
    token_id = pm["up_token"] if direction == "UP" else pm["down_token"]
    live_p = _trade_desk_live_price(token_id, amount, quote_p)
    plan = _pm_buy_plan(amount, live_p)
    if not plan["allowed"]:
        return {
            "ok": False,
            "error": (
                f"Polymarket min 5 pay — @{plan['price']:.2f} fiyatta en az ${plan['min_amount']:.2f} gerekir "
                f"(${amount:.2f} ile ~${plan['spent']:.2f} açılır)"
            ),
            "plan": plan,
        }

    order = pm_place_order(
        token_id, amount, pm.get("tick_size", "0.01"), pm.get("neg_risk", False),
        label="MANUEL PM",
    )
    if not order:
        return {"ok": False, "error": "PM emri başarısız"}

    try:
        entry_p = _trade_desk_slot_ref(symbol, timeframe, ts_period)
        if entry_p is None:
            entry_p = get_price(symbol)
    except Exception:
        entry_p = 0.0
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    pos = {
        "symbol": symbol,
        "predicted_dir": direction,
        "entry_price": entry_p,
        "amount": order["spent"],
        "pm_spent": order["spent"],
        "to_win": order["size"],
        "token_price": order.get("price"),
        "entry_time_tr": now_tr.isoformat(),
        "entry_dow": now_tr.weekday(),
        "entry_hour_tr": now_tr.hour,
        "entry_is_weekend": now_tr.weekday() >= 5,
        "timeframe": timeframe,
        "pm_slug": pm.get("slug", ""),
        "pm_token_dir": direction,
        "pm_token_id": token_id,
        "pm_size": order["size"],
        "pm_entry_price": order.get("price"),
        "pm_order_id": order.get("order_id", ""),
        "manual": True,
    }
    if timeframe == "5m":
        pos["ts_period"] = ts_period
        pos["ts_5m"] = ts_period
        pos["entry_period_min"] = 5
    elif timeframe == "15m":
        pos["ts_period"] = ts_period
        pos["ts_5m"] = ts_period
        pos["entry_period_min"] = 15

    state = load_state("manual")
    state.setdefault("open_positions", [])
    pos_id = _manual_pos_id(pos)
    state["open_positions"] = [
        p for p in state["open_positions"]
        if _manual_pos_id(p) != pos_id
    ]
    state["open_positions"].append(pos)
    save_state("manual", state)
    sys.path.insert(0, _DIR_POLY)
    try:
        from pm_manual_sync import register_manual_order
        register_manual_order(pos)
    except Exception:
        pass
    spent = order["spent"]
    requested = amount
    note = f" (girdiğin ${requested:.2f})" if abs(spent - requested) > 0.02 else ""
    return {
        "ok": True,
        "position": pos,
        "message": f"{pos['symbol'].replace('USDT', '')} {'YÜKSELİR' if direction == 'UP' else 'DÜŞER'} "
                   f"${spent:.2f} @{order.get('price', 0):.2f}{note}",
    }


def _clip_chart_overlay(overlay: dict | None, t0: int, t1: int) -> dict | None:
    """Overlay serilerini mum penceresine kırp (fitContent genişlemesini önler)."""
    if not overlay or not overlay.get("ok"):
        return overlay
    ov = overlay.get("overlays") or {}

    def _clip(series):
        if not series:
            return []
        return [p for p in series if t0 <= int(p["time"]) <= t1]

    out = dict(overlay)
    out["overlays"] = {
        **ov,
        "ema_fast": _clip(ov.get("ema_fast")),
        "ema_slow": _clip(ov.get("ema_slow")),
        "composite": _clip(ov.get("composite")),
        "trend": _clip(ov.get("trend")),
    }
    sigs = overlay.get("signals") or []
    out["signals"] = [s for s in sigs if t0 <= int(s["time"]) <= t1]
    return out


def _snap_overlay_signals_to_chart(candles: list[dict], signals: list[dict]) -> list[dict]:
    """110 motor oklarını mum zamanına hizala (1m grafikte 15m sinyaller)."""
    if not candles or not signals:
        return signals or []
    times = [int(c["time"]) for c in candles]
    time_set = set(times)

    def _snap(t: int) -> int | None:
        best = min(times, key=lambda x: abs(x - t))
        return best if abs(best - t) <= 450 else None

    out: list[dict] = []
    seen: set[tuple] = set()
    for s in signals:
        raw_t = int(s["time"])
        st = raw_t if raw_t in time_set else _snap(raw_t)
        if st is None:
            continue
        key = (st, s.get("dir"))
        if key in seen:
            continue
        seen.add(key)
        out.append({**s, "time": st})
    return out


def _snap_hourly_signals_to_chart(
    candles: list[dict],
    signals: list[dict],
    hourly_current: dict,
    window_start: int | None,
) -> list[dict]:
    """Saatlik A1/A3/A8 oklarını mum zamanına hizala (LightweightCharts tam eşleşme ister)."""
    if not candles:
        return []
    times = [int(c["time"]) for c in candles]
    time_set = set(times)

    def _snap(t: int) -> int | None:
        best = min(times, key=lambda x: abs(x - t))
        return best if abs(best - t) <= 2700 else None

    out: list[dict] = []
    seen: set[tuple] = set()
    for s in signals:
        raw_t = int(s["time"])
        st = raw_t if raw_t in time_set else _snap(raw_t)
        if st is None:
            continue
        key = (st, s.get("tag"), s.get("dir"))
        if key in seen:
            continue
        seen.add(key)
        out.append({**s, "time": st})

    if window_start and window_start in time_set and hourly_current:
        for tag, hk in (("A1", "a1"), ("A3", "a3"), ("A8", "a8"), ("ALFA", "alfa")):
            cur = hourly_current.get(hk)
            if not cur or not cur.get("dir"):
                continue
            key = (window_start, tag, cur["dir"])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "time": window_start,
                "dir": cur["dir"],
                "tag": tag,
                "live": True,
            })
    return out


def _snap_fifteen_signals_to_chart(
    candles: list[dict],
    signals: list[dict],
    fifteen_current: dict,
    window_start: int | None,
) -> list[dict]:
    """15m 112/113 oklarını mum zamanına hizala."""
    if not candles:
        return []
    times = [int(c["time"]) for c in candles]
    time_set = set(times)

    def _snap(t: int) -> int | None:
        best = min(times, key=lambda x: abs(x - t))
        return best if abs(best - t) <= 900 else None

    out: list[dict] = []
    seen: set[tuple] = set()
    for s in signals:
        raw_t = int(s["time"])
        st = raw_t if raw_t in time_set else _snap(raw_t)
        if st is None:
            continue
        key = (st, s.get("tag"), s.get("dir"))
        if key in seen:
            continue
        seen.add(key)
        out.append({**s, "time": st})

    if window_start and window_start in time_set and fifteen_current:
        for tag, hk in (("112", "a112"), ("113", "a113")):
            cur = fifteen_current.get(hk)
            if not cur or not cur.get("dir"):
                continue
            key = (window_start, tag, cur["dir"])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "time": window_start,
                "dir": cur["dir"],
                "tag": tag,
                "live": True,
            })
    return out


def _trade_desk_chart(
    symbol: str,
    timeframe: str,
    *,
    algo: str | None = None,
    ema_fast: int = 9,
    ema_slow: int = 21,
    gate: float = 15.0,
    price_tf: str = "1m",
    candle_limit: int | None = None,
) -> dict:
    """İşlemler grafiği — mumlar + slot ref + opsiyonel 110 algo overlay."""
    import time as _time
    name = symbol.replace("USDT", "")
    dec = 1 if name == "BTC" else 2
    spot = _trade_desk_spot(symbol, timeframe)
    if timeframe == "5m":
        ts_period, slot_label = _trade_desk_period_5m()
        window_secs = 300
        limit_1m = 36
        limit_5m = 12
        limit_15m = 24
        limit_1h = 12
    elif timeframe == "15m":
        ts_period, slot_label = _trade_desk_period_15m()
        window_secs = 900
        limit_1m = 60
        limit_5m = 24
        limit_15m = 60
        limit_1h = 24
    else:
        hour_start = datetime.now(_TZ_TR).replace(minute=0, second=0, microsecond=0)
        ts_period = int(hour_start.timestamp())
        slot_label = spot.get("slot_label") or hour_start.strftime("%H:%M")
        window_secs = 3600
        limit_1m = 90
        limit_5m = 24
        limit_15m = 48
        limit_1h = 48
    algo_key = (algo or "off").lower()
    price_tf = price_tf if price_tf in ("1m", "5m", "15m", "1h") else "1m"
    _px_limits = {"1m": limit_1m, "5m": limit_5m, "15m": limit_15m, "1h": limit_1h}
    if candle_limit is not None:
        cap = max(10, min(500, int(candle_limit)))
        _px_limits[price_tf] = cap
    px_limit = _px_limits[price_tf]
    now_f = _time.time()
    cache_key = (
        symbol, timeframe, ts_period, int(now_f) // 60,
        algo_key, ema_fast, ema_slow, round(float(gate), 1), price_tf,
        px_limit,
    )
    cached = _trade_chart_cache.get(cache_key)
    if cached and now_f - cached[0] < _TRADE_CHART_CACHE_TTL:
        out = dict(cached[1])
        out["live_price"] = spot.get("live_price")
        out["ref_price"] = spot.get("ref_price")
        out["now"] = int(now_f)
        if out.get("candles") and spot.get("live_price") is not None:
            last = dict(out["candles"][-1])
            lp = round(float(spot["live_price"]), dec)
            last["close"] = lp
            last["high"] = max(last["high"], lp)
            last["low"] = min(last["low"], lp)
            out["candles"] = out["candles"][:-1] + [last]
        return out
    candle_interval = price_tf
    candle_limit = px_limit
    raw = get_klines(symbol, candle_interval, limit=candle_limit)
    candles = [
        {
            "time": k["t"] // 1000,
            "open": round(k["o"], dec),
            "high": round(k["h"], dec),
            "low": round(k["l"], dec),
            "close": round(k["c"], dec),
            "volume": round(k["v"], 2),
        }
        for k in raw
    ]
    if candles:
        t0, t1 = candles[0]["time"], candles[-1]["time"]
    else:
        t0 = t1 = 0
    now_sec = int(now_f)
    result = {
        "symbol": symbol,
        "name": name,
        "timeframe": timeframe,
        "price_tf": price_tf,
        "slot_label": slot_label,
        "ts_period": ts_period,
        "window_start": ts_period,
        "window_end": ts_period + window_secs,
        "ref_price": spot.get("ref_price"),
        "live_price": spot.get("live_price"),
        "dec": dec,
        "candles": candles,
        "now": now_sec,
        "algo_overlay": None,
        "hourly_signals": [],
        "hourly_current": {},
        "fifteen_signals": [],
        "fifteen_current": {},
    }
    if algo_key not in ("", "off", "none", "0"):
        try:
            sys.path.insert(0, _DIR_POLY)
            from chart_algo_overlay import compute_algo_overlay
            result["algo_overlay"] = compute_algo_overlay(
                symbol, algo=algo_key, ema_fast=ema_fast, ema_slow=ema_slow, gate=gate,
            )
            if candles:
                clipped = _clip_chart_overlay(result["algo_overlay"], t0, t1)
                if clipped and clipped.get("signals"):
                    clipped = dict(clipped)
                    clipped["signals"] = _snap_overlay_signals_to_chart(candles, clipped["signals"])
                result["algo_overlay"] = clipped
        except Exception as e:
            result["algo_overlay"] = {"ok": False, "error": str(e), "algo": algo_key}
    if candles:
        t0, t1 = candles[0]["time"], candles[-1]["time"]
        try:
            from chart_hourly_signals import compute_hourly_chart_signals
            hs = compute_hourly_chart_signals(symbol, t0, t1)
            if hs.get("ok"):
                hc = hs.get("current") or {}
                if timeframe == "1h":
                    try:
                        from alfa_signal import chart_current_from_hourly
                        hc = {**hc, "alfa": chart_current_from_hourly(hc, symbol)}
                    except Exception:
                        pass
                snapped = _snap_hourly_signals_to_chart(
                    candles,
                    hs.get("signals") or [],
                    hc,
                    ts_period,
                )
                result["hourly_signals"] = snapped
                result["hourly_current"] = hc
                try:
                    from pm_balance_guard import get_pm_system_control
                    result.update({
                        k: get_pm_system_control()[k]
                        for k in ("a3a8_signal_strict", "a3a8_signal_mode", "a3a8_signal_mode_label")
                        if k in get_pm_system_control()
                    })
                except Exception:
                    pass
            else:
                result["hourly_signals"] = []
                result["hourly_current"] = {}
        except Exception:
            result["hourly_signals"] = []
            result["hourly_current"] = {}
    if candles and timeframe == "15m":
        t0, t1 = candles[0]["time"], candles[-1]["time"]
        try:
            from chart_15m_a3a8_signals import compute_15m_chart_signals
            fs = compute_15m_chart_signals(symbol, t0, t1)
            if fs.get("ok"):
                fc = fs.get("current") or {}
                snapped = _snap_fifteen_signals_to_chart(
                    candles,
                    fs.get("signals") or [],
                    fc,
                    ts_period,
                )
                result["fifteen_signals"] = snapped
                result["fifteen_current"] = fc
            else:
                result["fifteen_signals"] = []
                result["fifteen_current"] = {}
        except Exception:
            result["fifteen_signals"] = []
            result["fifteen_current"] = {}
    _trade_chart_cache[cache_key] = (now_f, result)
    if len(_trade_chart_cache) > 48:
        cutoff = now_f - 120
        for k in list(_trade_chart_cache):
            if _trade_chart_cache[k][0] < cutoff:
                del _trade_chart_cache[k]
    return result


_ISLEMLER_NOCACHE = {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}


def _json_nocache(data, status=200):
    resp = jsonify(data)
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/poly/api/trade-desk/spot")
def api_trade_desk_spot():
    if _auth_required():
        return jsonify({"error": "unauthorized"}), 401
    tf = str(request.args.get("timeframe", "15m"))
    sym = str(request.args.get("symbol", "SOLUSDT")).upper()
    return jsonify(_trade_desk_spot(sym, tf))


@app.route("/poly/api/trade-desk/chart")
def api_trade_desk_chart():
    if _auth_required():
        return jsonify({"error": "unauthorized"}), 401
    tf = str(request.args.get("timeframe", "15m"))
    if tf not in ("5m", "15m", "1h"):
        return jsonify({"error": "timeframe 5m, 15m veya 1h olmalı"}), 400
    sym = str(request.args.get("symbol", "SOLUSDT")).upper()
    allowed = _trade_desk_short_syms(tf)
    if sym not in allowed:
        return jsonify({"error": "desteklenmeyen sembol"}), 400
    algo = str(request.args.get("algo", "110")).strip().lower()
    price_tf = str(request.args.get("price_tf", "1m")).strip().lower()
    try:
        ema_fast = int(request.args.get("ema_fast", 9))
        ema_slow = int(request.args.get("ema_slow", 21))
        gate = float(request.args.get("gate", 15))
        candle_limit = request.args.get("limit")
        candle_limit = int(candle_limit) if candle_limit not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "geçersiz algo parametresi"}), 400
    return _json_nocache(_trade_desk_chart(
        sym, tf, algo=algo, ema_fast=ema_fast, ema_slow=ema_slow, gate=gate, price_tf=price_tf,
        candle_limit=candle_limit,
    ))


@app.route("/poly/api/trade-desk/estimate", methods=["POST"])
def api_trade_desk_estimate():
    if _auth_required():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "geçersiz tutar"}), 400
    timeframe = str(body.get("timeframe", "15m"))
    symbol = str(body.get("symbol", "SOLUSDT")).upper()
    direction = str(body.get("direction", "UP")).upper()
    if amount < 0.01:
        return jsonify({"ok": True, "plan": None})
    pm, _ = _trade_desk_resolve_pm(timeframe, symbol)
    if not pm:
        return jsonify({"ok": False, "error": "market yok"}), 400
    quote_p = float(pm["up_price"] if direction == "UP" else pm["down_price"])
    token_id = pm["up_token"] if direction == "UP" else pm["down_token"]
    live_p = _trade_desk_live_price(token_id, max(amount, 1.0), quote_p)
    plan = _pm_buy_plan(amount, live_p)
    return jsonify({"ok": True, "plan": plan})


@app.route("/poly/api/trade-desk")
def api_trade_desk():
    if _auth_required():
        return jsonify({"error": "unauthorized"}), 401
    q5 = [_trade_desk_quote_5m(s) for s in _TRADE_DESK_5M_SYMS]
    q15 = [_trade_desk_quote_15m(s) for s in _TRADE_DESK_15M_SYMS]
    q1h = [_trade_desk_quote_1h(s) for s in _TRADE_DESK_1H_SYMS]
    manual = load_state("manual")
    open_pos = []
    for p in manual.get("open_positions", []):
        if not _position_visible("manual", p):
            continue
        tf = _manual_timeframe(p)
        open_pos.append({
            "symbol": p.get("symbol", "").replace("USDT", ""),
            "symbol_full": p.get("symbol", ""),
            "dir": p.get("predicted_dir", ""),
            "dir_tr": "YÜKSELİR" if p.get("predicted_dir") == "UP" else "DÜŞER",
            "timeframe": tf,
            "slot": _position_slot_range(p, "manual"),
            "spent": round(float(p.get("pm_spent") or p.get("amount") or 0), 2),
            "size": p.get("pm_size"),
            "entry_time": (p.get("entry_time_tr") or "")[:16].replace("T", " "),
            "order_id": _manual_pos_id(p),
        })
    return jsonify({
        "cash": round(get_pm_balance(), 2),
        "quotes_5m": [q for q in q5 if q],
        "quotes_15m": [q for q in q15 if q],
        "quotes_1h": [q for q in q1h if q],
        "open_positions": open_pos,
    })


@app.route("/poly/api/trade-desk/open", methods=["POST"])
def api_trade_desk_open():
    if _auth_required():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "geçersiz tutar"}), 400
    result = _trade_desk_open(
        str(body.get("timeframe", "15m")),
        str(body.get("symbol", "SOLUSDT")),
        str(body.get("direction", "UP")),
        amount,
    )
    code = 200 if result.get("ok") else 400
    return jsonify(result), code


@app.route("/poly/api/trade-desk/sync", methods=["POST"])
def api_trade_desk_sync():
    if _auth_required():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    sys.path.insert(0, _DIR_POLY)
    try:
        from pm_manual_sync import sync_manual_open_positions
        result = sync_manual_open_positions()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify(result)


@app.route("/poly/api/close/<analiz>/<symbol>", methods=["POST"])
def api_close(analiz, symbol):
    if _auth_required(): return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        state  = load_state(analiz)
        symbol = symbol.upper()
        tf_filter = request.args.get("timeframe")
        order_id = request.args.get("order_id") or request.args.get("pos_id")
        req_sym = symbol.upper()
        if not req_sym.endswith("USDT"):
            req_sym = req_sym + "USDT"
        def _match(p):
            if analiz == "manual":
                return _manual_pos_match(
                    p, req_sym, timeframe=tf_filter, order_id=order_id,
                )
            if p.get("symbol", "").upper() != req_sym:
                return False
            return True
        matches = [p for p in state.get("open_positions", []) if _match(p)]
        if analiz == "manual" and not order_id and len(matches) > 1:
            return jsonify({
                "ok": False,
                "error": "Birden fazla manuel pozisyon var — order_id gerekli",
            }), 400
        pos = matches[0] if matches else None
        if not pos:
            return jsonify({"ok": False, "error": "pozisyon bulunamadı"}), 404

        token_id = pos.get("pm_token_id")
        pm_size  = pos.get("pm_size", 0)

        if not token_id or not pm_size:
            return jsonify({"ok": False, "error": f"token_id veya pm_size eksik ({token_id=}, {pm_size=})"}), 400

        sell_result = _pm_sell_position_retry(
            token_id, pm_size,
            pm_slug=pos.get("pm_slug", ""),
            token_dir=pos.get("pm_token_dir") or pos.get("predicted_dir", ""),
        )

        if not sell_result.get("ok"):
            sell_result = _pm_try_worthless_reconcile(pos) or sell_result

        if not sell_result.get("ok"):
            return jsonify({
                "ok": False,
                "error": _short_pm_error(sell_result.get("error", "PM satış başarısız")),
                "sell": sell_result,
                "symbol": symbol,
            }), 502

        state["open_positions"] = [
            p for p in state["open_positions"] if not _match(p)
        ]
        if analiz in _PM_CLOSE_ANALYSES:
            delta = _pm_close_pnl_delta(pos, sell_result)
            if delta:
                state["total_pnl"] = round(state.get("total_pnl", 0.0) + delta, 2)
        save_state(analiz, state)
        _record_dashboard_close(analiz, pos, sell_result)
        _tg_notify_pm_early_close(analiz, pos, sell_result)

        return jsonify({
            "ok": True,
            "sell": sell_result,
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
      <div class="page-sub">39 algoritma — BTC / ETH / SOL — 1 saatlik (konsensüs: 37 oy, #13–14 hariç)</div>
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
      <div class="card-signals" id="sigs-13"><div class="sig-na sig-pill">SOL —</div></div>
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
      <div class="card-signals" id="sigs-21"><div class="sig-loading sig-pill">BTC</div><div class="sig-loading sig-pill">SOL</div></div>
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
// Sembol bazlı sıralamada gösterilmez (basit algo #22 ≠ gerçek 1. Analiz trader)
const SYM_RANK_EXCLUDE = new Set(["22"]);

function renderSymRanking(acc, sym){
  const el = document.getElementById("sym-rank-list");
  if(!el) return;
  const entries = Object.entries(acc)
    .filter(([k,v]) => !SYM_RANK_EXCLUDE.has(k) && v.by_sym && v.by_sym[sym] && v.by_sym[sym].total > 0)
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

function renderTopSymAlgos(acc){
  const el = document.getElementById("top-sym-algos");
  if(!el) return;
  const SYMS = ["BTC","ETH","SOL"];
  const MIN_TRADES = 1;
  const items = [];

  for(const sym of SYMS){
    let best = null, bestWr = -1, bestStat = "", bestSym = false;

    for(const [num, data] of Object.entries(acc)){
      if(SYM_RANK_EXCLUDE.has(num)) continue;
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
  <div class="page-sub">A1 Live — işlem miktarları anlık güncellenir, bir sonraki saatte devreye girer</div>

  <div class="settings-card">
    <h3>İşlem Miktarları</h3>

    <div class="setting-row">
      <div class="setting-left">
        <div class="setting-label">A9 + A1 Live Aynı Yön</div>
        <div class="setting-desc">İki sistem hemfikir olduğunda açılan işlem miktarı</div>
      </div>
      <div class="setting-right">
        <span class="setting-unit">$</span>
        <input class="setting-input" id="amount_agree" type="number" step="0.5" min="1" max="100">
      </div>
    </div>

    <div class="setting-row">
      <div class="setting-left">
        <div class="setting-label">A9 Sessiz — A1 Live Var</div>
        <div class="setting-desc">Sadece A1 Live sinyal ürettiğinde açılan işlem miktarı</div>
      </div>
      <div class="setting-right">
        <span class="setting-unit">$</span>
        <input class="setting-input" id="amount_a5_only" type="number" step="0.5" min="1" max="100">
      </div>
    </div>

    <div class="setting-row">
      <div class="setting-left">
        <div class="setting-label">A9 Var — A1 Live Sessiz</div>
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
  <div class="page-sub" id="hm-subtitle">{{ harita_default_label }} — gün × saat kazanma oranı (tüm geçmiş)</div>

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
let _data = null, _sym = 'ALL', _analiz = '{{ harita_default_analiz }}';

function hmColor(wr,t){ if(!t)return'#1a1a1a'; if(wr>=70)return'#166534'; if(wr>=55)return'#14532d'; if(wr>=50)return'#365314'; if(wr>=40)return'#78350f'; return'#450a0a'; }
function hmTxt(wr,t){ if(!t)return'#333'; if(wr>=55)return'#4ade80'; if(wr>=50)return'#c8f135'; if(wr>=40)return'#fbbf24'; return'#f87171'; }

async function load() {
  try {
    const r = await fetch(`/poly/api/heatmap?sym=${_sym}&analiz=${_analiz}`);
    const d = await r.json();
    if (!d || !Array.isArray(d.cells)) {
      _data = [];
      renderSummary({total:0,wins:0,losses:0,wr:0,pnl:0,spent:0}, []);
      renderGrid([]);
      return;
    }
    _data = d.cells;
    renderSummary(d.summary || {total:0,wins:0,losses:0,wr:0,pnl:0,spent:0}, d.sym_breakdown || []);
    renderGrid(_data);
    const lbl = _ANALIZ_LABELS[_analiz] || _analiz;
    document.getElementById('hm-subtitle').textContent = `${lbl} — gün × saat kazanma oranı (${d.summary?.total || 0} işlem, ${d.cells.length} dolu hücre)`;
  } catch (e) {
    console.error('harita load', e);
    renderGrid([]);
  }
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
    _sym = allowed.length === 1 ? allowed[0] : 'ALL';
    document.querySelectorAll('.hm-filter').forEach(b => {
      const t = b.textContent.trim();
      b.classList.toggle('active', t === 'Tümü' ? _sym === 'ALL' : t === _sym);
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
  .pm-system-wrap { display:flex; flex-direction:column; gap:8px; margin-bottom:16px; }
  .pm-system-bar {
    display:flex; align-items:center; justify-content:space-between; gap:12px;
    padding:12px 14px; border-radius:14px;
    background:#132013; border:1px solid #2a3a2a;
  }
  .pm-system-bar.paused { background:#2a1414; border-color:#5a2a2a; }
  .pm-system-status { font-size:13px; font-weight:600; color:#9ae66e; line-height:1.35; }
  .pm-system-bar.paused .pm-system-status { color:#fca5a5; }
  .pm-system-sub { font-size:11px; color:#666; margin-top:3px; font-weight:500; }
  .pm-system-btn {
    flex-shrink:0; border:none; border-radius:10px; padding:9px 14px;
    font-size:12px; font-weight:800; cursor:pointer; color:#0d0d0d;
    background:#c8f135; transition:opacity .15s; white-space:nowrap;
  }
  .pm-system-btn:hover { opacity:.9; }
  .pm-system-btn.paused { background:#f87171; color:#fff; }
  .pm-system-btn:disabled { opacity:.55; cursor:wait; }

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

  /* PM 1H kotasyon */
  .pm-hourly-wrap { margin-bottom:14px; }
  .pm-hourly-title { font-size:15px; font-weight:700; color:#fff; margin-bottom:10px; }
  .pm-hourly-row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .pm-hourly-row.single { grid-template-columns:1fr; max-width:320px; }
  .pm-hourly-card { background:#141414; border-radius:16px; padding:12px 14px; border:1px solid #1e1e1e; }
  .pm-hourly-head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; }
  .pm-hourly-sym { font-size:14px; font-weight:800; color:#fff; }
  .pm-hourly-et { font-size:10px; color:#666; font-weight:600; }
  .pm-hourly-prices { display:flex; gap:8px; }
  .pm-hourly-pill { flex:1; border-radius:10px; padding:8px 10px; text-align:center; }
  .pm-hourly-pill.up { background:#14291e; }
  .pm-hourly-pill.down { background:#291414; }
  .pm-hourly-lbl { font-size:9px; font-weight:700; letter-spacing:.4px; margin-bottom:2px; }
  .pm-hourly-pill.up .pm-hourly-lbl { color:#4ade80; }
  .pm-hourly-pill.down .pm-hourly-lbl { color:#f87171; }
  .pm-hourly-val { font-size:16px; font-weight:800; color:#fff; }
  .pm-hourly-bn { font-size:13px; font-weight:600; color:#aaa; margin-top:8px; display:flex; flex-wrap:wrap; gap:10px 14px; }
  .pm-hourly-bn span { white-space:nowrap; }
  .pm-hourly-bn .bn-lbl { color:#666; font-weight:500; }
  .pm-hourly-bn .bn-val { color:#e8e8e8; font-weight:700; }
  .pm-hourly-bn .pos-live { color:#c8f135; font-weight:800; }
  @media(max-width:700px){ .pm-hourly-row { grid-template-columns:1fr; width:100%; } }
  .mobile-recent-section { display:none; }
  .mobile-profit-wrap { display:none; }

  /* pm-kar-donut — overview (mobil widget burada; patch sidebar için ayrı enjekte eder) */
  .sidebar-profit { margin:10px 0 4px; padding:14px 10px 12px; background:#0f140f;
    border:1px solid #1a2218; border-radius:18px; box-sizing:border-box; }
  .sidebar-profit .sp-title { font-size:10px; color:#666; text-transform:uppercase; letter-spacing:.4px; margin-bottom:12px; }
  .sidebar-profit .sp-inner { display:flex; flex-direction:column; align-items:center; gap:14px; width:100%; }
  .sidebar-profit .sp-chart { position:relative; width:132px; height:132px; flex-shrink:0; }
  .sidebar-profit .sp-chart svg { width:132px; height:132px; display:block; }
  .sidebar-profit .sp-center { position:absolute; top:0; left:0; width:132px; height:132px; z-index:2;
    display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:none; }
  .sidebar-profit .sp-total { font-size:17px; font-weight:800; color:#fff; line-height:1.1; }
  .sidebar-profit .sp-sub { font-size:9px; color:#555; margin-top:3px; text-align:center; }
  .sidebar-profit .sp-legend { width:100%; flex-shrink:0; display:flex; justify-content:space-between; gap:6px; }
  .sidebar-profit .sp-leg-item { flex:1; min-width:0; display:flex; flex-direction:column; align-items:center; text-align:center; gap:2px; }
  .sidebar-profit .sp-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; margin-bottom:2px; }
  .sidebar-profit .sp-leg-lbl { font-size:10px; color:#888; line-height:1.2; font-weight:600; }
  .sidebar-profit .sp-leg-val { font-size:12px; font-weight:700; color:#ddd; line-height:1.2; }

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
  .pos-card { background:#141414; border-radius:18px; padding:18px; border:2px solid #333; }
  .pos-card.dir-up   { border-color:#4ade80; }
  .pos-card.dir-down { border-color:#f87171; }
  .pos-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
  .pos-name { font-size:20px; font-weight:800; color:#fff; }
  .pos-dir  { font-size:12px; font-weight:700; padding:4px 10px; border-radius:10px; }
  .pos-dir.up   { background:#14532d; color:#4ade80; }
  .pos-dir.down { background:#450a0a; color:#f87171; }
  .pos-price-row { display:flex; align-items:baseline; gap:8px; margin:2px 0 6px; }
  .pos-current { font-size:22px; font-weight:700; color:#fff; }
  .pos-win-icon { font-size:18px; font-weight:800; line-height:1; margin-left:2px; }
  .pos-win-icon.ok { color:#4ade80; }
  .pos-win-icon.bad { color:#f87171; }
  .pos-pct { font-size:13px; font-weight:600; }
  .pos-pct.pos { color:#4ade80; } .pos-pct.neg { color:#f87171; }
  .pos-entry { font-size:14px; font-weight:600; color:#e8e8e8; margin-bottom:6px; }
  .pos-entry-lbl { color:#888; font-weight:500; }
  .pos-slot { font-size:13px; font-weight:600; color:#aaa; margin-bottom:10px; }
  .pos-slot-lbl { color:#666; font-weight:500; }
  .pos-risk-row { font-size:13px; color:#888; font-weight:600; margin-top:8px; }
  .pos-close-row { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; margin-top:10px; padding:10px 12px; background:#0f120f; border-radius:10px; border:1px solid #1a2a1a; }
  .close-lbl { font-size:10px; color:#666; font-weight:700; text-transform:uppercase; letter-spacing:.3px; }
  .live-close-val { font-size:20px; font-weight:800; color:#fff; line-height:1; }
  .live-close-pnl { font-size:14px; font-weight:800; }
  .live-close-pnl.pos { color:#4ade80; }
  .live-close-pnl.neg { color:#f87171; }
  .close-token { font-size:11px; color:#555; margin-left:auto; font-weight:600; }
  .live-updated { font-size:10px; color:#444; width:100%; margin-top:2px; }
  .pos-win-row { font-size:14px; color:#4ade80; font-weight:600; margin-top:6px; }
  .pos-win-row .win-lbl { color:#888; font-weight:500; }
  .pos-analiz-tag { display:inline-block; background:#2a2a2a; color:#ccc; font-size:11px;
                    padding:2px 8px; border-radius:6px; margin-left:6px; font-weight:600; }
  .close-btn-wrap { display:flex; justify-content:flex-end; margin-top:12px; }
  .close-btn { background:#c8f135; border:none; color:#111; font-size:12px; font-weight:800;
               padding:8px 18px; border-radius:12px; cursor:pointer; white-space:nowrap; transition:.2s; }
  .close-btn:hover { background:#d4ff3a; }
  .close-btn:disabled { background:#333; color:#666; cursor:not-allowed; opacity:.65; }
  .close-btn:disabled:hover { background:#333; }
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
  .trade-item.pending { opacity:.92; }
  .trade-item.pending .trade-pnl { color:#fbbf24; font-size:12px; font-weight:700; }
  .trade-badge-pending { font-size:9px; color:#fbbf24; background:#2a2208; padding:1px 5px;
                         border-radius:4px; margin-left:4px; font-weight:700; vertical-align:1px; }

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
    .pm-hourly-row.single { max-width:none; width:100%; }
    .pm-hourly-wrap { width:100%; }
    .pm-hourly-card { width:100%; box-sizing:border-box; }
    .mobile-recent-section {
      display:block; background:#1f1f1f; border-radius:20px;
      padding:16px 14px; margin-top:8px;
    }
    .mobile-recent-section .trade-item:last-child { border-bottom:none; }
    .mobile-profit-wrap {
      display:block; margin:16px 0 8px;
    }
    .mobile-profit-wrap .sidebar-profit {
      margin:0; padding:18px 16px 16px; width:100%; box-sizing:border-box;
    }
    .mobile-profit-wrap .sidebar-profit .sp-chart,
    .mobile-profit-wrap .sidebar-profit .sp-chart svg,
    .mobile-profit-wrap .sidebar-profit .sp-center { width:150px; height:150px; }
    .mobile-profit-wrap .sidebar-profit .sp-total { font-size:20px; }
    .mobile-profit-wrap .sidebar-profit .sp-leg-val { font-size:13px; }
    .chart-wrap { margin-top:0; }
    .updated-bar { display:none; }
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
      <div class="pm-system-wrap">
        <div class="pm-system-bar" id="pm-system-bar-analiz5">
          <div>
            <div class="pm-system-status" id="pm-system-status-analiz5">✅ A1 Live açılış aktif</div>
            <div class="pm-system-sub" id="pm-system-sub-analiz5">Saatlik BTC+SOL · kapanış :02 · Cum 22:00 otomatik kapanır</div>
          </div>
          <button type="button" class="pm-system-btn" id="pm-system-btn-analiz5" onclick="togglePmSystem('analiz5')">Kapat</button>
        </div>
        <div class="pm-system-bar" id="pm-system-bar-analiz2">
          <div>
            <div class="pm-system-status" id="pm-system-status-analiz2">✅ A2 açılış aktif</div>
            <div class="pm-system-sub" id="pm-system-sub-analiz2">Saatlik SOL · kapanış :02 · Cum 22:00 otomatik kapanır</div>
          </div>
          <button type="button" class="pm-system-btn" id="pm-system-btn-analiz2" onclick="togglePmSystem('analiz2')">Kapat</button>
        </div>
        <div class="pm-system-bar" id="pm-system-bar-a3a8">
          <div>
            <div class="pm-system-status" id="pm-system-status-a3a8">A3/A8 sıkı sinyal</div>
            <div class="pm-system-sub" id="pm-system-sub-a3a8">Entry bias + EMA kesişim · grafik + canlı A3/A8/112/113</div>
          </div>
          <button type="button" class="pm-system-btn" id="pm-system-btn-a3a8" onclick="toggleA3A8SignalMode()">Gevşek</button>
        </div>
        <div class="pm-system-bar" id="pm-system-bar-210">
          <div>
            <div class="pm-system-status" id="pm-system-status-210">✅ 210 açılış aktif</div>
            <div class="pm-system-sub" id="pm-system-sub-210">15M yeni işlem açabilir · Cum 22:00 otomatik kapanır</div>
          </div>
          <button type="button" class="pm-system-btn" id="pm-system-btn-210" onclick="togglePmSystem('m15_210')">Kapat</button>
        </div>
      </div>
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

      <!-- PM 1H anlık kotasyon (açık pozisyon varsa) -->
      <div class="pm-hourly-wrap" id="pm-hourly-wrap" style="display:none">
        <div class="pm-hourly-title">Saatlik</div>
        <div class="pm-hourly-row" id="pm-hourly">
          <div class="pm-hourly-card"><div style="color:#555;font-size:12px">PM 1H yükleniyor…</div></div>
        </div>
      </div>

      <!-- PM 15m anlık kotasyon (açık pozisyon varsa) -->
      <div class="pm-hourly-wrap" id="pm-15m-wrap" style="display:none">
        <div class="pm-hourly-title">15 Dakikalık</div>
        <div class="pm-hourly-row" id="pm-15m">
          <div class="pm-hourly-card"><div style="color:#555;font-size:12px">PM 15m yükleniyor…</div></div>
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
      <div id="top3-analizler" class="top3-desktop-only" style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:20px">
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
        <div class="mobile-profit-wrap">
          <div class="sidebar-profit">
            <div class="sp-title">PM Kar</div>
            <div class="sp-inner">
              <div class="sp-chart">
                <svg id="sp-mob-donut" viewBox="0 0 132 132"></svg>
                <div class="sp-center">
                  <div class="sp-total" id="sp-mob-total">$—</div>
                  <div class="sp-sub">Toplam Kar</div>
                </div>
              </div>
              <div class="sp-legend" id="sp-mob-legend"></div>
            </div>
          </div>
        </div>
        <div class="mobile-recent-section">
          <div class="section-title" style="margin:16px 0 12px">Son İşlemler <span style="font-size:11px;color:#666;font-weight:600">Gerçek PM</span></div>
          <div id="recent-trades-mob"><div style="color:#666;font-size:13px">Yükleniyor...</div></div>
        </div>
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
  <div id="hm-subtitle-main" style="font-size:13px;color:#666;margin-bottom:20px">1. Analiz — gün × saat kazanma oranı (tüm geçmiş)</div>

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
    <div class="rp-title">Sembol Başarı Oranı <span id="sym-wr-label" style="font-size:11px;color:#999;font-weight:600;margin-left:4px"></span></div>
    <div id="sym-wr" style="display:flex;gap:8px">
      <div style="color:#666;font-size:13px">Yükleniyor...</div>
    </div>
  </div>

  <!-- En iyi gün/saat -->
  <div class="rp-section">
    <div class="rp-title">En Etkili Zaman <span id="top-slots-label" style="font-size:10px;color:#666;font-weight:600"></span></div>
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
    <div class="rp-title">Son İşlemler <span style="font-size:10px;color:#666;font-weight:600">Gerçek PM</span></div>
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
let _panelAnaliz = 'analiz1';

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

async function closePosition(analiz, symbol, btn, orderId) {
  if (btn.disabled || btn.classList.contains('loading')) return;
  btn.disabled = true;
  btn.classList.add('loading'); btn.textContent = 'Kapatılıyor...';
  try {
    let url = '/poly/api/close/' + encodeURIComponent(analiz) + '/' + encodeURIComponent(symbol);
    if (orderId) url += '?order_id=' + encodeURIComponent(orderId);
    const r = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
    });
    let d;
    try { d = await r.json(); } catch (_) {
      btn.textContent = '⚠️ Sunucu yanıtı okunamadı';
      btn.style.background = '#f87171'; btn.classList.remove('loading'); btn.disabled = false; return;
    }
    if (!d.ok) {
      btn.textContent = '⚠️ ' + (d.error || 'Satış başarısız');
      btn.style.background = '#f87171';
      btn.classList.remove('loading');
      btn.disabled = false;
      setTimeout(() => { btn.textContent = 'Pozisyonu Kapat'; btn.style.background = ''; }, 4000);
      return;
    }
    const s = d.sell || {};
    btn.style.background = '#4ade80';
    btn.classList.remove('loading');
    if (s.reconciled) {
      btn.textContent = s.worthless ? '✅ Kapatıldı · kayıp' : '✅ Zincirde zaten kapalı';
    } else {
      btn.textContent = '✅ Kapatıldı · $' + (s.received || '?');
    }
    setTimeout(refresh, 1500);
  } catch(e) {
    btn.textContent = '⚠️ ' + e.message;
    btn.style.background = '#f87171';
    btn.classList.remove('loading');
    btn.disabled = false;
    setTimeout(() => { btn.textContent = 'Pozisyonu Kapat'; btn.style.background = ''; }, 4000);
  }
}

async function togglePmSystem(group) {
  const btn = document.getElementById('pm-system-btn-' + (group === 'm15_210' ? '210' : group));
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  const prev = btn.textContent;
  btn.textContent = '…';
  try {
    const r = await fetch('/poly/api/pm-system', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ group, toggle: true }),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Hata');
    updatePmSystemUI(d);
  } catch (e) {
    btn.textContent = prev;
    alert('Sistem anahtarı: ' + e.message);
  } finally {
    btn.disabled = false;
  }
}

const _PM_SYSTEM_ROWS = {
  analiz5: {
    bar: 'pm-system-bar-analiz5', btn: 'pm-system-btn-analiz5',
    status: 'pm-system-status-analiz5', sub: 'pm-system-sub-analiz5',
    active: '✅ A1 Live açılış aktif', paused: '⏸ A1 Live kapalı',
    subOn: 'Gerçek PM · saatlik BTC+SOL · kapanış :02 · Cum 22:00 otomatik kapanır',
    subOff: 'Gerçek PM yeni işlem açmaz (sanal A1 devam) · Pzt 08:00 otomatik açılır',
  },
  analiz2: {
    bar: 'pm-system-bar-analiz2', btn: 'pm-system-btn-analiz2',
    status: 'pm-system-status-analiz2', sub: 'pm-system-sub-analiz2',
    active: '✅ A2 açılış aktif', paused: '⏸ A2 kapalı',
    subOn: 'Gerçek PM · saatlik SOL · kapanış :02 · Cum 22:00 otomatik kapanır',
    subOff: 'Gerçek PM yeni işlem açmaz (sanal A2 devam) · Pzt 08:00 otomatik açılır',
  },
  m15_210: {
    bar: 'pm-system-bar-210', btn: 'pm-system-btn-210',
    status: 'pm-system-status-210', sub: 'pm-system-sub-210',
    active: '✅ 210 açılış aktif', paused: '⏸ 210 kapalı',
    subOn: 'Gerçek PM 15M · Cum 22:00 otomatik kapanır',
    subOff: 'Gerçek PM 15M açmaz (110 sanal devam) · Pzt 08:00 otomatik açılır',
  },
};

function _pmSystemRow(group, paused, updatedAt) {
  const cfg = _PM_SYSTEM_ROWS[group];
  if (!cfg) return;
  const bar = document.getElementById(cfg.bar);
  const btn = document.getElementById(cfg.btn);
  const status = document.getElementById(cfg.status);
  const sub = document.getElementById(cfg.sub);
  if (!bar || !btn || !status) return;
  bar.classList.toggle('paused', !!paused);
  btn.classList.toggle('paused', !!paused);
  status.textContent = paused ? cfg.paused : cfg.active;
  sub.textContent = paused ? cfg.subOff : cfg.subOn;
  btn.textContent = paused ? 'Aç' : 'Kapat';
  if (sub && updatedAt) {
    const t = String(updatedAt).slice(11, 16);
    if (t) sub.textContent += ' · ' + t;
  }
}

function updatePmSystemUI(d) {
  if (!d) return;
  _pmSystemRow('analiz5', !!d.analiz5_paused, d.updated_at_tr);
  _pmSystemRow('analiz2', !!d.analiz2_paused, d.updated_at_tr);
  _pmSystemRow('m15_210', !!d.m15_210_paused, d.updated_at_tr);
  _a3a8SignalRow(d);
}

function _a3a8SignalRow(d) {
  const strict = d.a3a8_signal_strict !== false;
  const bar = document.getElementById('pm-system-bar-a3a8');
  const status = document.getElementById('pm-system-status-a3a8');
  const sub = document.getElementById('pm-system-sub-a3a8');
  const btn = document.getElementById('pm-system-btn-a3a8');
  if (!bar || !status || !sub || !btn) return;
  bar.classList.toggle('paused', !strict);
  status.textContent = strict ? '🔒 A3/A8 sıkı sinyal' : '🔓 A3/A8 gevşek (her saat)';
  sub.textContent = strict
    ? 'Entry bias + EMA kesişim · grafik + canlı A3/A8/112/113'
    : 'Skor oylaması + EMA pozisyon · eski davranış';
  btn.textContent = strict ? 'Gevşek' : 'Sıkı';
}

async function toggleA3A8SignalMode() {
  const btn = document.getElementById('pm-system-btn-a3a8');
  if (btn) btn.disabled = true;
  try {
    const cur = await fetch('/poly/api/pm-system', {cache: 'no-store'}).then(r => r.json());
    const strict = !(cur.a3a8_signal_strict !== false);
    const r = await fetch('/poly/api/pm-system', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({a3a8_signal_strict: strict}),
    });
    const d = await r.json();
    if (d.ok) updatePmSystemUI(d);
  } catch (e) {
    console.warn('a3a8 signal toggle', e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function refresh() {
  try {
    const [rd, rs, rss] = await Promise.all([
      fetch('/poly/api/data', {cache: 'no-store'}),
      fetch('/poly/api/stats', {cache: 'no-store'}),
      fetch('/poly/api/symbol_stats', {cache: 'no-store'}),
    ]);
    const d  = await rd.json();
    const s  = await rs.json();
    const ss = await rss.json();
    _panelAnaliz = ss.analiz || 'analiz1';
    const panelLbl = ss.analiz_label ? `· ${ss.analiz_label}` : '';
    const totalStr = ss.total ? ` · ${ss.total} işlem` : '';
    const symLbl = document.getElementById('sym-wr-label');
    const slotLbl = document.getElementById('top-slots-label');
    if (symLbl) symLbl.textContent = panelLbl + totalStr;
    if (slotLbl) slotLbl.textContent = panelLbl;

    // Header stats
    document.getElementById('portfolio').textContent = d.portfolio >= 0 ? '$'+d.portfolio.toFixed(2) : '?';
    document.getElementById('cash').textContent      = d.cash >= 0 ? '$'+d.cash.toFixed(2) : '?';
    document.getElementById('updated').textContent   = d.updated;
    updatePmSystemUI(d);

    // PM kotasyon — yalnızca açık pozisyonun timeframe/sembolü
    function renderPmQuotes(el, quotes, timeKey) {
      if (!el) return;
      if (!quotes || !quotes.length) {
        el.innerHTML = '';
        el.classList.remove('single');
        return;
      }
      el.classList.toggle('single', quotes.length === 1);
      el.innerHTML = quotes.map(q => {
        if (q.error) {
          return `<div class="pm-hourly-card"><div class="pm-hourly-head"><span class="pm-hourly-sym">${q.name}</span></div><div style="color:#666;font-size:12px">${q.error}</div></div>`;
        }
        const bn = q.binance != null ? `$${q.binance}` : '—';
        const dec = q.name === 'BTC' ? 1 : 2;
        const upC = q.up_cents != null ? q.up_cents.toFixed(dec) : '—';
        const dnC = q.down_cents != null ? q.down_cents.toFixed(dec) : '—';
        const tl = q[timeKey] || '';
        const entryStr = q.pos_entry != null
          ? `<span><span class="bn-lbl">Giriş</span> <span class="bn-val">$${Number(q.pos_entry).toFixed(dec)}</span></span>`
          : '';
        const liveBnStr = `<span><span class="bn-lbl">Anlık</span> <span class="bn-val">${bn}</span></span>`;
        const posLiveStr = q.pos_live != null
          ? `<span><span class="bn-lbl">Pozisyon</span> <span class="pos-live">$${q.pos_live.toFixed(2)}</span>`
            + (q.pos_risk ? `<span style="color:#666;font-weight:600"> / $${q.pos_risk.toFixed(2)}</span>` : '')
            + `</span>`
          : '';
        return `<div class="pm-hourly-card">
          <div class="pm-hourly-head">
            <span class="pm-hourly-sym">${q.name}</span>
            <span class="pm-hourly-et">${tl}${q.closed ? ' · kapalı' : ''}</span>
          </div>
          <div class="pm-hourly-prices">
            <div class="pm-hourly-pill up"><div class="pm-hourly-lbl">UP</div><div class="pm-hourly-val">${upC}¢</div></div>
            <div class="pm-hourly-pill down"><div class="pm-hourly-lbl">DOWN</div><div class="pm-hourly-val">${dnC}¢</div></div>
          </div>
          <div class="pm-hourly-bn">${entryStr}${liveBnStr}${posLiveStr}</div>
        </div>`;
      }).join('');
    }
    const hourlyWrap = document.getElementById('pm-hourly-wrap');
    const m15Wrap = document.getElementById('pm-15m-wrap');
    const hasHourly = d.pm_hourly && d.pm_hourly.length;
    const hasM15 = d.pm_15m && d.pm_15m.length;
    if (hourlyWrap) hourlyWrap.style.display = hasHourly ? '' : 'none';
    if (m15Wrap) m15Wrap.style.display = hasM15 ? '' : 'none';
    renderPmQuotes(document.getElementById('pm-hourly'), d.pm_hourly, 'hour_et');
    renderPmQuotes(document.getElementById('pm-15m'), d.pm_15m, 'period_lbl');

    // WR & PnL — 1. Analiz
    const a1 = s.algo_stats.find(a => a.key === 'analiz1');
    if (a1) {
      const wrEl = document.getElementById('wr-stat');
      wrEl.textContent = a1.wr + '%';
      wrEl.className = 'stat-val ' + (a1.wr >= 50 ? 'up' : 'down');
      document.getElementById('wr-sub').textContent = a1.wins + 'W / ' + (a1.total - a1.wins) + 'L · ' + a1.total + ' işlem';
      const pnlEl = document.getElementById('pnl-stat');
      pnlEl.textContent = (a1.pnl >= 0 ? '+' : '') + '$' + a1.pnl.toFixed(2);
      pnlEl.className = 'stat-val ' + (a1.pnl >= 0 ? 'up' : 'down');
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
        const dec = p.name === 'BTC' ? 1 : 2;
        const deltaStr = p.delta != null
          ? (p.delta >= 0 ? '+' : '-') + '$' + Math.abs(p.delta).toFixed(dec)
          : '';
        const deltaUp = p.delta != null && p.delta >= 0;
        const slotStr = p.slot_range
          ? `<div class="pos-slot"><span class="pos-slot-lbl">${p.is_15m ? '15dk slot:' : 'Saat slot:'}</span> ${p.slot_range} İST</div>`
          : (p.entry_time ? `<div class="pos-slot"><span class="pos-slot-lbl">Saat:</span> ${p.entry_time.substring(11,16)} İST</div>` : '');
        const cvColor = p.close_val !== null ? (parseFloat(p.close_val)>=parseFloat(p.pm_spent)?'#4ade80':'#f87171') : '#555';
        const pnlClass = p.close_pnl != null ? (p.close_pnl >= 0 ? 'pos' : 'neg') : '';
        const pnlStr = p.close_pnl != null
          ? `<span class="live-close-pnl ${pnlClass}">${p.close_pnl >= 0 ? '+' : '-'}$${Math.abs(p.close_pnl).toFixed(2)}</span>`
          : '';
        const winStr = p.win_payout != null
          ? `<div class="pos-win-row"><span class="win-lbl">Kazanırsa:</span> $${p.win_payout.toFixed(2)}`
            + (p.win_profit != null ? ` <span style="opacity:.85">(${p.win_profit >= 0 ? '+' : ''}$${p.win_profit.toFixed(2)})</span>` : '')
            + '</div>'
          : '';
        const winIcon = p.current == null ? '' : p.winning === true
          ? '<span class="pos-win-icon ok" title="Yön tutuyor">✓</span>'
          : p.winning === false
            ? '<span class="pos-win-icon bad" title="Yön ters">✕</span>'
            : '';
        return `<div class="pos-card ${dirClass}" data-live="${p.analiz_key}:${p.name}" data-spent="${p.pm_spent}">
          <div class="pos-top">
            <div class="pos-name">${p.name}</div>
            <div class="pos-dir ${dc}">${p.dir_tr}</div>
          </div>
          <div class="pos-price-row">
            <span class="pos-current">${p.current?'$'+p.current:''}${winIcon}</span>
            <span class="pos-pct ${deltaUp?'pos':'neg'}">${p.current?deltaStr:''}</span>
          </div>
          <div class="pos-entry"><span class="pos-entry-lbl">Giriş:</span> $${p.entry}</div>
          ${slotStr}
          <div class="pos-close-row">
            <span class="close-lbl">Anlık kapatma</span>
            <span class="live-close-val" style="color:${cvColor}">${p.close_val != null ? '$'+p.close_val.toFixed(2) : '—'}</span>
            ${pnlStr}
            ${p.token_cents != null ? `<span class="close-token">@${p.token_cents}¢</span>` : ''}
            <span class="live-updated" data-live-ts="${p.analiz_key}:${p.name}"></span>
          </div>
          <div class="pos-risk-row">Risk: $${p.pm_spent}
            <span class="pos-analiz-tag">${p.analiz}</span>
          </div>
          ${winStr}
          ${p.closable ? `<div class="close-btn-wrap">
            <button class="close-btn" onclick="closePosition('${p.analiz_key}', '${p.symbol}', this, '${p.pos_id || p.pm_order_id || ''}')">Pozisyonu Kapat</button>
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

    // Son işlemler (sağ panel + mobil) — bekleyen + kapanmış, zamana göre
    function fmtTradeTime(raw) {
      const s = String(raw || '');
      if (s.length >= 16) return s.slice(11, 16);
      const m = s.match(/(\d{2}:\d{2})\s*$/);
      return m ? m[1] : s;
    }
    function tradeItemHTML(t) {
      const pending = !!t.pending;
      const dirIcon = t.dir==='UP' ? '📈' : '📉';
      const tStr = fmtTradeTime(t.time);
      if (pending) {
        return `<div class="trade-item pending">
          <div class="trade-left">
            <div class="trade-sym">${dirIcon} ${t.sym} <span style="font-size:10px;color:#555">${t.analiz}</span><span class="trade-badge-pending">AÇIK</span></div>
            <div class="trade-meta" style="color:#777">${tStr} · $${t.spent}</div>
          </div>
          <div class="trade-pnl">—</div>
        </div>`;
      }
      const pnlC = t.pnl >= 0 ? 'pos' : 'neg';
      const pnlStr = (t.pnl>=0?'+':'')+'$'+Math.abs(t.pnl).toFixed(2);
      return `<div class="trade-item">
        <div class="trade-left">
          <div class="trade-sym">${dirIcon} ${t.sym} <span style="font-size:10px;color:#555">${t.analiz}</span></div>
          <div class="trade-meta" style="color:#777">${tStr} · $${t.spent}</div>
        </div>
        <div class="trade-pnl ${pnlC}">${pnlStr}</div>
      </div>`;
    }
    const mergedRecent = [...(s.pending || []), ...(s.recent || [])]
      .sort((a, b) => String(b.time).localeCompare(String(a.time)))
      .slice(0, 20);
    const rt = document.getElementById('recent-trades');
    const recentHTML = mergedRecent.map(tradeItemHTML).join('') || '<div style="color:#666;font-size:13px">Henüz işlem yok</div>';
    if (rt) rt.innerHTML = recentHTML;
    const rtMob = document.getElementById('recent-trades-mob');
    if (rtMob) {
      const mobRecent = mergedRecent.slice(0, 10);
      rtMob.innerHTML = mobRecent.map(tradeItemHTML).join('') || '<div style="color:#666;font-size:13px">Henüz işlem yok</div>';
    }

    // Algoritma performansı
    const as = document.getElementById('algo-stats');
    as.innerHTML = s.algo_stats.map(a => `
      <div class="algo-item">
        <div class="algo-name">${a.label}</div>
        <div class="algo-bar"><div class="algo-bar-fill" style="width:${a.wr}%"></div></div>
        <div class="algo-wr" style="color:${a.wr>=55?'#4ade80':a.wr>=50?'#a3e635':'#f87171'}">${a.wr}%</div>
      </div>`).join('') || '<div style="color:#666;font-size:13px">Veri yok</div>';

    if (window.renderSidebarProfit) await renderSidebarProfit();

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
    const top3 = data.slice(0,2);
    document.getElementById('top3-analizler').innerHTML = top3.map((a,i) => {
      const color  = top3Color(a.wr);
      const pnlCls = a.pnl>0?'color:#4ade80':a.pnl<0?'color:#f87171':'color:#888';
      const pnlStr = (a.pnl>=0?'+':'')+'$'+Math.abs(a.pnl).toFixed(2);
      const medals = ['🥇','🥈'];
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

function patchPositionsLive(items, updated) {
  items.forEach(p => {
    const key = `${p.analiz_key}:${p.name}`;
    document.querySelectorAll(`[data-live="${key}"]`).forEach(card => {
      const dec = p.name === 'BTC' ? 1 : 2;
      const cv = card.querySelector('.live-close-val');
      const cp = card.querySelector('.live-close-pnl');
      const cur = card.querySelector('.pos-current');
      const pct = card.querySelector('.pos-pct');
      const tok = card.querySelector('.close-token');
      const ts = card.querySelector('.live-updated');
      if (cv && p.close_val != null) {
        cv.textContent = '$' + p.close_val.toFixed(2);
        cv.style.color = p.close_pnl != null ? (p.close_pnl >= 0 ? '#4ade80' : '#f87171') : '#fff';
      }
      if (cp && p.close_pnl != null) {
        cp.textContent = (p.close_pnl >= 0 ? '+' : '-') + '$' + Math.abs(p.close_pnl).toFixed(2);
        cp.className = 'live-close-pnl ' + (p.close_pnl >= 0 ? 'pos' : 'neg');
      }
      if (tok && p.token_cents != null) tok.textContent = '@' + p.token_cents + '¢';
      if (cur && p.current != null) {
        const winIcon = p.winning === true ? '<span class="pos-win-icon ok" title="Yön tutuyor">✓</span>'
          : p.winning === false ? '<span class="pos-win-icon bad" title="Yön ters">✕</span>' : '';
        cur.innerHTML = '$' + p.current + winIcon;
      }
      if (pct && p.delta != null) {
        const up = p.delta >= 0;
        pct.textContent = (up ? '+' : '-') + '$' + Math.abs(p.delta).toFixed(dec);
        pct.className = 'pos-pct ' + (up ? 'pos' : 'neg');
      }
      if (ts && updated) ts.textContent = updated + ' güncellendi';
    });
  });
}

async function refreshPositionsLive() {
  try {
    const r = await fetch('/poly/api/positions-live', {cache: 'no-store'});
    if (!r.ok) return;
    const d = await r.json();
    patchPositionsLive(d.positions || [], d.updated);
  } catch (e) { console.error('positions-live', e); }
}

refresh();
setInterval(refresh, 10000);
setInterval(refreshPositionsLive, 5000);
refreshPositionsLive();
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
    ? `/poly/api/heatmap/detail?dow=${dow}&hour=${hour}&sym=ALL&analiz=${_panelAnaliz}`
    : `/poly/api/heatmap/detail?hour=${hour}&sym=ALL&analiz=${_panelAnaliz}`;
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
  const analiz = _panelAnaliz || 'analiz1';
  updateMainHmSymFilters(analiz);
  const lbl = ({analiz1:'1. Analiz',analiz2:'2. Analiz (SOL)',analiz2_live:'A2 Live',analiz3:'3. Analiz Freqtrade',analiz5:'A1 Live',analiz8:'8. Analiz Jesse',analiz4:'4. Analiz',analiz6:'6. Analiz',analiz10:'10. Analiz',alfa:'ALFA','5m_sol_109':'15M 109 SOL','5m_sol_110':'15M 110 SOL','5m_sol_111':'15M 111 SOL','5m_sol_210':'15M 210 SOL'})[analiz] || analiz;
  const sub = document.getElementById('hm-subtitle-main');
  if (sub) sub.textContent = `${lbl} — gün × saat kazanma oranı`;
  try {
    const r = await fetch('/poly/api/heatmap?sym=' + _hmSym + '&analiz=' + analiz);
    const d = await r.json();
    if (!d || !Array.isArray(d.cells)) {
      renderHeatmap([]);
      return;
    }
    renderSummary(d.summary || {total:0,wins:0,losses:0,wr:0,pnl:0,spent:0}, d.sym_breakdown || []);
    renderHeatmap(d.cells);
  } catch (e) {
    console.error('heatmap', e);
    renderHeatmap([]);
  }
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
  document.querySelectorAll('#view-heatmap .hm-filter').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _hmSym  = sym;
  _hmData = null;
  loadHeatmap();
}

function updateMainHmSymFilters(analiz) {
  const allowed = {{ harita_heatmap_syms|safe }}[analiz] || ['BTC', 'ETH', 'SOL'];
  document.querySelectorAll('#view-heatmap .hm-filter').forEach(btn => {
    const sym = btn.dataset.sym;
    if (!sym) return;
    if (sym === 'ALL') {
      btn.style.display = '';
      return;
    }
    btn.style.display = allowed.includes(sym) ? '' : 'none';
  });
  if (_hmSym !== 'ALL' && !allowed.includes(_hmSym)) {
    _hmSym = allowed.length === 1 ? allowed[0] : 'ALL';
    document.querySelectorAll('#view-heatmap .hm-filter').forEach(b => {
      b.classList.toggle('active', b.dataset.sym === _hmSym);
    });
  }
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
    "amount_agree":    {"label": "A9 + A1 Live aynı yön", "unit": "$", "min": 1, "max": 100, "step": 0.5},
    "amount_a5_only":  {"label": "A9 sessiz, A1 Live var", "unit": "$", "min": 1, "max": 100, "step": 0.5},
    "amount_a9_only":  {"label": "A9 var, A1 Live sessiz", "unit": "$", "min": 1, "max": 100, "step": 0.5},
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
    resp = make_response(render_template_string(HTML))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp

@app.route("/poly/grafik")
@app.route("/poly/grafik/")
def page_grafik():
    if _auth_required():
        return _login_redirect()
    return GRAFIK_HTML, 200, _ISLEMLER_NOCACHE


@app.route("/poly/islemler")
@app.route("/poly/islemler/")
@app.route("/islemler")
@app.route("/islemler/")
def page_islemler():
    if request.path.rstrip("/") == "/islemler":
        return redirect("/poly/islemler")
    if _auth_required():
        return _login_redirect()
    return ISLEMLER_HTML, 200, _ISLEMLER_NOCACHE


@app.route("/harita")
@app.route("/harita/")
def harita():
    if _auth_required(): return redirect("/poly/login")
    labels = {k: v for k, v in _HARITA_TAB_ANALYSES}
    hm_syms = {k: v for k, v in _HEATMAP_SYMS.items() if k in _HEATMAP_ANALYSES}
    default_key = _HARITA_TAB_ANALYSES[0][0] if _HARITA_TAB_ANALYSES else "analiz5"
    default_label = labels.get(default_key, "Analiz")
    return render_template_string(
        HARITA_HTML,
        harita_tabs=_harita_tabs_html(),
        harita_labels=json.dumps(labels, ensure_ascii=False),
        harita_heatmap_syms=json.dumps(hm_syms, ensure_ascii=False),
        harita_default_analiz=default_key,
        harita_default_label=default_label,
    )

for _html_name in ("ANALIZLER_HTML", "GECMIS_HTML", "ALGORITMA_HTML", "AYARLAR_HTML", "HARITA_HTML", "GRAFIK_HTML", "ISLEMLER_HTML", "HTML"):
    globals()[_html_name] = _patch_nav_islemler(_patch_sidebar_profit(_patch_sidebar_cleanup(globals()[_html_name])))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
