"""Forex sistemi — ayrı sayfa kabuğu (Poly / Kripto ile aynı dashboard)."""

FOREX_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cem Forex</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%230d1b2a'/><text x='50%25' y='54%25' font-size='16' text-anchor='middle' dominant-baseline='central' fill='%23d4af37' font-family='Arial' font-weight='bold'>F</text></svg>">
<style>
:root{
  --bg:#05080d; --card:#101820; --card2:#16202a; --line:rgba(212,175,55,.14);
  --txt:#f3efe4; --muted:#8b8678; --gold:#d4af37; --teal:#3dd6c6; --red:#ff6b7a;
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  min-height:100vh;display:flex;color:var(--txt);
  font-family:'Sora',sans-serif;
  background:
    radial-gradient(800px 420px at 8% -8%, rgba(212,175,55,.10), transparent 55%),
    radial-gradient(640px 380px at 92% 0%, rgba(61,214,198,.08), transparent 50%),
    var(--bg);
}
.sidebar{
  width:220px;background:rgba(8,12,18,.94);backdrop-filter:blur(12px);
  padding:24px 16px;display:flex;flex-direction:column;gap:4px;flex-shrink:0;
  position:sticky;top:0;height:100vh;overflow-y:auto;border-right:1px solid var(--line);
}
.nav-label{font-size:10px;color:#555;text-transform:uppercase;letter-spacing:1px;margin:16px 0 6px 12px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;color:#888;text-decoration:none;font-size:13px;font-weight:600;transition:all .15s}
.nav-item:hover{background:rgba(255,255,255,.04);color:#ccc}
.nav-item.active{background:rgba(212,175,55,.12);color:var(--gold)}
.nav-dot{width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.5}
.nav-item.active .nav-dot{opacity:1;background:var(--gold)}
.nav-item.nav-sub{margin-left:14px;padding-left:14px;font-size:12px}
.sidebar-footer{margin-top:auto;font-size:11px;color:#555;padding:12px;display:flex;align-items:center;gap:6px}
.sidebar-footer .dot{width:6px;height:6px;border-radius:50%;background:var(--gold)}
.main{flex:1;padding:28px 28px 40px;min-width:0}
.head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:22px;flex-wrap:wrap}
.page-title{font-size:28px;font-weight:800;letter-spacing:-.6px}
.page-sub{font-size:13px;color:var(--muted);margin-top:6px}
.badge{display:inline-flex;align-items:center;font-size:11px;font-weight:700;padding:5px 10px;border-radius:999px;margin-left:8px;vertical-align:middle;background:rgba(212,175,55,.12);color:var(--gold);border:1px solid rgba(212,175,55,.28)}
.hero{
  display:grid;grid-template-columns:1.4fr .8fr;gap:16px;margin-bottom:18px;
}
.glass{
  background:linear-gradient(160deg, rgba(255,255,255,.05), rgba(255,255,255,.015));
  border:1px solid var(--line);border-radius:24px;padding:22px 24px;
}
.hero h2{font-size:18px;font-weight:800;margin-bottom:8px}
.hero p{font-size:13px;color:var(--muted);line-height:1.55}
.wallet{
  padding:20px 22px;border-radius:24px;position:relative;overflow:hidden;
  background:linear-gradient(145deg,#1b3a4b 0%,#0d1b2a 55%,#c9a227 160%);
  border:1px solid rgba(212,175,55,.28);
}
.wallet-lbl{font-size:11px;font-weight:700;opacity:.75}
.wallet-bal{font-size:32px;font-weight:800;letter-spacing:-1px;margin-top:6px}
.wallet-meta{font-size:12px;opacity:.8;margin-top:10px}
.section{padding:20px;border-radius:24px;background:var(--card);border:1px solid var(--line)}
.section-title{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin-bottom:14px}
.pairs{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.pair{
  background:var(--card2);border:1px solid var(--line);border-radius:16px;padding:16px;
}
.pair-sym{font-size:18px;font-weight:800;letter-spacing:-.3px}
.pair-name{font-size:12px;color:var(--muted);margin-top:4px}
.pair-st{margin-top:12px;font-size:11px;font-weight:700;color:var(--gold)}
.sys{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
.sys a{
  display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;
  border:1px solid var(--line);color:var(--muted);text-decoration:none;font-size:12px;font-weight:700;
}
.sys a:hover{border-color:rgba(212,175,55,.45);color:var(--gold)}
@media(max-width:800px){
  body{flex-direction:column}
  .sidebar{width:100%;height:auto;position:relative}
  .hero{grid-template-columns:1fr}
  .main{padding:20px 16px}
}
</style>
</head>
<body id="fx-page">
<div class="sidebar">
  __FOREX_BRAND__
  <div class="nav-label">Ana Menü</div>
  <a class="nav-item active" href="/forex/home"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item" href="/forex/algoritma-islemler"><span class="nav-dot"></span>Algoritma işlemler</a>
  <a class="nav-item" href="/forex/grafik"><span class="nav-dot"></span>CEM01</a>
  <a class="nav-item" href="/forex/cem02"><span class="nav-dot"></span>CAPITAL</a>
  <a class="nav-item" href="/forex/gpsusdt"><span class="nav-dot"></span>GPSUSDT</a>
  <a class="nav-item" href="/forex/islemler"><span class="nav-dot"></span>İşlemler</a>
  <div class="nav-label">Sistemler</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Poly'ye Geç</a>
  <a class="nav-item" href="/kripto"><span class="nav-dot"></span>Kripto'ya Geç</a>
  <div class="sidebar-footer"><span class="dot"></span>Forex kabuğu</div>
</div>
<div class="main">
  <div class="head">
    <div>
      <div class="page-title">Forex <span class="badge">yeni</span></div>
      <div class="page-sub">Sanal XAUUSD · $300 kasa · $100×500x · AL/SAT sinyal</div>
    </div>
  </div>
  <div class="hero">
    <div class="glass">
      <h2>Sayfa açık</h2>
      <p>XAUUSD sanal defter: kasa $300, her işlem $100 × 500x. Grafikte AL yeşil → al, SAT kırmızı → sat. Liste <a href="/forex/islemler" style="color:var(--gold)">İşlemler</a>’de.</p>
      <div class="sys">
        <a href="/poly">← Poly</a>
        <a href="/kripto">← Kripto</a>
      </div>
    </div>
    <div class="wallet">
      <div class="wallet-lbl">Sanal kasa</div>
      <div class="wallet-bal" id="fx-bal">$300.00</div>
      <div class="wallet-meta" id="fx-meta">0 defter · 0 açık işlem</div>
    </div>
  </div>
  <div class="section">
    <div class="section-title">aday pariteler</div>
    <div class="pairs" id="fx-pairs"></div>
  </div>
</div>
<script>
const FALLBACK = [
  {symbol:'EURUSD', name:'Euro / Dolar'},
  {symbol:'GBPUSD', name:'Sterlin / Dolar'},
  {symbol:'USDJPY', name:'Dolar / Yen'},
  {symbol:'XAUUSD', name:'Altın / Dolar'},
];
function renderPairs(rows){
  const el = document.getElementById('fx-pairs');
  el.innerHTML = (rows || FALLBACK).map(p =>
    '<a class="pair" href="'+(p.symbol==='XAUUSD'?'/forex/grafik':'#')+'" style="text-decoration:none;color:inherit;display:block">'
    +'<div class="pair-sym">'+p.symbol+'</div>'
    +'<div class="pair-name">'+(p.name||'')+'</div>'
    +'<div class="pair-st">'+(p.symbol==='XAUUSD'?'grafik →':'bekliyor')+'</div></a>'
  ).join('');
}
async function loadStatus(){
  try{
    const r = await fetch('/poly/api/forex/status', {cache:'no-store'});
    if(!r.ok) return;
    const d = await r.json();
    if(d.pairs && d.pairs.length) renderPairs(d.pairs);
    const n = (d.books||[]).length;
    document.getElementById('fx-meta').textContent = n+' defter · '+(d.open_count||0)+' açık işlem';
    if(d.balance != null) document.getElementById('fx-bal').textContent = '$'+Number(d.balance).toFixed(2);
  }catch(e){}
}
renderPairs(FALLBACK);
loadStatus();
</script>
</body>
</html>
"""

FOREX_CHART_TMPL = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1">
<meta name="theme-color" content="#071018">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>__FX_TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%230d1b2a'/><text x='50%25' y='54%25' font-size='16' text-anchor='middle' dominant-baseline='central' fill='%23d4af37' font-family='Arial' font-weight='bold'>F</text></svg>">
<style>
:root{
  --bg:#071018; --side:#0b141c; --line:#1c2a36;
  --txt:#e8eef4; --muted:#7d8b96;
  --bid:#26a69a; --ask:#ef5350; --gold:#d4af37;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{display:flex;color:var(--txt);font-family:Inter,system-ui,sans-serif;background:var(--bg)}
.sidebar{width:200px;background:var(--side);padding:20px 12px;display:flex;flex-direction:column;gap:3px;flex-shrink:0;border-right:1px solid var(--line)}
.nav-label{font-size:10px;color:#556;text-transform:uppercase;letter-spacing:1px;margin:14px 0 4px 10px}
.nav-item{display:flex;align-items:center;gap:8px;padding:9px 10px;border-radius:10px;color:#8a96a0;text-decoration:none;font-size:13px;font-weight:600}
.nav-item.active{background:rgba(212,175,55,.12);color:var(--gold)}
.nav-item.nav-sub{margin-left:12px;padding-left:16px;font-size:12px}
.nav-dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.sidebar-footer{margin-top:auto;font-size:11px;color:#556;padding:10px}
.desk{flex:1;min-width:0;display:flex;flex-direction:column;height:100%}
.topbar{display:flex;align-items:center;gap:10px;padding:8px 12px;background:#0e1a24;border-bottom:1px solid var(--line);flex-wrap:wrap}
.sym{font-size:15px;font-weight:800;letter-spacing:.02em}
.sym small{display:block;font-size:10px;color:var(--muted);font-weight:600}
.tfs{display:flex;gap:4px;flex-wrap:wrap}
.tf{border:1px solid var(--line);background:#12202b;color:#8a96a0;font:inherit;font-size:11px;font-weight:800;padding:6px 9px;border-radius:8px;cursor:pointer}
.tf.active{background:#1a3a36;border-color:var(--bid);color:#7ee8dc}
.meta{margin-left:auto;display:flex;gap:14px;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.meta b{color:var(--txt);font-weight:700}
.exec{display:grid;grid-template-columns:1fr 88px 1fr;gap:0;background:#0d47a1}
.ex-btn{border:none;color:#fff;padding:10px 14px;cursor:pointer;text-align:left;font:inherit;transition:background .25s}
.ex-btn.sell{background:#1565c0;text-align:left}
.ex-btn.buy{background:#0d47a1;text-align:right}
.ex-btn.sell.hot{background:#e53935 !important}
.ex-btn.buy.hot{background:#2e7d32 !important}
.exec.sig-up{background:#1b5e20}
.exec.sig-down{background:#8e1b1b}
.exec.sig-up .lot{background:#14532d}
.exec.sig-down .lot{background:#7f1d1d}
.ex-btn:active{filter:brightness(1.08)}
.ex-k{font-size:10px;font-weight:800;letter-spacing:.08em;opacity:.85}
.ex-p{font-size:20px;font-weight:800;letter-spacing:-.4px;font-variant-numeric:tabular-nums}
.lot{background:#0a3d91;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;border-left:1px solid rgba(255,255,255,.12);border-right:1px solid rgba(255,255,255,.12)}
.lot input{width:56px;background:transparent;border:none;color:#fff;font-size:18px;font-weight:800;text-align:center;outline:none}
.lot-lbl{font-size:9px;opacity:.7;font-weight:700}
.lot-step{display:flex;gap:8px}
.lot-step button{width:22px;height:18px;border:none;border-radius:4px;background:rgba(255,255,255,.15);color:#fff;cursor:pointer;font-weight:800}
.chart-row{flex:1;min-height:0;display:flex}
.rail{width:96px;flex-shrink:0;background:#070e14;display:flex;flex-direction:column;border-right:1px solid var(--line)}
.rail-card{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:12px 8px;border-bottom:1px solid var(--line);position:relative;overflow:hidden;transition:background .35s}
.rail-card:last-child{border-bottom:none}
.rail-card::before{content:'';position:absolute;inset:auto 18% 10px 18%;height:2px;border-radius:2px;background:rgba(255,255,255,.06)}
.rail-tf{font-size:10px;font-weight:800;letter-spacing:.14em;color:#6d7b86}
.rail-gauge{position:relative;width:58px;height:58px}
.rail-gauge svg{width:100%;height:100%;transform:rotate(-90deg)}
.rg-bg{fill:none;stroke:#182430;stroke-width:3.2}
.rg-fg{fill:none;stroke:#546e7a;stroke-width:3.2;stroke-linecap:round;stroke-dasharray:0 100;transition:stroke-dasharray .55s ease,stroke .35s}
.rail-score{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;font-variant-numeric:tabular-nums;color:#cfd8dc}
.rail-dir{font-size:11px;font-weight:800;text-align:center;line-height:1.15;color:#8a96a0;letter-spacing:.02em}
.rail-bars{display:flex;gap:4px;height:18px;align-items:flex-end}
.rail-bars i{width:7px;border-radius:2px 2px 0 0;background:#2a3a46;height:20%;transition:height .4s,background .35s}
.rail-cd{font-size:10px;font-weight:800;color:#5d6d78;font-variant-numeric:tabular-nums}
.rail-card.lean-up{background:linear-gradient(180deg,rgba(38,166,154,.10),transparent 70%)}
.rail-card.lean-up .rg-fg{stroke:#26a69a}
.rail-card.lean-up .rail-score,.rail-card.lean-up .rail-dir{color:#7ee8dc}
.rail-card.lean-up .rail-bars i{background:#1a5c55}
.rail-card.lean-down{background:linear-gradient(180deg,rgba(239,83,80,.10),transparent 70%)}
.rail-card.lean-down .rg-fg{stroke:#ef5350}
.rail-card.lean-down .rail-score,.rail-card.lean-down .rail-dir{color:#ff8a80}
.rail-card.lean-down .rail-bars i{background:#6b2a2a}
.rail-card.up{background:linear-gradient(180deg,rgba(38,166,154,.28),rgba(38,166,154,.04));animation:railPulseUp 1.6s ease-in-out infinite}
.rail-card.up .rg-fg{stroke:#26a69a}
.rail-card.up .rail-score,.rail-card.up .rail-dir{color:#26a69a}
.rail-card.down{background:linear-gradient(180deg,rgba(239,83,80,.28),rgba(239,83,80,.04));animation:railPulseDown 1.6s ease-in-out infinite}
.rail-card.down .rg-fg{stroke:#ef5350}
.rail-card.down .rail-score,.rail-card.down .rail-dir{color:#ef5350}
.rail-card.hot .rail-gauge{filter:drop-shadow(0 0 8px currentColor)}
@keyframes railPulseUp{0%,100%{box-shadow:inset 0 0 0 0 rgba(38,166,154,0)}50%{box-shadow:inset 0 0 22px 0 rgba(38,166,154,.22)}}
@keyframes railPulseDown{0%,100%{box-shadow:inset 0 0 0 0 rgba(239,83,80,0)}50%{box-shadow:inset 0 0 22px 0 rgba(239,83,80,.22)}}
.book-pane{
  width:300px;flex-shrink:0;background:#0b1116;border-left:1px solid var(--line);
  display:flex;flex-direction:column;min-height:0;
}
.book-head{padding:12px 14px 8px;border-bottom:1px solid var(--line)}
.book-head b{display:block;font-size:13px;font-weight:800}
.book-head small{color:var(--muted);font-size:10px}
.book-tabs{display:flex;gap:14px;padding:0 14px;border-bottom:1px solid var(--line)}
.book-tab{background:none;border:none;color:#6d7b86;font:inherit;font-size:10px;font-weight:800;letter-spacing:.04em;padding:8px 0;cursor:pointer}
.book-tab.on{color:#4ea3ff;border-bottom:2px solid #4ea3ff}
body.fx-g1 .book-tabs,body.fx-bybit .book-tabs,body.fx-gps .book-tabs{display:none}
.bk-box{margin:10px 10px 6px;border:1px solid #24303a;border-radius:10px;background:#111920}
.bk-box-h{padding:8px 12px 0;font-size:10px;font-weight:800;letter-spacing:.06em;color:#8a96a0}
.bk-box .bk-row{border-bottom:none;padding:8px 12px 10px}
.bk-box .bk-empty{padding:10px 12px 12px}
.bk-sec{padding:10px 14px 4px;font-size:10px;font-weight:800;letter-spacing:.06em;color:#6d7b86}
.book-list{flex:1;overflow:auto}
.bk-row{display:flex;justify-content:space-between;gap:8px;padding:10px 14px;border-bottom:1px solid var(--line)}
.bk-sym{font-size:12px;font-weight:700}
.bk-sym.buy{color:#3d8bfd}
.bk-sym.sell{color:#ef5350}
.bk-px{font-size:11px;color:#8a96a0;margin-top:3px;font-variant-numeric:tabular-nums}
.bk-right{text-align:right}
.bk-ts{font-size:10px;color:#6d7b86;font-variant-numeric:tabular-nums}
.bk-pnl{font-size:16px;font-weight:800;margin-top:3px;font-variant-numeric:tabular-nums}
.bk-pnl.pos{color:#c8f135}
.bk-pnl.neg{color:#ef5350}
.bk-empty{padding:18px 14px;color:#6d7b86;font-size:12px}
.book-eq{padding:10px 14px;border-top:1px solid var(--line);font-size:16px;font-weight:800;text-align:center}
.book-eq > span{display:block;font-size:10px;color:var(--muted);font-weight:600}
.book-eq-row{display:flex;align-items:baseline;justify-content:center;gap:8px}
.book-eq b{font-weight:800;font-variant-numeric:tabular-nums}
.book-eq em{display:none}
.chart-wrap{flex:1;min-width:0;min-height:0;position:relative;background:#fff}
#fx-chart{width:100%;height:100%}
.hud{position:absolute;top:10px;left:12px;z-index:4;font-size:12px;font-weight:700;color:#37474f;pointer-events:none}
.hud span{color:#90a4ae;font-weight:600}
.sig{position:absolute;top:10px;right:88px;z-index:5;min-width:148px;padding:8px 12px;border-radius:10px;background:rgba(255,255,255,.94);border:1px solid #cfd8dc;box-shadow:0 2px 10px rgba(0,0,0,.08);pointer-events:none}
.sig.up{border-color:#26a69a}
.sig.down{border-color:#ef5350}
.sig-dir{font-size:14px;font-weight:800;letter-spacing:.02em;color:#546e7a}
.sig.up .sig-dir{color:#26a69a}
.sig.down .sig-dir{color:#ef5350}
.sig-meta{font-size:10px;color:#78909c;margin-top:3px;font-weight:600}
.sig-ly{font-size:10px;color:#90a4ae;margin-top:2px;font-variant-numeric:tabular-nums}
.ck-row{display:flex;justify-content:space-between;gap:8px;padding:8px 14px;border-bottom:1px solid var(--line);font-size:11px}
.ck-row b{font-size:10px;font-weight:800;letter-spacing:.02em}
.ck-row .ck-sc{font-variant-numeric:tabular-nums;font-weight:800}
.ck-row.ok .ck-sc{color:#c8f135}
.ck-row.bad .ck-sc{color:#ef5350}
.ck-why{font-size:10px;color:#6d7b86;margin-top:3px;line-height:1.35}
.ck-head{padding:10px 14px;border-bottom:1px solid var(--line);font-size:12px;font-weight:800}
.ck-head small{display:block;font-size:10px;color:#6d7b86;font-weight:600;margin-top:3px}
.cd{position:absolute;right:72px;bottom:28px;z-index:4;background:#263238;color:#fff;font-size:11px;font-weight:800;padding:3px 8px;border-radius:6px;font-variant-numeric:tabular-nums}
.toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:#1b2832;border:1px solid var(--gold);color:var(--gold);padding:8px 14px;border-radius:10px;font-size:12px;font-weight:700;display:none;z-index:20}
body.fx-public .sidebar{display:none}
body.fx-public .desk{width:100%}
body.fx-public .book-pane{display:none}
button,a,.tf,.ex-btn{touch-action:manipulation;-webkit-tap-highlight-color:transparent}
@media(max-width:800px){
  html,body{height:100%;height:100dvh;overflow:hidden}
  body{
    flex-direction:column;
    padding-top:env(safe-area-inset-top);
    padding-bottom:env(safe-area-inset-bottom);
  }
  body:not(.fx-public) .sidebar{
    display:flex;flex-direction:row;flex-wrap:nowrap;align-items:center;
    width:100%;height:auto;padding:6px 8px;gap:4px;overflow-x:auto;
    -webkit-overflow-scrolling:touch;border-right:none;border-bottom:1px solid var(--line);
  }
  body:not(.fx-public) .nav-label,
  body:not(.fx-public) .sidebar-footer{display:none}
  body:not(.fx-public) .nav-item{white-space:nowrap;padding:8px 10px;font-size:12px}
  .desk{height:100%;min-height:0}
  .topbar{display:none}
  body.fx-gps .exec{display:none}
  .exec{
    order:3;grid-template-columns:1fr 72px 1fr;flex-shrink:0;
    padding-bottom:env(safe-area-inset-bottom,0);
  }
  .ex-btn{padding:10px 10px;min-height:56px}
  .ex-p{font-size:17px}
  .lot input{width:46px;font-size:16px}
  .lot-step button{width:28px;height:24px}
  .chart-row{order:2;flex-direction:column;flex:1;min-height:0}
  .rail{
    width:100%;flex-direction:row;height:auto;flex-shrink:0;
    border-right:none;border-bottom:1px solid var(--line);
  }
  .rail-card{
    flex:1;flex-direction:row;flex-wrap:nowrap;justify-content:center;
    align-items:center;gap:6px 8px;padding:7px 8px;
    border-bottom:none;border-right:1px solid var(--line);
  }
  .rail-card:last-child{border-right:none}
  .rail-card::before{display:none}
  .rail-tf{letter-spacing:.08em}
  .rail-gauge{width:40px;height:40px;flex-shrink:0}
  .rail-score{font-size:13px}
  .rail-dir{font-size:10px;min-width:0;text-align:left}
  .rail-bars{display:none}
  .rail-cd{font-size:9px;margin-left:auto}
  .book-pane{display:none}
  body.fx-gps .book-pane{
    display:flex;width:100%;max-height:46vh;border-left:none;
    border-top:1px solid var(--line);order:4;
  }
  .chart-wrap{flex:1;min-height:0}
  .hud{top:8px;left:8px;font-size:11px;max-width:46%}
  .sig{top:8px;right:8px;min-width:0;padding:6px 8px}
  .sig-dir{font-size:12px}
  .sig-ly{display:none}
  .cd{right:10px;bottom:10px}
  .toast{bottom:76px;left:12px;right:12px;transform:none;text-align:center}
}
@media(max-width:420px){
  .meta #m-hl{display:none}
  .ex-p{font-size:15px}
  .rail-dir{max-width:72px}
}
</style>
</head>
<body id="fx-page" class="__FX_BODY_CLASS__">
<div class="sidebar">
  __FOREX_BRAND__
  <div class="nav-label">Forex</div>
  <a class="nav-item" href="/forex/home"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item" href="/forex/algoritma-islemler"><span class="nav-dot"></span>Algoritma işlemler</a>
  <a class="nav-item __FX_NAV_G1__" href="/forex/grafik"><span class="nav-dot"></span>CEM01</a>
  <a class="nav-item __FX_NAV_C2__" href="/forex/cem02"><span class="nav-dot"></span>CAPITAL</a>
  <a class="nav-item __FX_NAV_GPS__" href="/forex/gpsusdt"><span class="nav-dot"></span>GPSUSDT</a>
  <a class="nav-item" href="__FX_ISLEMLER_HREF__"><span class="nav-dot"></span>İşlemler</a>
  <div class="nav-label">Sistemler</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Poly</a>
  <a class="nav-item" href="/kripto"><span class="nav-dot"></span>Kripto</a>
  <div class="sidebar-footer">__FX_FOOTER__</div>
</div>
<div class="desk">
  <div class="topbar">
    <div class="sym">__FX_PAIR__<small>__FX_PAIR_SUB__</small></div>
    <div class="tfs" id="tfs"></div>
    <div class="meta">
      <div>Spread <b id="m-spr">—</b></div>
      <div>Gün <b id="m-hl">—</b></div>
      <div id="m-clk">—</div>
    </div>
  </div>
  <div class="exec">
    <button type="button" class="ex-btn sell" onclick="paper('sell')">
      <div class="ex-k">SAT</div>
      <div class="ex-p" id="p-bid">—</div>
    </button>
    <div class="lot">
      <div class="lot-lbl">LOT</div>
      <div class="lot-step">
        <button type="button" onclick="nudgeLot(-0.01)">−</button>
        <input id="lot" value="0.10" inputmode="decimal">
        <button type="button" onclick="nudgeLot(0.01)">+</button>
      </div>
    </div>
    <button type="button" class="ex-btn buy" onclick="paper('buy')">
      <div class="ex-k">AL</div>
      <div class="ex-p" id="p-ask">—</div>
    </button>
  </div>
  <div class="chart-row">
    <div class="rail" id="rail">
      <div class="rail-card" id="rail-5m">
        <div class="rail-tf">M5</div>
        <div class="rail-gauge">
          <svg viewBox="0 0 36 36" aria-hidden="true">
            <circle class="rg-bg" cx="18" cy="18" r="15" pathLength="100"/>
            <circle class="rg-fg" id="rail-5m-ring" cx="18" cy="18" r="15" pathLength="100"/>
          </svg>
          <div class="rail-score" id="rail-5m-score">—</div>
        </div>
        <div class="rail-dir" id="rail-5m-dir">DENGELİ</div>
        <div class="rail-bars" id="rail-5m-bars"><i></i><i></i><i></i></div>
        <div class="rail-cd" id="rail-5m-cd">—</div>
      </div>
      <div class="rail-card" id="rail-15m">
        <div class="rail-tf">M15</div>
        <div class="rail-gauge">
          <svg viewBox="0 0 36 36" aria-hidden="true">
            <circle class="rg-bg" cx="18" cy="18" r="15" pathLength="100"/>
            <circle class="rg-fg" id="rail-15m-ring" cx="18" cy="18" r="15" pathLength="100"/>
          </svg>
          <div class="rail-score" id="rail-15m-score">—</div>
        </div>
        <div class="rail-dir" id="rail-15m-dir">DENGELİ</div>
        <div class="rail-bars" id="rail-15m-bars"><i></i><i></i><i></i></div>
        <div class="rail-cd" id="rail-15m-cd">—</div>
      </div>
    </div>
    <div class="chart-wrap">
      <div class="hud" id="hud">XAUUSD, M1</div>
      <div class="sig" id="sig">
        <div class="sig-dir" id="sig-dir">NÖTR</div>
        <div class="sig-meta" id="sig-meta">confluence bekleniyor</div>
        <div class="sig-ly" id="sig-ly"></div>
      </div>
      <div class="cd" id="cd">—</div>
      <div id="fx-chart"></div>
    </div>
    <aside class="book-pane" id="book-pane">
      <div class="book-head"><b>İşlemler</b><small>__FX_BOOK_SUB__</small></div>
      <div class="book-tabs">
        <button type="button" class="book-tab on" data-btab="pos" onclick="bookTab('pos')">POZİSYONLAR</button>
        <button type="button" class="book-tab" data-btab="hist" onclick="bookTab('hist')">İŞLEMLER</button>
      </div>
      <div class="book-list" id="book-list"></div>
      <div class="book-eq"><span>bakiye</span><div class="book-eq-row"><b id="book-eq">$300.00</b><em id="book-n">0 işlem</em></div></div>
    </aside>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
const FX_ALGO='__FX_ALGO__';
const FX_PAIR='__FX_PAIR__';
const TFS = [
  ['1m','M1'],['5m','M5'],['15m','M15'],['30m','M30'],['1h','H1'],['4h','H4'],['1d','D1']
];
let _tf = '1m', _chart=null, _series=null, _bidLine=null, _askLine=null;
let _srLines=[], _last=[], _req=0, _barLeft=60, _barSec=60;
const _railLeft={};
const TZ='Europe/Istanbul';

function utcToIst(sec){
  const p=new Intl.DateTimeFormat('en-GB',{timeZone:TZ,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).formatToParts(new Date(sec*1000));
  const g=t=>parseInt(p.find(x=>x.type===t).value,10);
  return Date.UTC(g('year'),g('month')-1,g('day'),g('hour'),g('minute'),g('second'))/1000;
}
function toast(msg){
  const el=document.getElementById('toast');
  el.textContent=msg; el.style.display='block';
  clearTimeout(window._tt); window._tt=setTimeout(()=>el.style.display='none',2200);
}
function paper(side){
  const lot=document.getElementById('lot').value;
  const px=side==='buy'?document.getElementById('p-ask').textContent:document.getElementById('p-bid').textContent;
  const msg=FX_ALGO==='a2'
    ? 'Sanal '+ (side==='buy'?'AL':'SAT') +' '+lot+' lot @ '+px+' — A2 kontrol listesi açarsa cron işler'
    : FX_ALGO==='gps'
    ? 'Binance MARKET '+ (side==='buy'?'BUY':'SELL') +' GPSUSDT @ '+px+' — sinyal gelince cron açar (paper)'
    : 'Sanal '+ (side==='buy'?'AL':'SAT') +' '+lot+' lot @ '+px+' — motor henüz yok';
  toast(msg);
}
function nudgeLot(d){
  const el=document.getElementById('lot');
  let v=parseFloat(el.value||'0.10')+d;
  if(v<0.01) v=0.01; if(v>10) v=10;
  el.value=v.toFixed(2);
}
function buildTfs(){
  const box=document.getElementById('tfs');
  box.innerHTML=TFS.map(([k,l])=>'<button type="button" class="tf'+(k===_tf?' active':'')+'" data-tf="'+k+'">'+l+'</button>').join('');
  box.querySelectorAll('.tf').forEach(b=>b.onclick=()=>{_tf=b.dataset.tf; buildTfs(); loadChart();});
}
function fmt(n,dec){ return n==null?'—':Number(n).toFixed(dec!=null?dec:2); }
function pxFmt(n){ return n==null?'—':Number(n).toFixed(FX_ALGO==='gps'?5:2); }
function money(n){ return n==null?'—':Number(n).toFixed(2); }
function fmtCd(sec){
  const n=Math.max(0,sec|0);
  return String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');
}
function tick(){
  document.getElementById('m-clk').textContent=new Date().toLocaleTimeString('tr-TR',{hour12:false,timeZone:TZ});
  if(_barLeft>0) _barLeft--;
  document.getElementById('cd').textContent=fmtCd(_barLeft);
  ['5m','15m'].forEach(tf=>{
    if(_railLeft[tf]==null) return;
    if(_railLeft[tf]>0) _railLeft[tf]--;
    const el=document.getElementById(tf==='5m'?'rail-5m-cd':'rail-15m-cd');
    if(el) el.textContent=fmtCd(_railLeft[tf]);
  });
}
function applyQuote(q){
  const dec=q.dec!=null?q.dec:2;
  document.getElementById('p-bid').textContent=fmt(q.bid,dec);
  document.getElementById('p-ask').textContent=fmt(q.ask,dec);
  document.getElementById('m-spr').textContent=q.spread!=null?q.spread.toFixed(2):'—';
  if(q.day_low!=null && q.day_high!=null)
    document.getElementById('m-hl').textContent=fmt(q.day_low,dec)+' / '+fmt(q.day_high,dec);
  if(q.bar_left!=null){ _barLeft=q.bar_left; _barSec=q.bar_sec||_barSec; }
  if(_series){
    if(_bidLine) _series.removePriceLine(_bidLine);
    if(_askLine) _series.removePriceLine(_askLine);
    _bidLine=_askLine=null;
    if(q.bid!=null) _bidLine=_series.createPriceLine({price:q.bid,color:'#26a69a',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Solid,axisLabelVisible:true,title:'Bid'});
    if(q.ask!=null) _askLine=_series.createPriceLine({price:q.ask,color:'#ef5350',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Solid,axisLabelVisible:true,title:'Ask'});
  }
  if(q.mid!=null && _last.length){
    const c=Object.assign({},_last[_last.length-1]);
    c.close=Number(q.mid.toFixed(dec)); c.high=Math.max(c.high,c.close); c.low=Math.min(c.low,c.close);
    _last[_last.length-1]=c; if(_series) _series.update(c);
  }
  if(q.rail) applyRail(q.rail);
  if(q.signal) applySignal(q, true);
  if(q.book) renderBook(q.book);
  if(FX_ALGO==='bybit'){
    const f=document.querySelector('.sidebar-footer');
    if(f) f.textContent='XAUUSD · Exness · canlı kapalı';
  }
}
function ensure(){
  if(_chart) return true;
  const el=document.getElementById('fx-chart');
  if(!el||!window.LightweightCharts) return false;
  _chart=LightweightCharts.createChart(el,{
    layout:{background:{type:'solid',color:'#0b141c'},textColor:'#7d8b96'},
    grid:{vertLines:{color:'#1c2a36'},horzLines:{color:'#1c2a36'}},
    rightPriceScale:{borderColor:'#1c2a36'},
    timeScale:{borderColor:'#1c2a36',timeVisible:true,secondsVisible:false},
    crosshair:{mode:LightweightCharts.CrosshairMode.Normal},
    width:el.clientWidth, height:el.clientHeight||480,
  });
  _series=_chart.addCandlestickSeries({
    upColor:'#26a69a', downColor:'#ef5350', borderUpColor:'#26a69a',
    borderDownColor:'#ef5350', wickUpColor:'#26a69a', wickDownColor:'#ef5350',
  });
  const sizeChart=()=>{
    if(!_chart) return;
    const w=el.clientWidth, h=el.clientHeight;
    if(w>0 && h>0) _chart.applyOptions({width:w,height:h});
  };
  window.addEventListener('resize',sizeChart);
  if(window.visualViewport) window.visualViewport.addEventListener('resize',sizeChart);
  if(window.ResizeObserver) new ResizeObserver(sizeChart).observe(el);
  requestAnimationFrame(sizeChart);
  return true;
}
async function refreshQuote(){
  try{
    const r=await fetch('/poly/api/forex/spot?timeframe='+_tf+'&algo='+FX_ALGO,{cache:'no-store'});
    applyQuote(await r.json());
  }catch(e){}
}
async function loadChart(){
  const id=++_req;
  if(!ensure()) return;
  const lab=(TFS.find(x=>x[0]===_tf)||[_tf,_tf])[1];
  document.getElementById('hud').innerHTML=(FX_ALGO==='bybit'
    ? 'XAUUSD, '+lab+' <span>Exness Raw</span>'
    : FX_ALGO==='gps'
    ? FX_PAIR+', '+lab+' <span>GPS / USDT</span>'
    : 'XAUUSD, '+lab+' <span>Gold vs US Dollar</span>');
  try{
    const r=await fetch('/poly/api/forex/chart?timeframe='+_tf+'&limit=240&algo='+FX_ALGO+'&_='+Date.now(),{cache:'no-store'});
    const d=await r.json();
    if(id!==_req) return;
    applyQuote(d);
    const candles=(d.candles||[]).map(c=>({time:utcToIst(c.time),open:c.open,high:c.high,low:c.low,close:c.close}));
    _last=candles.slice();
    _series.setData(candles);
    applySignal(d);
    applyRail(d.rail||{});
    applyLevels(d.levels||{});
    _chart.timeScale().fitContent();
  }catch(e){ console.error(e); }
}
function paintExec(dir){
  dir=String(dir||'').toUpperCase();
  const sell=document.querySelector('.ex-btn.sell');
  const buy=document.querySelector('.ex-btn.buy');
  const bar=document.querySelector('.exec');
  if(!sell||!buy||!bar) return;
  sell.classList.toggle('hot', dir==='DOWN');
  buy.classList.toggle('hot', dir==='UP');
  bar.classList.toggle('sig-up', dir==='UP');
  bar.classList.toggle('sig-down', dir==='DOWN');
  sell.style.background=dir==='DOWN'?'#e53935':'';
  buy.style.background=dir==='UP'?'#2e7d32':'';
}
function applySignal(d, quoteOnly){
  const s=d.signal||{};
  const dir=s.direction||'NEUTRAL';
  paintExec(dir);
  const el=document.getElementById('sig');
  el.className='sig'+(dir==='UP'?' up':dir==='DOWN'?' down':'');
  const lab=dir==='UP'?'YÜKSELİŞ':dir==='DOWN'?'DÜŞÜŞ':'NÖTR';
  document.getElementById('sig-dir').textContent=lab;
  const conf=s.confidence!=null?Number(s.confidence).toFixed(0):'—';
  let st=s.is_stable?'kararlı':'bekliyor';
  if(s.tick_lead) st='tick';
  if(s.price_lead) st='fiyat';
  if(s.rail_confirm) st='M5/M15';
  if(s.veto) st=s.veto==='rail'?'ray veto':'ray ayrıştı';
  if(s.engine==='algo2_pending') st='algoritma bekleniyor';
  if(s.engine==='algo2'){
    st=s.allow_entry?'aç':'bekliyor';
    if(s.regime) st+=' · '+s.regime;
  }
  document.getElementById('sig-meta').textContent=
    (s.engine==='algo2' && s.score!=null)
      ? ('skor '+Number(s.score).toFixed(0)+' · '+st)
      : ('güven '+conf+' · '+st);
  const L=s.layers||{};
  document.getElementById('sig-ly').textContent=
    s.engine==='algo2'
      ? ((s.verdict||'').slice(0,72) || ('T '+(L.trend!=null?Number(L.trend).toFixed(0):'—')+'  K '+(L.momentum!=null?Number(L.momentum).toFixed(0):'—')+'  P '+(L.pattern!=null?Number(L.pattern).toFixed(0):'—')))
      : ('T '+(L.trend!=null?Number(L.trend).toFixed(0):'—')
        +'  K '+(L.momentum!=null?Number(L.momentum).toFixed(0):'—')
        +'  P '+(L.pattern!=null?Number(L.pattern).toFixed(0):'—')
        +(L.tick!=null?'  Δ '+Number(L.tick).toFixed(0):''));
  _sig=s;
  if(FX_ALGO==='a2' && _btab==='karar') renderBook(_book);
  if(quoteOnly||!_series) return;
  const marks=(d.signal_markers||[]).map(m=>({
    time:utcToIst(m.time),
    position:m.direction==='UP'?'belowBar':'aboveBar',
    color:m.direction==='UP'?'#26a69a':'#ef5350',
    shape:m.direction==='UP'?'arrowUp':'arrowDown',
    text:m.direction==='UP'?'AL':'SAT',
  }));
  _series.setMarkers(marks);
}
function clearSr(){
  if(!_series) return;
  _srLines.forEach(l=>{ try{ _series.removePriceLine(l); }catch(e){} });
  _srLines=[];
}
function applyLevels(lv){
  clearSr();
  if(!_series || !lv || lv.ok===false) return;
  const near=(a,b)=>a!=null && b!=null && Math.abs(Number(a)-Number(b))<1e-6;
  const add=(price,color,title,axis,width,style)=>{
    if(price==null) return;
    _srLines.push(_series.createPriceLine({
      price:Number(price), color:color, lineWidth:width||1,
      lineStyle:style!=null?style:LightweightCharts.LineStyle.Dotted,
      axisLabelVisible:axis!==false, title:title,
    }));
  };
  if(lv.nearest_resistance)
    add(lv.nearest_resistance.price,'rgba(248,113,113,0.95)','Direnç',true,2,LightweightCharts.LineStyle.Solid);
  if(lv.nearest_support)
    add(lv.nearest_support.price,'rgba(74,222,128,0.95)','Destek',true,2,LightweightCharts.LineStyle.Solid);
  (lv.resistance||[]).slice(0,3).forEach((x,i)=>{
    if(near(x.price, lv.nearest_resistance && lv.nearest_resistance.price)) return;
    add(x.price,'rgba(248,113,113,0.28)','D'+(i+1),false);
  });
  (lv.support||[]).slice(0,3).forEach((x,i)=>{
    if(near(x.price, lv.nearest_support && lv.nearest_support.price)) return;
    add(x.price,'rgba(74,222,128,0.28)','S'+(i+1),false);
  });
  const hud=document.getElementById('hud');
  if(hud && (lv.nearest_support || lv.nearest_resistance)){
    const bits=[];
    if(lv.nearest_support) bits.push('S '+Number(lv.nearest_support.price).toFixed(2));
    if(lv.nearest_resistance) bits.push('D '+Number(lv.nearest_resistance.price).toFixed(2));
    const base=hud.innerHTML.split(' · S ')[0].split(' · D ')[0];
    hud.innerHTML=base+' <span>· '+bits.join(' · ')+'</span>';
  }
}
function applyRail(rail){
  [['5m','rail-5m'],['15m','rail-15m']].forEach(([tf,id])=>{
    const s=rail[tf]||{};
    const dir=s.direction||'NEUTRAL';
    const lean=s.lean||(s.raw_score>4?'UP':s.raw_score<-4?'DOWN':'FLAT');
    const fill=Math.max(0,Math.min(100,Number(s.fill!=null?s.fill:(s.confidence||0)/55*100)));
    const card=document.getElementById(id);
    let cls='rail-card';
    if(dir==='UP') cls+=' up';
    else if(dir==='DOWN') cls+=' down';
    else if(lean==='UP') cls+=' lean-up';
    else if(lean==='DOWN') cls+=' lean-down';
    if(fill>=70) cls+=' hot';
    card.className=cls;
    const ring=document.getElementById(id+'-ring');
    if(ring) ring.style.strokeDasharray=fill.toFixed(1)+' '+(100-fill).toFixed(1);
    document.getElementById(id+'-score').textContent=s.confidence!=null?Number(s.confidence).toFixed(0):'—';
    let lab='DENGELİ';
    if(dir==='UP') lab=s.is_stable?'ARTACAK':'↑ YAKIN';
    else if(dir==='DOWN') lab=s.is_stable?'DÜŞECEK':'↓ YAKIN';
    else if(lean==='UP') lab=fill>=45?'↑ YAKIN':'↑ EĞİLİM';
    else if(lean==='DOWN') lab=fill>=45?'↓ YAKIN':'↓ EĞİLİM';
    document.getElementById(id+'-dir').textContent=lab;
    const L=s.layers||{};
    const bars=document.getElementById(id+'-bars');
    if(bars){
      const vals=[L.trend,L.momentum,L.pattern].map(v=>{
        const n=Math.abs(Number(v)||0);
        return Math.max(18,Math.min(100,n));
      });
      bars.querySelectorAll('i').forEach((el,i)=>{
        el.style.height=vals[i]+'%';
        const raw=[L.trend,L.momentum,L.pattern][i]||0;
        el.style.background=raw>4?'#26a69a':raw<-4?'#ef5350':'#2a3a46';
      });
    }
    if(s.bar_left!=null) _railLeft[tf]=s.bar_left;
    const cd=document.getElementById(id+'-cd');
    if(cd && _railLeft[tf]!=null) cd.textContent=fmtCd(_railLeft[tf]);
  });
}
const q=new URLSearchParams(location.search);
if(TFS.some(x=>x[0]===q.get('tf'))) _tf=q.get('tf');
buildTfs(); tick(); setInterval(tick,1000);
let _book=null, _btab='pos', _sig=null;
if(FX_ALGO==='a2'){
  const tabs=document.querySelector('.book-tabs');
  if(tabs) tabs.insertAdjacentHTML('beforeend','<button type="button" class="book-tab" data-btab="karar" onclick="bookTab(\'karar\')">KARAR</button>');
}
function bookTab(t){
  _btab=t;
  document.querySelectorAll('.book-tab').forEach(x=>x.classList.toggle('on', x.dataset.btab===t));
  renderBook(_book);
}
function clockAt(s){
  const m=String(s||'').match(/(\d{2}):(\d{2})/);
  return m?m[1]+':'+m[2]:'';
}
function holdDur(a,z){
  const parse=s=>{
    const m=String(s||'').match(/(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2}):(\d{2})/);
    return m?new Date(+m[1],+m[2]-1,+m[3],+m[4],+m[5],+m[6]):null;
  };
  const A=parse(a), Z=parse(z);
  if(!A||!Z) return '';
  let s=Math.max(0,Math.round((Z-A)/1000));
  const h=Math.floor(s/3600); s%=3600;
  const m=Math.floor(s/60); const sec=s%60;
  if(h) return h+' sa '+m+' dk';
  if(m) return m+' dk'+(sec?(' '+sec+' sn'):'');
  return sec+' sn';
}
function rejText(r){
  const yon=r.side==='buy'?'AL':'SAT';
  if(r.reason==='bekleme') return yon+' sinyali var — kapanış sonrası bekleme '+r.wait+' sn.';
  if(r.reason==='stop_uzak') return yon+' sinyali var — stop çok uzak (risk $'+fmt(r.risk_usd)+'), açılmadı.';
  if(r.reason==='rr_dusuk') return yon+' sinyali var — ödül/risk '+fmt(r.rr)+' (en az 1.5), açılmadı.';
  if(r.reason==='seviye_yok') return yon+' sinyali var — fiyat destek/direnç arasında değil, açılmadı.';
  return '';
}
function renderBook(b){
  _book=b||_book;
  const pane=document.getElementById('book-pane');
  if(!pane || !b) return;
  const eq=document.getElementById('book-eq');
  if(eq){
    const px=b.equity!=null?b.equity:b.balance;
    const base=b.init_balance!=null?b.init_balance:300;
    const broke=(b.book==='bybit') && (b.halted || px<10);
    eq.textContent=broke?'para bitti':('$'+fmt(px));
    eq.classList.toggle('up', !broke && px>base);
    eq.classList.toggle('dn', broke || px<base);
  }
  const nEl=document.getElementById('book-n');
  if(nEl){
    const n=b.trade_count!=null?b.trade_count:((b.history||[]).length+(b.open_count||0));
    nEl.textContent=n+' işlem';
  }
  const sub=pane.querySelector('.book-head small');
  if(sub && b.book==='bybit' && b.costs){
    sub.textContent='XAUUSD · $100 × '+b.leverage+'x · Exness Raw kom $'+fmt(b.costs.commission_open)+' + $'+fmt(b.costs.commission_close);
  }
  if(sub && (b.book==='gps' || FX_ALGO==='gps') && b.costs){
    const av=b.available!=null?(' · serbest $'+fmt(b.available)): '';
    sub.textContent='Isolated $100×'+(b.leverage||20)+'x · kasa $'+fmt(b.init_balance||500)+av+' · taker %0.05 ($'+fmt(b.costs.commission_open)+' aç / $'+fmt(b.costs.commission_close)+' kapa)';
  }
  const el=document.getElementById('book-list');
  if(!el) return;
  const row=(side,vol,a,z,ts,pnl,open,extra)=>{
    const sell=side==='sell';
    const volTxt=FX_ALGO==='gps'?Math.round(Number(vol)).toLocaleString('tr-TR'):fmt(vol);
    const px=FX_ALGO==='gps'?pxFmt:fmt;
    return '<div class="bk-row"><div><div class="bk-sym '+(sell?'sell':'buy')+'">'+FX_PAIR+', '+(sell?'sell':'buy')+' '+volTxt+'</div>'
      +'<div class="bk-px">'+px(a)+(z!=null?' → '+px(z):'')+'</div>'
      +(extra?'<div class="bk-px" style="opacity:.65">'+extra+'</div>':'')+'</div>'
      +'<div class="bk-right"><div class="bk-ts">'+ts+(open?' · açık':'')+'</div>'
      +'<div class="bk-pnl '+(pnl>=0?'pos':'neg')+'">'+(pnl==null?'—':(FX_ALGO==='gps'?money(pnl):fmt(pnl)))+'</div></div></div>';
  };
  const plan=p=>{
    const bits=[];
    const px=FX_ALGO==='gps'?pxFmt:fmt;
    if(p.stop!=null) bits.push((p.lock_stage?'kilit ':'SL ')+px(p.stop));
    if(p.target!=null) bits.push('TP '+px(p.target));
    if(FX_ALGO==='gps'){
      if(p.liq_price) bits.push('liq '+px(p.liq_price));
      if(p.roe!=null) bits.push('ROE '+money(p.roe)+'%');
      if(p.commission_open!=null) bits.push('kom $'+money(p.commission_open));
      return bits.join(' · ');
    }
    if(p.progress!=null) bits.push('%'+fmt(p.progress));
    if(p.commission_open!=null) bits.push('kom aç $'+fmt(p.commission_open));
    else if(p.commission) bits.push('kom $'+fmt(p.commission));
    if(p.swap) bits.push('swap $'+fmt(p.swap));
    return bits.join(' · ');
  };
  const cost=t=>{
    const bits=[];
    if(t.commission_open!=null || t.commission_close!=null)
      bits.push('kom aç $'+fmt(t.commission_open)+' + kapa $'+fmt(t.commission_close));
    else if(t.commission) bits.push('kom $'+fmt(t.commission));
    if(t.swap) bits.push('swap $'+fmt(t.swap));
    return bits.join(' · ');
  };
  const posBlock=()=>{
    const ps=b.positions||(b.position?[b.position]:[]);
    let inner=ps.length?ps.map(p=>row(p.side,p.volume,p.entry,p.mark,clockAt(p.open_time)||p.open_time||'',p.float_net!=null?p.float_net:p.float_pnl,true,plan(p))).join(''):'<div class="bk-empty">Açık pozisyon yok.</div>';
    const rj=b.last_reject;
    if(rj) inner+='<div class="bk-empty" style="text-align:left">'+rejText(rj)+'</div>';
    return inner;
  };
  const histBlock=()=>{
    const h=b.history||[];
    return h.length?h.map(t=>{
      const sell=t.side==='sell';
      const dur=holdDur(t.open_time,t.close_time);
      const hh=clockAt(t.open_time);
      const extra=[hh?('aç '+hh):'', cost(t), dur?('süre '+dur):''].filter(Boolean).join(' · ');
      const volTxt=FX_ALGO==='gps'?Math.round(Number(t.volume)).toLocaleString('tr-TR'):fmt(t.volume);
      const px=FX_ALGO==='gps'?pxFmt:fmt;
      return '<div class="bk-row"><div><div class="bk-sym '+(sell?'sell':'buy')+'">'+FX_PAIR+', '+(sell?'sell':'buy')+' '+volTxt+'</div>'
        +'<div class="bk-px">'+px(t.entry)+(t.exit!=null?' → '+px(t.exit):'')+'</div>'
        +(extra?'<div class="bk-px" style="opacity:.65">'+extra+'</div>':'')+'</div>'
        +'<div class="bk-right"><div class="bk-pnl '+(t.pnl>=0?'pos':'neg')+'">'+(t.pnl==null?'—':(FX_ALGO==='gps'?money(t.pnl):fmt(t.pnl)))+'</div>'
        +(hh?'<div class="bk-ts">'+hh+'</div>':(dur?'<div class="bk-ts">'+dur+'</div>':''))+'</div></div>';
    }).join(''):'<div class="bk-empty">Kapanmış işlem yok.</div>';
  };
  if(FX_ALGO!=='a2'){
    el.innerHTML='<div class="bk-box"><div class="bk-box-h">POZİSYONLAR</div>'+posBlock()+'</div>'
      +'<div class="bk-sec">İŞLEMLER</div>'+histBlock();
    return;
  }
  if(_btab==='karar'){
    const s=_sig||{};
    const rows=s.checklist||[];
    let html='<div class="ck-head">skor '+(s.score!=null?Number(s.score).toFixed(0):'—')
      +(s.allow_entry?' · AÇ':' · BEKLE')
      +'<small>'+(s.verdict||'kontrol listesi bekleniyor')+'</small></div>';
    html+=rows.map(it=>{
      const ok=it.ok?'ok':'bad';
      return '<div class="ck-row '+ok+'"><div><b>'+it.id+'. '+it.name+'</b>'
        +'<div class="ck-why">'+(it.reason||'')+(it.vote&&it.vote!=='NEUTRAL'?' · '+it.vote:'')+'</div></div>'
        +'<div class="ck-sc">'+(it.score!=null?Number(it.score).toFixed(0):'—')+'</div></div>';
    }).join('');
    el.innerHTML=html||'<div class="bk-empty">Karar henüz yok.</div>';
    return;
  }
  if(_btab==='pos'){
    el.innerHTML=posBlock();
  }else{
    el.innerHTML=histBlock();
  }
}
async function loadBook(){
  try{
    const r=await fetch('/poly/api/forex/book?algo='+FX_ALGO,{cache:'no-store'});
    if(r.ok) renderBook(await r.json());
  }catch(e){}
}
loadChart(); refreshQuote(); loadBook();
setInterval(loadChart, 15000);
setInterval(refreshQuote, 2000);
setInterval(loadBook, 4000);
</script>
</body>
</html>
"""


def _chart_page(algo: str) -> str:
    g1 = "active" if algo == "g1" else ""
    bybit = "active" if algo == "bybit" else ""
    gps = "active" if algo == "gps" else ""
    a2 = "active" if algo == "a2" else ""
    if algo == "bybit":
        title = "XAUUSD — EXNESS"
        pair, sub, book, foot = "XAUUSD", "Exness Raw", "XAUUSD · $100 × 500x · kom $0.35", "XAUUSD · Exness"
        body = "fx-bybit"
    elif algo == "gps":
        title = "GPSUSDT — Binance"
        pair, sub, book, foot = "GPSUSDT", "Binance Isolated · sanal $500", "GPSUSDT · Isolated $100 × 20x · taker %0.05", "GPSUSDT · Binance $500"
        body = "fx-gps"
    elif algo == "a2":
        title = "XAUUSD — Algoritma 2"
        pair, sub, book, foot = "XAUUSD", "Altın / Dolar", "XAUUSD · $100 × 500x", "XAUUSD · sanal"
        body = "fx-a2"
    else:
        title = "XAUUSD — CEM01"
        pair, sub, book, foot = "XAUUSD", "Altın / Dolar", "XAUUSD · $100 × 500x", "XAUUSD · sanal"
        body = "fx-g1"
    return (
        FOREX_CHART_TMPL
        .replace("__FX_TITLE__", title)
        .replace("__FX_NAV_G1__", g1)
        .replace("__FX_NAV_C2__", "")
        .replace("__FX_NAV_BYBIT__", bybit)
        .replace("__FX_NAV_GPS__", gps)
        .replace("__FX_NAV_A2__", a2)
        .replace("__FX_ALGO__", algo)
        .replace("__FX_PAIR__", pair)
        .replace("__FX_PAIR_SUB__", sub)
        .replace("__FX_BOOK_SUB__", book)
        .replace("__FX_FOOTER__", foot)
        .replace("__FX_BODY_CLASS__", body)
        .replace("__FX_ISLEMLER_HREF__", "/forex/gpsusdt/islemler" if algo == "gps" else "/forex/islemler")
    )


FOREX_GRAFIK_HTML = _chart_page("g1")
FOREX_CEMBYBIT_HTML = _chart_page("bybit")
FOREX_ALGO2_HTML = _chart_page("a2")
FOREX_GPSUSDT_HTML = _chart_page("gps")
FOREX_CEM02_HTML = (
    FOREX_CHART_TMPL
    .replace("__FX_TITLE__", "XAUUSD — CEM01")
    .replace("__FX_NAV_G1__", "")
    .replace("__FX_NAV_C2__", "active")
    .replace("__FX_NAV_BYBIT__", "")
    .replace("__FX_NAV_GPS__", "")
    .replace("__FX_NAV_A2__", "")
    .replace("__FX_ALGO__", "g1")
    .replace("__FX_PAIR__", "XAUUSD")
    .replace("__FX_PAIR_SUB__", "Altın / Dolar")
    .replace("__FX_BOOK_SUB__", "XAUUSD · Capital")
    .replace("__FX_FOOTER__", "XAUUSD · Capital")
    .replace("__FX_BODY_CLASS__", "fx-g1")
    .replace("__FX_ISLEMLER_HREF__", "/forex/cem02/islemler")
    .replace("/poly/api/forex/spot", "/poly/api/forex/cem02/spot")
    .replace("/poly/api/forex/chart", "/poly/api/forex/cem02/chart")
    .replace("/poly/api/forex/book", "/poly/api/forex/cem02/book")
)

FOREX_ISLEMLER_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>İşlemler — Forex</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%230d1b2a'/><text x='50%25' y='54%25' font-size='16' text-anchor='middle' dominant-baseline='central' fill='%23d4af37' font-family='Arial' font-weight='bold'>F</text></svg>">
<style>
:root{
  --bg:#0b0e12; --card:#12171d; --line:#1e262e;
  --txt:#e8eef4; --muted:#7d8b96; --gold:#d4af37;
  --buy:#3d8bfd; --sell:#ef5350; --up:#c8f135;
}
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;display:flex;color:var(--txt);font-family:'Sora',system-ui,sans-serif;background:var(--bg)}
.sidebar{
  width:220px;background:#0e1318;padding:24px 16px;display:flex;flex-direction:column;gap:4px;flex-shrink:0;
  border-right:1px solid var(--line);
}
.nav-label{font-size:10px;color:#556;text-transform:uppercase;letter-spacing:1px;margin:16px 0 6px 12px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;color:#888;text-decoration:none;font-size:13px;font-weight:600}
.nav-item.active{background:rgba(212,175,55,.12);color:var(--gold)}
.nav-item.nav-sub{margin-left:14px;padding-left:14px;font-size:12px}
.nav-dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.sidebar-footer{margin-top:auto;font-size:11px;color:#556;padding:12px}
.desk{flex:1;min-width:0;display:flex;flex-direction:column;min-height:100vh}
.head{padding:16px 18px 8px}
.head h1{font-size:22px;font-weight:800}
.head small{display:block;color:var(--muted);font-size:12px;margin-top:4px}
.tabs{display:flex;gap:18px;padding:0 18px;border-bottom:1px solid var(--line)}
.tab{background:none;border:none;color:var(--muted);font:inherit;font-size:12px;font-weight:800;letter-spacing:.04em;padding:10px 0;cursor:pointer}
.tab.on{color:#4ea3ff;border-bottom:2px solid #4ea3ff}
.list{flex:1;overflow:auto}
.row{display:flex;justify-content:space-between;gap:12px;padding:12px 18px;border-bottom:1px solid var(--line)}
.sym{font-size:14px;font-weight:700}
.sym.buy{color:var(--buy)}
.sym.sell{color:var(--sell)}
.px{font-size:12px;color:#9aa8b3;margin-top:4px;font-variant-numeric:tabular-nums}
.right{text-align:right}
.ts{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.pnl{font-size:18px;font-weight:800;margin-top:4px;font-variant-numeric:tabular-nums}
.pnl.pos{color:var(--up)}
.pnl.neg{color:var(--sell)}
.empty{padding:28px 18px;color:var(--muted);font-size:13px}
.eq{
  margin:12px 16px 16px;padding:10px 16px;border-radius:999px;background:#1a2330;
  display:flex;align-items:center;justify-content:center;gap:8px;font-weight:800;font-size:18px;
}
.eq span{font-size:12px;color:var(--muted);font-weight:600}
@media(max-width:800px){
  body{flex-direction:column}
  .sidebar{width:100%;height:auto;flex-direction:row;flex-wrap:wrap;padding:10px}
  .nav-label,.sidebar-footer{display:none}
}
</style>
</head>
<body id="fx-page">
<div class="sidebar">
  __FOREX_BRAND__
  <div class="nav-label">Forex</div>
  <a class="nav-item" href="/forex/home"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item" href="/forex/algoritma-islemler"><span class="nav-dot"></span>Algoritma işlemler</a>
  <a class="nav-item" href="/forex/grafik"><span class="nav-dot"></span>CEM01</a>
  <a class="nav-item" href="/forex/cem02"><span class="nav-dot"></span>CAPITAL</a>
  <a class="nav-item" href="/forex/gpsusdt"><span class="nav-dot"></span>GPSUSDT</a>
  <a class="nav-item active" href="/forex/islemler"><span class="nav-dot"></span>İşlemler</a>
  <div class="nav-label">Sistemler</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Poly</a>
  <a class="nav-item" href="/kripto"><span class="nav-dot"></span>Kripto</a>
  <div class="sidebar-footer">XAUUSD · $100×500x</div>
</div>
<div class="desk">
  <div class="head">
    <h1>Geçmiş</h1>
    <small>XAUUSD · sanal $100 × 500x</small>
  </div>
  <div class="tabs">
    <button type="button" class="tab on" data-tab="pos" onclick="showTab('pos')">POZİSYONLAR</button>
    <button type="button" class="tab" data-tab="hist" onclick="showTab('hist')">İŞLEMLER</button>
  </div>
  <div class="list" id="list"></div>
  <div class="eq"><span>bakiye</span> <b id="eq">$300.00</b></div>
</div>
<script>
let _tab='pos', _book=null;
function fmt(n){ return n==null?'—':Number(n).toFixed(2); }
function clockAt(s){
  const m=String(s||'').match(/(\d{2}):(\d{2})/);
  return m?m[1]+':'+m[2]:'';
}
function holdDur(a,z){
  const parse=s=>{
    const m=String(s||'').match(/(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2}):(\d{2})/);
    return m?new Date(+m[1],+m[2]-1,+m[3],+m[4],+m[5],+m[6]):null;
  };
  const A=parse(a), Z=parse(z);
  if(!A||!Z) return '';
  let s=Math.max(0,Math.round((Z-A)/1000));
  const h=Math.floor(s/3600); s%=3600;
  const m=Math.floor(s/60); const sec=s%60;
  if(h) return h+' sa '+m+' dk';
  if(m) return m+' dk'+(sec?(' '+sec+' sn'):'');
  return sec+' sn';
}
function rowClosed(t){
  const sell=t.side==='sell';
  const dur=holdDur(t.open_time,t.close_time);
  const hh=clockAt(t.open_time);
  return '<div class="row">'
    +'<div><div class="sym '+(sell?'sell':'buy')+'">XAUUSD, '+(sell?'sell':'buy')+' '+fmt(t.volume)+'</div>'
    +'<div class="px">'+fmt(t.entry)+' → '+fmt(t.exit)+(t.reason?' · '+t.reason:'')+'</div>'
    +'<div class="px" style="opacity:.65">'+[hh?('aç '+hh):'',t.commission?'kom $'+fmt(t.commission):'',t.swap?'swap $'+fmt(t.swap):'',dur?('süre '+dur):''].filter(Boolean).join(' · ')+'</div></div>'
    +'<div class="right"><div class="pnl '+(t.pnl>=0?'pos':'neg')+'">'+fmt(t.pnl)+'</div>'
    +(hh?'<div class="ts">'+hh+'</div>':(dur?'<div class="ts">'+dur+'</div>':''))+'</div></div>';
}
function rowOpen(p){
  const sell=p.side==='sell';
  const pnl=p.float_pnl;
  return '<div class="row">'
    +'<div><div class="sym '+(sell?'sell':'buy')+'">XAUUSD, '+(sell?'sell':'buy')+' '+fmt(p.volume)+'</div>'
    +'<div class="px">'+fmt(p.entry)+(p.mark!=null?' → '+fmt(p.mark):'')+'</div>'
    +'<div class="px" style="opacity:.65">'+[p.stop!=null?(p.lock_stage?'kilit ':'SL ')+fmt(p.stop):'',p.target!=null?'TP '+fmt(p.target):'',p.progress!=null?'%'+fmt(p.progress):'',p.commission?'kom $'+fmt(p.commission):'',p.swap?'swap $'+fmt(p.swap):''].filter(Boolean).join(' · ')+'</div></div>'
    +'<div class="right"><div class="ts">'+(p.open_time||'')+' · açık</div>'
    +'<div class="pnl '+((p.float_net!=null?p.float_net:pnl)>=0?'pos':'neg')+'">'+fmt(p.float_net!=null?p.float_net:pnl)+'</div></div></div>';
}
function render(){
  const el=document.getElementById('list');
  const b=_book||{};
  document.getElementById('eq').textContent='$'+fmt(b.equity!=null?b.equity:b.balance);
  if(_tab==='pos'){
    const ps=b.positions||(b.position?[b.position]:[]);
    let html=ps.length?ps.map(rowOpen).join(''):'<div class="empty">Açık pozisyon yok.</div>';
    const r=b.last_reject;
    if(r){
      const yon=r.side==='buy'?'AL':'SAT';
      const msg={bekleme:'kapanış sonrası bekleme '+r.wait+' sn',stop_uzak:'stop çok uzak (risk $'+fmt(r.risk_usd)+')',rr_dusuk:'ödül/risk '+fmt(r.rr)+' (en az 1.5)',seviye_yok:'fiyat destek/direnç arasında değil'}[r.reason];
      if(msg) html+='<div class="empty" style="text-align:left">'+yon+' sinyali var — '+msg+', açılmadı.</div>';
    }
    el.innerHTML=html;
  }else{
    const h=b.history||[];
    el.innerHTML=h.length?h.map(rowClosed).join(''):'<div class="empty">Kapanmış işlem yok. Grafikte AL/SAT yanınca burada birikir.</div>';
  }
}
function showTab(t){
  _tab=t;
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on', x.dataset.tab===t));
  render();
}
async function load(){
  try{
    const r=await fetch('/poly/api/forex/book',{cache:'no-store'});
    if(r.ok) _book=await r.json();
  }catch(e){}
  render();
}
load(); setInterval(load, 4000);
</script>
</body>
</html>
"""

FOREX_CEM02_ISLEMLER_HTML = (
    FOREX_ISLEMLER_HTML
    .replace('href="/forex/islemler"', 'href="/forex/cem02/islemler"')
    .replace("/poly/api/forex/book", "/poly/api/forex/cem02/book")
)

FOREX_GPS_ISLEMLER_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>İşlemler — GPSUSDT</title>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0b0e12; --card:#12171d; --line:#1e262e;
  --txt:#e8eef4; --muted:#7d8b96; --gold:#d4af37;
  --buy:#3d8bfd; --sell:#ef5350; --up:#c8f135;
}
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;display:flex;color:var(--txt);font-family:'Sora',system-ui,sans-serif;background:var(--bg)}
.sidebar{
  width:220px;background:#0e1318;padding:24px 16px;display:flex;flex-direction:column;gap:4px;flex-shrink:0;
  border-right:1px solid var(--line);
}
.nav-label{font-size:10px;color:#556;text-transform:uppercase;letter-spacing:1px;margin:16px 0 6px 12px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;color:#888;text-decoration:none;font-size:13px;font-weight:600}
.nav-item.active{background:rgba(212,175,55,.12);color:var(--gold)}
.nav-item.nav-sub{margin-left:14px;padding-left:14px;font-size:12px}
.nav-dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.sidebar-footer{margin-top:auto;font-size:11px;color:#556;padding:12px}
.desk{flex:1;min-width:0;display:flex;flex-direction:column;min-height:100vh}
.head{padding:16px 18px 8px}
.head h1{font-size:22px;font-weight:800}
.head small{display:block;color:var(--muted);font-size:12px;margin-top:4px}
.box{margin:10px 16px 8px;border:1px solid #24303a;border-radius:10px;background:#111920}
.box-h{padding:10px 14px 0;font-size:10px;font-weight:800;letter-spacing:.06em;color:#8a96a0}
.sec{padding:10px 18px 4px;font-size:10px;font-weight:800;letter-spacing:.06em;color:#6d7b86}
.list{flex:1;overflow:auto}
.row{display:flex;justify-content:space-between;gap:12px;padding:12px 18px;border-bottom:1px solid var(--line)}
.box .row{border-bottom:none;padding:10px 14px 12px}
.sym{font-size:14px;font-weight:700}
.sym.buy{color:var(--buy)}
.sym.sell{color:var(--sell)}
.px{font-size:12px;color:#9aa8b3;margin-top:4px;font-variant-numeric:tabular-nums}
.right{text-align:right}
.ts{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.pnl{font-size:18px;font-weight:800;margin-top:4px;font-variant-numeric:tabular-nums}
.pnl.pos{color:var(--up)}
.pnl.neg{color:var(--sell)}
.empty{padding:20px 18px;color:var(--muted);font-size:13px}
.eq{
  margin:12px 16px 16px;padding:10px 16px;border-radius:999px;background:#1a2330;
  display:flex;align-items:center;justify-content:center;gap:8px;font-weight:800;font-size:18px;
}
.eq span{font-size:12px;color:var(--muted);font-weight:600}
.foot{padding:0 18px 16px;font-size:11px;color:var(--muted);text-align:center}
@media(max-width:800px){
  body{flex-direction:column}
  .sidebar{width:100%;height:auto;flex-direction:row;flex-wrap:wrap;padding:10px}
  .nav-label,.sidebar-footer{display:none}
}
</style>
</head>
<body id="fx-page">
<div class="sidebar">
  __FOREX_BRAND__
  <div class="nav-label">Forex</div>
  <a class="nav-item" href="/forex/home"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item" href="/forex/algoritma-islemler"><span class="nav-dot"></span>Algoritma işlemler</a>
  <a class="nav-item" href="/forex/grafik"><span class="nav-dot"></span>CEM01</a>
  <a class="nav-item" href="/forex/cem02"><span class="nav-dot"></span>CAPITAL</a>
  <a class="nav-item" href="/forex/gpsusdt"><span class="nav-dot"></span>GPSUSDT</a>
  <a class="nav-item active" href="/forex/gpsusdt/islemler"><span class="nav-dot"></span>İşlemler</a>
  <div class="nav-label">Sistemler</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Poly</a>
  <a class="nav-item" href="/kripto"><span class="nav-dot"></span>Kripto</a>
  <div class="sidebar-footer">GPSUSDT · Binance $500</div>
</div>
<div class="desk">
  <div class="head">
    <h1>İşlemler</h1>
    <small>GPSUSDT · Isolated $100 × 20x · kasa $500</small>
  </div>
  <div class="box">
    <div class="box-h">POZİSYONLAR</div>
    <div id="pos"></div>
  </div>
  <div class="sec">İŞLEMLER</div>
  <div class="list" id="hist"></div>
  <div class="eq"><span>bakiye</span> <b id="eq">$500.00</b></div>
  <div class="foot">Binance USDT-M sanal · taker %0.05 · borsaya emir gitmez</div>
</div>
<script>
function money(n){ return n==null?'—':Number(n).toFixed(2); }
function px(n){ return n==null?'—':Number(n).toFixed(5); }
function qty(n){ return n==null?'—':Math.round(Number(n)).toLocaleString('tr-TR'); }
function clockAt(s){
  const m=String(s||'').match(/(\d{2}):(\d{2})/);
  return m?m[1]+':'+m[2]:'';
}
function holdDur(a,z){
  const parse=s=>{
    const m=String(s||'').match(/(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2}):(\d{2})/);
    return m?new Date(+m[1],+m[2]-1,+m[3],+m[4],+m[5],+m[6]):null;
  };
  const A=parse(a), Z=parse(z);
  if(!A||!Z) return '';
  let s=Math.max(0,Math.round((Z-A)/1000));
  const h=Math.floor(s/3600); s%=3600;
  const m=Math.floor(s/60); const sec=s%60;
  if(h) return h+' sa '+m+' dk';
  if(m) return m+' dk';
  return sec+' sn';
}
function rowOpen(p){
  const sell=p.side==='sell';
  const pnl=p.float_net!=null?p.float_net:p.float_pnl;
  const extra=[
    p.stop!=null?(p.lock_stage?'kilit ':'SL ')+px(p.stop):'',
    p.target!=null?'TP '+px(p.target):'',
    p.commission_open!=null?'kom aç $'+money(p.commission_open):'',
  ].filter(Boolean).join(' · ');
  return '<div class="row"><div><div class="sym '+(sell?'sell':'buy')+'">GPSUSDT, '+(sell?'sell':'buy')+' '+qty(p.qty||p.volume)+'</div>'
    +'<div class="px">'+px(p.entry)+(p.mark!=null?' → '+px(p.mark):'')+'</div>'
    +(extra?'<div class="px" style="opacity:.65">'+extra+'</div>':'')+'</div>'
    +'<div class="right"><div class="ts">'+clockAt(p.open_time)+' · açık</div>'
    +'<div class="pnl '+(pnl>=0?'pos':'neg')+'">'+money(pnl)+'</div></div></div>';
}
function rowClosed(t){
  const sell=t.side==='sell';
  const dur=holdDur(t.open_time,t.close_time);
  const hh=clockAt(t.open_time);
  const extra=[hh?('aç '+hh):'','kom aç $'+money(t.commission_open)+' + kapa $'+money(t.commission_close),dur?('süre '+dur):''].filter(Boolean).join(' · ');
  return '<div class="row"><div><div class="sym '+(sell?'sell':'buy')+'">GPSUSDT, '+(sell?'sell':'buy')+' '+qty(t.volume)+'</div>'
    +'<div class="px">'+px(t.entry)+' → '+px(t.exit)+'</div>'
    +(extra?'<div class="px" style="opacity:.65">'+extra+'</div>':'')+'</div>'
    +'<div class="right"><div class="pnl '+(t.pnl>=0?'pos':'neg')+'">'+money(t.pnl)+'</div>'
    +(hh?'<div class="ts">'+clockAt(t.close_time||t.open_time)+'</div>':'')+'</div></div>';
}
function render(b){
  document.getElementById('eq').textContent='$'+money(b.equity!=null?b.equity:b.balance);
  const ps=b.positions||(b.position?[b.position]:[]);
  let posHtml=ps.length?ps.map(rowOpen).join(''):'<div class="empty">Açık pozisyon yok.</div>';
  const r=b.last_reject;
  if(r){
    const yon=r.side==='buy'?'AL':'SAT';
    const msg={bekleme:'kapanış sonrası bekleme',stop_uzak:'stop çok uzak',rr_dusuk:'ödül/risk düşük',seviye_yok:'plan yok'}[r.reason]||r.reason||'';
    if(msg) posHtml+='<div class="empty" style="text-align:left">'+yon+' sinyali var — '+msg+', açılmadı.</div>';
  }
  document.getElementById('pos').innerHTML=posHtml;
  const h=b.history||[];
  document.getElementById('hist').innerHTML=h.length?h.map(rowClosed).join(''):'<div class="empty">Kapanmış işlem yok.</div>';
}
async function load(){
  try{
    const r=await fetch('/poly/api/forex/book?algo=gps',{cache:'no-store'});
    if(r.ok) render(await r.json());
  }catch(e){}
}
load(); setInterval(load, 4000);
</script>
</body>
</html>
"""

FOREX_FX_ALGOS_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Algoritma işlemler — Forex XAUUSD</title>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0b0e12; --card:#12171d; --card2:#161d24; --line:#1e262e;
  --txt:#e8eef4; --muted:#7d8b96; --gold:#d4af37;
  --green:#39FF8E; --red:#ef5350;
}
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;display:flex;color:var(--txt);font-family:'Sora',system-ui,sans-serif;background:var(--bg)}
.sidebar{
  width:220px;background:#0e1318;padding:24px 16px;display:flex;flex-direction:column;gap:4px;flex-shrink:0;
  border-right:1px solid var(--line);
}
.nav-label{font-size:10px;color:#556;text-transform:uppercase;letter-spacing:1px;margin:16px 0 6px 12px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;color:#888;text-decoration:none;font-size:13px;font-weight:600}
.nav-item.active{background:rgba(212,175,55,.12);color:var(--gold)}
.nav-item.nav-sub{margin-left:14px;padding-left:14px;font-size:12px}
.nav-dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.sidebar-footer{margin-top:auto;font-size:11px;color:#556;padding:12px}
.main{flex:1;min-width:0;padding:22px 24px 40px}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:18px}
.page-title{font-size:22px;font-weight:800}
.page-sub{font-size:12px;color:var(--muted);margin-top:4px}
.chip{background:#1a2330;border-radius:999px;padding:8px 14px;font-size:12px;font-weight:700;white-space:nowrap}
.section-title{font-size:11px;font-weight:800;letter-spacing:.06em;color:#8a96a0;margin-bottom:10px;text-transform:uppercase}
.book-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.book-card{
  display:block;background:var(--card);border:1px solid var(--line);border-radius:16px;
  padding:14px 16px;text-decoration:none;color:inherit;
}
.book-card:hover{border-color:rgba(212,175,55,.35)}
.bt{font-size:14px;font-weight:800}
.bs{font-size:11px;color:var(--muted);margin-top:3px}
.br{display:flex;justify-content:space-between;margin-top:10px;font-size:12px;font-weight:700}
.br b{font-size:16px}
.pos{color:var(--green)}.neg{color:var(--red)}
.book-opens{font-size:11px;color:var(--muted);margin-top:8px}
.empty{color:#556;font-size:13px;padding:16px 0}
.detail-back{display:inline-block;margin-bottom:8px;font-size:12px;font-weight:700;color:var(--gold);text-decoration:none}
.positions{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.pos-card{background:var(--card2);border:1px solid var(--line);border-radius:16px;padding:14px 16px}
.pos-top{display:flex;justify-content:space-between;align-items:center}
.pos-name{font-size:16px;font-weight:800}
.pos-dir{font-size:11px;font-weight:800;padding:3px 8px;border-radius:8px}
.pos-dir.up{background:rgba(200,241,53,.12);color:var(--green)}
.pos-dir.down{background:rgba(239,83,80,.12);color:var(--red)}
.pos-current{font-size:22px;font-weight:800;margin:8px 0 2px}
.pos-entry{font-size:11px;color:var(--muted);margin-top:4px}
.hist-row{
  display:grid;grid-template-columns:72px 56px 1fr auto;gap:10px;align-items:center;
  padding:10px 0;border-bottom:1px solid var(--line);font-size:12px;
}
.hist-time{color:var(--muted);font-weight:600}
.hist-dir{font-size:10px;font-weight:800;padding:2px 6px;border-radius:6px;text-align:center}
.hist-dir.up{background:rgba(200,241,53,.12);color:var(--green)}
.hist-dir.down{background:rgba(239,83,80,.12);color:var(--red)}
.hist-meta{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hist-pnl{font-weight:800;text-align:right}
@media(max-width:800px){
  body{flex-direction:column}
  .sidebar{width:100%;height:auto;flex-direction:row;flex-wrap:wrap;padding:10px}
  .nav-label,.sidebar-footer{display:none}
  .main{padding:16px}
}
</style>
</head>
<body id="fx-page">
<div class="sidebar">
  __FOREX_BRAND__
  <div class="nav-label">Forex</div>
  <a class="nav-item" href="/forex/home"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item active" href="/forex/algoritma-islemler"><span class="nav-dot"></span>Algoritma işlemler</a>
  <a class="nav-item" href="/forex/grafik"><span class="nav-dot"></span>CEM01</a>
  <a class="nav-item" href="/forex/cem02"><span class="nav-dot"></span>CAPITAL</a>
  <a class="nav-item" href="/forex/gpsusdt"><span class="nav-dot"></span>GPSUSDT</a>
  <a class="nav-item" href="/forex/islemler"><span class="nav-dot"></span>İşlemler</a>
  <div class="nav-label">Sistemler</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Poly</a>
  <a class="nav-item" href="/kripto"><span class="nav-dot"></span>Kripto</a>
  <div class="sidebar-footer">XAUUSD · $1000 sanal</div>
</div>
<div class="main">
  <div id="view-list">
    <div class="head">
      <div>
        <div class="page-title">Algoritma işlemler</div>
        <div class="page-sub">XAUUSD sanal $1000 · $200 × 100x · kom $0.35 · 24s / 3×ATR · Poly listesinin altın kopyası</div>
      </div>
      <div class="chip" id="sum-chip">—</div>
    </div>
    <div class="section-title">algoritma durumu · en iyi → en kötü</div>
    <div id="algo-books"><div class="empty">yükleniyor…</div></div>
  </div>
  <div id="view-detail" style="display:none">
    <div class="head">
      <div>
        <a class="detail-back" href="/forex/algoritma-islemler">← Algoritmalar</a>
        <div class="page-title" id="detail-title">—</div>
        <div class="page-sub" id="detail-sub">XAUUSD · $1000</div>
      </div>
      <div class="chip" id="detail-sum">—</div>
    </div>
    <div class="section-title">Açık pozisyonlar</div>
    <div class="positions" id="detail-positions"><div class="empty">yükleniyor…</div></div>
    <div class="section-title" style="margin-top:22px">Geçmiş işlemler</div>
    <div id="detail-history"><div class="empty">yükleniyor…</div></div>
  </div>
</div>
<script>
const PATH = location.pathname.replace(/\/+$/,'');
const m = PATH.match(/\/forex\/algoritma-islemler\/([a-zA-Z0-9_]+)$/);
const DETAIL_ID = m ? m[1] : null;
function money(n){ return n==null?'—':Number(n).toFixed(2); }
function px(n){ return n==null?'—':Number(n).toFixed(2); }
function clock(s){
  const x=String(s||'');
  const mm=x.match(/T(\d{2}:\d{2})/)||x.match(/(\d{2}:\d{2})/);
  return mm?mm[1]:'';
}
function renderList(d){
  const mk=d.mark!=null?('XAU $'+money(d.mark)+' · '):'';
  const u=Number(d.total_unrealized||0);
  document.getElementById('sum-chip').textContent =
    mk+'Σ $'+money(d.total_balance)+' · Anlık '+(u>=0?'+':'')+money(u)
    +' · Net '+(Number(d.total_pnl||0)>=0?'+':'')+money(d.total_pnl)
    +' · açık '+(d.total_open||0);
  const books=(d.books||[]).slice().sort((a,b)=>
    Number(b.balance||0)-Number(a.balance||0)
    || Number(b.total_pnl||0)-Number(a.total_pnl||0)
    || Number(b.wr||0)-Number(a.wr||0)
  );
  const el=document.getElementById('algo-books');
  if(!books.length){ el.innerHTML='<div class="empty">defter yok</div>'; return; }
  el.innerHTML='<div class="book-grid">'+books.map(b=>{
    const pnl=Number(b.total_pnl||0);
    const upnl=Number(b.unrealized_pnl||0);
    const wr=b.wr!=null?('WR '+b.wr+'%'):'WR —';
    const href='/forex/algoritma-islemler/'+encodeURIComponent(b.id);
    const opens=(b.cards||[]).map(c=> (c.side==='LONG'?'AL':'SAT')).join(' · ')||'açık yok';
    return '<a class="book-card" href="'+href+'"><div class="bt">'+(b.name||b.id)+'</div>'
      +'<div class="bs">'+(b.title||'')+' · '+wr+' · '+(b.history_n||0)+' işlem</div>'
      +'<div class="br"><span>Bakiye</span><b>$'+money(b.balance)+'</b></div>'
      +'<div class="br"><span>Net P&amp;L</span><b class="'+(pnl>=0?'pos':'neg')+'">'+(pnl>=0?'+':'')+money(pnl)+'</b></div>'
      +'<div class="br"><span>Anlık</span><b class="'+(upnl>=0?'pos':'neg')+'">'+(upnl>=0?'+':'')+money(upnl)+'</b></div>'
      +'<div class="book-opens">'+(b.open_count||0)+' açık · '+opens
      +(b.cards&&b.cards[0]&&b.cards[0].mark!=null?(' · mark $'+money(b.cards[0].mark)):'')+'</div></a>';
  }).join('')+'</div>';
}
function renderDetail(b){
  document.getElementById('detail-title').textContent=b.name||b.id;
  document.getElementById('detail-sub').textContent=(b.title||'')+' · XAUUSD · $1000';
  const pnl=Number(b.total_pnl||0);
  document.getElementById('detail-sum').textContent=
    '$'+money(b.balance)+' · '+(pnl>=0?'+':'')+money(pnl)+' · WR '+(b.wr!=null?b.wr+'%':'—');
  const ps=b.positions||[];
  const pel=document.getElementById('detail-positions');
  pel.innerHTML=ps.length?ps.map(p=>{
    const sell=p.side==='SHORT'||p.side==='sell';
    const fn=p.float_net;
    return '<div class="pos-card"><div class="pos-top"><div class="pos-name">XAUUSD</div>'
      +'<div class="pos-dir '+(sell?'down':'up')+'">'+(sell?'SAT':'AL')+'</div></div>'
      +'<div class="pos-current '+(fn>=0?'pos':'neg')+'">'+money(fn)+'</div>'
      +'<div class="pos-entry">'+px(p.entry_price)+(p.mark!=null?' → '+px(p.mark):'')+' · '+clock(p.entry_time_tr)+'</div></div>';
  }).join(''):'<div class="empty">Açık pozisyon yok.</div>';
  const h=b.history||[];
  const hel=document.getElementById('detail-history');
  hel.innerHTML=h.length?h.map(t=>{
    const sell=t.side==='SHORT'||t.side==='sell';
    const tp=Number(t.pnl||0);
    return '<div class="hist-row"><div class="hist-time">'+clock(t.exit_time_tr||t.entry_time_tr)+'</div>'
      +'<div class="hist-dir '+(sell?'down':'up')+'">'+(sell?'SAT':'AL')+'</div>'
      +'<div class="hist-meta">'+px(t.entry_price)+' → '+px(t.exit_price)
      +' · kom $'+money(t.commission)+(t.close_reason?' · '+t.close_reason:'')+'</div>'
      +'<div class="hist-pnl '+(tp>=0?'pos':'neg')+'">'+(tp>=0?'+':'')+money(tp)+'</div></div>';
  }).join(''):'<div class="empty">Kapanmış işlem yok. Cron :05 / */10 ilk turları bekler.</div>';
}
async function loadFxAlgos(){
  try{
    if(DETAIL_ID){
      document.getElementById('view-list').style.display='none';
      document.getElementById('view-detail').style.display='block';
      const r=await fetch('/poly/api/forex/algo-books/'+encodeURIComponent(DETAIL_ID),{cache:'no-store'});
      const d=await r.json();
      if(!d||!d.ok){
        document.getElementById('detail-positions').innerHTML='<div class="empty">hata: '+(d&&d.error?d.error:'yüklenemedi')+'</div>';
        return;
      }
      renderDetail(d.book||d);
      return;
    }
    const r=await fetch('/poly/api/forex/algo-books',{cache:'no-store'});
    const d=await r.json();
    if(!d||!d.ok){
      document.getElementById('algo-books').innerHTML='<div class="empty">hata: '+(d&&d.error?d.error:'yüklenemedi')+'</div>';
      return;
    }
    renderList(d);
  }catch(e){
    const el=DETAIL_ID?document.getElementById('detail-positions'):document.getElementById('algo-books');
    if(el) el.innerHTML='<div class="empty">yükleme hatası</div>';
  }
}
loadFxAlgos(); setInterval(loadFxAlgos, 2000);
</script>
</body>
</html>
"""

