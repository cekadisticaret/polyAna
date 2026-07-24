# aiProject — Proje Yapısı

## Genel Bakış
BIST Telegram betikleri `BistAnaliz/` altında. Ortak motor: `BistAnaliz/bist_scanner.py`. Gizli ayar proje kökünde: `telegram_config.py` (şablon: `BistAnaliz/telegram_config.example.py`).

| Klasör | Açıklama |
|---|---|
| `BistAnaliz/` | `bist_scanner.py`, `backup.py`, Telegram şablonu; alt klasörlerde saatlik ve güçlü AL betikleri. |
| `BistAnaliz/BistHourSinyal/` | `bist_visual_v2.py` — trend + momentum metin bildirimi. |
| `BistAnaliz/BistYapayAnaliz/` | `bist_signal_hunter.py` — 15m/1h güçlü AL; geçmiş: `bist_signal_hunter_history.json`. |
| `BistAnaliz/yuzdeBist.py` | BIST 5dk güven tarayıcı — **PASIF** (crontab yorum satırı). |
| `web/poly_dashboard.py` | Poly dashboard — harita/geçmiş, PM kotasyon; **A1 Live / A2 / 210** aç-kapat; **3+8 Freqtrade/Jesse** harita; port **5050**. |
| `temmuzPoly/` | Poly trader'lar, algo motorları, backtest; dashboard port **5050**. |
| `crypto-news-monitor/` | Kripto haber/tweet tarayıcı — RSS + opsiyonel Twitter, Claude skor, Telegram alarm (30 dk cron) |
| `freqtrade/` | [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) — kurulu venv; dry-run config; **3. Analiz Freqtrade** saatlik sanal PM (BTC+SOL+ETH) |
| `freqtrade/poly_analiz3_freqtrade.py` | 3. Analiz Freqtrade — SampleStrategy TA + saatlik sanal Polymarket $300 |
| `freqtrade/analiz3_signal.py` | Freqtrade TA → PM UP/DOWN sinyal motoru |
| `jesse/` | [jesse-ai/jesse](https://github.com/jesse-ai/jesse) — kurulu venv; **8. Analiz Jesse** saatlik sanal PM (BTC+SOL+ETH) |
| `jesse/poly_analiz8_jesse.py` | 8. Analiz Jesse — GoldenCross EMA8/21 + saatlik sanal Polymarket $300 |
| `jesse/analiz8_signal.py` | Jesse indicators → PM UP/DOWN sinyal motoru |
| `temmuzPoly/alfa_signal.py` | ALFA — A1+A3+A8 WR ağırlıklı konsensüs sinyali (BTC+SOL) |
| `temmuzPoly/poly_trader_alfa.py` | ALFA sanal PM saatlik trader ($300, ayrı Telegram bot) |
| `temmuzPoly/run_alfa.sh` | ALFA runner (freqtrade+jesse venv birleşik) |
| `5M110Analiz/` | FeatureEngine v2 indikatör kütüphanesi (110/111/210 adaptörleri) |
| `5M110Analiz/predictor.py` | composite_signal → UP/DOWN (gate ±15; algo kütüphanesine dokunmaz) |
| `temmuzPoly/poly_predictor_analysis.py` | A1/A2/A1 Live/dual ortak `predict` motoru |
| `temmuzPoly/poly_trader_5m_common.py` | 5M BTC ortak yardımcılar (Binance, 4-algo, PM emir) |
| `temmuzPoly/btc_5m_105_algo.py` | 5M ortak sinyal motoru (107 + 15M adaptörleri; 4-algo + MR veto) |
| `temmuzPoly/pm_trader_helpers.py` | PM emir + sanal kotasyon; P&L = pm_size − pm_spent (2x fallback yok) |
| `temmuzPoly/pm_balance_guard.py` | PM USDC bakiye + `pm_system_control.json` dashboard açılış anahtarı (A1 Live · A2 · 210 ayrı) |
| `temmuzPoly/btc_analiz1_algo.py` | 1. Analiz tam algoritma (standalone kopya, poly_predictor ile aynı) |
| `temmuzPoly/poly_trader_analiz1.py` | 1. Analiz sanal (BTC+SOL); $12-16-20 WR; top-3 saatte +%50; 12:00 yarı; Cum 22–Paz 18 duraklama |
| `temmuzPoly/poly_trader_analiz2.py` | 2. Analiz sanal (SOL only; $300; **ALLOW_FALLBACK=False**) |
| `temmuzPoly/poly_trader_analiz2_live.py` | 2. Analiz **canlı PM** SOL $5-6-7 WR; en etkili 3 saatte +%50 giriş (A2 geçmişi) |
| `temmuzPoly/backtest_common.py` | 1Y walk-forward backtest ortak yardımcılar |
| `temmuzPoly/backtest_analiz2.py` | 2. Analiz 1Y walk-forward backtest (SOL, predict motoru) |
| `temmuzPoly/backtest_analiz1.py` | 1. Analiz 1Y walk-forward backtest (BTC+SOL, predict motoru) |
| `temmuzPoly/backtest_analiz_suite.py` | 4/10. Analiz 1Y backtest ($1000, algo import — canlıya dokunmaz) |
| `temmuzPoly/poly_trader_analiz4.py` | 4. Analiz sanal (BTC+ETH); PM gamma fiyatından gerçekçi P&L |
| `temmuzPoly/poly_trader_analiz5_midcheck.py` | A1 Live açık pozisyon :30 anlık değer + PM kotasyon görseli (TG) |
| `temmuzPoly/poly_trader_analiz5.py` | **A1 Live** — A1 motoru BTC+SOL gerçek PM ($5–7 WR); en etkili 3 saatte +%50 giriş |
| `temmuzPoly/poly_analiz_dual_core.py` | 10/13 çift konsensüs ortak motor (A1+A4; TG yalnızca açılış/kapanış) |
| `temmuzPoly/poly_trader_analiz10.py` | 10. Analiz çift konsensüs sanal (BTC+SOL, $300, $12-16-20 WR) |
| `temmuzPoly/poly_trader_analiz9.py` | 9. Analiz sanal (PASIF — `ANALIZ9_ENABLED=false`) |
| `temmuzPoly/poly_trader_analiz13.py` | 13. Analiz çift konsensüs sanal (**SOL only**, $10 sabit) |
| `temmuzPoly/poly_trader_manual_state.json` | Manuel PM işlemleri state (dashboard açık pozisyon) |
| `temmuzPoly/analiz32_5m_adapter.py` | 5M110Analiz → 5m sinyal adaptörü (algo bozulmaz) |
| `temmuzPoly/analiz32_15m_adapter.py` | 5M110Analiz → 15m sinyal adaptörü (110 SOL) |
| `temmuzPoly/analiz32_15m_adapter_111.py` | 5M110Analiz 15m filtreli adaptör (skor≥20, trend uyumu; algo bozulmaz) |
| `temmuzPoly/poly_trader_5m_sol_110.py` | 15M 110 SOL — A32 **sanal** $8-10-12; Cum 22–Paz 18 duraklama |
| `temmuzPoly/poly_trader_5m_sol_111.py` | 15M 111 SOL — 110 snapshot + filtreler; Cum 22–Paz 18 duraklama |
| `temmuzPoly/poly_trader_5m_sol_210.py` | 15M 210 SOL — 110 snapshot poll gerçek PM $4-5-6 (110 açınca mirror); gece 22:00–07:00 + hafta sonu open kapalı; saatlik son-10 özeti; TG=5.Analiz |
| `temmuzPoly/analiz32_15m_signal_snapshot.py` | 110→111/210 paylaşımlı 15m sinyal snapshot |
| `temmuzPoly/pm_balance_hourly.py` | PM portföy saatlik kayıt + 00:00 Telegram özeti + 3 saat peş peşe düşüş ALERT |
| `temmuzPoly/poly_trader_5m_real_stats.py` | 15M 110 sanal saatlik Telegram özeti |
| `temmuzPoly/poly_trader_5m_btc_107.py` | 5M 107 BTC sanal — **PASIF** ($200, $8-12/işlem, 105 algo+fren) |
| `temmuzPoly/algo_signals.py` | 39 saatlik algo sinyali (BTC/ETH/SOL); `/tmp/algo_signals.json` |

**Test:** `python3 BistAnaliz/BistHourSinyal/bist_visual_v2.py --test` — örnek BIST Analiz metni.  
`python3 BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py --test` — örnek GÜÇLÜ AL metni (tarama/seans yok).

## Cron
- `BistAnaliz/BistHourSinyal/bist_visual_v2.py 1h` — `1 7-15` + `31 14` iş günü → `/tmp/bist_visual.log`
- `BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py` — `*/5` iş günü → `/tmp/bist_signal_hunter.log`
- `BistAnaliz/backup.py` — `59 23 * * *` → `/tmp/backup.log`
- Saatlik analizler `close` **:02** / `open` **:05** (A1,A2,A4,A1 Live,A10,A13)
- `temmuzPoly/poly_trader_analiz1.py close/open` — 1. Analiz BTC+SOL **sanal** ($300); open Cum 22:00–Paz 18:00 İST kapalı
- `temmuzPoly/poly_trader_analiz1.py weekly` — Cumartesi 21:00 haftalık 1 ısı haritası
- `temmuzPoly/poly_trader_analiz1.py daily` — her gün 00:00 İST günlük işlem geçmişi (TG)
- `temmuzPoly/poly_trader_analiz2.py close/open` — 2. Analiz **SOL only** sanal ($300, $12-16-20 WR); **24/7**
- `temmuzPoly/poly_trader_analiz2_live.py close/open` — 2. Analiz **canlı PM** SOL $5-6-7 WR (`PM_ANALIZ2_REAL_ENABLED`; :02/:05)
- `temmuzPoly/poly_trader_analiz2.py weekly` — Cumartesi 21:00 haftalık 2 ısı haritası
- `temmuzPoly/poly_trader_analiz4.py close/open` — 4. Analiz çoklu-algo **sanal** (BTC+ETH)
- `temmuzPoly/poly_trader_analiz4.py weekly` — Cumartesi 21:00 haftalık 4 ısı haritası
- `temmuzPoly/poly_trader_analiz5.py close/open` — **A1 Live** BTC+SOL gerçek PM; open Cum 22–Paz 18 duraklama
- `temmuzPoly/poly_trader_analiz5_midcheck.py` — saat **:30** o saatin açık pozisyonu anlık değer + kotasyon görseli (TG)
- `temmuzPoly/poly_trader_analiz5.py weekly` — Cumartesi 21:00 haftalık 5 ısı haritası
- `temmuzPoly/poly_trader_analiz10.py close/open` — çift konsensüs **sanal** ($300, $12-16-20 WR)
- `temmuzPoly/poly_trader_analiz10.py weekly` — Cumartesi 21:00 haftalık 10 ısı haritası
- `temmuzPoly/poly_trader_analiz13.py close/open` — çift konsensüs **SOL only** sanal ($300, $10 sabit)
- `temmuzPoly/poly_trader_analiz13.py weekly` — Cumartesi 21:00 haftalık 13 ısı haritası
- `temmuzPoly/pm_balance_hourly.py` — saat başı PM portföy kaydı; **00:00 İST** Telegram bakiye özeti; 3 saat peş peşe düşüşte 🔴 ALERT
- `temmuzPoly/poly_trader_5m_real_stats.py` — saat başı: 110 sanal PM Telegram özeti
- `temmuzPoly/algo_signals.py` — `:05` her saat: 39 algo sinyali → `/tmp/algo_signals.json`
- `freqtrade/run_analiz3.sh close/open` — **3. Analiz Freqtrade** saatlik sanal PM BTC+SOL+ETH (:02/:05)
- `jesse/run_analiz8.sh close/open` — **8. Analiz Jesse** saatlik sanal PM BTC+SOL+ETH (:02/:05)
- `temmuzPoly/run_alfa.sh close/open` — **ALFA** A1+A3+A8 konsensüs sanal PM BTC+SOL (:02/:05)
# PASIF: `BistAnaliz/yuzdeBist.py` — crontab yorum satırı
# PASIF: `BistAnaliz/bist_scanner.py` — BIST Sinyal bildirim kapalı
# PASIF: `temmuzPoly/poly_trader_analiz9.py close/open/weekly` — 9. Analiz sanal (`ANALIZ9_ENABLED=false`)
- `temmuzPoly/poly_trader_5m_sol_110.py open` — 15M 110 SOL A32 **sanal** $8-10-12 (*/15, +1 sn)
- `temmuzPoly/poly_trader_5m_sol_110.py weekly` — Pazar 00:00 haftalık 110
- `temmuzPoly/poly_trader_5m_sol_111.py open` — 15M 111 SOL filtreli **sanal** $8-10-12 (*/15, +15 sn, 110 snapshot)
- `temmuzPoly/poly_trader_5m_sol_111.py weekly` — Pazar 00:00 haftalık 111
- `temmuzPoly/poly_trader_5m_sol_210.py open` — 15M 210 SOL 110 snapshot **gerçek PM** $4-5-6 (*/15, 110 snapshot poll max 20 sn)
- `temmuzPoly/poly_trader_5m_sol_210.py hourly` — saat başı son 10 işlem P&amp;L özeti (A1 Live TG)
- `temmuzPoly/poly_trader_5m_sol_210.py weekly` — Pazar 00:00 haftalık 210
# PASIF: `temmuzPoly/poly_trader_5m_btc_107.py open/weekly` — 5M 107 BTC sanal
# KALDIRILDI: `poly_trader_analiz6.py`, `poly_trader_analiz7.py`, `btc_1h_analiz7_algo.py`, `poly_trader_analiz21.py`, …
# YOK (disk/crontab): `polyManuel/sol_bot.py`, `temmuzPoly/poly_trader.py`

## Sürekli Çalışan Servisler
- `web/poly_dashboard.py` — port **5050**; PID izle; yeniden başlatmak için: `nohup python3 /root/aiProject/web/poly_dashboard.py > /tmp/poly_dashboard.log 2>&1 &`

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.

**Poly analiz TG kuralı:** Tüm analizlerde Telegram yalnızca gerçek açılış veya kapanışta gider; “pozisyon yok / sinyal yok / skip / önizleme” log’a yazılır.
