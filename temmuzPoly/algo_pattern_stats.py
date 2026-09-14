"""Poly Algo defterleri arası kalıp istatistikleri — saf, deterministik hesaplama.

Bu modül HİÇBİR yorum üretmez, sadece sayı hesaplar. Amaç: "A1 ve A6 aynı yönde işlem
açtığında kazanma oranı %X (N=Y)" gibi iddiaları güvenilir örneklem büyüklüğü ve
Wilson güven aralığıyla birlikte üretmek. Sayılar `pattern_stats.json`'a yazılır;
`poly_algo_analyst.py` ve `poly_algo_daily_report.py` bu dosyayı okuyup yorumlar —
kendileri yüzde uydurmaz.

Kullanım:
    python3 algo_pattern_stats.py            # hesapla, pattern_stats.json'a yaz, özet bas
"""
from __future__ import annotations

import itertools
import json
import math
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR_POLY = os.path.dirname(os.path.abspath(__file__))
_TZ_TR = ZoneInfo("Europe/Istanbul")
_STATS_FILE = os.path.join(_DIR_POLY, "pattern_stats.json")

# _ANALYST_KEYS ile aynı (web/poly_dashboard.py) — burada bağımsız kopya, Flask'ı
# import etmemek için.
BOOK_KEYS: list[str] = [
    "analiz1", "analiz2", "analiz6", "analiz6_v2", "analiz6_v3", "analiz15",
    "b1_01", "b1_02", "b1_mum",
] + [f"a2_{i:02d}" for i in range(1, 18)]

MIN_N_WATCH = 8       # bu eşiğin altı gürültü sayılır, rapora girmez
MIN_N_CONFIDENT = 20  # bu eşiği geçen kalıplar "güvenilir" etiketlenir
MIN_N_OVERLAP_RAW = 3  # ham JSON'a girmesi için minimum örtüşme (büyümeyi izlemek için)


_LABELS = {
    "analiz1": "A1", "analiz2": "A2(SOL)", "analiz6": "A6", "analiz6_v2": "A6V2",
    "analiz6_v3": "A6V3", "analiz15": "A15",
    "b1_01": "B1#01", "b1_02": "B1#02", "b1_mum": "B1#03 MUM",
}


def book_label(key: str) -> str:
    if key in _LABELS:
        return _LABELS[key]
    m = re.match(r"^a2_(\d+)$", key)
    if m:
        return f"A2#{int(m.group(1)):02d}"
    return key


def _trader_history_path(key: str) -> str:
    return os.path.join(_DIR_POLY, f"poly_trader_{key}_history.json")


def load_book_trades(key: str) -> list[dict]:
    """İlgili defterin history dosyasını okur, sonuçlanmış (win is not None) işlemleri döner."""
    path = _trader_history_path(key)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            hist = json.load(f)
    except Exception:
        return []
    out = []
    for t in hist:
        if not isinstance(t, dict) or t.get("win") is None:
            continue
        out.append(t)
    return out


def _hour_key(trade: dict) -> str | None:
    ts = trade.get("entry_time_tr") or trade.get("exit_time_tr")
    if not ts or not isinstance(ts, str) or len(ts) < 13:
        return None
    return ts[:13]  # "YYYY-MM-DDTHH"


