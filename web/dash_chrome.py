"""Ortak üst kabuk — POLY / FOREX / KRİPTO. İşlem mantığı yok."""
from __future__ import annotations

import re

WORLDS = (
    ("poly", "POLY", "/poly", "#C8F135", "#111"),
    ("forex", "FOREX", "/forex/home", "#3D8BFD", "#fff"),
    ("kripto", "KRİPTO", "/kripto", "#FF6B2C", "#111"),
)

_FOREX_HTML = frozenset({
    "FOREX_HTML", "FOREX_GRAFIK_HTML", "FOREX_CEMBYBIT_HTML", "FOREX_ISLEMLER_HTML",
    "FOREX_ALGO2_HTML", "FOREX_GPSUSDT_HTML", "FOREX_GPS_ISLEMLER_HTML",
    "FOREX_GPS2_HTML", "FOREX_GPS2_ISLEMLER_HTML",
    "FOREX_BINB103_HTML", "FOREX_BINB103_ISLEMLER_HTML",
    "FOREX_B103_HTML", "FOREX_B103_ISLEMLER_HTML",
    "FOREX_FX_ALGOS_HTML", "FOREX_CEM02_HTML", "FOREX_CEM02_ISLEMLER_HTML",
    "FOREX_OAPI_HTML", "FOREX_OAPI_ISLEMLER_HTML", "FOREX_YZA_HTML",
})
_KRIPTO_HTML = frozenset({
    "KRIPTO_FUTURE_HTML", "KRIPTO_YAPAY_ZEKA_ANALIZ_HTML",
    "KRIPTO_LIDER_ANALIZ_HTML", "KRIPTO_JARVIS_HTML",
})

_RE_BODY = re.compile(r"<body\b[^>]*>", re.I)
_RE_GEC = re.compile(
    r'\s*<a class="nav-item[^"]*" href="[^"]*">\s*'
    r'(?:<span class="nav-dot"></span>)?'
    r"(?:Kripto'ya Geç|Forex'e Geç|Poly'ye Geç(?:iş yap)?)"
    r"</a>",
    re.I,
)
_RE_SISTEMLER = re.compile(
    r'\s*<div class="nav-label">Sistemler</div>\s*'
    r'(?:<a class="nav-item[^"]*" href="/poly"><span class="nav-dot"></span>Poly(?:\'ye Geç)?</a>\s*)?'
    r'(?:<a class="nav-item[^"]*" href="/kripto"><span class="nav-dot"></span>Kripto(?:\'ya Geç)?</a>\s*)?',
    re.I,
)


def world_for_html(name: str) -> str:
    if name in _FOREX_HTML:
        return "forex"
    if name in _KRIPTO_HTML:
        return "kripto"
    return "poly"


def _css() -> str:
    rows = []
    for key, _lab, _href, accent, ink in WORLDS:
        rows.append(
            f'body[data-world="{key}"]{{--world:{accent};--world-ink:{ink};}}'
        )
    return (
        "/* dash-chrome */\n"
        + "".join(rows)
        + """
.dash-worldbar{
  position:fixed;top:0;left:220px;right:0;height:52px;z-index:45;
  display:flex;align-items:center;justify-content:center;gap:8px;
  padding:0 16px;
  background:#0c0e10;
  border-bottom:1px solid rgba(255,255,255,.08);
  box-sizing:border-box;
}
.dash-world{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:92px;height:34px;padding:0 16px;border-radius:999px;
  text-decoration:none;font:800 12px/1 Sora,system-ui,sans-serif;
  letter-spacing:.06em;color:#8a8a8a;background:#1a1c1e;
  border:1px solid rgba(255,255,255,.06);
}
.dash-world.on{background:var(--world);color:var(--world-ink);border-color:var(--world)}
body[data-world] .main,body[data-world] .desk,body[data-world] #kf-main{
  box-sizing:border-box;
}
body[data-world] .main{margin-top:52px}
body[data-world] .desk{padding-top:52px}
body[data-world] #kf-main{margin-top:52px}
body[data-world] .chart-full{
  margin-top:52px;height:calc(100vh - 52px);max-height:calc(100vh - 52px);
}
body[data-world] .right-panel,
body[data-world] .kf-right-panel,
body[data-world] .main-right{
  top:52px;
}
@media(max-width:800px){
  .dash-worldbar{display:none}
  body[data-world] .sidebar{margin-top:0}
  body[data-world] .main,body[data-world] #kf-main{margin-top:0}
  body[data-world] .desk{padding-top:0}
  body[data-world] .chart-full{margin-top:0;height:auto;max-height:none}
}
#fapi-ban-bar{
  display:none;position:fixed;top:52px;left:220px;right:0;z-index:46;
  padding:8px 16px;background:#3a2208;color:#f5c16c;
  font:700 12px/1.35 Sora,system-ui,sans-serif;
  border-bottom:1px solid rgba(245,166,35,.35);text-align:center;
}
@media(max-width:800px){#fapi-ban-bar{left:0;top:0}}
"""
    )


def _bar(world: str) -> str:
    pills = []
    for key, lab, href, _a, _i in WORLDS:
        on = " on" if key == world else ""
        pills.append(f'<a class="dash-world{on}" href="{href}">{lab}</a>')
    return (
        '<nav class="dash-worldbar" aria-label="Dünya">' + "".join(pills) + "</nav>"
        + '<div id="fapi-ban-bar" hidden></div>'
        + _ban_script()
    )


def _ban_script() -> str:
    return r"""<script>
(function(){
  function paint(d){
    var el=document.getElementById('fapi-ban-bar');
    if(!el) return;
    if(d&&d.blocked){
      el.hidden=false; el.style.display='block';
      el.textContent=d.msg||'Binance fapi IP ban — sayfa WS ile çalışır, emir yok';
    }else{
      el.hidden=true; el.style.display='none';
    }
  }
  window.showAppErr=function(s,fb){
    if(/fapi\s+(IP\s+)?ban/i.test(String(s||''))){ paint({blocked:true,msg:s}); return; }
    alert(s||fb||'hata');
  };
  function tick(){
    fetch('/poly/api/fapi-status',{cache:'no-store'}).then(function(r){return r.json();}).then(paint).catch(function(){});
  }
  tick();
  setInterval(tick,60000);
})();
</script>"""


def strip_sidebar_world_links(html: str) -> str:
    html = _RE_GEC.sub("", html)
    html = _RE_SISTEMLER.sub("\n", html)
    return html


def patch_dash_chrome(html: str, world: str = "poly") -> str:
    if not html or "dash-worldbar" in html:
        return html
    world = world if world in {w[0] for w in WORLDS} else "poly"
    html = strip_sidebar_world_links(html)

    def _body(m: re.Match) -> str:
        tag = m.group(0)
        if "data-world=" in tag:
            tag = re.sub(r'data-world="[^"]*"', f'data-world="{world}"', tag)
        else:
            tag = tag[:-1] + f' data-world="{world}">'
        return tag + _bar(world)

    html, n = _RE_BODY.subn(_body, html, count=1)
    if n == 0:
        return html
    style = "<style>" + _css() + "</style>\n"
    if "</head>" in html:
        html = html.replace("</head>", style + "</head>", 1)
    elif "</style>" in html:
        html = html.replace("</style>", "</style>\n" + style, 1)
    return html
