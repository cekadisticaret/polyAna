#!/usr/bin/env python3
"""'Coin liderleri' görselini (dashboard kartıyla aynı stil) PNG olarak üretir."""
from __future__ import annotations

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _twitter_handle() -> str:
    try:
        from post_tweet import TWITTER_HANDLE  # noqa: WPS433
        return TWITTER_HANDLE
    except Exception:
        return os.environ.get("TWITTER_HANDLE", "tradecomio").strip().lstrip("@")

W, H = 1080, 1350
TRADE_H = 900
PAD_X = 70

C_PURPLE_A = (91, 33, 182)     # #5b21b6
C_PURPLE_B = (124, 58, 237)    # #7c3aed
C_PURPLE_C = (167, 139, 250)   # #a78bfa
C_WHITE = (244, 244, 248)      # var(--txt)
C_MUTED = (222, 214, 245)      # yarı saydam beyaza yakın (mor zeminde okunaklı)
C_GREEN = (57, 255, 142)       # var(--green)
C_RED = (255, 92, 122)         # var(--red)
C_LINE = (255, 255, 255, 40)

C_BG_A = (7, 7, 11)            # #07070b
C_BG_B = (18, 18, 26)          # #12121a
C_CARD2 = (24, 24, 34)         # #181822
C_MUTED_DARK = (139, 139, 154)  # var(--muted)
C_ACCENT = (200, 241, 53)      # var(--accent) lime

_FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(_FONT_DIR, name), size)


def _diagonal_gradient(w: int, h: int) -> Image.Image:
    xs = np.linspace(0, 1, w, dtype=np.float32)
    ys = np.linspace(0, 1, h, dtype=np.float32)
    t = np.clip((xs[None, :] + ys[:, None]) / 2.0, 0.0, 1.0)  # 145deg yaklaşık diyagonal
    a = np.array(C_PURPLE_A, dtype=np.float32)
    b = np.array(C_PURPLE_B, dtype=np.float32)
    c = np.array(C_PURPLE_C, dtype=np.float32)
    t3 = t[..., None]
    first_half = a + (b - a) * np.clip(t3 * 2.0, 0.0, 1.0)
    second_half = b + (c - b) * np.clip(t3 * 2.0 - 1.0, 0.0, 1.0)
    rgb = np.where(t3 < 0.5, first_half, second_half).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def _vertical_gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    ys = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    a = np.array(top, dtype=np.float32)
    b = np.array(bottom, dtype=np.float32)
    row = a + (b - a) * ys
    rgb = np.repeat(row, w, axis=1).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def _fmt_money(v: float) -> str:
    sign = "+" if v >= 0 else "-"
    return f"{sign}${abs(v):,.2f}"