def build_slot_index(all_trades: dict[str, list[dict]]) -> dict[tuple[str, str], dict[str, dict]]:
    """(symbol, saat) -> {book_key: trade} — hangi defterlerin aynı slotta işlem açtığını hizalar."""
    index: dict[tuple[str, str], dict[str, dict]] = {}
    for key, trades in all_trades.items():
        for t in trades:
            sym = t.get("symbol")
            hk = _hour_key(t)
            if not sym or not hk:
                continue
            slot = (sym, hk)
            index.setdefault(slot, {})[key] = t
    return index


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson skor aralığı — küçük örneklemde normal yaklaşımdan daha güvenilir."""
    if n == 0:
        return (0.0, 1.0)
    phat = wins / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, center - margin) * 100, 1), round(min(1.0, center + margin) * 100, 1))


def _tier(n: int) -> str:
    if n >= MIN_N_CONFIDENT:
        return "confident"
    if n >= MIN_N_WATCH:
        return "watch"
    return "noise"


def pairwise_agreement_stats(
    slot_index: dict[tuple[str, str], dict[str, dict]],
    book_keys: list[str],
) -> list[dict]:
    """Her defter çifti için: aynı yönde açtıklarında kazanma oranı, ters açtıklarında
    hangisi daha çok haklı çıkıyor."""
    pairs_data: dict[tuple[str, str], dict] = {}
    for slot_books in slot_index.values():
        present = [k for k in book_keys if k in slot_books]
        for a, b in itertools.combinations(present, 2):
            ta, tb = slot_books[a], slot_books[b]
            d = pairs_data.setdefault((a, b), {
                "n_overlap": 0, "n_agree": 0, "wins_agree": 0,
                "n_disagree": 0, "a_wins_disagree": 0, "b_wins_disagree": 0,
            })
            d["n_overlap"] += 1
            if ta.get("predicted_dir") == tb.get("predicted_dir"):
                d["n_agree"] += 1
                if ta.get("win"):
                    d["wins_agree"] += 1
            else:
                d["n_disagree"] += 1
                if ta.get("win"):
                    d["a_wins_disagree"] += 1
                if tb.get("win"):
                    d["b_wins_disagree"] += 1

    out = []
    for (a, b), d in pairs_data.items():
        if d["n_overlap"] < MIN_N_OVERLAP_RAW:
            continue
        n_agree = d["n_agree"]
        n_dis = d["n_disagree"]
        row = {
            "book_a": a,
            "book_b": b,
            "n_overlap": d["n_overlap"],
            "n_agree": n_agree,
            "agree_rate_pct": round(100 * n_agree / d["n_overlap"], 1) if d["n_overlap"] else None,
            "win_rate_when_agree_pct": round(100 * d["wins_agree"] / n_agree, 1) if n_agree else None,
            "win_rate_when_agree_ci": wilson_ci(d["wins_agree"], n_agree) if n_agree else None,
            "tier_agree": _tier(n_agree),
            "n_disagree": n_dis,
            "a_win_rate_when_disagree_pct": round(100 * d["a_wins_disagree"] / n_dis, 1) if n_dis else None,
            "a_win_rate_when_disagree_ci": wilson_ci(d["a_wins_disagree"], n_dis) if n_dis else None,
            "b_win_rate_when_disagree_pct": round(100 * d["b_wins_disagree"] / n_dis, 1) if n_dis else None,
            "b_win_rate_when_disagree_ci": wilson_ci(d["b_wins_disagree"], n_dis) if n_dis else None,
            "tier_disagree": _tier(n_dis),
        }
        out.append(row)
    out.sort(key=lambda r: r["n_agree"], reverse=True)
    return out


_VOTE_FIELDS = ("ind_rsi_vote", "ind_macd_vote", "ind_ema_vote")


def indicator_alignment_stats(key: str, trades: list[dict]) -> dict | None:
    """Tek defter içinde: 3 indikatör de kararla (predicted_dir) aynı yönü söylediğinde
    (oybirliği) vs söylemediğinde (bölünmüş) kazanma oranı farkı var mı."""
    unanimous_wins = unanimous_n = 0
    split_wins = split_n = 0
    for t in trades:
        votes = [t.get(f) for f in _VOTE_FIELDS]
        if any(v is None for v in votes):
            continue
        pred = t.get("predicted_dir")
        if pred is None:
            continue
        if all(v == pred for v in votes):
            unanimous_n += 1
            if t.get("win"):
                unanimous_wins += 1
        else:
            split_n += 1
            if t.get("win"):
                split_wins += 1
    if unanimous_n < MIN_N_OVERLAP_RAW and split_n < MIN_N_OVERLAP_RAW:
        return None
    return {
        "book": key,
        "n_unanimous": unanimous_n,
        "win_rate_unanimous_pct": round(100 * unanimous_wins / unanimous_n, 1) if unanimous_n else None,
        "win_rate_unanimous_ci": wilson_ci(unanimous_wins, unanimous_n) if unanimous_n else None,
        "tier_unanimous": _tier(unanimous_n),
        "n_split": split_n,
        "win_rate_split_pct": round(100 * split_wins / split_n, 1) if split_n else None,
        "win_rate_split_ci": wilson_ci(split_wins, split_n) if split_n else None,
        "tier_split": _tier(split_n),
    }


def compute_pattern_stats(book_keys: list[str] | None = None) -> dict:
    keys = book_keys or BOOK_KEYS
    all_trades = {k: load_book_trades(k) for k in keys}
    all_trades = {k: v for k, v in all_trades.items() if v}

    slot_index = build_slot_index(all_trades)
    pairwise = pairwise_agreement_stats(slot_index, list(all_trades.keys()))
    indicator = [
        row for k, trades in all_trades.items()
        if (row := indicator_alignment_stats(k, trades)) is not None
    ]

    return {
        "generated_at_tr": datetime.now(_TZ_TR).isoformat(),
        "min_n_watch": MIN_N_WATCH,
        "min_n_confident": MIN_N_CONFIDENT,
        "book_trade_counts": {k: len(v) for k, v in all_trades.items()},
        "pairwise": pairwise,
        "indicator": indicator,
    }


def save_pattern_stats(stats: dict, path: str = _STATS_FILE) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def load_pattern_stats(path: str = _STATS_FILE) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def daily_book_summary(book_keys: list[str] | None = None, today_str: str | None = None) -> list[dict]:
    """Her defter için bugünkü ve tüm-zamanlar özet — günlük rapor için."""
    keys = book_keys or BOOK_KEYS
    today_str = today_str or datetime.now(_TZ_TR).strftime("%Y-%m-%d")
    out = []
    for key in keys:
        trades = load_book_trades(key)
        if not trades:
            continue
        today = [t for t in trades if (t.get("entry_time_tr") or "")[:10] == today_str]
        n_today = len(today)
        wins_today = sum(1 for t in today if t.get("win"))
        pnl_today = round(sum(float(t.get("pnl") or 0) for t in today), 2)
        n_total = len(trades)
        wins_total = sum(1 for t in trades if t.get("win"))
        pnl_total = round(sum(float(t.get("pnl") or 0) for t in trades), 2)
        out.append({
            "book": key,
            "label": book_label(key),
            "n_today": n_today,
            "wr_today_pct": round(100 * wins_today / n_today, 1) if n_today else None,
            "pnl_today": pnl_today,
            "n_total": n_total,
            "wr_total_pct": round(100 * wins_total / n_total, 1) if n_total else None,
            "pnl_total": pnl_total,
        })
    out.sort(key=lambda r: r["n_today"], reverse=True)
    return out


_TIER_RANK = {"noise": 0, "watch": 1, "confident": 2}


def diff_newly_significant(before: dict | None, after: dict, min_tier: str = "watch") -> dict:
    """`before` (bir önceki kaydedilmiş pattern_stats) ile `after` (yeni hesap) arasında
    eşik atlayan (ör. watch -> confident, ya da yoktan watch'a) kalıpları bulur."""
    thresh = _TIER_RANK[min_tier]
    before_pw = {(r["book_a"], r["book_b"]): r for r in (before or {}).get("pairwise", [])}
    before_ind = {r["book"]: r for r in (before or {}).get("indicator", [])}

    new_pw = []
    for r in after.get("pairwise", []):
        k = (r["book_a"], r["book_b"])
        old = before_pw.get(k)
        old_rank = _TIER_RANK.get(old["tier_agree"], -1) if old else -1
        new_rank = _TIER_RANK.get(r["tier_agree"], -1)
        if new_rank >= thresh and new_rank > old_rank:
            new_pw.append(r)

    new_ind = []
    for r in after.get("indicator", []):
        old = before_ind.get(r["book"])
        old_rank = _TIER_RANK.get(old["tier_unanimous"], -1) if old else -1
        new_rank = _TIER_RANK.get(r["tier_unanimous"], -1)
        if new_rank >= thresh and new_rank > old_rank:
            new_ind.append(r)

    return {"pairwise": new_pw, "indicator": new_ind}


def significant_patterns(stats: dict, min_tier: str = "watch") -> dict:
    """Sadece min_tier ('watch' veya 'confident') ve üstü kalıpları döner — LLM'e/rapora
    gönderilecek filtrelenmiş görünüm."""
    tiers_ok = {"watch": {"watch", "confident"}, "confident": {"confident"}}[min_tier]
    pairwise = [
        r for r in stats.get("pairwise", [])
        if r.get("tier_agree") in tiers_ok or r.get("tier_disagree") in tiers_ok
    ]
    indicator = [
        r for r in stats.get("indicator", [])
        if r.get("tier_unanimous") in tiers_ok or r.get("tier_split") in tiers_ok
    ]
    return {
        "generated_at_tr": stats.get("generated_at_tr"),
        "min_n_watch": stats.get("min_n_watch"),
        "min_n_confident": stats.get("min_n_confident"),
        "pairwise": pairwise,
        "indicator": indicator,
    }


def _print_summary(stats: dict) -> None:
    print(f"[pattern_stats] {stats['generated_at_tr']}")
    print(f"[pattern_stats] Defter trade sayıları: {stats['book_trade_counts']}")
    sig = significant_patterns(stats, "watch")
    print(f"[pattern_stats] {len(sig['pairwise'])} çift ilişki, {len(sig['indicator'])} indikatör kalıbı eşik üstü (N>={MIN_N_WATCH})")
    for r in sig["pairwise"][:15]:
        print(
            f"  {r['book_a']} + {r['book_b']}: anlaştıklarında N={r['n_agree']} "
            f"WR={r['win_rate_when_agree_pct']}% CI={r['win_rate_when_agree_ci']} [{r['tier_agree']}]"
        )
    for r in sig["indicator"][:15]:
        print(
            f"  {r['book']} indikatör oybirliği: N={r['n_unanimous']} WR={r['win_rate_unanimous_pct']}% "
            f"[{r['tier_unanimous']}] | bölünmüş: N={r['n_split']} WR={r['win_rate_split_pct']}% "
            f"[{r['tier_split']}]"
        )


def main() -> int:
    stats = compute_pattern_stats()
    save_pattern_stats(stats)
    _print_summary(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
