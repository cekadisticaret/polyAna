#!/usr/bin/env python3
"""CoptC dashboard — B1#05 ve B1#03 MUM.

    python3 web/dashboard.py            # 0.0.0.0:5060
    COPTC_PASSWORD=... python3 web/dashboard.py

`Live aç` gerçek para harcatır; `COPTC_PASSWORD` tanımlıysa oturum açmadan
hiçbir uç noktaya erişilemez.
"""
from __future__ import annotations

import os
import secrets
import sys
from functools import wraps

from flask import Flask, jsonify, redirect, render_template_string, request, session

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import api  # noqa: E402

app = Flask(__name__)
# .env'de anahtar tanımlı ama boşsa getenv boş string döner; `or` ile yakala,
# yoksa Flask "no secret key" diye oturumu tamamen reddediyor.
app.secret_key = os.getenv("COPTC_SECRET") or secrets.token_hex(16)
PASSWORD = (os.getenv("COPTC_PASSWORD") or "").strip()
PORT = int(os.getenv("COPTC_PORT") or 5060)


def guard(fn):
    @wraps(fn)
    def inner(*a, **kw):
        if PASSWORD and not session.get("ok"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "yetkisiz"}), 401
            return redirect("/giris")
        return fn(*a, **kw)
    return inner


# ── sayfa ────────────────────────────────────────────────────────
PAGE = """<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ badge }} · CoptC</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080b10; --card:#12161e; --card2:#161b25; --line:#212836;
  --tx:#e9edf4; --mut:#79839a; --lime:#c9f227; --violet:#7b61ff;
  --grn:#3ddc84; --red:#ff5f6e;
}
body{background:var(--bg);color:var(--tx);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  padding:22px 16px 60px;-webkit-font-smoothing:antialiased}
.wrap{max-width:980px;margin:0 auto;display:flex;flex-direction:column;gap:14px}
.mut{color:var(--mut)}
.cap{font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--mut);font-weight:600}

/* defter sekmeleri */
.tabs{display:flex;gap:8px}
.tab{padding:7px 15px;border-radius:9px;background:var(--card);border:1px solid var(--line);
  color:var(--mut);text-decoration:none;font-size:13px;font-weight:600}
.tab.on{background:var(--violet);border-color:var(--violet);color:#fff}

/* başlık */
.hd{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.badge{width:52px;height:52px;border-radius:14px;flex:0 0 auto;display:grid;place-items:center;
  background:linear-gradient(150deg,#4d7cfe,#8b5cf6);font-weight:800;font-size:13px;letter-spacing:.02em}
.hd h1{font-size:25px;font-weight:800;letter-spacing:-.02em}
.hd .sub{font-size:12px;color:var(--mut);margin-top:2px}
.hd .sp{margin-left:auto;display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.pill{padding:5px 12px;border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.04em;
  border:1px solid var(--red);color:var(--red)}
.pill.on{border-color:var(--grn);color:var(--grn)}
.btn{padding:8px 15px;border-radius:9px;border:1px solid var(--line);background:var(--card2);
  color:var(--tx);font-size:13px;font-weight:600;cursor:pointer}
.btn:hover{border-color:#3a4457}
.btn.v{background:var(--violet);border-color:var(--violet);color:#fff}
.btn.l{background:var(--lime);border-color:var(--lime);color:#0d1207}
.btn.r{background:transparent;border-color:var(--red);color:var(--red)}
.btn:disabled{opacity:.5;cursor:default}

/* zaman şeridi */
.tl{display:flex;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px 8px}
.tl div{flex:1;text-align:center;font-size:12px;color:var(--mut)}
.tl b{color:var(--lime);font-weight:700;margin-right:6px}

/* sembol kartları */
/* A1 iki sembolle geliyor — sabit 3 sütun yerine kart sayısına uy */
.syms{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
@media(max-width:760px){.syms{grid-template-columns:1fr}}
.sym{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:15px 15px 13px;position:relative;overflow:hidden}
.sym:before{content:"";position:absolute;inset:0 0 auto 0;height:3px;background:linear-gradient(90deg,var(--lime),var(--grn))}
.sym.dn:before{background:linear-gradient(90deg,#ff9e5f,var(--red))}
.sym.nu:before{background:linear-gradient(90deg,#37414f,#4a5568)}
.sym .r1{display:flex;align-items:center;justify-content:space-between}
.sym .nm{font-size:17px;font-weight:800}
.tag{font-size:10px;font-weight:800;letter-spacing:.08em;padding:3px 9px;border-radius:6px;background:#212836;color:var(--mut)}
.tag.up{background:rgba(61,220,132,.15);color:var(--grn)}
.tag.dn{background:rgba(255,95,110,.15);color:var(--red)}
.sym .px{font-size:23px;font-weight:800;margin:9px 0 11px;letter-spacing:-.02em}
.sym .mv{font-size:21px;font-weight:800;margin-top:3px}
.gauge{height:6px;border-radius:99px;background:#1d2330;margin:11px 0 8px;position:relative}
.gauge i{position:absolute;top:0;height:6px;width:26px;border-radius:99px;background:var(--grn);transform:translateX(-50%)}
.sym .ft{font-size:10px;color:#5f6878}

/* istatistik kartları */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
@media(max-width:860px){.stats{grid-template-columns:repeat(2,1fr)}}
.st{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:14px 15px}
.st .v{font-size:23px;font-weight:800;margin:7px 0 4px;letter-spacing:-.02em}
.st .f{font-size:11px;color:#5f6878}

/* risk kartı */
.risk{background:var(--lime);border-radius:15px;padding:17px 19px;color:#0d1207}
.risk .t{font-size:12px;font-weight:700;opacity:.72}
.risk .big{font-size:33px;font-weight:800;letter-spacing:-.03em;margin:2px 0 15px}
.risk .rg{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
@media(max-width:760px){.risk .rg{grid-template-columns:repeat(2,1fr)}}
.risk .rg .k{font-size:11px;font-weight:600;opacity:.66}
.risk .rg .w{font-size:16px;font-weight:800;margin-top:2px}

/* paneller */
.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 17px}
.panel h2{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:var(--mut);font-weight:700;
  display:flex;align-items:center;gap:9px;margin-bottom:13px}
.tagl{font-size:9px;letter-spacing:.09em;padding:3px 8px;border-radius:5px;background:rgba(255,95,110,.14);color:var(--red);font-weight:800}
.empty{text-align:center;color:#5f6878;font-size:13px;padding:26px 10px}

.pos{display:flex;align-items:center;gap:12px;padding:11px 13px;background:var(--card2);
  border:1px solid var(--line);border-radius:10px;margin-bottom:8px;flex-wrap:wrap}
.pos .s{font-weight:800;font-size:15px;min-width:44px}
.pos .m{font-size:11px;color:var(--mut)}
.pos .rr{margin-left:auto;text-align:right}

/* tutar kartı */
.abox{display:grid;grid-template-columns:repeat(3,1fr);gap:11px;margin-bottom:13px}
.abox .bx{background:var(--card2);border:1px solid var(--line);border-radius:10px;padding:12px 13px}
.abox .bx .v{font-size:20px;font-weight:800;margin-top:5px}
.arow{display:grid;grid-template-columns:repeat(3,1fr) auto;gap:11px;align-items:end}
@media(max-width:760px){.arow{grid-template-columns:1fr 1fr}}
.arow label{display:block}
.arow input{width:100%;margin-top:6px;background:var(--card2);border:1px solid var(--line);border-radius:9px;
  padding:10px 12px;color:var(--tx);font-size:15px;font-weight:700}
.hint{font-size:11px;color:#5f6878;margin-top:10px}

/* saat ızgarası */
.hrs{display:grid;grid-template-columns:repeat(12,1fr);gap:7px}
@media(max-width:760px){.hrs{grid-template-columns:repeat(6,1fr)}}
.hr{background:var(--card2);border:1px solid var(--line);border-radius:8px;padding:11px 2px;text-align:center;
  font-size:12px;font-weight:700;color:var(--mut)}
.hr.g{background:rgba(61,220,132,.14);border-color:rgba(61,220,132,.4);color:var(--grn)}
.hr.b{background:rgba(255,95,110,.12);border-color:rgba(255,95,110,.35);color:var(--red)}

/* para çekme */
.wd{border-color:#3a2b33}
.wrow{display:grid;grid-template-columns:2fr 1fr 1fr;gap:11px;margin-bottom:11px}
.wrow2{display:grid;grid-template-columns:1fr auto;gap:11px;align-items:end}
@media(max-width:760px){.wrow{grid-template-columns:1fr}}
.wd input,.wd select{width:100%;margin-top:6px;background:var(--card2);border:1px solid var(--line);
  border-radius:9px;padding:10px 12px;color:var(--tx);font-size:14px}
.wd input#wto{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
.wbtn{background:var(--red);border-color:var(--red);color:#fff;padding:11px 22px}
.wbtn:hover{filter:brightness(1.1)}
.wok{color:var(--grn)} .werr{color:var(--red)}
.wd .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;word-break:break-all}

/* tablo */
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);
  font-weight:700;padding:0 8px 10px}
td{padding:9px 8px;border-top:1px solid var(--line)}
.g{color:var(--grn)} .b{color:var(--red)}
.load{opacity:.45}
</style></head><body>
<div class="wrap">
  <div class="tabs">
    {% for k, b in books.items() %}
    <a class="tab {{ 'on' if k == book }}" href="/{{ k }}">{{ b.badge }}</a>
    {% endfor %}
  </div>

  <div class="hd">
    <div class="badge">{{ badge }}</div>
    <div>
      <h1>{{ title }}</h1>
      <div class="sub">{{ subtitle }}</div>
    </div>
    <div class="sp">
      <span class="pill" id="pill">—</span>
      <span class="mut" id="clock" style="font-size:12px"></span>
      <button class="btn" id="bsig">Sinyal çek</button>
      <button class="btn v" id="bref">Yenile</button>
      <button class="btn l" id="blive">—</button>
    </div>
  </div>

  <div class="tl">
    {% for t, l in timeline %}<div><b>{{ t }}</b>{{ l }}</div>{% endfor %}
  </div>

  <div class="syms" id="syms">
    {% for i in range(3) %}
    <div class="sym nu"><div class="r1"><span class="nm">—</span></div>
      <div class="px">…</div><div class="cap">yükleniyor</div><div class="gauge"><i style="left:50%"></i></div>
    </div>{% endfor %}
  </div>

  <div class="stats" id="stats"></div>
  <div class="risk" id="risk"></div>

  <section class="panel">
    <h2>Açık pozisyonlar — anlık</h2>
    <div id="pos"></div>
  </section>

  <section class="panel">
    <h2>Gerçek PM — giriş tutarları <span class="tagl">LIVE</span></h2>
    <div class="abox" id="abox"></div>
    <div class="arow">
      <label><span class="cap">Low (WR &lt; 50%)</span><input id="alow" type="number" step="0.5" min="1"></label>
      <label><span class="cap">Mid</span><input id="amid" type="number" step="0.5" min="1"></label>
      <label><span class="cap">High (WR &gt; 50%)</span><input id="ahigh" type="number" step="0.5" min="1"></label>
      <button class="btn v" id="bsave">Kaydet</button>
    </div>
    <div class="hint" id="ahint">Sembol win rate'e göre kademe seçilir. Kaydet → sonraki live açılışta geçerli.</div>
  </section>

  <section class="panel">
    <h2>Saat bazlı başarı <span class="tagl" id="hsrc">—</span></h2>
    <div class="hrs" id="hrs"></div>
  </section>

  <section class="panel wd">
    <h2>Polymarket'ten para çek <span class="tagl">GERÇEK PARA</span></h2>
    <div class="abox" id="wdinfo"></div>
    <div class="wrow">
      <label style="grid-column:span 2"><span class="cap">Hedef adres</span>
        <input id="wto" placeholder="0x…" autocomplete="off" spellcheck="false"></label>
      <label><span class="cap">Tutar ($)</span>
        <input id="wamt" type="number" step="0.01" min="0.01" placeholder="0.00"></label>
      <label><span class="cap">Token</span>
        <select id="wtok"><option value="PUSD">pUSD</option><option value="USDC.E">USDC.e</option></select></label>
    </div>
    <div class="wrow2">
      <label><span class="cap">Çekim kodu</span>
        <input id="wcode" type="password" autocomplete="off" placeholder="••••••••"></label>
      <button class="btn wbtn" id="wsend">Parayı çek</button>
    </div>
    <div class="hint" id="wmsg">Tutar ve adres bir kez gönderildikten sonra geri alınamaz. Kod 5 kez yanlış girilirse 15 dk kilitlenir.</div>
    <div id="wlog"></div>
  </section>

  <section class="panel">
    <h2>İşlem geçmişi <span class="tagl" id="tsrc">—</span></h2>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>Sembol</th><th>Tahmin</th><th>Gerçek</th><th>Sonuç</th><th>P&amp;L</th><th>Zaman</th></tr></thead>
      <tbody id="hist"></tbody>
    </table></div>
  </section>
</div>

<script>
const BOOK = {{ book|tojson }};
const $ = id => document.getElementById(id);
const money = v => v === null || v === undefined ? '—'
  : (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString('tr-TR', {minimumFractionDigits:2, maximumFractionDigits:2});
const cls = v => v > 0 ? 'g' : (v < 0 ? 'b' : '');

function clock(){
  const t = new Date().toLocaleTimeString('tr-TR', {timeZone:'Europe/Istanbul', hour12:false});
  $('clock').textContent = t + ' İST';
}
setInterval(clock, 1000); clock();

function renderSyms(rows){
  $('syms').innerHTML = rows.map(s => {
    const d = s.dir === 'UP' ? 'up' : (s.dir === 'DOWN' ? 'dn' : '');
    const card = s.dir === 'UP' ? '' : (s.dir === 'DOWN' ? 'dn' : 'nu');
    const px = s.price ? '$' + Number(s.price).toLocaleString('tr-TR', {maximumFractionDigits:2}) : '—';
    const gp = Math.round((s.gauge ?? .5) * 100);
    return `<div class="sym ${card}">
      <div class="r1"><span class="nm">${s.name}</span>
        <span class="tag ${d}">${s.dir || 'NÖTR'}</span></div>
      <div class="px">${px}</div>
      <div class="cap">${s.metric_label}</div>
      <div class="mv">${s.metric_value}</div>
      <div class="gauge"><i style="left:${Math.min(96, Math.max(4, gp))}%"></i></div>
      <div class="ft">${s.foot || ''}</div></div>`;
  }).join('');
}

function render(d){
  $('pill').textContent = d.live_open ? 'LIVE AÇIK' : 'LIVE KAPALI';
  $('pill').className = 'pill' + (d.live_open ? ' on' : '');
  $('blive').textContent = d.live_open ? 'Live kapat' : 'Live aç';
  $('blive').className = 'btn ' + (d.live_open ? 'r' : 'l');

  const wl = `${d.live_w}W / ${d.live_l}L`;
  $('stats').innerHTML = `
    <div class="st"><div class="cap">PM nakit</div><div class="v">${money(d.cash)}</div>
      <div class="f">${d.cash === null ? 'cüzdan tanımsız' : 'serbest USDC'}</div></div>
    <div class="st"><div class="cap">Redeem bekleyen</div><div class="v g">${money(d.redeem_pending)}</div>
      <div class="f">${d.risk.open} açık pozisyon</div></div>
    <div class="st"><div class="cap">Live P&amp;L</div><div class="v ${cls(d.live_pnl)}">${money(d.live_pnl)}</div>
      <div class="f">${wl}</div></div>
    <div class="st"><div class="cap">Sanal defter</div><div class="v">${money(d.sanal.balance)}</div>
      <div class="f">${d.sanal.trades} işlem · WR ${d.sanal.wr === null ? '—' : '%' + d.sanal.wr}</div></div>`;

  const r = d.risk;
  $('risk').innerHTML = `<div class="t">Toplam riskteki</div><div class="big">${money(r.total)}</div>
    <div class="rg">
      <div><div class="k">Kazanılacak</div><div class="w">${r.to_win ? money(r.to_win) : '—'}</div></div>
      <div><div class="k">Açık</div><div class="w">${r.open}</div></div>
      <div><div class="k">Anlık kâr/zarar</div><div class="w">${r.upnl >= 0 ? '+' : ''}${money(r.upnl)}</div></div>
      <div><div class="k">Anlık kapama toplamı</div><div class="w">${money(r.close_total)}</div></div>
    </div>`;

  const live = d.positions.map(p => `<div class="pos">
      <span class="s">${p.symbol}</span>
      <span class="tag ${p.dir === 'UP' ? 'up' : 'dn'}">${p.dir}</span>
      <span class="m">${p.slot} · giriş ${p.entry ?? '—'} · ${money(p.spent)} → ${money(p.to_win)}</span>
      <span class="rr"><b class="${cls(p.close_pnl)}">${p.close_pnl === null ? '—' : (p.close_pnl >= 0 ? '+' : '') + money(p.close_pnl)}</b>
        <div class="m">${p.close_val === null ? 'kotasyon yok' : 'şimdi ' + money(p.close_val)}</div></span></div>`).join('');
  const sanal = d.sanal.positions.map(p => `<div class="pos">
      <span class="s">${p.symbol}</span>
      <span class="tag ${p.dir === 'UP' ? 'up' : 'dn'}">${p.dir}</span>
      <span class="m">SANAL · ${p.slot} · giriş ${p.entry ?? '—'} · ${money(p.amount)}</span></div>`).join('');
  $('pos').innerHTML = (live + sanal) ||
    `<div class="empty">Şu an açık pozisyon yok — bir sonraki live slotunda UP/DOWN sinyalde açılır</div>`;

  const a = d.amounts;
  $('abox').innerHTML = `
    <div class="bx"><div class="cap">Win rate</div><div class="v ${a.wr === null ? '' : (a.wr >= 50 ? 'g' : 'b')}">${a.wr === null ? '—' : '%' + a.wr}</div></div>
    <div class="bx"><div class="cap">İşlem</div><div class="v">${a.trades}</div></div>
    <div class="bx"><div class="cap">Açık</div><div class="v">${a.open}</div></div>`;
  if (document.activeElement.tagName !== 'INPUT'){
    $('alow').value = a.low; $('amid').value = a.mid; $('ahigh').value = a.high;
  }

  $('hsrc').textContent = d.hours_source === 'live' ? 'LIVE' : 'SANAL';
  $('hrs').innerHTML = d.hours.map(h => {
    const k = h.wr === null ? '' : (h.wr >= 55 ? 'g' : (h.wr <= 45 ? 'b' : ''));
    return `<div class="hr ${k}" title="${h.n} işlem${h.wr === null ? '' : ' · %' + h.wr}">${String(h.h).padStart(2,'0')}</div>`;
  }).join('');

  $('tsrc').textContent = d.history_source === 'live' ? 'LIVE' : 'SANAL';
  $('hist').innerHTML = d.history.length ? d.history.map(t => `<tr>
      <td><b>${t.symbol}</b></td><td>${t.pred}</td><td>${t.actual}</td>
      <td class="${t.win ? 'g' : 'b'}">${t.win ? '✓' : '✗'}</td>
      <td class="${cls(t.pnl)}">${t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}$</td>
      <td class="mut">${t.time}</td></tr>`).join('')
    : `<tr><td colspan="6" class="empty">Henüz kapanmış işlem yok</td></tr>`;
}

async function load(){
  document.body.classList.add('load');
  try{
    const r = await fetch(`/api/${BOOK}/overview`);
    if (r.status === 401) return location.href = '/giris';
    render(await r.json());
  } finally { document.body.classList.remove('load'); }
}

async function signals(){
  $('bsig').disabled = true; $('bsig').textContent = 'Çekiliyor…';
  try{
    const r = await fetch(`/api/${BOOK}/signals`);
    renderSyms(await r.json());
  } finally { $('bsig').disabled = false; $('bsig').textContent = 'Sinyal çek'; }
}

$('bref').onclick = () => { load(); signals(); };
$('bsig').onclick = signals;

$('blive').onclick = async () => {
  const on = $('blive').textContent === 'Live aç';
  if (on && !confirm('GERÇEK PARA — bu defter bir sonraki live slotunda Polymarket emri açacak. Onaylıyor musun?')) return;
  $('blive').disabled = true;
  await fetch(`/api/${BOOK}/live`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({open:on})});
  $('blive').disabled = false; load();
};

$('bsave').onclick = async () => {
  const body = {low:+$('alow').value, mid:+$('amid').value, high:+$('ahigh').value};
  $('bsave').disabled = true;
  const r = await fetch(`/api/${BOOK}/amounts`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  $('ahint').textContent = r.ok ? 'Kaydedildi — sonraki live açılışta geçerli.' : 'Kaydedilemedi.';
  $('bsave').disabled = false; load();
};

// ── para çekme ────────────────────────────────────────────────
function renderWd(w){
  const short = a => a ? a.slice(0,6) + '…' + a.slice(-4) : '—';
  const durum = w.error ? `<span class="werr">hata</span>`
    : (!w.builder_ready ? `<span class="werr">relayer eksik</span>`
    : (w.proxy_match ? `<span class="wok">hazır</span>` : `<span class="werr">proxy uyuşmuyor</span>`));
  $('wdinfo').innerHTML = `
    <div class="bx"><div class="cap">Çekilebilir</div><div class="v">${money(w.balance)}</div></div>
    <div class="bx"><div class="cap">Proxy cüzdan</div><div class="v" style="font-size:14px">${short(w.funder)}</div></div>
    <div class="bx"><div class="cap">Durum</div><div class="v" style="font-size:15px">${durum}</div></div>`;
  if (w.error) $('wmsg').innerHTML = `<span class="werr">${w.error}</span>`;
  else if (!w.code_set) $('wmsg').innerHTML =
    `<span class="werr">Çekim kodu tanımsız — .env dosyasına COPTC_WITHDRAW_CODE ekle.</span>`;
  if (w.locked_for > 0) $('wmsg').innerHTML =
    `<span class="werr">Hatalı kod nedeniyle kilitli — ${w.locked_for} sn kaldı.</span>`;

  $('wlog').innerHTML = (w.history || []).length ? '<div style="margin-top:12px">' +
    w.history.map(h => `<div class="pos"><span class="m">${String(h.ts).slice(5,16).replace('T',' ')}</span>
      <span class="s">${money(h.amount)}</span>
      <span class="m mono">→ ${short(h.to)}</span>
      <span class="rr m mono">${h.tx ? h.tx.slice(0,14) + '…' : ''}</span></div>`).join('') + '</div>' : '';
}

async function loadWd(){
  const r = await fetch('/api/withdraw/info');
  if (r.ok) renderWd(await r.json());
}

$('wsend').onclick = async () => {
  const to = $('wto').value.trim(), amt = +$('wamt').value, code = $('wcode').value;
  if (!/^0x[0-9a-fA-F]{40}$/.test(to)) return $('wmsg').innerHTML = '<span class="werr">Adres geçersiz (0x + 40 karakter).</span>';
  if (!(amt > 0)) return $('wmsg').innerHTML = '<span class="werr">Tutar sıfırdan büyük olmalı.</span>';
  if (!code) return $('wmsg').innerHTML = '<span class="werr">Çekim kodunu gir.</span>';
  if (!confirm(`GERİ ALINAMAZ\n\n${money(amt)} ${$('wtok').value}\n→ ${to}\n\nGöndermek istediğine emin misin?`)) return;

  $('wsend').disabled = true; $('wsend').textContent = 'Gönderiliyor…';
  $('wmsg').innerHTML = 'Relayer bekleniyor, bu bir dakika sürebilir…';
  try{
    const r = await fetch('/api/withdraw/send', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({to, amount: amt, code, token: $('wtok').value})});
    const d = await r.json();
    if (!r.ok || d.error){ $('wmsg').innerHTML = `<span class="werr">${d.error || 'Gönderim başarısız'}</span>`; }
    else {
      const tx = d.transaction_hash || d.transaction_id || '';
      $('wmsg').innerHTML = `<span class="wok">Gönderildi — ${money(amt)} → ${to.slice(0,10)}…</span>` +
        (tx ? ` <a class="mono" style="color:var(--violet)" target="_blank" rel="noopener"
               href="https://polygonscan.com/tx/${tx}">${tx.slice(0,20)}…</a>` : '');
      $('wamt').value = ''; $('wcode').value = '';
    }
  } catch(e){ $('wmsg').innerHTML = `<span class="werr">${e}</span>`; }
  finally { $('wsend').disabled = false; $('wsend').textContent = 'Parayı çek'; loadWd(); load(); }
};

load(); signals(); loadWd(); setInterval(load, 30000);
</script></body></html>"""

