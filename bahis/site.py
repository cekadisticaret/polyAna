"""Herkese açık /site — MATCHDAY kabuk, sarı/lacivert. Şifre yok, emir yok."""

BAHIS_SITE_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MATCHDAY</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Oswald:wght@500;600;700&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%23F5C518'/><circle cx='16' cy='16' r='7' fill='%23080c14'/></svg>">
<style>
:root{
  --bg:#080c14; --navy:#0b1220; --card:#101826; --line:rgba(245,197,24,.28);
  --y:#F5C518; --y2:#ffd84a; --ink:#111; --txt:#fff; --muted:#9aa3b2;
  --win:#22c55e; --draw:#6b7280; --loss:#ef4444;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
html,body{min-height:100%;background:var(--bg);color:var(--txt);font-family:Inter,system-ui,sans-serif}
a{color:inherit;text-decoration:none}
button{font:inherit;cursor:pointer}
img{max-width:100%}
.ann{
  background:#05070c;border-bottom:1px solid rgba(245,197,24,.2);
  display:flex;justify-content:center;gap:28px;flex-wrap:wrap;
  padding:8px 16px;font-size:11px;font-weight:700;letter-spacing:.08em;color:#e8e8e8;
}
.ann b{color:var(--y)}
.nav{
  position:sticky;top:0;z-index:40;background:rgba(8,12,20,.94);
  border-bottom:1px solid rgba(255,255,255,.06);
  display:flex;align-items:center;gap:22px;padding:14px 28px;backdrop-filter:blur(12px);
}
.logo{display:flex;align-items:center;gap:10px;font:700 15px/1 Oswald,sans-serif;letter-spacing:.12em}
.logo i{
  width:38px;height:38px;border-radius:10px;background:var(--y);color:var(--ink);
  display:grid;place-items:center;font-style:normal;font-size:18px;
}
.links{display:flex;gap:22px;margin-left:18px}
.links a{font:600 13px/1 Oswald,sans-serif;letter-spacing:.1em;color:#c5c9d1}
.links a:hover{color:var(--y)}
.sp{flex:1}
.cta{
  background:var(--y);color:var(--ink);border:0;border-radius:6px;
  padding:10px 18px;font:800 12px/1 Oswald,sans-serif;letter-spacing:.1em;
}
.lgbar{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;padding:12px 16px;background:#05070c;border-bottom:1px solid rgba(245,197,24,.18)}
.lgchip{
  border:1px solid rgba(245,197,24,.28);background:#101826;color:#e8e8e8;border-radius:999px;
  padding:7px 12px;font:700 11px/1 Oswald,sans-serif;letter-spacing:.08em;cursor:pointer
}
.lgchip.on{background:var(--y);color:var(--ink);border-color:var(--y)}
.hero{
  position:relative;overflow:hidden;min-height:78vh;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  text-align:center;padding:56px 20px 48px;
  background:
    radial-gradient(ellipse at 20% 80%, rgba(245,197,24,.16), transparent 42%),
    radial-gradient(ellipse at 80% 20%, rgba(40,80,180,.22), transparent 40%),
    linear-gradient(180deg,#0a1220 0%,#080c14 70%);
}
.hero:before,.hero:after{
  content:"";position:absolute;width:42vw;height:70%;top:8%;opacity:.07;
  background:repeating-linear-gradient(90deg,transparent 0 18px,#fff 18px 19px);
  pointer-events:none;
}
.hero:before{left:-8%;transform:skewX(-12deg)}
.hero:after{right:-8%;transform:skewX(12deg)}
.kicker{color:var(--y);font:700 13px/1 Oswald,sans-serif;letter-spacing:.28em;margin-bottom:10px}
.hero h1{
  font-family:Anton,Impact,sans-serif;font-size:clamp(48px,10vw,108px);
  font-style:italic;letter-spacing:.02em;color:var(--y);line-height:.9;
  text-shadow:0 8px 0 rgba(0,0,0,.35);
}
.hero h1 em{font-style:italic;color:#fff}
.tag{margin-top:12px;font:600 16px/1.3 Oswald,sans-serif;letter-spacing:.16em;color:#e8e8e8}
.vsbox{display:flex;align-items:center;justify-content:center;gap:28px;margin:34px 0 18px;flex-wrap:wrap}
.side{width:140px}
.side img,.side .fb{
  width:92px;height:92px;border-radius:50%;object-fit:contain;background:#fff;
  border:3px solid var(--y);box-shadow:0 0 24px rgba(245,197,24,.25);
}
.side .fb{display:grid;place-items:center;font:800 18px Oswald,sans-serif;color:#111;margin:0 auto}
.side b{display:block;margin-top:10px;font:700 14px Oswald,sans-serif;letter-spacing:.08em}
.vs{font:italic 800 42px/1 Anton,sans-serif;color:var(--y)}
.meta{
  display:flex;gap:22px;flex-wrap:wrap;justify-content:center;
  font:600 12px/1 Oswald,sans-serif;letter-spacing:.12em;color:#d5d8de;margin-bottom:26px;
}
.meta span{display:flex;align-items:center;gap:6px}
.meta i{color:var(--y);font-style:normal}
.wrap{max-width:1120px;margin:0 auto;padding:0 22px 64px}
.props{
  display:grid;grid-template-columns:repeat(4,1fr);gap:0;
  border:1px solid var(--line);border-radius:4px;overflow:hidden;margin:-28px auto 48px;max-width:1120px;
  background:var(--navy);
}
.prop{padding:22px 16px;text-align:center;border-right:1px solid var(--line)}
.prop:last-child{border-right:0}
.prop i{display:block;color:var(--y);font-size:22px;margin-bottom:8px;font-style:normal}
.prop b{display:block;font:700 13px Oswald,sans-serif;letter-spacing:.08em}
.prop span{display:block;font-size:12px;color:var(--muted);margin-top:4px}
.sec-t{
  text-align:center;font:italic 800 28px/1 Anton,sans-serif;letter-spacing:.06em;
  color:#fff;margin:8px 0 18px;
}
.sec-t b{color:var(--y)}
.count{
  display:flex;justify-content:center;gap:18px;margin-bottom:48px;
}
.cd{
  min-width:92px;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:16px 10px;text-align:center;
}
.cd strong{display:block;font:italic 800 36px/1 Anton,sans-serif}
.cd span{font:600 11px Oswald,sans-serif;letter-spacing:.14em;color:var(--muted)}
.prev{
  background:var(--card);border:1px solid var(--line);border-radius:8px;padding:28px 22px;margin-bottom:40px;
}
.pgrid{display:grid;grid-template-columns:1fr auto 1fr;gap:18px;align-items:center}
.pteam{text-align:center}
.pteam img,.pteam .fb{width:72px;height:72px;border-radius:50%;object-fit:contain;background:#fff;margin:0 auto 8px}
.pteam .fb{display:grid;place-items:center;font-weight:800}
.pteam b{display:block;font:700 14px Oswald,sans-serif;letter-spacing:.06em;margin-bottom:10px}
.form{display:flex;justify-content:center;gap:5px}
.fm{
  width:22px;height:22px;border-radius:3px;display:grid;place-items:center;
  font:800 10px Inter,sans-serif;color:#fff;
}
.fm.W{background:var(--win)} .fm.D{background:var(--draw)} .fm.L{background:var(--loss)}
.mid{text-align:center}
.ghost{
  display:inline-block;margin-top:10px;border:1px solid #fff;color:#fff;border-radius:4px;
  padding:10px 16px;font:700 12px Oswald,sans-serif;letter-spacing:.1em;background:transparent;
}
.teams{display:flex;gap:10px;overflow:auto;padding:4px 0 28px}
.rew{width:64px;flex-shrink:0;text-align:center;cursor:pointer;opacity:.75}
.rew.on{opacity:1}
.rew img,.rew .fb{
  width:52px;height:52px;border-radius:50%;margin:0 auto 5px;background:#fff;object-fit:contain;
  border:2px solid transparent;
}
.rew.on img,.rew.on .fb{border-color:var(--y);box-shadow:0 0 12px rgba(245,197,24,.35)}
.rew .fb{display:grid;place-items:center;font-size:10px;font-weight:800;color:#111}
.rew span{font-size:10px;color:var(--muted);font-weight:700}
.kgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.kupon{
  display:block;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:18px 18px 16px;color:inherit;
}
.kupon:hover{border-color:var(--y)}
.kupon .lab{color:var(--y);font:700 11px Oswald,sans-serif;letter-spacing:.14em}
.kupon h3{font:italic 800 22px/1 Anton,sans-serif;margin:4px 0 12px}
.kfeat{display:flex;align-items:center;gap:10px;margin-bottom:12px;font-weight:700}
.kfeat img,.kfeat .fb{width:36px;height:36px;border-radius:50%;background:#fff;object-fit:contain}
.kfeat .fb{display:grid;place-items:center;font-size:10px;font-weight:800;color:#111}
.tip{color:var(--y);font:700 14px Oswald,sans-serif;letter-spacing:.04em;margin-bottom:12px}
.kodds{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
.kodds button{
  border:1px solid var(--line);border-radius:6px;padding:10px 4px;background:#0a101a;color:#fff;font-weight:800;
}
.kodds button.on{background:var(--y);color:var(--ink);border-color:var(--y)}
.kodds s{display:block;text-decoration:none;font-size:10px;opacity:.7}
.trust{
  display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:48px 0 0;padding:22px;
  background:#d7dbe3;color:#222;border-radius:4px;
}
.trust div{text-align:center;font:700 12px Oswald,sans-serif;letter-spacing:.08em}
.trust span{display:block;font:600 11px Inter,sans-serif;color:#555;margin-top:4px;letter-spacing:0}
.foot{
  background:#05070c;border-top:1px solid rgba(255,255,255,.06);padding:42px 22px 18px;margin-top:36px;
}
.fgrid{max-width:1120px;margin:0 auto;display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:28px}
.foot h4{font:700 13px Oswald,sans-serif;letter-spacing:.12em;color:var(--y);margin-bottom:10px}
.foot p,.foot a{color:#9aa3b2;font-size:13px;line-height:1.7}
.foot .copy{max-width:1120px;margin:28px auto 0;padding-top:14px;border-top:1px solid rgba(255,255,255,.06);font-size:12px;color:#6b7280}
.ov{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:60;display:none;align-items:center;justify-content:center;padding:20px}
.ov.on{display:flex}
.ovc{width:min(520px,100%);max-height:92vh;overflow:auto}
@media(max-width:900px){
  .links{display:none}
  .props,.pgrid,.kgrid,.trust,.fgrid{grid-template-columns:1fr}
  .prop{border-right:0;border-bottom:1px solid var(--line)}
  .hero h1{font-size:52px}
  .side{width:110px}
}
</style>
</head>
<body>
<div class="ann" id="ann"><span><b>BUGÜNÜN MAÇI</b> · SÜPER LİG</span><span>10 SEZON VERİ</span><span>KUPON AÇILMAZ</span></div>
<header class="nav">
  <a class="logo" href="#home"><i>⚽</i> MATCHDAY</a>
  <nav class="links">
    <a href="#home">MAÇLAR</a>
    <a href="#kuponlar">FİKSTÜR</a>
    <a href="/site/biten">BİTMİŞ</a>
    <a href="/site/kuponlar">KUPONLAR</a>
    <a href="#kuponlar">TAHMİN</a>
  </nav>
  <div class="sp"></div>
  <a class="cta" href="#kuponlar">TAHMİNİ GÖR</a>
</header>
<div class="lgbar" id="lgbar"></div>

<section class="hero" id="home">
  <div class="kicker" id="kicker">SÜPER LİG · 2026/27</div>
  <h1>IT'S <em>MATCHDAY</em></h1>
  <p class="tag">BUGÜN SAVAŞ. BUGÜN KAZAN.</p>
  <div class="vsbox" id="vsbox"></div>
  <div class="meta" id="meta"></div>
  <a class="cta" href="#kuponlar">TAHMİNİ GÖR</a>
</section>

<div class="wrap">
  <div class="props">
    <div class="prop"><i>⏱</i><b>CANLI FİKSTÜR</b><span>Haftanın maçları</span></div>
    <div class="prop"><i>📊</i><b>10 YIL H2H</b><span>Form + çıkarım</span></div>
    <div class="prop"><i>🛡</i><b>EMİR YOK</b><span>Sadece tahmin</span></div>
    <div class="prop"><i>⚽</i><b>1. LİG</b><span>18 takım</span></div>
  </div>

  <div class="sec-t">MAÇ <b>BAŞLIYOR</b></div>
  <div class="count" id="count">
    <div class="cd"><strong id="cdh">—</strong><span>SAAT</span></div>
    <div class="cd"><strong id="cdm">—</strong><span>DAKİKA</span></div>
    <div class="cd"><strong id="cds">—</strong><span>SANİYE</span></div>
  </div>

  <div class="prev" id="preview">
    <div class="sec-t" style="margin-top:0">MAÇ <b>ÖNİZLEME</b></div>
    <div class="pgrid" id="pgrid"></div>
  </div>

  <div class="teams" id="rew"></div>

  <div class="sec-t" id="kuponlar">YAKIN <b>FİKSTÜR</b></div>
  <div class="kgrid" id="kgrid"></div>

  <div class="trust">
    <div>EN İYİ ÇIKARIM<span>10 sezon</span></div>
    <div>FORM<span>Son 5 maç</span></div>
    <div>H2H<span>Kafa kafaya</span></div>
    <div>ÜCRETSİZ<span>Giriş yok</span></div>
  </div>
</div>

<footer class="foot">
  <div class="fgrid">
    <div>
      <div class="logo" style="margin-bottom:10px"><i>⚽</i> MATCHDAY</div>
      <p>7 lig · 10 yıl kafa kafaya. Bu sayfa kupon açmaz, bahis iletmez.</p>
    </div>
    <div>
      <h4>BAĞLANTILAR</h4>
      <a href="#home">Maçlar</a><br><a href="#kuponlar">Fikstür</a><br><a href="/site/biten">Bitmiş</a><br><a href="/site/kuponlar">Kuponlar</a>
    </div>
    <div>
      <h4>BİLGİ</h4>
      <p>Veri: football-data + fikstür. Tahmin çıkarım, garanti değil.</p>
    </div>
  </div>
  <div class="copy">© MATCHDAY · 7 lig · kupon yok</div>
</footer>
<div class="ov" id="ov" onclick="if(event.target===this)this.className='ov'"></div>
<script>
const $ = id => document.getElementById(id);
let SUM=null, TEAM='', FEAT=null, TMR=null;
let LEAGUE = new URLSearchParams(location.search).get('league') || 'tr';
function withLg(url){
  const join = url.includes('?') ? '&' : '?';
  return url + join + 'league=' + encodeURIComponent(LEAGUE);
}
function paintLeagues(list){
  const box=$('lgbar'); if(!box) return;
  box.innerHTML = (list||[]).map(x=>
    `<button class="lgchip${x.id===LEAGUE?' on':''}" type="button" data-id="${esc(x.id)}">${esc(x.flag)} ${esc(x.short)}</button>`
  ).join('');
}
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));}
function crest(t, cls){
  if(t&&t.crest) return `<img class="${cls||''}" src="${esc(t.crest)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:(cls||'')+' fb',style:'--c:${t.color}',textContent:'${esc(t.short)}'}))">`;
  return `<div class="${cls||''} fb" style="background:${t&&t.color||'#333'}">${esc((t&&t.short)||'?')}</div>`;
}
function formDots(arr){
  return (arr||[]).map(x=>`<i class="fm ${esc(x)}">${esc(x)}</i>`).join('') || '<span style="color:#9aa3b2">—</span>';
}
function kupon(m){
  const t=m.tip||{}, o=m.odds||{}, f=v=>v==null?'—':Number(v).toFixed(2);
  const pick=t.pick||'';
  return `<a class="kupon" href="/site/mac/${encodeURIComponent(m.id)}">
    <div class="lab">${esc(m.when||'')} ${m.week?'· H'+m.week:''}</div>
    <h3>${esc(m.home.short)} VS ${esc(m.away.short)}</h3>
    <div class="kfeat">${crest(m.home)}${crest(m.away)}<b>${esc(m.home.name)} — ${esc(m.away.name)}</b></div>
    <div class="tip">${esc(t.text||'Çıkarım yok')} · %${t.pct||'—'}</div>
    <div class="kodds">
      <span class="${pick==='H'?'on':''}" style="display:block;border:1px solid var(--line);border-radius:6px;padding:10px 4px;background:#0a101a;text-align:center;font-weight:800${pick==='H'?';background:var(--y);color:#111;border-color:var(--y)':''}"><s>1</s>${f(o.home)}</span>
      <span class="${pick==='D'?'on':''}" style="display:block;border:1px solid var(--line);border-radius:6px;padding:10px 4px;background:#0a101a;text-align:center;font-weight:800${pick==='D'?';background:var(--y);color:#111;border-color:var(--y)':''}"><s>X</s>${f(o.draw)}</span>
      <span class="${pick==='A'?'on':''}" style="display:block;border:1px solid var(--line);border-radius:6px;padding:10px 4px;background:#0a101a;text-align:center;font-weight:800${pick==='A'?';background:var(--y);color:#111;border-color:var(--y)':''}"><s>2</s>${f(o.away)}</span>
    </div>
  </a>`;
}
function paintHero(m){
  if(!m){ $('vsbox').innerHTML=''; $('meta').innerHTML=''; return; }
  $('vsbox').innerHTML = `
    <div class="side">${crest(m.home)}<b>${esc(m.home.name)}</b></div>
    <div class="vs">VS</div>
    <div class="side">${crest(m.away)}<b>${esc(m.away.name)}</b></div>`;
  $('meta').innerHTML = `
    <span><i>📅</i> ${esc(m.when||'—')}</span>
    <span><i>🏟</i> ${esc(m.venue||'Süper Lig')}</span>
    <span><i>⚽</i> HAFTA ${m.week||'—'}</span>`;
  $('ann').innerHTML = `<span><b>BUGÜNÜN MAÇI</b> · ${esc(m.home.short)} vs ${esc(m.away.short)}</span><span>${esc(m.when||'')}</span><span>KUPON AÇILMAZ</span>`;
  $('pgrid').innerHTML = `
    <div class="pteam">${crest(m.home)}<b>${esc(m.home.name)}</b><div class="form">${formDots(m.form_h)}</div></div>
    <div class="mid">
      <div class="vs" style="font-size:28px">VS</div>
      <div class="tip" style="margin:8px 0">${esc((m.tip&&m.tip.text)||'')}</div>
      <a class="ghost" href="/site/mac/${encodeURIComponent(m.id)}">MAÇ ÖNİZLEME</a>
    </div>
    <div class="pteam">${crest(m.away)}<b>${esc(m.away.name)}</b><div class="form">${formDots(m.form_a)}</div></div>`;
}
function tick(){
  if(!FEAT||!FEAT.kickoff) return;
  const t = new Date(FEAT.kickoff).getTime() - Date.now();
  const s = Math.max(0, Math.floor(t/1000));
  $('cdh').textContent = String(Math.floor(s/3600)).padStart(2,'0');
  $('cdm').textContent = String(Math.floor((s%3600)/60)).padStart(2,'0');
  $('cds').textContent = String(s%60).padStart(2,'0');
}
async function openH2H(a,b){
  const d = await (await fetch(withLg(`/site/api/h2h?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),{cache:'no-store'})).json();
  const feat = (d.upcoming&&d.upcoming[0]) || FEAT;
  const ov = $('ov'); ov.className='ov on';
  ov.innerHTML = `<div class="ovc">${feat?kupon(feat):''}
    <button class="cta" style="width:100%;margin-top:12px" type="button" onclick="document.getElementById('ov').className='ov'">KAPAT</button></div>`;
}
async function load(){
  SUM = await (await fetch(withLg('/site/api/summary'),{cache:'no-store'})).json();
  paintLeagues(SUM.leagues||[]);
  FEAT = (SUM.today&&SUM.today[0]) || (SUM.next&&SUM.next[0]);
  $('kicker').textContent = (SUM.league||'SÜPER LİG')+' · '+(SUM.current||'');
  paintHero(FEAT);
  if(FEAT&&FEAT.id){
    document.querySelectorAll('a.cta').forEach(a=>{ a.href='/site/mac/'+encodeURIComponent(FEAT.id); });
    const vb=$('vsbox'); if(vb){ vb.style.cursor='pointer'; vb.onclick=()=>location.href='/site/mac/'+encodeURIComponent(FEAT.id); }
  }
  tick(); if(TMR) clearInterval(TMR); TMR=setInterval(tick,1000);
  $('rew').innerHTML = (SUM.teams||[]).map(t=>`
    <div class="rew" data-k="${t.key}">${t.crest?`<img src="${esc(t.crest)}" alt="">`:`<div class="fb" style="background:${t.color}">${esc(t.short)}</div>`}<span>${esc(t.short)}</span></div>`).join('');
  $('kgrid').innerHTML = (SUM.next||[]).slice(0,8).map(kupon).join('');
}
$('rew').addEventListener('click', async e=>{
  const b=e.target.closest('.rew'); if(!b) return;
  TEAM = TEAM===b.dataset.k ? '' : b.dataset.k;
  document.querySelectorAll('.rew').forEach(x=>x.classList.toggle('on', x.dataset.k===TEAM && TEAM));
  const qs = new URLSearchParams({status:'upcoming', season:(SUM&&SUM.current)||'2627'});
  if(TEAM) qs.set('team', TEAM);
  const rows = await (await fetch(withLg('/site/api/matches?'+qs),{cache:'no-store'})).json();
  $('kgrid').innerHTML = rows.slice(0,8).map(kupon).join('');
});
document.addEventListener('click', e=>{
  const b=e.target.closest('.kodds button'); if(!b) return;
  b.parentElement.querySelectorAll('button').forEach(x=>x.classList.toggle('on', x===b));
});
$('lgbar').addEventListener('click', e=>{
  const b=e.target.closest('.lgchip'); if(!b) return;
  LEAGUE = b.dataset.id || 'tr';
  TEAM='';
  const u=new URL(location.href);
  u.searchParams.set('league', LEAGUE);
  history.replaceState(null,'',u);
  load();
});
load();
</script>
</body>
</html>
"""
