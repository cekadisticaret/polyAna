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
  <a class="nav-item" href="/forex/grafik"><span class="nav-dot"></span>Grafik</a>
  <div class="nav-label">Sistemler</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Poly'ye Geç</a>
  <a class="nav-item" href="/kripto"><span class="nav-dot"></span>Kripto'ya Geç</a>
  <div class="sidebar-footer"><span class="dot"></span>Forex kabuğu</div>
</div>
<div class="main">
  <div class="head">
    <div>
      <div class="page-title">Forex <span class="badge">yeni</span></div>
      <div class="page-sub">Poly ve Kripto’dan ayrı sistem · sanal defterler henüz bağlanmadı</div>
    </div>
  </div>
  <div class="hero">
    <div class="glass">
      <h2>Sayfa açık</h2>
      <p>Bu ekran Poly (`/poly`) ve Kripto (`/kripto`) gibi üçüncü sistem. İşlem motoru, cron ve defterler bir sonraki adımda eklenecek — şimdilik kabuk ve menü geçişi hazır.</p>
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

FOREX_GRAFIK_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>XAUUSD — Forex</title>
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
.ex-btn{border:none;color:#fff;padding:10px 14px;cursor:pointer;text-align:left;font:inherit}
.ex-btn.sell{background:#1565c0;text-align:left}
.ex-btn.buy{background:#0d47a1;text-align:right}
.ex-btn:active{filter:brightness(1.08)}
.ex-k{font-size:10px;font-weight:800;letter-spacing:.08em;opacity:.85}
.ex-p{font-size:20px;font-weight:800;letter-spacing:-.4px;font-variant-numeric:tabular-nums}
.lot{background:#0a3d91;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;border-left:1px solid rgba(255,255,255,.12);border-right:1px solid rgba(255,255,255,.12)}
.lot input{width:56px;background:transparent;border:none;color:#fff;font-size:18px;font-weight:800;text-align:center;outline:none}
.lot-lbl{font-size:9px;opacity:.7;font-weight:700}
.lot-step{display:flex;gap:8px}
.lot-step button{width:22px;height:18px;border:none;border-radius:4px;background:rgba(255,255,255,.15);color:#fff;cursor:pointer;font-weight:800}
.chart-wrap{flex:1;min-height:0;position:relative;background:#fff}
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
.cd{position:absolute;right:72px;bottom:28px;z-index:4;background:#263238;color:#fff;font-size:11px;font-weight:800;padding:3px 8px;border-radius:6px;font-variant-numeric:tabular-nums}
.toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:#1b2832;border:1px solid var(--gold);color:var(--gold);padding:8px 14px;border-radius:10px;font-size:12px;font-weight:700;display:none;z-index:20}
@media(max-width:800px){
  body{flex-direction:column;overflow:auto}
  .sidebar{width:100%;height:auto;flex-direction:row;flex-wrap:wrap;padding:8px}
  .desk{height:auto;min-height:80vh}
  .chart-wrap{min-height:62vh}
  .ex-p{font-size:16px}
}
</style>
</head>
<body id="fx-page">
<div class="sidebar">
  __FOREX_BRAND__
  <div class="nav-label">Forex</div>
  <a class="nav-item" href="/forex/home"><span class="nav-dot"></span>Overview</a>
  <a class="nav-item active" href="/forex/grafik"><span class="nav-dot"></span>Grafik</a>
  <div class="nav-label">Sistemler</div>
  <a class="nav-item" href="/poly"><span class="nav-dot"></span>Poly</a>
  <a class="nav-item" href="/kripto"><span class="nav-dot"></span>Kripto</a>
  <div class="sidebar-footer">XAUUSD · sanal</div>
</div>
<div class="desk">
  <div class="topbar">
    <div class="sym">XAUUSD<small>Altın / Dolar</small></div>
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
</div>
<div class="toast" id="toast"></div>
<script>
const TFS = [
  ['1m','M1'],['5m','M5'],['15m','M15'],['30m','M30'],['1h','H1'],['4h','H4'],['1d','D1']
];
let _tf = '1m', _chart=null, _series=null, _bidLine=null, _askLine=null;
let _last=[], _req=0, _barLeft=60, _barSec=60;
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
  toast('Sanal '+ (side==='buy'?'AL':'SAT') +' '+lot+' lot @ '+px+' — motor henüz yok');
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
function tick(){
  document.getElementById('m-clk').textContent=new Date().toLocaleTimeString('tr-TR',{hour12:false,timeZone:TZ});
  if(_barLeft>0) _barLeft--;
  const m=String(Math.floor(_barLeft/60)).padStart(2,'0');
  const s=String(_barLeft%60).padStart(2,'0');
  document.getElementById('cd').textContent=m+':'+s;
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
}
function ensure(){
  if(_chart) return true;
  const el=document.getElementById('fx-chart');
  if(!el||!window.LightweightCharts) return false;
  _chart=LightweightCharts.createChart(el,{
    layout:{background:{type:'solid',color:'#ffffff'},textColor:'#546e7a'},
    grid:{vertLines:{color:'#eceff1'},horzLines:{color:'#eceff1'}},
    rightPriceScale:{borderColor:'#cfd8dc'},
    timeScale:{borderColor:'#cfd8dc',timeVisible:true,secondsVisible:false},
    crosshair:{mode:LightweightCharts.CrosshairMode.Normal},
    width:el.clientWidth, height:el.clientHeight||480,
  });
  _series=_chart.addCandlestickSeries({
    upColor:'#26a69a', downColor:'#ef5350', borderUpColor:'#26a69a',
    borderDownColor:'#ef5350', wickUpColor:'#26a69a', wickDownColor:'#ef5350',
  });
  window.addEventListener('resize',()=>{ if(_chart) _chart.applyOptions({width:el.clientWidth,height:el.clientHeight||480}); });
  return true;
}
async function refreshQuote(){
  try{
    const r=await fetch('/poly/api/forex/spot?timeframe='+_tf,{cache:'no-store'});
    applyQuote(await r.json());
  }catch(e){}
}
async function loadChart(){
  const id=++_req;
  if(!ensure()) return;
  const lab=(TFS.find(x=>x[0]===_tf)||[_tf,_tf])[1];
  document.getElementById('hud').innerHTML='XAUUSD, '+lab+' <span>Gold vs US Dollar</span>';
  try{
    const r=await fetch('/poly/api/forex/chart?timeframe='+_tf+'&limit=240&_='+Date.now(),{cache:'no-store'});
    const d=await r.json();
    if(id!==_req) return;
    applyQuote(d);
    const candles=(d.candles||[]).map(c=>({time:utcToIst(c.time),open:c.open,high:c.high,low:c.low,close:c.close}));
    _last=candles.slice();
    _series.setData(candles);
    applySignal(d);
    _chart.timeScale().fitContent();
  }catch(e){ console.error(e); }
}
function applySignal(d){
  const s=d.signal||{};
  const dir=s.direction||'NEUTRAL';
  const el=document.getElementById('sig');
  el.className='sig'+(dir==='UP'?' up':dir==='DOWN'?' down':'');
  const lab=dir==='UP'?'YÜKSELİŞ':dir==='DOWN'?'DÜŞÜŞ':'NÖTR';
  document.getElementById('sig-dir').textContent=lab;
  const conf=s.confidence!=null?Number(s.confidence).toFixed(0):'—';
  const st=s.is_stable?'kararlı':'bekliyor';
  document.getElementById('sig-meta').textContent='güven '+conf+' · '+st;
  const L=s.layers||{};
  document.getElementById('sig-ly').textContent=
    'T '+(L.trend!=null?Number(L.trend).toFixed(0):'—')
    +'  M '+(L.momentum!=null?Number(L.momentum).toFixed(0):'—')
    +'  P '+(L.pattern!=null?Number(L.pattern).toFixed(0):'—');
  if(!_series) return;
  const marks=(d.signal_markers||[]).map(m=>({
    time:utcToIst(m.time),
    position:m.direction==='UP'?'belowBar':'aboveBar',
    color:m.direction==='UP'?'#26a69a':'#ef5350',
    shape:m.direction==='UP'?'arrowUp':'arrowDown',
    text:m.direction==='UP'?'AL':'SAT',
  }));
  _series.setMarkers(marks);
}
const q=new URLSearchParams(location.search);
if(TFS.some(x=>x[0]===q.get('tf'))) _tf=q.get('tf');
buildTfs(); tick(); setInterval(tick,1000);
loadChart(); refreshQuote();
setInterval(loadChart, 15000);
setInterval(refreshQuote, 2000);
</script>
</body>
</html>
"""
