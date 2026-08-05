#!/usr/bin/env python3
"""Kripto sanal algoritma TG — 10. ANALİZ kanalı (poly_analiz_dual_core)."""
from __future__ import annotations

import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
_POLY = os.path.join(_ROOT, "temmuzPoly")
if _POLY not in sys.path:
    sys.path.insert(0, _POLY)

from poly_analiz_dual_core import tg_send  # noqa: E402

TG_LABEL = "KRİPTO ALGORİTMALAR"
SEP = "━" * 26
_SIZE_TAG = "$30×10x · max 6"


def send(text: str) -> None:
    tg_send(text)


def _wr(wins: int, total: int) -> str:
    return f"%{wins / total * 100:.0f} ({wins}/{total})" if total else "—"


def _format_close_trade(t: dict) -> str:
    sym = (t.get("symbol") or "").replace("USDT", "")
    side = (t.get("side") or "").upper()
    entry = float(t.get("entry_price") or 0)
    exit_p = float(t.get("exit_price") or 0)
    pnl = float(t.get("pnl") or 0)
    icon = "✅" if pnl >= 0 else "❌"
    return f"{icon} {sym} {side} {entry:.4f}→{exit_p:.4f} {'+' if pnl >= 0 else ''}{pnl:.2f}$"


def _format_open_pos(p: dict) -> str:
    sym = (p.get("symbol") or "").replace("USDT", "")
    side = (p.get("side") or "").upper()
    entry = float(p.get("entry_price") or 0)
    icon = "📈" if side == "LONG" else "📉"
    dir_tr = "YÜKSELİR" if side == "LONG" else "DÜŞER"
    fee = float(p.get("entry_fee") or 0)
    fee_s = f"  kom≈${fee:.2f}" if fee else ""
    return f"{icon} {sym} {dir_tr} @{entry:.4f}{fee_s}"


def notify_close(
    *,
    saat_round: str,
    blocks: list[str],
    tur_pnl: float,
    total_closed: int,
    total_held: int,
) -> None:
    if not blocks or total_closed <= 0:
        return
    pnl_icon = "🟢" if tur_pnl >= 0 else "🔴"
    tur_str = f"{'+' if tur_pnl >= 0 else ''}{tur_pnl:.2f}$"
    held_note = f"  |  ATR hold: {total_held}" if total_held else ""
    body = (
        f"{SEP}\n"
        f"🏁 <b>{TG_LABEL} — {saat_round} Sonuçlar</b>  🔶 SANAL\n"
        f"{_SIZE_TAG}{held_note}\n\n"
        + f"\n\n{SEP}\n\n".join(blocks)
        + f"\n{SEP}\n"
        f"Bu tur: {tur_str}  |  Kapatılan: {total_closed} poz\n"
        f"{pnl_icon} Tur net P&L: {tur_str}\n"
        f"{SEP}"
    )
    if len(body) > 4000:
        body = body[:3950] + "\n… (mesaj kısaltıldı)\n" + SEP
    send(body)


def notify_open(
    *,
    saat: str,
    next_h: str,
    blocks: list[str],
    total_opened: int,
    total_open: int,
) -> None:
    if not blocks or total_opened <= 0:
        return
    body = (
        f"{SEP}\n"
        f"🆕 <b>{TG_LABEL} — {saat} - {next_h} Yeni İşlemler</b>  🔶 SANAL\n"
        f"{_SIZE_TAG}\n\n"
        + f"\n\n{SEP}\n\n".join(blocks)
        + f"\n{SEP}\n"
        f"📂 Açılan: {total_opened} poz  |  Toplam açık: {total_open}\n"
        f"{SEP}"
    )
    if len(body) > 4000:
        body = body[:3950] + "\n… (mesaj kısaltıldı)\n" + SEP
    send(body)
