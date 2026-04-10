# hourly_trades — tam liste

Kaynak: `data/trades.db`, tablo `hourly_trades`. Oluşturulma: 2026-04-10 11:00:25 UTC.

## Özet

- Toplam kayıt: **3**
- Başarılı: 1 | Başarısız: 0 | Beklemede: 2 | Emir/işlem hatası: 0

- İşlem açıldı (CLOB): **2** Evet | **1** Hayır (`trade_opened`; hayır = CLOB emri olmadan yazılan tahmin satırı)

- `işlem açıldı`: CLOB üzerinden emir gönderilip `hourly_trades` satırına yazıldıysa Evet (`trade_opened=1`); yalnızca tahmin/çözüm takibi için kayıt varsa Hayır.

---

## Gün ve ET saati özeti (`trade_date_et` × `et_clock_label`)

Sütunlar: kazanç (+) / kayıp (−) / beklemede (?) sayıları.

### 2026-04-09 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 03:00 ET | 1 | 0 | 0 |
| 07:00 ET | 0 | 0 | 2 |

---

## Tüm kayıtlar (sıra: `id`)

| # | coin | `trade_date_et` | ET saat | `predicted_at` (UTC) | durum | işlem açıldı | market (`slug`) |
|---|------|-----------------|---------|----------------------|-------|--------------|-----------------|
| 1 | ethereum | 2026-04-09 | 03:00 ET | `2026-04-10T07:49:50.506316+00:00` | Başarılı | Hayır | `ethereum-up-or-down-april-10-2026-3am-et` |
| 2 | ethereum | 2026-04-09 | 07:00 ET | `2026-04-10T11:00:17.343493+00:00` | Beklemede | Evet | `ethereum-up-or-down-april-10-2026-7am-et` |
| 3 | solana | 2026-04-09 | 07:00 ET | `2026-04-10T11:00:17.343493+00:00` | Beklemede | Evet | `solana-up-or-down-april-10-2026-7am-et` |
