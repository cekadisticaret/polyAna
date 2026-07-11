"""
PolyMarket Dashboard — bursaapp.com/poly
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template_string, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "temmuzPoly"))

_DIR_POLY = os.path.join(os.path.dirname(__file__), "..", "temmuzPoly")
_TZ_TR    = ZoneInfo("Europe/Istanbul")
_BINANCE  = "https://fapi.binance.com"

app = Flask(__name__)

# ── Yardımcı fonksiyonlar ──────────────────────────────────────
def _binance(path, params=None):
    qs  = ("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else ""
    req = urllib.request.Request(_BINANCE + path + qs, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)

def get_price(symbol: str) -> float:
    return float(_binance("/fapi/v1/ticker/price", {"symbol": symbol})["price"])

def get_klines(symbol: str, interval="1h", limit=50):
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

def collect_positions() -> list:
    """Tüm aktif analizlerin açık pozisyonlarını toplar."""
    analyses = ["analiz1", "analiz2", "analiz4", "analiz5", "analiz10"]
    seen = set()
    positions = []
    for name in analyses:
        state = load_state(name)
        for pos in state.get("open_positions", []):
            sym = pos.get("symbol", "")
            key = f"{name}_{sym}"
            if key in seen:
                continue
            seen.add(key)
            positions.append({**pos, "_analiz": name})
    return positions

# ── API ───────────────────────────────────────────────────────
@app.route("/poly/api/data")
def api_data():
    positions = collect_positions()
    symbols   = list({p["symbol"] for p in positions})

    prices = {}
    for sym in symbols:
        try:
            prices[sym] = get_price(sym)
        except Exception:
            prices[sym] = None

    enriched = []
    for pos in positions:
        sym          = pos["symbol"]
        current_p    = prices.get(sym)
        entry_p      = pos.get("entry_price", 0)
        pred         = pos.get("predicted_dir", "")
        pm_spent     = pos.get("pm_spent", 0)
        pm_size      = pos.get("pm_size", 0)

        # Anlık yön ve kazanç tahmini
        if current_p and entry_p:
            actual  = "UP" if current_p >= entry_p else "DOWN"
            winning = (actual == pred)
            pct     = (current_p - entry_p) / entry_p * 100
        else:
            winning, pct = None, 0.0

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
            "entry_time":   pos.get("entry_time_tr", ""),
            "pm_slug":      pos.get("pm_slug", ""),
        })

    balance = get_pm_balance()

    return jsonify({
        "balance":   round(balance, 2),
        "positions": enriched,
        "updated":   datetime.now(_TZ_TR).strftime("%H:%M:%S"),
    })

@app.route("/poly/api/klines/<symbol>")
def api_klines(symbol):
    try:
        data = get_klines(symbol.upper() + "USDT" if not symbol.endswith("USDT") else symbol.upper())
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/poly/api/close/<analiz>/<symbol>", methods=["POST"])
def api_close(analiz, symbol):
    try:
        state = load_state(analiz)
        before = len(state.get("open_positions", []))
        state["open_positions"] = [
            p for p in state.get("open_positions", [])
            if p.get("symbol") != symbol.upper()
        ]
        after = len(state["open_positions"])
        save_state(analiz, state)
        return jsonify({"ok": True, "removed": before - after})
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
  .header-label { font-size:13px; color:#666; letter-spacing:.5px; text-transform:uppercase; }
  .balance { font-size:48px; font-weight:700; letter-spacing:-1px; margin:4px 0; }
  .balance-sub { font-size:14px; color:#666; }
  .balance-sub span { color:#4ade80; }

  .chart-wrap { margin:20px 16px; background:#141414; border-radius:20px; overflow:hidden; }
  .chart-tabs { display:flex; gap:0; padding:16px 16px 0; }
  .chart-tab { padding:6px 14px; border-radius:20px; font-size:13px; font-weight:600;
               cursor:pointer; color:#555; transition:.2s; border:none; background:transparent; }
  .chart-tab.active { background:#1c1c1e; color:#fff; }
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

  .close-btn { background:#1c1c1e; border:none; color:#f87171; font-size:13px; font-weight:600;
               padding:10px 20px; border-radius:14px; cursor:pointer; margin-top:14px;
               width:100%; transition:.2s; letter-spacing:.3px; }
  .close-btn:hover { background:#2c1c1c; }
  .close-btn:active { transform:scale(.97); }
  .close-btn.loading { opacity:.5; pointer-events:none; }

  .empty { text-align:center; padding:48px 20px; color:#333; font-size:16px; }

  .refresh-bar { text-align:center; padding:20px; font-size:12px; color:#333; }
  .dot { width:6px; height:6px; background:#4ade80; border-radius:50%; display:inline-block;
         margin-right:6px; animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  .total-risk { background:#141414; border-radius:20px; margin:0 16px 20px; padding:16px 18px;
                display:flex; justify-content:space-between; align-items:center; }
  .risk-label { font-size:13px; color:#555; }
  .risk-val { font-size:18px; font-weight:700; color:#f97316; }
</style>
</head>
<body>

<div class="header">
  <div class="header-label">PolyMarket Bakiye</div>
  <div class="balance" id="balance">$—</div>
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
    const res = await fetch(`/poly/api/close/${analiz}/${symbol}`, { method: 'POST' });
    const data = await res.json();
    if (data.ok) { await refresh(); }
    else { btn.textContent = 'Hata!'; btn.classList.remove('loading'); }
  } catch(e) { btn.textContent = 'Hata!'; btn.classList.remove('loading'); }
}

async function refresh() {
  try {
    const res = await fetch('/poly/api/data');
    const d   = await res.json();

    document.getElementById('balance').textContent =
      d.balance >= 0 ? '$' + d.balance.toFixed(2) : '?';
    document.getElementById('updated').textContent = d.updated;

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
            <div class="pos-info">Riskteki: $${p.pm_spent}  ·  ${timeStr}</div>
            <div class="pos-analiz">${p.analiz}</div>
          </div>
          <button class="close-btn" onclick="closePosition('${p.analiz}','${p.symbol}',this)">
            Pozisyonu Kapat
          </button>
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
    return render_template_string(HTML)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
