""" /site/kuponlar — sanal kupon fişi. Canlı bahis yok. """

SITE_COUPONS_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kuponlar · MATCHDAY</title>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Oswald:wght@600;700&family=Inter:wght@500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0c1a2e;--navy:#081424;--y:#F5C518;--ink:#111;--txt:#fff;--muted:#9aa8bc;--ok:#22c55e;--no:#ef4444}
*{box-sizing:border-box;margin:0;padding:0}
body{
  min-height:100%;color:var(--txt);font-family:Inter,system-ui,sans-serif;
  background:
    radial-gradient(ellipse at 20% 0%, rgba(245,197,24,.08), transparent 50%),
    repeating-linear-gradient(0deg,transparent 0 3px,rgba(255,255,255,.015) 3px 4px),
    var(--bg);
}
a{color:inherit;text-decoration:none}
.nav{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:16px;padding:14px 22px;background:rgba(8,20,36,.95);border-bottom:1px solid rgba(245,197,24,.2)}
.logo{font:700 15px Oswald,sans-serif;letter-spacing:.12em}
.logo i{display:inline-grid;place-items:center;width:32px;height:32px;border-radius:8px;background:var(--y);color:var(--ink);font-style:normal;margin-right:8px}
.links{display:flex;gap:16px;flex-wrap:wrap}
.links a{font:600 12px Oswald,sans-serif;letter-spacing:.1em;color:#c5c9d1}
.links a.on,.links a:hover{color:var(--y)}
.cta{margin-left:auto;background:var(--y);color:var(--ink);border-radius:6px;padding:8px 14px;font:800 12px Oswald,sans-serif}
.wrap{max-width:560px;margin:0 auto;padding:22px 16px 64px}
h1{font:italic 800 34px/1 Anton,sans-serif;color:var(--y);margin:6px 0 8px}
.note{font-size:12px;color:var(--muted);margin-bottom:14px}
.lgbar{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}
.lgchip{border:1px solid rgba(245,197,24,.3);background:#102033;color:#e8e8e8;border-radius:999px;padding:6px 10px;font:700 11px Oswald,sans-serif;cursor:pointer}
.lgchip.on{background:var(--y);color:var(--ink)}
.tabs{display:flex;gap:8px;margin:0 0 14px}
.tab{border:0;background:#102033;color:#9aa8bc;border-radius:8px;padding:8px 14px;font:800 12px Oswald,sans-serif;letter-spacing:.08em;cursor:pointer}
.tab.on{background:var(--y);color:#111}
.bank{
  display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px
}
.bank b{background:#102033;border:1px solid rgba(245,197,24,.22);border-radius:10px;padding:10px 12px;font:700 12px Oswald,sans-serif}
.bank b i{display:block;font-style:normal;color:var(--muted);font-size:10px;letter-spacing:.08em;margin-bottom:4px}
.bank .up{color:var(--ok)} .bank .dn{color:var(--no)}
.slip{margin-bottom:28px;padding:12px;border-radius:16px}
.slip.won{
  background:linear-gradient(180deg,rgba(34,197,94,.18),rgba(34,197,94,.05));
  outline:2px solid rgba(34,197,94,.55);
}
.slip.lost{
  background:linear-gradient(180deg,rgba(239,68,68,.18),rgba(239,68,68,.05));
  outline:2px solid rgba(239,68,68,.5);
}
.slip-h{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.slip-h .lg{font:800 12px Oswald,sans-serif;color:var(--y);letter-spacing:.08em}
.badge{margin-left:auto;font:800 10px Oswald,sans-serif;letter-spacing:.08em;border-radius:99px;padding:5px 9px}
.badge.ok{background:#12351f;color:var(--ok)}
.badge.no{background:#3a1218;color:var(--no)}
.badge.wait{background:#1a1608;color:var(--y)}
.row{display:grid;grid-template-columns:1fr 86px;gap:8px;align-items:stretch;margin-bottom:10px}
.left{display:flex;align-items:center;gap:8px;min-width:0}
.crests{display:flex;flex-direction:column;gap:4px;flex-shrink:0}
.crests img,.crests .fb{
  width:36px;height:36px;border-radius:50%;object-fit:cover;background:#fff;border:2px solid #fff
}
.crests .fb{display:grid;place-items:center;font:800 9px Oswald,sans-serif;color:#fff}
.box{flex:1;min-width:0;border-radius:14px;overflow:hidden;box-shadow:0 6px 0 rgba(0,0,0,.18)}
.box .top{background:#fff;color:#111;padding:9px 12px;font:800 14px/1.15 Inter,sans-serif}
.box .top em{font-style:normal;color:#c9a227}
.box .clk{display:block;font:700 11px Oswald,sans-serif;color:#5a6573;letter-spacing:.04em;margin-top:3px}
.box .bot{background:#d5dbe3;color:#2a3340;padding:7px 10px;display:flex;align-items:center;justify-content:space-between;gap:8px;font:700 12px Inter,sans-serif}
.sel{background:var(--y);color:#111;min-width:28px;height:22px;border-radius:4px;display:grid;place-items:center;font:800 12px Oswald,sans-serif}
.odd{
  background:var(--y);border-radius:14px;display:grid;place-items:center;
  font:800 26px/1 Oswald,sans-serif;color:#111;box-shadow:0 6px 0 rgba(0,0,0,.18)
}
.foot{
  display:flex;align-items:center;gap:8px;margin-top:4px;
  background:linear-gradient(90deg,#0a1524 0 42%, var(--y) 42%);
  border-radius:12px;padding:8px 8px 8px 12px;min-height:52px
}
.foot .brand{flex:0 0 38%;font:800 12px/1.2 Oswald,sans-serif}
.foot .brand i{color:var(--y);font-style:normal}
.foot .tot{flex:1;display:flex;align-items:center;justify-content:flex-end;gap:10px;padding-right:4px}
.foot .tot span{font:800 13px Oswald,sans-serif;color:#111}
.foot .tot b{background:#fff;color:#111;border-radius:999px;padding:7px 16px;font:800 22px/1 Oswald,sans-serif}
.cash{margin-top:8px;display:flex;justify-content:space-between;font:700 12px Oswald,sans-serif;color:var(--muted)}
.cash strong{color:#fff}
.leg-hit{font-size:10px;margin-top:3px}
.leg-hit.ok{color:var(--ok)} .leg-hit.no{color:var(--no)}
@media(max-width:520px){
  .row{grid-template-columns:1fr 70px}
  .box .top{font-size:12px}
  .odd{font-size:20px}
  .foot{background:linear-gradient(90deg,#0a1524 0 36%, var(--y) 36%)}
  .foot .brand{flex-basis:32%;font-size:11px}
  .foot .tot b{font-size:18px;padding:6px 12px}
}
</style>
</head>
<body>
<header class="nav">
  <a class="logo" href="/site"><i>⚽</i> MATCHDAY</a>
  <nav class="links">
    <a href="/site">MAÇLAR</a>
    <a href="/site/biten">BİTMİŞ</a>
    <a class="on" href="/site/kuponlar">KUPONLAR</a>
  </nav>
  <a class="cta" href="/site">GERİ</a>
</header>
<div class="wrap">
  <h1>KUPONLAR</h1>
  <div class="note" id="meta">yükleniyor…</div>
  <div class="lgbar" id="lgbar"></div>
  <div class="tabs">
    <button class="tab on" type="button" data-tab="open">AÇIK</button>
    <button class="tab" type="button" data-tab="done">KUPON SONUÇLARI</button>
  </div>
  <div class="bank" id="bank"></div>
  <div id="list"></div>
</div>
<script>
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));}
function money(n){ const x=Number(n||0); return x.toLocaleString('tr-TR',{minimumFractionDigits:0,maximumFractionDigits:2})+' TL'; }
function crest(url, short, color){
  if(url) return `<img src="${esc(url)}" alt="" onerror="this.outerHTML='<div class=fb style=background:${esc(color||'#333')}>${esc((short||'?').slice(0,3))}</div>'">`;
  return `<div class="fb" style="background:${esc(color||'#333')}">${esc((short||'?').slice(0,3))}</div>`;
}
let LEAGUE = new URLSearchParams(location.search).get('league') || 'all';
let TAB = new URLSearchParams(location.search).get('tab') || 'open';
function withLg(url){
  const join = url.includes('?') ? '&' : '?';
  return url + join + 'league=' + encodeURIComponent(LEAGUE) + '&tab=' + encodeURIComponent(TAB);
}
function badge(st){
  if(st==='won') return '<span class="badge ok">KAZANDI</span>';
  if(st==='lost') return '<span class="badge no">KAYBETTİ</span>';
  return '<span class="badge wait">AÇIK</span>';
}
function row(l){
  let hit='';
  if(l.hit===true) hit='<div class="leg-hit ok">TUTTU'+(l.hg!=null?` ${l.hg}–${l.ag}`:'')+'</div>';
  else if(l.hit===false) hit='<div class="leg-hit no">TUTMADI'+(l.hg!=null?` ${l.hg}–${l.ag}`:'')+'</div>';
  else if(l.phase==='live') hit='<div class="leg-hit" style="color:#F5C518">OYNANIYOR</div>';
  else hit='<div class="leg-hit" style="color:#9aa8bc">bekliyor</div>';
  return `<div class="row">
    <div class="left">
      <div class="crests">${crest(l.home_crest,l.home_short,l.home_color)}${crest(l.away_crest,l.away_short,l.away_color)}</div>
      <div class="box">
        <div class="top">${esc(l.home)} <em>vs</em> ${esc(l.away)}<span class="clk">${esc(l.when_tr||l.when||'')}</span></div>
        <div class="bot"><span>${esc(l.market_label||'Maç Sonucu 1X2')}</span><span class="sel">${esc(l.sel_box||l.sel||'')}</span></div>
      </div>
    </div>
    <div class="odd">${Number(l.odds||0).toFixed(2)}</div>
  </div>${hit}`;
}
function slip(c){
  const pot = c.potential!=null ? c.potential : (c.stake||200)*(c.odds_product||1);
  const extra = c.status==='open' ? '' : ` · ${c.pnl>=0?'+':''}${money(c.pnl)}`;
  return `<article class="slip ${esc(c.status||'')}">
    <div class="slip-h"><span class="lg">${esc(c.league_short||'')} · ${esc(c.when||c.day||'')}</span>${badge(c.status)}</div>
    ${(c.legs||[]).map(row).join('')}
    <div class="foot">
      <div class="brand"><i>MATCHDAY</i><br>Kazandırır!</div>
      <div class="tot"><span>Toplam Oran</span><b>${Number(c.odds_product||0).toFixed(2)}</b></div>
    </div>
    <div class="cash"><span>Yatırım <strong>${money(c.stake||200)}</strong></span><span>Olası getiri <strong>${money(pot)}</strong>${extra}</span></div>
    <div class="cash" style="margin-top:4px"><span>oran ${esc(c.odds_src==='fd'?'football-data B365/Avg':'H2H vekil (canlı kota yok)')}</span><span>emir yok</span></div>
  </article>`;
}
async function load(){
  const d = await (await fetch(withLg('/site/api/coupons'),{cache:'no-store'})).json();
  const bar=document.getElementById('lgbar');
  const list = await (await fetch('/site/api/leagues',{cache:'no-store'})).json();
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on', t.dataset.tab===TAB));
  const chips=[{id:'all',flag:'🌍',short:'TÜM'}].concat(list.leagues||[]);
  bar.innerHTML = chips.map(x=>
    `<button class="lgchip${x.id===LEAGUE?' on':''}" type="button" data-id="${esc(x.id)}">${esc(x.flag||'')} ${esc(x.short)}</button>`
  ).join('');
  const st=d.stats||{}, w=st.week||{};
  const wk = w.verdict==='kâr'?'up':(w.verdict==='zarar'?'dn':'');
  document.getElementById('meta').textContent = (d.note||'') + (d.updated?(' · '+d.updated):'');
  document.getElementById('bank').innerHTML =
    `<b><i>KASA</i>${money(st.balance!=null?st.balance:10000)}</b>`+
    `<b><i>BAŞLANGIÇ</i>${money(st.starting||10000)}</b>`+
    `<b><i>BU HAFTA</i><span class="${wk}">${w.pnl>=0?'+':''}${money(w.pnl||0)} · ${esc(w.verdict||'beraber')}</span></b>`+
    `<b><i>AÇIK / KİLİTLİ</i>${st.open||0} · ${money(st.locked||0)}</b>`;
  document.getElementById('list').innerHTML = (d.coupons||[]).map(slip).join('')
    || `<div class="note">${TAB==='done'?'Henüz bitmiş kupon yok — maçlar bitince kazanan yeşil, kaybeden kırmızı burada durur.':'Açık kupon yok.'}</div>`;
}
document.getElementById('lgbar').addEventListener('click', e=>{
  const b=e.target.closest('.lgchip'); if(!b) return;
  LEAGUE = b.dataset.id || 'all';
  const u=new URL(location.href);
  if(LEAGUE==='all') u.searchParams.delete('league'); else u.searchParams.set('league', LEAGUE);
  u.searchParams.set('tab', TAB);
  history.replaceState({},'',u);
  load();
});
document.querySelector('.tabs').addEventListener('click', e=>{
  const b=e.target.closest('.tab'); if(!b) return;
  TAB = b.dataset.tab || 'open';
  const u=new URL(location.href);
  u.searchParams.set('tab', TAB);
  history.replaceState({},'',u);
  load();
});
load();
setInterval(load, 60000);
</script>
</body>
</html>
"""
