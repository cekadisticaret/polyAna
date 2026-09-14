# 2.Poly — bağımsız A2#05 Mean Reversion

Bu proje **temmuzPoly / diğer sunucuya bağlı değildir**. Tüm kod `lib/` içinde.

## Ne yapar
- Saatlik Mean Reversion (Z-Score) sinyali → BTC/ETH/SOL
- Sanal defter (`run_sanal.py`)
- Opsiyonel gerçek PM mirror (`run_live.py`, varsayılan **kapalı**)

## Kurulum
```bash
cd /root/aiProject/2.Poly
cp config/env.example .env
# .env doldur (live için POLY_PRIVATE_KEY / POLY_FUNDER)
pip3 install -r requirements.txt
chmod +x bin/*.sh
./bin/signals.sh
```

## Cron
`crontab.example` satırlarını `crontab -e` ile ekle.

## Live
`config/pm_system_control.json` → `a2_05_live_paused: true` (varsayılan).
Açmak: paused=false **ve** `PM_A2_05_LIVE_ENABLED=true`.
