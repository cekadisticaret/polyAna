"""B1#04 — algoritma-islemler defterlerinin kümelenmiş, edge-ağırlıklı konsensüsü.

Tasarım üç ölçüme dayanır (2026-08-11 analizi):

1. Defterlerin çoğu birbirinin kopyası — A2#05=#06=#07 (N=44, %100 uyum),
   A2#16=#17, A2#03=#04, A2#10=#11, A6/A6V2/A6V3 hep aynı yönü söylüyor.
   Düz çoğunluk oyu tek sinyali onlarca kez sayar. Bu yüzden >=%95 uyumlu
   defterler tek kümeye indirilir ve küme başına **tek oy** verilir.

2. Polymarket'te başabaş kazanma oranı = ödenen fiyat (~0.49). Ham WR yanıltıcı;
   oy ağırlığı = **büzülmüş** kazanma oranı - ortalama başabaş fiyat. Büzülme
   (shrinkage) küçük örneklemi başabaşa çeker, böylece 20 işlemlik şanslı bir
   defter 90 işlemlik defter kadar söz sahibi olmaz. Edge'i negatif çıkan defter
   0 ağırlık alır — **ters çevrilmez**: A2#13/#14 ilk yarıda %28 kazanıp ikinci
   yarıda %61.7'ye döndü, ters almak zarar ettirirdi.

   Not: Wilson %95 alt sınırı denendi ve fazla katı çıktı (22 defterden yalnızca
   1'i ağırlık alıyordu, o da eşik altında) — topluluk oyunu sustururdu.

3. Net ağırlık eşiği geçmezse işlem YOK. Varsayılan eşik şu an 0.0, yani bu kapı
   pratikte kapalı: ağırlıklı oylama bir yön gösterdiği her slotta işlem açılır.
   Eşiği geri açmak için `B1_04_MIN_EDGE` (örn. 0.03).

DENENİP ELENEN: "kazanan yöne en az N bağımsız küme oy vermeli" şartı. Uzlaşma
genişliği ile sonuç arasında ilişki yok — kümeler arası uzlaşma %100/%80-99/
%65-79/%50-64 kutularında WR sırasıyla %66.7/%66.7/%32.5/%62.5 (N=15/15/40/40,
güven aralıkları tamamen örtüşüyor, monoton değil). Şart eklendiğinde
walk-forward edge +4.9 → +0.7 puana düştü. Geniş uzlaşma bu defterlerde bilgi
taşımıyor; tekrar eklenmemeli.

Oy veren defterler yalnızca **birincil motorlar**. Hariç tutulanlar:
  - b1_01 / b1_02: başka defterlerin sinyalini aynalayan türev defterler
  - analiz2: analiz1 ile aynı `predict()` tabanını kullanır (çift sayma)
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
from collections import defaultdict

from algo_signals_v2 import ALGO_V2_META

_DIR = os.path.dirname(os.path.abspath(__file__))
_MAPPING_FILE = os.path.join(_DIR, "b1_04_mapping.json")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# Oy ağırlığı için defter başına bakılacak son kapanmış işlem sayısı.
# Edge zamanla bozulduğu için (A2#05: %72.7 → %48) pencere sınırlı tutulur.
_EDGE_WINDOW = 150
# Ağırlık verilebilmesi için asgari kapanmış işlem
_MIN_TRADES = 8
# Büzülme gücü: defter, gözlenen edge'inin yarısını hak etmek için ~bu kadar
# işleme ihtiyaç duyar. Sonuçlara göre değil, düzenlileştirme amaçlı seçildi.
_SHRINK_K = 50.0
# Bu uyum oranının üstündeki defter çiftleri aynı kümeye konur
_AGREE_CLUSTER = 0.95
_CLUSTER_MIN_OVERLAP = 8
# Net ağırlık eşiği (olasılık puanı). 0.0 = eşik kapalı: oylama bir yön
# gösterdiği her slotta işlem açılır (net tam 0 ise yön belirsiz sayılır, giriş
# yok). Kullanıcı kararıyla 0.03'ten 0.0'a çekildi — 08-10/08-11 backfill'inde
# 0.03 A2#05'in kazandığı 24 slotu atlayıp $314'te kalıyordu, 0.0 ise $421.
# Bu doğrulanmış bir optimum DEĞİL: eşik taraması monoton değil (0.02 → $274,
# 0.03 → $314, 0.05 → $333), yani aradaki fark gürültü seviyesinde.
_MIN_NET_EDGE = float(os.getenv("B1_04_MIN_EDGE", "0.0"))

_A2_NUMS = [num for num, *_ in ALGO_V2_META]
_A2_NAMES = {num: name for num, name, *_ in ALGO_V2_META}

# Türev/çift sayan defterler oy vermez
EXCLUDED_KEYS = ("b1_01", "b1_02", "b1_04", "analiz2")


def voter_keys() -> list[str]:
    """B1#04'e oy veren birincil motor defterleri."""
    keys = ["analiz1", "analiz6", "analiz6_v2", "analiz6_v3", "analiz15", "b1_mum"]
    keys.extend(f"a2_{n:02d}" for n in sorted(_A2_NUMS))
    return [k for k in keys if k not in EXCLUDED_KEYS]


