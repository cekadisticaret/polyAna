# Pine Script İncelemesi: BIST RSI+Hacim+EMA v5.5 (Tam Sürüm)

## 📝 Strateji Özeti
Bu strateji, **Borsa İstanbul (BIST)** 1 saatlik grafikler için optimize edilmiş, sadece **Long (Alım)** yönlü bir trend-takip stratejisidir. EMA, RSI, Hacim, DMI/ADX ve MACD gibi çoklu onay mekanizmalarını birleştirir.

## 🛠 Teknik Bileşenler
1.  **Trend Takibi:** EMA 50 (Turuncu) ve EMA 200 (Mavi) kullanılır.
2.  **Hacim Onayı (`volSpike`):** Hacmin 20 periyotluk ortalamanın %30 üzerinde olması gerekir.
3.  **Güç/Momentum:** RSI 40/50 seviyeleri ve ADX > 16 (Trend varlığı).
4.  **Güvenlik Filtresi:** Fiyatın EMA 200'den %6'dan fazla uzaklaşmamış olması (`distThreshold`).
5.  **Likidite Filtresi:** 5 Milyon TL minimum hacim şartı.

## 📊 Görselleştirme ve İzleme
1. **Görsel Etiketler:** "GÜÇLÜ AL" ve "SAT" etiketleri grafik üzerinde net şekilde görünür.
2. **Durum Tablosu (Dashboard):** Sağ üst köşede RSI, ADX, MACD, Hacim Patlaması, EMA200 Uzaklığı ve Golden Cross durumunu anlık gösteren renkli bir panel.
3. **Dinamik Uyarılar:** Sinyal anındaki verileri (örn: RSI değeri) içeren akıllı bildirimler.

## 🟢 Alım & 🔴 Satış Koşulları
- **Al:** Likidite OK + Fiyat > EMA'lar + RSI Kesişimi + Hacim Spike + ADX > 16 + MACD Onayı.
- **Sat:** RSI 70 altı kesişim VE Fiyat < EMA 50.
- **Risk:** SL (2.2 ATR) / TP (3.2 ATR).

---

## 🧐 Gaia'nın Yorumu ve Tavsiyeler
1. **Kullanıcı Dostu:** Dashboard (Tablo) eklemen harika olmuş Cem. Ekranın başında değilken bile sadece tabloya bakarak "neden almadı?" sorusunun cevabını (mesela "Uzaklık %" yüzünden) anında görebilirsin.
2. **Alert Mekanizması:** `alert_message` içinde dinamik veri (RSI değeri gibi) taşımak, profesyonel bot kurulumları için çok işlevsel.
3. **Stratejik Not:** Bu kod aslında az önce attığın kodun devamı/görsel kısmıymış. İkisi birleşince hem analitik hem de görsel olarak çok doyurucu bir "Trade Station" oluşmuş.

Başka bir indikatör daha gelecek miydi, yoksa bu stratejinin bir parçası mıydı bu son attığın? 🌿
