#!/usr/bin/env python3
"""CR6 Telegram kartı — ALGO2 Genel Konsensüs sarı kart stiline benzer PNG."""
from __future__ import annotations

import os
import urllib.parse
import urllib.request
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

_TZ = ZoneInfo("Europe/Istanbul")
_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ALGO2 koyu sarı palet
BG_TOP = (230, 194, 0)
BG_MID = (212, 176, 0)
BG_BOT = (196, 160, 0)
INK = (17, 17, 17)
MUTED = (60, 50, 20)
CHIP_BG = (0, 0, 0, 28)
UP = (10, 122, 62)
DN = (185, 28, 28)
FOOT_BG = (0, 0, 0, 36)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _FONT_B if bold and os.path.exists(_FONT_B) else _FONT
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _round_rect(draw: ImageDraw.ImageDraw, xy, r: int, fill) -> None:
    draw.rounded_rectangle(xy, radius=r, fill=fill)


def _gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), BG_MID)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        if t < 0.5:
            u = t * 2
            r = int(BG_TOP[0] + (BG_MID[0] - BG_TOP[0]) * u)
            g = int(BG_TOP[1] + (BG_MID[1] - BG_TOP[1]) * u)
            b = int(BG_TOP[2] + (BG_MID[2] - BG_TOP[2]) * u)
        else:
            u = (t - 0.5) * 2
            r = int(BG_MID[0] + (BG_BOT[0] - BG_MID[0]) * u)
            g = int(BG_MID[1] + (BG_BOT[1] - BG_MID[1]) * u)
            b = int(BG_MID[2] + (BG_BOT[2] - BG_MID[2]) * u)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def _name(sym: str) -> str:
    return (sym or "").replace("USDT", "")


def _dir_tr(side: str) -> str:
    return "Artar" if (side or "").upper() == "LONG" else "Düşer"


def _arrow(side: str) -> str:
    return "▲" if (side or "").upper() == "LONG" else "▼"


