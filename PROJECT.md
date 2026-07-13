# aiProject — Proje Yapısı

## Genel Bakış
BIST Telegram betikleri `BistAnaliz/` altında. Ortak motor: `BistAnaliz/bist_scanner.py`. Gizli ayar proje kökünde: `telegram_config.py` (şablon: `BistAnaliz/telegram_config.example.py`).

| Klasör | Açıklama |
|---|---|
| `BistAnaliz/` | `bist_scanner.py`, `backup.py`, Telegram şablonu; alt klasörlerde saatlik ve güçlü AL betikleri. |
| `BistAnaliz/BistHourSinyal/` | `bist_visual_v2.py` — trend + momentum metin bildirimi. |
| `BistAnaliz/BistYapayAnaliz/` | `bist_signal_hunter.py` — 15m/1h güçlü AL; geçmiş: `bist_signal_hunter_history.json`. |
| `BistAnaliz/yuzdeBist.py` | BIST 5dk güven tarayıcı — RSI/EMA/MACD/Momentum/Hacim skorlaması (maks 100), sinyal ≥ %50 tetikler; Telegram entegrasyonu hazır (TODO). |
| `polyManuel/` | `sol_bot.py` — SOL/USDT 1m Binance verisiyle 5dk tahmin botu; RSI/EMA/MACD/Momentum analizi, Telegram bildirimi. |
| `web/poly_dashboard.py` | Poly dashboard — overview, `/gecmis` işlem geçmişi, harita, analizler, ayarlar. |
| `temmuzPoly/` | Polymarket trader sistemleri. Aktif coinler: BTC, ETH, SOL. `301` (1h sanal MACD Hist Div), `analiz5`/`analiz10` (1h gerçek PM), `5M 101` (gerçek PM BTC $3/5dk), `5M 106` sanal (RSI Div+Markov), `5M 107` sanal (RSI Div #5), `5M 201/202` pasif. PM min bakiye: $80. |

**Test:** `python3 BistAnaliz/BistHourSinyal/bist_visual_v2.py --test` — örnek BIST Analiz metni.  
`python3 BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py --test` — örnek GÜÇLÜ AL metni (tarama/seans yok).

## Cron
- `BistAnaliz/BistHourSinyal/bist_visual_v2.py 1h` — `/tmp/bist_visual.log`
- `BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py` — `/tmp/bist_signal_hunter.log`
- `BistAnaliz/backup.py` — `/tmp/backup.log`
- `temmuzPoly/poly_trader.py close` — saat başı (`0 * * * *`): önceki saatin sonuçlarını kapatır
- `temmuzPoly/poly_trader.py open` — 5 geçe (`5 * * * *`): yeni tahmin + işlem açar
- `temmuzPoly/poly_trader_5m_real_stats.py` — saat başı (`0 * * * *`): 5M 201+202 birleşik özet Telegram
- `temmuzPoly/poly_trader_301.py close/open` — saat başı / 5 geçe: MACD Hist Div sanal trader
- `temmuzPoly/poly_trader_5m_btc_106.py open` — her 5 dk: RSI Div + Markov BTC sanal trader
- `temmuzPoly/poly_trader_5m_btc_107.py open` — her 5 dk: RSI Div (#5) BTC sanal trader

## Sürekli Çalışan Servisler
- `polyManuel/sol_bot.py` — PID izle; log: `/tmp/sol_bot.log`; yeniden başlatmak için: `nohup python3 /root/aiProject/polyManuel/sol_bot.py > /tmp/sol_bot.log 2>&1 &`

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.
