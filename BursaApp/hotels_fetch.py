#!/usr/bin/env python3
"""Enuygun MCP ile Bursa otel oda fiyatlarını günceller.

Kaynak: https://mcp.enuygun.com/mcp (hotel_search + hotel_room_detail)
Hedef: uploads/_enuygun_hotels_all.json + isteğe bağlı DB (--seed)

  python3 BursaApp/hotels_fetch.py
  python3 BursaApp/hotels_fetch.py --seed

Cron (İST 06:00 / 12:00 / 18:00 / 00:00 ≈ UTC 03:00 / 09:00 / 15:00 / 21:00):
  0 3,9,15,21 * * * cd /root/aiProject && python3 BursaApp/hotels_fetch.py --seed >> /tmp/hotels_fetch.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(_DIR, "uploads", "_enuygun_hotels_all.json")
META = os.path.join(_DIR, "data", "hotels_price_meta.json")
MCP_URL = "https://mcp.enuygun.com/mcp"
UA = "BursaApp/1.0 (https://bursaapp.com; hotel price sync)"
IST = ZoneInfo("Europe/Istanbul")
SLEEP_ROOM = 1.0
SLEEP_SEARCH = 0.5
MAX_RETRIES = 4


def _dates(offset_nights: int = 1) -> tuple[str, str]:
    base = datetime.now(IST).date() + timedelta(days=offset_nights)
    return base.strftime("%d.%m.%Y"), (base + timedelta(days=1)).strftime("%d.%m.%Y")


def _format_tl(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + " TL"


def _mcp_call(tool: str, arguments: dict, timeout: int = 90) -> dict:
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            body = json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}},
                ensure_ascii=False,
            ).encode()
            req = urllib.request.Request(
                MCP_URL,
                data=body,
                headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode())
            if resp.get("error"):
                raise RuntimeError(resp["error"])
            text = resp["result"]["content"][0]["text"]
            return json.loads(text)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt + 1 < MAX_RETRIES:
                wait = 8 * (attempt + 1)
                print(f"429 {tool} · {wait}s bekleniyor…", flush=True)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            last_err = e
            if attempt + 1 < MAX_RETRIES:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise last_err or RuntimeError("mcp call failed")


def _min_from_room_detail(payload: dict) -> tuple[int | None, str]:
    data = payload.get("data") or {}
    best = None
    best_room = ""
    for room in data.get("rooms") or []:
        rname = ((room.get("roomType") or {}).get("name") or "").strip()
        for offer in room.get("pricing") or []:
            if offer.get("saleable") is False:
                continue
            total = offer.get("total") or {}
            try:
                amt = int(float(str(total.get("amount") or "0").replace(",", ".")))
            except (TypeError, ValueError):
                continue
            if amt <= 0:
                continue
            if best is None or amt < best:
                best = amt
                best_room = rname
    return best, best_room


def _apply_price(hotel: dict, amount: int, check_in: str, check_out: str, room_name: str = "", source: str = "room") -> None:
    hotel["min_price"] = amount
    hotel["formatted_price"] = _format_tl(amount)
    hotel["currency"] = "TRY"
    hotel["price_fetched_at"] = datetime.now(IST).isoformat(timespec="seconds")
    hotel["price_check_in"] = check_in
    hotel["price_check_out"] = check_out
    hotel["price_source"] = source
    if room_name:
        hotel["price_room_from"] = room_name


def _is_bursa(h: dict) -> bool:
    city = (h.get("city") or "").strip().lower()
    if city and city not in ("bursa", "uludağ", "uludag"):
        return False
    blob = " ".join([h.get("name") or "", h.get("town") or "", city]).lower()
    return "yalova" not in blob


def _load_catalog() -> list[dict]:
    if not os.path.isfile(SRC):
        return []
    return json.load(open(SRC, encoding="utf-8"))


def _save_catalog(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    tmp = SRC + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SRC)


def fetch_search_prices(catalog_by_id: dict[str, dict], check_in: str, check_out: str) -> int:
    updated = 0
    page = 1
    while page <= 20:
        try:
            payload = _mcp_call(
                "hotel_search",
                {
                    "destination_name": "Bursa",
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "adults": 2,
                    "limit": 30,
                    "page": page,
                },
            )
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            print("search page fail", page, e, flush=True)
            break
        data = payload.get("data") or {}
        hotels = data.get("hotels") or []
        total = int(data.get("total_hotels") or 0)
        print(f"search p{page}: {len(hotels)} / total {total}", flush=True)
        if not hotels:
            break
        for h in hotels:
            if not _is_bursa(h):
                continue
            hid = str(h.get("id") or "")
            if not hid:
                continue
            try:
                amt = int(h.get("min_price") or 0)
            except (TypeError, ValueError):
                amt = 0
            if amt <= 0:
                continue
            row = catalog_by_id.get(hid)
            if row is None:
                row = dict(h)
                catalog_by_id[hid] = row
            else:
                for k, v in h.items():
                    if v not in (None, "", [], {}):
                        row[k] = v
            _apply_price(row, amt, check_in, check_out, source="search")
            updated += 1
        if total and page * 30 >= total:
            break
        page += 1
        time.sleep(SLEEP_SEARCH)
    return updated


def fetch_room_prices(catalog_by_id: dict[str, dict], check_in: str, check_out: str, limit: int = 0) -> tuple[int, int]:
    ids = sorted(catalog_by_id.keys(), key=lambda x: int(x))
    if limit > 0:
        ids = ids[:limit]
    pending = [hid for hid in ids if _is_bursa(catalog_by_id[hid])]
    updated_ids: set[str] = set()
    for pass_no in range(1, 3):
        if not pending:
            break
        retry: list[str] = []
        for i, hid in enumerate(pending, 1):
            row = catalog_by_id[hid]
            if row.get("price_check_in") == check_in and row.get("price_source") == "search" and row.get("min_price"):
                updated_ids.add(hid)
                continue
            if row.get("price_check_in") == check_in and row.get("min_price") and hid in updated_ids:
                continue
            try:
                payload = _mcp_call(
                    "hotel_room_detail",
                    {"hotel_id": int(hid), "check_in_date": check_in, "check_out_date": check_out, "adults": 2},
                    timeout=120,
                )
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError, urllib.error.HTTPError) as e:
                retry.append(hid)
                print(f"room fail p{pass_no} [{i}/{len(pending)}] {hid} · {e}", flush=True)
                time.sleep(SLEEP_ROOM * 2)
                continue
            if not payload.get("success"):
                retry.append(hid)
                time.sleep(SLEEP_ROOM)
                continue
            amt, room_name = _min_from_room_detail(payload)
            if amt is None:
                retry.append(hid)
                time.sleep(SLEEP_ROOM)
                continue
            _apply_price(row, amt, check_in, check_out, room_name)
            updated_ids.add(hid)
            if len(updated_ids) % 8 == 0 or i == len(pending):
                print(f"room ok {len(updated_ids)} · {row.get('name','')[:42]} · {_format_tl(amt)}", flush=True)
            time.sleep(SLEEP_ROOM)
        if retry and pass_no == 1:
            print(f"retry · {len(retry)} otel · 25s", flush=True)
            time.sleep(25)
        pending = retry
    failed = len(pending)
    return len(updated_ids), failed


def write_meta(check_in: str, check_out: str, search_n: int, room_n: int, failed: int, total: int) -> None:
    meta = {
        "fetched_at": datetime.now(IST).isoformat(timespec="seconds"),
        "check_in": check_in,
        "check_out": check_out,
        "search_updated": search_n,
        "room_updated": room_n,
        "failed": failed,
        "catalog_size": total,
        "note": "1 gece · 2 yetişkin · Enuygun MCP",
    }
    os.makedirs(os.path.dirname(META), exist_ok=True)
    with open(META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def run_seed() -> None:
    cmd = [sys.executable, os.path.join(_DIR, "seed_hotels_enuygun.py"), "--prices-only"]
    subprocess.run(cmd, check=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="Enuygun otel fiyat senkronu")
    ap.add_argument("--seed", action="store_true", help="Fetch sonrası DB fiyat güncelle")
    ap.add_argument("--no-search", action="store_true", help="Yalnız oda detayı")
    ap.add_argument("--no-room-detail", action="store_true", help="Yalnız arama")
    ap.add_argument("--limit", type=int, default=0, help="Oda detayı otel limiti (test)")
    ap.add_argument("--offset-nights", type=int, default=1, help="Giriş = bugün + N gece")
    args = ap.parse_args()

    check_in, check_out = _dates(args.offset_nights)
    print(f"dates {check_in} → {check_out}", flush=True)

    rows = _load_catalog()
    if not rows:
        print("missing catalog", SRC, flush=True)
        return 1
    by_id: dict[str, dict] = {str(h["id"]): h for h in rows if h.get("id")}

    search_n = 0
    if not args.no_search:
        search_n = fetch_search_prices(by_id, check_in, check_out)

    room_n = 0
    failed = 0
    if not args.no_room_detail:
        room_n, failed = fetch_room_prices(by_id, check_in, check_out, limit=args.limit)

    _save_catalog(list(by_id.values()))
    write_meta(check_in, check_out, search_n, room_n, failed, len(by_id))
    print(f"done search={search_n} room={room_n} fail={failed} catalog={len(by_id)}", flush=True)

    if args.seed:
        run_seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
