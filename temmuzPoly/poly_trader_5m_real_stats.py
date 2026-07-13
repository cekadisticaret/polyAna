"""5M 201 + 5M 202 gerçek PM trader birleşik istatistik bildirimi."""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_TZ_TR = ZoneInfo("Europe/Istanbul")

BOT_TOKEN = "8799859033:AAHjOkEDP7W5sk97lFknakMokgoKBf62Ssg"
CHAT_ID   = "830754964"

SYSTEMS = [
    ("5m_btc_real", "5M 201 BTC", "4-Algo Konsensüs"),
    ("5m_btc_202",  "5M 202 BTC", "A1+A9 Konsensüs"),
]


def _load_json(path: str) -> list | dict:
    if not os.path.exists(path):
        return [] if path.endswith("_history.json") else {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return [] if path.endswith("_history.json") else {}


def _wr(wins: int, total: int) -> str:
    if not total:
        return "—"
    return f"%{wins / total * 100:.0f}"


def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:
        print(f"[5M REAL STATS] TG hata: {e}", file=sys.stderr)


def _system_stats(key: str) -> dict:
    hist  = _load_json(os.path.join(_DIR, f"poly_trader_{key}_history.json"))
    state = _load_json(os.path.join(_DIR, f"poly_trader_{key}_state.json"))
    total = len(hist)
    wins  = sum(1 for t in hist if t.get("win"))
    losses = total - wins
    pnl   = round(sum(t.get("pnl", 0) for t in hist), 2)
    if not pnl and isinstance(state, dict):
        pnl = round(state.get("total_pnl", 0.0), 2)
    open_pos = state.get("open_positions", []) if isinstance(state, dict) else []
    open_n   = len(open_pos)
    risk     = round(sum(p.get("pm_spent", p.get("amount", 0)) for p in open_pos), 2)
    return {
        "total": total, "wins": wins, "losses": losses,
        "pnl": pnl, "open": open_n, "risk": risk,
    }


def _block(label: str, desc: str, s: dict) -> list[str]:
    pnl_icon = "🟢" if s["pnl"] >= 0 else "🔴"
    lines = [
        f"━━ <b>{label}</b> ━━",
        f"<i>{desc}</i>",
        f"📂 Açılan: <b>{s['total']}</b>  |  ✅ Başarılı: <b>{s['wins']}</b>  |  ❌ Kayıp: <b>{s['losses']}</b>",
        f"📈 WR: <b>{_wr(s['wins'], s['total'])}</b>  |  {pnl_icon} Kar: <b>{'+' if s['pnl'] >= 0 else ''}{s['pnl']:.2f}$</b>",
    ]
    if s["open"]:
        lines.append(f"🔴 Açık pozisyon: {s['open']}  |  Riskte: ${s['risk']:.2f}")
    return lines


def build_message() -> str:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    sep = "━" * 26
    lines = [
        sep,
        f"📊 <b>5M GERÇEK PM — Saatlik Özet</b>",
        f"🕐 {now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        "",
    ]

    grand_total = grand_wins = grand_losses = 0
    grand_pnl = 0.0

    for key, label, desc in SYSTEMS:
        s = _system_stats(key)
        grand_total  += s["total"]
        grand_wins   += s["wins"]
        grand_losses += s["losses"]
        grand_pnl    += s["pnl"]
        lines.extend(_block(label, desc, s))
        lines.append("")

    pnl_icon = "🟢" if grand_pnl >= 0 else "🔴"
    lines += [
        f"━━ <b>TOPLAM (201+202)</b> ━━",
        f"📂 Açılan: <b>{grand_total}</b>  |  ✅ Başarılı: <b>{grand_wins}</b>  |  ❌ Kayıp: <b>{grand_losses}</b>",
        f"📈 WR: <b>{_wr(grand_wins, grand_total)}</b>  |  {pnl_icon} Net Kar: <b>{'+' if grand_pnl >= 0 else ''}{grand_pnl:.2f}$</b>",
        sep,
    ]
    return "\n".join(lines)


def run() -> None:
    msg = build_message()
    tg_send(msg)
    print("[5M REAL STATS] saatlik özet gönderildi")


if __name__ == "__main__":
    run()