LOGIN = """<!doctype html><meta charset="utf-8"><title>CoptC</title>
<style>body{background:#080b10;color:#e9edf4;font:14px -apple-system,sans-serif;display:grid;
place-items:center;height:100vh;margin:0}form{background:#12161e;border:1px solid #212836;
border-radius:14px;padding:26px;display:flex;flex-direction:column;gap:12px;width:280px}
input{background:#161b25;border:1px solid #212836;border-radius:9px;padding:11px;color:#e9edf4}
button{background:#7b61ff;border:0;border-radius:9px;padding:11px;color:#fff;font-weight:700;cursor:pointer}
.e{color:#ff5f6e;font-size:12px}</style>
<form method="post"><b>CoptC</b><input type="password" name="p" placeholder="Parola" autofocus>
<button>Giriş</button>{% if err %}<span class="e">Hatalı parola</span>{% endif %}</form>"""


@app.route("/giris", methods=["GET", "POST"])
def login():
    if not PASSWORD:
        return redirect("/")
    err = False
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("p", ""), PASSWORD):
            session["ok"] = True
            return redirect("/")
        err = True
    return render_template_string(LOGIN, err=err)


@app.route("/")
@guard
def index():
    return redirect("/b1_05")


@app.route("/<book>")
@guard
def page(book: str):
    cfg = api.BOOKS.get(book)
    if not cfg:
        return redirect("/b1_05")
    return render_template_string(
        PAGE, book=book, books=api.BOOKS, badge=cfg["badge"],
        title=cfg["title"], subtitle=cfg["subtitle"], timeline=cfg["timeline"],
    )


