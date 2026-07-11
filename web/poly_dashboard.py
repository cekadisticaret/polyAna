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

def _pm_sell_position(token_id: str, size: float) -> dict | None:
    """Polymarket'ta token sat (pozisyonu kapat)."""
    try:
        import sys as _sys
        _sys.path.insert(0, _DIR_POLY)
        from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
        from py_clob_client_v2.order_builder.constants import SELL
        from decimal import Decimal, ROUND_DOWN
        client = get_pm_balance.__func__ if hasattr(get_pm_balance, '__func__') else None

        # client'ı analiz5'ten al
        import importlib.util, types
        spec = importlib.util.spec_from_file_location(
            "a5", os.path.join(_DIR_POLY, "poly_trader_analiz5.py"))
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        client = mod._pm_get_client()

        price = float(client.calculate_market_price(token_id, "SELL", size, OrderType.FAK))
        price = max(0.02, min(0.98, round(price, 2)))
        size  = float(Decimal(str(size)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        args  = OrderArgs(token_id=token_id, price=price, size=size, side=SELL)
        signed = client.create_order(args, PartialCreateOrderOptions())
        resp   = client.post_order(signed, order_type=OrderType.FAK)
        if resp and resp.get("success"):
            return {"ok": True, "price": price, "size": size,
                    "received": round(size * price, 2)}
        return {"ok": False, "error": str(resp)}
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

        # Gerçek PM satış emri
        sell_result = _pm_sell_position(token_id, pm_size) if token_id and pm_size else None

        # State'ten kaldır
        state["open_positions"] = [
            p for p in state["open_positions"] if p.get("symbol") != symbol
        ]
        save_state(analiz, state)

        return jsonify({
            "ok":         True,
            "sell":       sell_result,
            "symbol":     symbol,
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
  body { background:#0d0d0d; color:#fff; font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif; min-height:100vh; }

  .header { padding:24px 20px 12px; }
  .header-row { display:flex; gap:32px; }
  .header-col { flex:1; }
  .header-label { font-size:13px; color:#666; letter-spacing:.5px; text-transform:uppercase; margin-bottom:4px; }
  .balance { font-size:36px; font-weight:700; letter-spacing:-1px; color:#4ade80; }
  .balance.portfolio { color:#a3e635; }
  .balance-sub { font-size:13px; color:#444; margin-top:8px; }
  .balance-sub span { color:#4ade80; }

  .chart-wrap { margin:20px 16px; background:#141414; border-radius:20px; overflow:hidden; }
  .chart-tabs { display:flex; gap:8px; padding:16px 16px 0; }
  .chart-tab { padding:6px 14px; border-radius:20px; font-size:13px; font-weight:700;
               cursor:pointer; color:#555; transition:.2s; border:none; background:transparent; }
  .chart-tab.active { background:#c8f135; color:#111; }
  #chart { height:220px; margin:12px 0 0; }

  .section-title { font-size:13px; color:#555; text-transform:uppercase; letter-spacing:.5px;
                   padding:0 20px; margin:24px 0 12px; }

  .positions { padding:0 16px; display:flex; flex-direction:column; gap:12px; }
  .pos-card { background:#141414; border-radius:20px; padding:18px; position:relative; overflow:hidden; }
  .pos-card.winning { border-left:3px solid #4ade80; }
  .pos-card.losing  { border-left:3px solid #f87171; }
  .pos-card.pending { border-left:3px solid #555; }

  .pos-top { display:flex; justify-content:space-between; align-items:center; }
  .pos-name { font-size:22px; font-weight:700; }
  .pos-dir  { font-size:13px; font-weight:600; padding:4px 10px; border-radius:10px; }
  .pos-dir.up   { background:#14532d; color:#4ade80; }
  .pos-dir.down { background:#450a0a; color:#f87171; }

  .pos-prices { margin:10px 0; }
  .pos-entry  { font-size:13px; color:#555; }
  .pos-current { font-size:28px; font-weight:700; letter-spacing:-.5px; }
  .pos-pct { font-size:14px; font-weight:600; margin-left:8px; }
  .pos-pct.pos { color:#4ade80; }
  .pos-pct.neg { color:#f87171; }

  .pos-meta { display:flex; justify-content:space-between; align-items:center; margin-top:12px; }
  .pos-info { font-size:12px; color:#555; }
  .pos-analiz { font-size:11px; color:#333; background:#1c1c1e; padding:3px 8px; border-radius:8px; }

  .close-btn-wrap { display:flex; justify-content:flex-end; margin-top:14px; }
  .close-btn { background:#c8f135; border:none; color:#111; font-size:13px; font-weight:800;
               padding:10px 20px; border-radius:14px; cursor:pointer;
               width:50%; transition:.2s; letter-spacing:.3px; white-space:nowrap; }
  .close-btn:hover { background:#d4ff3a; }
  .close-btn:active { transform:scale(.97); }
  .close-btn.loading { opacity:.5; pointer-events:none; }

  .empty { text-align:center; padding:48px 20px; color:#333; font-size:16px; }

  .refresh-bar { text-align:center; padding:20px; font-size:12px; color:#333; }
  .dot { width:6px; height:6px; background:#4ade80; border-radius:50%; display:inline-block;
         margin-right:6px; animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  .total-risk { background:#c8f135; border-radius:20px; margin:0 16px 20px; padding:16px 18px;
                display:flex; justify-content:space-between; align-items:center; }
  .risk-label { font-size:13px; color:#111; font-weight:700; }
  .risk-val { font-size:20px; font-weight:800; color:#111; }
</style>
</head>
<body>

<div class="header">
  <div class="header-row">
    <div class="header-col">
      <div class="header-label">Portfolio</div>
      <div class="balance portfolio" id="portfolio">$—</div>
    </div>
    <div class="header-col">
      <div class="header-label">Cash</div>
      <div class="balance" id="cash">$—</div>
    </div>
  </div>
  <div class="balance-sub">Son güncelleme: <span id="updated">—</span></div>
</div>

<div class="chart-wrap">
  <div class="chart-tabs" id="chart-tabs"></div>
  <div id="chart"></div>
</div>

<div class="total-risk">
  <span class="risk-label">Toplam Riskteki</span>
  <span class="risk-val" id="total-risk">$—</span>
</div>

<div class="section-title">Açık Pozisyonlar</div>
<div class="positions" id="positions">
  <div class="empty">Yükleniyor...</div>
</div>
<div class="refresh-bar"><span class="dot"></span>Her 30 saniyede otomatik güncellenir</div>

<script>
let chartInstance = null;
let seriesInstance = null;
let currentSym = null;
const symColors = { BTC: '#f97316', ETH: '#818cf8', SOL: '#4ade80' };

function initChart(container) {
  if (chartInstance) { chartInstance.remove(); }
  chartInstance = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 220,
    layout: { background: { color: '#141414' }, textColor: '#666' },
    grid: { vertLines: { color: '#1c1c1e' }, horzLines: { color: '#1c1c1e' } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    timeScale: { borderColor: '#1c1c1e', timeVisible: true },
    rightPriceScale: { borderColor: '#1c1c1e' },
  });
  seriesInstance = chartInstance.addCandlestickSeries({
    upColor: '#4ade80', downColor: '#f87171',
    borderUpColor: '#4ade80', borderDownColor: '#f87171',
    wickUpColor: '#4ade80', wickDownColor: '#f87171',
  });
  return chartInstance;
}

async function loadChart(sym) {
  currentSym = sym;
  document.querySelectorAll('.chart-tab').forEach(t => t.classList.toggle('active', t.dataset.sym === sym));
  const container = document.getElementById('chart');
  initChart(container);
  try {
    const res = await fetch(`/poly/api/klines/${sym}`);
    const data = await res.json();
    seriesInstance.setData(data.map(k => ({
      time: Math.floor(k.t / 1000),
      open: k.o, high: k.h, low: k.l, close: k.c,
    })));
  } catch(e) { console.error(e); }
}

function buildTabs(syms) {
  const tabs = document.getElementById('chart-tabs');
  tabs.innerHTML = '';
  syms.forEach(sym => {
    const btn = document.createElement('button');
    btn.className = 'chart-tab' + (sym === currentSym ? ' active' : '');
    btn.textContent = sym;
    btn.dataset.sym = sym;
    btn.onclick = () => loadChart(sym);
    tabs.appendChild(btn);
  });
}

async function closePosition(analiz, symbol, btn) {
  btn.classList.add('loading');
  btn.textContent = 'Kapatılıyor...';
  try {
    const res  = await fetch(`/poly/api/close/${analiz}/${symbol}`, { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      const s = data.sell;
      if (s && s.ok) {
        btn.style.background = '#4ade80';
        btn.textContent = `✅ Kapatıldı · $${s.received}`;
      } else if (s && !s.ok) {
        btn.style.background = '#f87171';
        btn.textContent = `⚠️ ${s.error || 'PM hatası'}`;
        btn.classList.remove('loading');
      } else {
        btn.textContent = '✅ Kapatıldı';
      }
      setTimeout(() => refresh(), 2000);
    } else {
      btn.textContent = 'Hata!';
      btn.style.background = '#f87171';
      btn.classList.remove('loading');
    }
  } catch(e) { btn.textContent = 'Hata!'; btn.classList.remove('loading'); }
}

async function refresh() {
  try {
    const res = await fetch('/poly/api/data');
    const d   = await res.json();

    document.getElementById('portfolio').textContent = d.portfolio >= 0 ? '$' + d.portfolio.toFixed(2) : '?';
    document.getElementById('cash').textContent      = d.cash >= 0 ? '$' + d.cash.toFixed(2) : '?';
    document.getElementById('updated').textContent   = d.updated;

    const totalRisk = d.positions.reduce((s, p) => s + (p.pm_spent || 0), 0);
    document.getElementById('total-risk').textContent = '$' + totalRisk.toFixed(2);

    const syms = [...new Set(d.positions.map(p => p.name))];
    buildTabs(syms);
    if (syms.length && !currentSym) { loadChart(syms[0]); }

    const container = document.getElementById('positions');
    if (!d.positions.length) {
      container.innerHTML = '<div class="empty">Şu an açık pozisyon yok</div>';
      return;
    }

    container.innerHTML = d.positions.map(p => {
      const winClass = p.winning === true ? 'winning' : p.winning === false ? 'losing' : 'pending';
      const dirClass = p.dir === 'UP' ? 'up' : 'down';
      const pctClass = p.pct >= 0 ? 'pos' : 'neg';
      const pctStr   = (p.pct >= 0 ? '+' : '') + p.pct.toFixed(2) + '%';
      const timeStr  = p.entry_time ? p.entry_time.substring(11, 16) + ' İST' : '';
      return `
        <div class="pos-card ${winClass}">
          <div class="pos-top">
            <div class="pos-name">${p.name}</div>
            <div class="pos-dir ${dirClass}">${p.dir_tr}</div>
          </div>
          <div class="pos-prices">
            <div class="pos-entry">Giriş: $${p.entry}</div>
            <div>
              <span class="pos-current">${p.current ? '$' + p.current : '—'}</span>
              <span class="pos-pct ${pctClass}">${p.current ? pctStr : ''}</span>
            </div>
          </div>
          <div class="pos-meta">
            <div class="pos-info">
              Riskteki: $${p.pm_spent}
              ${p.close_val !== null
                ? ` <span style="color:${parseFloat(p.close_val) >= parseFloat(p.pm_spent) ? '#4ade80' : '#f87171'};font-weight:700;">→ $${p.close_val}</span>`
                : ''}
              · ${timeStr}
            </div>
            <div class="pos-analiz">${p.analiz}</div>
          </div>
          <div class="close-btn-wrap">
            <button class="close-btn" onclick="closePosition('${p.analiz}','${p.symbol}',this)">
              Pozisyonu Kapat
            </button>
          </div>
        </div>`;
    }).join('');
  } catch(e) { console.error(e); }
}

refresh();
setInterval(refresh, 30000);
window.addEventListener('resize', () => {
  if (chartInstance) {
    const c = document.getElementById('chart');
    chartInstance.applyOptions({ width: c.clientWidth });
  }
});
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