def _rounded_rect(draw: "ImageDraw.ImageDraw", box, radius: int, fill=None, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _trade_labels(lang: str) -> dict[str, str]:
    if lang == "en":
        return {
            "title": "TRADE RESULT",
            "entry": "ENTRY",
            "exit": "EXIT",
            "margin": "margin",
            "leverage": "leverage",
            "profit": "profit",
            "lev_return": "leveraged return",
        }
    return {
        "title": "İŞLEM SONUCU",
        "entry": "GİRİŞ",
        "exit": "KAPANIŞ",
        "margin": "marj",
        "leverage": "kaldıraç",
        "profit": "kâr",
        "lev_return": "kaldıraçlı getiri",
    }


def render_trade_card(trade: dict, *, ts_label: str, out_path: str, lang: str = "tr") -> str:
    """trade: {symbol, side, algo, book, interval, leverage, margin_usd,
    entry_price, exit_price, pnl, pnl_pct, close_reason}"""
    img = _vertical_gradient(W, TRADE_H, C_BG_A, C_BG_B)
    draw = ImageDraw.Draw(img, "RGBA")

    win = float(trade.get("pnl") or 0) >= 0
    glow = C_GREEN if win else C_RED

    # üstte hafif renkli parıltı şeridi
    draw.rectangle([(0, 0), (W, 10)], fill=glow)

    f_label = _font("DejaVuSans-Bold.ttf", 30)
    f_symbol = _font("DejaVuSans-Bold.ttf", 64)
    f_badge = _font("DejaVuSans-Bold.ttf", 28)
    f_price_lbl = _font("DejaVuSans.ttf", 26)
    f_price_val = _font("DejaVuSans-Bold.ttf", 46)
    f_arrow = _font("DejaVuSans-Bold.ttf", 40)
    f_hero = _font("DejaVuSans-Bold.ttf", 128)
    f_hero_sub = _font("DejaVuSans-Bold.ttf", 34)
    f_meta = _font("DejaVuSans.ttf", 26)
    f_footer = _font("DejaVuSans-Bold.ttf", 26)

    labels = _trade_labels(lang)

    y = 70
    draw.text((PAD_X, y), labels["title"], font=f_label, fill=C_MUTED_DARK)

    algo_lbl = str(trade.get("algo") or "")
    bbox = draw.textbbox((0, 0), algo_lbl, font=f_badge)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    bx0 = W - PAD_X - bw - 36
    _rounded_rect(draw, (bx0, y - 8, W - PAD_X, y - 8 + bh + 26), 14,
                  fill=(255, 255, 255, 18), outline=(255, 255, 255, 50), width=1)
    draw.text((bx0 + 18, y - 8 + 10), algo_lbl, font=f_badge, fill=C_WHITE)

    y += 68
    symbol = str(trade.get("symbol") or "").upper().replace("USDT", "")
    side = str(trade.get("side") or "").upper()
    draw.text((PAD_X, y), f"{symbol}/USDT", font=f_symbol, fill=C_WHITE)
    side_txt = f"{'▲' if side == 'LONG' else '▼'} {side}"
    side_color = C_GREEN if side == "LONG" else C_RED
    sbbox = draw.textbbox((0, 0), symbol + "/USDT", font=f_symbol)
    sx = PAD_X + (sbbox[2] - sbbox[0]) + 24
    _rounded_rect(draw, (sx, y + 10, sx + 190, y + 62), 16,
                  fill=(side_color[0], side_color[1], side_color[2], 34),
                  outline=(side_color[0], side_color[1], side_color[2], 120), width=2)
    draw.text((sx + 20, y + 18), side_txt, font=f_badge, fill=side_color)

    y += 110
    lev = trade.get("leverage")
    margin = trade.get("margin_usd")
    interval = trade.get("interval") or "1h"
    meta_txt = f"{interval.upper()} · ${margin:.0f} {labels['margin']}" if isinstance(margin, (int, float)) else interval.upper()
    if lev:
        meta_txt += f" · {int(lev)}x {labels['leverage']}"
    draw.text((PAD_X, y), meta_txt, font=f_meta, fill=C_MUTED_DARK)

    y += 56
    card_top = y
    card_h = 150
    _rounded_rect(draw, (PAD_X, card_top, W - PAD_X, card_top + card_h), 20,
                  fill=(255, 255, 255, 10), outline=(255, 255, 255, 22), width=1)

    entry_px = float(trade.get("entry_price") or 0)
    exit_px = float(trade.get("exit_price") or 0)
    col_w = (W - 2 * PAD_X) / 2
    cx = PAD_X + 40
    cy = card_top + 30
    draw.text((cx, cy), labels["entry"], font=f_price_lbl, fill=C_MUTED_DARK)
    draw.text((cx, cy + 38), f"${entry_px:,.4f}".rstrip("0").rstrip("."), font=f_price_val, fill=C_WHITE)

    ax = PAD_X + col_w
    draw.text((ax - 14, cy + 42), "→", font=f_arrow, fill=C_MUTED_DARK)

    cx2 = PAD_X + col_w + 40
    draw.text((cx2, cy), labels["exit"], font=f_price_lbl, fill=C_MUTED_DARK)
    draw.text((cx2, cy + 38), f"${exit_px:,.4f}".rstrip("0").rstrip("."), font=f_price_val, fill=C_WHITE)

    y = card_top + card_h + 60
    pnl = float(trade.get("pnl") or 0)
    pnl_pct = trade.get("pnl_pct")
    hero_color = C_GREEN if pnl >= 0 else C_RED
    hero_txt = f"{'+' if pnl_pct is not None and pnl_pct >= 0 else ''}{pnl_pct:.1f}%" if pnl_pct is not None else _fmt_money(pnl)
    hbbox = draw.textbbox((0, 0), hero_txt, font=f_hero)
    hw = hbbox[2] - hbbox[0]
    draw.text(((W - hw) / 2, y), hero_txt, font=f_hero, fill=hero_color)
    y += 176

    sub_txt = f"{_fmt_money(pnl)} {labels['profit']}" + (f" · {int(lev)}x {labels['lev_return']}" if lev else "")
    sbbox = draw.textbbox((0, 0), sub_txt, font=f_hero_sub)
    sw = sbbox[2] - sbbox[0]
    draw.text(((W - sw) / 2, y), sub_txt, font=f_hero_sub, fill=C_WHITE)
    y += 90

    footer_y = TRADE_H - 76
    draw.line([(PAD_X, footer_y - 24), (W - PAD_X, footer_y - 24)], fill=(255, 255, 255, 22), width=2)
    draw.text((PAD_X, footer_y), f"@{_twitter_handle()}", font=f_footer, fill=C_ACCENT)
    bbox = draw.textbbox((0, 0), ts_label, font=f_meta)
    tw = bbox[2] - bbox[0]
    draw.text((W - PAD_X - tw, footer_y + 2), ts_label, font=f_meta, fill=C_MUTED_DARK)

    img.save(out_path, "PNG")
    return out_path


def render_coin_leaders(rows: list[dict], *, avg_wr: float, coin_count: int, ts_label: str, out_path: str) -> str:
    """rows: [{"symbol","algo","wins","trades","pnl"}, ...] (en fazla 6)"""
    img = _diagonal_gradient(W, H)
    draw = ImageDraw.Draw(img, "RGBA")

    f_title = _font("DejaVuSans-Bold.ttf", 34)
    f_big = _font("DejaVuSans-Bold.ttf", 150)
    f_sub = _font("DejaVuSans.ttf", 30)
    f_row_main = _font("DejaVuSans-Bold.ttf", 38)
    f_row_meta = _font("DejaVuSans.ttf", 27)
    f_row_pnl = _font("DejaVuSans-Bold.ttf", 42)
    f_footer = _font("DejaVuSans-Bold.ttf", 26)

    y = 64
    draw.text((PAD_X, y), "COİN LİDERLERİ", font=f_title, fill=C_WHITE)
    y += 60
    draw.text((PAD_X, y), f"{avg_wr:.0f}%", font=f_big, fill=C_WHITE)
    y += 168
    draw.text((PAD_X, y), f"{coin_count} coin · ortalama WR · saatlik", font=f_sub, fill=C_MUTED)
    y += 66

    draw.line([(PAD_X, y), (W - PAD_X, y)], fill=(255, 255, 255, 60), width=2)
    y += 24

    row_h = 132
    for i, r in enumerate(rows[:6]):
        top = y + i * row_h
        label = f"{r['symbol']} · {r['algo']}"
        meta = f"{r['wins']}/{r['trades']} işlem"
        pnl = float(r.get("pnl") or 0)
        pnl_txt = _fmt_money(pnl)
        pnl_color = C_GREEN if pnl >= 0 else C_RED

        draw.text((PAD_X, top), label, font=f_row_main, fill=C_WHITE)
        draw.text((PAD_X, top + 48), meta, font=f_row_meta, fill=C_MUTED)

        bbox = draw.textbbox((0, 0), pnl_txt, font=f_row_pnl)
        pw = bbox[2] - bbox[0]
        draw.text((W - PAD_X - pw, top + 14), pnl_txt, font=f_row_pnl, fill=pnl_color)

        if i < min(len(rows), 6) - 1:
            ly = top + row_h - 14
            draw.line([(PAD_X, ly), (W - PAD_X, ly)], fill=(255, 255, 255, 28), width=1)

    footer_y = H - 76
    draw.line([(PAD_X, footer_y - 24), (W - PAD_X, footer_y - 24)], fill=(255, 255, 255, 40), width=2)
    draw.text((PAD_X, footer_y), f"@{_twitter_handle()}", font=f_footer, fill=C_WHITE)
    bbox = draw.textbbox((0, 0), ts_label, font=f_row_meta)
    tw = bbox[2] - bbox[0]
    draw.text((W - PAD_X - tw, footer_y + 2), ts_label, font=f_row_meta, fill=C_MUTED)

    img.save(out_path, "PNG")
    return out_path