def render_open_card(
    positions: list[dict],
    *,
    margin_usd: float = 15.0,
    leverage: int = 15,
    now: datetime | None = None,
    title: str = "Supertrend · Futures Açılış",
    panel: str | None = None,
) -> bytes:
    """Açılış kartı PNG bytes — ALGO2 konsensüs layout."""
    now = now or datetime.now(_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_TZ)
    else:
        now = now.astimezone(_TZ)

    w, h = 720, 420
    base = _gradient(w, h).convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # dekor daireler
    d.ellipse((520, -60, 780, 200), fill=(0, 0, 0, 18))
    d.ellipse((560, 40, 720, 200), fill=(0, 0, 0, 14))

    f_title = _font(22, True)
    f_sub = _font(14)
    f_hero = _font(48, True)
    f_meta_k = _font(12)
    f_meta_v = _font(16, True)
    f_chip_n = _font(15, True)
    f_chip_a = _font(12, True)
    f_chip_p = _font(18, True)
    f_chip_c = _font(12)
    f_foot = _font(13)

    # pencere: bu saatin :05 — sonraki :02
    end_h = (now.hour + 1) % 24
    pencere = f"{now.strftime('%H')}:05—{end_h:02d}:02"
    updated = now.strftime("%H:%M")
    panel_txt = panel or f"ST Live · {len(positions)} işlem"

    d.text((28, 22), title, font=f_title, fill=INK)
    d.text(
        (28, 52),
        f"{updated} güncellendi · ${margin_usd:.0f}×{leverage}x · ATR kilit",
        font=f_sub,
        fill=MUTED,
    )

    top = positions[0] if positions else {}
    top_name = _name(top.get("symbol") or "—")
    top_side = top.get("side") or "LONG"
    hero = f"{top_name} {_arrow(top_side)} {_dir_tr(top_side)}"
    d.text((28, 90), hero, font=f_hero, fill=INK)

    # meta
    d.text((28, 160), "Panel", font=f_meta_k, fill=MUTED)
    d.text((28, 178), panel_txt, font=f_meta_v, fill=INK)
    d.text((360, 160), "Pencere", font=f_meta_k, fill=MUTED)
    d.text((360, 178), pencere, font=f_meta_v, fill=INK)

    # chips
    n = max(len(positions), 1)
    gap = 12
    chip_w = (w - 56 - gap * (min(n, 3) - 1)) // min(n, 3)
    chip_h = 110
    y0 = 220
    for i, pos in enumerate(positions[:3]):
        x0 = 28 + i * (chip_w + gap)
        _round_rect(d, (x0, y0, x0 + chip_w, y0 + chip_h), 18, CHIP_BG)
        name = _name(pos.get("symbol") or "")
        side = pos.get("side") or "LONG"
        up = side.upper() == "LONG"
        pill = _dir_tr(side)
        entry = float(pos.get("entry_price") or 0)
        tier = pos.get("tier_label") or ""
        atr_u = pos.get("atr_usd")
        d.text((x0 + 14, y0 + 12), name, font=f_chip_n, fill=INK)
        # pill
        pw, ph = 70, 22
        px, py = x0 + 14, y0 + 38
        _round_rect(d, (px, py, px + pw, py + ph), 11, UP if up else DN)
        d.text((px + 10, py + 3), pill, font=f_chip_a, fill=(255, 255, 255))
        entry_s = f"${entry:.4f}" if entry < 10 else f"${entry:.2f}"
        d.text((x0 + 14, y0 + 68), entry_s, font=f_chip_p, fill=INK)
        sub = tier
        if atr_u:
            sub = f"{tier} · atr${float(atr_u):.1f}" if tier else f"atr${float(atr_u):.1f}"
        d.text((x0 + 14, y0 + 90), sub or "—", font=f_chip_c, fill=MUTED)

    # footer
    _round_rect(d, (20, h - 56, w - 20, h - 16), 14, FOOT_BG)
    parts = []
    for p in positions:
        parts.append(
            f"{_name(p.get('symbol'))} {_dir_tr(p.get('side') or 'LONG').lower()} "
            f"@{float(p.get('entry_price') or 0):.4f}"
        )
    foot = (
        f"Şu an {now.strftime('%H:%M')}  ·  {pencere} arasında Supertrend "
        f"${margin_usd:.0f}×{leverage}x: " + " • ".join(parts)
    )
    d.text((34, h - 44), foot[:95], font=f_foot, fill=INK)

    out = Image.alpha_composite(base, overlay).convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_event_card(
    title: str,
    hero: str,
    rows: list[str],
    *,
    footer: str = "",
    now: datetime | None = None,
) -> bytes:
    """Kapanış / hold / ATR stop için aynı palet."""
    now = now or datetime.now(_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_TZ)
    else:
        now = now.astimezone(_TZ)

    w, h = 720, 360
    base = _gradient(w, h).convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.ellipse((520, -60, 780, 200), fill=(0, 0, 0, 18))

    f_title = _font(22, True)
    f_sub = _font(14)
    f_hero = _font(40, True)
    f_row = _font(16, True)
    f_foot = _font(13)

    d.text((28, 22), title, font=f_title, fill=INK)
    d.text((28, 52), f"{now.strftime('%H:%M')} güncellendi · CR6", font=f_sub, fill=MUTED)
    d.text((28, 95), hero[:40], font=f_hero, fill=INK)

    y = 170
    for line in rows[:5]:
        _round_rect(d, (28, y, w - 28, y + 36), 12, CHIP_BG)
        d.text((42, y + 8), line[:70], font=f_row, fill=INK)
        y += 44

    if footer:
        _round_rect(d, (20, h - 52, w - 20, h - 14), 14, FOOT_BG)
        d.text((34, h - 40), footer[:100], font=f_foot, fill=INK)

    out = Image.alpha_composite(base, overlay).convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def tg_send_photo(
    bot_token: str,
    chat_id: str,
    png: bytes,
    caption: str = "",
) -> None:
    if not bot_token or not chat_id or not png:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    boundary = "----Cr6CardBoundary"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode(),
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n"
            f"{caption}\r\n"
        ).encode(),
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; "
            f"filename=\"cr6.png\"\r\nContent-Type: image/png\r\n\r\n"
        ).encode()
        + png
        + f"\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()
