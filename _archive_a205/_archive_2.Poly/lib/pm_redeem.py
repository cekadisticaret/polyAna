#!/usr/bin/env python3
"""Polymarket kazanan pozisyonları otomatik redeem — pUSD'ye çevir."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any

_PM_HEADERS = {"User-Agent": "2.Poly", "Accept": "application/json"}


def _fetch_redeemable(funder: str) -> list[dict[str, Any]]:
    url = (
        "https://data-api.polymarket.com/positions"
        f"?user={funder}&redeemable=true&sizeThreshold=0"
    )
    req = urllib.request.Request(url, headers=_PM_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        rows = json.loads(r.read().decode())
    out = []
    for p in rows if isinstance(rows, list) else []:
        size = float(p.get("size") or 0)
        value = float(p.get("currentValue") or 0)
        if size <= 0 or value <= 0.01:
            continue
        out.append(p)
    return out


def _secure_client():
    from polymarket import RelayerApiKey, SecureClient

    pk = os.getenv("POLY_PRIVATE_KEY", "")
    wallet = os.getenv("POLY_FUNDER", "")
    rel_key = os.getenv("RELAYER_API_KEY", "")
    rel_addr = os.getenv("RELAYER_API_KEY_ADDRESS", "") or os.getenv("POLY_SIGNER_ADDRESS", "")
    if not all([pk, wallet, rel_key, rel_addr]):
        raise RuntimeError("POLY_PRIVATE_KEY, POLY_FUNDER, RELAYER_API_KEY, RELAYER_API_KEY_ADDRESS gerekli")
    return SecureClient.create(
        private_key=pk,
        wallet=wallet,
        api_key=RelayerApiKey(key=rel_key, address=rel_addr),
    )


def redeem_all(*, dry_run: bool = False) -> dict[str, Any]:
    """Redeem bekleyen kazanan pozisyonları nakde çevir."""
    funder = os.getenv("POLY_FUNDER", "")
    if not funder:
        return {"ok": False, "error": "POLY_FUNDER yok", "redeemed": 0}

    positions = _fetch_redeemable(funder)
    total_value = round(sum(float(p.get("currentValue") or 0) for p in positions), 2)
    if not positions:
        return {"ok": True, "redeemed": 0, "total_value": 0.0, "items": []}

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "redeemed": 0,
            "pending": len(positions),
            "total_value": total_value,
            "items": [
                {"title": p.get("title", ""), "value": round(float(p.get("currentValue") or 0), 2)}
                for p in positions
            ],
        }

    client = _secure_client()
    redeemed = []
    failed = []
    for pos in positions:
        cid = pos.get("conditionId") or pos.get("condition_id") or ""
        title = (pos.get("title") or cid[:12])[:60]
        value = round(float(pos.get("currentValue") or 0), 2)
        if not cid:
            failed.append({"title": title, "error": "conditionId yok"})
            continue
        try:
            tx = client.redeem_positions(condition_id=cid)
            tx.wait()
            redeemed.append({"title": title, "value": value, "condition_id": cid})
            print(f"[PM redeem] OK {title} +${value:.2f}", file=sys.stderr)
        except Exception as e:
            err = str(e)
            failed.append({"title": title, "error": err})
            print(f"[PM redeem] FAIL {title}: {err}", file=sys.stderr)

    return {
        "ok": len(failed) == 0,
        "redeemed": len(redeemed),
        "failed": len(failed),
        "total_value": round(sum(x["value"] for x in redeemed), 2),
        "items": redeemed,
        "errors": failed,
    }


def main() -> int:
    from bootstrap import init

    init()
    dry = "--dry-run" in sys.argv or os.getenv("POLY_DRY_RUN", "").lower() == "true"
    result = redeem_all(dry_run=dry)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