@app.route("/api/<book>/overview")
@guard
def api_overview(book: str):
    if book not in api.BOOKS:
        return jsonify({"error": "bilinmeyen defter"}), 404
    return jsonify(api.overview(book))


@app.route("/api/<book>/signals")
@guard
def api_signals(book: str):
    if book not in api.BOOKS:
        return jsonify({"error": "bilinmeyen defter"}), 404
    return jsonify(api.live_signals(book))


@app.route("/api/<book>/live", methods=["POST"])
@guard
def api_live(book: str):
    if book not in api.BOOKS:
        return jsonify({"error": "bilinmeyen defter"}), 404
    want = bool((request.get_json(silent=True) or {}).get("open"))
    return jsonify({"live_open": api.set_live(book, want)})


@app.route("/api/withdraw/info")
@guard
def api_withdraw_info():
    info = api.withdraw_info()
    info["history"] = api.withdraw_history()
    return jsonify(info)


@app.route("/api/withdraw/send", methods=["POST"])
@guard
def api_withdraw_send():
    # Parola korumasız panelde gerçek para gönderimi açılmaz.
    if not PASSWORD:
        return jsonify({"error": "Panel parolasız — çekim kapalı. .env'e COPTC_PASSWORD ekle."}), 403
    d = request.get_json(silent=True) or {}
    res, status = api.withdraw_send(
        to=str(d.get("to") or ""), amount=d.get("amount"),
        code=str(d.get("code") or ""), token=str(d.get("token") or "PUSD"),
    )
    return jsonify(res), status


@app.route("/api/<book>/amounts", methods=["POST"])
@guard
def api_amounts(book: str):
    if book not in api.BOOKS:
        return jsonify({"error": "bilinmeyen defter"}), 404
    d = request.get_json(silent=True) or {}
    try:
        vals = [round(float(d[k]), 2) for k in ("low", "mid", "high")]
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "low/mid/high sayı olmalı"}), 400
    if not all(1.0 <= v <= 500.0 for v in vals):
        return jsonify({"error": "kademe $1–$500 aralığında olmalı"}), 400
    return jsonify(api.save_amounts(book, *vals))


if __name__ == "__main__":
    if not PASSWORD:
        print("UYARI: COPTC_PASSWORD tanımsız — panel korumasız, Live düğmesi herkese açık.")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
