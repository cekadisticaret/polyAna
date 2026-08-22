#!/usr/bin/env python3
"""JARVIS — Kripto Sistem Denetimi (yalnız /kripto/test).

`skill_audit.py` üzerine kurulu; aktif sanal defterler Test'tedir.
Çıktı: `jarvis_audit.json` (JARVIS 2. sekme bunu okur).

Kullanım:
    python3 AgustosKripto/Test/jarvis_audit.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

_DIR = os.path.dirname(os.path.abspath(__file__))
_AGUSTOS = os.path.dirname(_DIR)
if _AGUSTOS not in sys.path:
    sys.path.insert(0, _AGUSTOS)

import skill_audit as sa  # noqa: E402

AUDIT_FILE = os.path.join(_DIR, "jarvis_audit.json")
TR = timezone(timedelta(hours=3))


def _round(v: float, n: int = 2) -> float:
    return round(float(v), n)


def _exit_rows(trades: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        buckets[t.get("close_reason") or "?"].append(t)
    out = []
    for name, rows in buckets.items():
        sp = sa.skill_split(rows)
        if not sp:
            continue
        out.append({
            "sebep": name,
            "n": sp["n"],
            "wr": round(sp["wr"], 1),
            "net": round(sp["net_pnl"], 2),
            "brut": round(sp["gross_pnl"], 2),
            "komisyon": round(sp["commission"], 2),
            "skill": round(sp["skill"], 4),
            "t": round(sp["t"], 2),
        })
    out.sort(key=lambda x: -x["n"])
    return out


def _book_skill_count(trades: list[dict]) -> dict:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        key = f"{t['_group']}·{t.get('algo') or t['_bookfile']}"
        buckets[key].append(t)
    both_pos = 0
    measurable = 0
    for rows in buckets.values():
        sp = sa.skill_split(rows)
        if not sp or sp["n"] < 25:
            continue
        measurable += 1
        if sp.get("both_positive"):
            both_pos += 1
    return {"olculebilir": measurable, "iki_yon_pozitif": both_pos}


def _live_ghosts() -> list[dict]:
    """crypto_futures_cr6 state/history desenkronu."""
    state_path = os.path.join(_AGUSTOS, "crypto_futures_cr6_state.json")
    hist_path = os.path.join(_AGUSTOS, "crypto_futures_cr6_history.json")
    if not os.path.exists(state_path) or not os.path.exists(hist_path):
        return []
    try:
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
        with open(hist_path, encoding="utf-8") as fh:
            hist = json.load(fh)
    except Exception:
        return []
    if not isinstance(hist, list):
        return []
    closed_ids = {str(h.get("order_id")) for h in hist if h.get("order_id")}
    ghosts = []
    for p in state.get("open_positions") or []:
        oid = str(p.get("order_id") or "")
        if oid and oid in closed_ids:
            ghosts.append({
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "entry": (p.get("entry_time_tr") or "")[:19],
                "peak": p.get("peak_upnl"),
                "stop_level": p.get("atr_stop_level"),
            })
    return ghosts


def _cr6_summary() -> dict | None:
    hist_path = os.path.join(_AGUSTOS, "crypto_futures_cr6_history.json")
    if not os.path.exists(hist_path):
        return None
    try:
        with open(hist_path, encoding="utf-8") as fh:
            rows = json.load(fh)
    except Exception:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    net = sum(float(r.get("pnl") or 0) for r in rows)
    gross = sum(float(r.get("pnl_gross") or 0) for r in rows)
    comm = sum(float(r.get("commission") or 0) for r in rows)
    return {"n": len(rows), "net": round(net, 2), "brut": round(gross, 2), "komisyon": round(comm, 2)}


def _rejim(trades: list[dict]) -> dict:
    """Çıkış rejimi geçişinin ileriye dönük etkisi.

    Rejim 15.08.2026'da değişti (`exit_policy.py`). Geçmiş işlemler eski
    rejimde ölçüldüğü için ikisi ayrı raporlanır — karıştırılırsa yeni
    rejimin etkisi eski verinin altında kaybolur.
    """
    try:
        import exit_policy as ep
    except Exception:
        return {}
    cfg = {}
    try:
        with open(ep.CONFIG_FILE, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception:
        pass
    switch = str(cfg.get("switched_at_tr") or "")

    def _blk(rows: list[dict]) -> dict:
        sp = sa.skill_split(rows)
        kom = sum(float(r.get("commission") or 0) for r in rows)
        return {
            "n": len(rows),
            "net": round(sum(float(r.get("pnl") or 0) for r in rows), 2),
            "brut": round(sum(float(r.get("pnl_gross") or 0) for r in rows), 2),
            "komisyon": round(kom, 2),
            "skill": round(sp["skill"], 4) if sp else 0.0,
            "t": round(sp["t"], 2) if sp else 0.0,
        }

    eski = [t for t in trades if not switch or str(t.get("entry_time_tr") or "") < switch]
    yeni = [t for t in trades if switch and str(t.get("entry_time_tr") or "") >= switch]
    return {
        "aktif": ep.describe("Test"),
        "gecis_tr": switch,
        "eski": _blk(eski) if eski else {},
        "yeni": _blk(yeni) if yeni else {},
        # exit_lab.py ölçümü — girişler sabit, gerçek 1m veriyle yeniden oynatıldı
        "olcum": {
            "kaynak": "Test/exit_lab.py · 50.892 işlem · 06–14 Ağu 2026",
            "eski_net": -20255, "eski_islem": 46305, "eski_kom": 19052, "eski_t": -2.74,
            "yeni_net": -1916, "yeni_islem": 9542, "yeni_kom": 4378, "yeni_t": 0.85,
        },
    }


def _bulgular(ov: dict, mfe: list[dict], exits: list[dict], kons: list[dict],
              book_ct: dict, rejim: dict | None = None) -> list[dict]:
    out: list[dict] = []
    gross = ov["gross_pnl"]
    comm = ov["commission"]
    net = ov["net_pnl"]

    if comm > 0 and abs(gross) < comm * 0.25:
        out.append({
            "tip": "kritik",
            "baslik": "Sistem piyasada değil, komisyonda kaybediyor",
            "metin": (
                f"Brüt sonuç ${gross:+,.2f} — pratikte sıfır. Komisyon ${comm:,.2f}. "
                f"Kenar maliyetin {comm / max(abs(gross), 0.01):.0f} katı küçük."
            ),
        })

    dead = next((m for m in mfe if m["band"].startswith("0-0.5") or m["band"].startswith("0-")), None)
    if dead and dead.get("share_pct", 0) > 70:
        out.append({
            "tip": "uyari",
            "baslik": f"İşlemlerin %{dead['share_pct']:.0f}'i doğru anda ölü",
            "metin": (
                f"{dead['n']:,} işlem 0,5 ATR bile lehe gitmiyor (toplam ${dead['total_net']:+,.0f}). "
                "Sorun çıkışlarda değil, giriş ayrım gücünde."
            ),
        })

    h1 = next((e for e in exits if e["sebep"] in ("1h_close", "hourly")), None)
    if h1 and h1["n"] > ov["trades"] * 0.5:
        out.append({
            "tip": "uyari",
            "baslik": "Zamanlı kapanış sessiz katil",
            "metin": (
                f"{h1['sebep']}: {h1['n']:,} işlem, brüt ${h1['brut']:+,.2f}, "
                f"net ${h1['net']:+,.2f}. Üçte ikiden fazlası süre dolduğu için kapanıyor."
            ),
        })

    if rejim and rejim.get("olcum"):
        o = rejim["olcum"]
        out.append({
            "tip": "iyi",
            "baslik": "Çıkış rejimi değişti — zararın %90'ı silindi",
            "metin": (
                f"Aynı girişler gerçek 1m veriyle yeniden oynatıldı ({o['kaynak']}). "
                f"Eski rejim (1h/4h zorunlu + 2×ATR stop): {o['eski_islem']:,} işlem, "
                f"net ${o['eski_net']:+,}, komisyon ${o['eski_kom']:,}. "
                f"Yeni rejim (zaman kapanışı yok · 24s tavan · 6×ATR stop): "
                f"{o['yeni_islem']:,} işlem, net ${o['yeni_net']:+,}, "
                f"komisyon ${o['yeni_kom']:,}. Aktif: {rejim.get('aktif', '')}"
            ),
        })
        out.append({
            "tip": "kritik",
            "baslik": "Yeni rejim de kâr etmiyor — kenar hâlâ komisyonun altında",
            "metin": (
                "En iyi çıkış rejiminin brüt kenarı %0,059; taker gidiş-dönüş maliyeti "
                "%0,100. Gün bazlı kümelenmiş t = +0,85, yani sıfırdan ayırt edilemez. "
                "Geçmiş başarıya göre defter seçmek walk-forward'da TERS çalıştı "
                "(seçilen %0,062 · filtresiz %0,084). Kalan açık çıkışla değil, "
                "giriş kalitesi veya maker maliyetiyle kapanır."
            ),
        })

    tam = next((k for k in kons if "95" in k.get("ad", "")), None)
    if tam and tam.get("skill", 0) < 0:
        out.append({
            "tip": "uyari",
            "baslik": "Çoğunluk oyu ters çalışıyor",
            "metin": (
                f"Tam uzlaşı (≥%95) SKILL %{tam['skill']:.4f} — istatistiksel olarak negatif. "
                "Kripto tarafında konsensüs filtresi zarar veriyor olabilir."
            ),
        })

    bp = book_ct.get("iki_yon_pozitif", 0)
    meas = book_ct.get("olculebilir", 0)
    if meas:
        out.append({
            "tip": "bilgi",
            "baslik": "Defter bazında beceri testi",
            "metin": (
                f"Her iki yönde de pozitif getiri üreten defter: {bp} / {meas}. "
                f"Saf şans eseri beklenen ~{meas * 0.25:.0f}."
            ),
        })

    maker_net = ov.get("maker_net_pnl")
    if maker_net is not None and net < 0 < maker_net + abs(net) * 0.5:
        out.append({
            "tip": "iyi",
            "baslik": "Maker geçişi en büyük tek kaldıraç",
            "metin": (
                f"Taker ile net ${net:+,.0f}; aynı evrende maker ile tahmini "
                f"${maker_net:+,.0f} (komisyon %0,04 gidiş-dönüş)."
            ),
        })

    return out


ACTIVE_GROUPS = {"Test": sa.GROUPS["Test"]}


def build_report() -> dict:
    trades = sa.load_trades(ACTIVE_GROUPS)
    ov = sa.overall(trades)
    mfe = sa.mfe_distribution(trades)
    exits = _exit_rows(trades)
    coins = sa.by_coin(trades, min_n=40)
    kons_raw = sa.consensus(trades)
    kons = [
        {
            "ad": k["name"],
            "nL": k["n_long"],
            "nS": k["n_short"],
            "skill": round(k["skill"], 4),
            "t": round(k["t"], 2),
            "mL": round(k["mean_long"], 4),
            "mS": round(k["mean_short"], 4),
        }
        for k in kons_raw
    ]
    book_ct = _book_skill_count(trades)
    ghosts = _live_ghosts()
    cr6 = _cr6_summary()
    rejim = _rejim(trades)

    # defter sayısı
    books = set()
    for g, ddir in ACTIVE_GROUPS.items():
        for p in glob.glob(os.path.join(ddir, "*_history.json")):
            books.add(f"{g}·{os.path.basename(p).replace('_history.json', '')}")

    drift = [
        {
            "coin": c["name"],
            "nL": c["n_long"],
            "nS": c["n_short"],
            "skill": round(c["skill"], 4),
            "drift": round(c["drift"], 4),
            "mL": round(c["mean_long"], 4),
            "mS": round(c["mean_short"], 4),
        }
        for c in sorted(coins, key=lambda x: -abs(x.get("drift", 0)))[:8]
    ]

    return {
        "olusturma": datetime.now(TR).isoformat(timespec="seconds"),
        "ozet": {
            "defter": len(books),
            "islem": ov["trades"],
            "gun": round(ov["days"], 1),
            "ilk": (ov["first_entry"] or "")[:19],
            "son": (ov["last_entry"] or "")[:19],
            "wr": round(ov["wr"], 1),
            "brut": round(ov["gross_pnl"], 2),
            "net": round(ov["net_pnl"], 2),
            "komisyon": round(ov["commission"], 2),
            "hacim": round(ov["notional"], 2),
            "fee_oran": round(ov["fee_rate_pct"], 4),
            "brut_kenar": round(ov["gross_edge_pct"], 4),
            "islem_basi": round(ov["net_pnl"] / max(ov["trades"], 1), 3),
            "maker_net": round(ov["maker_net_pnl"], 2),
        },
        "mfe": [
            {
                "band": m["band"].replace("-inf", "+").replace("0.0", "0").replace(".0", ""),
                "n": m["n"],
                "pay": round(m["share_pct"], 1),
                "ort": round(m["avg_net"], 2),
                "wr": round(m["wr"], 1),
                "net": round(m["total_net"], 2),
            }
            for m in mfe
        ],
        "kapanis": exits,
        "drift": drift,
        "konsensus": kons,
        "beceri": book_ct,
        "live": {"hayalet": ghosts, "cr6": cr6},
        "rejim": rejim,
        "bulgular": _bulgular(ov, mfe, exits, kons, book_ct, rejim),
    }


def save(rapor: dict) -> None:
    tmp = AUDIT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rapor, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, AUDIT_FILE)


def load_report() -> dict | None:
    try:
        with open(AUDIT_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def main() -> None:
    rapor = build_report()
    save(rapor)
    o = rapor["ozet"]
    print(
        f"[jarvis-audit] {rapor['olusturma']} · {o['defter']} defter · "
        f"{o['islem']} işlem · brüt ${o['brut']:+,.2f} · net ${o['net']:+,.2f}"
    )


if __name__ == "__main__":
    main()
