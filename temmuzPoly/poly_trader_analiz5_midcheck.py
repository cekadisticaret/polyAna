"""5. Analiz — açık pozisyon :30 anlık değer + PM kotasyon görseli (Telegram)."""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

_ENV_FILE = os.path.join(_DIR, "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from poly_trader_analiz5 import (
    BOT_TOKEN,
    CHAT_ID,
    STATE_FILE,
    load_state,
    save_state,
    tg_send_photo,
    _pm_find_market,
    _binance_get,
)

_TZ_TR = ZoneInfo("Europe/Istanbul")
_PM_GAMMA = "https://gamma-api.polymarket.com/events"
LABEL = "5. ANALİZ"


def _get_price(symbol: str) -> float:
    raw = _binance_get("/fapi/v1/ticker/price", {"symbol": symbol})
    return float(raw["price"])


def _quote_for_symbol(sym: str) -> dict:
    name = sym.replace("USDT", "")
    now_utc = datetime.now(timezone.utc)
    et_hour = (now_utc - timedelta(hours=4)).hour
    row: dict = {"symbol": sym, "name": name}
    try:
        row["binance"] = round(_get_price(sym), 2 if name == "BTC" else 4)
    except Exception:
        row["binance"] = None
    try:
        pm = _pm_find_market(sym, et_hour, now_utc)
    except Exception:
        pm = None
    if not pm:
        row["error"] = "market yok"
        return row
    op = pm.get("outcome_prices") or []
    up_p = float(op[0]) if len(op) > 0 else None
    down_p = float(op[1]) if len(op) > 1 else None
    title = pm.get("title") or ""
    hour_lbl = title.split(",")[-1].strip() if "," in title else title
    row.update({
        "hour_et": hour_lbl,
        "up_cents": round(up_p * 100, 1) if up_p is not None else None,
        "down_cents": round(down_p * 100, 1) if down_p is not None else None,
    })
    return row


