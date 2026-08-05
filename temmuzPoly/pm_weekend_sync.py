"""Hafta sonu PM dashboard senkronu (İST).

Cuma 22:00 kapat · Pzt 11:00 erken aç (A6/A2#16/A15) · Pzt 12:00 A1/A2/A10 aç.
Manuel aç/kapat her zaman mümkün — cron yalnızca tek seferlik tetiklenir.
"""
from __future__ import annotations

import sys

from pm_balance_guard import (
    get_pm_system_control,
    weekend_pause_all,
    weekend_resume_all,
    weekend_resume_early,
    weekend_resume_a1a2a10,
)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode == "close":
        state = weekend_pause_all()
        print("[PM WEEKEND] Cuma 22:00 — sistemler kapatildi")
    elif mode in ("open", "open_early"):
        # Pzt 11:00 — A1/A2/A10 kapalı kalır (12:00'e kadar)
        state = weekend_resume_early()
        print("[PM WEEKEND] Pazartesi 11:00 — erken acilis (A1/A2/A10 haric)")
    elif mode in ("open_a1a2a10", "open_late"):
        state = weekend_resume_a1a2a10()
        print("[PM WEEKEND] Pazartesi 12:00 — A1/A2/A10 acildi")
    elif mode == "open_all":
        state = weekend_resume_all()
        print("[PM WEEKEND] tum weekend gruplari acildi")
    elif mode == "status":
        state = get_pm_system_control()
        print("[PM WEEKEND] durum:", state)
        return
    else:
        print(f"Bilinmeyen mod: {mode} (close/open/open_a1a2a10/open_all/status)")
        sys.exit(1)
    print(
        f"  analiz5={state['analiz5_paused']} "
        f"analiz2={state['analiz2_paused']} "
        f"analiz10={state.get('analiz10_paused')} "
        f"analiz6_live={state.get('analiz6_live_paused')} "
        f"by={state.get('updated_by')}"
    )


if __name__ == "__main__":
    main()
