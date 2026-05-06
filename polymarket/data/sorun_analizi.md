# Bot Sorun Analizi

Hazırlanma: 2026-04-16 19:38 UTC  
Kapsam: `data/trades.db` üzerindeki işlem geçmişi (2026-03-27 → 2026-04-16) incelenerek
tespit edilen teknik sorunlar ve yapılan düzeltmeler.

---

## ✅ Çözülen Sorunlar

---

### 1. Likidasyon Sinyali Hiçbir Zaman Çalışmıyordu

**Durum:** ✅ Çözüldü  
**İlgili dosya:** `src/analyzer/poly_predictor.py` → `src/analyzer/poly_predictor_analysis.py`

**Sorun:**  
Eski motor likidasyonu WebSocket stream üzerinden (`forceOrder@arr`) anlık olarak
`states[sym].liq_data` listesine yazıyordu. Oysa bot cron ile çalışıyor: her saat
`python -m src.main open` diyince yeni bir Python process başlıyor, `states` sıfırlanıyor
ve WebSocket hiç açılmıyor. Sonuç: `liq_data` her zaman boş, sinyal her zaman
`NEUTRAL` dönüyordu.

Bu durum confidence hesaplamasını da bozuyordu: ağırlık 2 olan bu sinyal hiçbir zaman
`bull_pts` veya `bear_pts`'e eklenmiyordu; ancak `total_w`'ye hep +2 ekleniyordu.
Yani payda şişiyor, pay şişmiyordu → YÜKSEK güven eşiğine ulaşmak zorlaşıyordu.

**Çözüm:**  
Yeni motor `_fetch_liquidations()` fonksiyonu ile REST endpoint'ten son 100 likidasyonu
çekiyor (`fapi.binance.com/fapi/v1/allForceOrders`). Bu endpoint public ve her çağrıda
gerçek veri döndürüyor. WebSocket gerektirmiyor.

---

### 2. CVD 5dk ve 30dk Sinyalleri Aynı Veriyi Ölçüyordu

**Durum:** ✅ Çözüldü  
**İlgili dosya:** `src/analyzer/poly_predictor.py` → `src/analyzer/poly_predictor_analysis.py`

**Sorun:**  
Eski motor CVD hesabı için `fetch_recent_trades_rest()` ile 500 aggTrade çekiyordu.
ETH Futures gibi likit markette 500 aggTrade yoğun saatlerde yalnızca 10–60 saniyeyi
kapsıyor. `cvd(300)` (5 dakika) ve `cvd(1800)` (30 dakika) fonksiyonları `time.time() - seconds`
ile filtreleme yapıyordu; ancak elimizdeki tüm trade'ler zaten bu kısa pencere içindeydi.
İki "farklı" sinyal aslında aynı 60 saniyelik veriyi görüyordu. Toplam 5 ağırlık noktası
tek bir kısa anlık ölçüme dayanıyordu.

**Çözüm:**  
Yeni motor kline bazlı taker buy oranını kullanıyor:

- CVD 5dk → `"5m"` interval, `limit=6` (son ~30 dakika, 6 adet 5m bar)
- CVD 30dk → `"30m"` interval, `limit=2` (son ~1 saat, 2 adet 30m bar)

Her bar içindeki `taker_buy_base_asset_volume / total_volume` oranı `[-1, +1]` aralığında
normalize ediliyor. İki sinyal gerçekten bağımsız zaman penceresini kapsıyor.

---

### 3. Large Trade Bias Bozuk Veriyle Çalışıyordu

**Durum:** ✅ Çözüldü  
**İlgili dosya:** `src/analyzer/poly_predictor.py` → `src/analyzer/poly_predictor_analysis.py`

**Sorun:**  
Eski motor büyük işlem yönü için yine aynı 500 aggTrade verisini kullanıyor, `>$100K`
sabit USD threshold arıyordu. Kısa veri penceresinde bu eşiği geçen işlem çoğunlukla
bulunamıyor, sinyal neredeyse her zaman `NEUTRAL` dönüyordu. Ağırlık 3.

**Çözüm:**  
Yeni motor 1000 aggTrade çekiyor ve **dinamik eşik** kullanıyor: büyüklüğe göre sıralanan
işlemlerin üst %10'u "büyük işlem" sayılıyor. Bu yöntem piyasa koşullarına göre kendiliğinden
adapte oluyor; düşük hacimli saatlerde de anlamlı sinyal üretiyor.

---

### 4. Motor Cron ile Uyumsuzdu (Yapısal Sorun)

**Durum:** ✅ Çözüldü  
**İlgili dosya:** `src/analyzer/poly_predictor.py` → `src/analyzer/poly_predictor_analysis.py`

**Sorun:**  
Eski motor (`poly_predictor.py`) WebSocket stream'leri sürekli açık tutan ve
`asyncio.sleep(120)` ile 2 dakika bekleyerek veri biriktiren bir long-running process
olarak tasarlanmıştı. Bot ise cron ile her saat ayrı bir process olarak çalışıyordu.
Her process başlangıcında `states` tamamen sıfırlanıyor, WebSocket hiç açılmıyordu.
Likidasyon, anlık OB güncellemeleri ve tick-bazlı CVD verileri hiçbir zaman doğru
biriktirilmiyordu.

**Çözüm:**  
Yeni motor (`poly_predictor_analysis.py`) tamamen stateless REST tasarımına sahip.
Her çağrıda tüm veri `asyncio.gather` ile paralel olarak REST'ten çekiliyor; WebSocket
veya warm-up süresi gerektirmiyor. Cron mimarisiyle tam uyumlu.

---

### 5. BTC Sisteme Dahil Değildi