def book_label(key: str) -> str:
    if m := re.match(r"^a2_(\d+)$", key):
        return f"A2#{int(m.group(1)):02d}"
    return {
        "analiz1": "A1", "analiz2": "A2", "analiz6": "A6",
        "analiz6_v2": "A6V2", "analiz6_v3": "A6V3", "analiz15": "A15",
        "b1_mum": "B1#03", "b1_01": "B1#01", "b1_02": "B1#02",
    }.get(key, key)


def _history_path(key: str) -> str:
    return os.path.join(_DIR, f"poly_trader_{key}_history.json")


def _load_history(key: str) -> list:
    path = _history_path(key)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _shrunk_rate(wins: int, n: int, prior: float, k: float = _SHRINK_K) -> float:
    """Başabaşa doğru büzülmüş kazanma oranı (empirical-Bayes)."""
    if n <= 0:
        return prior
    return (wins + k * prior) / (n + k)


def compute_book_edges(window: int = _EDGE_WINDOW) -> dict[str, dict]:
    """{key: {edge, wr, breakeven, n, label}} — edge = büzülmüş WR - başabaş."""
    out: dict[str, dict] = {}
    for key in voter_keys():
        rows = [
            t for t in _load_history(key)
            if t.get("win") is not None and t.get("pm_entry_price")
        ]
        if len(rows) < _MIN_TRADES:
            continue
        rows.sort(key=lambda t: t.get("entry_time_tr") or "")
        rows = rows[-window:]
        n = len(rows)
        wins = sum(1 for t in rows if t.get("win"))
        breakeven = sum(float(t["pm_entry_price"]) for t in rows) / n
        edge = _shrunk_rate(wins, n, breakeven) - breakeven
        out[key] = {
            "label": book_label(key),
            "n": n,
            "wr": round(100 * wins / n, 1),
            "breakeven": round(100 * breakeven, 1),
            "shrunk_wr": round(100 * _shrunk_rate(wins, n, breakeven), 1),
            "edge": round(edge, 4),
            "weight": round(max(0.0, edge), 4),
        }
    return out


def compute_clusters() -> dict[str, str]:
    """{key: kume_koku} — >=%95 yön uyumlu defterler aynı köke bağlanır."""
    keys = voter_keys()
    # (tarih+saat, sembol) slotunda her defterin yönü
    slots: dict[tuple, dict[str, str]] = defaultdict(dict)
    for key in keys:
        for t in _load_history(key):
            if t.get("win") is None:
                continue
            ts = t.get("entry_time_tr") or ""
            direction = t.get("predicted_dir")
            if not ts or direction not in ("UP", "DOWN"):
                continue
            slots[(ts[:13], t.get("symbol"))][key] = direction

    agree: dict[tuple, list] = defaultdict(lambda: [0, 0])
    for books in slots.values():
        present = sorted(books)
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                a, b = present[i], present[j]
                rec = agree[(a, b)]
                rec[0] += 1
                if books[a] == books[b]:
                    rec[1] += 1

    parent = {k: k for k in keys}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), (overlap, same) in agree.items():
        if overlap < _CLUSTER_MIN_OVERLAP:
            continue
        if same / overlap < _AGREE_CLUSTER:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    return {k: find(k) for k in keys}


