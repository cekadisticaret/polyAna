"""5M 102 BTC sanal trader — saatlik istatistik bildirimi."""
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

KEY   = "5m_btc_102"
LABEL = "5M 102 BTC"
DESC  = "101 + Momentum (sanal $6)"
INITIAL_BALANCE = 150.0


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
        print(f"[5M 102 STATS] TG hata: {e}", file=sys.stderr)


def _today_key(iso_tr: str) -> bool:
    today = datetime.now(timezone.utc).astimezone(_TZ_TR).date().isoformat()
    return iso_tr[:10] == today


def build_message() -> str:
    hist  = _load_json(os.path.join(_DIR, f"poly_trader_{KEY}_history.json"))
    state = _load_json(os.path.join(_DIR, f"poly_trader_{KEY}_state.json"))

    total  = len(hist)
    wins   = sum(1 for t in hist if t.get("win"))
    losses = total - wins
    pnl    = round(state.get("total_pnl", sum(t.get("pnl", 0) for t in hist)), 2)
    balance = round(state.get("balance", INITIAL_BALANCE), 2)

    today_hist = [t for t in hist if _today_key(t.get("entry_time_tr", ""))]
    t_wins  = sum(1 for t in today_hist if t.get("win"))
    t_total = len(today_hist)
    t_pnl   = round(sum(t.get("pnl", 0) for t in today_hist), 2)

    open_pos = state.get("open_positions", [])
    open_n   = len(open_pos)
    risk     = round(sum(p.get("amount", 0) for p in open_pos), 2)

    up   = [t for t in hist if t.get("predicted_dir") == "UP"]
    down = [t for t in hist if t.get("predicted_dir") == "DOWN"]
    up_w = sum(1 for t in up if t.get("win"))
    dn_w = sum(1 for t in down if t.get("win"))

    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    pnl_icon = "🟢" if pnl >= 0 else "🔴"
    t_icon   = "🟢" if t_pnl >= 0 else "🔴"
    sep = "━" * 26

    lines = [
        sep,
        f"📊 <b>5M 102 BTC — Saatlik Özet</b>",
        f"🕐 {now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"<i>{DESC}</i>",
        "",
        f"💰 Bakiye: <b>${balance:.2f}</b>  (başlangıç ${INITIAL_BALANCE:.0f})",
        f"📂 Toplam: <b>{total}</b>  |  ✅ {wins}  |  ❌ {losses}  |  WR <b>{_wr(wins, total)}</b>",
        f"{pnl_icon} Net P&amp;L: <b>{'+' if pnl >= 0 else ''}{pnl:.2f}$</b>",
        "",
        f"📅 Bugün: <b>{t_total}</b> işlem  |  WR {_wr(t_wins, t_total)}  |  {t_icon} {'+' if t_pnl >= 0 else ''}{t_pnl:.2f}$",
        f"📈 UP: {_wr(up_w, len(up))} ({len(up)})  |  📉 DOWN: {_wr(dn_w, len(down))} ({len(down)})",
    ]

    if open_n:
        pos = open_pos[0]
        d_tr = "YÜKSELİR" if pos.get("predicted_dir") == "UP" else "DÜŞER"
        lines.append(f"🔴 Açık: {d_tr}  ${risk:.2f} risk  ({pos.get('consensus', '?')}/4)")
    else:
        lines.append("⚪ Açık pozisyon yok")

    lines.append(sep)
    return "\n".join(lines)


def run() -> None:
    tg_send(build_message())
    print("[5M 102 STATS] saatlik özet gönderildi")


if __name__ == "__main__":
    run()