**Durum:** ✅ Çözüldü  
**İlgili dosyalar:** `pipeline.py`, `market_fetcher.py`, `poly_bridge.py`,
`poly_predictor_analysis.py`, `hourly_trades.py`

**Sorun:**  
`COINS`, `SYMBOL_FOR_COIN`, `HOURLY_UP_DOWN_COINS` ve tahmin motoru yalnızca ETH ve SOL
için tanımlanmıştı. BTC için Polymarket marketi mevcut olmasına rağmen tahmin üretilmiyor,
emir açılmıyordu. DB'de yalnızca eski dönemden kalma bitcoin kayıtları bulunuyordu.

**Çözüm:**  
Tüm coin listelerine `bitcoin` / `BTCUSDT` eklendi. Artık her saat başında BTC, ETH ve SOL
için paralel tahmin üretiliyor ve `bitcoin-up-or-down-...` Polymarket marketleri işleme dahil.

---

### 6. Günlük Sıfırlanma 16:00 TR'de Oluyordu

**Durum:** ✅ Çözüldü  
**İlgili dosya:** `src/analyzer/pipeline.py`

**Sorun:**  
`_business_day_date_tr()` TR saatiyle 16:00'ı iş günü kesim noktası olarak kullanıyordu.
Bu, gece yarısı ile 16:00 arasındaki tahminlerin bir önceki güne yazılmasına yol açıyordu.
Sezgisel olmayan bir davranış ve gün özeti istatistiklerini yanıltıcı hale getiriyordu.

**Çözüm:**  
Kesim noktası TR takvim gününün başına (**00:00 TR**) alındı. Artık `trade_date_et` değeri
TR saat dilimiyle doğrudan örtüşüyor. Telegram gün özeti de buna göre güncellendi:
00:00–00:59 arası çalışan `resolve` cron'u hâlâ önceki günü göstererek boş bildirim
gönderilmesini önlüyor.

---

## ⚠️ Devam Eden Sorunlar

---

### 7. Makro Rejim Değişikliklerinde Model Başarısızlığı

**Durum:** ⚠️ Devam ediyor — yapısal model sınırı  
**İlgili dosya:** `src/analyzer/poly_predictor_analysis.py`

**Sorun:**  
İşlem geçmişinde 2 Nisan 2026 ("Liberation Day" ABD tarife duyurusu) sonrasında başarı
oranının sert düştüğü gözlemlendi:

```
2026-03-28: %75  (18/24)  ← en iyi dönem
2026-03-29: %69  ( 9/13)
2026-03-31: %32  ( 6/19)  ← ilk düşüş
2026-04-03: %25  ( 4/16)  ← tarife şoku
2026-04-04: %38  ( 6/16)
2026-04-05: %41  ( 7/17)
```

RSI, MACD, EMA, CVD gibi momentum ve teknik analiz sinyalleri trendin devam ettiği
"normal" piyasa koşullarında anlamlı tahmin üretiyor. Ancak ani makro olaylar (merkez
bankası kararı, jeopolitik gelişme, büyük düzenleyici haber) piyasayı teknik seviyelerden
bağımsız hareket ettiriyor; bu durumda teknik sinyal tabanlı modeller sistematik olarak
başarısız oluyor.

**Neden çözülmedi:**  
Bu bir implementasyon hatası değil, kullanılan metodolojinin (teknik analiz + order flow)
temel bir sınırı. Çözüm için haber akışı, sosyal medya sentiment verisi veya makroekonomik
takvim verisi gibi ek veri kaynakları gerekiyor; bu kapsam dışında tutuldu.

---

### 8. Order Book Hâlâ Tek Anlık Snapshot

**Durum:** ⚠️ Devam ediyor — düşük öncelik  
**İlgili dosya:** `src/analyzer/poly_predictor_analysis.py`

**Sorun:**  
Hem eski hem yeni motorda OB verisi tek bir REST snapshot olarak alınıyor. Gerçek zamanlı
bir piyasada emir kitabı saniyeler içinde değişebilir; tahmin anındaki tek fotoğraf kısa
vadeli manipülasyona (spoof emirleri) karşı hassas.

**Fark:**  
Eski motorda bu bir *bozulma* — WebSocket tabanlı sürekli güncel OB beklenirken cron
nedeniyle hiç güncellenmiyordu. Yeni motorda ise *tasarım gereği* snapshot alınıyor;
bir regresyon yok.

**Neden çözülmedi:**  
OB snapshot Polymarket saatlik UP/DOWN tahmini için kabul edilebilir bir yaklaşım.
Gerçek zamanlı OB takibi için sürekli çalışan bir WebSocket process mimarisi gerekiyor;
mevcut cron tasarımıyla uyumsuz.

---

### 9. Confidence Eşiği (0.65) Henüz Kalibre Edilmedi

**Durum:** ⚠️ İzleme gerekiyor  
**İlgili dosya:** `src/analyzer/poly_bridge.py`

**Sorun:**  
Yeni motorda `prob_up >= 0.65` → YÜKSEK güven eşiği eski sistemdeki `gap >= total_w × 40%`
mantığından türetildi. Ancak iki motorun puanlama dinamiği farklı; bu eşiğin yeni motor
üzerinde gerçek performansı henüz gözlemlenmedi.

Eşik çok düşükse az güvenilir sinyallerle işlem açılır; çok yüksekse az sayıda işlem
açılır ve fırsat kaçırılır.

**Öneri:**  
İlk 2–3 hafta paper trade (POLYMARKET_TRADING_ENABLED=false) modunda çalıştırarak
hangi `prob_up` değerlerinin gerçekten başarıya dönüştüğü gözlemlenebilir. Bu veriye
dayanarak eşik optimize edilebilir.
