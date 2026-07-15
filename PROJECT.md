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
| `web/poly_dashboard.py` | Poly dashboard — harita/geçmiş; `analiz509` → `btc_analiz_509_history.json`. |
| `temmuzPoly/` | Poly trader'lar, 5M 102/105/106; dashboard port **5050**. |
| `temmuzPoly/poly_trader_15m_btc.py` | 5M 101 BTC sanal trader (4-algo ≥2/4, $200, $3/işlem) |
| `temmuzPoly/kalem_filters_102.py` | KALEM deneysel filtreler (102: fitil + seri dinlenme) |
| `temmuzPoly/btc_5m_102_algo.py` | 5M 102 sinyal motoru (standalone, 4 algo; trader'dan bağımsız) |
| `temmuzPoly/btc_5m_105_algo.py` | 5M 105 sinyal motoru (102 + MR veto + Trend nötr band) |
| `temmuzPoly/btc_5m_106_algo.py` | 5M 106 sinyal motoru (102 + yalnızca MR veto; trend nötr/KALEM yok) |
| `temmuzPoly/btc_1h_analiz7_algo.py` | 7. Analiz 1H gelişmiş sinyal motoru (6 algo ≥3/6 + filtreler) |
| `temmuzPoly/pm_trader_helpers.py` | PM emir + sanal kotasyon; P&L = pm_size − pm_spent (2x fallback yok) |
| `temmuzPoly/btc_analiz1_algo.py` | 1. Analiz tam algoritma (standalone kopya, poly_predictor ile aynı) |
| `temmuzPoly/poly_trader_analiz1.py` | 1. Analiz sanal (BTC+SOL); PM gamma fiyatından gerçekçi P&L |
| `temmuzPoly/poly_trader_analiz2.py` | 2. Analiz sanal ($300, $10-15-20; ABD açık=A1, kapalı=yedek sinyal) |
| `temmuzPoly/poly_trader_analiz4.py` | 4. Analiz sanal (BTC+ETH); PM gamma fiyatından gerçekçi P&L |
| `temmuzPoly/poly_analiz_dual_core.py` | 10/13 çift konsensüs ortak motor (A1+A4, elenme TG) |
| `temmuzPoly/poly_trader_analiz10.py` | 10. Analiz çift konsensüs sanal (BTC+SOL, $300, $10/işlem, elenme TG) |
| `temmuzPoly/poly_trader_analiz13.py` | 13. Analiz çift konsensüs sanal (B≥2/4, $10-15-20, elenme TG) |
| `temmuzPoly/poly_trader_5m_btc_102.py` | 5M 102 BTC sanal (8256912678 bot, UP $4 / DOWN $6) |
| `temmuzPoly/poly_trader_5m_real_stats.py` | 5M 102/105 saatlik Telegram özeti (8799859033) |
| `temmuzPoly/poly_trader_5m_btc_105.py` | 5M 105 BTC gerçek PM ($2/işlem, 8799859033 bot) |
| `temmuzPoly/poly_trader_5m_btc_106.py` | 5M 106 BTC sanal ($200, UP $4 / DOWN $6, MR veto, 102 bot) |
| `temmuzPoly/algo_signals.py` | 39 saatlik algo sinyali (BTC/ETH/SOL); `/tmp/algo_signals.json` |
| `temmuzPoly/btc_analiz_hourly.py` | 12. Analiz Algoritma — 27 oy özeti (:01) + Analiz 509 sanal (:02) |

**Test:** `python3 BistAnaliz/BistHourSinyal/bist_visual_v2.py --test` — örnek BIST Analiz metni.  
`python3 BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py --test` — örnek GÜÇLÜ AL metni (tarama/seans yok).

## Cron
- `BistAnaliz/BistHourSinyal/bist_visual_v2.py 1h` — `/tmp/bist_visual.log`
- `BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py` — `/tmp/bist_signal_hunter.log`
- `BistAnaliz/backup.py` — `/tmp/backup.log`
- `temmuzPoly/poly_trader.py close` — saat başı (`0 * * * *`): önceki saatin sonuçlarını kapatır
- `temmuzPoly/poly_trader.py open` — 5 geçe (`5 * * * *`): yeni tahmin + işlem açar
# PASIF: `temmuzPoly/poly_trader_15m_btc.py open/weekly` — 5M 101 BTC sanal ($3/işlem)
- `temmuzPoly/poly_trader_5m_btc_102.py open` — her 5 dk: 101 + KALEM BTC **sanal** ($200, UP $4 / DOWN $6); 22:00–07:00 İST kapalı
- `temmuzPoly/poly_trader_5m_btc_105.py open` — her 5 dk: 105 BTC **gerçek PM** ($2/işlem); 22:00–07:00 İST kapalı
- `temmuzPoly/poly_trader_5m_btc_105.py weekly` — Pazar 00:00 haftalık 105 ısı haritası
- `temmuzPoly/poly_trader_5m_real_stats.py` — saat başı: 5M 102 + 105 saatlik Telegram özeti (8799859033)
- `temmuzPoly/poly_trader_5m_btc_106.py open` — her 5 dk: 106 BTC **sanal** ($200, UP $4 / DOWN $6, MR veto); 22:00–07:00 İST kapalı
- `temmuzPoly/poly_trader_5m_btc_106.py weekly` — Pazar 00:00 haftalık 106 ısı haritası
- `temmuzPoly/poly_trader_analiz1.py close/open` — saat başı / 5 geçe: 1. Analiz BTC+SOL **sanal** ($300)
- `temmuzPoly/poly_trader_analiz1.py weekly` — Cumartesi 21:00 haftalık 1 ısı haritası
- `temmuzPoly/poly_trader_analiz2.py close/open` — saat başı / 5 geçe: 2. Analiz BTC+SOL **sanal** ($300, $10-15-20)
- `temmuzPoly/poly_trader_analiz2.py weekly` — Cumartesi 21:00 haftalık 2 ısı haritası
- `temmuzPoly/poly_trader_analiz13.py close/open` — saat başı / 3 geçe: çift konsensüs B≥2/4 **sanal** ($300, $10-15-20, elenme TG)
- `temmuzPoly/poly_trader_analiz13.py weekly` — Pazar 21:00 haftalık 13 ısı haritası
- `temmuzPoly/poly_trader_analiz5.py close/open` — saat başı / 5 geçe: A1 motoru BTC+SOL **gerçek PM** ($8/işlem)
- `temmuzPoly/poly_trader_analiz7.py close/open` — saat başı / 5 geçe: Enhanced 6-algo BTC 1H sanal ($500, $15)
- `temmuzPoly/algo_signals.py` — `:05` her saat: 39 algo sinyali → `/tmp/algo_signals.json`
- `temmuzPoly/btc_analiz_hourly.py` — `:01` analiz/Telegram, `:02` Analiz 509 sanal açılış → karisim1 kanalı

## Sürekli Çalışan Servisler
- `polyManuel/sol_bot.py` — PID izle; log: `/tmp/sol_bot.log`; yeniden başlatmak için: `nohup python3 /root/aiProject/polyManuel/sol_bot.py > /tmp/sol_bot.log 2>&1 &`

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.
