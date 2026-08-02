# Kritik dosya silinme / geri yükleme kaydı

Son güncelleme: 2026-08-02 13:30 İST

## Olay özeti (2026-08-02)

Tracked kaynak dosyaları (`*.py`, `PROJECT.md`, cron rules) working tree’den silindi;
git HEAD’de duruyorlardı (commit edilmemiş `D`). Runtime JSON’lar genelde kaldı.
Faili yapan komut / agent transcript’te net `rm`/`Delete` bulunamadı.

| Aralık (İST) | Ne |
|---|---|
| **03:03** | Gece yedeği `backups/aiProject_20260801_2359.tar.gz` — kaynaklar **hâlâ var** |
| **03:03 – 09:11** | Silinme penceresi (kim/ne bilinmiyor) |
| **09:11** | Hafta sonu reset işi başında Agustos kaynakları eksik bulundu |
| **09:17** | **Geri dönüş #1** — Agustos + docs `git checkout HEAD -- …` |
| **09:23** | **Geri dönüş #1b** — `web/poly_dashboard.py` yeniden kaybolmuştu → git’ten restore |
| **13:25** | **Geri dönüş #2** — `pm_balance_guard.py` / `pm_orphan_sync.py` / diğer temmuzPoly `.py` → git’ten restore (overview `/poly/api/data` 500 sebebi) |

### Geri dönüş #1 — ~09:17 İST (06:17 UTC)

`git checkout HEAD --` ile:

- `AgustosKripto/virtual_book.py` (+ atr, binance client, cr6, trader, fee_utils, …)
- `AgustosKripto/Algoritmalar/{runner,catalog}.py`
- `AgustosKripto/Analizler/{runner,signals}.py`
- `PROJECT.md`, `.cursor/rules/cron-and-ops.mdc`

Dosya mtime doğrulama: `virtual_book.py` → **2026-08-02 06:17:47 UTC** (= 09:17 İST).

### Geri dönüş #1b — ~09:23 İST (06:23 UTC)

- `web/poly_dashboard.py` → `git checkout HEAD -- web/poly_dashboard.py`
- mtime: **2026-08-02 06:23:07 UTC** (= 09:23 İST)

### Geri dönüş #2 — ~13:25 İST (10:25 UTC)

Overview boş / `ModuleNotFoundError: pm_balance_guard` sonrası:

- `temmuzPoly/pm_balance_guard.py`
- `temmuzPoly/pm_orphan_sync.py`
- `temmuzPoly/pm_trader_helpers.py`
- diğer silinen `temmuzPoly/*.py` (15m/a2/110/analiz6/15 …)

mtime: `pm_balance_guard.py` → **2026-08-02 10:25:55 UTC** (= 13:25 İST).

## İzleme (bundan sonra)

- Script: `scripts/watch_critical_files.py` (inotify)
- Unit: `aiproject-file-watch.service` — kurulum: `bash ops/install_file_watch.sh`
- Sürekli log: `tail -f /tmp/aiproject_file_watch.log`
- **Olay kayıtları (silinme/eksik):** `ops/incidents/incident_*.json` (+ `.txt` özet)
  - İçerik: process listesi (pid/ppid/exe/cmd), `git status` D satırları, auditd (varsa), who/last, dashboard log tail
- auditd kuralları: `ops/aiproject-del.rules` (key=`aiproject_del`) — silen pid/exe için
  - Sorgu: `ausearch -k aiproject_del -ts recent -i`
- Heartbeat: 60 sn’de kritik dosya yoksa `MISSING` incident
- İzleyici ilk kez: **2026-08-02 13:32 İST**; incident kaydı güçlendirildi: **2026-08-02 ~13:45 İST**
