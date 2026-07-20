# aiProject — Proje Yapısı

## Genel Bakış
BIST Telegram betikleri `BistAnaliz/` altında. Ortak motor: `BistAnaliz/bist_scanner.py`. Gizli ayar proje kökünde: `telegram_config.py` (şablon: `BistAnaliz/telegram_config.example.py`).

| Klasör | Açıklama |
|---|---|
| `BistAnaliz/` | `bist_scanner.py`, `backup.py`, Telegram şablonu; alt klasörlerde saatlik ve güçlü AL betikleri. |
| `BistAnaliz/BistHourSinyal/` | `bist_visual_v2.py` — trend + momentum metin bildirimi. |
| `BistAnaliz/BistYapayAnaliz/` | `bist_signal_hunter.py` — 15m/1h güçlü AL; geçmiş: `bist_signal_hunter_history.json`. |
| `BistAnaliz/yuzdeBist.py` | BIST 5dk güven tarayıcı — **PASIF** (crontab yorum satırı). |
| `web/poly_dashboard.py` | Poly dashboard — harita/geçmiş; port **5050**. |
| `temmuzPoly/` | Poly trader'lar, algo motorları, backtest; dashboard port **5050**. |
| `Analiz31/` | Multi-TF tahmin motoru (15m/1h/4h/1d, walk-forward backtest) |
| `Analiz31/main.py` | CLI — `--once`, `--loop`, `--backtest` |
| `Analiz31/predictor.py` | HTF bias + trend rejimi + SOL filtresi + gate 75 tahmin motoru (**v1.2**) |
| `Analiz31/guncelleme101/` | v1.1 yama staging (PATCH_NOTES + config/predictor/scorer kopyası) |
| `Analiz32/` | FeatureEngine v2 indikatör kütüphanesi + trader adaptörü |
| `Analiz32/predictor.py` | composite_signal → UP/DOWN (gate ±15; algo kütüphanesine dokunmaz) |
| `temmuzPoly/poly_trader_analiz32.py` | 32. Analiz sanal (**SOL only**, $300, $12-16-20) |
| `temmuzPoly/poly_predictor_analysis.py` | A1/A2/A5/dual ortak `predict` motoru |
| `temmuzPoly/poly_trader_5m_common.py` | 5M BTC ortak yardımcılar (Binance, 4-algo, PM emir) |
| `temmuzPoly/btc_5m_105_algo.py` | 5M ortak sinyal motoru (107 + 15M adaptörleri; 4-algo + MR veto) |
| `temmuzPoly/btc_1h_analiz7_algo.py` | 7. Analiz 1H gelişmiş sinyal motoru (6 algo ≥2/6, momentum kapalı) |
| `temmuzPoly/pm_trader_helpers.py` | PM emir + sanal kotasyon; P&L = pm_size − pm_spent (2x fallback yok) |
| `temmuzPoly/btc_analiz1_algo.py` | 1. Analiz tam algoritma (standalone kopya, poly_predictor ile aynı) |
| `temmuzPoly/poly_trader_analiz1.py` | 1. Analiz sanal (BTC+SOL); Cum 22:00–Paz 22:00 İST duraklama |
| `temmuzPoly/poly_trader_analiz2.py` | 2. Analiz sanal (SOL only; $300; **ALLOW_FALLBACK=False**) |
| `temmuzPoly/backtest_common.py` | 1Y walk-forward backtest ortak yardımcılar |
| `temmuzPoly/backtest_analiz2.py` | 2. Analiz 1Y walk-forward backtest (SOL, predict motoru) |
| `temmuzPoly/backtest_analiz1.py` | 1. Analiz 1Y walk-forward backtest (BTC+SOL, predict motoru) |
| `temmuzPoly/backtest_analiz_suite.py` | 4/10/21. Analiz 1Y backtest ($1000, algo import — canlıya dokunmaz) |
| `temmuzPoly/backtest_analiz31.py` | 31. Analiz 1Y Multi-TF backtest (BTC+SOL, v1.2 motor) |
| `temmuzPoly/backtest_analiz32.py` | 32. Analiz 1Y FeatureEngine backtest (BTC+SOL, composite gate±15) |
| `temmuzPoly/poly_trader_analiz4.py` | 4. Analiz sanal (BTC+ETH); PM gamma fiyatından gerçekçi P&L |
| `temmuzPoly/poly_trader_analiz5.py` | 5. Analiz A1 motoru BTC+SOL **gerçek PM** ($6–12); hafta sonu duraklama Cum 22–Paz 22 |
| `temmuzPoly/poly_trader_analiz7.py` | 7. Analiz Enhanced 6-algo BTC 1H sanal ($300, $12-16-20 WR) |
| `temmuzPoly/poly_analiz_dual_core.py` | 10/13 çift konsensüs ortak motor (A1+A4; TG yalnızca açılış/kapanış) |
| `temmuzPoly/poly_trader_analiz10.py` | 10. Analiz çift konsensüs sanal (BTC+SOL, $300, $12-16-20 WR) |
| `temmuzPoly/poly_trader_analiz9.py` | 9. Analiz sanal (PASIF — `ANALIZ9_ENABLED=false`) |
| `temmuzPoly/poly_trader_analiz13.py` | 13. Analiz çift konsensüs sanal (**SOL only**, $24-32-40 WR) |
| `temmuzPoly/btc_analiz21_algo.py` | 21. Analiz motoru — BTC Hull MA / SOL MACD Hist |
| `temmuzPoly/poly_trader_analiz21.py` | 21. Analiz sanal (BTC+SOL, $300, $12-16-20) |
| `temmuzPoly/poly_trader_analiz23.py` | 23. Analiz hibrit sanal (A4 BTC + A2 SOL, $300, $20-30-40, TG=5M107) |
| `temmuzPoly/poly_trader_analiz31.py` | 31. Analiz Multi-TF MR sanal ($300, $12-16-20) |
| `temmuzPoly/poly_trader_analiz6.py` | 6. Analiz A1+A4 konsensus sanal ($300, $20; open :06) |
| `temmuzPoly/analiz32_5m_adapter.py` | Analiz32 → 5m sinyal adaptörü (algo bozulmaz) |
| `temmuzPoly/analiz32_15m_adapter.py` | Analiz32 → 15m sinyal adaptörü (110 SOL) |
| `temmuzPoly/analiz32_15m_adapter_111.py` | Analiz32 15m filtreli adaptör (skor≥20, trend uyumu; algo bozulmaz) |
| `temmuzPoly/poly_trader_5m_sol_110.py` | 15M 110 SOL — A32 sanal $8-10-12, cron */15 (+1 sn açılış) |
| `temmuzPoly/poly_trader_5m_sol_111.py` | 15M 111 SOL — 110 snapshot + filtreler, cron */15 (+15 sn) |
| `temmuzPoly/analiz32_15m_signal_snapshot.py` | 110→111 paylaşımlı 15m sinyal snapshot |
| `temmuzPoly/poly_trader_5m_real_stats.py` | 15M gerçek PM saatlik Telegram özeti (yalnızca gerçek PM açıkken) |
| `temmuzPoly/poly_trader_5m_btc_107.py` | 5M 107 BTC sanal — **PASIF** ($200, $8-12/işlem, 105 algo+fren) |
| `temmuzPoly/algo_signals.py` | 39 saatlik algo sinyali (BTC/ETH/SOL); `/tmp/algo_signals.json` |

