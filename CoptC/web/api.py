#!/usr/bin/env python3
"""Dashboard veri katmanı — defter state/history'sini ekranın beklediği şekle çevirir.

Sunum tarafı (dashboard.py) buradan gelen sözlükleri olduğu gibi basar; PM
ağına çıkan tek yer `pm_snapshot()` ve `live_signals()`.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_POLY = os.path.join(_DIR, "..", "poly")
sys.path.insert(0, _POLY)

# CoptC/.env — trader'lar kendi başlarına yüklüyor, dashboard süreci de görsün
_ENV = os.path.join(_DIR, "..", ".env")
if os.path.exists(_ENV):
    with open(_ENV, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

_TZ_TR = ZoneInfo("Europe/Istanbul")

BOOKS = {
    "b1_05": {
        "badge": "B1#05",
        "title": "Coin Başına En İyi Motor",
        "subtitle": "24 defterlik havuz · BTC · ETH · SOL · Saatlik",
        "sanal": "b1_05",
        "live": "b1_05_live",
        "group": "b1_05_live",
        "amount_key": "b1_05",
        "amount_def": (4.0, 5.0, 6.0),
        "metric": "engine",
        "timeline": [(":02", "Live kapat"), (":05", "Sinyal + sanal"), (":06", "Live PM aç")],
    },
    "b1_mum": {
        "badge": "MUM",
        "title": "Sonnet Mum Confluence",
        "subtitle": "Mum formasyonu · ±15 eşik · BTC · ETH · SOL · Saatlik",
        "sanal": "b1_mum",
        "live": "b1_mum_live",
        "group": "b1_mum_live",
        "amount_key": "b1_mum",
        "amount_def": (6.0, 8.0, 10.0),
        "metric": "score",
        "timeline": [(":02", "Live kapat"), (":05", "Sinyal + sanal"), (":06", "Live PM aç")],
    },
    "analiz1": {
        "badge": "A1",
        "title": "1. Analiz · PolyPred",
        "subtitle": "Akış + türev motoru · BTC · SOL · Saatlik",
        "sanal": "analiz1",
        "live": "analiz5",
        "group": "analiz5",
        "amount_key": "a1",
        "amount_def": (10.0, 12.0, 14.0),
        "metric": "conf",
        # Live aynalamıyor, kendi sinyalini çözüyor — :06:30'u beklemez
        "timeline": [(":02", "Live kapat"), (":05", "Sinyal + sanal + Live PM")],
    },
}

_SETTINGS = os.path.join(_POLY, "analiz5_settings.json")


# ── dosya yardımcıları ───────────────────────────────────────────
def _path(key: str, kind: str) -> str:
    return os.path.join(_POLY, f"poly_trader_{key}_{kind}.json")


def _load(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def state(key: str) -> dict:
    return _load(_path(key, "state"), {"balance": 0.0, "open_positions": [], "total_pnl": 0.0})


def history(key: str) -> list:
    h = _load(_path(key, "history"), [])
    return h if isinstance(h, list) else []


# ── ayarlar / live anahtarı ──────────────────────────────────────
def amounts(book: str) -> dict:
    cfg = BOOKS[book]
    s = _load(_SETTINGS, {})
    k = cfg["amount_key"]
    lo, mid, hi = cfg.get("amount_def", (4.0, 5.0, 6.0))
    return {
        "low": float(s.get(f"{k}_amount_low", lo)),
        "mid": float(s.get(f"{k}_amount_mid", mid)),
        "high": float(s.get(f"{k}_amount_high", hi)),
    }


def save_amounts(book: str, low: float, mid: float, high: float) -> dict:
    k = BOOKS[book]["amount_key"]
    s = _load(_SETTINGS, {})
    s[f"{k}_amount_low"], s[f"{k}_amount_mid"], s[f"{k}_amount_high"] = low, mid, high
    tmp = _SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _SETTINGS)
    return amounts(book)


def live_open(book: str) -> bool:
    from pm_balance_guard import is_group_paused
    return not is_group_paused(BOOKS[book]["group"])


def set_live(book: str, open_: bool) -> bool:
    """pm_system_control.json — tek otorite burası, .env değil."""
    p = os.path.join(_POLY, "pm_system_control.json")
    c = _load(p, {})
    c[f"{BOOKS[book]['group']}_paused"] = not open_
    c["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    c["updated_by"] = "coptc-dashboard"
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)
    return live_open(book)


# ── istatistik ───────────────────────────────────────────────────
def _wr(hist: list) -> tuple[int, int, float | None]:
    graded = [t for t in hist if t.get("win") is not None]
    w = sum(1 for t in graded if t.get("win"))
    return w, len(graded), (round(w / len(graded) * 100, 1) if graded else None)


def hour_grid(hist: list) -> list[dict]:
    buckets: dict[int, list] = {h: [] for h in range(24)}
    for t in hist:
        h = t.get("entry_hour_tr")
        if isinstance(h, int) and 0 <= h < 24 and t.get("win") is not None:
            buckets[h].append(bool(t["win"]))
    out = []
    for h in range(24):
        b = buckets[h]
        out.append({
            "h": h, "n": len(b),
            "wr": round(sum(b) / len(b) * 100) if b else None,
        })
    return out


def recent(hist: list, n: int = 25) -> list[dict]:
    rows = []
    for t in reversed(hist[-400:]):
        if t.get("win") is None:
            continue
        ts = str(t.get("exit_time_tr") or t.get("entry_time_tr") or "")
        rows.append({
            "symbol": (t.get("symbol") or "").replace("USDT", ""),
            "pred": t.get("predicted_dir"),
            "actual": t.get("actual_dir"),
            "win": bool(t.get("win")),
            "pnl": round(float(t.get("pnl") or 0), 2),
            "time": ts[5:16].replace("T", " "),
        })
        if len(rows) >= n:
            break
    return rows


# ── PM tarafı ────────────────────────────────────────────────────
_QUOTE_CACHE: dict[str, tuple[float, float]] = {}   # slug -> (ts, up_price)
_QUOTE_TTL = 20.0


def _token_price(slug: str, direction: str) -> float | None:
    """Gamma'dan slot kotasyonu; UP tarafının fiyatı, DOWN = 1 − UP."""
    import time
    import urllib.request

    if not slug:
        return None
    hit = _QUOTE_CACHE.get(slug)
    now = time.time()
    if hit and now - hit[0] < _QUOTE_TTL:
        up = hit[1]
    else:
        try:
            req = urllib.request.Request(
                f"https://gamma-api.polymarket.com/markets?slug={slug}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            if not data:
                return None
            m = data[0] if isinstance(data, list) else data
            prices = m.get("outcomePrices")
            if isinstance(prices, str):
                prices = json.loads(prices)
            if not prices:
                return None
            up = float(prices[0])
            _QUOTE_CACHE[slug] = (now, up)
        except Exception:
            return None
    return up if (direction or "UP").upper() == "UP" else round(1.0 - up, 4)


def _estimate(pos: dict) -> tuple[float | None, float | None]:
    """(anlık kapama değeri, anlık kâr/zarar) — kotasyon yoksa (None, None)."""
    price = _token_price(
        pos.get("pm_slug") or "",
        pos.get("pm_token_dir") or pos.get("predicted_dir") or "UP",
    )
    if price is None:
        return None, None
    size = float(pos.get("pm_size") or 0)
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    val = round(size * price, 2)
    return val, round(val - spent, 2)


def pm_snapshot(book: str) -> dict:
    """Nakit + açık pozisyonların anlık durumu. Cüzdan yoksa nakit None."""
    cfg = BOOKS[book]
    live_state = state(cfg["live"])
    opens = [p for p in live_state.get("open_positions") or [] if p.get("pm_token_id")]

    cash = None
    if os.getenv("POLY_PRIVATE_KEY"):   # cüzdan yoksa boşuna 3 kez denemesin
        try:
            from pm_trader_helpers import pm_get_balance
            b = pm_get_balance()
            cash = round(float(b), 2) if b is not None and float(b) >= 0 else None
        except Exception:
            pass

    rows, risk, to_win, upnl, close_tot = [], 0.0, 0.0, 0.0, 0.0
    for p in opens:
        spent = float(p.get("pm_spent") or p.get("amount") or 0)
        size = float(p.get("pm_size") or 0)
        cval, cpnl = _estimate(p)
        risk += spent
        to_win += size
        if cval is not None:
            close_tot += cval
            upnl += cpnl or 0.0
        rows.append({
            "symbol": (p.get("symbol") or "").replace("USDT", ""),
            "dir": p.get("predicted_dir") or p.get("pm_token_dir"),
            "entry": p.get("entry_price"),
            "spent": round(spent, 2),
            "to_win": round(size, 2),
            "close_val": cval,
            "close_pnl": cpnl,
            "slot": str(p.get("entry_time_tr") or "")[11:16],
            "title": p.get("pm_title") or p.get("pm_slug") or "",
        })

    hist = history(cfg["live"])
    w, n, wr = _wr(hist)
    pnl = round(sum(float(t.get("pnl") or 0) for t in hist), 2)
    return {
        "cash": cash,
        "redeem_pending": round(close_tot, 2) if opens else 0.0,
        "live_pnl": pnl,
        "live_w": w, "live_l": n - w, "live_wr": wr, "live_trades": n,
        "equity": round((cash or 0) + close_tot, 2) if cash is not None else None,
        "risk": {
            "total": round(risk, 2), "to_win": round(to_win, 2),
            "open": len(rows), "upnl": round(upnl, 2),
            "close_total": round(close_tot, 2),
        },
        "positions": rows,
    }


def live_signals(book: str) -> list[dict]:
    """Motorların şu anki yönü — sayfa açılışında ve 'Sinyal çek'te çağrılır."""
    cfg = BOOKS[book]

    async def go() -> list[dict]:
        if book == "analiz1":
            from poly_predictor_analysis import predict_status, _fetch_klines
            import poly_trader_analiz1 as a1
            out = []
            for sym in a1.SYMBOLS:
                st = await predict_status(sym, kill_zone=False)
                kl = await _fetch_klines(sym, "1h", 1)
                conf = st.get("conf_a")
                out.append({
                    "name": sym.replace("USDT", ""),
                    "price": kl[-1]["close"] if kl else None,
                    "dir": st.get("predicted_dir"),
                    "metric_label": "PREDICTOR GÜVENİ",
                    "metric_value": f"%{conf * 100:.1f}" if conf else "—",
                    # 0.5 = kararsız; kartın göstergesi 0.5→50 ile ortada dursun
                    "gauge": max(0.0, min(1.0, float(conf))) if conf else 0.5,
                    "foot": st.get("reason") or ("gate altı" if not st.get("predicted_dir") else ""),
                })
            return out

        if book == "b1_mum":
            import b1_mum_signal as eng
            out = []
            for sym in eng.SYMBOLS:
                sig, price, name = await eng.resolve_live_signal(sym)
                score = _parse_score(name)
                out.append({
                    "name": sym.replace("USDT", ""), "price": price, "dir": sig,
                    "metric_label": "MUM SKORU (±15 EŞİK)",
                    "metric_value": f"{score:+.0f}" if score is not None else "—",
                    "gauge": max(0.0, min(1.0, (score + 50) / 100)) if score is not None else 0.5,
                    "foot": name[:60],
                })
            return out

        import b1_05_signal as eng
        mapping = eng.load_mapping(refresh=True)
        out = []
        for sym in eng.SYMBOLS:
            short = sym.replace("USDT", "")
            row = mapping.get(short) or {}
            sig, price, name = await eng.resolve_live_signal(sym)
            out.append({
                "name": short, "price": price, "dir": sig,
                "metric_label": "SEÇİLİ MOTOR",
                "metric_value": row.get("label") or "—",
                "gauge": (row.get("wr") or 50) / 100.0,
                "foot": (f"WR %{row['wr']} · {row['w']}/{row['t']}" if row else "yeterli geçmiş yok"),
            })
        return out

    try:
        return asyncio.run(go())
    except Exception as e:
        return [{"name": s, "price": None, "dir": None, "metric_label": "HATA",
                 "metric_value": "—", "gauge": 0.5, "foot": str(e)[:60]}
                for s in (("BTC", "SOL") if book == "analiz1" else ("BTC", "ETH", "SOL"))]


def _parse_score(text: str) -> float | None:
    """'skor +41 · engulfing' / 'nötr -4 (eşik ±15)' → sayı."""
    import re
    m = re.search(r"([+-]?\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else None


# ── Polymarket'ten para çekme ────────────────────────────────────
_WITHDRAW_LOG = os.path.join(_POLY, "withdraw_log.jsonl")
_MAX_FAILS = 5
_LOCK_SEC = 900.0
_fails = {"n": 0, "until": 0.0}


def _audit(event: str, **fields) -> None:
    """Her çekim denemesi diske yazılır — tutar/adres evet, kod asla."""
    rec = {"ts": datetime.now(_TZ_TR).isoformat(), "event": event, **fields}
    try:
        with open(_WITHDRAW_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _valid_address(a: str) -> bool:
    import re
    return bool(re.fullmatch(r"0x[0-9a-fA-F]{40}", (a or "").strip()))


def withdraw_info() -> dict:
    """Cüzdan durumu — panelde çekim kartının üst satırı."""
    import time

    out = {
        "code_set": bool(os.getenv("COPTC_WITHDRAW_CODE")),
        "locked_for": max(0, int(_fails["until"] - time.time())),
        "funder": "", "eoa": "", "proxy_match": False,
        "balance": None, "builder_ready": False, "error": "",
    }
    try:
        import pm_transfer
        info = pm_transfer.wallet_info()
        bal = info.get("balance_usd")
        out.update({
            "funder": info.get("funder") or "",
            "eoa": info.get("eoa") or "",
            "proxy_match": bool(info.get("proxy_match")),
            "balance": round(float(bal), 2) if bal is not None and float(bal) >= 0 else None,
            "builder_ready": bool(info.get("builder_ready")),
        })
    except Exception as e:
        out["error"] = str(e)[:160]
    return out


def withdraw_send(to: str, amount: float, code: str, token: str = "PUSD") -> tuple[dict, int]:
    """Proxy cüzdandan relayer ile gerçek gönderim. (yanıt, http_kodu) döner."""
    import time

    expected = os.getenv("COPTC_WITHDRAW_CODE", "")
    if not expected:
        return {"error": "Çekim kodu tanımsız — .env dosyasına COPTC_WITHDRAW_CODE ekle."}, 400

    now = time.time()
    if now < _fails["until"]:
        return {"error": f"Çok fazla hatalı kod. {int(_fails['until'] - now)} sn sonra tekrar dene."}, 429

    if not secrets.compare_digest(code or "", expected):
        _fails["n"] += 1
        if _fails["n"] >= _MAX_FAILS:
            _fails["until"] = now + _LOCK_SEC
            _fails["n"] = 0
            _audit("kod_kilidi", to=to, amount=amount)
            return {"error": f"Çok fazla hatalı kod — {int(_LOCK_SEC / 60)} dk kilitlendi."}, 429
        _audit("kod_hatali", to=to, amount=amount, kalan=_MAX_FAILS - _fails["n"])
        return {"error": f"Kod hatalı. Kalan deneme: {_MAX_FAILS - _fails['n']}"}, 403
    _fails["n"] = 0

    to = (to or "").strip()
    if not _valid_address(to):
        return {"error": "Hedef adres geçersiz (0x + 40 karakter olmalı)."}, 400
    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        return {"error": "Tutar sayı olmalı."}, 400
    if amount <= 0:
        return {"error": "Tutar sıfırdan büyük olmalı."}, 400

    info = withdraw_info()
    if info.get("balance") is None:
        return {"error": "PM bakiyesi okunamadı — cüzdan tanımlı mı? " + (info.get("error") or "")}, 400
    if amount > info["balance"]:
        return {"error": f"Bakiye yetersiz: ${info['balance']:.2f} var, ${amount:.2f} istendi."}, 400
    if not info["proxy_match"]:
        return {"error": "Proxy adresi POLY_FUNDER ile uyuşmuyor — gönderim durduruldu."}, 400
    if not info["builder_ready"]:
        return {"error": "Relayer anahtarları eksik (POLY_BUILDER_API_KEY/SECRET/PASSPHRASE)."}, 400

    _audit("gonderim_basladi", to=to, amount=amount, token=token)

    # pm_transfer global POLY_DRY_RUN'a bakıyor; o bayrak alım-satım içindi.
    # Çekimin kendi kapısı (kod + onay) geçildiği için yalnız bu çağrı boyunca devre dışı.
    prev = os.environ.get("POLY_DRY_RUN")
    os.environ["POLY_DRY_RUN"] = "false"
    try:
        import pm_transfer
        res = pm_transfer.relay_send_erc20(
            to=to, amount_usd=amount, token=token, confirm=True, wait=True,
        )
    except Exception as e:
        _audit("gonderim_hata", to=to, amount=amount, hata=str(e)[:300])
        return {"error": str(e)[:300]}, 500
    finally:
        if prev is None:
            os.environ.pop("POLY_DRY_RUN", None)
        else:
            os.environ["POLY_DRY_RUN"] = prev

    _audit("gonderim_bitti", to=to, amount=amount,
           tx=res.get("transaction_hash") or res.get("transaction_id"))
    return res, 200


def withdraw_history(n: int = 10) -> list[dict]:
    if not os.path.exists(_WITHDRAW_LOG):
        return []
    try:
        with open(_WITHDRAW_LOG, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
    except Exception:
        return []
    return [r for r in rows if r.get("event") == "gonderim_bitti"][-n:][::-1]


def overview(book: str) -> dict:
    cfg = BOOKS[book]
    sanal = state(cfg["sanal"])
    shist = history(cfg["sanal"])
    sw, sn, swr = _wr(shist)
    pm = pm_snapshot(book)
    lhist = history(cfg["live"])
    _, ln, _ = _wr(lhist)

    return {
        "book": book,
        "badge": cfg["badge"], "title": cfg["title"], "subtitle": cfg["subtitle"],
        "timeline": cfg["timeline"],
        "live_open": live_open(book),
        "now": datetime.now(_TZ_TR).strftime("%H:%M:%S"),
        "sanal": {
            "balance": round(float(sanal.get("balance") or 0), 2),
            "pnl": round(float(sanal.get("total_pnl") or 0), 2),
            "open": len(sanal.get("open_positions") or []),
            "wr": swr, "w": sw, "trades": sn,
            "positions": [{
                "symbol": (p.get("symbol") or "").replace("USDT", ""),
                "dir": p.get("predicted_dir"),
                "entry": p.get("entry_price"),
                "amount": p.get("amount"),
                "slot": str(p.get("entry_time_tr") or "")[11:16],
            } for p in sanal.get("open_positions") or []],
        },
        "amounts": {**amounts(book), "wr": pm["live_wr"], "trades": ln, "open": pm["risk"]["open"]},
        "hours": hour_grid(lhist if lhist else shist),
        "hours_source": "live" if lhist else "sanal",
        "history": recent(lhist if lhist else shist),
        "history_source": "live" if lhist else "sanal",
        **pm,
    }
