# aiProject — Proje Yapısı

## Genel Bakış
BIST Telegram betikleri `BistAnaliz/` altında. Ortak motor: `BistAnaliz/bist_scanner.py`. Gizli ayar proje kökünde: `telegram_config.py` (şablon: `BistAnaliz/telegram_config.example.py`).

| Klasör | Açıklama |
|---|---|
| `BistAnaliz/` | `bist_scanner.py`, `backup.py`, Telegram şablonu; alt klasörlerde saatlik ve güçlü AL betikleri. |
| `BistAnaliz/BistHourSinyal/` | `bist_visual_v2.py` — trend + momentum metin bildirimi. |
| `BistAnaliz/BistYapayAnaliz/` | `bist_signal_hunter.py` — 15m/1h güçlü AL; geçmiş: `bist_signal_hunter_history.json`. |
| `BistAnaliz/yuzdeBist.py` | BIST 5dk güven tarayıcı — **PASIF** (crontab yorum satırı). |
| `temmuzPoly/chart_algo_overlay.py` | Grafik overlay — 5M110Analiz EMA/composite/sinyal serileri (110/111/109). |
| `temmuzPoly/chart_hourly_signals.py` | Grafik overlay — 1. Analiz (A1) + 3. Freqtrade (A3) + Jesse A8 saatlik UP/DOWN okları. |
| `temmuzPoly/a3a8_signal_mode.py` | A3/A8 sıkı vs gevşek sinyal modu (`pm_system_control.json` → `a3a8_signal_strict`) |
| `temmuzPoly/chart_15m_a3a8_signals.py` | Grafik overlay — 15m A8 (112) + A3 (113) UP/DOWN okları. |
| `web/poly_dashboard.py` | Poly dashboard — **`/poly/grafik`** ve **`/poly/islemler`**: 5m **110**; **15m 110+112+113**; **1h** A1+A3+A8+ALFA; port **5050**. |
| `temmuzPoly/` | Poly trader'lar, algo motorları, backtest; dashboard port **5050**. |
| `crypto-news-monitor/` | Kripto haber/tweet tarayıcı — RSS + opsiyonel Twitter, Claude skor, Telegram alarm (30 dk cron) |
| `freqtrade/` | [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) — kurulu venv; dry-run config; **3. Analiz Freqtrade** saatlik sanal PM (BTC+SOL+ETH) |
| `freqtrade/poly_analiz3_freqtrade.py` | 3. Analiz Freqtrade — SampleStrategy TA + saatlik sanal Polymarket $300 |
| `freqtrade/analiz3_signal.py` | Freqtrade TA → PM UP/DOWN sinyal motoru |
| `jesse/` | [jesse-ai/jesse](https://github.com/jesse-ai/jesse) — kurulu venv; **8. Analiz Jesse** saatlik sanal PM (BTC+SOL+ETH) |
| `jesse/poly_analiz8_jesse.py` | 8. Analiz Jesse — GoldenCross EMA8/21 + saatlik sanal Polymarket $300 |
| `jesse/analiz8_signal.py` | Jesse indicators → PM UP/DOWN sinyal motoru |
| `temmuzPoly/alfa_signal.py` | ALFA — SOL: A1+A3+A8+Markov (2/4→$6, 3/4→$12, 4/4→$24); BTC/ETH: 2/3→$8, 3/3→$16 |
| `temmuzPoly/poly_trader_alfa.py` | ALFA sanal PM saatlik (BTC+SOL+ETH, $300; ayrı Telegram bot) |
| `temmuzPoly/run_alfa.sh` | ALFA runner (freqtrade+jesse venv birleşik) |
| `5M110Analiz/` | FeatureEngine v2 indikatör kütüphanesi (110/111/210 adaptörleri) |
| `5M110Analiz/predictor.py` | composite_signal → UP/DOWN (gate ±15; algo kütüphanesine dokunmaz) |
| `temmuzPoly/poly_predictor_analysis.py` | A1/A2/A1 Live/dual ortak `predict` motoru |
| `temmuzPoly/btc_5m_105_algo.py` | 5M ortak sinyal motoru (15M adaptörleri; 4-algo + MR veto) |
| `temmuzPoly/poly_trader_5m_common.py` | 5M BTC ortak yardımcılar (Binance, 4-algo, PM emir) |
| `temmuzPoly/pm_trader_helpers.py` | PM emir + sanal kotasyon; P&L = pm_size − pm_spent (2x fallback yok) |
| `temmuzPoly/pm_cem_pool.py` | CEM-ANALİZ ortak sanal havuz ($300, A1+A2+110 mirror) |
| `temmuzPoly/pm_manual_sync.py` | Manuel PM — Polymarket activity → manual state senkron (5/15dk + saatlik) |
| `temmuzPoly/pm_poly_history.py` | Polymarket data-api activity → slug bazlı gerçek PM geçmişi + açık (bekleyen) işlemler |
| `temmuzPoly/poly_trader_cem_analiz.py` | **CEM-ANALİZ** — A1/A2/110 mirror; TG=13. Analiz kanalı |
| `temmuzPoly/pm_balance_guard.py` | PM USDC bakiye + `pm_system_control.json` dashboard açılış anahtarı (A1 Live · A2 · 210 ayrı; sanal trader'lar etkilenmez) |
| `temmuzPoly/pm_weekend_sync.py` | Cum 22:00 / Pzt 08:00 İST — 3 PM anahtarını otomatik kapat/aç (dashboard senkron) |
| `temmuzPoly/btc_analiz1_algo.py` | 1. Analiz tam algoritma (standalone kopya, poly_predictor ile aynı) |
| `temmuzPoly/poly_trader_analiz1.py` | 1. Analiz sanal (BTC+SOL); $12-16-20 WR; top-3 saatte +%50; 12:00 yarı; Cum 22–Paz 18 duraklama |
| `temmuzPoly/poly_trader_analiz2.py` | 2. Analiz sanal (SOL only; $300; Cum 22–Paz 18 duraklama; **ALLOW_FALLBACK=False**) |
| `temmuzPoly/poly_trader_analiz2_live.py` | 2. Analiz **canlı PM** SOL $6-7-8 WR; en etkili 3 saatte +%50 giriş (A2 geçmişi) |
| `temmuzPoly/backtest_common.py` | 1Y walk-forward backtest ortak yardımcılar |
| `temmuzPoly/backtest_analiz2.py` | 2. Analiz 1Y walk-forward backtest (SOL, predict motoru) |
| `temmuzPoly/backtest_analiz1.py` | 1. Analiz 1Y walk-forward backtest (BTC+SOL, predict motoru) |
| `temmuzPoly/backtest_analiz_suite.py` | 4/10. Analiz 1Y backtest ($1000, algo import — canlıya dokunmaz) |
| `temmuzPoly/backtest_analiz3_8.py` | 3/8. Analiz 1Y backtest (BTC+SOL+ETH, $300, `--telegram`) |
| `temmuzPoly/poly_trader_analiz4.py` | 4. Analiz sanal (BTC+ETH); Cum 22–Paz 18 duraklama |
| `temmuzPoly/poly_trader_analiz6.py` | 6. Analiz sanal (BTC+SOL); MACD Hist. Div #26; $300; Cum 22–Paz 18 duraklama |
| `temmuzPoly/poly_trader_analiz5_midcheck.py` | A1 Live açık pozisyon :30 anlık değer + PM kotasyon görseli (TG) |
| `temmuzPoly/pm_partial_takeprofit.py` | **210** kısmi kar al — max kârın %65'inde %75 sat (A1/A2 saatlik eski düzen) |
| `temmuzPoly/poly_trader_analiz5.py` | **A1 Live** — A1 motoru BTC+SOL gerçek PM ($6–8 WR); en etkili 3 saatte +%50 giriş |
| `temmuzPoly/poly_analiz_dual_core.py` | 10. Analiz çift konsensüs ortak motor (A1+A4; TG yalnızca açılış/kapanış) |
| `temmuzPoly/poly_trader_analiz10.py` | 10. Analiz çift konsensüs sanal (BTC+SOL, $300; Cum 22–Paz 18 duraklama) |
| `temmuzPoly/poly_trader_manual_state.json` | Manuel PM işlemleri state (dashboard açık pozisyon) |
| `temmuzPoly/analiz32_5m_adapter.py` | 5M110Analiz → 5m sinyal adaptörü (algo bozulmaz) |
| `temmuzPoly/analiz32_15m_adapter.py` | 5M110Analiz → 15m sinyal adaptörü (110 SOL) |
| `temmuzPoly/analiz32_15m_adapter_111.py` | 5M110Analiz 15m filtreli adaptör (skor≥15, trend uyumu; algo bozulmaz) |
| `temmuzPoly/poly_trader_15m_dir_runner.py` | 15m yön trader çekirdeği (109 kalıbı; A3/A8 vb. parametrik) |
| `temmuzPoly/analiz_15m_a3a8_adapter.py` | 15m A8 (112) + A3 (113) sinyal adaptörü |
| `temmuzPoly/poly_trader_5m_sol_109.py` | 15M 109 SOL — 110 ile aynı algo; **7/24** sanal $8-10-12 |
| `temmuzPoly/poly_trader_5m_sol_110.py` | 15M 110 SOL — A32 **sanal** $8-10-12; Cum 22–Paz 18 duraklama |
| `temmuzPoly/poly_trader_5m_sol_112.py` | 15M 112 A8 — Jesse A8 @ 15m sanal $8-10-12 (+2 sn) |
| `temmuzPoly/analiz_114_15m_filter.py` | 15M 114 — 110 + 1h ALFA/A8 hizası, gece filtresi, kayıp serisi mola |
| `temmuzPoly/poly_trader_5m_sol_114.py` | 15M 114 SOL — filtreli 110 @ 15m sanal $8-10-12 (+4 sn) |
| `temmuzPoly/poly_trader_5m_sol_113.py` | 15M 113 A3 — Freqtrade A3 @ 15m sanal $8-10-12 (+3 sn); `recent` son 10 işlem TG |
| `temmuzPoly/poly_trader_5m_sol_111.py` | 15M 111 SOL — 110 snapshot + filtreler; **7/24** sanal $8-10-12 |
| `temmuzPoly/poly_trader_5m_sol_210.py` | 15M 210 SOL — 110 snapshot poll gerçek PM $4-5-6; Cum 22–Paz 18 + gece 22–07 duraklama |
| `temmuzPoly/analiz32_15m_signal_snapshot.py` | 110→111/210 paylaşımlı 15m sinyal snapshot |
| `temmuzPoly/pm_balance_hourly.py` | PM portföy saatlik kayıt + 00:00 Telegram özeti + 3 saat peş peşe düşüş ALERT |
| `temmuzPoly/poly_trader_5m_real_stats.py` | 15M 110 sanal saatlik Telegram özeti |
| `temmuzPoly/algo_signals.py` | 39 saatlik algo sinyali (BTC/ETH/SOL); `/tmp/algo_signals.json` |

**Test:** `python3 BistAnaliz/BistHourSinyal/bist_visual_v2.py --test` — örnek BIST Analiz metni.  
`python3 BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py --test` — örnek GÜÇLÜ AL metni (tarama/seans yok).

## Cron
- `BistAnaliz/BistHourSinyal/bist_visual_v2.py 1h` — `1 7-15` + `31 14` iş günü → `/tmp/bist_visual.log`
- `BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py` — `*/5` iş günü → `/tmp/bist_signal_hunter.log`
- `BistAnaliz/backup.py` — `59 23 * * *` → `/tmp/backup.log`
- Saatlik analizler `close` **:02** / `open` **:05** — **tüm aktif analizlerde Cum 22:00–Paz 18:00 İST open+close kapalı**
- `temmuzPoly/poly_trader_analiz1.py close/open` — 1. Analiz BTC+SOL **sanal** ($300); open Cum 22:00–Paz 18:00 İST kapalı
- `temmuzPoly/poly_trader_analiz1.py weekly` — Cumartesi 21:00 haftalık 1 ısı haritası
- `temmuzPoly/poly_trader_analiz1.py daily` — her gün 00:00 İST günlük işlem geçmişi (TG)
- `temmuzPoly/poly_trader_analiz2.py close/open` — 2. Analiz **SOL only** sanal ($300, $12-16-20 WR); open Cum 22:00–Paz 18:00 İST kapalı
- `temmuzPoly/poly_trader_cem_analiz.py close_hourly/open_hourly/sync_15m` — **CEM-ANALİZ** A1+A2+110 mirror ($300 ortak); TG=13. Analiz kanalı; `:03`/`:06`/`1,16,31,46`
- `temmuzPoly/poly_trader_analiz2_live.py close/open` — 2. Analiz **canlı PM** SOL $6-7-8 WR (`PM_ANALIZ2_REAL_ENABLED`; :02/:05; hafta sonu dashboard anahtarı)
- `temmuzPoly/poly_trader_analiz2.py weekly` — Cumartesi 21:00 haftalık 2 ısı haritası
- `temmuzPoly/poly_trader_analiz4.py close/open` — 4. Analiz çoklu-algo **sanal** (BTC+ETH); Cum 22–Paz 18 kapalı
- `temmuzPoly/poly_trader_analiz4.py weekly` — Cumartesi 21:00 haftalık 4 ısı haritası
- `temmuzPoly/poly_trader_analiz6.py close/open` — 6. Analiz **MACD Hist. Div** sanal (BTC+SOL, $300); Cum 22–Paz 18 kapalı
- `temmuzPoly/poly_trader_analiz6.py weekly` — Cumartesi 21:00 haftalık 6 ısı haritası
- `temmuzPoly/poly_trader_analiz5.py close/open` — **A1 Live** BTC+SOL gerçek PM; hafta sonu dashboard anahtarı (`pm_weekend_sync`)
- `temmuzPoly/pm_weekend_sync.py close/open` — Cum **22:00** / Pzt **08:00** İST: A1 Live + A2 + 210 dashboard anahtarları (manuel override mümkün)
- `temmuzPoly/poly_trader_analiz5_midcheck.py` — saat **:30** o saatin açık pozisyonu anlık değer + kotasyon görseli (TG)
- `temmuzPoly/pm_partial_takeprofit.py` — ***/5** yalnız **210**: max kâr yolunun **≥65%**'inde **75%** sat (A1/A2 dokunulmaz)
- `temmuzPoly/poly_trader_analiz5.py weekly` — Cumartesi 21:00 haftalık 5 ısı haritası
- `temmuzPoly/poly_trader_analiz10.py close/open` — çift konsensüs **sanal**; Cum 22–Paz 18 kapalı
- `temmuzPoly/poly_trader_analiz10.py weekly` — Cumartesi 21:00 haftalık 10 ısı haritası
- `temmuzPoly/pm_balance_hourly.py` — saat başı PM portföy kaydı; **00:00 İST** Telegram bakiye özeti; 3 saat peş peşe düşüşte 🔴 ALERT
- `temmuzPoly/poly_trader_5m_real_stats.py` — saat başı: 110 sanal PM Telegram özeti
- `temmuzPoly/algo_signals.py` — `:05` her saat: 39 algo sinyali → `/tmp/algo_signals.json`
- `freqtrade/run_analiz3.sh close/open` — **3. Analiz Freqtrade** saatlik sanal PM BTC+SOL+ETH (:02/:05)
- `jesse/run_analiz8.sh close/open` — **8. Analiz Jesse** saatlik sanal PM BTC+SOL+ETH (:02/:05)
- `temmuzPoly/run_alfa.sh close/open` — **ALFA** A1+A3+A8 konsensüs sanal PM BTC+SOL (:02/:05)
# PASIF: `BistAnaliz/yuzdeBist.py` — crontab yorum satırı
# PASIF: `BistAnaliz/bist_scanner.py` — BIST Sinyal bildirim kapalı
- `temmuzPoly/poly_trader_5m_sol_109.py open` — 15M 109 SOL (110 clone) **7/24** sanal $8-10-12 (`1,16,31,46`)
- `temmuzPoly/poly_trader_5m_sol_109.py weekly` — Pazar 00:00 haftalık 109
- `temmuzPoly/poly_trader_5m_sol_112.py open` — 15M 112 A8 Jesse @ 15m sanal $8-10-12 (`*/15`, +2 sn)
- `temmuzPoly/poly_trader_5m_sol_113.py open` — 15M 113 A3 Freqtrade @ 15m sanal $8-10-12 (`*/15`, +3 sn)
- `temmuzPoly/poly_trader_5m_sol_114.py open` — 15M 114 SOL 110+1h filtre sanal (`*/15`, +4 sn)
- `temmuzPoly/poly_trader_5m_sol_110.py open` — 15M 110 SOL A32 **sanal** $8-10-12 (*/15, +1 sn)
- `temmuzPoly/poly_trader_5m_sol_110.py weekly` — Pazar 00:00 haftalık 110
- `temmuzPoly/poly_trader_5m_sol_111.py open` — 15M 111 SOL filtreli **sanal** $8-10-12 (**7/24**, */15 +15 sn; snapshot yoksa kendi sinyal)
- `temmuzPoly/poly_trader_5m_sol_111.py weekly` — Pazar 00:00 haftalık 111
- `temmuzPoly/poly_trader_5m_sol_210.py open` — 15M 210 SOL 110 snapshot **gerçek PM** $4-5-6 (*/15; dashboard hafta sonu + gece 22–07 anahtarı)
- `temmuzPoly/poly_trader_5m_sol_210.py hourly` — saat başı son 10 işlem P&amp;L özeti (A1 Live TG; o saatte 15m işlem yoksa atlanır)
- `temmuzPoly/poly_trader_5m_sol_210.py weekly` — Pazar 00:00 haftalık 210
# KALDIRILDI: `poly_trader_analiz9.py`, `poly_trader_analiz13.py`, `poly_trader_5m_btc_107.py`, …
# YOK (disk/crontab): `polyManuel/sol_bot.py`, `temmuzPoly/poly_trader.py`

## CEM-ANALİZ (A1 + A2 + 110 mirror)
- **Bağımsız sistem:** $300 ortak havuz; Cum 22–Paz 18 İST tam duraklama
- **Mirror:** CEM kaynak state dosyalarını okuyup aynı işlemleri kopyalar
- **Telegram:** 13. Analiz kanalı — `🏁 CEM-ANALİZ — HH:00 Sonuçlar 🔶 SANAL`
- **Cron:** `:03 close_hourly` | `:06 open_hourly` | `1,16,31,46 * * * * sync_15m`
- **CLI:** `python3 temmuzPoly/poly_trader_cem_analiz.py status|reset 300`

## Sürekli Çalışan Servisler
- `web/poly_dashboard.py` — port **5050**; PID izle; yeniden başlatmak için: `nohup python3 /root/aiProject/web/poly_dashboard.py > /tmp/poly_dashboard.log 2>&1 &`

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.

**Poly analiz TG kuralı:** Tüm analizlerde Telegram yalnızca gerçek açılış veya kapanışta gider; “pozisyon yok / sinyal yok / skip / önizleme” log’a yazılır.
