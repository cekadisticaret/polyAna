# aiProject — Proje Yapısı

## Genel Bakış
Kripto ve BIST piyasaları için otomatik analiz, paper trading ve sosyal medya paylaşım sistemi.

---

## Modüller

### Kripto — Paper Trading (15m)
| Dosya | Açıklama |
|---|---|
| `paper_trader.py` | 15m OKX/Binance verisiyle Long/Short paper trading motoru. EMA21/100, MACD 8/21/5, RSI 14, ADX 22, ATR SL/TP. 10x kaldıraç, 200 USDT sanal sermaye. Tüm işlemler 15m barla (5m kaldırıldı). |
| `paper_trader_alternatif.py` | Confluence stratejisi (Pine Scalping Confluence → Python). 6 faktör, min 3 confluence + EMA cross + R:R filtresi. Ayrı Telegram, ayrı state. |
| `paper_trader_alt_config.py` | Alternatif Telegram bot token/chat_id (gitignore). |
| `crypto_futures_list.py` | Binance Futures'da aktif 202 coin sembolü listesi. |
| `paper_trades.json` | Açık/kapalı işlemler ve sermaye durumu (runtime verisi). |
| `paper_trades_alt.json` | Alternatif paper trader state. |
| `paper_report.json` | 100 işlem tamamlandığında üretilen performans raporu. |

**Cron:** `*/5 * * * *` → her 5 dakikada bir (`/tmp/paper_trader.log`). Alternatif: `*/5 * * * *` → `/tmp/paper_trader_alt.log`

### Kripto — Binance Gerçek Trader (15m)
| Dosya | Açıklama |
|---|---|
| `binance_trader.py` | paper_trader ile aynı sinyal + swing SL/TP; margin = min(%10 hedef, serbest). MAX_OPEN 8 (paper ile aynı); `[binance_open]` logları. |
| `binance_api.py` | Binance USDT-M Futures API istemcisi (HMAC imzalı, urllib). |
| `binance_config.py` | API key/secret (gitignore). |
| `binance_state.json` | Açık pozisyonlar ve bar sayacı (runtime). |

**Cron:** `*/5 * * * *` → her 5 dk (`/tmp/binance_trader.log`) — paper_trader ile aynı zamanlama

**Strateji parametreleri (v3 — 18.03.2026 — HTF filtresi eklendi):**
- LEVERAGE: 10x | POS_SIZE_PCT: %10 | MAX_OPEN: 8 (paper ve binance) | **paper:** BULL/BEAR yön limiti | **binance:** yön limiti yok; margin serbeste göre kısılır
- STOP_ATR_MULT: 2.0 | TAKE_ATR_MULT: 4.5 | MAX_SL_PCT: %0.8 | ADX eşiği: 22 | R:R ≈ 1:2.25
- COOLDOWN_BARS: 4 (60 dk) | MIN_HOLD_BARS: 2 (30 dk)
- **Per-coin HTF filtresi (1h EMA21):** her coin kendi 1h trendine göre yön doğrulaması yapar; BTC piyasa biası kaldırıldı
- Trailing stop yok — sade SL / TP / sinyal çıkışı
- Hacim spike: vol > ort×1.5 | Hacim onayı: vol > max(son 12 bar)×1.2
- Exit: SL hit | TP hit | RSI>75 | EMA100 ihlali | MACD bear + RSI düşüyor (ikisi birden)
- Her 100 işlemde rapor, sistem duraksız çalışır

---

### BIST — Tarayıcı & Görsel
| Dosya | Açıklama |
|---|---|
| `bist_scanner.py` | 427 BIST hissesini tarar. `scan()`: 1h trend taraması (EMA50/200, RSI, ADX, MACD, Hacim, Likidite). `scan_momentum()`: günlük ≥%5 hareket + RSI>50 + likidite. |
| `bist_scanner_v1_backup.py` | 16.03.2026 önceki scanner yedeği. |
| `bist_visual_v2.py` | Ana çalıştırıcı: trend + momentum taramalarını çalıştırır, iki bölümlü kart görseli üretir, Telegram'a gönderir. |
| `bist_tickers.py` | BIST sembol listesi. |
| `bist_sender.py` | BIST sonuçlarını düz metin olarak Telegram'a gönderici. |
| `bist_visual_sender.py` | BIST sonuçlarını tablo görseli olarak Telegram'a gönderici. |
| `bist_scalping_alerts.py` | 427 hisse 15m Scalping Confluence (Pine ile uyumlu): AL + TP1. Telegram özel mesaj: `bist_scalping_config.py` — `CHAT_ID` = kullanıcı ID. `bist_scalping_get_chat_id.py` yardımcı. State: `bist_scalping_state.json`. |