def _token_price_from_slug(pm_slug: str, token_dir: str) -> float | None:
    try:
        req = urllib.request.Request(
            f"{_PM_GAMMA}?slug={pm_slug}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
        if not data:
            return None
        m = data[0].get("markets", [{}])[0]
        raw = m.get("outcomePrices")
        op = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if len(op) >= 2:
            return float(op[0]) if token_dir == "UP" else float(op[1])
    except Exception:
        pass
    return None


def _position_value(pos: dict) -> tuple[float, float, float | None]:
    """(spent, current_value, token_price)"""
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    size = float(pos.get("pm_size") or 0)
    token_dir = pos.get("pm_token_dir") or pos.get("predicted_dir")
    slug = pos.get("pm_slug", "")
    tp = _token_price_from_slug(slug, token_dir) if slug and token_dir else None
    if tp is not None and size > 0:
        return spent, round(size * tp, 2), tp
    return spent, spent, tp


def _render_card(
    quote: dict,
    *,
    pred: str,
    spent: float,
    cur: float,
    stamp: str,
    out_path: str,
    test_tag: str = "",
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    name = quote["name"]
    hour_et = quote.get("hour_et") or "—"
    up_c = quote.get("up_cents")
    down_c = quote.get("down_cents")
    bn = quote.get("binance")
    delta = round(cur - spent, 2)
    delta_color = "#4ade80" if delta >= 0 else "#f87171"
    arr = "→"

    fig_h = 4.2 if not test_tag else 4.5
    fig, ax = plt.subplots(figsize=(5.4, fig_h))
    fig.patch.set_facecolor("#0d0d0d")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor("#0d0d0d")

    card = FancyBboxPatch(
        (0.03, 0.02), 0.94, 0.96,
        boxstyle="round,pad=0.02,rounding_size=0.035",
        facecolor="#141414", edgecolor="#2a2a2a", linewidth=1.5,
    )
    ax.add_patch(card)

    # üst başlık + saat damgası
    ax.text(0.08, 0.94, LABEL, fontsize=11, fontweight="bold", color="#888888", va="top")
    stamp_txt = f"{stamp} İST · canlı"
    if test_tag:
        stamp_txt += f" · {test_tag}"
    ax.text(0.92, 0.94, stamp_txt, fontsize=9, color="#4fc3f7", ha="right", va="top")

    # sembol + yön
    ax.text(0.08, 0.86, f"{name}  {pred}", fontsize=20, fontweight="bold", color="white", va="top")

    # anlık değer satırı
    pnl_sign = "+" if delta >= 0 else ""
    ax.text(
        0.08, 0.76,
        f"Anlık ${spent:.2f} {arr} ${cur:.2f}",
        fontsize=15, fontweight="bold", color="white", va="top",
    )
    ax.text(
        0.92, 0.76,
        f"{pnl_sign}{delta:.2f}$",
        fontsize=15, fontweight="bold", color=delta_color, ha="right", va="top",
    )

    # ayırıcı
    ax.plot([0.08, 0.92], [0.70, 0.70], color="#2a2a2a", linewidth=1)

    # PM saat + sembol satırı
    ax.text(0.08, 0.64, name, fontsize=13, fontweight="bold", color="#cccccc", va="top")
    ax.text(0.92, 0.64, hour_et, fontsize=9, color="#666666", ha="right", va="top")

    up_txt = f"{up_c:.1f}¢" if up_c is not None else "—"
    dn_txt = f"{down_c:.1f}¢" if down_c is not None else "—"

    for x0, lbl, val, bg, lc in [
        (0.08, "UP", up_txt, "#14291e", "#4ade80"),
        (0.54, "DOWN", dn_txt, "#291414", "#f87171"),
    ]:
        pill = FancyBboxPatch(
            (x0, 0.20), 0.38, 0.40,
            boxstyle="round,pad=0.02,rounding_size=0.06",
            facecolor=bg, edgecolor="none",
        )
        ax.add_patch(pill)
        ax.text(x0 + 0.19, 0.50, lbl, fontsize=10, fontweight="bold", color=lc, ha="center", va="center")
        ax.text(x0 + 0.19, 0.30, val, fontsize=20, fontweight="bold", color="white", ha="center", va="center")

    if bn is not None:
        bn_txt = f"Binance ${bn:,.1f}" if name == "BTC" else f"Binance ${bn}"
        ax.text(0.08, 0.10, bn_txt, fontsize=12, fontweight="bold", color="#e8e8e8", va="center")

    plt.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="#0d0d0d", pad_inches=0.12)
    plt.close()


def run() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    slot = now_tr.strftime("%Y-%m-%dT%H")  # saat başına bir kez

    state = load_state()
    positions = [
        p for p in state.get("open_positions", [])
        if p.get("pm_slug") and p.get("pm_order_id") and not p.get("pm_error")
    ]
    if not positions:
        print(f"[{LABEL} midcheck] {saat} — açık PM pozisyon yok")
        return

    changed = False
    for pos in positions:
        if (pos.get("midcheck_tr") or "").startswith(slot):
            continue

        sym = pos.get("symbol", "")
        if not sym:
            continue

        spent, cur, _ = _position_value(pos)
        quote = _quote_for_symbol(sym)
        if quote.get("error"):
            print(f"[{LABEL} midcheck] {sym} — kotasyon yok", file=sys.stderr)
            continue

        name = sym.replace("USDT", "")
        pred = pos.get("predicted_dir") or pos.get("pm_token_dir") or "?"
        img_path = f"/tmp/a5_midcheck_{name}_{slot.replace(':', '')}.png"
        _render_card(
            quote, pred=pred, spent=spent, cur=cur, stamp=saat, out_path=img_path,
        )

        tg_send_photo(img_path, "")
        pos["midcheck_tr"] = now_tr.isoformat()
        changed = True
        print(f"[{LABEL} midcheck] {saat} — {name} ${spent:.2f}→${cur:.2f} TG gönderildi")

    if changed:
        save_state(state)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
        saat = now_tr.strftime("%H:%M")
        quote = _quote_for_symbol("BTCUSDT")
        if quote.get("error"):
            print("Kotasyon alınamadı")
            sys.exit(1)
        spent, cur = 8.00, 8.15
        img = "/tmp/a5_midcheck_TEST.png"
        _render_card(
            quote, pred="DOWN", spent=spent, cur=cur, stamp=saat,
            out_path=img, test_tag="TEST",
        )
        tg_send_photo(img, "")
        print(f"[{LABEL} midcheck] TEST kart gönderildi (PM emir yok)")
    else:
        run()
