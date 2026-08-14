#!/usr/bin/env python3
"""JARVIS — Kripto Test defterlerinin kendini güncelleyen denetim raporu.

Her gece 00:00 (İST) cron ile koşar, `AgustosKripto/Test/data/*.json`
dosyalarını okuyup tek bir anlık görüntü üretir:

  jarvis_report.json    → en güncel rapor (dashboard bunu okur)
  jarvis_history.jsonl  → her koşunun özeti (gün gün değişimi izlemek için)

Ölçüt WR değil **drift-nötr SKILL**: (ort.LONG% + ort.SHORT%) / 2. Sebep,
`runner.py` içinde uzun uzun anlatılıyor — WR örneklem dönemindeki piyasa
yönünü ölçüyor, algoritmanın becerisini değil.

Kullanım:
    python3 AgustosKripto/Test/jarvis_report.py          # üret + kaydet
    python3 AgustosKripto/Test/jarvis_report.py --print  # üret + ekrana bas
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_DIR, "data")
REPORT_FILE = os.path.join(_DIR, "jarvis_report.json")
HISTORY_FILE = os.path.join(_DIR, "jarvis_history.jsonl")

TR = timezone(timedelta(hours=3))

# Nitelik kapısı. LEADER_MIN_SKILL runner.py'de %0.04 ("maker gidiş-dönüş")
# ama defterler taker ödüyor — gerçek maliyet veriden ölçülüp kullanılıyor.
KOD_ESIGI_PCT = 0.04
MIN_TRADES = 20


# ── yardımcılar ───────────────────────────────────────────────


def _ret_pct(t: dict) -> float | None:
    """Kaldıraçsız yüzde getiri — yön düzeltmeli (runner._trade_ret_pct ile aynı)."""
    try:
        entry = float(t["entry_price"])
        exit_ = float(t["exit_price"])
    except (KeyError, TypeError, ValueError):
        return None
    if entry <= 0:
        return None
    move = (exit_ - entry) / entry * 100.0
    return move if t.get("side") == "LONG" else -move


def _mean_sd(vals: list[float]) -> tuple[float, float]:
    n = len(vals)
    if not n:
        return 0.0, 0.0
    mu = sum(vals) / n
    sd = (sum((v - mu) ** 2 for v in vals) / n) ** 0.5 if n > 1 else 0.0
    return mu, sd


def _skill(longs: list[float], shorts: list[float]) -> tuple[float | None, float | None, float | None]:
    """SKILL, DRIFT ve SKILL'in kendi t-istatistiği.

    runner.py'deki `t` birleşik ortalamanın t'si — içinde drift de var.
    Burada SKILL'in kendi standart hatası kullanılıyor (iki örneklem),
    yani "bu beceri sıfırdan farklı mı" sorusunun doğru testi.
    """
    if len(longs) < 2 or len(shorts) < 2:
        return None, None, None
    ml, sl = _mean_sd(longs)
    ms, ss = _mean_sd(shorts)
    skill = (ml + ms) / 2
    drift = (ms - ml) / 2
    se = math.sqrt(sl**2 / len(longs) + ss**2 / len(shorts)) / 2
    t = skill / se if se > 0 else 0.0
    return skill, drift, t


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _history_rows(raw) -> list[dict]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return raw.get("history") or raw.get("trades") or []
    return []


# ── rapor ─────────────────────────────────────────────────────


def build_report() -> dict:
    books: list[dict] = []
    all_trades: list[dict] = []
    bos_defterler: list[str] = []
    toplam_bakiye = toplam_deposit = 0.0

    for state_path in sorted(glob.glob(os.path.join(DATA_DIR, "*_state.json"))):
        base = os.path.basename(state_path)
        key = base[len("test_") : -len("_state.json")] if base.startswith("test_") else base[: -len("_state.json")]
        state = _load(state_path) or {}
        toplam_bakiye += float(state.get("balance") or 0)
        toplam_deposit += float(state.get("deposit") or 0)

        rows = _history_rows(_load(state_path.replace("_state.json", "_history.json")))
        if not rows:
            bos_defterler.append(key)
            continue

        longs: list[float] = []
        shorts: list[float] = []
        for t in rows:
            t["_book"] = key
            v = _ret_pct(t)
            if v is None:
                continue
            (longs if t.get("side") == "LONG" else shorts).append(v)
        all_trades.extend(rows)

        skill, drift, tstat = _skill(longs, shorts)
        wins = sum(1 for r in rows if r.get("win") is True)
        n = len(rows)
        books.append(
            {
                "key": key,
                "ad": (rows[-1].get("book") or rows[-1].get("algo") or key),
                "n": n,
                "wr": round(100.0 * wins / n, 1),
                "skill": round(skill, 4) if skill is not None else None,
                "drift": round(drift, 4) if drift is not None else None,
                "t": round(tstat, 2) if tstat is not None else None,
                "brut": round(sum(float(r.get("pnl_gross") or 0) for r in rows), 2),
                "net": round(float(state.get("total_pnl") or 0), 2),
                "komisyon": round(float(state.get("total_commission") or 0), 2),
                "bakiye": round(float(state.get("balance") or 0), 2),
            }
        )

    books.sort(key=lambda b: -(b["skill"] if b["skill"] is not None else -99))

    brut = round(sum(float(t.get("pnl_gross") or 0) for t in all_trades), 2)
    net = round(sum(float(t.get("pnl") or 0) for t in all_trades), 2)
    komisyon = round(brut - net, 2)

    # gerçek gidiş-dönüş taker oranı (veriden — varsayım değil)
    oranli = [t for t in all_trades if float(t.get("notional") or 0) > 0 and t.get("commission") is not None]
    gercek_oran = (
        round(sum(float(t["commission"]) / float(t["notional"]) for t in oranli) / len(oranli) * 100, 4)
        if oranli
        else 0.10
    )

    # günlük seri
    gun = defaultdict(lambda: {"n": 0, "brut": 0.0, "net": 0.0})
    for t in all_trades:
        d = (t.get("entry_time_tr") or "")[:10]
        if not d:
            continue
        gun[d]["n"] += 1
        gun[d]["brut"] += float(t.get("pnl_gross") or 0)
        gun[d]["net"] += float(t.get("pnl") or 0)
    gunluk = [
        {"gun": d, "n": v["n"], "brut": round(v["brut"], 2), "net": round(v["net"], 2)}
        for d, v in sorted(gun.items())
        if v["n"] >= 10  # ilk kısmi günü eleme
    ]

    # kapanış sebebi
    kap = defaultdict(lambda: {"n": 0, "net": 0.0, "wins": 0})
    for t in all_trades:
        r = t.get("close_reason") or "?"
        kap[r]["n"] += 1
        kap[r]["net"] += float(t.get("pnl") or 0)
        if t.get("win") is True:
            kap[r]["wins"] += 1
    kapanis = sorted(
        (
            {
                "sebep": r,
                "n": v["n"],
                "wr": round(100.0 * v["wins"] / v["n"], 1),
                "net": round(v["net"], 2),
                "ort": round(v["net"] / v["n"], 2),
            }
            for r, v in kap.items()
        ),
        key=lambda x: -x["n"],
    )

    # coin
    sym = defaultdict(lambda: {"n": 0, "net": 0.0, "brut": 0.0, "wins": 0})
    for t in all_trades:
        s = (t.get("symbol") or "?").replace("USDT", "")
        sym[s]["n"] += 1
        sym[s]["net"] += float(t.get("pnl") or 0)
        sym[s]["brut"] += float(t.get("pnl_gross") or 0)
        if t.get("win") is True:
            sym[s]["wins"] += 1
    coinler = sorted(
        (
            {
                "coin": s,
                "n": v["n"],
                "wr": round(100.0 * v["wins"] / v["n"], 1),
                "brut": round(v["brut"], 2),
                "net": round(v["net"], 2),
            }
            for s, v in sym.items()
        ),
        key=lambda x: -x["n"],
    )

    olculebilir = [b for b in books if b["skill"] is not None]
    pozitif = [b for b in olculebilir if b["skill"] > 0]
    esik_ustu = [b for b in olculebilir if b["skill"] >= gercek_oran]
    anlamli = [b for b in olculebilir if b["t"] is not None and abs(b["t"]) >= 2]
    ort_skill = round(sum(b["skill"] for b in olculebilir) / len(olculebilir), 4) if olculebilir else 0.0
    # Bonferroni: aynı anda N test edilince gereken eşik
    bonferroni_t = round(2.0 + 0.45 * math.log(max(len(olculebilir), 1)), 2)

    zaman = sorted(t.get("entry_time_tr", "") for t in all_trades if t.get("entry_time_tr"))
    karli = [b for b in books if b["net"] > 0]

    rapor = {
        "olusturma": datetime.now(TR).isoformat(timespec="seconds"),
        "ozet": {
            "defter": len(books) + len(bos_defterler),
            "aktif_defter": len(books),
            "bos_defter": len(bos_defterler),
            "bos_defter_liste": bos_defterler,
            "islem": len(all_trades),
            "brut": brut,
            "net": net,
            "komisyon": komisyon,
            "bakiye": round(toplam_bakiye, 2),
            "deposit": round(toplam_deposit, 2),
            "kayip_yuzde": round(-100.0 * net / toplam_deposit, 2) if toplam_deposit else 0.0,
            "ilk_islem": zaman[0][:19] if zaman else None,
            "son_islem": zaman[-1][:19] if zaman else None,
            "karli_defter": len(karli),
        },
        "maliyet": {
            "gercek_oran": gercek_oran,
            "kod_esigi": KOD_ESIGI_PCT,
            "kat": round(gercek_oran / KOD_ESIGI_PCT, 1) if KOD_ESIGI_PCT else 0,
            "islem_basi": round(komisyon / len(all_trades), 3) if all_trades else 0.0,
        },
        "beceri": {
            "olculebilir": len(olculebilir),
            "pozitif": len(pozitif),
            "ort_skill": ort_skill,
            "anlamli": len(anlamli),
            "anlamli_beklenen": round(0.05 * len(olculebilir), 1),
            "bonferroni_t": bonferroni_t,
            "esik_ustu": len(esik_ustu),
            "esik_ustu_liste": [b["key"] for b in esik_ustu],
        },
        "lider": books[0] if books else None,
        "en_karli": max(books, key=lambda b: b["net"]) if books else None,
        "defterler": books,
        "gunluk": gunluk,
        "kapanis": kapanis,
        "coinler": coinler[:12],
        "bulgular": _bulgular(brut, komisyon, net, gercek_oran, olculebilir, pozitif, esik_ustu, kapanis, karli),
    }
    return rapor


def _bulgular(brut, komisyon, net, oran, olculebilir, pozitif, esik_ustu, kapanis, karli) -> list[dict]:
    """Veriden otomatik türeyen yorumlar — her koşuda yeniden yazılır."""
    out: list[dict] = []

    if komisyon > 0 and abs(brut) < komisyon * 0.25:
        out.append(
            {
                "tip": "kritik",
                "baslik": "Zararın tamamı komisyon",
                "metin": (
                    f"İşlemlerin brüt sonucu ${brut:+,.2f} — pratikte sıfır. "
                    f"Ödenen komisyon ${komisyon:,.2f}. Yani algoritmalar ne kazandırdı ne kaybettirdi; "
                    f"kasayı işlem ücreti eritti."
                ),
            }
        )

    if oran > KOD_ESIGI_PCT * 1.5:
        out.append(
            {
                "tip": "uyari",
                "baslik": "Nitelik kapısının eşiği gerçek maliyetin altında",
                "metin": (
                    f"runner.py'de LEADER_MIN_SKILL = %{KOD_ESIGI_PCT:.2f} ve yorumunda 'maker' yazıyor. "
                    f"Ama işlem verisinden ölçülen gerçek gidiş-dönüş taker maliyeti %{oran:.4f} — "
                    f"{oran / KOD_ESIGI_PCT:.1f} katı. Kapı, masrafını çıkaramayan defterleri nitelikli gösteriyor."
                ),
            }
        )

    if olculebilir:
        pay = 100.0 * len(pozitif) / len(olculebilir)
        out.append(
            {
                "tip": "bilgi" if 40 <= pay <= 60 else "uyari",
                "baslik": "Beceri dağılımı yazı-turaya benziyor"
                if 40 <= pay <= 60
                else "Beceri dağılımı simetrik değil",
                "metin": (
                    f"{len(olculebilir)} ölçülebilir defterin %{pay:.0f}'i pozitif SKILL'e sahip "
                    f"(rastgelede %50 beklenir). Gerçek maliyet eşiğini aşan defter: {len(esik_ustu)}."
                ),
            }
        )

    zaman_cikis = [k for k in kapanis if k["sebep"] in ("1h_close", "4h_close")]
    if zaman_cikis:
        tn = sum(k["n"] for k in zaman_cikis)
        tnet = sum(k["net"] for k in zaman_cikis)
        toplam_n = sum(k["n"] for k in kapanis) or 1
        out.append(
            {
                "tip": "uyari",
                "baslik": "Zarar zamanlı kapanışlardan geliyor",
                "metin": (
                    f"İşlemlerin %{100 * tn / toplam_n:.0f}'i sinyal yüzünden değil, süre dolduğu için "
                    f"kapanıyor (1h/4h close) ve bu grup ${tnet:+,.2f} üretiyor."
                ),
            }
        )

    atr = [k for k in kapanis if k["sebep"].startswith("atr")]
    if atr:
        anet = sum(k["net"] for k in atr)
        if anet > 0:
            out.append(
                {
                    "tip": "iyi",
                    "baslik": "ATR katmanı pozitif çalışıyor",
                    "metin": (
                        f"Kâr kilidi + zarar-stopu birlikte ${anet:+,.2f} üretiyor. "
                        f"Sistemdeki tek net pozitif bileşen bu."
                    ),
                }
            )

    if karli:
        out.append(
            {
                "tip": "bilgi",
                "baslik": f"{len(karli)} defter net artıda",
                "metin": "En iyileri: "
                + " · ".join(f"{b['key']} ${b['net']:+.2f}" for b in sorted(karli, key=lambda x: -x["net"])[:5]),
            }
        )

    return out


# ── kayıt ─────────────────────────────────────────────────────


def save(rapor: dict) -> None:
    tmp = REPORT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rapor, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, REPORT_FILE)

    o = rapor["ozet"]
    satir = {
        "ts": rapor["olusturma"],
        "gun": rapor["olusturma"][:10],
        "islem": o["islem"],
        "brut": o["brut"],
        "net": o["net"],
        "komisyon": o["komisyon"],
        "bakiye": o["bakiye"],
        "aktif_defter": o["aktif_defter"],
        "karli_defter": o["karli_defter"],
        "ort_skill": rapor["beceri"]["ort_skill"],
        "esik_ustu": rapor["beceri"]["esik_ustu"],
        "lider": (rapor["lider"] or {}).get("key"),
        "lider_skill": (rapor["lider"] or {}).get("skill"),
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(satir, ensure_ascii=False) + "\n")


def load_report() -> dict | None:
    return _load(REPORT_FILE)


def load_history(limit: int = 60) -> list[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    rows: list[dict] = []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    # gün başına son kayıt
    son: dict[str, dict] = {}
    for r in rows:
        son[r.get("gun") or r.get("ts", "")[:10]] = r
    return [son[k] for k in sorted(son)][-limit:]


def main() -> None:
    rapor = build_report()
    save(rapor)
    o, b, m = rapor["ozet"], rapor["beceri"], rapor["maliyet"]
    print(
        f"[jarvis] {rapor['olusturma']} · {o['aktif_defter']} defter · {o['islem']} işlem · "
        f"brüt ${o['brut']:+,.2f} · komisyon ${o['komisyon']:,.2f} · net ${o['net']:+,.2f}"
    )
    print(
        f"[jarvis] SKILL ort %{b['ort_skill']:+.4f} · pozitif {b['pozitif']}/{b['olculebilir']} · "
        f"maliyet eşiği %{m['gercek_oran']:.4f} · eşiği aşan {b['esik_ustu']}"
    )
    if "--print" in sys.argv:
        for f in rapor["bulgular"]:
            print(f"  [{f['tip']}] {f['baslik']} — {f['metin']}")
    # Sistem denetimi — aynı gece 00:00 turunda
    try:
        import jarvis_audit as _ja
        _ja.save(_ja.build_report())
        ao = _ja.load_report()["ozet"]
        print(
            f"[jarvis-audit] {ao['defter']} defter · {ao['islem']} işlem · "
            f"net ${ao['net']:+,.2f}"
        )
    except Exception as exc:
        print(f"[jarvis-audit] HATA: {exc}")


if __name__ == "__main__":
    main()
