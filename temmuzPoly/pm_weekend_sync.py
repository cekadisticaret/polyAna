"""Hafta sonu PM dashboard senkronu — Cuma 22:00 kapat / Pazartesi 08:00 aç (İST).

pm_system_control.json güncellenir; dashboard butonları bir sonraki yenilemede uyumlu olur.
Manuel aç/kapat her zaman mümkün — cron yalnızca tek seferlik tetiklenir.
"""
from __future__ import annotations

import sys

from pm_balance_guard import get_pm_system_control, weekend_pause_all, weekend_resume_all


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode == "close":
        state = weekend_pause_all()
        print("[PM WEEKEND] Cuma 22:00 — sistemler kapatildi (A1 Live + A2 + A8 Live + 210)")
    elif mode == "open":
        state = weekend_resume_all()
        print("[PM WEEKEND] Pazartesi 08:00 — sistemler acildi")
    elif mode == "status":
        state = get_pm_system_control()
        print("[PM WEEKEND] durum:", state)
        return
    else:
        print(f"Bilinmeyen mod: {mode} (close/open/status)")
        sys.exit(1)
    print(
        f"  analiz5={state['analiz5_paused']} "
        f"analiz2={state['analiz2_paused']} "
        f"analiz8={state.get('analiz8_paused')} "
        f"210={state['m15_210_paused']} "
        f"by={state.get('updated_by')}"
    )


if __name__ == "__main__":
    main()
