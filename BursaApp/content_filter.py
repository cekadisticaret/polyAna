"""Metin küfür / hakaret filtresi — yıldızlarla sansürler."""
from __future__ import annotations

import re

# Küçük harf; eşleşmede TR karakter varyantları normalize edilir
_BAD_WORDS = (
    "amk",
    "aq",
    "orospu",
    "orospuçocuğu",
    "orospu cocugu",
    "piç",
    "sik",
    "sikeyim",
    "sikerim",
    "göt",
    "yarrak",
    "kahpe",
    "pezevenk",
    "ibne",
    "oç",
)

_TR_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _norm(s: str) -> str:
    return s.translate(_TR_MAP).lower()


def _mask(match: re.Match) -> str:
    return "*" * len(match.group(0))


def filter_profanity(text: str) -> str:
    """Küfür/hakaret içeren kelimeleri aynı uzunlukta yıldızla değiştirir."""
    if not text or not text.strip():
        return ""
    out = text
    for word in _BAD_WORDS:
        plain = re.sub(r"\s+", "", word)
        letters = re.sub(r"[^a-z0-9]+", "", _norm(plain))
        if len(letters) < 2:
            continue
        if len(letters) <= 4:
            pattern = r"(?<![\w])" + re.escape(letters) + r"(?![\w])"
            out = re.sub(pattern, _mask, out, flags=re.IGNORECASE)
            continue
        gap = r"[\W_]*"
        pattern = gap.join(re.escape(c) for c in letters)
        out = re.sub(pattern, _mask, out, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", out).strip()


def profanity_ok(text: str) -> bool:
    """Sansür sonrası anlamlı metin kaldı mı?"""
    cleaned = filter_profanity(text)
    if not cleaned:
        return False
    letters = re.sub(r"[^\w]", "", cleaned, flags=re.UNICODE)
    return len(letters) >= 2 and not set(letters) <= {"*"}
