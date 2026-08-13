"""Poly Telegram kanal yönlendirme — tek kaynak.

1. ANALİZ sanal defteri (poly_trader_analiz1.py) yalnızca TELEGRAM_ANALIZ1_CHAT_ID
kanalına yazar (varsayılan 830754964).

Diğer tüm poly trader / live / kripto bildirimleri bu kanala ASLA düşmez;
TELEGRAM_POLY_TRADERS_CHAT_ID veya TELEGRAM_CHAT kullanılır (farklı bir ID olmalı).
"""
from __future__ import annotations

import os

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


# Yalnızca 1. ANALİZ sanal defteri
ANALIZ1_CHAT_ID = _env("TELEGRAM_ANALIZ1_CHAT_ID", "")


def _not_analiz1(cid: str) -> str:
    """Analiz1 kanalı başka trader'lara yanlışlıkla verilmesin."""
    if not cid or cid == ANALIZ1_CHAT_ID:
        return ""
    return cid


def chat_analiz1() -> str:
    return ANALIZ1_CHAT_ID


def chat_poly_traders() -> str:
    """1. ANALİZ dışı genel poly trader bildirimleri."""
    return _not_analiz1(_env("TELEGRAM_POLY_TRADERS_CHAT_ID") or _env("TELEGRAM_CHAT"))


def chat_pm_live() -> str:
    """A1 Live + gerçek PM trader'lar (PolyAktif bot)."""
    return _not_analiz1(_env("TELEGRAM_PM_LIVE_CHAT_ID") or chat_poly_traders())


def chat_analiz4() -> str:
    return _not_analiz1(_env("TELEGRAM_ANALIZ4_CHAT_ID") or chat_poly_traders())


def chat_analiz9() -> str:
    return _not_analiz1(_env("TELEGRAM_ANALIZ9_CHAT_ID") or chat_poly_traders())


def chat_analiz10() -> str:
    return _not_analiz1(_env("TELEGRAM_ANALIZ10_CHAT_ID") or chat_poly_traders())


def chat_analist() -> str:
    return _not_analiz1(_env("TELEGRAM_ANALIST_CHAT_ID") or chat_poly_traders())
