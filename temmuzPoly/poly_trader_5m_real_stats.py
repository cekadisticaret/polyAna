"""5M 102/105 BTC sanal trader — saatlik istatistik bildirimi."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from poly_tg_5m_102 import tg_send

_TZ_TR = ZoneInfo("Europe/Istanbul")

SYSTEMS = [
    {
        "key": "5m_btc_102",
        "label": "5M 102 BTC",
        "desc": "101 + KALEM (sanal)",
        "initial": 200.0,
    },
    {
        "key": "5m_btc_105",
        "label": "5M 105 BTC",
        "desc": "102 + MR veto + trend nötr (gerçek PM $2)",
        "initial": 200.0,
    },
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


def _today_key(iso_tr: str) -> bool:
    today = datetime.now(timezone.utc).astimezone(_TZ_TR).date().isoformat()
    return iso_tr[:10] == today


def build_message(cfg: dict) -> str:
    key = cfg["key"]
    hist = _load_json(os.path.join(_DIR, f"poly_trader_{key}_history.json"))
    state = _load_json(os.path.join(_DIR, f"poly_trader_{key}_state.json"))
    initial = cfg["initial"]

    total = len(hist)
    wins = sum(1 for t in hist if t.get("win"))
    losses = total - wins
    pnl = round(state.get("total_pnl", sum(t.get("pnl", 0) for t in hist)), 2)
    balance = round(state.get("balance", initial), 2)

    today_hist = [t for t in hist if _today_key(t.get("entry_time_tr", ""))]
    t_wins = sum(1 for t in today_hist if t.get("win"))
    t_total = len(today_hist)
    t_pnl = round(sum(t.get("pnl", 0) for t in today_hist), 2)

    open_pos = state.get("open_positions", [])
    open_n = len(open_pos)
    risk = round(sum(p.get("pm_spent") or p.get("amount", 0) for p in open_pos), 2)

    up = [t for t in hist if t.get("predicted_dir") == "UP"]
    down = [t for t in hist if t.get("predicted_dir") == "DOWN"]
    up_w = sum(1 for t in up if t.get("win"))
    dn_w = sum(1 for t in down if t.get("win"))

    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    pnl_icon = "🟢" if pnl >= 0 else "🔴"
    t_icon = "🟢" if t_pnl >= 0 else "🔴"
    sep = "━" * 26

    lines = [
        sep,
        f"📊 <b>{cfg['label']} — Saatlik Özet</b>",
        f"🕐 {now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"<i>{cfg['desc']}</i>",
        "",
        f"💰 Bakiye: <b>${balance:.2f}</b>  (başlangıç ${initial:.0f})",
        f"📂 Toplam: <b>{total}</b>  |  ✅ {wins}  |  ❌ {losses}  |  WR <b>{_wr(wins, total)}</b>",
        f"{pnl_icon} Net P&amp;L: <b>{'+' if pnl >= 0 else ''}{pnl:.2f}$</b>",
        "",
        f"📅 Bugün: <b>{t_total}</b> işlem  |  WR {_wr(t_wins, t_total)}  |  {t_icon} {'+' if t_pnl >= 0 else ''}{t_pnl:.2f}$",
        f"📈 UP: {_wr(up_w, len(up))} ({len(up)})  |  📉 DOWN: {_wr(dn_w, len(down))} ({len(down)})",
    ]

    if open_n:
        parts = []
        for pos in open_pos[:3]:
            d_tr = "YÜKSELİR" if pos.get("predicted_dir") == "UP" else "DÜŞER"
            amt = pos.get("pm_spent") or pos.get("amount", 0)
            cons = pos.get("consensus", "?")
            parts.append(f"{d_tr} ${amt:.2f} ({cons}/4)")
        extra = f" +{open_n - 3} daha" if open_n > 3 else ""
        lines.append(f"🔴 Açık ({open_n}): {', '.join(parts)}{extra}  |  ${risk:.2f} risk")
    else:
        lines.append("⚪ Açık pozisyon yok")

    lines.append(sep)
    return "\n".join(lines)


def run(key: str | None = None) -> None:
    targets = SYSTEMS
    if key:
        targets = [c for c in SYSTEMS if c["key"] == key or c["key"].endswith(key)]
        if not targets:
            print(f"[5M STATS] Bilinmeyen key: {key}")
            return

    for i, cfg in enumerate(targets):
        ok = tg_send(build_message(cfg))
        print(f"[{cfg['label']} STATS] saatlik özet: {'OK' if ok else 'HATA'}")
        if i < len(targets) - 1:
            time.sleep(1)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(arg)
