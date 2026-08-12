"""Yüksek güven vetosu — uzlaşı arttıkça beklenti düşüyor.

Neden bu filtre var
-------------------
`skill_audit.py` iki bağımsız kesitte aynı sonuca vardı:

  1) Algo içi skor yüzdeliği: üst %20 kovası SKILL **-0.0653%**, t=-3.89;
     5 zaman diliminin **5'inde de** negatif. Drift ayrıştırması yapıldı,
     DRIFT yalnızca +0.0144% — yani bu piyasa yönü değil, gerçek negatif
     yetenek. İleri doğrulama: eşik eğitimde (>85) seçildi, testte de
     tuttu (-0.0727%).
  2) Defterler arası uzlaşı: tam uzlaşı (≥%95) SKILL **-0.0658%**,
     t=-2.15; bölünmüş oylar (<%65) pozitif.

İki farklı ölçüm neredeyse aynı sayıyı verdi (-0.065 / -0.066). Bulgu
52 defterin 37'sinde (%71) mevcut, yani birkaç bozuk algoya ait değil.

Ne yapıyor / ne yapmıyor
------------------------
Üst güven kovasını **açmıyoruz**. Tersini açmak kâğıt üzerinde pozitif
(+0.0653% - %0.04 maker = +0.0253%/işlem) ama %95 güven aralığının alt
sınırı (+0.0264%) maker maliyetinin altında kaldığı için **gerçek parayla
ters işlem açılmıyor**. Bunun yerine vetolanan her sinyal gölge deftere
yazılıyor; ileriye dönük veri birikince karar veri ile verilecek.

Örneklem 5,2 gün. Bu modül eşikleri sabit sayı olarak taşımaz; oranlar
`skill_audit.py` yeniden çalıştırıldığında güncellenmelidir.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta

_DIR = os.path.dirname(os.path.abspath(__file__))
SHADOW_LOG = os.path.join(_DIR, "conviction_shadow.jsonl")
CONFIG_FILE = os.path.join(_DIR, "conviction_filter.json")
_TZ_TR = timezone(timedelta(hours=3))

# Ölçülen kenarlar (skill_audit 2026-08-11, 21.351 işlem / 5,2 gün)
MEASURED_TOP_SKILL_PCT = -0.0653
MEASURED_CONSENSUS_SKILL_PCT = -0.0658
MAKER_ROUNDTRIP_PCT = 0.04

DEFAULTS = {
    # Oy birliği = en yüksek güven kovası; ölçülen kenarı negatif.
    "veto_unanimous": True,
    # 4 defterden kaçı aynı yöne oy verirse veto: None = yalnız oy birliği.
    "veto_min_agree": None,
    # Vetolanan sinyalin tersini gerçek parayla açma. Kanıt yetersiz.
    "invert_vetoed": False,
    "shadow_log": True,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                raw = json.load(f) or {}
            if isinstance(raw, dict):
                cfg.update(raw)
        except Exception:
            pass
    return cfg


def agreement(candidate: dict) -> int:
    """Aynı yöne oy veren defter sayısı."""
    contributors = candidate.get("contributors") or []
    if contributors:
        return len(contributors)
    # Geriye uyum: score = base + 0.5*(agree-1), base majors'ta 2
    try:
        score = float(candidate.get("score") or 0)
    except (TypeError, ValueError):
        return 0
    if score <= 0:
        return 0
    base = 2.0 if score >= 2.0 else 1.0
    return int(round((score - base) / 0.5)) + 1


def evaluate(candidate: dict, *, total_books: int, cfg: dict | None = None) -> dict:
    """Aday açılmalı mı? `veto` True ise açılış atlanır."""
    cfg = cfg or load_config()
    agree = agreement(candidate)
    unanimous = total_books > 1 and agree >= total_books
    reasons = []
    if cfg.get("veto_unanimous") and unanimous:
        reasons.append(f"oy birliği {agree}/{total_books}")
    min_agree = cfg.get("veto_min_agree")
    if min_agree and agree >= int(min_agree):
        reasons.append(f"uzlaşı {agree} ≥ {min_agree}")
    return {
        "veto": bool(reasons),
        "reason": " · ".join(reasons),
        "agree": agree,
        "total_books": total_books,
        "unanimous": unanimous,
    }


def log_shadow(candidate: dict, verdict: dict, *, slot: str = "",
               label: str = "cr6") -> None:
    """Vetolanan sinyali kaydet — ileriye dönük doğrulama için.

    Gerçek emir yok; yalnız 'şu sinyali açmadık' kaydı. Sonradan fiyat
    çekilip vetonun doğru olup olmadığı ölçülebilir.
    """
    if not load_config().get("shadow_log"):
        return
    row = {
        "ts": datetime.now(_TZ_TR).isoformat(),
        "slot": slot,
        "label": label,
        "symbol": candidate.get("symbol"),
        "signal": candidate.get("signal"),
        "price": candidate.get("price"),
        "score": candidate.get("score"),
        "agree": verdict.get("agree"),
        "total_books": verdict.get("total_books"),
        "reason": verdict.get("reason"),
        "contributors": candidate.get("contributors") or [],
    }
    try:
        with open(SHADOW_LOG, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_shadow(limit: int | None = None) -> list[dict]:
    if not os.path.exists(SHADOW_LOG):
        return []
    out = []
    try:
        with open(SHADOW_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out[-limit:] if limit else out


def summary() -> dict:
    cfg = load_config()
    rows = read_shadow()
    by_reason: dict[str, int] = {}
    for r in rows:
        key = r.get("reason") or "?"
        by_reason[key] = by_reason.get(key, 0) + 1
    return {
        "config": cfg,
        "shadow_count": len(rows),
        "by_reason": by_reason,
        "measured_top_skill_pct": MEASURED_TOP_SKILL_PCT,
        "measured_consensus_skill_pct": MEASURED_CONSENSUS_SKILL_PCT,
        "maker_cost_pct": MAKER_ROUNDTRIP_PCT,
        "first": rows[0].get("ts") if rows else None,
        "last": rows[-1].get("ts") if rows else None,
    }


def _print_summary() -> None:
    s = summary()
    print("YÜKSEK GÜVEN VETOSU")
    print("-" * 60)
    for k, v in s["config"].items():
        print(f"  {k:18} = {v}")
    print()
    print(f"  ölçülen üst kova SKILL   : {s['measured_top_skill_pct']:+.4f}%")
    print(f"  ölçülen tam uzlaşı SKILL : {s['measured_consensus_skill_pct']:+.4f}%")
    print(f"  maker gidiş-dönüş        : {s['maker_cost_pct']:.4f}%")
    print()
    print(f"  gölge kayıt: {s['shadow_count']}")
    if s["shadow_count"]:
        print(f"  ilk: {s['first']}  son: {s['last']}")
        for reason, n in sorted(s["by_reason"].items(), key=lambda kv: -kv[1]):
            print(f"    {n:5}  {reason}")
    else:
        print("  (henüz veto yok — CR6 open çalıştıkça birikir)")


if __name__ == "__main__":
    _print_summary()
