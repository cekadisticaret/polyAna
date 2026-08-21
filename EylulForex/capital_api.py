"""Capital.com Open API — yalnız CAPITAL (/forex/cem02). Demo varsayılan.

Docs: https://open-api.capital.com/
Base demo: https://demo-api-capital.backend-capital.com/

Env:
  CAPITAL_API_KEY
  CAPITAL_IDENTIFIER   (platform e-posta)
  CAPITAL_API_PASSWORD (API key özel şifresi, hesap şifresi değil)
  CAPITAL_DEMO=true    (false = canlı URL; varsayılan demo)
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
_ENV = _ROOT / ".env"
_SESS = _DIR / "data" / "capital_session.json"
_EPIC_CACHE = _DIR / "data" / "capital_epic.json"

_DEMO = "https://demo-api-capital.backend-capital.com"
_LIVE = "https://api-capital.backend-capital.com"
_SESSION_TTL = 8 * 60  # 10 dk; yenilemeyi erken tut
_RES = {
    "1m": "MINUTE",
    "5m": "MINUTE_5",
    "15m": "MINUTE_15",
    "30m": "MINUTE_30",
    "1h": "HOUR",
    "4h": "HOUR_4",
    "1d": "DAY",
}

if _ENV.exists():
    for _line in _ENV.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _k, _v = _k.strip(), _v.strip()
            if _v or not os.environ.get(_k):
                os.environ[_k] = _v


def _demo() -> bool:
    return str(os.environ.get("CAPITAL_DEMO") or "true").strip().lower() not in ("0", "false", "no")


def base_url() -> str:
    return _DEMO if _demo() else _LIVE


def keys() -> tuple[str, str, str]:
    return (
        (os.environ.get("CAPITAL_API_KEY") or "").strip(),
        (os.environ.get("CAPITAL_IDENTIFIER") or "").strip(),
        (os.environ.get("CAPITAL_API_PASSWORD") or "").strip(),
    )


def configured() -> bool:
    k, ident, pw = keys()
    return bool(k and ident and pw)


def _load_sess() -> dict:
    try:
        return json.loads(_SESS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_sess(data: dict) -> None:
    _SESS.parent.mkdir(parents=True, exist_ok=True)
    tmp = _SESS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_SESS)


def _http(method: str, path: str, body: dict | None = None, auth: bool = True, retry: bool = True) -> tuple[dict, dict]:
    url = base_url() + path
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    api_key, _, _ = keys()
    if api_key:
        headers["X-CAP-API-KEY"] = api_key
    if auth:
        sess = ensure_session()
        headers["CST"] = sess["cst"]
        headers["X-SECURITY-TOKEN"] = sess["security"]
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8") or "{}"
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"raw": raw}
            if not isinstance(payload, dict):
                payload = {"data": payload}
            return payload, hdrs
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:400]
        if auth and retry and e.code in (401, 403):
            _SESS.unlink(missing_ok=True)
            return _http(method, path, body, auth=True, retry=False)
        raise RuntimeError(f"capital {method} {path} {e.code}: {err_body}") from e


def ensure_session() -> dict:
    now = time.time()
    cached = _load_sess()
    if (
        cached.get("cst")
        and cached.get("security")
        and float(cached.get("until") or 0) > now
        and cached.get("demo") == _demo()
    ):
        return cached
    if not configured():
        raise RuntimeError("capital_credentials_missing")
    api_key, ident, pw = keys()
    body = {"identifier": ident, "password": pw, "encryptedPassword": False}
    url = base_url() + "/api/v1/session"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-CAP-API-KEY": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8") or "{}"
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"capital_session {e.code}: {err}") from e
    cst = hdrs.get("cst") or ""
    sec = hdrs.get("x-security-token") or ""
    if not cst or not sec:
        raise RuntimeError("capital_session_no_tokens")
    sess = {
        "cst": cst,
        "security": sec,
        "until": now + _SESSION_TTL,
        "demo": _demo(),
        "account_id": (payload.get("currentAccountId") or payload.get("accountId") or ""),
        "ts": now,
    }
    _save_sess(sess)
    return sess


def ping() -> dict:
    if not configured():
        return {"ok": False, "error": "credentials_missing", "demo": _demo()}
    try:
        body, _ = _http("GET", "/api/v1/ping")
        return {"ok": True, "demo": _demo(), "pong": body}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "demo": _demo()}


def accounts() -> list[dict]:
    body, _ = _http("GET", "/api/v1/accounts")
    rows = body.get("accounts") or []
    return rows if isinstance(rows, list) else []


def preferred_account() -> dict:
    rows = accounts()
    for a in rows:
        if a.get("preferred"):
            return a
    return rows[0] if rows else {}


def resolve_epic(search: str = "GOLD") -> str:
    try:
        cached = json.loads(_EPIC_CACHE.read_text(encoding="utf-8"))
        if cached.get("epic") and time.time() - float(cached.get("ts") or 0) < 3600:
            return str(cached["epic"])
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    q = urllib.parse.urlencode({"searchTerm": search})
    body, _ = _http("GET", f"/api/v1/markets?{q}")
    markets = body.get("markets") or []
    want = ("GOLD", "XAUUSD", "GOLD/USD", "XAU/USD")
    pick = None
    for m in markets:
        epic = str(m.get("epic") or "")
        name = str(m.get("instrumentName") or m.get("symbol") or "")
        status = str(m.get("marketStatus") or "")
        if epic in want or name.upper() in want:
            pick = m
            if status == "TRADEABLE":
                break
        if pick is None and "GOLD" in (epic + " " + name).upper() and "SILVER" not in name.upper():
            pick = m
    if not pick and markets:
        pick = markets[0]
    if not pick:
        raise RuntimeError("capital_epic_not_found")
    epic = str(pick["epic"])
    _EPIC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _EPIC_CACHE.write_text(json.dumps({"epic": epic, "ts": time.time(), "name": pick.get("instrumentName")}), encoding="utf-8")
    return epic


def market(epic: str | None = None) -> dict:
    epic = epic or resolve_epic()
    body, _ = _http("GET", f"/api/v1/markets/{urllib.parse.quote(epic, safe='')}")
    snap = body.get("snapshot") if isinstance(body.get("snapshot"), dict) else {}
    inst = body.get("instrument") if isinstance(body.get("instrument"), dict) else {}
    out = {**inst, **snap}
    out["epic"] = epic or inst.get("epic") or out.get("epic")
    return out


def quote() -> dict:
    m = market()
    bid = m.get("bid")
    ask = m.get("offer") or m.get("ask") or m.get("ofr")
    try:
        bid = float(bid) if bid is not None else None
        ask = float(ask) if ask is not None else None
    except (TypeError, ValueError):
        bid = ask = None
    mid = None
    if bid is not None and ask is not None:
        mid = round((bid + ask) / 2, 2)
        spr = round(ask - bid, 2)
    elif bid is not None:
        mid, spr, ask = bid, None, None
    else:
        spr = None
    return {
        "ok": True,
        "symbol": "XAUUSD",
        "name": "Altın / Dolar",
        "epic": m.get("epic"),
        "dec": 2,
        "mid": mid,
        "bid": round(bid, 2) if bid is not None else None,
        "ask": round(ask, 2) if ask is not None else None,
        "spread": spr,
        "day_high": _f(m.get("high")),
        "day_low": _f(m.get("low")),
        "live_price": mid,
        "src": "capital_demo" if _demo() else "capital_live",
        "market_status": m.get("marketStatus"),
        "stale_sec": 0,
    }


def _f(v):
    try:
        return round(float(v), 2) if v is not None else None
    except (TypeError, ValueError):
        return None


def _mid_px(obj: dict | None) -> float | None:
    if not isinstance(obj, dict):
        return None
    bid, ask = obj.get("bid"), obj.get("ask")
    try:
        if bid is not None and ask is not None:
            return (float(bid) + float(ask)) / 2
        if bid is not None:
            return float(bid)
        if ask is not None:
            return float(ask)
    except (TypeError, ValueError):
        return None
    return None


def prices(tf: str = "1m", limit: int = 240, epic: str | None = None) -> list[dict]:
    epic = epic or resolve_epic()
    res = _RES.get(tf, "MINUTE")
    n = max(20, min(1000, int(limit)))
    q = urllib.parse.urlencode({"resolution": res, "max": n})
    body, _ = _http("GET", f"/api/v1/prices/{urllib.parse.quote(epic, safe='')}?{q}")
    rows = []
    for p in body.get("prices") or []:
        ts = p.get("snapshotTimeUTC") or p.get("snapshotTime")
        try:
            t = int(datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp())
        except (TypeError, ValueError):
            continue
        o = _mid_px(p.get("openPrice"))
        h = _mid_px(p.get("highPrice"))
        lo = _mid_px(p.get("lowPrice"))
        c = _mid_px(p.get("closePrice"))
        if None in (o, h, lo, c):
            continue
        rows.append({
            "time": t,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(lo, 2),
            "close": round(c, 2),
            "volume": float(p.get("lastTradedVolume") or 0),
        })
    return rows


def positions() -> list[dict]:
    body, _ = _http("GET", "/api/v1/positions")
    rows = body.get("positions") or []
    return rows if isinstance(rows, list) else []


def transactions(last_period: int = 86400) -> list[dict]:
    q = urllib.parse.urlencode({"lastPeriod": int(last_period)})
    try:
        body, _ = _http("GET", f"/api/v1/history/transactions?{q}")
    except Exception:
        return []
    rows = body.get("transactions") or []
    return rows if isinstance(rows, list) else []


def snapshot_book() -> dict:
    """CEM01 defter şekli — CAPITAL ekranı aynı JS ile okusun."""
    acc = preferred_account()
    bal = (acc.get("balance") or {}) if isinstance(acc.get("balance"), dict) else {}
    balance = _f(bal.get("balance")) or 0.0
    available = _f(bal.get("available"))
    upl = _f(bal.get("profitLoss")) or 0.0
    equity = round(balance + (upl or 0), 2)
    pos_out = []
    for row in positions():
        p = row.get("position") or {}
        m = row.get("market") or {}
        direction = str(p.get("direction") or "").upper()
        side = "buy" if direction == "BUY" else "sell"
        entry = _f(p.get("level"))
        mark = _f(m.get("bid") if side == "sell" else (m.get("offer") or m.get("ask")))
        pos_out.append({
            "id": p.get("dealId"),
            "symbol": m.get("epic") or m.get("symbol") or "XAUUSD",
            "side": side,
            "volume": p.get("size"),
            "entry": entry,
            "mark": mark,
            "open_time": p.get("createdDate") or p.get("createdDateUTC"),
            "float_pnl": _f(p.get("upl")),
            "float_net": _f(p.get("upl")),
            "stop": _f(p.get("stopLevel")),
            "target": _f(p.get("profitLevel")),
            "leverage": p.get("leverage"),
            "src": "capital",
        })
    hist = []
    for t in transactions(86400 * 7):
        note = str(t.get("note") or t.get("transactionType") or "")
        hist.append({
            "side": "sell" if "SELL" in note.upper() else "buy",
            "volume": t.get("size"),
            "entry": None,
            "exit": None,
            "pnl": _f(t.get("size")) if t.get("transactionType") == "TRADE" else None,
            "reason": note,
            "open_time": t.get("date") or t.get("dateUtc"),
            "close_time": t.get("date") or t.get("dateUtc"),
            "src": "capital",
        })
    out = {
        "ok": True,
        "book": "capital",
        "symbol": "XAUUSD",
        "balance": balance,
        "equity": equity,
        "available": available,
        "init_balance": _f(bal.get("deposit")),
        "total_pnl": upl,
        "float_pnl": upl if pos_out else None,
        "open_count": len(pos_out),
        "trade_count": len(hist) + len(pos_out),
        "position": pos_out[0] if pos_out else None,
        "positions": pos_out,
        "history": list(reversed(hist[-200:])),
        "live": {
            "ok": True,
            "demo": _demo(),
            "account_id": acc.get("accountId"),
            "account_name": acc.get("accountName"),
            "currency": acc.get("currency") or "USD",
            "status": acc.get("status"),
        },
        "src": "capital_demo" if _demo() else "capital_live",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        from desk_meta import attach
        attach(out, "cem02", hist=hist, init=out.get("init_balance") or out.get("balance"))
    except Exception:
        pass
    return out


def status() -> dict:
    if not configured():
        return {
            "ok": False,
            "configured": False,
            "demo": _demo(),
            "error": "credentials_missing",
            "need": ["CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_API_PASSWORD"],
        }
    try:
        book = snapshot_book()
        q = quote()
        return {
            "ok": True,
            "configured": True,
            "demo": _demo(),
            "account": book.get("live"),
            "balance": book.get("balance"),
            "equity": book.get("equity"),
            "open_count": book.get("open_count"),
            "epic": q.get("epic"),
            "bid": q.get("bid"),
            "ask": q.get("ask"),
        }
    except Exception as e:
        return {"ok": False, "configured": True, "demo": _demo(), "error": str(e)[:240]}
