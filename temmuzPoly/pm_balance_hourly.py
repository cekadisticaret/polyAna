"""Polymarket portföy bakiyesi — saatlik kayıt + 00:00 Telegram özeti + düşüş ALERT."""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

_ENV_FILE = os.path.join(_DIR, "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from pm_trader_helpers import pm_get_balance
from telegram_poly_channels import chat_pm_live

_TZ_TR = ZoneInfo("Europe/Istanbul")
DATA_FILE = os.path.join(_DIR, "pm_balance_hourly.json")
MAX_RECORDS = 8760  # ~1 yıl

# A1 Live / PolyAktif bot
BOT_TOKEN = "8529258517:AAHuVn1VFftXK7RR2Z1w3UqyHGuHNDXDYI4"
CHAT_ID = chat_pm_live()


def _portfolio() -> tuple[float, float, float] | None:
    """(cash_usdc, positions_usd, portfolio_usd) — API hatasında None."""
    try:
        cash = pm_get_balance()
    except Exception as e:
        print(f"[PM BALANCE] bakiye okunamadı: {e}", file=sys.stderr)
        return None
    if cash < 0:
        print("[PM BALANCE] POLY_PRIVATE_KEY yok veya API hatası — kayıt atlanıyor", file=sys.stderr)
        return None
    pos_val = 0.0
    funder = os.getenv("POLY_FUNDER", "")
    if funder:
        try:
            url = f"https://data-api.polymarket.com/positions?user={funder}&sizeThreshold=0.01"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                for p in json.load(r):
                    pos_val += float(p.get("currentValue") or 0)
        except Exception as e:
            print(f"[PM BALANCE] positions API: {e}", file=sys.stderr)
    return round(cash, 2), round(pos_val, 2), round(cash + pos_val, 2)


def _load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"records": []}
    try:
        with open(DATA_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return {"records": data}
        return data
    except Exception:
        return {"records": []}


def _save_data(data: dict) -> None:
    recs = data.get("records", [])
    if len(recs) > MAX_RECORDS:
        data["records"] = recs[-MAX_RECORDS:]
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _last_midnight_record(records: list, before: datetime) -> dict | None:
    """before gününden önceki en son 00:xx kaydı."""
    target_date = before.date()
    candidates = []
    for r in records:
        ts = r.get("time_tr", "")
        if len(ts) < 16:
            continue
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_TZ_TR)
        except Exception:
            continue
        if dt.date() < target_date and dt.hour == 0:
            candidates.append((dt, r))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def tg_send(text: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=body)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"[PM BALANCE TG] Hata: {e}", file=sys.stderr)
        return False


def _hour_label(time_tr: str) -> str:
    if len(time_tr) >= 16:
        return time_tr[11:16]
    return time_tr


def _unique_hourly_records(records: list) -> list:
    by_hour: dict[str, dict] = {}
    for r in records:
        ts = r.get("time_tr", "")
        if len(ts) < 13:
            continue
        by_hour[ts[:13]] = r
    return sorted(by_hour.values(), key=lambda x: x.get("time_tr", ""))


def _three_consecutive_drops(records: list) -> list | None:
    """Son 3 saatlik kayıt sürekli düşüyorsa o 3 kaydı döndür."""
    if len(records) < 3:
        return None
    last3 = records[-3:]
    vals = [float(r.get("portfolio_usd") or 0) for r in last3]
    if vals[0] > vals[1] > vals[2]:
        return last3
    return None


def _drop_alert_message(records: list) -> str:
    sep = "━" * 26
    v0 = float(records[0].get("portfolio_usd") or 0)
    v2 = float(records[2].get("portfolio_usd") or 0)
    total_drop = round(v0 - v2, 2)
    lines = [
        sep,
        "🔴 <b>ALERT — PM Bakiye Düşüşü</b>",
        "",
        "⚠️ <b>3 saat üst üste düşüş</b> tespit edildi",
        "",
    ]
    prev = None
    for r in records:
        val = float(r.get("portfolio_usd") or 0)
        lbl = _hour_label(r.get("time_tr", ""))
        if prev is None:
            lines.append(f"🕐 {lbl}  <b>${val:.2f}</b>")
        else:
            d = round(val - prev, 2)
            lines.append(f"🕐 {lbl}  <b>${val:.2f}</b>  <code>({d:+.2f}$)</code>")
        prev = val
    lines += [
        "",
        f"📉 3 saat toplam: <b>-${total_drop:.2f}</b>",
        f"📊 Güncel portföy: <b>${v2:.2f}</b>",
        sep,
    ]
    return "\n".join(lines)


def _continuing_alert_message(prev_r: dict, cur_r: dict) -> str:
    sep = "━" * 26
    prev_val = float(prev_r.get("portfolio_usd") or 0)
    cur_val = float(cur_r.get("portfolio_usd") or 0)
    delta = round(cur_val - prev_val, 2)
    lines = [
        sep,
        "🔴 <b>ALERT — Düşüş Devam Ediyor</b>",
        "",
        "⚠️ Bakiye <b>yükselmedi</b>, düşüş sürüyor",
        "",
        f"🕐 {_hour_label(prev_r.get('time_tr', ''))}  <b>${prev_val:.2f}</b>",
        f"🕐 {_hour_label(cur_r.get('time_tr', ''))}  <b>${cur_val:.2f}</b>  <code>({delta:+.2f}$)</code>",
        "",
        f"📊 Güncel portföy: <b>${cur_val:.2f}</b>",
        sep,
    ]
    return "\n".join(lines)