def save_mapping(edges: dict, clusters: dict) -> None:
    groups: dict[str, list[str]] = defaultdict(list)
    for key, root in clusters.items():
        groups[root].append(book_label(key))
    try:
        with open(_MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "min_net_edge": _MIN_NET_EDGE,
                "edge_window": _EDGE_WINDOW,
                "voters": len(voter_keys()),
                "clusters": {r: sorted(v) for r, v in groups.items() if len(v) > 1},
                "edges": edges,
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[B1#04] mapping yazılamadı: {e}")


async def _signal_from_book(key: str, symbol: str) -> tuple[str | None, float | None, str]:
    """Defterin şu anki canlı yönü. Mevcut modüller değiştirilmeden kullanılır."""
    try:
        if key == "b1_mum":
            from b1_mum_signal import resolve_live_signal as mum_resolve
            return await mum_resolve(symbol)
        if key == "analiz1":
            from poly_predictor_analysis import predict
            pred = await predict(symbol, kill_zone=False)
            if pred is None:
                return None, None, "A1 predictor"
            price = getattr(pred, "current_price", None) or getattr(pred, "entry_price", None)
            return getattr(pred, "predicted_dir", None), price, "A1 predictor"
        # analiz6 / v2 / v3 / analiz15 / a2_xx
        from b1_01_signal import resolve_from_book
        return await resolve_from_book(key, symbol)
    except Exception as e:
        print(f"[B1#04] {book_label(key)} {symbol} sinyal hatası: {e}")
        return None, None, book_label(key)


async def collect_votes(symbol: str) -> list[dict]:
    """Tüm oy veren defterlerin bu sembol için yönü."""
    keys = voter_keys()
    results = await asyncio.gather(
        *(_signal_from_book(k, symbol) for k in keys),
        return_exceptions=True,
    )
    votes = []
    for key, res in zip(keys, results):
        if isinstance(res, Exception) or not isinstance(res, tuple):
            continue
        direction, price, name = res
        if direction not in ("UP", "DOWN"):
            continue
        votes.append({"key": key, "label": book_label(key),
                      "dir": direction, "price": price, "algo": name})
    return votes


def score_votes(votes: list[dict], edges: dict, clusters: dict) -> dict:
    """Küme başına tek oy, ağırlık = kanıtlanmış edge. Net = UP - DOWN."""
    # (küme, yön) -> en güçlü üye ağırlığı
    cluster_vote: dict[tuple, float] = {}
    cluster_src: dict[tuple, str] = {}
    used, skipped = [], []

    for v in votes:
        info = edges.get(v["key"])
        weight = float(info["weight"]) if info else 0.0
        if weight <= 0:
            skipped.append(v["label"])
            continue
        root = clusters.get(v["key"], v["key"])
        ckey = (root, v["dir"])
        if weight > cluster_vote.get(ckey, 0.0):
            cluster_vote[ckey] = weight
            cluster_src[ckey] = v["label"]
        used.append(v["label"])

    up = sum(w for (_r, d), w in cluster_vote.items() if d == "UP")
    down = sum(w for (_r, d), w in cluster_vote.items() if d == "DOWN")
    net = up - down
    direction = "UP" if net > 0 else "DOWN" if net < 0 else None
    return {
        "up": round(up, 4), "down": round(down, 4), "net": round(net, 4),
        "direction": direction,
        "passes": abs(net) >= _MIN_NET_EDGE and direction is not None,
        "clusters_voted": len(cluster_vote),
        "used": used, "skipped": skipped,
        "leaders": sorted(
            ({"label": cluster_src[k], "dir": k[1], "w": round(w, 4)}
             for k, w in cluster_vote.items()),
            key=lambda x: -x["w"],
        )[:4],
    }


def engine_label(_symbol: str = "") -> str:
    return "Edge-ağırlıklı küme konsensüsü"


async def resolve_live_signal(symbol: str) -> tuple[str | None, float | None, str]:
    """(UP|DOWN|None, fiyat, açıklama) — B1#04 karar çıktısı."""
    edges = compute_book_edges()
    clusters = compute_clusters()
    save_mapping(edges, clusters)

    votes = await collect_votes(symbol)
    if not votes:
        return None, None, "oy yok"

    score = score_votes(votes, edges, clusters)
    price = next((v["price"] for v in votes if v.get("price")), None)

    top = " ".join(
        f"{x['label']}{'↑' if x['dir'] == 'UP' else '↓'}{x['w']:.2f}"
        for x in score["leaders"]
    )
    detail = (
        f"net {score['net']:+.3f} (↑{score['up']:.2f}/↓{score['down']:.2f}) · "
        f"{score['clusters_voted']} küme/{len(votes)} oy · {top}"
    )
    if not score["passes"]:
        print(f"[B1#04] {symbol} — eşik altı: {detail} (min {_MIN_NET_EDGE})")
        return None, price, detail
    return score["direction"], price, detail
