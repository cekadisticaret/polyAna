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
| `web/poly_dashboard.py` | Poly dashboard — yeni analizler harita sekmesine otomatik eklenir (`poly_trader_*_history.json`). |
| `temmuzPoly/` | Poly trader'lar, 5M 102/103, 6. Analiz; dashboard port **5050**. |
| `temmuzPoly/btc_5m_102_algo.py` | 5M 102 sinyal motoru (standalone, 4 algo + momentum; trader'dan bağımsız) |
| `temmuzPoly/btc_5m_104_algo.py` | 5M 104 gelişmiş sinyal motoru (5 algo + ADX/hacim/HTF filtreleri, ATR lot) |
| `temmuzPoly/btc_1h_analiz7_algo.py` | 7. Analiz 1H gelişmiş sinyal motoru (6 algo ≥3/6 + filtreler) |
| `temmuzPoly/poly_trader_analiz7.py` | 7. Analiz BTC 1H sanal ($500, $15/işlem) |
| `temmuzPoly/poly_trader_5m_btc_104.py` | 5M 104 BTC sanal trader ($200, UP $4 / DOWN $6, Telegram) |

**Test:** `python3 BistAnaliz/BistHourSinyal/bist_visual_v2.py --test` — örnek BIST Analiz metni.  
`python3 BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py --test` — örnek GÜÇLÜ AL metni (tarama/seans yok).

## Cron
- `BistAnaliz/BistHourSinyal/bist_visual_v2.py 1h` — `/tmp/bist_visual.log`
- `BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py` — `/tmp/bist_signal_hunter.log`
- `BistAnaliz/backup.py` — `/tmp/backup.log`
- `temmuzPoly/poly_trader.py close` — saat başı (`0 * * * *`): önceki saatin sonuçlarını kapatır
- `temmuzPoly/poly_trader.py open` — 5 geçe (`5 * * * *`): yeni tahmin + işlem açar
- `temmuzPoly/poly_trader_5m_btc_102.py open` — her 5 dk: 101 + momentum BTC **gerçek PM** (UP $4 / DOWN $6); 22:00–07:00 İST kapalı
- `temmuzPoly/poly_trader_5m_btc_103.py open` — her 5 dk: A10 çift konsensüs BTC+SOL sanal ($150/$6)
- `temmuzPoly/poly_trader_5m_btc_104.py open` — her 5 dk: 5-algo enhanced BTC sanal ($200, UP $4 / DOWN $6)
- `temmuzPoly/poly_trader_analiz6.py close/open` — saat başı / 5 geçe: RSI Div Katı BTC+SOL sanal ($500, lot $8–20)
- `temmuzPoly/poly_trader_analiz7.py close/open` — saat başı / 5 geçe: Enhanced 6-algo BTC 1H sanal ($500, $15)

## Sürekli Çalışan Servisler
- `polyManuel/sol_bot.py` — PID izle; log: `/tmp/sol_bot.log`; yeniden başlatmak için: `nohup python3 /root/aiProject/polyManuel/sol_bot.py > /tmp/sol_bot.log 2>&1 &`

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.