def _check_drop_alerts(data: dict, dry_run: bool = False) -> None:
    """Peş peşe 3 saat düşüş → ilk ALERT; sonrasında düşüş sürerse devam uyarısı."""
    records = _unique_hourly_records(data.get("records", []))
    if len(records) < 2:
        return

    alert = data.setdefault("alert", {
        "active": False,
        "initial_sent_at": None,
        "last_contin_sent_at": None,
    })
    cur = records[-1]
    cur_ts = cur.get("time_tr", "")
    prev = records[-2]
    cur_val = float(cur.get("portfolio_usd") or 0)
    prev_val = float(prev.get("portfolio_usd") or 0)

    # Toparlanma: yükseldiyse uyarı modunu kapat
    if alert.get("active") and cur_val > prev_val:
        alert["active"] = False
        alert["initial_sent_at"] = None
        alert["last_contin_sent_at"] = None
        print(f"[PM BALANCE] Alert sıfırlandı — bakiye yükseldi (${prev_val:.2f} → ${cur_val:.2f})")
        return

    drop3 = _three_consecutive_drops(records)

    # İlk ALERT: 3 saat üst üste düşüş
    if drop3 and not alert.get("active"):
        msg = _drop_alert_message(drop3)
        print(f"[PM BALANCE] 3 saat düşüş ALERT tetiklendi")
        if dry_run:
            print(msg)
        else:
            ok = tg_send(msg)
            print(f"[PM BALANCE] Düşüş ALERT Telegram {'OK' if ok else 'HATA'}")
        alert["active"] = True
        alert["initial_sent_at"] = cur_ts
        alert["last_contin_sent_at"] = None
        return

    # Devam uyarısı: alert aktifken bir saat daha düştüyse
    if alert.get("active") and cur_val < prev_val:
        if alert.get("last_contin_sent_at") == cur_ts:
            return
        msg = _continuing_alert_message(prev, cur)
        print(f"[PM BALANCE] Düşüş devam ALERT (${prev_val:.2f} → ${cur_val:.2f})")
        if dry_run:
            print(msg)
        else:
            ok = tg_send(msg)
            print(f"[PM BALANCE] Devam ALERT Telegram {'OK' if ok else 'HATA'}")
        alert["last_contin_sent_at"] = cur_ts


def _midnight_message(now_tr: datetime, cash: float, pos: float, total: float, prev: dict | None) -> str:
    date_str = now_tr.strftime("%d.%m.%Y")
    sep = "━" * 26
    lines = [
        sep,
        f"🌙 <b>PM Bakiye — {date_str} 00:00 İST</b>",
        f"💵 USDC nakit: <b>${cash:.2f}</b>",
    ]
    if pos > 0.01:
        lines.append(f"🎫 Açık token: <b>${pos:.2f}</b>")
    lines.append(f"📊 Toplam portföy: <b>${total:.2f}</b>")

    if prev:
        prev_total = float(prev.get("portfolio_usd") or 0)
        if prev_total > 0:
            delta = round(total - prev_total, 2)
            icon = "🟢" if delta >= 0 else "🔴"
            prev_day = (prev.get("time_tr") or "")[:10]
            lines.append(f"{icon} Önceki gece ({prev_day}): ${prev_total:.2f}  →  {delta:+.2f}$")

    dep = 0.0
    try:
        with open(os.path.join(_DIR, "poly_trader_analiz5_state.json")) as f:
            a5 = json.load(f)
        dep = float(a5.get("deposit_usd") or 0)
    except Exception:
        pass
    if dep > 0:
        net = round(total - dep, 2)
        icon = "🟢" if net >= 0 else "🔴"
        lines.append(f"{icon} Yatırım ${dep:.0f}'a göre net: {net:+.2f}$")

    lines.append(sep)
    return "\n".join(lines)


def run() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    port = _portfolio()
    if port is None:
        print(f"[PM BALANCE] {now_tr.strftime('%H:%M')} İST — API hatası, saatlik kayıt atlandı")
        return
    cash, pos, total = port

    data = _load_data()
    record = {
        "time_tr": now_tr.replace(minute=0, second=0, microsecond=0).isoformat(),
        "cash_usdc": cash,
        "positions_usd": pos,
        "portfolio_usd": total,
    }
    data.setdefault("records", []).append(record)
    _save_data(data)

    saat = now_tr.strftime("%H:%M")
    print(
        f"[PM BALANCE] {saat} İST — kaydedildi: "
        f"nakit ${cash:.2f} + token ${pos:.2f} = ${total:.2f}"
    )

    if now_tr.hour == 0:
        prev = _last_midnight_record(data["records"][:-1], now_tr)
        msg = _midnight_message(now_tr, cash, pos, total, prev)
        ok = tg_send(msg)
        print(f"[PM BALANCE] 00:00 Telegram {'OK' if ok else 'HATA'}")

    _check_drop_alerts(data)
    _save_data(data)


def test_alert() -> None:
    """Örnek veriyle ALERT mesajlarını Telegram'a gönder (gerçek bakiye okumaz)."""
    sample = {
        "records": [
            {"time_tr": "2026-07-22T09:00:00+03:00", "portfolio_usd": 376.0},
            {"time_tr": "2026-07-22T10:00:00+03:00", "portfolio_usd": 372.0},
            {"time_tr": "2026-07-22T11:00:00+03:00", "portfolio_usd": 355.0},
        ],
        "alert": {"active": False, "initial_sent_at": None, "last_contin_sent_at": None},
    }
    print("[PM BALANCE TEST] İlk ALERT (3 saat düşüş):")
    _check_drop_alerts(sample, dry_run=False)

    sample["records"].append(
        {"time_tr": "2026-07-22T12:00:00+03:00", "portfolio_usd": 348.0}
    )
    print("[PM BALANCE TEST] Devam ALERT:")
    _check_drop_alerts(sample, dry_run=False)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test-alert":
        test_alert()
    else:
        run()
