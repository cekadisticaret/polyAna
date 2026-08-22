#!/usr/bin/env python3
"""CoptC Forex API — bursaapp /poly/api/forex ve /forex/api aynası.

    python3 EylulForex/forex_server.py   # 127.0.0.1:5070
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
sys.path.insert(0, str(_DIR))
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "temmuzPoly"))
sys.path.insert(0, str(_ROOT / "AgustosKripto"))

_ENV = _ROOT / ".env"
if _ENV.exists():
    for _line in _ENV.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

app = Flask(__name__)
app.secret_key = os.getenv("FOREX_REMOTE_TOKEN") or secrets.token_hex(16)
_TZ = ZoneInfo("Europe/Istanbul")
_FEED = _DIR / "data" / "forex_analyst_feed.jsonl"
_REMOTE_TOKEN = (os.getenv("FOREX_REMOTE_TOKEN") or "").strip()


def _json_nocache(data, status=200):
    resp = jsonify(data)
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


def _token_ok() -> bool:
    if not _REMOTE_TOKEN:
        return True
    got = (request.headers.get("X-Forex-Remote") or "").strip()
    return bool(got) and secrets.compare_digest(got, _REMOTE_TOKEN)


@app.before_request
def _gate():
    path = request.path or ""
    if path.startswith("/forex/api/gpsusdt") or path.startswith("/forex/api/bin-b103"):
        return None
    if path.startswith("/poly/api/forex") or path.startswith("/forex/api"):
        if not _token_ok():
            return _json_nocache({"ok": False, "error": "unauthorized"}, 401)
    return None


def _gpsusdt_api_token_ok() -> bool:
    expected = (os.environ.get("GPSUSDT_API_TOKEN") or "").strip()
    if not expected:
        return False
    got = (
        request.headers.get("X-Gpsusdt-Token")
        or request.headers.get("X-Api-Token")
        or request.args.get("token")
        or ""
    ).strip()
    return bool(got) and secrets.compare_digest(got, expected)


def _bin_b103_api_token_ok() -> bool:
    expected = (
        (os.environ.get("BIN_B103_API_TOKEN") or "").strip()
        or (os.environ.get("GPSUSDT_API_TOKEN") or "").strip()
    )
    if not expected:
        return False
    got = (
        request.headers.get("X-Bin-B103-Token")
        or request.headers.get("X-Gpsusdt-Token")
        or request.headers.get("X-Api-Token")
        or request.args.get("token")
        or ""
    ).strip()
    return bool(got) and secrets.compare_digest(got, expected)


@app.route("/poly/api/forex/analyst/feed")
def api_forex_analyst_feed():
    entries = []
    if _FEED.exists():
        for line in _FEED.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    except ValueError:
        limit = 50
    entries = entries[-limit:][::-1]
    return jsonify({
        "ok": True,
        "count": len(entries),
        "entries": entries,
        "generated_at_tr": datetime.now(_TZ).isoformat(),
    })


@app.route("/poly/api/forex/spot")
@app.route("/forex/api/spot")
def api_forex_spot():
    tf = str(request.args.get("timeframe") or request.args.get("tf") or "1m")
    algo = str(request.args.get("algo") or "g1")
    if algo == "gps":
        from gpsusdt_data import gps_spot
        return _json_nocache(gps_spot(tf))
    if algo == "gps2":
        from gps2_data import gps_spot as gps2_spot
        return _json_nocache(gps2_spot(tf))
    if algo == "b103":
        from b103_data import forex_spot as b103_spot
        return _json_nocache(b103_spot(tf))
    if algo == "binb103":
        from bin_b103_data import live_spot as bin_b103_spot
        return _json_nocache(bin_b103_spot(tf))
    from forex_data import forex_spot
    return _json_nocache(forex_spot(tf, algo=algo))


@app.route("/poly/api/forex/chart")
@app.route("/forex/api/chart")
def api_forex_chart():
    from forex_data import forex_chart
    tf = str(request.args.get("timeframe") or request.args.get("tf") or "1m")
    try:
        lim = request.args.get("limit")
        lim = int(lim) if lim not in (None, "") else None
    except (TypeError, ValueError):
        lim = None
    try:
        plain = str(request.args.get("plain") or "") in ("1", "true", "yes")
        algo = str(request.args.get("algo") or "g1")
        if algo == "gps":
            from gpsusdt_data import gps_chart
            out = gps_chart(tf, lim or 240)
        elif algo == "gps2":
            from gps2_data import gps_chart as gps2_chart
            out = gps2_chart(tf, lim or 240)
        elif algo == "b103":
            from b103_data import forex_chart as b103_chart
            out = b103_chart(tf, limit=lim, plain=plain)
        elif algo == "binb103":
            from bin_b103_data import live_chart as bin_chart
            out = bin_chart(tf, lim or 240)
        else:
            out = forex_chart(tf, limit=lim, plain=plain, algo=algo)
        return _json_nocache(out)
    except Exception as e:
        return _json_nocache({
            "symbol": "XAUUSD", "timeframe": tf,
            "candles": [], "error": "chart_data", "detail": str(e)[:200],
        })


@app.route("/poly/api/forex/status")
def api_forex_status():
    from forex_book import snapshot
    from forex_data import forex_quote
    q = forex_quote()
    book = snapshot(q.get("bid"), q.get("ask"))
    return jsonify({
        "ok": True,
        "system": "forex",
        "label": "Forex",
        "status": "paper",
        "host": "coptc",
        "balance": book.get("equity", book.get("balance")),
        "open_count": book.get("open_count") or 0,
        "books": [book],
        "note": "CoptC · sanal $300 · $100×500x",
    })


@app.route("/poly/api/forex/gpsusdt")
def api_forex_gpsusdt():
    from gpsusdt_data import gps_chart
    tf = str(request.args.get("timeframe") or request.args.get("tf") or "1m")
    try:
        lim = int(request.args.get("limit") or 240)
    except (TypeError, ValueError):
        lim = 240
    return _json_nocache(gps_chart(tf, lim))


@app.route("/poly/api/forex/cem02/spot")
def api_forex_cem02_spot():
    tf = str(request.args.get("timeframe") or request.args.get("tf") or "1m")
    from cem02_data import forex_spot as cem02_spot
    return _json_nocache(cem02_spot(tf))


@app.route("/poly/api/forex/cem02/chart")
def api_forex_cem02_chart():
    tf = str(request.args.get("timeframe") or request.args.get("tf") or "1m")
    try:
        lim = request.args.get("limit")
        lim = int(lim) if lim not in (None, "") else None
    except (TypeError, ValueError):
        lim = None
    try:
        plain = str(request.args.get("plain") or "") in ("1", "true", "yes")
        from cem02_data import forex_chart as cem02_chart
        return _json_nocache(cem02_chart(tf, limit=lim, plain=plain))
    except Exception as e:
        return _json_nocache({
            "symbol": "XAUUSD", "timeframe": tf,
            "candles": [], "error": "chart_data", "detail": str(e)[:200],
        })


@app.route("/poly/api/forex/cem02/book")
def api_forex_cem02_book():
    try:
        from capital_api import configured, snapshot_book
        if configured():
            return _json_nocache(snapshot_book())
    except Exception as e:
        return _json_nocache({"ok": False, "error": str(e)[:200]})
    from cem02_book import snapshot as cem02_snapshot
    from cem02_data import forex_quote as cem02_quote
    q = cem02_quote()
    return _json_nocache(cem02_snapshot(q.get("bid"), q.get("ask")))


@app.route("/poly/api/forex/cem02/capital")
def api_forex_cem02_capital():
    from capital_api import status
    return _json_nocache(status())


@app.route("/poly/api/forex/openapi/spot")
def api_forex_openapi_spot():
    tf = str(request.args.get("timeframe") or request.args.get("tf") or "1m")
    from oapi_data import forex_spot as oapi_spot
    return _json_nocache(oapi_spot(tf))


@app.route("/poly/api/forex/openapi/chart")
def api_forex_openapi_chart():
    tf = str(request.args.get("timeframe") or request.args.get("tf") or "1m")
    try:
        lim = request.args.get("limit")
        lim = int(lim) if lim not in (None, "") else None
    except (TypeError, ValueError):
        lim = None
    try:
        plain = str(request.args.get("plain") or "") in ("1", "true", "yes")
        from oapi_data import forex_chart as oapi_chart
        return _json_nocache(oapi_chart(tf, limit=lim, plain=plain))
    except Exception as e:
        return _json_nocache({
            "symbol": "XAUUSD", "timeframe": tf,
            "candles": [], "error": "chart_data", "detail": str(e)[:200],
        })


@app.route("/poly/api/forex/openapi/book")
def api_forex_openapi_book():
    try:
        from ctrader_api import configured, snapshot_book
        if configured():
            return _json_nocache(snapshot_book())
    except Exception as e:
        return _json_nocache({"ok": False, "error": str(e)[:200]})
    from oapi_book import snapshot as oapi_snapshot
    from oapi_data import forex_quote as oapi_quote
    q = oapi_quote()
    return _json_nocache(oapi_snapshot(q.get("bid"), q.get("ask")))


@app.route("/poly/api/forex/openapi/status")
def api_forex_openapi_status():
    from ctrader_api import status
    return _json_nocache(status())


def _gpsusdt_api_payload() -> dict:
    from gpsusdt_book import snapshot as gps_snapshot
    from gpsusdt_data import gps_quote
    q = gps_quote()
    book = gps_snapshot(q.get("bid"), q.get("ask"))
    try:
        lim = int(request.args.get("limit") or 50)
    except (TypeError, ValueError):
        lim = 50
    lim = max(1, min(lim, 200))
    hist = list(book.get("history") or [])[:lim]
    live = book.get("live") or {}
    return {
        "ok": True,
        "book": "gps",
        "host": "coptc",
        "page": "/forex/gpsusdt/islemler",
        "symbol": book.get("symbol") or "GPSUSDT",
        "title": "GPSUSDT · CANLI Isolated",
        "venue": "binance_usdm",
        "margin": book.get("margin"),
        "leverage": book.get("leverage"),
        "margin_type": book.get("margin_type"),
        "equity": book.get("equity"),
        "balance": book.get("balance"),
        "wallet": book.get("wallet"),
        "available": book.get("available"),
        "used_margin": book.get("used_margin"),
        "init_balance": book.get("init_balance"),
        "total_pnl": book.get("total_pnl"),
        "float_pnl": book.get("float_pnl"),
        "started_at": book.get("started_at"),
        "trade_count": book.get("trade_count"),
        "open_count": book.get("open_count"),
        "last_dir": book.get("last_dir"),
        "last_reject": book.get("last_reject"),
        "night_quiet": book.get("night_quiet"),
        "night_window": book.get("night_window"),
        "live": {
            "enabled": live.get("enabled"),
            "paused": live.get("paused"),
            "configured": live.get("configured"),
            "symbol": live.get("symbol") or "GPSUSDT",
            "position": live.get("position"),
            "usdt_wallet": live.get("usdt_wallet"),
            "usdt_available": live.get("usdt_available"),
            "usdt_equity": live.get("usdt_equity"),
            "usdt_unrealized": live.get("usdt_unrealized"),
        },
        "positions": book.get("positions") or [],
        "history": hist,
        "history_n": len(book.get("history") or []),
        "costs": book.get("costs"),
        "bid": q.get("bid"),
        "ask": q.get("ask"),
        "mid": q.get("mid"),
        "ts": book.get("ts"),
    }


@app.route("/forex/api/gpsusdt")
@app.route("/forex/api/gpsusdt/")
@app.route("/forex/api/gpsusdt/islemler")
def api_forex_gpsusdt_token():
    if not (_token_ok() or _gpsusdt_api_token_ok()):
        return _json_nocache({"ok": False, "error": "unauthorized"}, 401)
    try:
        return _json_nocache(_gpsusdt_api_payload())
    except Exception as e:
        return _json_nocache({"ok": False, "error": str(e)[:200]}, 500)


def _bin_b103_api_payload() -> dict:
    from bin_b103_book import snapshot as bin_snapshot
    from bin_b103_data import live_quote as bin_quote
    q = bin_quote()
    book = bin_snapshot(q.get("bid"), q.get("ask"))
    try:
        lim = int(request.args.get("limit") or 50)
    except (TypeError, ValueError):
        lim = 50
    lim = max(1, min(lim, 200))
    hist = list(book.get("history") or [])[:lim]
    live = book.get("live") or {}
    eng = book.get("engine") or {}
    return {
        "ok": True,
        "book": "binb103",
        "host": "coptc",
        "page": "/forex/bin-b103/islemler",
        "symbol": book.get("symbol") or "XAUUSDT",
        "title": book.get("title") or "BIN_XAUUSDT",
        "venue": "binance_usdm",
        "engine": eng,
        "margin": book.get("margin"),
        "leverage": book.get("leverage"),
        "margin_type": book.get("margin_type"),
        "equity": book.get("equity"),
        "balance": book.get("balance"),
        "wallet": book.get("wallet"),
        "available": book.get("available"),
        "used_margin": book.get("used_margin"),
        "init_balance": book.get("init_balance"),
        "total_pnl": book.get("total_pnl"),
        "float_pnl": book.get("float_pnl"),
        "started_at": book.get("started_at"),
        "trade_count": book.get("trade_count"),
        "open_count": book.get("open_count"),
        "last_dir": book.get("last_dir"),
        "last_reject": book.get("last_reject"),
        "night_quiet": book.get("night_quiet"),
        "night_window": book.get("night_window"),
        "live": {
            "enabled": live.get("enabled"),
            "paused": live.get("paused"),
            "paper": live.get("paper"),
            "configured": live.get("configured"),
            "symbol": live.get("symbol") or "XAUUSDT",
            "position": live.get("position"),
            "usdt_wallet": live.get("usdt_wallet"),
            "usdt_available": live.get("usdt_available"),
            "usdt_equity": live.get("usdt_equity"),
            "usdt_unrealized": live.get("usdt_unrealized"),
        },
        "positions": book.get("positions") or [],
        "position": book.get("position"),
        "history": hist,
        "history_n": len(book.get("history") or []),
        "costs": book.get("costs"),
        "bid": q.get("bid"),
        "ask": q.get("ask"),
        "mid": q.get("mid"),
        "ts": book.get("ts"),
    }


@app.route("/forex/api/bin-b103")
@app.route("/forex/api/bin-b103/")
@app.route("/forex/api/bin-b103/islemler")
@app.route("/poly/api/forex/bin-b103")
def api_forex_bin_b103_token():
    if not (_token_ok() or _bin_b103_api_token_ok()):
        return _json_nocache({"ok": False, "error": "unauthorized"}, 401)
    try:
        return _json_nocache(_bin_b103_api_payload())
    except Exception as e:
        return _json_nocache({"ok": False, "error": str(e)[:200]}, 500)


@app.route("/poly/api/forex/bin-b103/live", methods=["GET", "POST"])
def api_forex_bin_b103_live():
    from bin_b103_binance import load_control, paper_mode, live_paused
    if request.method == "GET":
        c = load_control()
        paper = paper_mode()
        return _json_nocache({
            "ok": True,
            "live": (not paper) and (not live_paused()),
            "paper": paper,
            "paused": live_paused(),
            "control": c,
        })
    body = request.get_json(silent=True) or {}
    from bin_b103_book import switch_live
    if body.get("toggle"):
        want = paper_mode()
    elif "live" in body:
        want = bool(body.get("live"))
    elif "paused" in body or "live_paused" in body:
        want = not bool(body.get("paused", body.get("live_paused")))
    else:
        return _json_nocache({"ok": False, "error": "toggle veya live gerekli"}, 400)
    try:
        out = switch_live(want)
    except Exception as e:
        return _json_nocache({"ok": False, "error": str(e)[:200]}, 400)
    return _json_nocache(out)


@app.route("/poly/api/forex/bin-b103/engine", methods=["GET", "POST"])
def api_forex_bin_b103_engine():
    from bin_b103_signal import engine_info
    if request.method == "GET":
        info = engine_info()
        info["ok"] = True
        return _json_nocache(info)
    body = request.get_json(silent=True) or {}
    uid = str(body.get("uid") or body.get("engine") or "").strip().lower()
    if not uid:
        return _json_nocache({"ok": False, "error": "uid gerekli"}, 400)
    from bin_b103_book import switch_engine
    return _json_nocache(switch_engine(uid))


@app.route("/poly/api/forex/book")
def api_forex_book():
    algo = str(request.args.get("algo") or "g1")
    if algo == "gps":
        from gpsusdt_book import snapshot as gps_snapshot
        from gpsusdt_data import gps_quote
        q = gps_quote()
        return _json_nocache(gps_snapshot(q.get("bid"), q.get("ask")))
    if algo == "gps2":
        from gps2_book import snapshot as gps2_snapshot
        from gps2_data import gps_quote as gps2_quote
        q = gps2_quote()
        return _json_nocache(gps2_snapshot(q.get("bid"), q.get("ask")))
    if algo == "b103":
        from b103_book import snapshot as b103_snapshot
        from forex_data import forex_quote
        q = forex_quote()
        return _json_nocache(b103_snapshot(q.get("bid"), q.get("ask")))
    if algo == "binb103":
        from bin_b103_book import snapshot as bin_b103_snapshot
        from bin_b103_data import live_quote as bin_b103_quote
        try:
            q = bin_b103_quote()
        except Exception:
            q = {}
        return _json_nocache(bin_b103_snapshot(q.get("bid"), q.get("ask")))
    from forex_book import snapshot
    from forex_data import forex_quote
    q = forex_quote()
    return _json_nocache(snapshot(q.get("bid"), q.get("ask"), book=algo))


@app.route("/poly/api/forex/algo-books")
def api_forex_algo_books():
    from forex_data import forex_quote
    from fx_algo_book import snapshot_all
    q = forex_quote()

    def _f(v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    mark = _f(q.get("mid") or q.get("bid") or q.get("ask"))
    out = snapshot_all(mark, bid=_f(q.get("bid")), ask=_f(q.get("ask")))
    try:
        from bin_b103_signal import engine_info
        out["bin_engine"] = engine_info()
    except Exception:
        out["bin_engine"] = None
    out["host"] = "coptc"
    return _json_nocache(out)


@app.route("/poly/api/forex/algo-books/<uid>")
def api_forex_algo_book(uid):
    from fx_algo_book import snapshot
    from fx_algo_catalog import get_book
    book = get_book(uid)
    if not book:
        return _json_nocache({"ok": False, "error": "unknown_book"}, 404)
    from forex_data import forex_quote
    q = forex_quote()

    def _f(v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    mark = _f(q.get("mid") or q.get("bid") or q.get("ask"))
    return _json_nocache(snapshot(book["uid"], mark, bid=_f(q.get("bid")), ask=_f(q.get("ask"))))


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "forex", "host": "coptc"})


if __name__ == "__main__":
    host = os.getenv("FOREX_SERVER_HOST") or "127.0.0.1"
    port = int(os.getenv("FOREX_SERVER_PORT") or 5070)
    app.run(host=host, port=port, threaded=True)
