# Polymarket Analyzer

Quantitative prediction market analizi. Polymarket'ten filtreli market çeker, Grok LLM ile fırsat tespit eder, simüle işlem loglar ve Telegram bildirir. **Gerçek işlem yapılmaz.**

## Yapı

- **Polymarket Gamma API**: Filtreli market çekme (24h resolution, volume>10k, liquidity>5k, spread<4%)
- **xAI Grok**: Quantitative analiz (mispricing, edge, trade direction)
- **SQLite**: İşlem logu ve resolution takibi
- **Telegram**: Bildirimler (analiz önerileri + resolution özeti)

## Filtreler

- `resolution_time` < 24 saat
- `volume` > 10.000 $
- `liquidity` > 5.000 $
- `spread` < 4%

## Çalışma Saatleri

Saat başı `open`, 5. dakikada `resolve` — iki cron satırı; ayrıntı `cron.example`.

## Kurulum

```bash
pip install -r requirements.txt
cp .env.example .env
# .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, XAI_API_KEY
```

## Çalıştırma

```bash
# Tek seferlik (varsayılan: open)
python -m src.main open

# Cron — tam satırlar için `cron.example`
crontab -e
```

## Çıktılar

- `data/trades.db` – Simüle işlemler ve resolution durumu
- `data/logs/analysis.log` – Analiz geçmişi
- Telegram – Yeni analiz bildirimi + resolution özeti

## API Güvenliği

Tüm anahtarlar `.env` içinde. `POLYMARKET_PRIVATE_KEY` ileride gerçek işlem için kullanılacak.
