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
| `web/poly_dashboard.py` | Poly dashboard — harita/geçmiş; port **5050**. |
| `temmuzPoly/` | Poly trader'lar; dashboard port **5050**. |
| `Analiz31/` | Multi-TF tahmin motoru (15m/1h/4h/1d, walk-forward backtest) |
| `Analiz31/main.py` | CLI — `--once`, `--loop`, `--backtest` |
| `Analiz31/predictor.py` | HTF bias + kill zone + crash kapısı tahmin motoru |
| `temmuzPoly/poly_trader_5m_common.py` | 5M BTC ortak yardımcılar (Binance, 4-algo, PM emir) |
| `temmuzPoly/btc_5m_105_algo.py` | 5M 105 sinyal motoru (4-algo + MR veto + Trend nötr band) |
| `temmuzPoly/btc_1h_analiz7_algo.py` | 7. Analiz 1H gelişmiş sinyal motoru (6 algo ≥3/6 + filtreler) |
| `temmuzPoly/pm_trader_helpers.py` | PM emir + sanal kotasyon; P&L = pm_size − pm_spent (2x fallback yok) |
| `temmuzPoly/btc_analiz1_algo.py` | 1. Analiz tam algoritma (standalone kopya, poly_predictor ile aynı) |
| `temmuzPoly/poly_trader_analiz1.py` | 1. Analiz sanal (BTC+SOL); PM gamma fiyatından gerçekçi P&L |
| `temmuzPoly/poly_trader_analiz2.py` | 2. Analiz sanal (SOL only; $300, $10-15-20; **24/7**) |
| `temmuzPoly/poly_trader_analiz4.py` | 4. Analiz sanal (BTC+ETH); PM gamma fiyatından gerçekçi P&L |
| `temmuzPoly/poly_analiz_dual_core.py` | 10/13 çift konsensüs ortak motor (A1+A4; TG yalnızca açılış/kapanış) |
| `temmuzPoly/poly_trader_analiz10.py` | 10. Analiz çift konsensüs sanal (BTC+SOL, $300, $10/işlem) |
| `temmuzPoly/poly_trader_analiz9.py` | 9. Analiz sanal (PASIF — `ANALIZ9_ENABLED=false`) |
| `temmuzPoly/poly_trader_analiz13.py` | 13. Analiz çift konsensüs sanal (B≥1/4, $10-15-20) |
| `temmuzPoly/btc_analiz21_algo.py` | 21. Analiz motoru — BTC RSI Div / ETH Volume Profile / SOL MACD Hist |
| `temmuzPoly/poly_trader_analiz21.py` | 21. Analiz sanal (BTC+ETH+SOL, $300, $12-16-20) |
| `temmuzPoly/poly_trader_5m_btc_105.py` | 5M 105 BTC sanal ($200, $8-12/işlem WR'ye göre; 8799859033 bot) |
| `temmuzPoly/poly_trader_5m_real_stats.py` | 5M 105 saatlik Telegram özeti (yalnızca gerçek PM açıkken) |
| `temmuzPoly/poly_trader_5m_btc_107.py` | 5M 107 BTC sanal — **PASIF** ($200, $8-12/işlem, 105+fren) |
| `temmuzPoly/algo_signals.py` | 39 saatlik algo sinyali (BTC/ETH/SOL); `/tmp/algo_signals.json` |

**Test:** `python3 BistAnaliz/BistHourSinyal/bist_visual_v2.py --test` — örnek BIST Analiz metni.  
`python3 BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py --test` — örnek GÜÇLÜ AL metni (tarama/seans yok).

## Cron
- `BistAnaliz/BistHourSinyal/bist_visual_v2.py 1h` — `/tmp/bist_visual.log`
- `BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py` — `/tmp/bist_signal_hunter.log`
- `BistAnaliz/backup.py` — `/tmp/backup.log`
- `temmuzPoly/poly_trader.py close` — saat başı (`0 * * * *`): önceki saatin sonuçlarını kapatır
- `temmuzPoly/poly_trader.py open` — 5 geçe (`5 * * * *`): yeni tahmin + işlem açar
- `temmuzPoly/poly_trader_5m_btc_105.py open` — her 5 dk: 105 BTC **sanal** ($200, $8-12/işlem); **24/7**
- `temmuzPoly/poly_trader_5m_btc_105.py weekly` — Pazar 00:00 haftalık 105 ısı haritası
- `temmuzPoly/poly_trader_analiz1.py close/open` — saat başı / **5 geçe**: 1. Analiz BTC+SOL **sanal** ($300)
- `temmuzPoly/poly_trader_analiz1.py weekly` — Cumartesi 21:00 haftalık 1 ısı haritası
- `temmuzPoly/poly_trader_analiz2.py close/open` — saat başı / **5 geçe**: 2. Analiz **SOL only** sanal ($300, $10-15-20); **24/7**; açılışta stake düşülür
- `temmuzPoly/poly_trader_analiz2.py weekly` — Cumartesi 21:00 haftalık 2 ısı haritası
- `temmuzPoly/poly_trader_analiz4.py close/open` — saat başı / **5 geçe**: 4. Analiz çoklu-algo **sanal** (BTC+ETH)
- `temmuzPoly/poly_trader_analiz10.py close/open` — saat başı / **5 geçe**: çift konsensüs **sanal** ($300, $10/işlem)
- `temmuzPoly/poly_trader_analiz10.py weekly` — Cumartesi 21:00 haftalık 10 ısı haritası
- `temmuzPoly/poly_trader_analiz13.py close/open` — saat başı / **5 geçe**: çift konsensüs B≥1/4 **sanal** ($300, $10-15-20)
- `temmuzPoly/poly_trader_analiz13.py weekly` — Pazar 21:00 haftalık 13 ısı haritası
- `temmuzPoly/poly_trader_analiz31.py close/open` — saat başı / **5 geçe**: 31. Analiz Multi-TF MR **sanal** ($300, $12-16-20)
- `temmuzPoly/poly_trader_analiz31.py weekly` — Cumartesi 21:00 haftalık 31 ısı haritası
- `temmuzPoly/poly_trader_analiz21.py close/open` — saat başı / **5 geçe**: 21. Analiz sembol-algo **sanal** ($300, $12-16-20)
- `temmuzPoly/poly_trader_analiz21.py weekly` — Cumartesi 21:00 haftalık 21 ısı haritası
- `temmuzPoly/poly_trader_analiz5.py close/open` — saat başı / **5 geçe**: A1 motoru BTC+SOL **gerçek PM** ($6–12/işlem WR'ye göre)
- `temmuzPoly/poly_trader_analiz7.py close/open` — saat başı / 5 geçe: Enhanced 6-algo BTC 1H sanal ($500, $15)
- `temmuzPoly/algo_signals.py` — `:05` her saat: 39 algo sinyali → `/tmp/algo_signals.json`
# KALDIRILDI: `temmuzPoly/btc_analiz_hourly.py` — 12. Analiz Algoritma (509 sanal)
# PASIF: `temmuzPoly/poly_trader_analiz9.py close/open/weekly` — 9. Analiz sanal (`ANALIZ9_ENABLED=false`)
# PASIF: `temmuzPoly/poly_trader_5m_btc_107.py open/weekly` — 5M 107 BTC sanal

## Sürekli Çalışan Servisler
- `polyManuel/sol_bot.py` — PID izle; log: `/tmp/sol_bot.log`; yeniden başlatmak için: `nohup python3 /root/aiProject/polyManuel/sol_bot.py > /tmp/sol_bot.log 2>&1 &`

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.

**Poly analiz TG kuralı:** Tüm analizlerde Telegram yalnızca gerçek açılış veya kapanışta gider; “pozisyon yok / sinyal yok / skip / önizleme” log’a yazılır.