**Test:** `python3 BistAnaliz/BistHourSinyal/bist_visual_v2.py --test` — örnek BIST Analiz metni.  
`python3 BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py --test` — örnek GÜÇLÜ AL metni (tarama/seans yok).

## Cron
- `BistAnaliz/BistHourSinyal/bist_visual_v2.py 1h` — `1 7-15` + `31 14` iş günü → `/tmp/bist_visual.log`
- `BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py` — `*/5` iş günü → `/tmp/bist_signal_hunter.log`
- `BistAnaliz/backup.py` — `59 23 * * *` → `/tmp/backup.log`
- Saatlik analizler `close` **:02** / `open` **:05** (A1,A2,A4,A5,A7,A10,A13,A21,A31,A32)
- `temmuzPoly/poly_trader_analiz1.py close/open` — 1. Analiz BTC+SOL **sanal** ($300); open Cum 22:00–Paz 22:00 İST kapalı
- `temmuzPoly/poly_trader_analiz1.py weekly` — Cumartesi 21:00 haftalık 1 ısı haritası
- `temmuzPoly/poly_trader_analiz1.py daily` — her gün 00:00 İST günlük işlem geçmişi (TG)
- `temmuzPoly/poly_trader_analiz2.py close/open` — 2. Analiz **SOL only** sanal ($300, $12-16-20 WR); **24/7**
- `temmuzPoly/poly_trader_analiz2.py weekly` — Cumartesi 21:00 haftalık 2 ısı haritası
- `temmuzPoly/poly_trader_analiz4.py close/open` — 4. Analiz çoklu-algo **sanal** (BTC+ETH)
- `temmuzPoly/poly_trader_analiz4.py weekly` — Cumartesi 21:00 haftalık 4 ısı haritası
- `temmuzPoly/poly_trader_analiz6.py close/open` — 6. Analiz A1+A4 konsensus **sanal** ($300, $20); open **:06**
- `temmuzPoly/poly_trader_analiz6.py weekly` — Cumartesi 21:00 haftalık 6 ısı haritası
- `temmuzPoly/poly_trader_analiz5.py close/open` — A1 motoru BTC+SOL **gerçek PM**; open Cum 22–Paz 22 duraklama
- `temmuzPoly/poly_trader_analiz5.py weekly` — Cumartesi 21:00 haftalık 5 ısı haritası
- `temmuzPoly/poly_trader_analiz7.py close/open` — Enhanced 6-algo BTC 1H sanal ($300, $12-16-20 WR)
- `temmuzPoly/poly_trader_analiz10.py close/open` — çift konsensüs **sanal** ($300, $12-16-20 WR)
- `temmuzPoly/poly_trader_analiz10.py weekly` — Cumartesi 21:00 haftalık 10 ısı haritası
- `temmuzPoly/poly_trader_analiz13.py close/open` — çift konsensüs **SOL only** sanal ($300, $24-32-40 WR)
- `temmuzPoly/poly_trader_analiz13.py weekly` — Cumartesi 21:00 haftalık 13 ısı haritası
- `temmuzPoly/poly_trader_analiz21.py close/open` — 21. Analiz sembol-algo **sanal** ($300, $12-16-20)
- `temmuzPoly/poly_trader_analiz21.py weekly` — Cumartesi 21:00 haftalık 21 ısı haritası
- `temmuzPoly/poly_trader_analiz23.py close/open` — 23. Analiz A4 BTC + A2 SOL **sanal** ($300, $20-30-40)
- `temmuzPoly/poly_trader_analiz23.py weekly` — Cumartesi 21:00 haftalık 23 ısı haritası
- `temmuzPoly/poly_trader_analiz31.py close/open` — 31. Analiz Multi-TF MR **sanal** ($300, $12-16-20)
- `temmuzPoly/poly_trader_analiz31.py weekly` — Cumartesi 21:00 haftalık 31 ısı haritası
- `temmuzPoly/poly_trader_analiz32.py close/open` — 32. Analiz FeatureEngine **sanal SOL only** ($300, $12-16-20)
- `temmuzPoly/poly_trader_analiz32.py weekly` — Cumartesi 21:00 haftalık 32 ısı haritası
- `temmuzPoly/poly_trader_analiz32.py daily` — her gün 00:00 İST günlük işlem geçmişi (TG)
- `temmuzPoly/poly_trader_5m_real_stats.py` — saat başı: 5M gerçek PM Telegram özeti → `/tmp/poly_5m_real_stats.log`
- `temmuzPoly/algo_signals.py` — `:05` her saat: 39 algo sinyali → `/tmp/algo_signals.json`
# PASIF: `BistAnaliz/yuzdeBist.py` — crontab yorum satırı
# PASIF: `BistAnaliz/bist_scanner.py` — BIST Sinyal bildirim kapalı
# PASIF: `temmuzPoly/poly_trader_analiz9.py close/open/weekly` — 9. Analiz sanal (`ANALIZ9_ENABLED=false`)
- `temmuzPoly/poly_trader_5m_sol_110.py open` — 15M 110 SOL A32 **sanal** $8-10-12 (*/15, +1 sn)
- `temmuzPoly/poly_trader_5m_sol_110.py weekly` — Pazar 00:00 haftalık 110
- `temmuzPoly/poly_trader_5m_sol_111.py open` — 15M 111 SOL filtreli **sanal** $8-10-12 (*/15, +15 sn, 110 snapshot)
- `temmuzPoly/poly_trader_5m_sol_111.py weekly` — Pazar 00:00 haftalık 111
# PASIF: `temmuzPoly/poly_trader_5m_btc_107.py open/weekly` — 5M 107 BTC sanal
# KALDIRILDI: `temmuzPoly/poly_trader_analiz3.py`, `poly_trader_karisim1.py`, `btc_analiz_hourly.py`, `poly_trader_5m_btc_105.py`
# YOK (disk/crontab): `polyManuel/sol_bot.py`, `temmuzPoly/poly_trader.py`

## Sürekli Çalışan Servisler
- `web/poly_dashboard.py` — port **5050**; PID izle; yeniden başlatmak için: `nohup python3 /root/aiProject/web/poly_dashboard.py > /tmp/poly_dashboard.log 2>&1 &`

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.

**Poly analiz TG kuralı:** Tüm analizlerde Telegram yalnızca gerçek açılış veya kapanışta gider; “pozisyon yok / sinyal yok / skip / önizleme” log’a yazılır.
