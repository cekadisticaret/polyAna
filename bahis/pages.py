"""BAHİS — Green Betting kit. POLY/KRİPTO şeridi yok."""

BAHIS_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Green Betting</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&display=swap" rel="stylesheet">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%2300ff88'/></svg>">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#121517; --card:#1a1f24; --card2:#22282e; --line:#2a3036;
  --txt:#fff; --muted:#8b9590; --g:#00ff88; --g2:#00df81;
  --ink:#08140c;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{min-height:100%;background:var(--bg);color:var(--txt);font-family:Manrope,system-ui,sans-serif}
body{display:flex}
.rail{
  width:76px;background:#0d1013;border-right:1px solid var(--line);
  display:flex;flex-direction:column;align-items:center;gap:10px;
  padding:18px 0;position:sticky;top:0;height:100vh;z-index:30;
}
.logo-dot{
  width:42px;height:42px;border-radius:13px;background:var(--g);color:var(--ink);
  font-weight:800;display:grid;place-items:center;box-shadow:0 0 24px rgba(0,255,136,.45);
}
.ric{
  width:44px;height:44px;border:0;border-radius:12px;background:transparent;color:#5d6662;cursor:default;
  display:grid;place-items:center;
}
.ric.on{background:var(--g);color:var(--ink);box-shadow:0 0 16px rgba(0,255,136,.35)}
.ric svg{width:20px;height:20px}
.stage{flex:1;min-width:0}
.top{
  height:68px;display:flex;align-items:center;gap:18px;padding:0 28px;
  background:rgba(13,16,19,.92);border-bottom:1px solid var(--line);
  position:sticky;top:0;z-index:20;backdrop-filter:blur(14px);
}
.word{font-weight:800;letter-spacing:.08em;font-size:14px}
.word i{font-style:normal;color:var(--g)}
.tabs{display:flex;background:#171b1f;border-radius:999px;padding:4px}
.tab{border:0;background:transparent;color:#6e7773;font:800 11px/1 Manrope,sans-serif;letter-spacing:.1em;padding:9px 18px;border-radius:999px}
.tab.on{background:var(--g);color:var(--ink)}
.sp{flex:1}
.ico{width:36px;height:36px;border-radius:50%;border:1px solid var(--line);background:#171b1f;color:#9aa39e;display:grid;place-items:center}
.ava{width:38px;height:38px;border-radius:50%;border:2px solid var(--g);box-shadow:0 0 12px rgba(0,255,136,.4);background:#111}
.page{padding:22px 26px 48px;max-width:1380px;margin:0 auto}
.shell{display:grid;grid-template-columns:minmax(0,1fr) 272px;gap:16px;align-items:start}
.mk{
  position:sticky;top:84px;background:var(--card);border:1px solid var(--line);
  border-radius:18px;padding:14px 14px 16px;max-height:calc(100vh - 100px);overflow:auto;
}
.mk h3{font-size:11px;letter-spacing:.1em;color:var(--g);margin-bottom:4px}
.mk .note{font-size:10px;color:var(--muted);line-height:1.4;margin-bottom:10px}
.mk .g{font-size:10px;font-weight:800;letter-spacing:.08em;color:#6e7773;margin:10px 0 5px;text-transform:uppercase}
.mk li{list-style:none;font-size:12px;font-weight:700;padding:4px 0;border-bottom:1px solid #242a2e;color:#e8eeea}
.mk li span{display:block;font-size:10px;color:var(--muted);font-weight:600;margin-top:1px}
.hero{
  display:flex;align-items:center;gap:22px;padding:18px 22px;margin-bottom:16px;
  background:linear-gradient(180deg,#1c2227,#161b1f);border:1px solid var(--line);border-radius:22px;
}
.glow-ring{
  width:86px;height:86px;border-radius:50%;flex-shrink:0;
  background:conic-gradient(var(--g) 70%, #2a3330 0);
  display:grid;place-items:center;box-shadow:0 0 28px rgba(0,255,136,.25);
}
.glow-ring b{width:68px;height:68px;border-radius:50%;background:#121517;display:grid;place-items:center;font-size:13px;letter-spacing:.06em}
.hero h1{font-size:22px;letter-spacing:.04em}
.hero p{color:var(--muted);font-size:12px;margin-top:4px}
.trow{display:flex;gap:10px;flex-wrap:wrap;margin-left:auto}
.tcirc{
  width:46px;height:46px;border-radius:50%;border:1px solid var(--line);background:#171b1f;
  overflow:hidden;cursor:pointer;display:grid;place-items:center;font-size:9px;font-weight:800;
}
.tcirc.on{border-color:var(--g);box-shadow:0 0 12px rgba(0,255,136,.35)}
.tcirc img{width:100%;height:100%;object-fit:contain;background:#fff}
.liveb{
  display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;
  padding:14px 20px;margin-bottom:16px;border-radius:18px;
  background:linear-gradient(90deg,#171d1a,#1a1f24);border:1px solid #2a3a32;
  cursor:pointer;
}
.lteam{display:flex;align-items:center;gap:10px;font-weight:800;min-width:160px}
.lteam img,.crest{
  width:36px;height:36px;border-radius:50%;object-fit:contain;background:#fff;
  border:2px solid #2a3036;
}
.crest.fb{background:var(--c,#333);color:#fff;display:grid;place-items:center;font-size:10px;font-weight:800}
.lmid{text-align:center}
.lpill{
  display:inline-block;background:var(--g);color:var(--ink);font:800 10px/1 Manrope,sans-serif;
  letter-spacing:.12em;padding:4px 10px;border-radius:999px;box-shadow:0 0 12px rgba(0,255,136,.45);
}
.lscore{font-size:28px;font-weight:800;letter-spacing:2px;margin-top:4px}
.ltime{font-size:11px;color:var(--muted);margin-top:2px}
.row3{display:grid;grid-template-columns:360px 1fr 280px;gap:14px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px;box-shadow:0 12px 28px rgba(0,0,0,.28)}
.motd{padding:0;overflow:visible;background:transparent;border:0;box-shadow:none}
.club{width:90px;text-align:center}
.ped{
  width:72px;height:72px;margin:0 auto 6px;border-radius:50%;
  background:radial-gradient(circle at 50% 40%, #fff 0 42%, transparent 43%), var(--c,#333);
  box-shadow:0 10px 0 #0a0d0c, 0 0 22px rgba(0,255,136,.2);overflow:hidden;
  display:grid;place-items:center;
}
.ped img{width:70%;height:70%;object-fit:contain}
.ped span{font-weight:800;font-size:14px}
.cn{font-size:11px;font-weight:800}
.ms{font-size:34px;font-weight:800;letter-spacing:-1px}
.bcard{
  position:relative;background:#14181c;border:1px solid #2a3036;border-radius:28px;
  padding:18px 16px 14px;box-shadow:0 0 0 1px rgba(0,255,136,.05),0 18px 40px rgba(0,0,0,.42);
}
.bhead{display:grid;grid-template-columns:1fr 88px 1fr;align-items:start;position:relative;min-height:118px;margin-bottom:8px}
.bcrest{
  width:76px;height:76px;border-radius:50%;margin:0 auto;
  background:var(--c,#222);display:grid;place-items:center;overflow:hidden;
  box-shadow:0 0 0 4px #1a1f24, 0 8px 18px rgba(0,0,0,.45);
}
.bcrest img{width:62%;height:62%;object-fit:contain}
.bcrest span{font-weight:800;font-size:15px}
.bshort{text-align:center;font-weight:800;font-size:13px;letter-spacing:.06em;margin-top:8px}
.bvs{text-align:center;padding-top:14px}
.bvs-t{font-size:22px;font-weight:800;letter-spacing:.14em}
.bwhen{font-size:11px;color:var(--muted);margin-top:4px;font-weight:700}
.btip{
  position:absolute;left:12%;right:12%;top:46px;z-index:3;margin:0;padding:9px 10px 7px;
  border-radius:14px;background:rgba(12,28,18,.92);
  border:1px solid rgba(0,255,136,.38);color:var(--g);
  font-size:12px;font-weight:800;text-align:center;line-height:1.35;
  backdrop-filter:blur(10px);
}
.btip small{display:block;color:#8b9590;font-weight:700;margin-top:3px;font-size:10px}
.tip{
  margin:8px 0 2px;padding:6px 10px;border-radius:10px;
  background:rgba(0,255,136,.12);border:1px solid rgba(0,255,136,.35);
  color:var(--g);font-size:11px;font-weight:800;text-align:center;line-height:1.35;
}
.tip small{display:block;color:#8b9590;font-weight:700;margin-top:2px}
.odds{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
.ob{
  background:#101417;border:1.5px solid #2a3036;border-radius:12px;padding:9px 4px;
  text-align:center;cursor:pointer;color:#fff;
}
.ob:hover,.ob.on{border-color:var(--g);background:rgba(0,255,136,.08)}
.ob s{display:block;text-decoration:none;color:var(--muted);font-size:10px;font-weight:700}
.ob b{display:block;margin-top:2px;font-size:16px}
.pbet{
  display:block;text-align:center;text-decoration:none;
  width:100%;margin-top:12px;border:0;border-radius:999px;padding:13px;
  background:var(--g);color:var(--ink);font:800 13px Manrope,sans-serif;
  letter-spacing:.1em;cursor:pointer;box-shadow:0 0 22px rgba(0,255,136,.4);
}
.gstat{
  background:linear-gradient(160deg,#00ff88,#00c46a);color:var(--ink);border:0;
  display:flex;flex-direction:column;justify-content:center;gap:10px;
}
.gstat .n{font-size:42px;font-weight:800;line-height:1}
.gstat .l{font-size:12px;font-weight:800;opacity:.75;text-transform:uppercase;letter-spacing:.06em}
.sec{font-size:10px;font-weight:800;letter-spacing:.12em;color:var(--muted);margin-bottom:10px}
.latest{display:flex;flex-direction:column;gap:8px}
.lrow{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700}
.lnum{width:20px;height:20px;border-radius:50%;background:var(--g);color:var(--ink);display:grid;place-items:center;font-size:10px;font-weight:800}
.charts{display:grid;grid-template-columns:1.1fr .9fr .9fr;gap:14px;margin-bottom:16px}
.cv{height:210px}
.cmp{
  display:grid;grid-template-columns:1fr 220px 1fr;gap:10px;align-items:center;
  padding:18px;margin-bottom:16px;
}
.statue{display:flex;flex-direction:column;align-items:center}
.statue .ped{width:110px;height:110px;box-shadow:0 14px 0 #0a0d0c, 0 0 30px rgba(0,255,136,.28)}
.st{display:flex;flex-direction:column;gap:7px}
.st-row{display:grid;grid-template-columns:40px 1fr 40px;gap:8px;align-items:center;font-size:11px;font-weight:800}
.st-bar{height:6px;background:#2a3036;border-radius:99px;overflow:hidden;display:flex}
.st-bar i{height:100%;background:var(--g)}
.st-bar b{height:100%;background:#3d4650;margin-left:auto}
.gridm{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:16px}
.mc{padding:0;background:transparent;border:0}
.hist{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px}
.hrow{
  display:grid;grid-template-columns:90px 1fr 70px;gap:10px;align-items:center;
  padding:10px 0;border-bottom:1px solid #242a2e;cursor:pointer;font-size:13px;font-weight:700;
}
.foot{
  margin-top:18px;border-radius:20px;padding:28px 24px;text-align:center;
  background:linear-gradient(90deg,#15201a,#1a1f24 40%,#15201a);
  border:1px solid #2a3a32;
}
.foot b{font-size:28px;letter-spacing:.04em}
.foot b i{font-style:normal;color:var(--g)}
.foot p{color:var(--muted);margin-top:6px}
.ov{
  position:fixed;inset:0;background:rgba(0,0,0,.62);z-index:50;display:none;align-items:center;justify-content:center;padding:20px;
}
.ov.on{display:flex}
.ovc{width:min(720px,100%);max-height:92vh;overflow:auto;background:#161b1f;border:1px solid var(--line);border-radius:22px;padding:20px}
.ptabs{display:flex;gap:8px;margin:0 0 16px;flex-wrap:wrap}
.ptab{border:0;background:#171b1f;color:#6e7773;font:800 11px/1 Manrope,sans-serif;letter-spacing:.1em;padding:10px 16px;border-radius:999px;cursor:pointer}
.ptab.on{background:var(--g);color:var(--ink)}
#pane-p,#pane-t{display:none}
.tnote{color:var(--muted);font-size:12px;margin:-4px 0 14px;line-height:1.45}
.tgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-bottom:16px}
.tcard{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:16px;cursor:pointer}
.tcard .when{font-size:11px;color:var(--muted);font-weight:700;margin-bottom:10px}
.tcard .vs{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center;margin-bottom:12px}
.tcard .vs .side{text-align:center}
.tcard .vs .nm{font-weight:800;font-size:13px;margin-top:6px}
.tcard .xg{font-size:11px;color:var(--muted);font-weight:700}
.tpick{
  margin:0 0 12px;padding:8px 10px;border-radius:12px;text-align:center;
  background:rgba(0,255,136,.12);border:1px solid rgba(0,255,136,.35);
  color:var(--g);font-weight:800;font-size:13px;
}
.tpick small{display:block;color:#8b9590;font-size:10px;margin-top:3px}
.tbar{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:10px}
.tbar .ob{cursor:default}
.tmk{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}
.tmk .box{background:#101417;border:1px solid #2a3036;border-radius:12px;padding:8px 10px}
.tmk .box s{display:block;text-decoration:none;color:var(--muted);font-size:10px;font-weight:700}
.tmk .box b{display:block;margin-top:2px;font-size:14px}
.tsc{display:flex;flex-wrap:wrap;gap:6px}
.tsc i{font-style:normal;background:#101417;border:1px solid #2a3036;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:800}
.tsc i em{font-style:normal;color:var(--g);margin-left:4px}
.vbadge{display:inline-block;margin-left:6px;background:var(--g);color:var(--ink);font-size:9px;font-weight:800;letter-spacing:.08em;padding:2px 6px;border-radius:999px}
.tstr{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.tstr .chip{background:#171b1f;border:1px solid var(--line);border-radius:999px;padding:5px 10px;font-size:11px;font-weight:700;color:#c8d0cc}
.tcard.kind-elo{border-color:#f5c518}
.tcard.kind-bankroll{border-color:#00ff88}
.tcard.pas{opacity:.62}
.elo-n{font-size:28px;font-weight:800;letter-spacing:-1px;line-height:1}
.elo-d{font-size:11px;color:var(--muted);font-weight:700;margin-top:4px}
.erow{display:grid;grid-template-columns:90px 54px 58px 70px 1fr;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid #242a2e;font-size:12px;font-weight:700}
.erow .ok{color:var(--g)}
.erow .no{color:#8b9590}
.pbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.pbar select,.pbar input{
  background:#171b1f;border:1px solid var(--line);color:#fff;border-radius:10px;
  padding:8px 10px;font:700 12px Manrope,sans-serif;
}
.pchip{
  border:1px solid var(--line);background:#171b1f;color:#9aa39e;border-radius:999px;
  padding:6px 10px;font:800 10px Manrope,sans-serif;letter-spacing:.06em;cursor:pointer;
}
.pchip.on{border-color:var(--g);color:var(--ink);background:var(--g)}
.plead{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:14px}
.pcard{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:12px}
.pcard .h{font-size:10px;letter-spacing:.1em;color:var(--muted);font-weight:800;margin-bottom:8px}
.prow{display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid #242a2e;cursor:pointer;font-size:12px;font-weight:700}
.prow img,.pface{width:28px;height:28px;border-radius:50%;object-fit:cover;background:#222}
.pface{display:grid;place-items:center;font-size:9px;font-weight:800}
.pval{margin-left:auto;color:var(--g);font-weight:800}
.ptable{width:100%;border-collapse:collapse;font-size:12px}
.ptable th{text-align:left;font-size:10px;letter-spacing:.08em;color:var(--muted);padding:6px 4px;cursor:pointer}
.ptable td{padding:7px 4px;border-top:1px solid #242a2e}
.ptable tr{cursor:pointer}
.ptable tr:hover td{background:#1c2227}
.psquad{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}
@media(max-width:1100px){
  .row3,.charts,.cmp,.gridm,.plead,.psquad,.tgrid{grid-template-columns:1fr}
  .rail{display:none}
  .trow{display:none}
  .shell{grid-template-columns:1fr}
}
</style>
</head>
<body data-world="bahis">
<aside class="rail">
  <div class="logo-dot">GB</div>
  <button class="ric on" type="button" title="Futbol"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 3a15 15 0 010 18M12 3a15 15 0 000 18M3 12h18"/></svg></button>
  <button class="ric" type="button" title="Basket"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 3c3 3 3 15 0 18M3 12c3-2 15-2 18 0"/></svg></button>
  <button class="ric" type="button" title="Tenis"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M4 8c6 2 10 6 12 12"/></svg></button>
</aside>
<div class="stage">
  <header class="top">
    <div class="word">GREEN <i>BETTING</i></div>
    <div class="tabs">
      <button class="tab" type="button">CASINO</button>
      <button class="tab on" type="button">SPORT</button>
      <a class="tab" href="/site" style="display:inline-flex;align-items:center">SITE</a>
    </div>
    <div class="sp"></div>
    <div class="ico">⌕</div>
    <div class="ico">◎</div>
    <div class="ava"></div>
  </header>
  <div class="page">
  <div class="shell">
  <div>
    <section class="hero">
      <div class="glow-ring"><b>1.LİG</b></div>
      <div>
        <h1 id="ttl">SÜPER LİG</h1>
        <p id="sub">Son 10 yıl · kim kiminle oynayacak</p>
      </div>
      <div class="trow" id="trow"></div>
    </section>

    <div class="ptabs" id="ptabs">
      <button class="ptab on" type="button" data-pane="m">MAÇLAR</button>
      <button class="ptab" type="button" data-pane="p">OYUNCULAR</button>
      <button class="ptab" type="button" data-pane="t" data-engine="dixon">DIXON-COLES</button>
      <button class="ptab" type="button" data-pane="t" data-engine="elo">ELO</button>
      <button class="ptab" type="button" data-pane="t" data-engine="bankroll">BANKROLL</button>
    </div>

    <div id="pane-m">
    <div class="liveb" id="liveb"></div>

    <div class="row3">
      <div class="card motd" id="motd"></div>
      <div class="card gstat" id="gstat"></div>
      <div class="card">
        <div class="sec">GOL TRENDİ</div>
        <canvas id="line" class="cv"></canvas>
      </div>
    </div>

    <div class="charts">
      <div class="card">
        <div class="sec">SON MAÇLAR</div>
        <div class="latest" id="latest"></div>
      </div>
      <div class="card">
        <div class="sec">VICTORY ANALYTICS</div>
        <canvas id="radar" class="cv"></canvas>
      </div>
      <div class="card">
        <div class="sec">H2H PAY</div>
        <canvas id="donut" class="cv"></canvas>
      </div>
    </div>

    <div class="card cmp" id="cmp"></div>

    <div class="sec">KİM KİMLE · FİKSTÜR</div>
    <div class="gridm" id="gridm"></div>

    <div class="hist">
      <div class="sec">10 YIL · BÜTÜN MAÇLAR</div>
      <div id="hist"></div>
    </div>

    <div class="foot">
      <b>GREEN <i>BETTING</i></b>
      <p>1. Lig takımları · son 10 sezon · çıkarım, emir yok</p>
    </div>
    </div>

    <div id="pane-p">
      <div class="pbar">
        <select id="psea"></select>
        <input id="pq" type="search" placeholder="oyuncu / takım" />
        <button class="pchip on" type="button" data-stat="goals">GOL</button>
        <button class="pchip" type="button" data-stat="assists">ASİST</button>
        <button class="pchip" type="button" data-stat="ga">G+A</button>
        <button class="pchip" type="button" data-stat="xg">xG</button>
        <button class="pchip" type="button" data-stat="xa">xA</button>
        <button class="pchip" type="button" data-stat="rating">PUAN</button>
        <button class="pchip" type="button" data-stat="yellow">SARI</button>
        <button class="pchip" type="button" data-stat="red">KIRMIZI</button>
        <button class="pchip" type="button" data-stat="clean_sheets">CS</button>
        <button class="pchip" type="button" data-stat="minutes">DK</button>
      </div>
      <div class="plead" id="plead"></div>
      <div class="card" style="padding:12px 14px;margin-bottom:14px;overflow:auto">
        <div class="sec" id="pttl">OYUNCU TABLOSU</div>
        <table class="ptable" id="ptable"></table>
      </div>
      <div class="psquad" id="psquad"></div>
    </div>

    <div id="pane-t">
      <p class="tnote" id="tmeta">Dixon-Coles · yakın fikstür</p>
      <div class="tstr" id="tstr"></div>
      <div class="tgrid" id="tgrid"></div>
    </div>
  </div>
  <aside class="mk">
    <h3>TR KURUM MARKETLERİ</h3>
    <div class="note">Nesine · Bilyoner · Misli · Tuttur · Birebin · Oley — hepsi İddaa / MBY planı. Bu sayfa kupon açmaz.</div>
    <div class="g">Sonuç</div>
    <ul>
      <li>Maç sonucu (1-X-2)<span>90 dk kim kazanır</span></li>
      <li>Çifte şans<span>1X · 12 · X2</span></li>
      <li>Handikaplı maç sonucu<span>0:1 / 1:0 avans</span></li>
      <li>Doğru skor / maç skoru</li>
      <li>Hangi takım kaç farkla kazanır</li>
      <li>Hangi takım tur atlar</li>
    </ul>
    <div class="g">Kaç gol</div>
    <ul>
      <li>Toplam gol alt/üst<span>0.5 … 5.5</span></li>
      <li>Karşılıklı gol var/yok</li>
      <li>MS + 2.5 alt/üst</li>
      <li>KG + 2.5 alt/üst</li>
      <li>Ev / deplasman alt-üst</li>
      <li>Toplam gol tek/çift</li>
      <li>İlk golü hangi takım atar</li>
      <li>Gol hangi aralıkta olur</li>
    </ul>
    <div class="g">Devre</div>
    <ul>
      <li>İlk yarı sonucu · 2. yarı sonucu</li>
      <li>İY / maç sonucu (1/1 …)</li>
      <li>İY 1.5 gol A/Ü</li>
      <li>Hangi yarıda daha çok gol</li>
      <li>İY karşılıklı gol · İY skoru</li>
    </ul>
    <div class="g">Kaç korner</div>
    <ul>
      <li>Korner sayısı<span>0–8 · 9–11 · 12+</span></li>
      <li>Korner alt/üst</li>
      <li>İY korner sayısı / A/Ü</li>
      <li>Kim daha çok korner kullanır</li>
      <li>İlk korneri kim kullanır</li>
      <li>Ev / dep. korner A/Ü</li>
    </ul>
    <div class="g">Kart</div>
    <ul>
      <li>Kırmızı kart olur mu</li>
      <li>Toplam kart puanı A/Ü<span>sarı 1 · kırmızı 2</span></li>
      <li>Hangi takım daha fazla kart görür</li>
      <li>Ev / dep. kart puanı A/Ü</li>
    </ul>
    <div class="g">Oyuncu</div>
    <ul>
      <li>İlk / son / herhangi gol atan</li>
      <li>Sıradaki golü kim atar</li>
      <li>Oyuncu özel (penaltı, kart…)</li>
    </ul>
    <div class="g">Canlı / diğer</div>
    <ul>
      <li>Kalanını kim kazanır</li>
      <li>10 dk aralık gol / korner / kart</li>
      <li>Uzatma olur mu · uzatma A/Ü</li>
    </ul>
  </aside>
  </div>
  </div>
</div>
<div class="ov" id="ov" onclick="if(event.target===this)this.className='ov'"></div>
<script type="application/json" id="engines-json">__ENGINES__</script>
<script>
const $ = id => document.getElementById(id);
const ENGINES = (()=>{ try{ return JSON.parse(($('engines-json').textContent||'[]').trim()); }catch(e){ return []; } })();
let SUM=null, TEAM='', CH={}, PLAY=null, PSTAT='goals', PSEA='', PRED=null, ENGINE=(ENGINES[0]&&ENGINES[0].id)||'';

function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));}
function crest(t, cls){
  if(t&&t.crest) return `<img class="${cls||'crest'}" src="${esc(t.crest)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'crest fb',style:'--c:${t.color}',textContent:'${esc(t.short)}'}))">`;
  return `<div class="crest fb" style="--c:${t.color||'#333'}">${esc(t.short||'?')}</div>`;
}
function ped(t, big){
  const img = t.crest ? `<img src="${esc(t.crest)}" alt="" onerror="this.remove()">` : `<span>${esc(t.short)}</span>`;
  return `<div class="ped" style="--c:${t.color||'#333'};${big?'width:110px;height:110px':''}">${img}</div>`;
}
function tipBox(m){
  const t=m.tip; if(!t) return '';
  return `<div class="tip">${esc(t.text)} · %${t.pct}<small>${esc(t.why||'')}</small></div>`;
}
function bcrest(t){
  const img = t.crest ? `<img src="${esc(t.crest)}" alt="" onerror="this.remove()">` : `<span>${esc(t.short||'?')}</span>`;
  return `<div class="bcrest" style="--c:${t.color||'#222'}">${img}</div>`;
}
function odds(m){
  const o=m.odds||{}, f=v=>v==null?'—':Number(v).toFixed(2);
  const p=(m.tip&&m.tip.pick)||'';
  return `<div class="odds">
    <button class="ob${p==='H'?' on':''}" type="button" data-pick="H"><s>1</s><b>${f(o.home)}</b></button>
    <button class="ob${p==='D'?' on':''}" type="button" data-pick="D"><s>X</s><b>${f(o.draw)}</b></button>
    <button class="ob${p==='A'?' on':''}" type="button" data-pick="A"><s>2</s><b>${f(o.away)}</b></button>
  </div>`;
}
function betCard(m){
  const t=m.tip;
  const tip = t ? `<div class="btip">${esc(t.text)} · %${t.pct}<small>${esc(t.why||'')}</small></div>` : '';
  return `<div class="bcard" data-id="${esc(m.id||'')}" data-h="${esc(m.home.key)}" data-a="${esc(m.away.key)}">
    <div class="bhead">
      <div>${bcrest(m.home)}<div class="bshort">${esc(m.home.short)}</div></div>
      <div class="bvs"><div class="bvs-t">${m.played? `${m.hg}:${m.ag}` : 'VS'}</div><div class="bwhen">${esc(m.when||'')}</div></div>
      <div>${bcrest(m.away)}<div class="bshort">${esc(m.away.short)}</div></div>
      ${tip}
    </div>
    ${odds(m)}
    <a class="pbet" href="/site/mac/${encodeURIComponent(m.id||'')}">MAÇ DETAY</a>
  </div>`;
}
function kill(c){ if(CH[c]){ CH[c].destroy(); CH[c]=null; } }

function paintLive(m){
  if(!m){ $('liveb').style.display='none'; return; }
  const sc = m.played ? `${m.hg}  -  ${m.ag}` : 'VS';
  $('liveb').onclick = () => { if(m.id) location.href='/site/mac/'+encodeURIComponent(m.id); else openH2H(m.home.key, m.away.key); };
  $('liveb').innerHTML = `
    <div class="lteam">${crest(m.home)} ${esc(m.home.name)}</div>
    <div class="lmid">
      <div class="lpill">${m.played?'MS':'LIVE'}</div>
      <div class="lscore">${sc}</div>
      ${m.tip?`<div class="tip" style="margin:6px auto 0;max-width:240px">${esc(m.tip.text)} · %${m.tip.pct}</div>`:''}
      <div class="ltime">${esc(m.when)}${m.week?' · H'+m.week:''}</div>
    </div>
    <div class="lteam" style="justify-content:flex-end">${esc(m.away.name)} ${crest(m.away)}</div>`;
}

function paintMotd(m){
  if(!m){ $('motd').innerHTML=''; return; }
  $('motd').innerHTML = betCard(m);
}

function lineChart(){
  kill('line');
  const g = SUM.goals_by_season||[];
  CH.line = new Chart($('line'), {
    type:'line',
    data:{
      labels:g.map(x=>x.label.replace('20','')),
      datasets:[{data:g.map(x=>x.goals), borderColor:'#00ff88', backgroundColor:'rgba(0,255,136,.15)',
        fill:true, tension:.45, pointBackgroundColor:'#00ff88', pointRadius:4, borderWidth:3}]
    },
    options:{plugins:{legend:{display:false}}, scales:{x:{ticks:{color:'#8b9590'},grid:{display:false}}, y:{ticks:{color:'#8b9590'},grid:{color:'#242a2e'}}}}
  });
}

function paintLatest(){
  $('latest').innerHTML = (SUM.latest||[]).map((m,i)=>`
    <div class="lrow" onclick="location.href='/site/mac/'+encodeURIComponent('${esc(m.id||'')}')">
      <div class="lnum">${i+1}</div>${crest(m.home)}
      <div>${esc(m.home.short)} ${m.hg}–${m.ag} ${esc(m.away.short)}</div>
    </div>`).join('');
}

function paintCmp(d){
  if(!d){ $('cmp').innerHTML=''; return; }
  const tot = Math.max(1, d.n);
  const rows = [
    ['Maç', d.n, d.n],
    ['Galibiyet', d.home_w, d.away_w],
    ['Beraberlik', d.draw, d.draw],
    ['Gol', d.gf, d.ga],
  ];
  $('cmp').innerHTML = `
    <div class="statue">${ped(d.a,true)}<div class="cn">${esc(d.a.name)}</div></div>
    <div class="st">
      <div class="sec" style="text-align:center">STATISTIC · 10 YIL</div>
      ${rows.map(([l,a,b])=>`
        <div class="st-row"><span>${a}</span>
          <div><div style="text-align:center;font-size:10px;color:#8b9590;margin-bottom:3px">${l}</div>
          <div class="st-bar"><i style="width:${(a/Math.max(a,b,1)*50).toFixed(0)}%"></i><b style="width:${(b/Math.max(a,b,1)*50).toFixed(0)}%"></b></div></div>
        <span style="text-align:right">${b}</span></div>`).join('')}
    </div>
    <div class="statue">${ped(d.b,true)}<div class="cn">${esc(d.b.name)}</div></div>`;
}

function chartsH2H(d){
  kill('radar'); kill('donut');
  if(!d) return;
  CH.radar = new Chart($('radar'), {
    type:'radar',
    data:{
      labels:['Galibiyet','Beraberlik','Gol','Yenen','Form'],
      datasets:[
        {label:d.a.short, data:[d.home_w,d.draw,d.gf,d.ga,(d.form_a||[]).filter(x=>x==='W').length],
          borderColor:'#00ff88', backgroundColor:'rgba(0,255,136,.22)', pointBackgroundColor:'#00ff88'},
        {label:d.b.short, data:[d.away_w,d.draw,d.ga,d.gf,(d.form_b||[]).filter(x=>x==='W').length],
          borderColor:'#f5c518', backgroundColor:'rgba(245,197,24,.15)', pointBackgroundColor:'#f5c518'}
      ]
    },
    options:{plugins:{legend:{labels:{color:'#ccc',boxWidth:10}}}, scales:{r:{angleLines:{color:'#2a3036'},grid:{color:'#2a3036'},pointLabels:{color:'#8b9590'},ticks:{display:false}}}}
  });
  CH.donut = new Chart($('donut'), {
    type:'doughnut',
    data:{
      labels:[d.a.short,'X',d.b.short],
      datasets:[{data:[d.home_w,d.draw,d.away_w], backgroundColor:['#00ff88','#3d4650','#f5c518'], borderWidth:0}]
    },
    options:{cutout:'68%', plugins:{legend:{labels:{color:'#ccc'}}}}
  });
}

function paintGrid(rows){
  $('gridm').innerHTML = (rows||[]).slice(0,9).map(m=>`<div class="mc">${betCard(m)}</div>`).join('');
}

async function loadSum(){
  SUM = await (await fetch('/bahis/api/summary',{cache:'no-store'})).json();
  $('ttl').textContent = (SUM.league||'SÜPER LİG').toUpperCase();
  $('sub').textContent = `${SUM.played_n} maç · ${SUM.upcoming_n} fikstür · 10 sezon`;
  $('trow').innerHTML = (SUM.teams||[]).map(t=>`
    <button class="tcirc" data-k="${t.key}" type="button" title="${esc(t.name)}">${t.crest?`<img src="${esc(t.crest)}" alt="">`:esc(t.short)}</button>`).join('');
  $('gstat').innerHTML = `
    <div><div class="n">${SUM.played_n}</div><div class="l">Games · 10 yıl</div></div>
    <div><div class="n">${SUM.upcoming_n}</div><div class="l">Sıradaki fikstür</div></div>
    <div><div class="n">${SUM.teams.length}</div><div class="l">1. Lig takım</div></div>`;
  const feat = (SUM.today&&SUM.today[0]) || (SUM.next&&SUM.next[0]);
  paintLive(feat);
  paintMotd(feat);
  paintLatest();
  lineChart();
  paintGrid(SUM.next);
  if(feat) await openH2H(feat.home.key, feat.away.key, true);
  loadHist();
}

async function loadHist(){
  const qs = new URLSearchParams({status:'played'});
  if(TEAM) qs.set('team', TEAM);
  const rows = await (await fetch('/bahis/api/matches?'+qs,{cache:'no-store'})).json();
  $('hist').innerHTML = rows.slice(0,40).map(m=>`
    <div class="hrow" onclick="location.href='/site/mac/'+encodeURIComponent('${esc(m.id||'')}')">
      <div>${esc(m.when)}</div>
      <div>${esc(m.home.name)} <b>${m.hg}–${m.ag}</b> ${esc(m.away.name)}</div>
      <div>${esc(m.season_label)}</div>
    </div>`).join('') || '<div class="ltime">Maç yok</div>';
}

async function openH2H(a,b, silent){
  const d = await (await fetch(`/bahis/api/h2h?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,{cache:'no-store'})).json();
  paintCmp(d);
  chartsH2H(d);
  if(silent) return;
  const ov = $('ov');
  ov.className = 'ov on';
  const feat = (d.upcoming&&d.upcoming[0]) || null;
  ov.innerHTML = `<div class="ovc">
    ${feat?betCard(feat): (d.tip?`<div class="btip">${esc(d.tip.text)} · %${d.tip.pct}<small>${esc(d.tip.why||'')}</small></div>`:'')}
    <div class="cmp" style="padding:0;margin:18px 0 0">${$('cmp').innerHTML}</div>
    <div style="margin-top:14px">${(d.upcoming||[]).map(m=>`<div class="hrow"><div>${esc(m.when)}</div><div>${esc(m.home.name)} vs ${esc(m.away.name)}</div><div>H${m.week||''}</div></div>`).join('')||''}</div>
    <div style="margin-top:10px">${(d.matches||[]).map(m=>`<div class="hrow"><div>${esc(m.when)}</div><div>${esc(m.home.short)} ${m.hg}–${m.ag} ${esc(m.away.short)}</div><div>${esc(m.season_label)}</div></div>`).join('')}</div>
    ${scorerBlock(d)}
    <button class="pbet" type="button" onclick="document.getElementById('ov').className='ov'">KAPAT</button>
  </div>`;
}

function face(p){
  const letter = esc((p.name||'?')[0]);
  if(!p.photo) return `<div class="pface">${letter}</div>`;
  return `<img src="${esc(p.photo)}" alt="" onerror="this.style.display='none'">`;
}
function scorerBlock(d){
  const s=d.scorers||{};
  const col=(arr,title)=>!arr||!arr.length?'':`<div><div class="sec">${esc(title)}</div>${arr.map(p=>`
    <div class="prow" onclick="openPlayer(${p.id})">${face(p)}<div>${esc(p.name)}<div style="font-size:10px;color:#8b9590">${esc(p.team_short||'')} · ${p.matches||0} maç</div></div>
    <div class="pval">${(p.stats&&p.stats.goals)||0}G · ${(p.stats&&p.stats.assists)||0}A</div></div>`).join('')}</div>`;
  const a=col(s.a, (d.a&&d.a.short||'EV')+' GOLCÜ'), b=col(s.b,(d.b&&d.b.short||'DEP')+' GOLCÜ');
  if(!a&&!b) return '';
  return `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px">${a}${b}</div>`;
}
function paintLeaders(leaders){
  const keys=[['goals','GOL KRALI'],['assists','ASİST'],['xg','xG'],['rating','PUAN']];
  $('plead').innerHTML = keys.map(([k,h])=>{
    const rows=(leaders&&leaders[k])||[];
    return `<div class="pcard"><div class="h">${h}</div>${rows.slice(0,6).map((p,i)=>`
      <div class="prow" onclick="openPlayer(${p.id})"><span style="width:14px;color:#6e7773">${i+1}</span>${face(p)}
        <div>${esc(p.name)}<div style="font-size:10px;color:#8b9590">${esc(p.team_short||p.team||'')}</div></div>
        <div class="pval">${p.value??'—'}</div></div>`).join('')||'<div class="ltime">veri yok</div>'}</div>`;
  }).join('');
}
function paintPTable(rows, sort){
  const cols=[['name','Oyuncu'],['team_short','Takım'],['matches','M'],['minutes','Dk'],['goals','G'],['assists','A'],['xg','xG'],['xa','xA'],['rating','Puan'],['yellow','Sarı'],['red','Kırmızı']];
  const th=cols.map(([k,l])=>`<th data-s="${k}" class="${k===sort?'on':''}">${l}</th>`).join('');
  const st=p=>p.stats||{};
  const cell=(p,k)=>{
    if(k==='name') return `<td style="display:flex;align-items:center;gap:8px">${face(p)}${esc(p.name)}</td>`;
    if(k==='team_short') return `<td>${esc(p.team_short||'')}</td>`;
    if(k==='matches'||k==='minutes') return `<td>${p[k]??'—'}</td>`;
    const v=st(p)[k];
    return `<td>${v==null?'—':v}</td>`;
  };
  $('ptable').innerHTML = `<thead><tr>${th}</tr></thead><tbody>${(rows||[]).map(p=>`
    <tr onclick="openPlayer(${p.id})">${cols.map(([k])=>cell(p,k)).join('')}</tr>`).join('')}</tbody>`;
  $('ptable').querySelectorAll('th').forEach(th=>{
    th.onclick=e=>{ e.stopPropagation(); loadPlayers(th.dataset.s); };
  });
}
async function loadPlayers(sort){
  if(sort && !['name','team_short'].includes(sort)) PSTAT=sort;
  document.querySelectorAll('#pane-p .pchip').forEach(x=>x.classList.toggle('on', x.dataset.stat===PSTAT));
  const qs=new URLSearchParams({sort:PSTAT, limit:'80'});
  if(PSEA) qs.set('season', PSEA);
  if(TEAM) qs.set('team', TEAM);
  const q=($('pq').value||'').trim();
  if(q) qs.set('q', q);
  const [d, sum] = await Promise.all([
    (await fetch('/bahis/api/players?'+qs,{cache:'no-store'})).json(),
    (await fetch('/bahis/api/players?kind=summary'+(PSEA?'&season='+encodeURIComponent(PSEA):''),{cache:'no-store'})).json(),
  ]);
  if(sum&&sum.ok) paintLeaders(sum.leaders);
  $('pttl').textContent = `${(d.season&&d.season.label)||''} · ${d.count||0} oyuncu · ${PSTAT}`;
  paintPTable(d.players||[], PSTAT);
  if(TEAM){
    const sq=await (await fetch('/bahis/api/players?kind=squad&team='+encodeURIComponent(TEAM),{cache:'no-store'})).json();
    const groups=(sq.squad&&sq.squad.groups)||[];
    $('psquad').innerHTML = groups.filter(g=>g.role!=='coach').map(g=>`
      <div class="pcard"><div class="h">${esc(g.role).toUpperCase()} · ${g.players.length}</div>
      ${(g.players||[]).map(p=>`<div class="prow" onclick="openPlayer(${p.id})">${face(p)}<div>${esc(p.name)}<div style="font-size:10px;color:#8b9590">${p.age||''} · ${esc(p.ccode||'')}</div></div></div>`).join('')}</div>`).join('');
  } else $('psquad').innerHTML='';
}
async function loadPlaySum(){
  PLAY=await (await fetch('/bahis/api/players?kind=summary',{cache:'no-store'})).json();
  if(!PLAY||!PLAY.ok) return;
  PSEA = (PLAY.season&&PLAY.season.id)||'';
  $('psea').innerHTML=(PLAY.seasons||[]).map(s=>`<option value="${s.id}">${esc(s.label)} · ${s.n}</option>`).join('');
  $('psea').value=PSEA;
  paintLeaders(PLAY.leaders);
  loadPlayers(PSTAT);
}
async function openPlayer(id){
  const d=await (await fetch('/bahis/api/players?id='+id,{cache:'no-store'})).json();
  if(!d.ok) return;
  const c=d.career||{};
  const ov=$('ov'); ov.className='ov on';
  ov.innerHTML=`<div class="ovc">
    <div style="display:flex;gap:14px;align-items:center;margin-bottom:12px">${face(d)}
      <div><b style="font-size:20px">${esc(d.name)}</b><div class="ltime">${esc(d.ccode||'')} · ${d.n||0} sezon</div></div></div>
    <div class="odds" style="margin-bottom:12px">
      <div class="ob"><s>Maç</s><b>${c.matches||0}</b></div>
      <div class="ob"><s>Gol</s><b>${c.goals||0}</b></div>
      <div class="ob"><s>Asist</s><b>${c.assists||0}</b></div>
      <div class="ob"><s>xG</s><b>${c.xg||0}</b></div>
    </div>
    <div class="sec">10 SEZON</div>
    ${(d.seasons||[]).map(s=>`<div class="hrow" style="grid-template-columns:90px 1fr 90px">
      <div>${esc(s.label)}</div><div>${esc(s.team_short||s.team||'')} · ${s.matches||0} maç · ${s.minutes||0} dk</div>
      <div>${(s.stats&&s.stats.goals)||0}G ${(s.stats&&s.stats.assists)||0}A</div></div>`).join('')||'<div class="ltime">lig istatistiği yok</div>'}
    <button class="pbet" type="button" onclick="document.getElementById('ov').className='ov'">KAPAT</button>
  </div>`;
}

document.addEventListener('click', e=>{
  const b=e.target.closest('.ob'); if(!b) return;
  const card=b.closest('.bcard,.odds');
  (card||b.parentElement).querySelectorAll('.ob').forEach(x=>x.classList.toggle('on', x===b));
});
document.addEventListener('click', e=>{
  if(e.target.closest('.ob,.pbet')) return;
  const c=e.target.closest('.bcard'); if(!c||!c.dataset.id) return;
  location.href='/site/mac/'+encodeURIComponent(c.dataset.id);
});
$('trow').addEventListener('click', async e=>{
  const b=e.target.closest('.tcirc'); if(!b) return;
  TEAM = TEAM===b.dataset.k ? '' : b.dataset.k;
  document.querySelectorAll('.tcirc').forEach(x=>x.classList.toggle('on', x.dataset.k===TEAM && TEAM));
  const qs = new URLSearchParams({status:'upcoming', season:'2627'});
  if(TEAM) qs.set('team', TEAM);
  const rows = await (await fetch('/bahis/api/matches?'+qs,{cache:'no-store'})).json();
  paintGrid(rows);
  loadHist();
  if($('pane-p').style.display==='block') loadPlayers();
  if($('pane-t').style.display==='block') loadPreds();
});
document.getElementById('tgrid').addEventListener('click', e=>{
  const c=e.target.closest('.tcard'); if(!c) return;
  if(c.dataset.id){ location.href='/site/mac/'+encodeURIComponent(c.dataset.id); return; }
  openH2H(c.dataset.h, c.dataset.a);
});
function pct(p){ return Math.round(Number(p||0)*100); }
function bars(m){
  const r=m.matchResult||{};
  return `<div class="tbar">
    <div class="ob${m.pick==='1'?' on':''}"><s>1</s><b>%${pct(r['1'])}</b></div>
    <div class="ob${m.pick==='X'?' on':''}"><s>X</s><b>%${pct(r.X)}</b></div>
    <div class="ob${m.pick==='2'?' on':''}"><s>2</s><b>%${pct(r['2'])}</b></div>
  </div>`;
}
function vsHead(m, left, right){
  return `<div class="when">${esc(m.when||'')}${m.week?' · H'+m.week:''}${m.venue?' · '+esc(m.venue):''}</div>
    <div class="vs">
      <div class="side">${crest(m.home)}<div class="nm">${esc(m.home.name)}</div><div class="xg">${left||''}</div></div>
      <div class="bvs-t">VS</div>
      <div class="side">${crest(m.away)}<div class="nm">${esc(m.away.name)}</div><div class="xg">${right||''}</div></div>
    </div>`;
}
function paintDixonCard(m, label){
  const ou=(m.overUnder&&m.overUnder['2.5'])||{};
  const scores=(m.correctScoreTop5||[]).slice(0,5).map(s=>`<i>${esc(s.score)}<em>%${s.pct}</em></i>`).join('');
  return `<div class="tcard kind-dixon" data-id="${esc(m.id||'')}" data-h="${esc(m.home.key)}" data-a="${esc(m.away.key)}">
    ${vsHead(m, m.xg?('xG '+m.xg.home):'', m.xg?('xG '+m.xg.away):'')}
    <div class="tpick">${esc(m.text)} · %${m.pct}<small>Poisson · ${esc(label)}</small></div>
    ${bars(m)}
    <div class="tmk">
      <div class="box"><s>2.5 alt / üst</s><b>%${pct(ou.under)} / %${pct(ou.over)}</b></div>
      <div class="box"><s>KG var / yok</s><b>%${pct(m.bttsYes)} / %${pct(m.bttsNo)}</b></div>
    </div>
    <div class="tsc">${scores}</div>
  </div>`;
}
function paintEloCard(m, label){
  const e=m.elo||{};
  const dh=(e.home||0)-(e.away||0);
  return `<div class="tcard kind-elo" data-id="${esc(m.id||'')}" data-h="${esc(m.home.key)}" data-a="${esc(m.away.key)}">
    ${vsHead(m, '', '')}
    <div class="vs" style="margin-top:-6px">
      <div class="side"><div class="elo-n">${e.home??'—'}</div><div class="elo-d">RD ${e.rd_h??'—'} · ${e.n_h??0} maç</div></div>
      <div class="elo-d">${dh>0?'+':''}${dh} ev</div>
      <div class="side"><div class="elo-n">${e.away??'—'}</div><div class="elo-d">RD ${e.rd_a??'—'} · ${e.n_a??0} maç</div></div>
    </div>
    <div class="tpick">${esc(m.text)} · %${m.pct}<small>ELO 1X2 · ${e.reliable?'güvenilir':'az veri'}</small></div>
    ${bars(m)}
  </div>`;
}
function paintBankCard(m){
  const ok=m.stake&&m.stake.should_bet;
  const rows=(m.evals||[]).map(e=>`<div class="erow">
    <div>${esc(e.label||e.selection)}</div>
    <div>${e.odds==null?'—':Number(e.odds).toFixed(2)}</div>
    <div>%${pct(e.model_prob)}</div>
    <div class="${e.edge>=0.03?'ok':'no'}">${e.edge>=0?'+':''}${(e.edge*100).toFixed(1)}p</div>
    <div class="${e.should_bet?'ok':'no'}">${e.should_bet? ('AL '+e.stake) : ('PAS · '+esc(e.reason||''))}</div>
  </div>`).join('');
  return `<div class="tcard kind-bankroll${ok?'':' pas'}" data-id="${esc(m.id||'')}" data-h="${esc(m.home.key)}" data-a="${esc(m.away.key)}">
    ${vsHead(m, '', '')}
    <div class="tpick">${esc(m.text)}${ok?`<span class="vbadge">AL</span>`:''}<small>¼ Kelly · Dixon olasılığı × piyasa oranı</small></div>
    <div class="erow" style="color:#8b9590;font-size:10px;letter-spacing:.06em"><div>SEÇİM</div><div>ORAN</div><div>MODEL</div><div>EDGE</div><div>KARAR</div></div>
    ${rows||'<div class="ltime">oran yok</div>'}
  </div>`;
}
function paintPreds(d){
  PRED=d;
  if(!d||!d.ok){ $('tmeta').textContent='Tahmin yok'; $('tgrid').innerHTML=''; return; }
  const name=d.label||d.model||'Tahmin';
  const kind=d.engine||d.model||'';
  $('tmeta').textContent = `${name} · ${d.note||''} · ${d.n||0} maç`;
  if(kind==='bankroll'&&d.bankroll){
    const b=d.bankroll;
    $('tstr').innerHTML = `<span class="chip">kasa ${b.current_bankroll}</span><span class="chip">${d.taken_n||0} AL</span><span class="chip">DD %${b.current_drawdown_pct}</span>`;
  } else if(kind==='elo'){
    $('tstr').innerHTML = (d.strengths||[]).slice(0,12).map(t=>
      `<span class="chip">${esc(t.short)} ELO ${t.attack} · RD ${t.defense}</span>`).join('');
  } else {
    $('tstr').innerHTML = (d.strengths||[]).slice(0,12).map(t=>
      `<span class="chip">${esc(t.short)} atk ${t.attack} · def ${t.defense}</span>`).join('');
  }
  const paint = kind==='elo' ? paintEloCard : kind==='bankroll' ? paintBankCard : paintDixonCard;
  $('tgrid').innerHTML = (d.preds||[]).map(m=>paint(m, name)).join('') || '<div class="ltime">Yakın maç yok</div>';
}
async function loadPreds(){
  if(!ENGINE){ $('tmeta').textContent='Motor yok'; return; }
  $('tmeta').textContent = ENGINE.toUpperCase()+' yükleniyor…';
  $('tgrid').innerHTML = '';
  const qs=new URLSearchParams({limit:'24', engine:ENGINE});
  if(TEAM) qs.set('team', TEAM);
  const d=await (await fetch('/bahis/api/preds?'+qs,{cache:'no-store'})).json();
  if((d.engine||d.model) && ENGINE && d.engine && d.engine!==ENGINE) return;
  paintPreds(d);
}
(function mountEngineTabs(){
  const box=$('ptabs');
  const have=new Set([...box.querySelectorAll('.ptab[data-engine]')].map(x=>x.dataset.engine));
  ENGINES.forEach(e=>{
    if(have.has(e.id)) return;
    const b=document.createElement('button');
    b.className='ptab';
    b.type='button';
    b.dataset.pane='t';
    b.dataset.engine=e.id;
    b.textContent=e.label;
    box.appendChild(b);
  });
})();
$('ptabs').addEventListener('click', e=>{
  const b=e.target.closest('.ptab'); if(!b) return;
  document.querySelectorAll('.ptab').forEach(x=>x.classList.toggle('on', x===b));
  $('pane-m').style.display = b.dataset.pane==='m' ? '' : 'none';
  $('pane-p').style.display = b.dataset.pane==='p' ? 'block' : 'none';
  $('pane-t').style.display = b.dataset.pane==='t' ? 'block' : 'none';
  if(b.dataset.pane==='p' && !PLAY) loadPlaySum();
  else if(b.dataset.pane==='p') loadPlayers();
  else if(b.dataset.pane==='t'){ ENGINE=b.dataset.engine||ENGINE; loadPreds(); }
});
$('psea').addEventListener('change', ()=>{ PSEA=$('psea').value; loadPlayers(); });
$('pq').addEventListener('input', ()=>{ clearTimeout($('pq')._t); $('pq')._t=setTimeout(()=>loadPlayers(), 220); });
document.querySelector('#pane-p .pbar').addEventListener('click', e=>{
  const b=e.target.closest('.pchip'); if(!b) return;
  loadPlayers(b.dataset.stat);
});
loadSum();
</script>
</body>
</html>
"""
