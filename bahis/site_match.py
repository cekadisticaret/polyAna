""" /site/mac — maç detay, tüm pazarlar. Emir yok. """

SITE_MATCH_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Maç detay · MATCHDAY</title>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Oswald:wght@500;700&family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#080c14;--card:#101826;--line:rgba(245,197,24,.28);--y:#F5C518;--ink:#111;--txt:#fff;--muted:#9aa3b2}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:Inter,system-ui,sans-serif}
a{color:inherit;text-decoration:none}
.nav{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:16px;padding:14px 22px;background:rgba(8,12,20,.95);border-bottom:1px solid rgba(255,255,255,.06)}
.logo{font:700 15px Oswald,sans-serif;letter-spacing:.12em}
.logo i{display:inline-grid;place-items:center;width:32px;height:32px;border-radius:8px;background:var(--y);color:var(--ink);font-style:normal;margin-right:8px}
.cta{margin-left:auto;background:var(--y);color:var(--ink);border-radius:6px;padding:8px 14px;font:800 12px Oswald,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:22px 18px 56px}
.hero{text-align:center;padding:18px 0 10px}
.hero h1{font:italic 800 42px/1 Anton,sans-serif;color:var(--y)}
.vs{display:flex;align-items:center;justify-content:center;gap:22px;margin:16px 0}
.vs img,.fb{width:72px;height:72px;border-radius:50%;background:#fff;object-fit:contain}
.fb{display:grid;place-items:center;font-weight:800;color:#111}
.vs b{display:block;margin-top:6px;font:700 13px Oswald,sans-serif}
.pick{color:var(--y);font:700 16px Oswald,sans-serif;margin:8px 0}
.models{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:16px 0}
.mb{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;text-align:center}
.mb s{display:block;text-decoration:none;color:var(--y);font:700 10px Oswald,sans-serif;letter-spacing:.08em}
.mb b{display:block;font-size:13px;margin-top:4px}
.g{margin:22px 0 8px;font:700 13px Oswald,sans-serif;letter-spacing:.14em;color:var(--y)}
.note{font-size:12px;color:var(--muted);margin-bottom:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px}
.box s{display:block;text-decoration:none;color:var(--muted);font-size:10px;font-weight:700}
.box b{display:block;margin-top:4px;font-size:15px}
.box.on{border-color:var(--y);background:#1a1608}
.val{color:#22c55e;font-size:11px;font-weight:800}
.warn{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:8px 0 18px}
.wb{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.wb.bad{border-color:#e11d48;background:#1a0c10}
.wb s{display:block;text-decoration:none;color:var(--y);font:700 11px Oswald,sans-serif;letter-spacing:.08em}
.wb p{margin-top:6px;font-size:12px;color:#c8ced8;line-height:1.45}
@media(max-width:800px){.warn{grid-template-columns:1fr}}
.scores{display:flex;flex-wrap:wrap;gap:6px}
.scores i{font-style:normal;background:var(--card);border:1px solid var(--line);border-radius:99px;padding:4px 10px;font-size:12px;font-weight:800}
.prow{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #1c2430;font-size:13px;font-weight:700}
.prow img{width:28px;height:28px;border-radius:50%}
@media(max-width:800px){.models{grid-template-columns:repeat(2,1fr)}.hero h1{font-size:28px}}
</style>
</head>
<body>
<header class="nav">
  <a class="logo" href="/site"><i>⚽</i> MATCHDAY</a>
  <a href="/site/biten" style="font:600 12px Oswald,sans-serif;letter-spacing:.1em;color:#c5c9d1">BİTMİŞ</a>
  <a class="cta" href="/site">GERİ</a>
</header>
<div class="wrap">
  <div class="hero">
    <div class="note" id="when">—</div>
    <h1 id="ttl">MAÇ</h1>
    <div class="vs" id="vs"></div>
    <div class="pick" id="pick"></div>
    <div class="note" id="note"></div>
  </div>
  <div class="g">MODELLER</div>
  <div class="models" id="models"></div>
  <div class="g">VALUE · KELLY</div>
  <div class="grid" id="value"></div>
  <div class="g">ÖNEMLİ UYARILAR</div>
  <div class="warn" id="warn"></div>
  <div id="mk"></div>
</div>
<script>
const $ = id => document.getElementById(id);
const MID = decodeURIComponent(location.pathname.split('/mac/')[1]||'').replace(/\/$/,'');
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));}
function pct(p){return Math.round(Number(p||0)*100)}
function crest(t){
  if(t&&t.crest) return `<img src="${esc(t.crest)}" alt="">`;
  return `<div class="fb">${esc((t&&t.short)||'?')}</div>`;
}
function box(k,v,on){return `<div class="box${on?' on':''}"><s>${esc(k)}</s><b>${v}</b></div>`}
function sec(title, html, note){
  return `<div class="g">${esc(title)}</div>${note?`<div class="note">${esc(note)}</div>`:''}${html}`;
}
function grid(items){return `<div class="grid">${items.join('')}</div>`}
function maxKey(o){let k=null,m=-1; for(const [a,b] of Object.entries(o||{})){ if(Number(b)>m){m=Number(b);k=a;} } return k}
async function load(){
  const d = await (await fetch('/site/api/match?id='+encodeURIComponent(MID),{cache:'no-store'})).json();
  if(!d.ok){ $('ttl').textContent='Maç yok'; return; }
  const m=d.match, mk=d.markets, md=d.models;
  document.title = `${m.home.short} vs ${m.away.short} · MATCHDAY`;
  $('when').textContent = `${m.when||''} ${m.venue?('· '+m.venue):''} ${m.week?('· H'+m.week):''}`;
  $('ttl').textContent = 'IT\'S MATCHDAY';
  $('vs').innerHTML = `<div>${crest(m.home)}<b>${esc(m.home.name)}</b></div><div class="pick">VS</div><div>${crest(m.away)}<b>${esc(m.away.name)}</b></div>`;
  $('pick').textContent = `${d.text} · %${d.pct}`;
  const g=d.grade||{};
  if(g.played && g.hit!=null){
    $('pick').textContent += g.hit ? ` · TUTTU ${g.hg}–${g.ag}` : ` · TUTMADI ${g.hg}–${g.ag}`;
  } else if(g.played){
    $('pick').textContent += ` · skor ${g.hg}–${g.ag} · maç öncesi kilit yok`;
  }
  $('note').textContent = d.note||'';
  const row = (name,o)=> box(name, `1 ${pct(o['1'])} · X ${pct(o.X)} · 2 ${pct(o['2'])}`, false);
  $('models').innerHTML = [
    row('POISSON', md.poisson), row('ELO', md.elo), row('XG', md.xg),
    row('ENSEMBLE', md.ensemble), row('MONTE CARLO', md.monteCarlo),
    box('λ / μ', `${d.xg.home} / ${d.xg.away}`)
  ].join('');
  const ov=d.overround;
  const vextra = ov ? [box('overround', '%'+ov.pct+' · toplam %'+(ov.sum*100).toFixed(1)), box('¼ Kelly','tavan %3 · tam kasa yok')] : [box('¼ Kelly','tavan %3 · tam kasa yok')];
  $('value').innerHTML = (d.value||[]).map(v=>box(
    v.sel+' @ '+v.odds,
    v.isValue? `VALUE +${(v.edge*100).toFixed(1)}p · ${v.stake}` : `pas · ${(v.edge*100).toFixed(1)}p`,
    v.isValue
  )).concat(vextra).join('') || box('oran','yok');
  $('warn').innerHTML = (d.warnings||[]).map(w=>`<div class="wb${w.ok?'':' bad'}"><s>${esc(w.title)}</s><p>${esc(w.text)}</p></div>`).join('');
  const r=mk.result, top=maxKey(r);
  const parts=[];
  parts.push(sec('SONUÇ · 1X2', grid([
    box('1', '%'+pct(r['1']), top==='1'), box('X','%'+pct(r.X), top==='X'), box('2','%'+pct(r['2']), top==='2'),
    box('1X','%'+pct(mk.doubleChance['1X'])), box('12','%'+pct(mk.doubleChance['12'])), box('X2','%'+pct(mk.doubleChance.X2)),
  ]), '90 dk kim kazanır · çifte şans'));
  parts.push(sec('HANDİKAP', grid([
    box('0:1 ev −1 · 1', '%'+pct(mk.ah01['1'])), box('0:1 X', '%'+pct(mk.ah01.X)), box('0:1 2', '%'+pct(mk.ah01['2'])),
    box('1:0 dep −1 · 1', '%'+pct(mk.ah10['1'])), box('1:0 X', '%'+pct(mk.ah10.X)), box('1:0 2', '%'+pct(mk.ah10['2'])),
  ]), '0:1 / 1:0 avans'));
  parts.push(sec('DOĞRU SKOR', `<div class="scores">${(mk.correctScore||[]).map(s=>`<i>${esc(s.score)} <em style="color:var(--y);font-style:normal">%${s.pct}</em></i>`).join('')}</div>`));
  parts.push(sec('FARK', grid([
    box(m.home.short+' 1 fark', '%'+pct(mk.margin.h1)), box(m.home.short+' 2+', '%'+pct(mk.margin.h2p)),
    box(m.away.short+' 1 fark', '%'+pct(mk.margin.a1)), box(m.away.short+' 2+', '%'+pct(mk.margin.a2p)),
    box('Tur atlar', 'lig maçı · yok'),
  ])));
  const ou=mk.ou||{};
  parts.push(sec('KAÇ GOL', grid([
    ...['0.5','1.5','2.5','3.5','4.5','5.5'].map(l=>box(l+' alt/üst', `%${pct((ou[l]||{}).under)} / %${pct((ou[l]||{}).over)}`)),
    box('KG var', '%'+pct(mk.btts.yes)), box('KG yok', '%'+pct(mk.btts.no)),
    box('tek', '%'+pct(mk.oddEven.odd)), box('çift', '%'+pct(mk.oddEven.even)),
  ])));
  parts.push(sec('MS + 2.5  ·  KG + 2.5', grid([
    box('1 ve üst', '%'+pct(mk.ms25['1_over'])), box('1 ve alt', '%'+pct(mk.ms25['1_under'])),
    box('X ve üst', '%'+pct(mk.ms25.X_over)), box('X ve alt', '%'+pct(mk.ms25.X_under)),
    box('2 ve üst', '%'+pct(mk.ms25['2_over'])), box('2 ve alt', '%'+pct(mk.ms25['2_under'])),
    box('KG+üst', '%'+pct(mk.kg25.yes_over)), box('KG+alt', '%'+pct(mk.kg25.yes_under)),
    box('KG yok+üst', '%'+pct(mk.kg25.no_over)), box('KG yok+alt', '%'+pct(mk.kg25.no_under)),
  ])));
  parts.push(sec('EV / DEP ALT-ÜST', grid([
    box('Ev 0.5 A/Ü', `%${pct(mk.homeOu['0.5'].under)} / %${pct(mk.homeOu['0.5'].over)}`),
    box('Ev 1.5 A/Ü', `%${pct(mk.homeOu['1.5'].under)} / %${pct(mk.homeOu['1.5'].over)}`),
    box('Ev 2.5 A/Ü', `%${pct(mk.homeOu['2.5'].under)} / %${pct(mk.homeOu['2.5'].over)}`),
    box('Dep 0.5 A/Ü', `%${pct(mk.awayOu['0.5'].under)} / %${pct(mk.awayOu['0.5'].over)}`),
    box('Dep 1.5 A/Ü', `%${pct(mk.awayOu['1.5'].under)} / %${pct(mk.awayOu['1.5'].over)}`),
    box('Dep 2.5 A/Ü', `%${pct(mk.awayOu['2.5'].under)} / %${pct(mk.awayOu['2.5'].over)}`),
  ])));
  parts.push(sec('İLK GOL · ARALIK', grid([
    box('İlk gol ev', '%'+pct(mk.firstGoal.home)), box('İlk gol dep', '%'+pct(mk.firstGoal.away)), box('Golsüz', '%'+pct(mk.firstGoal.none)),
    ...(mk.goalWindows||[]).map(w=>box(w.k+"' gol olur", '%'+w.pct)),
  ]), 'Poisson bekleme · dakika verisi yok'));
  const iy=mk.iyMs||{};
  const sh=mk.sh||{};
  parts.push(sec('DEVRE', grid([
    box('İY 1', '%'+pct(mk.ht['1'])), box('İY X', '%'+pct(mk.ht.X)), box('İY 2', '%'+pct(mk.ht['2'])),
    box('2Y 1', '%'+pct(sh['1'])), box('2Y X', '%'+pct(sh.X)), box('2Y 2', '%'+pct(sh['2'])),
    box('İY 1.5 alt/üst', `%${pct(mk.htOu15.under)} / %${pct(mk.htOu15.over)}`),
    box('İY KG', '%'+pct(mk.htBtts)),
    box('1. yarı daha çok', '%'+pct(mk.halfMore.first)), box('2. yarı daha çok', '%'+pct(mk.halfMore.second)), box('eşit', '%'+pct(mk.halfMore.eq)),
    ...Object.entries(iy).map(([k,v])=>box('İY/MS '+k, '%'+pct(v))),
  ])));
  parts.push(sec('İY SKOR', `<div class="scores">${(mk.htScores||[]).map(s=>`<i>${esc(s.score)} <em style="color:var(--y);font-style:normal">%${s.pct}</em></i>`).join('')}</div>`));
  parts.push(sec('KORNER', grid([
    box('0–8', '%'+pct(mk.cornersBucket.le8)), box('9–11', '%'+pct(mk.cornersBucket['9_11'])), box('12+', '%'+pct(mk.cornersBucket.ge12)),
    ...Object.entries(mk.cornerOu||{}).map(([l,v])=>box(l+' A/Ü', `%${pct(v.under)} / %${pct(v.over)}`)),
    ...Object.entries(mk.htCornerOu||{}).map(([l,v])=>box('İY '+l+' A/Ü', `%${pct(v.under)} / %${pct(v.over)}`)),
    box('daha çok ev', '%'+pct(mk.cornerMore.home)), box('daha çok dep', '%'+pct(mk.cornerMore.away)),
    box('ilk korner ev', '%'+pct(mk.firstCorner.home)), box('ilk korner dep', '%'+pct(mk.firstCorner.away)),
    box('ev 8.5 A/Ü', `%${pct(mk.homeCornerOu['8.5'].under)} / %${pct(mk.homeCornerOu['8.5'].over)}`),
    box('dep 8.5 A/Ü', `%${pct(mk.awayCornerOu['8.5'].under)} / %${pct(mk.awayCornerOu['8.5'].over)}`),
  ]), 'Son 10 maç HC/AC Poisson + 6k sim'));
  parts.push(sec('KART', grid([
    box('kırmızı olur', '%'+pct(mk.redYes)),
    ...Object.entries(mk.cardOu||{}).map(([l,v])=>box('puan '+l+' A/Ü', `%${pct(v.under)} / %${pct(v.over)}`)),
    box('daha çok ev', '%'+pct(mk.cardMore.home)), box('daha çok dep', '%'+pct(mk.cardMore.away)), box('eşit', '%'+pct(mk.cardMore.eq)),
    box('ev 1.5 A/Ü', `%${pct((mk.homeCardOu['1.5']||{}).under)} / %${pct((mk.homeCardOu['1.5']||{}).over)}`),
    box('ev 2.5 A/Ü', `%${pct((mk.homeCardOu['2.5']||{}).under)} / %${pct((mk.homeCardOu['2.5']||{}).over)}`),
    box('dep 1.5 A/Ü', `%${pct((mk.awayCardOu['1.5']||{}).under)} / %${pct((mk.awayCardOu['1.5']||{}).over)}`),
    box('dep 2.5 A/Ü', `%${pct((mk.awayCardOu['2.5']||{}).under)} / %${pct((mk.awayCardOu['2.5']||{}).over)}`),
  ]), 'sarı 1 · kırmızı 2'));
  const sc=d.scorers||{};
  const col=(arr,t)=>(arr||[]).map(p=>`<div class="prow">${p.photo?`<img src="${esc(p.photo)}">`:''}<div>${esc(p.name)}<div class="note">${esc(t)} · herhangi %${pct(p.anyGoal)} · ilk %${pct(p.firstGoal)} · ${(p.stats&&p.stats.goals)||0}G · ${(p.stats&&p.stats.xg)||0} xG${p.yellow?(' · '+p.yellow+'S'):''}${p.pen?(' · pen '+p.pen):''}</div></div></div>`).join('');
  parts.push(sec('OYUNCU', `<div class="grid" style="grid-template-columns:1fr 1fr"><div>${col(sc.a,m.home.short)}</div><div>${col(sc.b,m.away.short)}</div></div>`, 'İlk / son / herhangi / sıradaki gol — xG payı · Fotmob'));
  const lv=mk.live||{}, tm=lv.tenMin||{};
  parts.push(sec('CANLI / DİĞER', grid([
    box('maç başladı', lv.started?'evet':'hayır'),
    box('kalanını kim', lv.remainWinner? (`1 ${pct(lv.remainWinner['1'])} · X ${pct(lv.remainWinner.X)} · 2 ${pct(lv.remainWinner['2'])}`) : 'maç öncesi kapalı'),
    box('10 dk gol', '%'+pct(tm.goal)),
    box('10 dk korner', '%'+pct(tm.corner)),
    box('10 dk kart', '%'+pct(tm.card)),
    box('uzatma', 'lig · yok'),
    box('tur', 'lig · yok'),
  ]), 'Canlı kalan-kazanan yalnız maç başladıysa; uzatma/tur ligde yok'));
  $('mk').innerHTML = parts.join('');
}
load();
</script>
</body>
</html>
"""
