"""cTrader Open API — yalnız OPEN API (/forex/openapi). CAPITAL'e dokunmaz.

Docs: https://help.ctrader.com/open-api/
Apps: https://openapi.ctrader.com/apps

OAuth REST + JSON WebSocket. Emir yok (yalnız hesap/fiyat/pozisyon).

Env:
  CTRADER_CLIENT_ID
  CTRADER_CLIENT_SECRET
  CTRADER_REDIRECT_URI   (uygulamada kayıtlı olmalı)
  CTRADER_SCOPE=accounts (görüntü; trading = emir hakkı, kullanmıyoruz)
  CTRADER_DEMO=true      (false = live.ctraderapi.com)
  CTRADER_ACCOUNT_ID     (boşsa token'daki ilk hesap)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
_ENV = _ROOT / ".env"
_TOKEN = _DIR / "data" / "ctrader_token.json"
_SYM = _DIR / "data" / "ctrader_symbol.json"

_TOKEN_URL = "https://openapi.ctrader.com/apps/token"
_GRANT_URL = "https://id.ctrader.com/my/settings/openapi/grantingaccess/"
_WS_DEMO = "wss://demo.ctraderapi.com:5036"
_WS_LIVE = "wss://live.ctraderapi.com:5036"

PT_APP_AUTH_REQ = 2100
PT_APP_AUTH_RES = 2101
PT_ACC_AUTH_REQ = 2102
PT_ACC_AUTH_RES = 2103
PT_SYMBOLS_REQ = 2114
PT_SYMBOLS_RES = 2115
PT_TRADER_REQ = 2121
PT_TRADER_RES = 2122
PT_RECONCILE_REQ = 2124
PT_RECONCILE_RES = 2125
PT_SUB_SPOTS_REQ = 2127
PT_SUB_SPOTS_RES = 2128
PT_SPOT_EVENT = 2131
PT_TREND_REQ = 2137
PT_TREND_RES = 2138
PT_ERROR = 2142
PT_ACCOUNTS_REQ = 2149
PT_ACCOUNTS_RES = 2150
PT_DEAL_LIST_REQ = 2133
PT_DEAL_LIST_RES = 2134
PT_HEARTBEAT = 51

_PERIOD = {
    "1m": 1, "5m": 5, "15m": 7, "30m": 8,
    "1h": 9, "4h": 10, "1d": 12,
}
_BAR_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
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
    return str(os.environ.get("CTRADER_DEMO") or "true").strip().lower() not in ("0", "false", "no")


def _client() -> tuple[str, str]:
    return (
        (os.environ.get("CTRADER_CLIENT_ID") or "").strip(),
        (os.environ.get("CTRADER_CLIENT_SECRET") or "").strip(),
    )


def redirect_uri() -> str:
    return (os.environ.get("CTRADER_REDIRECT_URI") or "https://bursaapp.com/forex/openapi/oauth").strip()


def scope() -> str:
    s = (os.environ.get("CTRADER_SCOPE") or "accounts").strip().lower()
    return s if s in ("accounts", "trading") else "accounts"


def app_configured() -> bool:
    cid, sec = _client()
    return bool(cid and sec)


def configured() -> bool:
    return app_configured() and bool((load_token().get("accessToken") or "").strip())


def ws_url() -> str:
    return _WS_DEMO if _demo() else _WS_LIVE


def load_token() -> dict:
    try:
        return json.loads(_TOKEN.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_token(data: dict) -> None:
    _TOKEN.parent.mkdir(parents=True, exist_ok=True)
    tmp = _TOKEN.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_TOKEN)


def oauth_url() -> str:
    cid, _ = _client()
    q = urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": redirect_uri(),
        "scope": scope(),
        "product": "web",
    })
    return f"{_GRANT_URL}?{q}"


def _token_http(params: dict) -> dict:
    cid, sec = _client()
    q = dict(params)
    q["client_id"] = cid
    q["client_secret"] = sec
    url = _TOKEN_URL + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(
        url, method="GET",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"ctrader token {e.code}: {err}") from e
    if not isinstance(body, dict):
        raise RuntimeError("ctrader token: bad body")
    if body.get("errorCode"):
        raise RuntimeError(f"ctrader token: {body.get('errorCode')} {body.get('description')}")
    if not body.get("accessToken"):
        raise RuntimeError("ctrader token: accessToken yok")
    body["saved_at"] = time.time()
    save_token(body)
    return body


def exchange_code(code: str) -> dict:
    return _token_http({
        "grant_type": "authorization_code",
        "code": (code or "").strip(),
        "redirect_uri": redirect_uri(),
    })


def refresh_access() -> dict:
    tok = load_token()
    rt = (tok.get("refreshToken") or "").strip()
    if not rt:
        raise RuntimeError("ctrader refreshToken yok — yeniden bağla")
    return _token_http({
        "grant_type": "refresh_token",
        "refresh_token": rt,
    })


def ensure_token() -> str:
    tok = load_token()
    at = (tok.get("accessToken") or "").strip()
    if not at:
        raise RuntimeError("ctrader accessToken yok")
    saved = float(tok.get("saved_at") or 0)
    exp = float(tok.get("expiresIn") or 2_628_000)
    if saved and time.time() - saved > max(60.0, exp - 86_400):
        tok = refresh_access()
        at = (tok.get("accessToken") or "").strip()
    return at


def _money(v, digits=None) -> float | None:
    if v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    d = int(digits) if digits not in (None, "") else 2
    if d <= 0:
        return n
    return n / (10 ** d)


def _px(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v) / 100_000.0
    except (TypeError, ValueError):
        return None


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class _Ws:
    def __init__(self, ws):
        self.ws = ws
        self.inbox: list[dict] = []

    async def send(self, payload_type: int, payload: dict) -> str:
        mid = uuid.uuid4().hex[:12]
        await self.ws.send(json.dumps({
            "clientMsgId": mid,
            "payloadType": payload_type,
            "payload": payload,
        }))
        return mid

    async def recv(self, timeout: float = 12.0) -> dict:
        raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        msg = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(msg, dict):
            return {"payloadType": 0, "payload": {}}
        pt = int(msg.get("payloadType") or 0)
        if pt == PT_HEARTBEAT:
            try:
                await self.send(PT_HEARTBEAT, {})
            except Exception:
                pass
        return msg

    async def wait(self, types: set[int], timeout: float = 15.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = await self.recv(timeout=max(0.5, deadline - time.time()))
            pt = int(msg.get("payloadType") or 0)
            if pt == PT_HEARTBEAT:
                continue
            if pt == PT_ERROR:
                p = msg.get("payload") or {}
                raise RuntimeError(f"ctrader {p.get('errorCode') or p.get('description') or p}")
            if pt in types:
                return msg
            self.inbox.append(msg)
        raise TimeoutError(f"ctrader timeout {sorted(types)}")


async def _authed(ws: _Ws) -> tuple[int, str]:
    cid, sec = _client()
    token = ensure_token()
    await ws.send(PT_APP_AUTH_REQ, {"clientId": cid, "clientSecret": sec})
    await ws.wait({PT_APP_AUTH_RES})
    acc_env = (os.environ.get("CTRADER_ACCOUNT_ID") or "").strip()
    acc_id = int(acc_env) if acc_env.isdigit() else 0
    if not acc_id:
        await ws.send(PT_ACCOUNTS_REQ, {"accessToken": token})
        res = await ws.wait({PT_ACCOUNTS_RES})
        rows = (res.get("payload") or {}).get("ctidTraderAccount") or []
        if not rows:
            raise RuntimeError("ctrader hesap listesi boş")
        acc_id = int(rows[0].get("ctidTraderAccountId"))
    await ws.send(PT_ACC_AUTH_REQ, {
        "ctidTraderAccountId": acc_id,
        "accessToken": token,
    })
    await ws.wait({PT_ACC_AUTH_RES})
    return acc_id, token


async def _with_ws(fn):
    import websockets

    last_err = None
    for attempt in range(2):
        try:
            async with websockets.connect(ws_url(), open_timeout=12, close_timeout=3) as raw:
                ws = _Ws(raw)
                acc_id, token = await _authed(ws)
                return await fn(ws, acc_id, token)
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if attempt == 0 and ("token" in msg or "auth" in msg or "expired" in msg or "invalid" in msg):
                try:
                    refresh_access()
                    continue
                except Exception:
                    pass
            raise
    raise last_err or RuntimeError("ctrader ws")


def _run(fn):
    return asyncio.run(_with_ws(fn))


def _load_sym() -> dict:
    try:
        return json.loads(_SYM.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_sym(data: dict) -> None:
    _SYM.parent.mkdir(parents=True, exist_ok=True)
    tmp = _SYM.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_SYM)


def _pick_gold(symbols: list) -> dict | None:
    ranked = []
    for s in symbols or []:
        name = str(s.get("symbolName") or s.get("name") or "").upper().replace(" ", "")
        if name in ("XAUUSD", "XAU/USD", "GOLD", "XAUUSD.A", "XAUUSD."):
            ranked.append((0, s))
        elif "XAUUSD" in name or name.startswith("XAU"):
            ranked.append((1, s))
        elif name == "GOLD":
            ranked.append((0, s))
    ranked.sort(key=lambda x: x[0])
    return ranked[0][1] if ranked else None


async def _ensure_symbol(ws: _Ws, acc_id: int) -> dict:
    cached = _load_sym()
    if cached.get("symbolId") and cached.get("accountId") == acc_id:
        return cached
    await ws.send(PT_SYMBOLS_REQ, {
        "ctidTraderAccountId": acc_id,
        "includeArchivedSymbols": False,
    })
    res = await ws.wait({PT_SYMBOLS_RES}, timeout=20)
    rows = (res.get("payload") or {}).get("symbol") or []
    hit = _pick_gold(rows)
    if not hit:
        raise RuntimeError("ctrader XAUUSD/GOLD sembolü yok")
    out = {
        "accountId": acc_id,
        "symbolId": int(hit.get("symbolId")),
        "symbolName": hit.get("symbolName") or "XAUUSD",
        "digits": int(hit.get("digits") or 2),
    }
    _save_sym(out)
    return out


def quote() -> dict:
    async def _do(ws, acc_id, _token):
        sym = await _ensure_symbol(ws, acc_id)
        await ws.send(PT_SUB_SPOTS_REQ, {
            "ctidTraderAccountId": acc_id,
            "symbolId": [sym["symbolId"]],
        })
        await ws.wait({PT_SUB_SPOTS_RES, PT_SPOT_EVENT})
        spot = None
        deadline = time.time() + 8
        while time.time() < deadline:
            msg = await ws.recv(timeout=max(0.4, deadline - time.time()))
            if int(msg.get("payloadType") or 0) == PT_SPOT_EVENT:
                spot = msg.get("payload") or {}
                break
        if not spot:
            raise RuntimeError("ctrader spot yok")
        bid = _px(spot.get("bid"))
        ask = _px(spot.get("ask"))
        mid = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2
        elif bid is not None:
            mid = bid
        elif ask is not None:
            mid = ask
        return {
            "ok": True,
            "symbol": "XAUUSD",
            "name": "Altın / Dolar",
            "epic": sym.get("symbolName") or "XAUUSD",
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread": (ask - bid) if bid is not None and ask is not None else None,
            "src": "ctrader_demo" if _demo() else "ctrader_live",
            "market_status": "TRADEABLE",
            "stale_sec": 0,
            "dec": int(sym.get("digits") or 2),
        }

    return _run(_do)


def prices(tf: str = "1m", limit: int = 200) -> list[dict]:
    tf = tf if tf in _PERIOD else "1m"
    n = max(20, min(500, int(limit)))
    period = _PERIOD[tf]
    span = _BAR_MS[tf] * (n + 5)
    to_ts = int(time.time() * 1000)
    from_ts = to_ts - span

    async def _do(ws, acc_id, _token):
        sym = await _ensure_symbol(ws, acc_id)
        await ws.send(PT_TREND_REQ, {
            "ctidTraderAccountId": acc_id,
            "symbolId": sym["symbolId"],
            "period": period,
            "fromTimestamp": from_ts,
            "toTimestamp": to_ts,
            "count": n,
        })
        res = await ws.wait({PT_TREND_RES}, timeout=20)
        bars = (res.get("payload") or {}).get("trendbar") or []
        out = []
        for b in bars:
            low = _px(b.get("low"))
            if low is None:
                continue
            o = low + (_px(b.get("deltaOpen")) or 0)
            c = low + (_px(b.get("deltaClose")) or 0)
            h = low + (_px(b.get("deltaHigh")) or 0)
            ts = b.get("utcTimestampInMinutes")
            if ts is None:
                ts = b.get("timestamp")
            if ts is None:
                continue
            tsec = int(ts) * 60 if int(ts) < 10_000_000_000 else int(ts) // 1000
            out.append({
                "time": tsec,
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "volume": float(b.get("volume") or 0),
            })
        out.sort(key=lambda x: x["time"])
        return out[-n:]

    return _run(_do)


def snapshot_book() -> dict:
    async def _do(ws, acc_id, _token):
        await ws.send(PT_TRADER_REQ, {"ctidTraderAccountId": acc_id})
        tr = ((await ws.wait({PT_TRADER_RES})).get("payload") or {}).get("trader") or {}
        digits = tr.get("moneyDigits")
        balance = _money(tr.get("balance"), digits) or 0.0
        await ws.send(PT_RECONCILE_REQ, {"ctidTraderAccountId": acc_id})
        rec = (await ws.wait({PT_RECONCILE_RES})).get("payload") or {}
        pos_out = []
        for row in rec.get("position") or []:
            td = row.get("tradeData") or {}
            side_raw = str(td.get("tradeSide") or "").upper()
            side = "buy" if side_raw in ("1", "BUY") else "sell"
            md = row.get("moneyDigits") or digits
            vol = td.get("volume")
            try:
                lots = float(vol) / 100.0 if vol is not None else None
            except (TypeError, ValueError):
                lots = None
            pos_out.append({
                "id": row.get("positionId"),
                "symbol": "XAUUSD",
                "side": side,
                "volume": lots if lots is not None else vol,
                "entry": _f(row.get("price")),
                "mark": None,
                "open_time": td.get("openTimestamp") or row.get("utcLastUpdateTimestamp"),
                "float_pnl": None,
                "float_net": None,
                "stop": _f(row.get("stopLoss")),
                "target": _f(row.get("takeProfit")),
                "leverage": None,
                "src": "ctrader",
                "swap": _money(row.get("swap"), md),
            })
        hist = []
        try:
            now_ms = int(time.time() * 1000)
            await ws.send(PT_DEAL_LIST_REQ, {
                "ctidTraderAccountId": acc_id,
                "fromTimestamp": now_ms - 7 * 86400 * 1000,
                "toTimestamp": now_ms,
                "maxRows": 200,
            })
            deals = ((await ws.wait({PT_DEAL_LIST_RES}, timeout=12)).get("payload") or {}).get("deal") or []
            for d in deals:
                td = d.get("tradeData") or {}
                side_raw = str(td.get("tradeSide") or "").upper()
                md = d.get("moneyDigits") or digits
                hist.append({
                    "side": "buy" if side_raw in ("1", "BUY") else "sell",
                    "volume": td.get("volume"),
                    "entry": _f(d.get("executionPrice") or d.get("closePrice")),
                    "exit": _f(d.get("executionPrice")),
                    "pnl": _money(d.get("closePositionDetail", {}).get("grossProfit") if isinstance(d.get("closePositionDetail"), dict) else d.get("pnl"), md),
                    "reason": str(d.get("dealStatus") or ""),
                    "open_time": td.get("openTimestamp"),
                    "close_time": d.get("executionTimestamp"),
                    "src": "ctrader",
                })
        except Exception:
            hist = []
        out = {
            "ok": True,
            "book": "openapi",
            "symbol": "XAUUSD",
            "balance": balance,
            "equity": balance,
            "available": None,
            "init_balance": None,
            "total_pnl": None,
            "float_pnl": None,
            "open_count": len(pos_out),
            "trade_count": len(hist) + len(pos_out),
            "position": pos_out[0] if pos_out else None,
            "positions": pos_out,
            "history": list(reversed(hist[-200:])),
            "live": {
                "ok": True,
                "demo": _demo(),
                "account_id": acc_id,
                "account_name": tr.get("brokerName") or "cTrader",
                "currency": "USD",
                "status": "authorized",
                "login": tr.get("traderLogin"),
            },
            "src": "ctrader_demo" if _demo() else "ctrader_live",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        try:
            from desk_meta import attach
            attach(out, "oapi", hist=hist, init=out.get("init_balance") or out.get("balance"))
        except Exception:
            pass
        return out

    return _run(_do)


def status() -> dict:
    if not app_configured():
        return {
            "ok": False,
            "configured": False,
            "oauth_ready": False,
            "demo": _demo(),
            "error": "credentials_missing",
            "need": ["CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET"],
            "apps": "https://openapi.ctrader.com/apps",
            "redirect_uri": redirect_uri(),
        }
    if not configured():
        return {
            "ok": False,
            "configured": False,
            "oauth_ready": True,
            "demo": _demo(),
            "error": "token_missing",
            "oauth_url": oauth_url(),
            "connect": "/forex/openapi/connect",
            "redirect_uri": redirect_uri(),
            "apps": "https://openapi.ctrader.com/apps",
        }
    try:
        book = snapshot_book()
        q = quote()
        return {
            "ok": True,
            "configured": True,
            "oauth_ready": True,
            "demo": _demo(),
            "account": book.get("live"),
            "balance": book.get("balance"),
            "equity": book.get("equity"),
            "open_count": book.get("open_count"),
            "epic": q.get("epic"),
            "bid": q.get("bid"),
            "ask": q.get("ask"),
            "src": q.get("src"),
        }
    except Exception as e:
        return {
            "ok": False,
            "configured": True,
            "oauth_ready": True,
            "demo": _demo(),
            "error": str(e)[:240],
            "oauth_url": oauth_url(),
            "connect": "/forex/openapi/connect",
        }


def ping() -> dict:
    if not configured():
        return {"ok": False, "error": "token_missing"}
    try:
        q = quote()
        return {"ok": True, "bid": q.get("bid"), "ask": q.get("ask"), "src": q.get("src")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
