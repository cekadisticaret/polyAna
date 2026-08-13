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
| `Sonnet/candle_pattern_engine1.py` | Mum pattern + S/D + confluence + `generate_report()` (grafik raporu) |
| `Sonnet/candle_pattern_engine.py` | v1 motor (yedek; grafik engine1 kullanır) |
| `web/poly_dashboard.py` | Poly dashboard **5050** — `/poly/grafik` mum analizi; `/algoritma-islemler` A1/A2/A6/V2/V3/A15/B1×3 + A2 Top-17 (7/24 sanal); `/poly/yapay-zeka-analiz` Poly Algo Analist bildirim akışı + Lider Analizi; `/kripto/yapay-zeka-analiz` Kripto Test AI Analist bildirim akışı + Lider Analizi; `/kripto` coin liderleri **SKILL + t** ile sıralanır (WR değil) |
| `temmuzPoly/repair_a2_sanal_settlement.py` | A2 sanal geçmişi PM slot open/close ile yeniden hesaplar (Binance 1h). |
| `scripts/watch_critical_files.py` | Kritik kaynak inotify izleyici — silinmede `ops/incidents/` olay kaydı |
| `ops/CRITICAL_FILE_RESTORE.md` | 2026-08-02 kaynak silinme / geri yükleme zaman çizelgesi |
| `ops/incidents/` | Silinme/eksik olay JSON+txt (process, git D, audit) |
| `AgustosKripto/` | Kripto Future — CR6 canlı + sanal Algoritmalar/Analizler; `bursaapp.com/kripto` |
| `AgustosKripto/virtual_book.py` | Sanal futures — net PnL + ATR kâr kilidi; cache + `/tmp/agustos_snap` |
| `AgustosKripto/atr_profit_lock.py` | ATR trailing kâr kilidi (**arm 1.0 / trail 0.5** — MFE'de işlemlerin %79'u 0.5 ATR'yi geçmiyordu) + zarar-stop (`2.0×ATR$`, min 10 dk yaş); `lock_history` (seviye/zaman/fiyat) |
| `AgustosKripto/Test/` | Poly sinyal kaynaklarının (A1/A2/B1 MUM vb.) sanal Binance Futures defterleri; `$100×6x` deposit $1000; 1h/4h coin+algo bazlı otomatik seçim; gerçek Binance komisyon oranı; **65 defter** = 61 ayna + 4 PRO; `bursaapp.com/kripto/test` |
| `AgustosKripto/Test/kripto_test_analyst.py` | Kripto Test AI Analist — 3 saatte bir Kripto Test defterleri arasında ayrışma bulur, Anthropic API ile doğal dilde yorum üretir, Telegram'a (LAB bot, ayrı kanal) gönderir, tam metni `kripto_analyst_feed.jsonl`'a kaydeder; `bursaapp.com/kripto/yapay-zeka-analiz` |
| `AgustosKripto/Test/analog.py` | Analog pencere eşleştirme — son 48 mum z-score şekli → 270k geçmiş pencerede korelasyon → ileri getiri dağılımı + güven skoru; `build`/`query`/`eval` |
| `AgustosKripto/Test/backtest_fast.py` | `backtest_1y` ile birebir aynı sonuç, ön hesaplı dilim (4 faz hizalı 4h + normalize 1h + ATR memo); A2'de 34x, A6'da 5.4x; `--books`/`--source`/`--verify` |
| `AgustosKripto/Test/horizon_sweep.py` | Tutma süresi taraması — sinyal → 1/2/4/8/12/24/48s getiri; imzalı brüt **ve** drift-nötr SKILL (küme-dayanıklı SE); `--symbols` evren kısıtı, `--per-symbol` coin kırılımı (edge_gate girdisi) |
| `AgustosKripto/Test/edge_gate.py` | **Ölçülen kenar kapısı** — (defter, coin) çifti yalnız 1Y SKILL komisyonu aşarsa ve t eşiğini geçerse işlem açar; `proven` t≥3 tam kademe · `candidate` t≥2 çeyrek kademe · diğer kapalı. Tablo yoksa **kapalı** (varsayılan güvenli). `--build` / `--show` |
| `AgustosKripto/Test/backtest_pro4.py` | Çıkış rejimi taraması (A2#05·A6V3·B1#03·MELEZ) — saatlik zorunlu kapanış vs sinyal-dönene-kadar, taker/maker, 4h, majör evren; SKILL/t + kapanış gerekçesi dökümü |
| `AgustosKripto/Test/minute_data.py` | Maker fill sim için 1m OHLC cache — `fetch`/`info`; `data/minute_cache/*_1m.npz` (30 coin × 90g ≈ 3.9M mum, ~28 MB) |
| `AgustosKripto/Test/maker_sim.py` | Limit emir fill simülasyonu — analog sinyal + 1m low/high; offset × pencere × ters seçilim; taker vs maker karşılaştırma |
| `AgustosKripto/fee_utils.py` | Binance komisyon — estimate + userTrades; brüt→net; `get_taker_rate` / `get_maker_rate` |
| `AgustosKripto/skill_audit.py` | Kalıcı denetim — drift-nötr `SKILL` = (ort. LONG% + ort. SHORT%)/2, `DRIFT`, t-istatistiği; defter/coin/konsensüs/güven kırılımı + MFE dağılımı + maker senaryosu. `--leaders` `--mfe` `--consensus` `--conviction` `--all` |
| `AgustosKripto/conviction_filter.py` | Yüksek güven vetosu — oy birliği (4/4) sinyalleri açılmaz; ölçülen SKILL −0.065% (t=−3.89, 5/5 dilim). Vetolananlar `conviction_shadow.jsonl` gölge defterine yazılır; ters açma **kapalı** (kanıt yetersiz). Ayar: `conviction_filter.json` |
| `AgustosKripto/funding_harvest.py` | Funding hasadı tarayıcı (delta-nötr) — perp funding oranı + `fundingIntervalHours` (4h/8h sembole göre) → yıllık %, başabaş süre, likidite skoru; **emir açmaz**, `--tg` ile rapor |
| `AgustosKripto/algo_tg_notify.py` | Kripto sanal algo TG — **10. ANALİZ kanalı** (`poly_analiz_dual_core` bot); close/open özeti 🔶 SANAL |
| `AgustosKripto/Algoritmalar/` | ALGO2+ALGO1 sanal $300; **tüm 51 defter open $30×10x** max6 (komisyon dahil net PnL); A2#05/#06/#07 + A1#11 ayrıca gerçek Binance'te $7×20x (`real_live`); hafta sonu skip; `reset` |
| `AgustosKripto/Analizler/` | A1–A10 + A6(Supertrend $10×15x max4); ATR runner; A3/A8 venv |
| `AgustosKripto/binance_futures_client.py` | Binance USD-M REST — emir, bakiye, commissionRate, userTrades, `book_ticker`, `query_order`, `premium_index`, `funding_info` |
| `AgustosKripto/crypto_futures_trader.py` | Futures open/close + `dust` süpürme (|notional|≤$2); brüt/komisyon/net; `open_maker` (post-only GTX limit, tick yuvarlama, dolmazsa iptal) |
| `AgustosKripto/crypto_futures_cr6.py` | **Algoritmalar Live** (gerçek Binance) — Hurst+A1#11 MR+Z-Score MR+Mean Reversion çoğunluk oyu; top-N; $7×20x; **yeni open BTC/ETH/BNB yok**; ATR/hard SL; `fcntl` state kilidi + atomik yazım, `order_id` idempotency (hayalet pozisyon temizliği), `MAX_HOLD_HOURS` |
| `AgustosKripto/crypto_futures_live_control.json` | Binance Live — `live_paused` (yeni açılış) + `top_n` (1–10); sanal Algoritma/Analiz etkilenmez |
| `AgustosKripto/cr6_tg_card.py` | Algoritmalar Live TG sarı kart (ALGO2 stili) — açılış/kapanış/ATR photo |
| `AgustosKripto/crypto_futures_config.json` | Sembol allowlist + default $6 / 10x; `CRYPTO_FUTURES_LIVE` + CR6 canlı; `entry_mode: maker` + `maker_wait_sec: 90` |
| `temmuzPoly/analiz5_settings.json` | A1/A2/A10/A6 Live WR giriş tutarları (düşük/orta/yüksek) |
| `temmuzPoly/pm_profit_baseline.json` | PM Kar başlangıç bakiyesi (varsayılan $314); Toplam Kar = nakit − baseline. |
| `temmuzPoly/` | Poly trader'lar, algo motorları, backtest; dashboard port **5050**. |
| `crypto-news-monitor/` | Kripto haber/tweet tarayıcı — RSS + opsiyonel Twitter, Claude skor, Telegram alarm (30 dk cron) |
| `twitter_bot/` | @tradecomio otomatik tweet — `post_tweet.py` (tweepy, OAuth1.0a v2+v1.1 medya), `render_card.py` (Pillow "İşlem Sonucu" görsel kartı), `tweet_trade_card.py` (saatlik cron: son 3 saatteki en başarılı Test işlemi → giriş/kapanış/kâr% kart; yeni kazanan yoksa atlar, `data/trade_card_state.json` dedupe) |
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
| `temmuzPoly/pm_trader_helpers.py` | PM emir + sanal kotasyon; gerçek PM WR giriş (`load_pm_live_amounts` / `analiz5_settings.json`); slot tutarı: zayıf saat -%30, hot-hour büyütme **kapalı** (`HOT_HOUR_BOOST=1.0`) |
| `temmuzPoly/telegram_poly_channels.py` | Poly TG kanal yönlendirme — `TELEGRAM_ANALIZ1_CHAT_ID` yalnızca 1. ANALİZ; diğer trader'lar `TELEGRAM_POLY_TRADERS_CHAT_ID` / `TELEGRAM_PM_LIVE_CHAT_ID` vb. (analiz1 kanalına asla düşmez) |
| `temmuzPoly/pm_manual_sync.py` | Manuel PM — Polymarket activity → manual state senkron (5/15dk + saatlik) |
| `temmuzPoly/poly_trader_manual.py` | Manuel PM slot-sonu otomatik settle (`close`) — 5m/15m/1h |
| `temmuzPoly/pm_orphan_sync.py` | Ghost PM — zincirde açık ama state'te yok pozisyonları live trader'a yazar (trader sembol allowlist) |
| `temmuzPoly/pm_poly_history.py` | Polymarket data-api activity → slug bazlı gerçek PM geçmişi + açık (bekleyen) işlemler |
| `temmuzPoly/pm_balance_guard.py` | PM USDC bakiye + `pm_system_control.json` dashboard açılış anahtarı (A1 Live · A2 ayrı; sanal trader'lar etkilenmez). Geçerli grup listesi `_VALID_GROUPS` — **15 Live anahtarının tek doğru kaynağı**, dashboard bu listeye göre doğrular |
| `temmuzPoly/pm_weekend_sync.py` | Cum 22:00 / Pzt 11:00 İST — A1 Live + A2 dashboard anahtarlarını otomatik kapat/aç |
| `temmuzPoly/btc_analiz1_algo.py` | 1. Analiz tam algoritma (standalone kopya, poly_predictor ile aynı) |
| `temmuzPoly/poly_trader_analiz1.py` | 1. Analiz sanal (BTC+SOL); $12-16-20 WR; PM net kazanç ≥%50 yoksa giriş yok; top-3 saatte +%50; 12:00 yarı; **hafta sonu da açık** |
| `temmuzPoly/poly_trader_analiz2.py` | 2. Analiz sanal (SOL only; $300; PM net kazanç ≥%50 yoksa giriş yok; **ALLOW_FALLBACK=False**) |
| `temmuzPoly/poly_trader_analiz2_live.py` | 2. Analiz **canlı PM** SOL; slot gate zayıf saat -%30; PM net ≥%50 |
| `temmuzPoly/backtest_common.py` | 1Y walk-forward backtest ortak yardımcılar |
| `temmuzPoly/backtest_analiz2.py` | 2. Analiz 1Y walk-forward backtest (SOL, predict motoru) |
| `temmuzPoly/backtest_analiz1.py` | 1. Analiz 1Y walk-forward backtest (BTC+SOL, predict motoru) |
| `temmuzPoly/backtest_analiz_suite.py` | 10. Analiz 1Y backtest ($1000, algo import — canlıya dokunmaz) |
| `temmuzPoly/analiz15_signal.py` | 15. Analiz sinyal — BTC→A6 MACD, ETH→A8 Jesse, SOL→A2 predictor |
| `temmuzPoly/poly_trader_analiz15.py` | 15. Analiz sanal (BTC+ETH+SOL); Cum 22:00–Pzt 11:00 open kapalı; TG A4 botu; $300 |
| `temmuzPoly/backtest_algo_catalog.py` | 78 algo 1Y yön backtest (BTC+ETH+SOL 1h) → `backtest_algo_catalog_1y.json` |
| `temmuzPoly/backtest_algo_catalog_notify.py` | Top-30 algo 1Y P&L özeti + Telegram (`--send`) |
| `temmuzPoly/poly_trader_analiz5_midcheck.py` | A1 Live açık pozisyon :30 anlık değer + PM kotasyon görseli (TG) |
| `temmuzPoly/poly_trader_analiz5.py` | **A1 Live** — gerçek PM; slot gate: zayıf saat -%30 (hot-hour büyütme kapalı) |
| `temmuzPoly/poly_analiz_dual_core.py` | 10. Analiz çift konsensüs ortak motor (A1+A4; PM net kazanç ≥%50 filtresi) |
| `temmuzPoly/poly_trader_analiz10.py` | 10. Analiz çift konsensüs sanal (BTC+SOL, $300); Cum 22:00–Pzt 11:00 open kapalı |
| `temmuzPoly/poly_trader_analiz10_live.py` | A10 Live gerçek PM; slot gate (zayıf saat -%30); PM net ≥%50 yoksa giriş yok |
| `temmuzPoly/poly_trader_analiz6.py` | 6. Analiz sanal (BTC+SOL+ETH); TG=15. Analiz (A4 botu); A6 Live eşleme; **hafta sonu da açık** |
| `temmuzPoly/poly_trader_analiz6_v2.py` | 6. Analiz V2 sanal (BTC+ETH only); A6V2 Live eşleme; **hafta sonu da açık** |
| `temmuzPoly/poly_trader_analiz6_v3.py` | 6. Analiz V3 sanal (BTC/ETH→A6 · SOL→A2); A6V3 Live eşleme; **hafta sonu da açık** |
| `temmuzPoly/poly_trader_analiz6_v4.py` | **A2#05 X A6V3 MELEZ** sanal — V3 iskeletini import edip globalleri yönlendirir (V3 dosyası dokunulmaz); BTC→MACD Div #26 · ETH/SOL→Mean Rev ($300); defter anahtarı `melez` · URL `/algoritma-islemler/melez` |
| `temmuzPoly/poly_trader_b1_01.py` | B1#01 sanal — sembol bazlı en iyi motor birleşimi ($300); **hafta sonu da açık** |
| `temmuzPoly/b1_01_signal.py` | B1#01 motor seçimi — algoritma-islemler WR taraması |
| `temmuzPoly/poly_trader_b1_02.py` | B1#02 sanal — sabit BTC→A15 · ETH→A6 · SOL→A2#01 ($300); **hafta sonu da açık** |
| `temmuzPoly/poly_trader_b1_mum.py` | B1#03 MUM ANALİZ sanal — Sonnet mum confluence 1h ±15 ($300); TG; **hafta sonu açık** |
| `temmuzPoly/poly_trader_b1_04.py` | B1#04 sanal — 23 birincil motorun edge-ağırlıklı küme konsensüsü ($300); :02 close / :07 open |
| `temmuzPoly/b1_04_signal.py` | B1#04 karar motoru — kopya defterleri tek oya indirir, oyları başabaşa göre ölçülmüş edge ile ağırlıklandırır; eşik `B1_04_MIN_EDGE` (varsayılan **0.0** = oylama yön gösterince gir) |
| `temmuzPoly/b1_04_backfill.py` | B1#04 geçmişini A2#05 slotlarında walk-forward simüle edip doldurur (`--write`); kayıtlar `backfill: true` |
| `temmuzPoly/poly_trader_b1_05.py` | **B1#05** sanal — coin başına en iyi motor ($300); B1#01 iskeletini import edip globalleri yönlendirir (B1#01 dosyası dokunulmaz); :02 close / :06 open · URL `/algoritma-islemler/b1_05` |
| `temmuzPoly/b1_05_signal.py` | B1#05 eşleme motoru — B1#01 ile aynı fikir ama havuzda **b1_mum + melez** da var (dashboard "coin başına en iyi" kartıyla birebir); türev defterler (b1_01/02/04/05, analiz2) havuz dışı; eşleme her open turunda yeniden hesaplanır → `b1_05_mapping.json` |
| `temmuzPoly/b1_05_backfill.py` | B1#05 geçmişini A2#05 slotlarında walk-forward doldurur (`--write`); seçilen motorun o slottaki gerçek kaydından yön/fiyat/sonuç alır, motor o slotta işlem açmamışsa atlar; `algo_name` = `B1#05←<motor>` (motor bazlı isabet dökümü için) |
| `temmuzPoly/poly_trader_b1_05_live.py` | **B1#05 Live** — gerçek PM, kademe `/ayarlar` → İşlem Miktarları'ndan ayarlanır (varsayılan $4/5/6); sanal B1#05'i aynalar (bağımsız sinyal yok); tek otorite dashboard Ayarlar anahtarı, **varsayılan kapalı**; :02+:12 close / **:06:30** open (`sleep 30`; sanal :06 sonrası); `min_profit_ratio=None` → PM kâr kapısı yok, **sanal ne açarsa aynısı**. ⚠️ Backfill kenar bulamadı — kademe bilerek en düşük |
| `temmuzPoly/poly_trader_b1_mum_live.py` | **B1#03 MUM Live** — gerçek PM, kademe `/ayarlar` (varsayılan $6/8/10); sanal B1#03 MUM'u aynalar; dashboard anahtarı, **varsayılan kapalı**; :02+:12 close / :06 open (sanal :05 state sonrası) |
| `temmuzPoly/algo_islemler_fresh_start.py` | Algoritma-islemler close + bakiye $300 sıfırla (cron open bekler) |
| `temmuzPoly/algo_islemler_defer_to_next_hour.py` | (ops) open erteleme — normalde kullanma |
| `temmuzPoly/b1_02_signal.py` | B1#02 sabit sembol→motor eşlemesi |
| `temmuzPoly/analiz6_v3_signal.py` | A6V3 sinyal — BTC/ETH A6, SOL A2 (algo→predict kline dönüşümü) |
| `temmuzPoly/analiz6_v4_signal.py` | MELEZ sinyal — her sembolde uzun dönem isabeti en yüksek motor: BTC→`macd_histogram_div` (%55,0), ETH/SOL→`mean_reversion` (%54,2 / %53,2) |
| `temmuzPoly/analiz6_v4_backfill.py` | MELEZ geçmişini A6V3 (BTC) + A2#05 (ETH/SOL) defterlerinin gerçek kararlarından walk-forward kurar (`--write`); kayıtlar `backfilled: true` |
| `temmuzPoly/backtest_a2_a6_melez_1y.py` | A2#05 · A6V3 · MELEZ — 1Y walk-forward backtest (BTC/ETH/SOL); ay ay Telegram (`--telegram`) |
| `temmuzPoly/poly_trader_analiz6_v2_live.py` | A6V2 Live gerçek PM (BTC+ETH); dashboard toggle |
| `temmuzPoly/poly_trader_analiz6_v3_live.py` | A6V3 Live gerçek PM (BTC+ETH+SOL); dashboard toggle |
| `temmuzPoly/poly_trader_analiz6_live.py` | A6 Live gerçek PM; slot gate zayıf saat -%30; sanal A6 adayları |
| `temmuzPoly/poly_live_hourly_common.py` | Saatlik gerçek PM ortak açılış yardımcıları |
| `temmuzPoly/poly_trader_manual_state.json` | Manuel PM işlemleri state (dashboard açık pozisyon) |
| `temmuzPoly/analiz32_5m_adapter.py` | 5M110Analiz → 5m sinyal adaptörü (algo bozulmaz) |
| `temmuzPoly/analiz32_15m_adapter.py` | 5M110Analiz → 15m sinyal adaptörü (110 SOL) |
| `temmuzPoly/poly_trader_5m_sol_110.py` | 15M 110 SOL — A32 **sanal** $8-10-12; Cum 22:00–Pzt 11:00 open kapalı |
| `temmuzPoly/analiz32_15m_signal_snapshot.py` | 110 15m sinyal snapshot kaydı |
| `temmuzPoly/pm_balance_hourly.py` | PM portföy saatlik kayıt + 00:00 Telegram özeti + 3 saat peş peşe düşüş ALERT |
| `temmuzPoly/poly_algo_analyst.py` | Poly Algo Analist — 3 saatte bir A1/A6 ailesi/A2#01-17/A10/A15/B1#01-02 arasında ayrışma bulur, Anthropic API ile doğal dilde yorum üretir, Telegram'a gönderir, özeti `analyst_journal.jsonl`'a kaydeder |
| `temmuzPoly/algo_pattern_stats.py` | Defterler arası kalıp istatistikleri — Wilson güven aralığıyla "ikisi aynı yönde açtığında kazanma oranı" ve "indikatör oybirliği" hesaplar (N>=8 izlemede, N>=20 güvenilir); `pattern_stats.json` |
| `temmuzPoly/analyst_common.py` | Analist scriptleri ortak yardımcıları (.env, dashboard API, Telegram, Claude çağrısı) |
| `temmuzPoly/poly_algo_daily_report.py` | Poly Algo Analist Günlük Rapor — 00:00 İST; günlük defter özeti + o gün eşik atlayan yeni kalıplar; `analyst_daily_reports.jsonl` |
| `temmuzPoly/poly_trader_5m_real_stats.py` | 15M 110 sanal saatlik Telegram özeti |
| `temmuzPoly/algo_signals.py` | 36 saatlik algo sinyali (BTC/ETH/SOL); `/tmp/algo_signals.json` |
| `temmuzPoly/algo_signals_v2.py` | 17 kârlı algo (Analiz 2 sekmesi); `/tmp/algo_signals_v2.json` + `algo_accuracy_v2.json` |
| `temmuzPoly/poly_trader_a2.py` | A2 Top 17 sanal trader ($300, $8/$12/$16); `poly_trader_a2_XX_{state,history}.json` |
| `temmuzPoly/poly_a2_algo_live_core.py` | A2 Live ortak çekirdek — gerçek PM open/close |
| `temmuzPoly/poly_trader_a2_02_live.py` | A2#02 RSI Div Live — $4/5/6; sanal #02 ayrı; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_08_live.py` | A2#08 Williams Live — $4/5/6; sanal #08 ayrı; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_03_live.py` | A2#03 Stoch RSI Live — $4/5/6; sanal #03 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_trader_a2_04_live.py` | A2#04 Schaff Live — $4/5/6; sanal #04 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_a2_algo_live_core.py` | A2 Live çekirdeği — sanal defter mirror/sync (309 gibi); open :07; `A2LiveSpec.min_profit_ratio` ile PM kâr kapısı defter bazlı (`None` = tam ayna) |
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
- `temmuzPoly/poly_trader_analiz1.py close/open` — 1. Analiz BTC+SOL **sanal** ($300); hafta sonu da çalışır
- `temmuzPoly/poly_trader_analiz1.py weekly` — Cumartesi 21:00 haftalık 1 ısı haritası
- `temmuzPoly/poly_trader_analiz1.py daily` — her gün 00:00 İST günlük işlem geçmişi (TG)
- `temmuzPoly/poly_trader_analiz2.py close/open` — 2. Analiz **SOL only** sanal ($300, $12-16-20 WR); open Cum 22:00–Paz 18:00 İST kapalı
- `temmuzPoly/poly_trader_analiz2_live.py close/open` — 2. Analiz **canlı PM** SOL $6-7-8 WR (`PM_ANALIZ2_REAL_ENABLED`; :02/:05; hafta sonu dashboard anahtarı)
- `temmuzPoly/poly_trader_analiz2.py weekly` — Cumartesi 21:00 haftalık 2 ısı haritası
- `temmuzPoly/poly_trader_analiz6.py close/open` — 6. Analiz sanal; **open** aynı adayda A6 Live gerçek PM dener (`PM_ANALIZ6_LIVE_ENABLED` + dashboard)
- `temmuzPoly/poly_trader_analiz6_v2.py close/open` — 6. Analiz V2 sanal (BTC+ETH); A6 ile aynı indikatör; SOL yok; Live yok
- `temmuzPoly/poly_trader_analiz6_live.py close` — A6 Live kapanış :02; open sanal A6 open ile tetiklenir
- `AgustosKripto/crypto_futures_cr6.py close/open/trail` — **Algoritmalar Live** (gerçek Binance); Hurst+A1#11 MR+Z-Score MR+MR çoğunluk oyu; top-4 majors önce; $7×20x; ATR kâr kilidi; giriş **maker** (dolmazsa iptal, işlem atlanır); `MAX_HOLD_HOURS` slot kilitlenmesini önler
- `AgustosKripto/skill_audit.py` — elle; **20.826 işlem / 5,2 gün** denetimi: brüt PnL −$694 (t=−0,91 ≈ sıfır), komisyon $9.334 → net **−$10.027**. Eşiği geçen defter **2/103** (şans beklentisi ~26 → gerçek kenar yok). Konsensüs ters çalışıyor: **tam uzlaşı ≥%95 SKILL −%0,066 t=−2,15**, bölünmüş <%65 pozitif. MFE: işlemlerin **%79'u 0,5 ATR'yi geçmiyor** ve tüm zararı bu bant yapıyor (−$19.984)
- **Ölü bant filtresi kurulamaz:** MFE ancak kapanışta bilinir, giriş anında vekil değişken aranmalı. Denenen tüm giriş özellikleri (ATR%, saat, interval, tutma süresi) ileri testte çöktü — eğitimin seçtiği "en iyi 6 saat" testte t=−1,85'e döndü (aşırı uydurma kanıtı). LONG/SHORT asimetrisi drift, yetenek değil
- **Yerine kurulan — güven vetosu:** algo içi skor yüzdeliğinin **üst %20'si** SKILL −%0,065 · t=−3,89 · **5/5 zaman diliminde negatif** · DRIFT yalnız +%0,014 (yani piyasa yönü değil). 52 defterin 37'sinde (%71) mevcut. Konsensüs kesitiyle bağımsız olarak aynı sayı (−0,065 / −0,066). Üst kova atılınca kalanın SKILL'i **−0,000%** — zarar durur, kâr başlamaz. Ters açmanın maker sonrası beklentisi +%0,025 ama **%95 aralık [−0,007%, +0,057%] sıfırı kesiyor** → gerçek parayla ters işlem yok, gölge defter toplanıyor
- `AgustosKripto/funding_harvest.py` — elle / `--tg`; funding oranı taraması, yön riski yok; sembol başına gerçek `fundingIntervalHours` (4h/8h) ile yıllıklandırma
- `AgustosKripto/Algoritmalar/runner.py close/open/trail/reset` — sanal $300; tüm 51 defter open $30×10x; close/open TG → **10. ANALİZ kanalı** (🔶 SANAL); Cum 22:00–Pzt 11:00 İST skip
- `AgustosKripto/Analizler/runner.py close/open/trail` — A1–A10 + A6(Supertrend $10×15x max4) + ATR trail
- `AgustosKripto/Test/runner.py close/open/trail/scan` — Poly sinyal kaynaklı sanal defterler; `$100×6x`; `scan` 10 dk'da bir erken sinyal yakalar (`:05` beklemeden). **PRO defterleri** (`pro_a2_05` · `pro_analiz6_v3` · `pro_b1_mum` · `pro_melez`) `close`'ta saatlik settle edilmez; yalnız süre sınırı (`max_hold_h`, kapının verdiği ufuk / tavan 48s), ters sinyal (`scan`) ve ATR stopu (`trail`) kapatır; açılış `edge_gate`'ten geçmek zorunda
- **Poly→Kripto uyumsuzluğu (ölçüldü, 2026-08-12):** Aynı sinyal Poly'de kâr, kriptoda zarar. Sebep komisyon oranı değil **başabaş eşiği**: Poly'de başabaş = piyasa fiyatı ≈ %49,8 (binary 1:1 ödeme), kriptoda = komisyon + ödeme şekli ⇒ A2#05 %61,7 · A6V3 %70,4 · B1#03 %44,6. Yani kriptoda kâr için ~12 puan daha isabet gerekiyor. 1Y ölçüm (181 bin sinyal, 7 ufuk, drift-nötr SKILL) 4 defterin hiçbirinde komisyonu aşan kenar bulamadı — tek yakın aday A6V3 majör 48s (+%0,109 · t=+2,65) ve o da 840 testlik çoklu-test düzeltmesini geçmiyor. Çözüm bu yüzden "daha iyi ayar" değil **kanıt şartı** (`edge_gate`): kenar yoksa pozisyon açılmaz
- **Çıkış rejimi ölçümü (1Y, `backtest_pro4.py`):** saatlik zorunlu kapanış A2#05'e 34.692 işlem yükledi (−$26.552); aynı sinyal sinyal-dönene-kadar tutulunca 5.841 işlem (−$11.811) → komisyonun **%83'ü** kalkıyor. Kayıp küçülüyor ama kenar olmadığı için kâra dönmüyor; bu yüzden PRO rejimi kapı ile birlikte çalışır
- `AgustosKripto/Test/analog.py build/query/eval` — cron yok, elle çalışır; indeks `data/analog_index.npz` (52 MB, 270k pencere). **180g eval** (k=5000, step=4): isabet %49, ort. imzalı getiri **−%0,0023**; üst güven kovasında en fazla +%0,03 — komisyon sonrası işe yaramaz
- `AgustosKripto/Test/backtest_fast.py` — elle; profil sürenin %92'sinin format dönüşümünde geçtiğini gösterdi (`_resample_4h` %59, `_bars_ohlc` %33) → coin başına bir kez ön hesap. A2 Top-17 1Y: 6541s → dakikalar. Sonuçlar `backtest_1y` ile birebir (`--verify`)
- `AgustosKripto/Test/horizon_sweep.py` — elle; A1/A6/A6V2/A6V3 1Y taraması: **hiçbir ufuk %0,10 komisyonu aşmıyor**; edge süreyle büyümüyor, azalıyor (A1 4s'te −%0,056 t=−2,33; A6V3 8s'te −%0,048 t=−2,64). En iyi brüt A6 2s +%0,008 — komisyonun 12'de biri. **A6 = A6V2 birebir aynı** (30 coinlik evrende 27 coin aynı varsayılana düşüyor)
- `AgustosKripto/Test/minute_data.py fetch` — elle; 30 coin × 90g 1m OHLC (`data/minute_cache/`, ~28 MB)
- `AgustosKripto/Test/maker_sim.py` — elle; 88g üst %10 (3180 sinyal): taker net/sinyal **−%0,095**; maker fill **ters seçilim** (dolanlar kötü, kaçanlar brüt +%0,13…+%0,76); limit emir kurtarmıyor
- `twitter_bot/tweet_trade_card.py` — `20 * * * *` saatlik: son 3 saatteki en yüksek %kârlı Test işlemi → giriş/kapanış/kâr görsel kart → @tradecomio tweet; yeni kazanan yoksa atlar (`/tmp/twitter_trade_card.log`)
- `temmuzPoly/poly_trader_analiz15.py close/open` — **15. Analiz** BTC→A6 · ETH→A8 · SOL→A2 sanal ($300); Cum 22:00–Pzt 11:00 open kapalı
- `temmuzPoly/poly_trader_analiz6.py weekly` — Cumartesi 21:00 haftalık 6 ısı haritası
- `temmuzPoly/poly_trader_analiz15.py weekly` — Cumartesi 21:00 haftalık 15 ısı haritası
- `temmuzPoly/poly_trader_analiz5.py close/open` — **A1 Live**; slot gate: zayıf saat -%30 (hot-hour büyütme kapalı)
- `temmuzPoly/poly_trader_analiz2_live.py close/open` — **A2 Live**; aynı slot gate (zayıf saat -%30)
- `temmuzPoly/pm_weekend_sync.py close/open` — Cum **22:00** / Pzt **11:00** İST erken açılış; A1/A2/A10 Live Pzt **12:00**
- `temmuzPoly/poly_trader_analiz5_midcheck.py` — saat **:30** o saatin açık pozisyonu anlık değer + kotasyon görseli (TG)
- `temmuzPoly/poly_trader_analiz5.py weekly` — Cumartesi 21:00 haftalık 5 ısı haritası
- `temmuzPoly/poly_trader_analiz10.py close/open` — çift konsensüs **sanal**; Cum 22:00–Pzt 11:00 open kapalı
- `temmuzPoly/poly_trader_analiz10_live.py` — **A10 Live** :02/:05; slot gate zayıf saat -%30; Ayarlar anahtarı
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
- `web/poly_dashboard.py` — port **5050**; `systemctl restart poly-dashboard.service` (PID izlemek için: `pgrep -af poly_dashboard.py`)

### Ayarlar Live anahtarları (`/ayarlar`)
- 15 satır, `pm_balance_guard._VALID_GROUPS` ile birebir: A1 · A2 · A10 · A6 · A6V2 · A6V3 · A2#16 · A2#02 · A2#03 · A2#04 · A2#05 · A2#06 · A2#07 · A2#08 · A15
- `POST /poly/api/pm-system` **grup adı geldiyse asla ana şaltere düşmez**; bilinmeyen ad `400` döner. Grup adı hiç yoksa (eski çağrı) ana şalter çalışır — hepsini birlikte çevirir
- **2026-08-12 hatası:** POST'ta ayrı bir sabit grup listesi vardı ve `analiz6_v2_live` / `analiz6_v3_live` bu listede yoktu. A6V3'e basınca istek `else` dalına düşüp `toggle_pm_open_paused()` çağırıyor, yani **15 Live defterin hepsini birlikte** açıp kapatıyordu. Liste kaldırıldı; doğrulama tek kaynağa (`_VALID_GROUPS`) bağlandı. A2#16 ve A2#02'nin ayar satırı da yoktu (kaza ile kapanıp geri açılamıyorlardı) — eklendi

## Ayna API — dış sunucu (2026-08-13)
Başka bir sunucunun ":06'da A6V3 ne açtı?" diye sorup aynı işlemi kendi tarafında açması için **salt okunur** uç. Emir tetiklemez, hiçbir state dosyasına yazmaz.

| Uç | Ne döner |
|---|---|
| `GET /poly/api/mirror` | 29 defter — bakiye → net PnL → WR sırası; her satırda `sanal_balance`, `initial_balance` ($300), `total_pnl`, `wr`, `trades` |
| `GET /poly/api/mirror/<defter>` | Açık pozisyonlar + aynı defterin `sanal_balance` / WR özeti |

- **Kimlik:** `X-Mirror-Token` başlığı (ya da `?token=`), `.env` → `MIRROR_API_TOKEN`, `secrets.compare_digest`. **Token tanımlı değilse uç tamamen kapalı** (`401`) — yanlışlıkla açık kalmaz.
- **Defter adı esnek:** `a6v3` · `A6V3` · `analiz6_v3` · `b1#05` · `a2#05` · `5` hepsi çözülür. Takma adlar `_OVERVIEW_SHORT_LABELS`'tan **türetilir** (`_ALGO_SHORT_ALIASES`), elle ikinci liste tutulmaz — yeni defter eklenince kısa adı kendiliğinden çalışır.
- **Pozisyon alanları:** `symbol` · `dir` · `amount_usd` · `pm_slug` · `pm_title` · `pm_entry_price` (sanalın gördüğü fiyat) · `pm_size` · `entry_time_tr`. `?market=1` (varsayılan) ile Gamma'dan ek olarak **`pm_token_id`** (doğrudan emir için), `pm_price_now`, `pm_price_drift_pct`, `pm_tick_size`, `pm_neg_risk`. Gamma cevabı 45 sn cache'lenir; hata olursa `pm_market_error` gelir, çekirdek alanlar yine döner.
- **`is_current_slot`:** pozisyon içinde bulunulan saate mi ait. Kapanış hata verip önceki saatten pozisyon kalırsa aynalayan taraf onu yanlışlıkla açmasın diye. `age_sec` de var — bu projede gecikme kaynaklı kaymanın bedeli ölçüldü (59 sn = %34 pahalı giriş), aynalayan taraf yaşa bakıp vazgeçebilmeli.
- Kod: `poly_dashboard.py::_mirror_token_ok` · `_mirror_market` · `_mirror_rows` + iki rota.

## CoptC — bağımsız kopya (2026-08-12)
`CoptC/` bu projeden **tamamen bağımsız**, başka sunucuya taşınmak için hazırlanmış bir paket: **B1#05**, **B1#03 MUM** ve **A1** (her biri sanal + gerçek PM) + kendi dashboard'u. Ana proje ile hiçbir dosya paylaşmaz — cron/servis/veri yolları ayrı.

| Yol | Ne yapar |
|---|---|
| `CoptC/runner.py` | Tek giriş: `close` (:02) · `open` (:05) · `live-open` (:06) · `settle` (:12) · `status` |
| `CoptC/poly/` | 33 motor/trader modülü + 46 state/history JSON (temmuzPoly düzeninin kopyası) |
| `CoptC/poly/pool_tracker.py` | B1#05'in aday havuzundaki 22 defteri her saat gölge notlar — eşleme donmasın |
| `CoptC/poly/poly_trader_analiz1.py` · `poly_trader_analiz5.py` | A1 sanal (BTC+SOL, $12/16/20) + A1 Live (gerçek PM, `a1_amount_*`) |
| `CoptC/Sonnet/candle_pattern_engine1.py` | B1#03 MUM'un mum motoru (`importlib` ile dinamik yükleniyor) |
| `CoptC/web/dashboard.py` · `api.py` | Panel, port **5060**, defter sekmeli + para çekme kartı |
| `CoptC/poly/pm_transfer.py` | Bridge + relayer transferi (ana projeden kopya, gömülü sır yok) |
| `CoptC/deploy/` | `crontab.txt` + `coptc-dashboard.service` |

- **Çakışma önlemi:** kopyalardaki `/tmp/algo_signals*.json` → `/tmp/coptc_*` olarak ayrıldı; aynı makinede iki proje birlikte koşarsa sinyal dosyaları birbirini ezmez.
- **Cron sadeleşti:** `runner.py open` a2 sinyallerini kendi ürettiği için B1#05 artık ana projedeki `:06`/`:06:30` gecikmesini beklemiyor — ikisi de `:05` sanal, `:06` live.
- **Güvenlik:** üç Live defteri de **kapalı** kurulur (`CoptC/poly/pm_system_control.json`), `.env` yoksa `POLY_DRY_RUN=true` ile emir gitmez, panelde `COPTC_PASSWORD` ile oturum koruması var.
- **A1 dahil edildi (2026-08-13):** Sanal `poly_trader_analiz1.py` + gerçek PM `poly_trader_analiz5.py` (isim ana projeden miras; A1'in canlısı "analiz5" dosyasında). Diğer iki defterden **yapısal farkı**: A1 Live sanalı aynalamıyor, `poly_predictor_analysis.predict()` ile kendi sinyalini çözüyor — bu yüzden `:06`'yı beklemesi anlamsız, `runner.py open` içinde `:05`'te sanalın hemen ardından koşuyor (beklemek yalnız giriş fiyatını kötüleştirirdi). Semboller BTC+SOL (ETH yok), sanal kademe kod içinde sabit **$12/16/20**, gerçek PM kademesi panelden **`a1_amount_*`** ($10/12/14 kurulur) — yani paneldeki tutar kartı A1 sekmesinde yalnız canlıyı etkiler.
- **A1 Live geçmişi taşındı (296 işlem), sıfırlanmadı:** `resolve_open_slot_gates(history, …)` defterin **kendi** geçmişinden zayıf-saat kesintisini (−%30) hesaplıyor; sıfırlansaydı kapı körleşirdi. Bedeli: panelde "live" geçmiş/saat ızgarası eski cüzdanın 08-05'e kadarki işlemlerini gösteriyor. B1#05/MUM Live'lar zaten boştu, onlar sıfır başlıyor.
- **`analiz5` fail-open açığı kapatıldı:** ana projede `_DEFAULT_OPEN_GROUPS = {analiz5, analiz2, analiz10}`, yani `pm_system_control.json` yoksa/anahtar eksikse **açık** dönüyordu — yeni sunucuda kontrol dosyası oluşmadan A1 Live gerçek para açabilirdi. CoptC'de küme boşaltıldı + `_load_control` varsayılanları `True` yapıldı; anahtarsız durum test edildi, üçü de `paused=True`.
- **`:05` / `:06` yarışı kilitle çözüldü:** açılış turu artık 4 trader koşuyor (A1 sanal + A1 Live + MUM + B1#05), 60 sn'yi aşarsa `:06`'daki aynalama yarım sanal state'i kopyalardı. `runner.py::_open_gate` (`fcntl.flock`) — açılış kilidi tutar, `live-open` en fazla **45 sn** bekler, dolarsa yine de devam eder (beklemek atlamaktan iyi).
- **Devredilmeyenler:** live state/history sıfır başlar (yeni cüzdan); sanal defterler geçmişi + bakiyeyi korur, açık pozisyonlar ana projede bırakıldı.
- `poly_trader_b1_01.py` kopyasında kalan 6 sabit `[15. ANALİZ …]` log etiketi `LABEL` değişkenine bağlandı (B1#05 kapanışta yanlış defter adı yazıyordu).
- **Panelden para çekme (2026-08-13):** CoptC dashboard'unun altındaki kart `relay_send_erc20` ile proxy cüzdandan gasless ERC-20 gönderir. Ana projede bu fonksiyon API'de var ama UI'da bilerek buton yoktu (CLI'a bırakılmıştı); CoptC'de butona bağlandı. Katmanlar: panel parolası **zorunlu** (parolasızsa uç `403`), `COPTC_WITHDRAW_CODE` her gönderimde istenir (5 hatada 15 dk kilit, `secrets.compare_digest`), adres biçimi + tutar ≤ bakiye + proxy/`POLY_FUNDER` eşleşme kontrolü, her deneme `poly/withdraw_log.jsonl`'a yazılır (**kod asla kaydedilmez**). `POLY_DRY_RUN` alım-satım bayrağı olduğu için yalnız gönderim çağrısı boyunca geçici olarak devre dışı bırakılır — global ayar değişmez.
- **`.env` boş değer tuzağı:** `os.getenv("COPTC_SECRET", <varsayılan>)` anahtar tanımlı ama boşken boş string döndürüyor, varsayılan devreye girmiyordu → Flask "no secret key" ile **girişi tamamen kırıyordu**. `getenv(...) or <varsayılan>` kalıbına geçildi (`COPTC_SECRET`, `COPTC_PORT`, `COPTC_PASSWORD`).
- **Telegram tamamen kapalı (2026-08-13):** `COPTC_TELEGRAM` ana şalteri, varsayılan **off**. 11 gönderim fonksiyonunun (7 dosya, `tg_send` · `tg_send_photo` · `tg_send_pm_live` · `_tg_send_raw`) hepsinde **ilk ifade** olarak kapı duruyor; şalter açılmadıkça token doldurulsa bile ağa çıkmaz, `.env` hiç yoksa da varsayılan kapalı (fail-closed). Açmak için `COPTC_TELEGRAM=on` + kanal/token değişkenleri. Dışa çıkan adres denetimi: Binance kline, PM gamma/clob/relayer/bridge, alternative.me — başka bildirim kanalı (discord/slack/twitter/mail) yok.
- **Telegram sırları temizlendi:** ana projede bot token'ları 8 kaynak dosyaya düz metin gömülü (`pm_trader_helpers.py`, `poly_a2_algo_trader_core.py`, `poly_trader_analiz6{,_v2}.py`, `poly_trader_b1_{01,mum}.py`, `backtest_analiz2.py`, `telegram_poly_channels.py` varsayılan chat id). CoptC kopyalarında hepsi boşaltıldı, gönderim fonksiyonlarına "token yoksa sessizce çık" kapısı eklendi. Yeni sunucuda TG istenirse `.env` üzerinden ve **ayrı kanalla** verilmeli. *Ana projedeki gömülü token'lar olduğu gibi duruyor — ayrıca ele alınmalı.*

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.

**Poly analiz TG kuralı:** Tüm analizlerde Telegram yalnızca gerçek açılış veya kapanışta gider; “pozisyon yok / sinyal yok / skip / önizleme” log’a yazılır.