**Cron:** `1 7-15 * * 1-5` → haftaiçi 10:01–18:01 İST arası her saat başı (`/tmp/bist_visual.log`)

**BIST Scalping AL:** `*/5 * * * 1-5` → `python3 bist_scalping_alerts.py` → `/tmp/bist_scalping_alerts.log` (script sadece **Pazartesi–Cuma 10:00–18:00 İST** çalışır; dışında hemen çıkar)

---

### Kripto & BIST — Tweet Otomasyonu (@ZekaChain)
| Dosya | Açıklama |
|---|---|
| `crypto_tweet_generator.py` | Binance 30m verisinden en çok düşen coinleri alır, `fetch_all_changes()` sağlar. |
| `twitter_poster.py` | Kripto ve BIST alınabilir listelerini görsel ile Twitter/X'e paylaşır. `mode: crypto|bist|both` |
| `twitter_config.py` | Twitter API token'larını `.env` dosyasından okur. |
| `.env` | Twitter API key/secret/token (plaintext tutulmaz, git'e eklenmez). |

**Cron:** `0 8 * * *` → her gün 08:00 UTC (11:00 İST) both mod (`/tmp/twitter_poster.log`)

---

### Altyapı & Konfigürasyon
| Dosya | Açıklama |
|---|---|
| `telegram_config.py` | Telegram bot token ve chat ID ayarları. |
| `crypto_list.py` | Genel kripto sembol listesi (spot). |
| `backup.py` | Günlük 23:59'da tüm proje dosyalarını `backups/` klasörüne tar.gz olarak yedekler. Son 7 gün saklanır. |

**Cron:** `59 23 * * *` → her gün 23:59 (`/tmp/backup.log`) | Yedek: `backups/aiProject_YYYYMMDD_HHMM.tar.gz`

---

### Analiz — Order Flow Scanner
| Dosya | Açıklama |
|---|---|
| `analiz/order_scanner.py` | CVD, imbalance, sweep — Telegram bildirimi, state.json. systemd servisi. |
| `analiz/web_server.py` | Web dashboard (port 8765). |
| `analiz/analiz_config.py` | Telegram bot (gitignore). |

**Servis:** `order-scanner` systemd | Log: `/tmp/order_scanner.log`

---

### Kripto — Scalp Paper Trading (5m+15m)
| Dosya | Açıklama |
|---|---|
| `scalp_trader.py` | 5m sinyal + 15m çıkış kararı. EMA21/55/100, MACD 8/21/5, RSI 14, ADX 22. ATR SL×3.5, TP×8.5. TP'ye ulaşınca kapat. 50 major coin. |
| `scalp_trader_winrate35.py` | v2 yedeği — %35.4 WR, 200→153 USDT (−%23.4). TP çalışmıyordu, trail çok sıkıydı. |
| `scalp_trades.json` | Açık/kapalı işlemler ve sermaye (runtime verisi). |
| `scalp_reports/scalp_16032026.json` | 16.03.2026 arşivi — 144 işlem, 200→153.17 USDT (%−23.4). |

**Cron:** `* * * * *` → her dakika (`/tmp/scalp_trader.log`)

**Strateji parametreleri (v3 — 17.03.2026):**
- LEVERAGE: 10x (skor≥60 → 15x) | POS_SIZE_PCT: %10 | MAX_OPEN: 3
- STOP_ATR_MULT: 3.5 | TAKE_ATR_MULT: 8.5 | MAX_SL_PCT: %0.7 | ADX eşiği: 22
- COOLDOWN_BARS: 20 (100 dk) | MIN_HOLD_BARS: 6 (30 dk) | TRAIL_ATR_MULT: 3.5
- MIN_ENTRY_SCORE: 62 | MAX_NEW_PER_SCAN: 1 (senkronize giriş önlenir)
- Giriş: 5m analiz | Çıkış sinyali: 15m analiz → 5m gürültüsü filtrelenir
- RSI giriş: >58 (long), <42 (short) | Saatlik rapor (12 bar)
- **v3 değişiklikleri:** TP artık pozisyonu kapatıyor | TRAIL_ATR_MULT 2.0→3.5 | EMA100 makro trend filtresi eklendi

---

### PineScript Stratejiler
| Dosya | Açıklama |
|---|---|
| `crypto_strategy_15m_v2.pine` | 15m kripto strateji (paper_trader.py ile uyumlu). |
| `crypto_macd_pro_15m_v2.pine` | MACD Pro 15m strateji. |

---

## Telegram Bildirimleri
- İşlem açılışı / kapanışı anlık mesaj
- 100 işlem tamamlanınca özet rapor + tüm işlem listesi
- Her işlem bildiriminin altında `─ ─ ─` ayraç çizgisi
- Kapanış mesajında komisyon ayrı satırda gösterilir

---

## Karar Geçmişi (15.03.2026)

### 1h → 15m geçişi
- Sistem 1h barla çalışıyordu, 1 saatte 1 sinyal fırsatı → hiç işlem bulamıyordu
- `is_new_hour` → `is_new_15m` (`minute % 15 <= 4`) değiştirildi
- Giriş ve çıkış sinyalleri `analyze(symbol, "15m")` olarak güncellendi

### Paralel tarama eklendi
- 202 coin sıralı taranınca 85 saniye sürüyordu (5 dk cron için tehlikeli)
- `ThreadPoolExecutor(max_workers=30)` ile 7 saniyeye düşürüldü

### PineScript ile hizalama (SL/TP/ADX)
- PineScript parametreleri ile paper_trader uyumsuzdu:
  - ADX eşiği: 25 → **22** (PineScript ile eşitlendi)
  - STOP_ATR_MULT: 1.2 → **2.5** (15m spike'larına karşı geniş stop)
  - TAKE_ATR_MULT: 2.8 → **4.0**
  - MAX_SL_PCT: %0.35 → **%0.6**
  - COOLDOWN_BARS: 5 → **4**
- Amaç: TradingView'da LONG/SHORT işareti gördüğünde paper trader da aynı sinyali görmeli

### Dinamik kaldıraç (skor ≥ 60 → 15x)
- Her işlem için 0–100 sinyal skoru hesaplanır (RSI gücü, ADX gücü, EMA mesafesi, hacim)
- Skor ≥ 60 ise 15x, altında 10x kaldıraç kullanılır
- Skor ve kaldıraç Telegram bildiriminde gösterilir

### Komisyon eklendi
- Giriş %0.05 + Çıkış %0.05 = notional üzerinden %0.1 toplam
- `close_position`'da PnL'den otomatik düşülür, bildirimde ayrı satırda gösterilir

### vol_spike gevşetildi (×1.5 → ×1.2)
- Filtre analizi: 201 coin, LONG yönünde ADX 77 coin, vol_spike 39 coin eliyordu
- ADX düşürmek (seçenek A) trend kalitesini bozar, daha fazla whipsaw riski
- vol_spike ×1.5 → ×1.2 (seçenek B): trend kalitesi korunur, daha fazla sinyal
- PineScript'te de `volMult` 1.5 → 1.2 olarak güncellendi

### 6 saatlik rapor bug düzeltmesi
- `cur_bar % 24 == 0` koşulu `is_new_15m` olmadan kontrol ediliyordu
- `total_bars` 24'ün katında sabit kalırken cron her 5 dk rapor gönderiyordu
- Düzeltme: `is_new_15m AND cur_bar % 24 == 0 AND cur_bar > 0`

### Günlük yedekleme (backup.py)
- Her gün 23:59'da `backups/aiProject_YYYYMMDD_HHMM.tar.gz` oluşturur
- `.env`, `__pycache__`, `backups/`, runtime JSON'lar hariç tutulur
- Tüm yedekler birikir, silinmez

### Scalp Trader v2 — 1m→5m geçişi (16.03.2026)
- v1 sonuçları: 144 işlem, %100 stop loss, ort. tutma 2.9 dk, −23.4% sermaye
- Temel sorunlar: 1m wick'leri SL'yi vuruyordu, senkronize 5 giriş aynı anda stop yiyordu
- v2 değişiklikleri: giriş 5m, çıkış 15m, MAX_OPEN 5→3, MAX_NEW_PER_SCAN=1, MIN_SCORE=62, SL genişletildi
- Eski veri: `scalp_reports/scalp_16032026.json`

### Scalp Trader v3 — TP düzeltmesi + trail genişletme (17.03.2026)
- v2 analizi: 144 işlem, %35.4 WR, SIFIR TP çıkışı, LONG %32 WR vs SHORT %43 WR
- Sorunlar: TP'ye ulaşınca kapatmak yerine trail sıkılaştırıp TP uzatıyordu; TRAIL_ATR_MULT=2.0 ile SL ATR×1.0'a sıkışıyordu (beklenen ATR×3.5)
- v3 düzeltmeleri: (1) `tp_hit` → `close_position("TAKE PROFIT")` eklendi, (2) TRAIL_ATR_MULT 2.0→3.5, (3) EMA100 makro trend filtresi eklendi (LONG için macro_bull, SHORT için macro_bear)
- Yedek: `scalp_trader_winrate35.py`

### BIST Telegram chat ID güncellendi (16.03.2026)
- Grup üye sayısı arttığı için Telegram otomatik olarak **supergroup'a** yükseltti
- Eski ID: `-5179547954` → Yeni ID: `-1003821803200`
- `telegram_config.py` güncellendi; `bist_visual_v2.py` artık görseli başarıyla gönderiyor
