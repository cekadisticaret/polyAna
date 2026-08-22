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
| `temmuzPoly/chart_hourly_signals.py` | Grafik overlay — 1. Analiz (A1) saatlik UP/DOWN okları. |
| `temmuzPoly/a3a8_signal_mode.py` | A3/A8 sıkı (filtreli) vs gevşek mod (`a3a8_signal_strict`; sıkı=entry/kesişim veya momentum+RSI teyit) |
| `temmuzPoly/chart_algo_panel.py` | Grafik ALG1/ALG2 — 5m/15m konsensüs + slot WR takibi (`update_wr` cron */5). |
| `Sonnet/candle_pattern_engine1.py` | Mum pattern + S/D + confluence + `generate_report()` (grafik raporu) |
| `Sonnet/candle_pattern_engine.py` | v1 motor (yedek; grafik engine1 kullanır) |
| `web/dash_chrome.py` | Ortak üst bar POLY / FOREX / KRİPTO — dünya aksanı; login hariç HTML yaması; **mobilde (≤800px) gizli** |
| `web/poly_dashboard.py` | Poly dashboard **5050** — `/poly/grafik` mum analizi; `/algoritma-islemler` A1/A2/A6/V2/V3/A15/B1×3 + A2 Top-17 (7/24 sanal), **34 defterin tamamı listelenir** (X1#01 + COMBO dahil) (bakiye filtresi 2026-08-14'te kaldırıldı — sıfırlama sonrası hepsi $300'dan başladığı için zarardaki her defter gizleniyordu); `/poly/yapay-zeka-analiz` Poly Algo Analist bildirim akışı + Lider Analizi; `/kripto/yapay-zeka-analiz` Kripto Test AI Analist bildirim akışı; **`/kripto/lider-analiz`** Kripto Test 30 coin lider tablosu (genel + coin bazlı PnL/WR); **`/kripto/jarvis`** JARVIS denetim ekranı (cyan/magenta/gold HUD, iki sekme: Kripto Test Analizi + Kripto Sistem Denetimi; veri `/kripto/api/jarvis` → `jarvis_report.json` + `jarvis_audit.json`, gece 00:00 tazelenir, CSS sınıfları `j-` önekli); `/kripto` coin liderleri **SKILL + t** ile sıralanır (WR değil); **`/forex`** üçüncü sistem kabuğu — Grafik 1 Kalman + Algoritma 2 (13 katman, sanal) + **`/forex/algoritma-islemler`** (Poly listesinin XAUUSD $1000 kopyası) |
| `EylulForex/` | Forex sistemi — Poly/Kripto gibi ayrı klasör; `bursaapp.com/forex` |
| `EylulForex/forex_pages.py` | Forex overview + **GPSUSDT** (menü 2.) + **BIN_XAUUSDT** + **Algoritma işlemler** + **CEM01** + **CAPITAL** + **OPEN API** + `/forex/islemler` + **Yapay Zeka Analiz** · `/forex/b103` ve `/forex/gpsusdt2` menüde yok · `/xau` = CEM01; EXNESS ve Algoritma 2 menüde yok |
| `EylulForex/forex_analyst.py` | CEM01 grafik AI analist — 3 saatte bir Claude; `apply_signal` yok; feed `data/forex_analyst_feed.jsonl` |
| `EylulForex/fx_algo_catalog.py` | Forex Algoritma işlemler kataloğu — Poly `_ALGO_ISLEMLER_KEYS` + **D101–D106**; $1000 / $200×100x / kom $0.35 |
| `EylulForex/fx_algo_signals.py` | XAU mumunda aynı indikatör; Poly import (yazma yok); D101–D106 `fx_algo_d`; c101_v2 trader yok |
| `EylulForex/fx_algo_d.py` | D101 trend · D102 mean-rev · D103 vol kırılım · D104 akış vekili · D105 Kalman+Hurst · D106 confluence |
| `EylulForex/fx_algo_book.py` | XAUUSD sanal defter `data/fx_algo_*` — $1000 · max 1 · Test çıkış (24s · 3×ATR) |
| `EylulForex/fx_algo_runner.py` | Cron :02 close · :05 open · */2 trail · */10 scan; manuel open yok |
| `EylulForex/capital_api.py` | Capital.com Open API — oturum/hesap/GOLD fiyat/pozisyon; emir yok; `.env` `CAPITAL_*` |
| `EylulForex/cem02_book.py` | CEM02 sanal XAUUSD — CEM01 kopyası, bağımsız `data/cem02_*`; `forex_book` import yok |
| `EylulForex/cem02_data.py` | CEM02 kotasyon/mum — CEM01 kopyası; `forex_data` import yok |
| `EylulForex/cem02_signal.py` | CEM02 Kalman+VWAP — CEM01 kopyası; `forex_signal` import yok |
| `EylulForex/cem02_paper.py` | Cron `* * * * *`: Capital demo oturum ping; anahtar yoksa eski sanal defter |
| `EylulForex/ctrader_api.py` | cTrader Open API — OAuth + JSON WS; DEMO MARKET emir (`orders_allowed`); canlı hesaba emir yok; `.env` `CTRADER_SCOPE=trading` |
| `EylulForex/oapi_book.py` | OPEN API sanal XAUUSD — CAPITAL kopyası, bağımsız `data/oapi_*`; cem02/forex_book import yok |
| `EylulForex/oapi_data.py` | OPEN API kotasyon/mum — CAPITAL kopyası; cem02/forex_data import yok |
| `EylulForex/oapi_signal.py` | Eski kopya; sayfa/emir artık `forex_signal` (CEM01) |
| `EylulForex/oapi_trader.py` | CEM01 Grafik g1 aynası → cTrader DEMO 0.10 lot; canlı hesap yok |
| `EylulForex/oapi_paper.py` | Cron `* * * * *`: g1 aynası DEMO emir; token yoksa sanal |
| `EylulForex/gpsusdt_data.py` | GPSUSDT Binance **USDT-M** mum/kotasyon (fapi, spot yedek) — CEM01'e dokunmaz |
| `EylulForex/gpsusdt_binance.py` | GPSUSDT fapi + Isolated MARKET; kapanış `close_live` (borsa lotu, bitene kadar retry) |
| `EylulForex/gpsusdt_book.py` | GPSUSDT Isolated **$20×10x canlı** — aynı sinyal/plan; dolum gerçek MARKET; gece penceresi yok |
| `EylulForex/gpsusdt_signal.py` | GPSUSDT Kalman+VWAP + S/R — `forex_signal.py` kopyası değil, aynı motor ayrı veri |
| `EylulForex/gpsusdt_paper.py` | Cron `* * * * *` (+10s): GPSUSDT canlı open/trail; `forex_paper.py` değişmedi |
| `GET /forex/api/gpsusdt` | GPSUSDT işlemler salt okunur — token `GPSUSDT_API_TOKEN`; emir yok |
| `EylulForex/data/gpsusdt_live_control.json` | GPSUSDT canlı anahtar — `live_paused: false` = emir açık |
| `EylulForex/gps2_data.py` | GPSUSDT_2 mum/kotasyon — canlı `gpsusdt_data` kopyası, ayrı |
| `EylulForex/gps2_binance.py` | GPSUSDT_2 fapi kotasyon + VWAP `market_fill` — emir yok |
| `EylulForex/gps2_book.py` | GPSUSDT_2 sanal Isolated **$50×15x · kasa $160** — canlı GPS'e dokunmaz |
| `EylulForex/gps2_signal.py` | GPSUSDT_2 Kalman+VWAP — canlı `gpsusdt_signal` kopyası |
| `EylulForex/gps2_paper.py` | Cron `* * * * *` (+15s): GPSUSDT_2 sanal open/trail |
| `EylulForex/b103_data.py` | B1#03 grafik — CEM01 kotasyon, ayrı defter |
| `EylulForex/b103_book.py` | B1#03 sanal XAUUSD — CEM01 kopyası $300 · $100×500x; `forex_book` dokunulmaz |
| `EylulForex/b103_signal.py` | B1#03 sinyal — `b1_mum_signal` (1h mum confluence ±15); eski motor değişmez |
| `EylulForex/b103_paper.py` | Cron `* * * * *` (+25s): B1#03 sanal open/trail |
| `EylulForex/bin_b103_data.py` | BIN_B1#03 XAUUSDT mum/kotasyon — GPSUSDT ayrı |
| `EylulForex/bin_b103_binance.py` | BIN_B1#03 fapi Isolated MARKET XAUUSDT — GPSUSDT/CR6'ya yazmaz |
| `EylulForex/bin_b103_book.py` | BIN_XAUUSDT $20×10x D104 ayna; canlı üst sayı = Binance USDT-M; borsa boşsa kart yok; aynı D104 satırı tekrar açılmaz |
| `EylulForex/binance_um_wallet.py` | Tek USDT-M cüzdan (GPS+BIN aynı sayı); ban’de REST yok, son okuma |
| `EylulForex/bin_b103_signal.py` | BIN_XAUUSDT — Aktif et motorunun `fx_algo_*_state` açık satırını okur; kendi sinyalini koşturmaz |
| `EylulForex/bin_b103_paper.py` | Cron D104'dan sonra ayna (close :02+20s · open :05+25s · trail +35s · scan +20s); $20×10x |
| `GET /forex/api/bin-b103` | BIN_XAUUSDT işlemler salt okunur — token `BIN_B103_API_TOKEN` (yoksa `GPSUSDT_API_TOKEN`); emir yok |
| `EylulForex/night_window.py` | Gece penceresi **kapalı** — GPSUSDT ve BIN 22:00–08:00 da açık |
| `EylulForex/data/bin_b103_live_control.json` | BIN_XAUUSDT — CANLI/sanal + `engine_uid` (Aktif et) |
| `EylulForex/desk_meta.py` | Forex masa sağ alt — başlangıç bakiyesi + ilk çalışma anı (işlem mantığı yok) |
| `EylulForex/forex_book.py` | XAUUSD sanal — $300 · $100×500x · 1 AL + 1 SAT; `book=g1\|a2\|bybit`; EXNESS sayfası Exness Raw kom $0.35/taraf |
| `EylulForex/forex_paper.py` | Cron `* * * * *`: CEM01 + A2 + **EXNESS** sanal (canlı emir kapalı) |
| `EylulForex/algo2_engine.py` | **Algoritma 2** — 13 katman (sinyal/rejim/MTF/S-R/süpürme/filtre/risk/pozisyon/performans/simülasyon/paper/panel/karar); Grafik 1'e dokunmaz |
| `EylulForex/algo2_backtest.py` | A2 kapı simülasyonu (5m, emir yok) → `data/algo2_backtest.json` |
| `EylulForex/forex_data.py` | CEM01: Yahoo `GC=F` (+ bayatta PAXG); EXNESS sayfası: geçici Bybit altın ticker (Exness API bekleniyor); defter sinyali **1m**, S/R **5m** |
| `EylulForex/bybit_xau.py` | Geçici altın fiyat — `XAUUSDT` ticker/kline; EXNESS defteri bunu kullanır; CEM01'e dokunmaz |
| `EylulForex/bybit_trade.py` | Eski Bybit canlı yol — **devre dışı**; EXNESS canlı için Exness API anahtarı gerekir |
| `EylulForex/confluence_signal_engine.py` | Sinyal motoru: H1 trend + **Kalman+VWAP** (MACD yok) + pattern + opsiyonel PAXG tick |
| `EylulForex/forex_signal.py` | Overlay: tick + M5/M15 veto; ray kendi Kalman+VWAP'ı (tick yok) |
| `temmuzPoly/repair_a2_sanal_settlement.py` | A2 sanal geçmişi PM slot open/close ile yeniden hesaplar (Binance 1h). |
| `scripts/watch_critical_files.py` | Kritik kaynak inotify izleyici — silinmede `ops/incidents/` olay kaydı |
| `ops/CRITICAL_FILE_RESTORE.md` | 2026-08-02 kaynak silinme / geri yükleme zaman çizelgesi |
| `ops/incidents/` | Silinme/eksik olay JSON+txt (process, git D, audit) |
| `AgustosKripto/` | Kripto Future — CR6/A139/B1#03 Live + sanal Test (`bursaapp.com/kripto` · `/kripto/test`) |
| `AgustosKripto/virtual_book.py` | Sanal futures — net PnL + ATR kâr kilidi; `close`/`trail` `policy=` alır (None = eski); fapi ban'de mark spot public kline; cache + `/tmp/agustos_snap` |
| `AgustosKripto/exit_policy.py` | **Çıkış rejimi tek kaynağı** — zaman kapanışı yok · 24s tavan · **3×ATR** zarar stop. Kâr kilidi ARM **0.5×ATR** (`atr_profit_lock.py`). `exit_policy.json` ile kod değişmeden kapatılır |
| `AgustosKripto/orphan_scan.py` | Sahipsiz defter taraması — hiçbir runner'ın işlemediği `*_state.json` (açık pozisyon tutar, sessizce muhasebe dışı kalır); `--archive` |
| `AgustosKripto/Test/exit_lab.py` | Çıkış rejimi laboratuvarı — girişler sabit, gerçek 1m veriyle yeniden oynatma; `--validate` (kayıtlı sonucu üretiyor mu) · `--sweep` · `--deep` (gün-kümelenmiş t) · `--realistic` · `--walkforward` |
| `AgustosKripto/Test/exit_diag.py` | Kapanış-sebebi tablosunun seçilim yanlılığı teşhisi (MFE + silahlanma oranı kırılımı) |
| `AgustosKripto/atr_profit_lock.py` | ATR trailing kâr kilidi (**arm 1.0 / trail 0.5** — MFE'de işlemlerin %79'u 0.5 ATR'yi geçmiyordu) + zarar-stop; modül varsayılanı `2.0×ATR$` **değişmedi** (gerçek para yolu `crypto_futures_cr6` bunu doğrudan import ediyor), sanal defterler `exit_policy` ile pozisyon başına `6.0` kullanır |
| `AgustosKripto/Test/` | Tek kripto sanal ekran (`/kripto/test`, menü **Algoritma İşlemler**); `$100×6x` deposit $1000; 1h/4h TF seçimi; **73 defter** = 67 ayna + 4 PRO + JARVIS_V1 + CEBU; B1#03 **KAITO pasif**; çıkış: zaman kapanışı yok · 24s · 3×ATR · ATR kilit |
| `AgustosKripto/Test/leader_mapping.py` | Lider Analiz + JARVIS_V1 ortak sıralama (PnL→WR→işlem); tablo değişince JARVIS eşlemesi geçmiş mtime ile yenilenir |
| `AgustosKripto/Test/jarvis_v1.py` | JARVIS_V1 — `leader_mapping` üzerinden coin→motor; ARB→A1#33 · OP→B1#03 pin; kaynak TF kopyası; max 10 pozisyon |
| `AgustosKripto/Test/cebu.py` | CEBU — sabit coin→motor (BTC/ETH/KAITO/HYPE pasif); sinyal gelince açar, kota yok (max 18); `/kripto/cebu` |
| `AgustosKripto/Test/kripto_test_analyst.py` | Kripto Test AI Analist — 3 saatte bir Kripto Test defterleri arasında ayrışma bulur, Anthropic API ile doğal dilde yorum üretir, Telegram'a (LAB bot, ayrı kanal) gönderir, tam metni `kripto_analyst_feed.jsonl`'a kaydeder; `bursaapp.com/kripto/yapay-zeka-analiz` |
| `AgustosKripto/Test/jarvis_report.py` | **JARVIS motoru (1. sekme)** — 69 Test defterini tarar, drift-nötr SKILL + t, komisyon/brüt/net kırılımı, kapanış-sebebi ve coin dökümü üretir; bulgular veriden otomatik yazılır. Çıktı `jarvis_report.json` + `jarvis_history.jsonl` (gün gün). Gece **00:00** cron aynı turda `jarvis_audit.py`'yi de çalıştırır; `bursaapp.com/kripto/jarvis` |
| `AgustosKripto/Test/jarvis_audit.py` | **JARVIS sistem denetimi (2. sekme)** — yalnız Test defterleri `skill_audit.py` ile taranır; MFE, kapanış-sebebi, drift, konsensüs, CR6 hayaletleri. Çıktı `jarvis_audit.json` |
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
| `AgustosKripto/Algoritmalar/` | Sinyal kataloğu (CR6 + Test A1/A2). Sanal sayfa `/kripto/algoritmalar` kaldırıldı (2026-08-22); runner cron'u durdu |
| `AgustosKripto/Analizler/` | A10 Dual + Supertrend sinyal kaynağı. Sanal sayfa `/kripto/analizler` kaldırıldı; A10/ST Test'e taşındı |
| `AgustosKripto/binance_futures_client.py` | Binance USD-M REST — emir, bakiye, commissionRate, userTrades, `book_ticker`, `query_order`, `premium_index`, `funding_info` |
| `AgustosKripto/crypto_futures_trader.py` | Futures open/close + `dust` süpürme (|notional|≤$2); brüt/komisyon/net; `open_maker` (post-only GTX limit, tick yuvarlama, dolmazsa iptal) |
| `AgustosKripto/crypto_futures_cr6.py` | **Algoritmalar Live** (gerçek Binance) — Hurst+A1#11 MR+Z-Score MR+Mean Reversion çoğunluk oyu; top-N; $7×20x; **yeni open BTC/ETH/BNB yok**; ATR/hard SL; `fcntl` state kilidi + atomik yazım, `order_id` idempotency (hayalet pozisyon temizliği), `MAX_HOLD_HOURS` · **şu an paused** |
| `AgustosKripto/crypto_futures_a139.py` | **A1#39 Live** (gerçek Binance) — Test `a1_39` (H1 Kombinasyon) ile aynı sinyal/TF/çıkış; $20×7x; max 4; 30 coin; `/kripto` kartları yerel defterden (Binance 418/yasak ekranı boşaltmaz); USDT son okunan cache |
| `AgustosKripto/crypto_futures_b1_mum.py` | **B1#03 MUM Live** — Test `b1_mum` ayna; Isolated **$10×20x**; Binance boşsa hayalet kapanır (`bn_flat`); aynı slot tekrar açılmaz |
| `AgustosKripto/crypto_futures_live_control.json` | CR6 Binance Live — `live_paused` (yeni açılış) + `top_n`; **paused kalır**, A1#39 ayrı kontrol |
| `AgustosKripto/crypto_futures_a139_control.json` | A1#39 Live — `live_paused` + `top_n` (1–4); **19.08 durduruldu** · `/kripto` çubuğu artık B1#03 |
| `AgustosKripto/crypto_futures_b1_mum_control.json` | B1#03 MUM Live — `live_paused`; `/kripto` üst çubuğu |
| `temmuzPoly/pm_home_display.json` | Poly `/poly` overview'da gösterilecek tek sanal defter (`book_key`; varsayılan `a2_05`) — `/algoritma-islemler` kartından "Poly overview'da aktif et" |
| `AgustosKripto/kaito_paper.py` | **KAITO kağıt defteri** — cr6 kararları, gerçek emir yok; `/kripto` overview'dan kaldırıldı (cron hâlâ ölçer) |
| `AgustosKripto/cr6_tg_card.py` | Algoritmalar Live TG sarı kart (ALGO2 stili) — açılış/kapanış/ATR photo |
| `AgustosKripto/crypto_futures_config.json` | Sembol allowlist + default $6 / 10x; `CRYPTO_FUTURES_LIVE` + CR6 canlı; `entry_mode: maker` + `maker_wait_sec: 90` |
| `temmuzPoly/analiz5_settings.json` | A1/A2/A10/A6 Live WR giriş tutarları (düşük/orta/yüksek) |
| `temmuzPoly/pm_profit_baseline.json` | PM Kar başlangıç bakiyesi (varsayılan $314); Toplam Kar = nakit − baseline. |
| `temmuzPoly/` | Poly trader'lar, algo motorları, backtest; dashboard port **5050**. |
| `crypto-news-monitor/` | Kripto haber/tweet tarayıcı — RSS + opsiyonel Twitter, Claude skor, Telegram alarm (30 dk cron) |
| `twitter_bot/` | @tradecomio otomatik tweet — `tweet_trade_card.py` (saatlik kripto kart) + `tweet_forex_wins.py` (30 dk: CEM01 kazananları + WR, birden fazlaysa aynı görsel) |
| `5M110Analiz/` | FeatureEngine v2 indikatör kütüphanesi (110/111/210 adaptörleri) |
| `5M110Analiz/predictor.py` | composite_signal → UP/DOWN (gate ±15; algo kütüphanesine dokunmaz) |
| `temmuzPoly/poly_predictor_analysis.py` | A1/A2 ortak `predict`; Kill Zone (ET 9–11, gate 62/55) varsayılan açık |
| `temmuzPoly/btc_5m_105_algo.py` | 5M ortak sinyal motoru (15M adaptörleri; 4-algo + MR veto) |
| `temmuzPoly/poly_trader_5m_common.py` | 5M BTC ortak yardımcılar (Binance, 4-algo, PM emir) |
| `binance_fapi_guard.py` | fapi kesici; mum **spot/data-api** (fapi yalnız XAU/HYPE); WS `get_mark`/`get_last`/`get_book`/`position_state` |
| `binance_ws_marks.py` | `/market` mark+last · `/public` GPS/XAU book · `/private` pozisyon+cüzdan |
| `temmuzPoly/pm_trader_helpers.py` | PM emir + sanal kotasyon. Saatlik kapanış mumu `pm_sanal_slot_candle`: önce `fapi`, 418 olursa spot data API. **Sanal dolum canlı emirle birebir aynı formül** (`pm_sanal_fill`): `pm_order_book` (CLOB defteri, 20 sn önbellek, borsanın `min_order_size`/`tick_size`'ı) → `pm_book_vwap` (derinlik yürüyüşü) → 2 haneye yuvarla → min adet → `pm_fit_buy`. 63 senaryoda canlı `pm_place_order` ile sıfır sapma. **PM taker ücreti** `fee = C×0,07×p×(1−p)` (`pm_taker_fee`) tüm P&L'den düşülür; gerçek PM WR giriş (`load_pm_live_amounts` / `analiz5_settings.json`); slot tutarı: zayıf saat -%30, hot-hour büyütme **kapalı** (`HOT_HOUR_BOOST=1.0`) |
| `temmuzPoly/telegram_poly_channels.py` | Poly TG kanal yönlendirme — `TELEGRAM_ANALIZ1_CHAT_ID` yalnızca 1. ANALİZ; diğer trader'lar `TELEGRAM_POLY_TRADERS_CHAT_ID` / `TELEGRAM_PM_LIVE_CHAT_ID` vb. (analiz1 kanalına asla düşmez) |
| `temmuzPoly/pm_manual_sync.py` | Manuel PM — Polymarket activity → manual state senkron (5/15dk + saatlik) |
| `temmuzPoly/poly_trader_manual.py` | Manuel PM slot-sonu otomatik settle (`close`) — 5m/15m/1h |
| `temmuzPoly/pm_orphan_sync.py` | Ghost PM — zincirde açık ama state'te yok pozisyonları live trader'a yazar (trader sembol allowlist) |
| `temmuzPoly/pm_poly_history.py` | Polymarket data-api activity → slug bazlı gerçek PM geçmişi + açık (bekleyen) işlemler |
| `temmuzPoly/pm_balance_guard.py` | PM USDC bakiye + Live anahtarları; **`user_live_hold`** gerçek PM'i kullanıcı açana kadar kilitler (hafta sonu / dashboard Aç aşamaz) |
| `temmuzPoly/pm_weekend_sync.py` | Cum 22:00 / Pzt 11:00 İST — A1 Live + A2 dashboard anahtarlarını otomatik kapat/aç |
| `temmuzPoly/btc_analiz1_algo.py` | 1. Analiz tam algoritma (standalone kopya, poly_predictor ile aynı) |
| `temmuzPoly/poly_trader_analiz1.py` | 1. Analiz sanal (BTC+SOL); **$1000** · $24/36/48 WR; PM net kazanç ≥%50 yoksa giriş yok; top-3 saatte +%50; 12:00 yarı; **hafta sonu da açık** |
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
| `temmuzPoly/poly_trader_b1_04.py` | B1#04 sanal — 23 birincil motorun edge-ağırlıklı küme konsensüsü ($1000); :01 close / :02:30 open |
| `temmuzPoly/b1_04_signal.py` | B1#04 karar motoru — kopya defterleri tek oya indirir, oyları başabaşa göre ölçülmüş edge ile ağırlıklandırır; eşik `B1_04_MIN_EDGE` (varsayılan **0.0** = oylama yön gösterince gir) |
| `temmuzPoly/b1_04_backfill.py` | B1#04 geçmişini A2#05 slotlarında walk-forward simüle edip doldurur (`--write`); kayıtlar `backfill: true` |
| `temmuzPoly/poly_trader_b1_05.py` | **B1#05** sanal — coin başına en iyi motor ($1000); B1#01 iskeletini import edip globalleri yönlendirir (B1#01 dosyası dokunulmaz); :01 close / :02:30 open · URL `/algoritma-islemler/b1_05` |
| `temmuzPoly/b1_05_signal.py` | B1#05 eşleme motoru — B1#01 ile aynı fikir ama havuzda **b1_mum + melez** da var (dashboard "coin başına en iyi" kartıyla birebir); türev defterler (b1_01/02/04/05, analiz2) havuz dışı; eşleme her open turunda yeniden hesaplanır → `b1_05_mapping.json` |
| `temmuzPoly/b1_05_backfill.py` | B1#05 geçmişini A2#05 slotlarında walk-forward doldurur (`--write`); seçilen motorun o slottaki gerçek kaydından yön/fiyat/sonuç alır, motor o slotta işlem açmamışsa atlar; `algo_name` = `B1#05←<motor>` (motor bazlı isabet dökümü için) |
| `temmuzPoly/poly_trader_b1_05_live.py` | **B1#05 Live** — gerçek PM, kademe `/ayarlar` → İşlem Miktarları'ndan ayarlanır (varsayılan $4/5/6); sanal B1#05'i aynalar (bağımsız sinyal yok); tek otorite dashboard Ayarlar anahtarı, **varsayılan kapalı**; :02+:12 close / **:06:30** open (`sleep 30`; sanal :06 sonrası); `min_profit_ratio=None` → PM kâr kapısı yok, **sanal ne açarsa aynısı**. ⚠️ Backfill kenar bulamadı — kademe bilerek en düşük |
| `temmuzPoly/poly_trader_b1_mum_live.py` | **B1#03 MUM Live** — gerçek PM, kademe `/ayarlar` (varsayılan $6/8/10); sanal B1#03 MUM'u aynalar; dashboard anahtarı, **varsayılan kapalı**; :02+:12 close / :06 open (sanal :05 state sonrası) |
| `temmuzPoly/poly_trader_c101.py` | **C1#01 · OPUS-OHLCV** sanal (**$1000**) — yön tahmin etmez; 5 puan kenar; kademe **$24/36/48** WR; :01 close / :02 open / :25 backfill · URL `/algoritma-islemler/c101`. Gerçek para yolu yok |
| `temmuzPoly/poly_trader_c101_v2.py` | **C1#01 V2 · GERÇEK ASK** sanal (**$1000**) — C1#01 ile **tek farkı kotasyon kaynağı ve eşik**: iki tarafın CLOB `best_ask`'i + **3 puan** kenar (`C101_V2_EDGE_MIN`). Model/veri/Kelly/settle birebir aynı. `poly_trader_c101.py`'yi import edip globallerini yönlendirir (`analiz6_v4` kalıbı) — **C1#01 dosyası dokunulmaz**. Ayrı state/history/kalibrasyon dosyaları; :01 close / :02 open / :25 backfill · URL `/algoritma-islemler/c101_v2` |
| `temmuzPoly/c101_signal.py` | C1#01 **ve V2'nin ortak** modeli — `P(UP)=Φ(ln(S/PTB)/(σ·√T_kalan))`, sürüklenme sıfır; σ = Parkinson H/L (12s/72s harman) × emir defteri derinlik çarpanı × saat içi aralık çarpanı; funding/OI/taker akışından ±0,05 sınırlı yön eğimi; binary Kelly `(P−p)/(1−p)`. `evaluate(..., edge_min=)` ile defter başına eşik |
| `temmuzPoly/c101_data.py` | C1#01 **OHLCV dışı** veri toplayıcı (Binance Futures public, urllib, /tmp TTL cache): `/fapi/v1/depth` ±%0,1 derinlik+dengesizlik · kline `takerBuyBase` (CVD vekili) · `premiumIndex` funding+z · `openInterestHist` |
| `temmuzPoly/c101_calibration.jsonl` | C1#01 kalibrasyon günlüğü — açılan **ve açılmayan** her değerlendirme (saatte 3 satır); `calib` modu model vs piyasa **Brier skoru** verir. Defterin asıl ölçüm çıktısı. **14.08.2026 15:10–21:20 arası satırlar CLOB ask'e karşı ölçüldü**, öncesi ve sonrası Gamma mid — piyasa Brier'ini karşılaştırırken bu pencereyi ayır |
| `temmuzPoly/c101_v2_calibration.jsonl` | C1#01 V2 kalibrasyon günlüğü — aynı biçim, kotasyon hep ask. `pm_up`/`pm_down` ask, `up_mid`/`down_mid` Gamma mid; iki defterin aynı slotta neye baktığı buradan karşılaştırılır |
| `temmuzPoly/c101_depth_baseline.json` | Sembol başına likidite oranı EWMA referansı; ilk 20 tur derinlik çarpanı 1,0 (etkisiz) |
| `temmuzPoly/algo_islemler_fresh_start.py` | Algoritma-islemler close + **34 defterin** bakiyesini $1000'e sıfırla (cron open bekler, manuel open yok). Liste dashboard `_ALGO_ISLEMLER_KEYS` ile birebir; `melez` dosya adı farklı olduğu için `_STATE_FILE_KEY` ile eşlenir. Bayraklar: `--check` (yazmadan eksik dosya raporu) · `--reset-only` · `--wipe-history` (geçmişi `_archive_<tarih>/` klasörüne taşır, silmez) |
| `temmuzPoly/poly_trader_x101.py` | **X1#01 - 13Analiz** — sanal $1000 · BTC/ETH/SOL saatlik; 13 katman + ask kenarı; **`:01` close / `:02` open**; gerçek PM yok |
| `temmuzPoly/x101_signal.py` | X1#01 kontrol listesi (skor ≥64 · MTF 2/3 · ask kenarı ≥3p) |
| `temmuzPoly/poly_trader_e01.py` | **COMBO** — sanal $1000 · A1 + C1#01 + A2#05 V2 oy; çatışmada açmaz; 1/2/3 oy = **$24 / $36 / $48**; **`:01` close / `:02:25` open**; gerçek PM yok · URL `/algoritma-islemler/combo` |
| `temmuzPoly/e01_signal.py` | COMBO oy okuyucu — üç kaynağın o saat açık pozisyonuna bakar, sinyal üretmez |
| `temmuzPoly/pm_fee_backfill.py` | (ops, tek sefer koştu) Geçmiş defterlere PM taker ücretini işler — `pm_fee` yazar, `pnl`'i düşürür, bakiyeyi ücret kadar azaltır. Varsayılan kuru çalışma, `--apply` ile yazar; yedek `_fee_backfill_backup/`. İdempotent (`pm_fee` dolu kaydı atlar) |
| `temmuzPoly/algo_islemler_defer_to_next_hour.py` | (ops) open erteleme — normalde kullanma |
| `temmuzPoly/b1_02_signal.py` | B1#02 sabit sembol→motor eşlemesi |
| `temmuzPoly/analiz6_v3_signal.py` | A6V3 sinyal — BTC/ETH A6, SOL A2 (algo→predict kline dönüşümü) |
| `temmuzPoly/analiz6_v4_signal.py` | MELEZ sinyal — her sembolde uzun dönem isabeti en yüksek motor: BTC→`macd_histogram_div` (%55,0), ETH/SOL→`mean_reversion` (%54,2 / %53,2) |
| `temmuzPoly/analiz6_v4_backfill.py` | MELEZ geçmişini A6V3 (BTC) + A2#05 (ETH/SOL) defterlerinin gerçek kararlarından walk-forward kurar (`--write`); kayıtlar `backfilled: true` |
| `temmuzPoly/backtest_a2_a6_melez_1y.py` | A2#05 · A6V3 · MELEZ — 1Y walk-forward backtest (BTC/ETH/SOL); ay ay Telegram (`--telegram`) |
| `temmuzPoly/backtest_selected_algos_1y.py` | Seçili 8 defter — 1Y walk-forward; $1000 · $24/36/48; model ask + PM ücreti; aylık P&L Telegram |
| `temmuzPoly/backtest_e01_family_1y.py` | A1 · C101 · A2#05 · COMBO — 1Y walk-forward, $1000 · $24/36/48, aylık P&L |
| `temmuzPoly/poly_trader_analiz6_v2_live.py` | A6V2 Live gerçek PM (BTC+ETH); dashboard toggle |
| `temmuzPoly/poly_trader_analiz6_v3_live.py` | A6V3 Live gerçek PM (BTC+ETH+SOL); dashboard toggle |
| `temmuzPoly/poly_trader_analiz6_live.py` | A6 Live gerçek PM; slot gate zayıf saat -%30; sanal A6 adayları |
| `temmuzPoly/poly_live_hourly_common.py` | Saatlik gerçek PM ortak açılış yardımcıları |
| `temmuzPoly/poly_trader_manual_state.json` | Manuel PM işlemleri state (dashboard açık pozisyon) |
| `temmuzPoly/analiz32_5m_adapter.py` | 5M110Analiz → 5m sinyal adaptörü (algo bozulmaz) |
| `temmuzPoly/analiz32_15m_adapter.py` | 5M110Analiz → 15m sinyal adaptörü (110 SOL) |
| `temmuzPoly/pm_balance_hourly.py` | PM portföy saatlik kayıt + 00:00 Telegram özeti + 3 saat peş peşe düşüş ALERT |
| `temmuzPoly/poly_algo_analyst.py` | Poly Algo Analist — 3 saatte bir A1/A6 ailesi/A2#01-17/A10/A15/B1#01-02 arasında ayrışma bulur, Anthropic API ile doğal dilde yorum üretir, Telegram'a gönderir, özeti `analyst_journal.jsonl`'a kaydeder |
| `temmuzPoly/algo_pattern_stats.py` | Defterler arası kalıp istatistikleri — Wilson güven aralığıyla "ikisi aynı yönde açtığında kazanma oranı" ve "indikatör oybirliği" hesaplar (N>=8 izlemede, N>=20 güvenilir); `pattern_stats.json` |
| `temmuzPoly/analyst_common.py` | Analist scriptleri ortak yardımcıları (.env, dashboard API, Telegram, Claude çağrısı) |
| `temmuzPoly/poly_algo_daily_report.py` | Poly Algo Analist Günlük Rapor — 00:00 İST; günlük defter özeti + o gün eşik atlayan yeni kalıplar; `analyst_daily_reports.jsonl` |
| `temmuzPoly/algo_signals.py` | 36 saatlik algo sinyali (BTC/ETH/SOL); `/tmp/algo_signals.json` |
| `temmuzPoly/algo_signals_v2.py` | 17 kârlı algo (Analiz 2 sekmesi); `/tmp/algo_signals_v2.json` + `algo_accuracy_v2.json` |
| `temmuzPoly/poly_trader_a2.py` | A2 Top 17 sanal trader ($1000, $24/$36/$48 WR); `poly_trader_a2_XX_{state,history}.json` |
| `temmuzPoly/poly_a2_algo_live_core.py` | A2 Live ortak çekirdek — gerçek PM open/close |
| `temmuzPoly/poly_trader_a2_02_live.py` | A2#02 RSI Div Live — $4/5/6; sanal #02 ayrı; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_08_live.py` | A2#08 Williams Live — $4/5/6; sanal #08 ayrı; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_03_live.py` | A2#03 Stoch RSI Live — $4/5/6; sanal #03 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_trader_a2_04_live.py` | A2#04 Schaff Live — $4/5/6; sanal #04 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_a2_algo_live_core.py` | A2 Live çekirdeği — sanal defter mirror/sync (309 gibi); open :07; `A2LiveSpec.min_profit_ratio` ile PM kâr kapısı defter bazlı (`None` = tam ayna) |
| `temmuzPoly/poly_trader_a2_05_live.py` | A2#05 Mean Rev Live — sanal #05 ile birebir sync; $4/5/6; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_06_live.py` | A2#06 Z-Score MR Live — $4/5/6; sanal #06 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_trader_a2_07_live.py` | A2#07 Hurst Live — $4/5/6; sanal #07 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_a2_algo_trader_core.py` | A2 sanal Top17 ($300); Cum 22:00–Pzt 11:00 open kapalı; #09/#16/#17 → eski ALFA kanalı. `A2Config`'te türev defterler için iki opsiyonel alan: `min_entry_price` (None = taban yok) · `live_mirror` (False = gerçek para aynası hiç çağrılmaz) — **varsayılanlar mevcut 17 defterin davranışı** |
| `temmuzPoly/poly_trader_a2_05_v2.py` | **A2#05 V2 · Z KAPISI** sanal ($1000 · $24/36/48) — A2#05 ile aynı sinyal, **1,0 ≤ \|z\| < 1,5** + **bilet tabanı 0,40**. `live_mirror=False`; **:01 close / :02 open** · URL `/algoritma-islemler/a2_05_v2` |
| `temmuzPoly/a2_05_v2_zlog.py` | A2#05 V2 gölge günlüğü — açılan **ve** z kapısına takılan slotların sonucunu Binance 1h mumundan doldurur (`zbackfill`) ve \|z\| kovası bazında kenar tablosu basar (`zstats`). Komşu bantların cevabı işlem açmadan gelir; günlük `a2_05_v2_zlog.jsonl` |
**Test:** `python3 BistAnaliz/BistHourSinyal/bist_visual_v2.py --test` — örnek BIST Analiz metni.  
`python3 BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py --test` — örnek GÜÇLÜ AL metni (tarama/seans yok).

## Cron
- `BistAnaliz/BistHourSinyal/bist_visual_v2.py 1h` — `1 7-15` + `31 14` iş günü → `/tmp/bist_visual.log`
- `BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py` — `*/5` iş günü → `/tmp/bist_signal_hunter.log`
- `BistAnaliz/backup.py` — `59 23 * * *` → `/tmp/backup.log`
- `/algoritma-islemler` sanal: `close` **:01** / `open` **:02** (B1#04/#05 `:02:30`, COMBO `:02:25`). A5/A10 + Live PM: `close` **:02** / `open` **:05**
- `temmuzPoly/poly_trader_analiz1.py close/open` — 1. Analiz BTC+SOL **sanal** ($1000 · $24/36/48); hafta sonu da çalışır
- `temmuzPoly/poly_trader_analiz1.py weekly` — Cumartesi 21:00 haftalık 1 ısı haritası
- `temmuzPoly/poly_trader_analiz1.py daily` — her gün 00:00 İST günlük işlem geçmişi (TG)
- `temmuzPoly/poly_trader_analiz2.py close/open` — 2. Analiz **SOL only** sanal ($300, $12-16-20 WR); open Cum 22:00–Paz 18:00 İST kapalı
- `temmuzPoly/poly_trader_analiz2_live.py close/open` — 2. Analiz **canlı PM** SOL $6-7-8 WR (`PM_ANALIZ2_REAL_ENABLED`; :02/:05; hafta sonu dashboard anahtarı)
- `temmuzPoly/poly_trader_analiz2.py weekly` — Cumartesi 21:00 haftalık 2 ısı haritası
- `temmuzPoly/poly_trader_analiz6.py close/open` — 6. Analiz sanal; **open** aynı adayda A6 Live gerçek PM dener (`PM_ANALIZ6_LIVE_ENABLED` + dashboard)
- `temmuzPoly/poly_trader_analiz6_v2.py close/open` — 6. Analiz V2 sanal (BTC+ETH); A6 ile aynı indikatör; SOL yok; Live yok
- `temmuzPoly/poly_trader_analiz6_live.py close` — A6 Live kapanış :02; open sanal A6 open ile tetiklenir
- `AgustosKripto/crypto_futures_cr6.py close/open/trail` — **Algoritmalar Live** (gerçek Binance); Hurst+A1#11 MR+Z-Score MR+MR çoğunluk oyu; top-4 majors önce; $7×20x; **şu an paused**
- `AgustosKripto/crypto_futures_a139.py close/open/trail/scan` — **A1#39 Live** (gerçek Binance); Test `/kripto/test/a1_39` motoru; $20×7x; **paused**
- `AgustosKripto/crypto_futures_b1_mum.py close/open/trail/scan` — **B1#03 MUM Live**; Test `/kripto/test/b1_mum` state aynası; Isolated **$10×20x**; cron sanal turundan sonra (`:02+20s` close · `:05+25s` open · trail +15s · scan +20s); manuel open yok
- `AgustosKripto/kaito_paper.py close/open/trail` — **KAITO kağıt defteri**; cr6 ile aynı 4 algo oyu + `conviction_filter` vetosu + $7×20x + ATR kilidi/`exit_policy`, ama **gerçek emir yok** (dosyada emir fonksiyonu geçmez; KAITO zaten `FG_SYMBOLS`'te değil). Amaç: "canlıda sadece KAITO açalım" fikrini kasa riske girmeden ölçmek — Kripto Test'teki +$1.272 rakamı **başka bir stratejiye** ait ($100×6x, 69 defter) ve kenar değil düşen coine short kalmak (t_gün +0,76 · kârın %63'ü 5 işlemde · KAITO 11 günde −%61,3). `stats` ile oku
- `AgustosKripto/skill_audit.py` — elle; **20.826 işlem / 5,2 gün** denetimi: brüt PnL −$694 (t=−0,91 ≈ sıfır), komisyon $9.334 → net **−$10.027**. Eşiği geçen defter **2/103** (şans beklentisi ~26 → gerçek kenar yok). Konsensüs ters çalışıyor: **tam uzlaşı ≥%95 SKILL −%0,066 t=−2,15**, bölünmüş <%65 pozitif. MFE: işlemlerin **%79'u 0,5 ATR'yi geçmiyor** ve tüm zararı bu bant yapıyor (−$19.984)
- **Ölü bant filtresi kurulamaz:** MFE ancak kapanışta bilinir, giriş anında vekil değişken aranmalı. Denenen tüm giriş özellikleri (ATR%, saat, interval, tutma süresi) ileri testte çöktü — eğitimin seçtiği "en iyi 6 saat" testte t=−1,85'e döndü (aşırı uydurma kanıtı). LONG/SHORT asimetrisi drift, yetenek değil
- **Yerine kurulan — güven vetosu:** algo içi skor yüzdeliğinin **üst %20'si** SKILL −%0,065 · t=−3,89 · **5/5 zaman diliminde negatif** · DRIFT yalnız +%0,014 (yani piyasa yönü değil). 52 defterin 37'sinde (%71) mevcut. Konsensüs kesitiyle bağımsız olarak aynı sayı (−0,065 / −0,066). Üst kova atılınca kalanın SKILL'i **−0,000%** — zarar durur, kâr başlamaz. Ters açmanın maker sonrası beklentisi +%0,025 ama **%95 aralık [−0,007%, +0,057%] sıfırı kesiyor** → gerçek parayla ters işlem yok, gölge defter toplanıyor
- `AgustosKripto/funding_harvest.py` — elle / `--tg`; funding oranı taraması, yön riski yok; sembol başına gerçek `fundingIntervalHours` (4h/8h) ile yıllıklandırma
- `AgustosKripto/Algoritmalar/runner.py` · `Analizler/runner.py` — **sayfa yok, cron yok** (2026-08-22). Sinyal modülleri duruyor; sanal defterler `/kripto/test`
- `AgustosKripto/Test/runner.py close/open/trail/scan` — tek kripto sanal runner; `$100×6x`; zaman kapanışı yok · 24s · 3×ATR · ATR kilit; `scan` */10. PRO: `edge_gate` + süre tavanı, saatlik settle yok
- `EylulForex/fx_algo_runner.py close/open/trail/scan` — Forex Algoritma işlemler; Poly listesinin **XAUUSD** sanal kopyası ($1000 · $200×100x · kom $0.35); cron :02 close · :05 open · **dakikalık trail** · */10 scan; anlık PnL bid/ask (CEM01 gibi); CEM01/Poly dosyalarına dokunmaz; manuel open yok
- `EylulForex/forex_analyst.py` — 3 saatte bir CEM01 grafik yorumu (`/forex/yapay-zeka-analiz`); `forex_spot`/`apply_signal` çağırmaz; `/tmp/forex_analyst.log`
- `EylulForex/oapi_paper.py` — dakikalık OPEN API (`/forex/openapi`); cTrader DEMO emir (`oapi_trader`); `cem02_*`/`forex_*` import yok; `/tmp/oapi_paper.log`
- `EylulForex/gpsusdt_paper.py` — dakikalık GPSUSDT; Kalman+VWAP aynı; Binance Isolated **CANLI $20×10x**; gece penceresi yok; `data/gpsusdt_live_control.json`; `/tmp/gpsusdt_paper.log`
- `EylulForex/gps2_paper.py` — dakikalık GPSUSDT_2; aynı Kalman+VWAP; **sanal $160 · Isolated $50×15x**; emir yok; `/tmp/gps2_paper.log`
- `EylulForex/b103_paper.py` — dakikalık B1#03; CEM01 masa kopyası; sinyal `b1_mum_signal` 1h; sanal $300 · $100×500x; `/tmp/b103_paper.log`
- `EylulForex/bin_b103_paper.py` — **BIN_XAUUSDT** `/forex/bin-b103`; **D104 sanal defterin birebir aynası** (Aktif et motorunun açık satırı); Isolated **$20×10x**; gece penceresi yok; cron D104'dan sonra; `/tmp/bin_b103_paper.log`
- **Poly→Kripto uyumsuzluğu (ölçüldü, 2026-08-12):** Aynı sinyal Poly'de kâr, kriptoda zarar. Sebep komisyon oranı değil **başabaş eşiği**: Poly'de başabaş = piyasa fiyatı ≈ %49,8 (binary 1:1 ödeme), kriptoda = komisyon + ödeme şekli ⇒ A2#05 %61,7 · A6V3 %70,4 · B1#03 %44,6. Yani kriptoda kâr için ~12 puan daha isabet gerekiyor. 1Y ölçüm (181 bin sinyal, 7 ufuk, drift-nötr SKILL) 4 defterin hiçbirinde komisyonu aşan kenar bulamadı — tek yakın aday A6V3 majör 48s (+%0,109 · t=+2,65) ve o da 840 testlik çoklu-test düzeltmesini geçmiyor. Çözüm bu yüzden "daha iyi ayar" değil **kanıt şartı** (`edge_gate`): kenar yoksa pozisyon açılmaz
- **Çıkış rejimi ölçümü (1Y, `backtest_pro4.py`):** saatlik zorunlu kapanış A2#05'e 34.692 işlem yükledi (−$26.552); aynı sinyal sinyal-dönene-kadar tutulunca 5.841 işlem (−$11.811) → komisyonun **%83'ü** kalkıyor. Kayıp küçülüyor ama kenar olmadığı için kâra dönmüyor; bu yüzden PRO rejimi kapı ile birlikte çalışır
- **Çıkış rejimi TÜM sanal defterlerde değişti (2026-08-15):** … yeni rejim **zaman kapanışı yok · 24s tavan · 3×ATR stop** (canlı ince ayar: önce 6×→4×→3×). **ATR kâr kilidi ARM 0.5** (önce 1.0→0.7→0.5).
 - **Kapanış-sebebi tablosu yanıltıcıydı.** "1h_close −$17.756" satırı sebebi değil sonucu gösteriyordu: ATR kâr kilidi kazananları erken alıp götürünce saatlik kapanışa artık kaybedenler kalıyordu. Ölçüldü (`exit_diag.py`): `atr_stop` işlemlerinin MFE ortalaması 2,26 ATR ve %100'ü silahlanmış; `1h_close` işlemlerinin %83,5'i 0,5 ATR'yi bile görmemiş.
 - **Kanıt yöntemi:** `exit_lab.py` her gerçek işlemi girişi sabit tutup 1m fiyat verisiyle yeniden oynatıyor. Simülatör kayıtlı sonucu **işlem başına medyan $0,000 · p90 $0,030** sapmayla üretiyor (47.371 işlem, sebep örtüşmesi %92,4) — alternatif rejimler bu yüzden güvenilir.
 - **Gerçekçi replay** ((defter, coin) başına tek pozisyon): eski **46.305 işlem · net −$20.255 · komisyon $19.052**; yeni **9.542 işlem · net −$1.916 · komisyon $4.378**. Zararın **%90'ı** siliniyor, komisyonun %77'si.
 - **Ama kâr etmiyor:** en iyi rejimin brüt kenarı %0,059, taker gidiş-dönüş maliyeti %0,100. Gün bazlı kümelenmiş t = **+0,85** (sıfırdan ayırt edilemez). İşlem düzeyi t=+10,5 sahte hassasiyet — 118 defter aynı 30 coinde aynı saatte işlem açıyor, bağımsız birim gün.
 - **Eski rejimin zararı ise istatistiksel olarak gerçekti:** SKILL −0,0126 · t_gün **−3,42**. Yani değişiklik "belki daha iyi" değil, ölçülen bir kanamayı durduruyor.
 - **Elenen alternatifler (aynı veri):** zorunlu kapanışı 2/4/8/12 saate uzatmak (hepsi negatif) · zarar stopunu sıkmak 1×ATR (daha kötü) · ATR kilit parametreleri (fark gürültü) · **geçmiş başarıya göre defter seçmek** — walk-forward'da TERS çalıştı (eğitimde SKILL>0,10 seçilenler testte %0,062 kenar, filtresiz %0,084).
 - **Geri alma:** `exit_policy.json` → `{"enabled": false}`. Kod değişmeden bir sonraki cron turunda eski davranışa döner. `virtual_book.close_all_positions/trail_positions` `policy=None` ile çağrıldığında **eski davranışı korur** (geriye uyumluluk test edildi).
 - `atr_profit_lock.py` modül varsayılanları **değiştirilmedi** — gerçek para yolu (`crypto_futures_cr6`) onu doğrudan import ediyor; yeni eşik pozisyon başına `loss_stop_atr` alanıyla veriliyor.
- **Sahipsiz defter temizlendi (2026-08-15):** `Analizler/data/a4` kataloğdan (`ANALIZ_META`) kaldırılmış ama dosyası kalmıştı; hiçbir `close`/`trail` turu görmediği için **6 pozisyon 55 saattir açıktı** ve ne kapanıyor ne de zarar olarak sayılıyordu. `orphan_scan.py --archive` ile `_archive_orphan_20260815/`'e taşındı (353 kapanmış işlem, bakiye $106,06 / $300). Tarama tüm sistemde başka sahipsiz defter bulmadı.
- **`LEADER_MIN_SKILL` düzeltildi (2026-08-15):** %0,04 → **%0,10**. Eski değerin yorumu "maker gidiş-dönüş" diyordu ama defterler taker ödüyor; 50.554 gerçek işlemden ölçülen fiili maliyet %0,10. Kapı gerçeğin 2,5 katı altında olduğu için masrafını çıkaramayan (defter, coin) çiftlerini "nitelikli" gösteriyordu
- `AgustosKripto/Test/jarvis_report.py` — `0 21 * * *` (00:00 İST); `/kripto/jarvis` sayfasını besler (1. sekme Test + 2. sekme sistem denetimi), veri `/kripto/api/jarvis`. **İlk ölçüm (7 gün · 22.092 işlem):** brüt −$166 · komisyon $13.046 · net −$13.211 — kayıp tamamen komisyon; ortalama SKILL %−0,0044, 24/54 defter pozitif (yazı-tura), Bonferroni |t|≈3,8'i geçen yok. İşlemlerin %79'u süre dolduğu için kapanıyor ve zarar orada; ATR katmanı tek pozitif bileşen (+$1.392). **Sistem denetimi (118 defter · 50.801 işlem):** net −$21.709. 2. sekmede ayrıca **çıkış rejimi paneli** var: eski/yeni rejim karşılaştırması + geçiş sonrası biriken canlı veri (`jarvis_audit._rejim`). **Bulgu kapandı:** `LEADER_MIN_SKILL` %0,04 → %0,10 düzeltildi
- `AgustosKripto/Test/analog.py build/query/eval` — cron yok, elle çalışır; indeks `data/analog_index.npz` (52 MB, 270k pencere). **180g eval** (k=5000, step=4): isabet %49, ort. imzalı getiri **−%0,0023**; üst güven kovasında en fazla +%0,03 — komisyon sonrası işe yaramaz
- `AgustosKripto/Test/backtest_fast.py` — elle; profil sürenin %92'sinin format dönüşümünde geçtiğini gösterdi (`_resample_4h` %59, `_bars_ohlc` %33) → coin başına bir kez ön hesap. A2 Top-17 1Y: 6541s → dakikalar. Sonuçlar `backtest_1y` ile birebir (`--verify`)
- `AgustosKripto/Test/horizon_sweep.py` — elle; A1/A6/A6V2/A6V3 1Y taraması: **hiçbir ufuk %0,10 komisyonu aşmıyor**; edge süreyle büyümüyor, azalıyor (A1 4s'te −%0,056 t=−2,33; A6V3 8s'te −%0,048 t=−2,64). En iyi brüt A6 2s +%0,008 — komisyonun 12'de biri. **A6 = A6V2 birebir aynı** (30 coinlik evrende 27 coin aynı varsayılana düşüyor)
- `AgustosKripto/Test/minute_data.py fetch` — elle; 30 coin × 90g 1m OHLC (`data/minute_cache/`, ~28 MB)
- `AgustosKripto/Test/maker_sim.py` — elle; 88g üst %10 (3180 sinyal): taker net/sinyal **−%0,095**; maker fill **ters seçilim** (dolanlar kötü, kaçanlar brüt +%0,13…+%0,76); limit emir kurtarmıyor
- `twitter_bot/tweet_trade_card.py` — `20 * * * *` saatlik: son 3 saatteki en yüksek %kârlı Test işlemi → giriş/kapanış/kâr görsel kart → @tradecomio tweet; yeni kazanan yoksa atlar (`/tmp/twitter_trade_card.log`)
- `twitter_bot/tweet_forex_wins.py` — `*/30 * * * *`: CEM01 (`/forex/grafik`) son 30 dk kazananları + defter WR, birden fazlaysa aynı görsel (`/tmp/twitter_forex_wins.log`)
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
- `temmuzPoly/algo_signals.py` — `:05` her saat: 36 algo sinyali → `/tmp/algo_signals.json`
- `temmuzPoly/algo_signals_v2.py` — `:01` + `:04:40` her saat: 17 kârlı algo (Analiz 2) → `/tmp/algo_signals_v2.json` (`:01` A2#05/:02 open için)
- `temmuzPoly/poly_trader_a2.py` — A2 Top-17 **`:01 close` / `:02 open`** (ayna penceresi ile aynı); A2#05 **bilet tabanı 0,40**; Cmt 21:00 weekly
- `temmuzPoly/poly_trader_a2_{02,03,04,06,07,08,16}_live.py` — `:02 close` / `:05:10 open`: sanal :05:00 sonrası mirror
- `temmuzPoly/poly_trader_a2_05_live.py` — **`:01 close` / `:02:10 open`** (sanal A2#05 :02 sonrası)
# PASIF: `BistAnaliz/yuzdeBist.py` — crontab yorum satırı
# PASIF: `BistAnaliz/bist_scanner.py` — BIST Sinyal bildirim kapalı
# KALDIRILDI: `run_alfa.sh`, `poly_trader_alfa.py`, `alfa_signal.py`, `poly_trader_5m_sol_109.py`, `poly_trader_5m_sol_210.py`, …
# KALDIRILDI (2026-08-14, dosyalar da silindi): `poly_trader_5m_sol_110.py`, `poly_trader_15m_a2.py`, `poly_15m_a2_algo_trader_core.py`, `poly_trader_15m_309_live.py`, `poly_trader_5m_real_stats.py`, `analiz32_15m_signal_snapshot.py` — 15M/5M defterleri (110 · 309 · 316 · 317 + 309 Live) tamamen kaldırıldı
# YOK (disk/crontab): `polyManuel/sol_bot.py`, `temmuzPoly/poly_trader.py`

## Sürekli Çalışan Servisler
- `web/poly_dashboard.py` — port **5050**, **yalnız `127.0.0.1`** (2026-08-14; eskiden `0.0.0.0` idi ve panel `http://IP:5050` ile TLS'siz açılıyordu). Dışarıya nginx `443` üzerinden `bursaapp.com/poly` olarak çıkar; farklı bir arayüze bağlamak gerekirse `POLY_DASHBOARD_HOST`. `systemctl restart poly-dashboard.service` (PID izlemek için: `pgrep -af poly_dashboard.py`)
- `binance_ws_marks.py` — `binance-ws-marks.service`; tüm perp mark + last, 3 sn. Dashboard yedek thread (flock). Kart / canlı `mark_price` REST'e gitmez.
- Sunucuda `ufw` **aktif**: yalnız **22/80/443** girişe açık, gerisi `deny`. Yeni bir servisi dışarı açacaksanız kural eklemeniz gerekir (`ufw allow …`).

### Ayarlar Live anahtarları (`/ayarlar`)
- 15 satır, `pm_balance_guard._VALID_GROUPS` ile birebir: A1 · A2 · A10 · A6 · A6V2 · A6V3 · A2#16 · A2#02 · A2#03 · A2#04 · A2#05 · A2#06 · A2#07 · A2#08 · A15
- `POST /poly/api/pm-system` **grup adı geldiyse asla ana şaltere düşmez**; bilinmeyen ad `400` döner. Grup adı hiç yoksa (eski çağrı) ana şalter çalışır — hepsini birlikte çevirir
- **2026-08-12 hatası:** POST'ta ayrı bir sabit grup listesi vardı ve `analiz6_v2_live` / `analiz6_v3_live` bu listede yoktu. A6V3'e basınca istek `else` dalına düşüp `toggle_pm_open_paused()` çağırıyor, yani **15 Live defterin hepsini birlikte** açıp kapatıyordu. Liste kaldırıldı; doğrulama tek kaynağa (`_VALID_GROUPS`) bağlandı. A2#16 ve A2#02'nin ayar satırı da yoktu (kaza ile kapanıp geri açılamıyorlardı) — eklendi

## Ayna API — dış sunucu (2026-08-13)
Başka bir sunucunun ":06'da A6V3 ne açtı?" diye sorup aynı işlemi kendi tarafında açması için **salt okunur** uç. Emir tetiklemez, hiçbir state dosyasına yazmaz.

| Uç | Ne döner |
|---|---|
| `GET /poly/api/mirror` | 29 defter — bakiye → net PnL → WR sırası; `open` = **aktif slot** pozisyon sayısı; `active_slot.slot_tr` (ör. `13:02-14:01` İST) · tüm defterler aynı pencere |
| `GET /poly/api/mirror/<defter>` | Aktif slot pozisyonları + defter özeti; pozisyonda `slot_tr` · `entry_hour_tr` · `prediction_tr` |

- **Kimlik:** `X-Mirror-Token` başlığı (ya da `?token=`), `.env` → `MIRROR_API_TOKEN`, `secrets.compare_digest`. **Token tanımlı değilse uç tamamen kapalı** (`401`) — yanlışlıkla açık kalmaz.
- **Defter adı esnek:** `a6v3` · `A6V3` · `analiz6_v3` · `b1#05` · `a2#05` · `5` hepsi çözülür. Takma adlar `_OVERVIEW_SHORT_LABELS`'tan **türetilir** (`_ALGO_SHORT_ALIASES`), elle ikinci liste tutulmaz — yeni defter eklenince kısa adı kendiliğinden çalışır.
- **Slot filtresi (varsayılan):** Yalnızca aktif saatlik slot döner — `13:02` open → ertesi saat `14:01` close arası `slot_tr: "13:02-14:01"`. Önceki saatten kalan stale pozisyonlar **dahil edilmez**. `?all=1` ile hepsi (stale işaretli) gelir.
- **`active_slot.status`:** her zaman `active` (ayna turu atlamasın). **`slot_phase`:** `open` (`:02+`) · `pre_open` (`:01`) · `closing` (`:00`). :01'de yeni open yok (settle çakışması).
- **Pozisyon alanları:** `symbol` · `dir` · `amount_usd` · `pm_slug` · `pm_title` · `pm_entry_price` · `slot_tr` · `entry_hour_tr` · `prediction_tr` · `entry_time_tr` · `is_current_slot` · `position_id` (`defter:tarih:saat:sembol` — ayna mükerrer kontrolü için sabit kimlik). `?market=1` (varsayılan) ile `pm_token_id`, `pm_price_now`, `pm_mid_price`, `pm_quote_src`, `pm_price_drift_pct`. `age_sec` gecikme kontrolü için.
- **Kopyalama kararı kaynakta verilir (2026-08-14):** her pozisyonda `copyable` + `block_reason` + `block_detail`; ayna yalnız uygular, eşikleri yeniden yorumlamaz. Engel kodları: `stale_slot` · `stale` · `missing_dir` · `too_old` · `market_closed` · `missing_token` · `no_price` · `price_above_cap` · `price_below_floor` · `adverse_drift` · `no_market_data`. Defter ucunda ayrıca `copyable_count`. **`?market=0` ile karar hesaplanamaz** → alan yazılmamak yerine `no_market_data` ile **kapalı** döner (eksik alan aynada "engel yok" diye okunabiliyordu).
- **Eşikler `policy` altında yayınlanır:** `entry_price_min` 0.40 · `entry_price_max` 0.75 · `max_age_sec` **1200** (20 dk — ayna zinciri ~12 dk gecikmeli; 600 yetmiyordu) · `max_adverse_drift_pct` 40 · `max_spend_ratio` 1.15 · `min_shares` 5.0 (Polymarket alım minimumu). `min_stake_usd` = `5×fiyat/oran`, harcama toleransını aşmayan en küçük niyet tutarı. Her eşik `.env` ile ezilir; **`policy.sources` hangi env anahtarının geçerli olduğunu söyler**, çünkü fiyat eşiklerinin iki adı var: burada `MIRROR_ENTRY_PRICE_MIN/MAX`, ayna sunucusunun kendi kodunda `MIRROR_MIN/MAX_ENTRY_PRICE`. İkisi de okunur, ilki öncelikli.
- **Gece yarısı slot:** `23:02–00:01` kapanırken `00:00` hâlâ 23 slotu; `00:01` pre_open (01:02 beklenir); `00:02+` yeni slot. Pozisyon eşlemesi `_mirror_pos_slot_date` ile giriş gününe sabitlenir.
- **Fiyat = gerçek CLOB best_ask** (`_mirror_ask` → `pm_best_ask`), Gamma mid'i **değil**. Ölçüldü: mid ile ask arası 13 puana kadar açılabiliyor, yani ayna alamayacağı fiyata göre tavan/taban kararı veriyordu (2026-08-13'te ETH 0.77'den doldu, tavan 0.75 iken). Ask okunamazsa mid'e düşülür ve `pm_quote_src` bunu söyler; mid ayrıca `pm_mid_price` alanında durur.
- Kod: `poly_dashboard.py::_mirror_active_slot` · `_mirror_slot_fields` · `_mirror_rows` · `_mirror_market` / `_mirror_ask` · `_mirror_policy` / `_mirror_copy_decision` / `_mirror_min_stake` + iki rota.

## GPSUSDT işlemler API (2026-08-21)
`/forex/gpsusdt/islemler` ekranının salt okunur kopyası. Emir yok, state yazılmaz.

| Uç | Ne döner |
|---|---|
| `GET /forex/api/gpsusdt` | bakiye · açık pozisyon · geçmiş · last_reject · canlı cüzdan |
| `GET /forex/api/gpsusdt/islemler` | aynı |
| `GET /poly/api/forex/gpsusdt` | aynı (eski `/poly/api` yolu) |

- **Kimlik:** `X-Gpsusdt-Token` veya `X-Api-Token` (ya da `?token=`), `.env` → `GPSUSDT_API_TOKEN`. Token yoksa `401`.
- `?limit=` geçmiş satır sayısı (varsayılan 50, tavan 200).

## BIN_XAUUSDT işlemler API (2026-08-21)
`/forex/bin-b103/islemler` ekranının salt okunur kopyası. GPSUSDT API ile aynı biçim. Emir yok.

| Uç | Ne döner |
|---|---|
| `GET /forex/api/bin-b103` | bakiye · açık pozisyon · geçmiş · last_reject · motor · canlı/sanal |
| `GET /forex/api/bin-b103/islemler` | aynı |
| `GET /poly/api/forex/bin-b103` | aynı (eski `/poly/api` yolu) |

- **Kimlik:** `X-Bin-B103-Token` veya `X-Api-Token` (ya da `?token=`), `.env` → `BIN_B103_API_TOKEN`. Yoksa `GPSUSDT_API_TOKEN` kabul. Token yoksa `401`.
- `?limit=` geçmiş satır sayısı (varsayılan 50, tavan 200).

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.

**Poly analiz TG kuralı:** Tüm analizlerde Telegram yalnızca gerçek açılış veya kapanışta gider; “pozisyon yok / sinyal yok / skip / önizleme” log’a yazılır.
