# aiProject — Proje Yapısı

## Genel Bakış
BIST Telegram betikleri `BistAnaliz/` altında. Ortak motor: `BistAnaliz/bist_scanner.py`. Gizli ayar proje kökünde: `telegram_config.py` (şablon: `BistAnaliz/telegram_config.example.py`).

| Klasör | Açıklama |
|---|---|
| `BistAnaliz/` | `bist_scanner.py`, `backup.py`, Telegram şablonu; alt klasörlerde saatlik ve güçlü AL betikleri. |
| `BistAnaliz/BistHourSinyal/` | `bist_visual_v2.py` — trend + momentum metin bildirimi. |
| `BistAnaliz/BistYapayAnaliz/` | `bist_signal_hunter.py` — 15m/1h güçlü AL; geçmiş: `bist_signal_hunter_history.json`. |
| `BistAnaliz/yuzdeBist.py` | BIST 5dk güven tarayıcı — **PASIF** (crontab yorum satırı). |
| `temmuzPoly/chart_algo_overlay.py` | Grafik overlay — 5M110Analiz EMA/composite/sinyal serileri (110/111). |
| `temmuzPoly/chart_multi_confirm_signals.py` | Grafik MC teyit — pattern+hacim+seviye+momentum (Pine portu; rozet, oklar kapalı). |
| `temmuzPoly/chart_signal_accuracy.py` | Grafik MC/YT/TAHMİN/TAHMİN2 saatlik WR takibi + pill’lerde gösterim |
| `temmuzPoly/chart_tahmin2_signals.py` | Grafik TAHMİN2 — LM+ST+ADX+LZ+CVD oylaması (TAHMİN yanında). |
| `temmuzPoly/weekly_slot_heatmap_all.py` | Son 7g saatlik slot ısı haritası → A15/A4 TG; cron her gece 00:00 İST |
| `temmuzPoly/slot_data_archive.py` | Saatlik slot arşivi → `temmuzPoly/slot_data/` (latest/daily/hourly/events) |
| `temmuzPoly/chart_hourly_signals.py` | Grafik overlay — 1. Analiz (A1) + 3. Freqtrade (A3) + Jesse A8 saatlik UP/DOWN okları. |
| `temmuzPoly/a3a8_signal_mode.py` | A3/A8 sıkı (filtreli) vs gevşek mod (`a3a8_signal_strict`; sıkı=entry/kesişim veya momentum+RSI teyit) |
| `temmuzPoly/chart_algo_panel.py` | Grafik ALG1/ALG2 — 5m/15m konsensüs + slot WR takibi (`update_wr` cron */5). |
| `web/poly_dashboard.py` | Poly dashboard **5050** — `/algoritma-islemler` A6/A6V2/A6V3/A15/B1#01 + A2 Top-17; Ayarlar→Kripto'ya Geç; A6V2/V3 Live toggle; geçmiş WR sıralı |
| `temmuzPoly/repair_a2_sanal_settlement.py` | A2 sanal geçmişi PM slot open/close ile yeniden hesaplar (Binance 1h). |
| `scripts/watch_critical_files.py` | Kritik kaynak inotify izleyici — silinmede `ops/incidents/` olay kaydı |
| `ops/CRITICAL_FILE_RESTORE.md` | 2026-08-02 kaynak silinme / geri yükleme zaman çizelgesi |
| `ops/incidents/` | Silinme/eksik olay JSON+txt (process, git D, audit) |
| `AgustosKripto/` | Kripto Future — CR6 canlı + sanal Algoritmalar/Analizler; `bursaapp.com/kripto` |
| `AgustosKripto/virtual_book.py` | Sanal futures — net PnL + ATR kâr kilidi; cache + `/tmp/agustos_snap` |
| `AgustosKripto/atr_profit_lock.py` | ATR trailing kâr kilidi — arm 1.7 / trail 1.0; saatlik close skip + trail stop |
| `AgustosKripto/fee_utils.py` | Binance komisyon — estimate + userTrades; brüt→net |
| `AgustosKripto/algo_tg_notify.py` | Kripto sanal algo TG — **10. ANALİZ kanalı** (`poly_analiz_dual_core` bot); close/open özeti 🔶 SANAL |
| `AgustosKripto/Algoritmalar/` | ALGO2+ALGO1 sanal $300; **tüm 51 defter open $30×10x** max6 (komisyon dahil net PnL); A2#05/#06/#07 + A1#11 ayrıca gerçek Binance'te $7×20x (`real_live`); hafta sonu skip; `reset` |
| `AgustosKripto/Analizler/` | A1–A10 + A6(Supertrend $10×15x max4); ATR runner; A3/A8 venv |
| `AgustosKripto/binance_futures_client.py` | Binance USD-M REST — emir, bakiye, commissionRate, userTrades |
| `AgustosKripto/crypto_futures_trader.py` | Futures open/close + `dust` süpürme (|notional|≤$2); brüt/komisyon/net |
| `AgustosKripto/crypto_futures_cr6.py` | **Algoritmalar Live** (gerçek Binance) — Hurst+A1#11 MR+Z-Score MR+Mean Reversion çoğunluk oyu; top-N; $7×20x; **yeni open BTC/ETH/BNB yok**; ATR/hard SL |
| `AgustosKripto/crypto_futures_live_control.json` | Binance Live — `live_paused` (yeni açılış) + `top_n` (1–10); sanal Algoritma/Analiz etkilenmez |
| `AgustosKripto/cr6_tg_card.py` | Algoritmalar Live TG sarı kart (ALGO2 stili) — açılış/kapanış/ATR photo |
| `AgustosKripto/crypto_futures_config.json` | Sembol allowlist + default $6 / 10x; `CRYPTO_FUTURES_LIVE` + CR6 canlı |
| `temmuzPoly/analiz5_settings.json` | A1/A2/A10/A6 Live WR giriş tutarları (düşük/orta/yüksek) |
| `temmuzPoly/pm_profit_baseline.json` | PM Kar başlangıç bakiyesi (varsayılan $314); Toplam Kar = nakit − baseline. |
| `temmuzPoly/` | Poly trader'lar, algo motorları, backtest; dashboard port **5050**. |
| `crypto-news-monitor/` | Kripto haber/tweet tarayıcı — RSS + opsiyonel Twitter, Claude skor, Telegram alarm (30 dk cron) |
| `freqtrade/` | [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) — kurulu venv; dry-run config; **3. Analiz Freqtrade** saatlik sanal PM (BTC+SOL+ETH) |
| `freqtrade/poly_analiz3_freqtrade.py` | 3. Analiz Freqtrade — SampleStrategy TA + saatlik sanal Polymarket $300 |
| `freqtrade/analiz3_signal.py` | Freqtrade TA → PM UP/DOWN sinyal motoru |
| `jesse/` | [jesse-ai/jesse](https://github.com/jesse-ai/jesse) — kurulu venv; **8. Analiz Jesse** saatlik sanal PM (BTC+SOL+ETH) |
| `jesse/poly_analiz8_jesse.py` | 8. Analiz Jesse — GoldenCross EMA8/21 + saatlik sanal Polymarket $300 |
| `jesse/analiz8_signal.py` | Jesse indicators → PM UP/DOWN sinyal motoru |
| `5M110Analiz/` | FeatureEngine v2 indikatör kütüphanesi (110/111/210 adaptörleri) |
| `5M110Analiz/predictor.py` | composite_signal → UP/DOWN (gate ±15; algo kütüphanesine dokunmaz) |
| `temmuzPoly/poly_predictor_analysis.py` | A1/A2 ortak `predict`; Kill Zone yalnızca A2 (`kill_zone=True`) |
| `temmuzPoly/btc_5m_105_algo.py` | 5M ortak sinyal motoru (15M adaptörleri; 4-algo + MR veto) |
| `temmuzPoly/poly_trader_5m_common.py` | 5M BTC ortak yardımcılar (Binance, 4-algo, PM emir) |
| `temmuzPoly/pm_trader_helpers.py` | PM emir + sanal kotasyon; gerçek PM WR giriş (`load_pm_live_amounts` / `analiz5_settings.json`) |
| `temmuzPoly/pm_manual_sync.py` | Manuel PM — Polymarket activity → manual state senkron (5/15dk + saatlik) |
| `temmuzPoly/poly_trader_manual.py` | Manuel PM slot-sonu otomatik settle (`close`) — 5m/15m/1h |
| `temmuzPoly/pm_orphan_sync.py` | Ghost PM — zincirde açık ama state'te yok pozisyonları live trader'a yazar (trader sembol allowlist) |
| `temmuzPoly/pm_poly_history.py` | Polymarket data-api activity → slug bazlı gerçek PM geçmişi + açık (bekleyen) işlemler |
| `temmuzPoly/pm_balance_guard.py` | PM USDC bakiye + `pm_system_control.json` dashboard açılış anahtarı (A1 Live · A2 ayrı; sanal trader'lar etkilenmez) |
| `temmuzPoly/pm_weekend_sync.py` | Cum 22:00 / Pzt 11:00 İST — A1 Live + A2 dashboard anahtarlarını otomatik kapat/aç |
| `temmuzPoly/btc_analiz1_algo.py` | 1. Analiz tam algoritma (standalone kopya, poly_predictor ile aynı) |
| `temmuzPoly/poly_trader_analiz1.py` | 1. Analiz sanal (BTC+SOL); $12-16-20 WR; PM net kazanç ≥%50 yoksa giriş yok; top-3 saatte +%50; 12:00 yarı |
| `temmuzPoly/poly_trader_analiz2.py` | 2. Analiz sanal (SOL only; $300; PM net kazanç ≥%50 yoksa giriş yok; **ALLOW_FALLBACK=False**) |
| `temmuzPoly/poly_trader_analiz2_live.py` | 2. Analiz **canlı PM** SOL; slot gate WR>%85 → $25; PM net ≥%50 |
| `temmuzPoly/backtest_common.py` | 1Y walk-forward backtest ortak yardımcılar |
| `temmuzPoly/backtest_analiz2.py` | 2. Analiz 1Y walk-forward backtest (SOL, predict motoru) |
| `temmuzPoly/backtest_analiz1.py` | 1. Analiz 1Y walk-forward backtest (BTC+SOL, predict motoru) |
| `temmuzPoly/backtest_analiz_suite.py` | 4/10. Analiz 1Y backtest ($1000, algo import — canlıya dokunmaz) |
| `temmuzPoly/backtest_analiz3_8.py` | 3/8. Analiz 1Y backtest (BTC+SOL+ETH, $300, `--telegram`) |
| `temmuzPoly/poly_trader_analiz4.py` | 4. Analiz sanal (BTC+ETH); Cum 22:00–Pzt 11:00 open kapalı; TG ana bot |
| `temmuzPoly/analiz15_signal.py` | 15. Analiz sinyal — BTC→A6 MACD, ETH→A8 Jesse, SOL→A2 predictor |
| `temmuzPoly/poly_trader_analiz15.py` | 15. Analiz sanal (BTC+ETH+SOL); Cum 22:00–Pzt 11:00 open kapalı; TG A4 botu; $300 |
| `temmuzPoly/backtest_algo_catalog.py` | 78 algo 1Y yön backtest (BTC+ETH+SOL 1h) → `backtest_algo_catalog_1y.json` |
| `temmuzPoly/backtest_algo_catalog_notify.py` | Top-30 algo 1Y P&L özeti + Telegram (`--send`) |
| `temmuzPoly/poly_trader_analiz5_midcheck.py` | A1 Live açık pozisyon :30 anlık değer + PM kotasyon görseli (TG) |
| `temmuzPoly/poly_trader_analiz5.py` | **A1 Live** — gerçek PM; slot gate: top3 +%40 / zayıf saat -%30 / WR>%85 → **$25** |
| `temmuzPoly/poly_analiz_dual_core.py` | 10. Analiz çift konsensüs ortak motor (A1+A4; PM net kazanç ≥%50 filtresi) |
| `temmuzPoly/poly_trader_analiz10.py` | 10. Analiz çift konsensüs sanal (BTC+SOL, $300); Cum 22:00–Pzt 11:00 open kapalı |
| `temmuzPoly/poly_trader_analiz10_live.py` | A10 Live gerçek PM; slot gate (WR>%85 → $25); PM net ≥%50 yoksa giriş yok |
| `temmuzPoly/poly_trader_analiz6.py` | 6. Analiz sanal (BTC+SOL+ETH); TG=15. Analiz (A4 botu); A6 Live eşleme |
| `temmuzPoly/poly_trader_analiz6_v2.py` | 6. Analiz V2 sanal (BTC+ETH only); A6V2 Live eşleme |
| `temmuzPoly/poly_trader_analiz6_v3.py` | 6. Analiz V3 sanal (BTC/ETH→A6 · SOL→A2); A6V3 Live eşleme |
| `temmuzPoly/poly_trader_b1_01.py` | B1#01 sanal — sembol bazlı en iyi motor birleşimi ($300) |
| `temmuzPoly/b1_01_signal.py` | B1#01 motor seçimi — algoritma-islemler WR taraması |
| `temmuzPoly/analiz6_v3_signal.py` | A6V3 sinyal — BTC/ETH A6, SOL A2 |
| `temmuzPoly/poly_trader_analiz6_v2_live.py` | A6V2 Live gerçek PM (BTC+ETH); dashboard toggle |
| `temmuzPoly/poly_trader_analiz6_v3_live.py` | A6V3 Live gerçek PM (BTC+ETH+SOL); dashboard toggle |
| `temmuzPoly/poly_trader_analiz6_live.py` | A6 Live gerçek PM; slot gate WR>%85 → $25; sanal A6 adayları |
| `temmuzPoly/poly_live_hourly_common.py` | Saatlik gerçek PM ortak açılış yardımcıları |
| `temmuzPoly/poly_trader_manual_state.json` | Manuel PM işlemleri state (dashboard açık pozisyon) |
| `temmuzPoly/analiz32_5m_adapter.py` | 5M110Analiz → 5m sinyal adaptörü (algo bozulmaz) |
| `temmuzPoly/analiz32_15m_adapter.py` | 5M110Analiz → 15m sinyal adaptörü (110 SOL) |
| `temmuzPoly/poly_trader_5m_sol_110.py` | 15M 110 SOL — A32 **sanal** $8-10-12; Cum 22:00–Pzt 11:00 open kapalı |
| `temmuzPoly/analiz32_15m_signal_snapshot.py` | 110 15m sinyal snapshot kaydı |
| `temmuzPoly/pm_balance_hourly.py` | PM portföy saatlik kayıt + 00:00 Telegram özeti + 3 saat peş peşe düşüş ALERT |
| `temmuzPoly/poly_trader_5m_real_stats.py` | 15M 110 sanal saatlik Telegram özeti |
| `temmuzPoly/algo_signals.py` | 36 saatlik algo sinyali (BTC/ETH/SOL); `/tmp/algo_signals.json` |
| `temmuzPoly/algo_signals_v2.py` | 17 kârlı algo (Analiz 2 sekmesi); `/tmp/algo_signals_v2.json` + `algo_accuracy_v2.json` |
| `temmuzPoly/poly_trader_a2.py` | A2 Top 17 sanal trader ($300, $8/$12/$16); `poly_trader_a2_XX_{state,history}.json` |
| `temmuzPoly/poly_a2_algo_live_core.py` | A2 Live ortak çekirdek — gerçek PM open/close |
| `temmuzPoly/poly_trader_a2_02_live.py` | A2#02 RSI Div Live — $4/5/6; sanal #02 ayrı; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_08_live.py` | A2#08 Williams Live — $4/5/6; sanal #08 ayrı; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_03_live.py` | A2#03 Stoch RSI Live — $4/5/6; sanal #03 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_trader_a2_04_live.py` | A2#04 Schaff Live — $4/5/6; sanal #04 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_a2_algo_live_core.py` | A2 Live çekirdeği — sanal defter mirror/sync (309 gibi); open :07 |
| `temmuzPoly/poly_trader_a2_05_live.py` | A2#05 Mean Rev Live — sanal #05 ile birebir sync; $4/5/6; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_06_live.py` | A2#06 Z-Score MR Live — $4/5/6; sanal #06 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_trader_a2_07_live.py` | A2#07 Hurst Live — $4/5/6; sanal #07 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_a2_algo_trader_core.py` | A2 sanal Top17 ($300); Cum 22:00–Pzt 11:00 open kapalı; #09/#16/#17 → eski ALFA kanalı |
| `temmuzPoly/poly_15m_a2_algo_trader_core.py` | 15M A2 Top3 çekirdek (309/316/317; $300; Cum 22–Pzt 11 open kapalı; TG=110 botu) |
| `temmuzPoly/poly_trader_15m_a2.py` | 15M A2 Top3 runner (`*/15` open=close+open; BTC+ETH+SOL sanal; 309 sonrası live tetikler) |
| `temmuzPoly/poly_trader_15m_309_live.py` | 15M 309 Live $3 — sanal 309 ile aynı sinyal/anda mirror; pencere yok; `PM_15M_309_REAL_ENABLED` |

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
- `temmuzPoly/poly_trader_analiz2_live.py close/open` — 2. Analiz **canlı PM** SOL $6-7-8 WR (`PM_ANALIZ2_REAL_ENABLED`; :02/:05; hafta sonu dashboard anahtarı)
- `temmuzPoly/poly_trader_analiz2.py weekly` — Cumartesi 21:00 haftalık 2 ısı haritası
- `temmuzPoly/poly_trader_analiz4.py close/open` — 4. Analiz çoklu-algo **sanal** (BTC+ETH); Cum 22:00–Pzt 11:00 open kapalı
- `temmuzPoly/poly_trader_analiz4.py weekly` — Cumartesi 21:00 haftalık 4 ısı haritası
- `temmuzPoly/poly_trader_analiz6.py close/open` — 6. Analiz sanal; **open** aynı adayda A6 Live gerçek PM dener (`PM_ANALIZ6_LIVE_ENABLED` + dashboard)
- `temmuzPoly/poly_trader_analiz6_v2.py close/open` — 6. Analiz V2 sanal (BTC+ETH); A6 ile aynı indikatör; SOL yok; Live yok
- `temmuzPoly/poly_trader_analiz6_live.py close` — A6 Live kapanış :02; open sanal A6 open ile tetiklenir
- `AgustosKripto/crypto_futures_cr6.py close/open/trail` — **Algoritmalar Live** (gerçek Binance); Hurst+A1#11 MR+Z-Score MR+MR çoğunluk oyu; top-4 majors önce; $7×20x; ATR kâr kilidi
- `AgustosKripto/Algoritmalar/runner.py close/open/trail/reset` — sanal $300; tüm 51 defter open $30×10x; close/open TG → **10. ANALİZ kanalı** (🔶 SANAL); Cum 22:00–Pzt 11:00 İST skip
- `AgustosKripto/Analizler/runner.py close/open/trail` — A1–A10 + A6(Supertrend $10×15x max4) + ATR trail
- `temmuzPoly/poly_trader_analiz15.py close/open` — **15. Analiz** BTC→A6 · ETH→A8 · SOL→A2 sanal ($300); Cum 22:00–Pzt 11:00 open kapalı
- `temmuzPoly/poly_trader_analiz6.py weekly` — Cumartesi 21:00 haftalık 6 ısı haritası
- `temmuzPoly/poly_trader_analiz15.py weekly` — Cumartesi 21:00 haftalık 15 ısı haritası
- `temmuzPoly/poly_trader_analiz5.py close/open` — **A1 Live**; WR>%85 → **$25** PM (slot gate)
- `temmuzPoly/poly_trader_analiz2_live.py close/open` — **A2 Live**; aynı slot gate ($25 force)
- `temmuzPoly/pm_weekend_sync.py close/open` — Cum **22:00** / Pzt **11:00** İST erken açılış; A1/A2/A10 Live Pzt **12:00**
- `temmuzPoly/poly_trader_analiz5_midcheck.py` — saat **:30** o saatin açık pozisyonu anlık değer + kotasyon görseli (TG)
- `temmuzPoly/poly_trader_analiz5.py weekly` — Cumartesi 21:00 haftalık 5 ısı haritası
- `temmuzPoly/poly_trader_analiz10.py close/open` — çift konsensüs **sanal**; Cum 22:00–Pzt 11:00 open kapalı
- `temmuzPoly/poly_trader_analiz10_live.py` — **A10 Live** :02/:05; slot gate WR>%85 → $25; Ayarlar anahtarı
- `temmuzPoly/pm_balance_hourly.py` — saat başı PM portföy kaydı; **00:00 İST** Telegram bakiye özeti; 3 saat peş peşe düşüşte 🔴 ALERT
- `temmuzPoly/poly_trader_5m_real_stats.py` — saat başı: 110 sanal PM Telegram özeti
- `temmuzPoly/algo_signals.py` — `:05` her saat: 36 algo sinyali → `/tmp/algo_signals.json`
- `temmuzPoly/algo_signals_v2.py` — `:05` her saat: 17 kârlı algo (Analiz 2) → `/tmp/algo_signals_v2.json`
- `temmuzPoly/poly_trader_a2.py` — `:02 close` / `:06 open` / Cmt 21:00 weekly: 17 sanal ($300; Cum 22:00–Pzt 11:00 open kapalı)
- `temmuzPoly/poly_trader_a2_{02,03,04,08}_live.py` — `:02 close` / `:06 open`: A2#02/#03/#04/#08 gerçek PM $4–5–6 (sanal ayrı; #03/#04 varsayılan kapalı)
- `temmuzPoly/poly_trader_15m_a2.py open` — 15M 309/316/317 sanal; **309 Live $3** sanal ile aynı anda/aynı sinyal (`*/15`)
- `temmuzPoly/poly_trader_15m_309_live.py` — 15M 309 Live mirror ($3; sanal mantık; pencere yok; `PM_15M_309_REAL_ENABLED`)
- `temmuzPoly/poly_trader_15m_a2.py weekly` — Pazar 00:00 haftalık 15M A2 Top3
- `freqtrade/run_analiz3.sh close/open` — **3. Analiz Freqtrade** saatlik sanal PM BTC+SOL+ETH (:02/:05)
- `jesse/run_analiz8.sh close/open` — **8. Analiz Jesse** saatlik sanal PM BTC+SOL+ETH (:02/:05)
# PASIF: `BistAnaliz/yuzdeBist.py` — crontab yorum satırı
# PASIF: `BistAnaliz/bist_scanner.py` — BIST Sinyal bildirim kapalı
- `temmuzPoly/poly_trader_5m_sol_110.py open` — 15M 110 SOL A32 **sanal** $8-10-12 (*/15, +1 sn)
- `temmuzPoly/poly_trader_5m_sol_110.py weekly` — Pazar 00:00 haftalık 110
# KALDIRILDI: `run_alfa.sh`, `poly_trader_alfa.py`, `alfa_signal.py`, `poly_trader_5m_sol_109.py`, `poly_trader_5m_sol_210.py`, …
# YOK (disk/crontab): `polyManuel/sol_bot.py`, `temmuzPoly/poly_trader.py`

## Sürekli Çalışan Servisler
- `web/poly_dashboard.py` — port **5050**; PID izle; yeniden başlatmak için: `nohup python3 /root/aiProject/web/poly_dashboard.py > /tmp/poly_dashboard.log 2>&1 &`

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.

**Poly analiz TG kuralı:** Tüm analizlerde Telegram yalnızca gerçek açılış veya kapanışta gider; “pozisyon yok / sinyal yok / skip / önizleme” log’a yazılır.
