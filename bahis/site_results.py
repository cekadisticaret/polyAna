""" /site/biten — bitmiş maçlar + tahmin isabeti. Emir yok. """

SITE_RESULTS_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bitmiş maçlar · MATCHDAY</title>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Oswald:wght@500;700&family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#080c14;--card:#101826;--line:rgba(245,197,24,.28);--y:#F5C518;--ink:#111;--txt:#fff;--muted:#9aa3b2;--ok:#22c55e;--no:#ef4444}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:Inter,system-ui,sans-serif}
a{color:inherit;text-decoration:none}
.nav{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:16px;padding:14px 22px;background:rgba(8,12,20,.95);border-bottom:1px solid rgba(255,255,255,.06)}
.logo{font:700 15px Oswald,sans-serif;letter-spacing:.12em}
.logo i{display:inline-grid;place-items:center;width:32px;height:32px;border-radius:8px;background:var(--y);color:var(--ink);font-style:normal;margin-right:8px}
.links{display:flex;gap:16px}
.links a{font:600 12px Oswald,sans-serif;letter-spacing:.1em;color:#c5c9d1}
.links a.on,.links a:hover{color:var(--y)}
.cta{margin-left:auto;background:var(--y);color:var(--ink);border-radius:6px;padding:8px 14px;font:800 12px Oswald,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:22px 18px 56px}
h1{font:italic 800 36px/1 Anton,sans-serif;color:var(--y);margin:8px 0 6px}
.note{font-size:13px;color:var(--muted);margin-bottom:16px}
.stat{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}
.stat b{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;font:700 13px Oswald,sans-serif}
.card{display:block;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:10px}
.card:hover{border-color:var(--y)}
.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.sc{font:italic 800 22px Anton,sans-serif;color:var(--y);min-width:72px}
.nm{font:700 14px Oswald,sans-serif}
.sub{font-size:12px;color:var(--muted);margin-top:2px}
.hit{margin-left:auto;font:800 11px Oswald,sans-serif;letter-spacing:.08em;border-radius:99px;padding:6px 10px}
.hit.ok{background:#12351f;color:var(--ok)}
.hit.no{background:#3a1218;color:var(--no)}
.hit.wait{background:#1a1608;color:var(--y)}
@media(max-width:640px){h1{font-size:26px}.sc{min-width:56px;font-size:18px}}
</style>
</head>
<body>
<header class="nav">
  <a class="logo" href="/site"><i>⚽</i> MATCHDAY</a>
  <nav class="links">
    <a href="/site">MAÇLAR</a>
    <a class="on" href="/site/biten">BİTMİŞ</a>
  </nav>
  <a class="cta" href="/site">GERİ</a>
</header>
<div class="wrap">
  <h1>BİTMİŞ MAÇLAR</h1>
  <div class="note" id="meta">yükleniyor…</div>
  <div class="stat" id="stat"></div>
  <div id="list"></div>
</div>
<script>
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));}
function when(k){
  if(!k) return '';
  try{ const d=new Date(k); return d.toLocaleString('tr-TR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}); }
  catch(e){ return k; }
}
function badge(m){
  if(m.hit===true) return '<span class="hit ok">TUTTU</span>';
  if(m.hit===false) return '<span class="hit no">TUTMADI</span>';
  return '<span class="hit wait">TAHMİN YOK</span>';
}
async function load(){
  const d = await (await fetch('/site/api/finished',{cache:'no-store'})).json();
  document.getElementById('meta').textContent =
    (d.note||'') + (d.updated?(' · güncelleme '+when(d.updated)):'') + (d.src&&d.src.length?(' · '+d.src.join(' + ')):'');
  document.getElementById('stat').innerHTML =
    `<b>${d.n||0} MAÇ</b><b>İSABET ${d.hits||0}/${d.graded_n||0}</b><b>WR ${d.wr==null?'—':('%'+d.wr)}</b>`;
  const rows = d.matches||[];
  document.getElementById('list').innerHTML = rows.map(m=>{
    const h=m.home||{}, a=m.away||{};
    const pred = m.pick==='1'?(h.short||h.name): m.pick==='2'?(a.short||a.name): 'X';
    const act = m.result==='1'?(h.short||'1'): m.result==='2'?(a.short||'2'): (m.result||'—');
    return `<a class="card" href="/site/mac/${encodeURIComponent(m.id)}">
      <div class="row">
        <div class="sc">${m.hg??'—'}–${m.ag??'—'}</div>
        <div>
          <div class="nm">${esc(h.name||m.home_name)} — ${esc(a.name||m.away_name)}</div>
          <div class="sub">${when(m.kickoff)}${m.week?(' · H'+m.week):''} · tahmin ${esc(pred)} · sonuç ${esc(act)}</div>
        </div>
        ${badge(m)}
      </div>
    </a>`;
  }).join('') || '<div class="note">Henüz bitmiş maç yok — cron sonuçları çekince dolacak.</div>';
}
load();
</script>
</body>
</html>
"""
