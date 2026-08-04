# Saatlik slot arşivi (A1/A2/A4/A6/A10/A15 + A2 Top17)

| Dosya | İçerik |
|---|---|
| `latest.json` | Son snapshot (7g + 30g slot/WR/PnL) |
| `daily/YYYY-MM-DD.json` | Günlük kopya |
| `hourly/YYYY-MM-DD_HH.json` | Saatlik kopya |
| `force_hot_latest.json` | WR>%85 saatler (kitap bazlı) |
| `events.jsonl` | Append-only işlem olayları |

Üretici: `python3 temmuzPoly/slot_data_archive.py`  
Cron: her saat `:15` UTC
