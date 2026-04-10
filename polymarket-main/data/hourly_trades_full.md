# hourly_trades — tam liste

Kaynak: `data/trades.db`, tablo `hourly_trades`. Oluşturulma: 2026-04-06 17:28:22 UTC.

## Özet

- Toplam kayıt: **212**
- Başarılı: 110 | Başarısız: 102 | Beklemede: 0 | Emir/işlem hatası: 0

- İşlem açıldı (CLOB): **204** Evet | **8** Hayır (`trade_opened`; hayır = CLOB emri olmadan yazılan tahmin satırı)

- `işlem açıldı`: CLOB üzerinden emir gönderilip `hourly_trades` satırına yazıldıysa Evet (`trade_opened=1`); yalnızca tahmin/çözüm takibi için kayıt varsa Hayır.

---

## Gün ve ET saati özeti (`trade_date_et` × `et_clock_label`)

Sütunlar: kazanç (+) / kayıp (−) / beklemede (?) sayıları.

### 2026-03-27 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 05:00 ET | 1 | 0 | 0 |
| 06:00 ET | 1 | 0 | 0 |
| 07:00 ET | 0 | 1 | 0 |
| 10:00 ET | 0 | 2 | 0 |
| 11:00 ET | 1 | 0 | 0 |
| 12:00 ET | 2 | 0 | 0 |
| 16:00 ET | 2 | 0 | 0 |
| 17:00 ET | 0 | 1 | 0 |
| 18:00 ET | 1 | 1 | 0 |
| 19:00 ET | 0 | 1 | 0 |
| 20:00 ET | 0 | 1 | 0 |
| 21:00 ET | 0 | 1 | 0 |
| 22:00 ET | 0 | 1 | 0 |

### 2026-03-28 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 00:00 ET | 1 | 0 | 0 |
| 01:00 ET | 2 | 0 | 0 |
| 02:00 ET | 2 | 0 | 0 |
| 04:00 ET | 0 | 1 | 0 |
| 05:00 ET | 1 | 0 | 0 |
| 07:00 ET | 2 | 0 | 0 |
| 08:00 ET | 2 | 0 | 0 |
| 09:00 ET | 2 | 0 | 0 |
| 11:00 ET | 1 | 0 | 0 |
| 12:00 ET | 0 | 1 | 0 |
| 13:00 ET | 0 | 1 | 0 |
| 14:00 ET | 1 | 0 | 0 |
| 16:00 ET | 1 | 1 | 0 |
| 19:00 ET | 0 | 2 | 0 |
| 20:00 ET | 1 | 0 | 0 |
| 21:00 ET | 1 | 0 | 0 |
| 23:00 ET | 1 | 0 | 0 |

### 2026-03-29 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 00:00 ET | 1 | 0 | 0 |
| 01:00 ET | 1 | 1 | 0 |
| 02:00 ET | 1 | 1 | 0 |
| 03:00 ET | 1 | 1 | 0 |
| 04:00 ET | 1 | 1 | 0 |
| 06:00 ET | 1 | 0 | 0 |
| 09:00 ET | 1 | 0 | 0 |
| 22:00 ET | 1 | 0 | 0 |
| 23:00 ET | 1 | 0 | 0 |

### 2026-03-30 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 00:00 ET | 1 | 0 | 0 |
| 02:00 ET | 0 | 2 | 0 |
| 04:00 ET | 1 | 0 | 0 |
| 07:00 ET | 1 | 0 | 0 |
| 08:00 ET | 2 | 0 | 0 |
| 09:00 ET | 0 | 1 | 0 |
| 10:00 ET | 2 | 0 | 0 |
| 11:00 ET | 1 | 1 | 0 |
| 13:00 ET | 0 | 1 | 0 |
| 14:00 ET | 0 | 1 | 0 |
| 16:00 ET | 1 | 1 | 0 |
| 17:00 ET | 0 | 2 | 0 |
| 18:00 ET | 1 | 0 | 0 |
| 22:00 ET | 1 | 0 | 0 |

### 2026-03-31 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 00:00 ET | 0 | 1 | 0 |
| 01:00 ET | 1 | 0 | 0 |
| 02:00 ET | 0 | 2 | 0 |
| 03:00 ET | 0 | 2 | 0 |
| 05:00 ET | 0 | 1 | 0 |
| 06:00 ET | 0 | 1 | 0 |
| 10:00 ET | 0 | 1 | 0 |
| 12:00 ET | 0 | 1 | 0 |
| 13:00 ET | 1 | 0 | 0 |
| 14:00 ET | 1 | 0 | 0 |
| 15:00 ET | 0 | 2 | 0 |
| 16:00 ET | 2 | 0 | 0 |
| 17:00 ET | 0 | 1 | 0 |
| 18:00 ET | 0 | 1 | 0 |
| 20:00 ET | 1 | 0 | 0 |

### 2026-04-01 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 00:00 ET | 3 | 0 | 0 |
| 01:00 ET | 2 | 0 | 0 |
| 02:00 ET | 2 | 0 | 0 |
| 03:00 ET | 0 | 4 | 0 |
| 04:00 ET | 2 | 0 | 0 |
| 05:00 ET | 0 | 1 | 0 |
| 06:00 ET | 0 | 1 | 0 |
| 07:00 ET | 2 | 0 | 0 |
| 08:00 ET | 2 | 1 | 0 |
| 09:00 ET | 1 | 2 | 0 |
| 10:00 ET | 1 | 0 | 0 |
| 11:00 ET | 1 | 0 | 0 |
| 12:00 ET | 1 | 1 | 0 |
| 13:00 ET | 0 | 1 | 0 |
| 14:00 ET | 0 | 1 | 0 |
| 15:00 ET | 0 | 1 | 0 |
| 16:00 ET | 0 | 2 | 0 |
| 17:00 ET | 1 | 2 | 0 |
| 18:00 ET | 2 | 0 | 0 |
| 20:00 ET | 1 | 2 | 0 |
| 21:00 ET | 3 | 0 | 0 |
| 22:00 ET | 2 | 0 | 0 |
| 23:00 ET | 1 | 1 | 0 |

### 2026-04-02 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 10:00 ET | 0 | 2 | 0 |
| 11:00 ET | 1 | 0 | 0 |
| 12:00 ET | 1 | 1 | 0 |
| 14:00 ET | 0 | 1 | 0 |
| 15:00 ET | 1 | 1 | 0 |
| 17:00 ET | 1 | 0 | 0 |
| 18:00 ET | 1 | 1 | 0 |
| 19:00 ET | 1 | 0 | 0 |
| 20:00 ET | 0 | 1 | 0 |
| 22:00 ET | 1 | 0 | 0 |
| 23:00 ET | 1 | 0 | 0 |

### 2026-04-03 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 01:00 ET | 0 | 1 | 0 |
| 03:00 ET | 0 | 1 | 0 |
| 04:00 ET | 0 | 1 | 0 |
| 06:00 ET | 1 | 1 | 0 |
| 07:00 ET | 0 | 1 | 0 |
| 12:00 ET | 1 | 0 | 0 |
| 16:00 ET | 0 | 2 | 0 |
| 17:00 ET | 0 | 1 | 0 |
| 18:00 ET | 0 | 1 | 0 |
| 20:00 ET | 0 | 1 | 0 |
| 21:00 ET | 0 | 1 | 0 |
| 22:00 ET | 1 | 0 | 0 |
| 23:00 ET | 1 | 1 | 0 |

### 2026-04-04 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 01:00 ET | 1 | 0 | 0 |
| 02:00 ET | 1 | 0 | 0 |
| 03:00 ET | 0 | 1 | 0 |
| 04:00 ET | 0 | 2 | 0 |
| 06:00 ET | 0 | 1 | 0 |
| 09:00 ET | 1 | 0 | 0 |
| 11:00 ET | 1 | 0 | 0 |
| 12:00 ET | 0 | 1 | 0 |
| 14:00 ET | 0 | 1 | 0 |
| 17:00 ET | 1 | 0 | 0 |
| 18:00 ET | 1 | 0 | 0 |
| 19:00 ET | 0 | 2 | 0 |
| 20:00 ET | 0 | 2 | 0 |

### 2026-04-05 (ET iş günü)

| ET saati | + kazanç | − kayıp | ? beklemede |
|----------|----------|---------|-------------|
| 00:00 ET | 1 | 1 | 0 |
| 02:00 ET | 0 | 1 | 0 |
| 03:00 ET | 2 | 0 | 0 |
| 04:00 ET | 1 | 0 | 0 |
| 05:00 ET | 2 | 0 | 0 |
| 09:00 ET | 0 | 2 | 0 |
| 10:00 ET | 0 | 2 | 0 |
| 11:00 ET | 0 | 1 | 0 |
| 12:00 ET | 1 | 1 | 0 |
| 13:00 ET | 1 | 1 | 0 |
| 14:00 ET | 1 | 1 | 0 |
| 16:00 ET | 1 | 0 | 0 |
| 18:00 ET | 1 | 0 | 0 |
| 20:00 ET | 2 | 0 | 0 |
| 21:00 ET | 0 | 1 | 0 |
| 23:00 ET | 0 | 1 | 0 |

---

## Tüm kayıtlar (sıra: `id`)

| # | coin | `trade_date_et` | ET saat | `predicted_at` (UTC) | durum | işlem açıldı | market (`slug`) |
|---|------|-----------------|---------|----------------------|-------|--------------|-----------------|
| 1 | ethereum | 2026-03-27 | 05:00 ET | `2026-03-27T09:44:29.298727+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-27-2026-5am-et` |
| 2 | bitcoin | 2026-03-27 | 06:00 ET | `2026-03-27T10:00:02.947191+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-27-2026-6am-et` |
| 3 | ethereum | 2026-03-27 | 07:00 ET | `2026-03-27T11:00:03.535248+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-27-2026-7am-et` |
| 4 | bitcoin | 2026-03-27 | 10:00 ET | `2026-03-27T14:00:02.641679+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-27-2026-10am-et` |
| 5 | ethereum | 2026-03-27 | 10:00 ET | `2026-03-27T14:00:02.641679+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-27-2026-10am-et` |
| 6 | bitcoin | 2026-03-27 | 11:00 ET | `2026-03-27T15:00:03.348699+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-27-2026-11am-et` |
| 7 | bitcoin | 2026-03-27 | 12:00 ET | `2026-03-27T16:00:03.020955+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-27-2026-12pm-et` |
| 8 | ethereum | 2026-03-27 | 12:00 ET | `2026-03-27T16:00:03.020955+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-27-2026-12pm-et` |
| 9 | bitcoin | 2026-03-27 | 16:00 ET | `2026-03-27T20:00:02.933433+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-27-2026-4pm-et` |
| 10 | ethereum | 2026-03-27 | 16:00 ET | `2026-03-27T20:00:02.933433+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-27-2026-4pm-et` |
| 11 | bitcoin | 2026-03-27 | 17:00 ET | `2026-03-27T21:00:03.390915+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-27-2026-5pm-et` |
| 12 | bitcoin | 2026-03-27 | 18:00 ET | `2026-03-27T22:00:03.360070+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-27-2026-6pm-et` |
| 13 | ethereum | 2026-03-27 | 18:00 ET | `2026-03-27T22:00:03.360070+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-27-2026-6pm-et` |
| 14 | ethereum | 2026-03-27 | 19:00 ET | `2026-03-27T23:00:03.616595+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-27-2026-7pm-et` |
| 15 | bitcoin | 2026-03-27 | 20:00 ET | `2026-03-28T00:00:04.828708+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-27-2026-8pm-et` |
| 16 | ethereum | 2026-03-27 | 21:00 ET | `2026-03-28T01:00:03.392266+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-27-2026-9pm-et` |
| 17 | ethereum | 2026-03-27 | 22:00 ET | `2026-03-28T02:00:03.516997+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-27-2026-10pm-et` |
| 18 | bitcoin | 2026-03-28 | 00:00 ET | `2026-03-28T04:00:02.815126+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-28-2026-12am-et` |
| 19 | bitcoin | 2026-03-28 | 01:00 ET | `2026-03-28T05:00:03.753679+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-28-2026-1am-et` |
| 20 | ethereum | 2026-03-28 | 01:00 ET | `2026-03-28T05:00:03.753679+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-28-2026-1am-et` |
| 21 | bitcoin | 2026-03-28 | 02:00 ET | `2026-03-28T06:00:03.167968+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-28-2026-2am-et` |
| 22 | ethereum | 2026-03-28 | 02:00 ET | `2026-03-28T06:00:03.167968+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-28-2026-2am-et` |
| 23 | bitcoin | 2026-03-28 | 04:00 ET | `2026-03-28T08:00:03.010184+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-28-2026-4am-et` |
| 24 | ethereum | 2026-03-28 | 05:00 ET | `2026-03-28T09:00:02.558268+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-28-2026-5am-et` |
| 25 | bitcoin | 2026-03-28 | 07:00 ET | `2026-03-28T11:00:03.384995+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-28-2026-7am-et` |
| 26 | ethereum | 2026-03-28 | 07:00 ET | `2026-03-28T11:00:03.384995+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-28-2026-7am-et` |
| 27 | bitcoin | 2026-03-28 | 08:00 ET | `2026-03-28T12:00:03.380076+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-28-2026-8am-et` |
| 28 | ethereum | 2026-03-28 | 08:00 ET | `2026-03-28T12:00:03.380076+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-28-2026-8am-et` |
| 29 | bitcoin | 2026-03-28 | 09:00 ET | `2026-03-28T13:00:03.105769+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-28-2026-9am-et` |
| 30 | ethereum | 2026-03-28 | 09:00 ET | `2026-03-28T13:00:03.105769+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-28-2026-9am-et` |
| 31 | ethereum | 2026-03-28 | 11:00 ET | `2026-03-28T15:00:02.803735+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-28-2026-11am-et` |
| 32 | ethereum | 2026-03-28 | 12:00 ET | `2026-03-28T16:00:03.341399+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-28-2026-12pm-et` |
| 33 | bitcoin | 2026-03-28 | 13:00 ET | `2026-03-28T17:00:03.163080+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-28-2026-1pm-et` |
| 34 | bitcoin | 2026-03-28 | 14:00 ET | `2026-03-28T18:00:03.551580+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-28-2026-2pm-et` |
| 35 | bitcoin | 2026-03-28 | 16:00 ET | `2026-03-28T20:00:03.454874+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-28-2026-4pm-et` |
| 36 | ethereum | 2026-03-28 | 16:00 ET | `2026-03-28T20:00:03.454874+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-28-2026-4pm-et` |
| 37 | bitcoin | 2026-03-28 | 19:00 ET | `2026-03-28T23:00:02.785986+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-28-2026-7pm-et` |
| 38 | ethereum | 2026-03-28 | 19:00 ET | `2026-03-28T23:00:02.785986+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-28-2026-7pm-et` |
| 39 | bitcoin | 2026-03-28 | 20:00 ET | `2026-03-29T00:00:03.736454+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-28-2026-8pm-et` |
| 40 | bitcoin | 2026-03-28 | 21:00 ET | `2026-03-29T01:00:03.646722+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-28-2026-9pm-et` |
| 41 | bitcoin | 2026-03-28 | 23:00 ET | `2026-03-29T03:00:02.883115+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-28-2026-11pm-et` |
| 42 | ethereum | 2026-03-29 | 00:00 ET | `2026-03-29T04:00:02.826918+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-29-2026-12am-et` |
| 43 | bitcoin | 2026-03-29 | 01:00 ET | `2026-03-29T05:00:03.147849+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-29-2026-1am-et` |
| 44 | ethereum | 2026-03-29 | 01:00 ET | `2026-03-29T05:00:03.147849+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-29-2026-1am-et` |
| 45 | bitcoin | 2026-03-29 | 02:00 ET | `2026-03-29T06:00:02.966169+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-29-2026-2am-et` |
| 46 | ethereum | 2026-03-29 | 02:00 ET | `2026-03-29T06:00:02.966169+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-29-2026-2am-et` |
| 47 | bitcoin | 2026-03-29 | 03:00 ET | `2026-03-29T07:00:03.290572+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-29-2026-3am-et` |
| 48 | ethereum | 2026-03-29 | 03:00 ET | `2026-03-29T07:00:03.290572+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-29-2026-3am-et` |
| 49 | bitcoin | 2026-03-29 | 04:00 ET | `2026-03-29T08:00:03.942999+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-29-2026-4am-et` |
| 50 | ethereum | 2026-03-29 | 04:00 ET | `2026-03-29T08:00:03.942999+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-29-2026-4am-et` |
| 51 | bitcoin | 2026-03-29 | 06:00 ET | `2026-03-29T10:00:03.507365+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-29-2026-6am-et` |
| 52 | ethereum | 2026-03-29 | 09:00 ET | `2026-03-29T13:09:22.595416+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-29-2026-9am-et` |
| 53 | ethereum | 2026-03-29 | 22:00 ET | `2026-03-30T02:00:03.072656+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-29-2026-10pm-et` |
| 54 | ethereum | 2026-03-29 | 23:00 ET | `2026-03-30T03:00:02.515197+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-29-2026-11pm-et` |
| 55 | bitcoin | 2026-03-30 | 00:00 ET | `2026-03-30T04:00:03.024291+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-30-2026-12am-et` |
| 56 | bitcoin | 2026-03-30 | 02:00 ET | `2026-03-30T06:00:04.680844+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-30-2026-2am-et` |
| 57 | ethereum | 2026-03-30 | 02:00 ET | `2026-03-30T06:00:04.680844+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-30-2026-2am-et` |
| 58 | ethereum | 2026-03-30 | 04:00 ET | `2026-03-30T08:00:02.909686+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-30-2026-4am-et` |
| 59 | bitcoin | 2026-03-30 | 07:00 ET | `2026-03-30T11:00:02.854544+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-30-2026-7am-et` |
| 60 | bitcoin | 2026-03-30 | 08:00 ET | `2026-03-30T12:00:03.671507+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-30-2026-8am-et` |
| 61 | ethereum | 2026-03-30 | 08:00 ET | `2026-03-30T12:00:03.671507+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-30-2026-8am-et` |
| 62 | bitcoin | 2026-03-30 | 09:00 ET | `2026-03-30T13:00:03.434380+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-30-2026-9am-et` |
| 63 | bitcoin | 2026-03-30 | 10:00 ET | `2026-03-30T14:00:03.225450+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-30-2026-10am-et` |
| 64 | ethereum | 2026-03-30 | 10:00 ET | `2026-03-30T14:00:03.225450+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-30-2026-10am-et` |
| 65 | bitcoin | 2026-03-30 | 11:00 ET | `2026-03-30T15:00:02.846236+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-30-2026-11am-et` |
| 66 | ethereum | 2026-03-30 | 11:00 ET | `2026-03-30T15:00:02.846236+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-30-2026-11am-et` |
| 67 | ethereum | 2026-03-30 | 13:00 ET | `2026-03-30T17:00:02.915163+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-30-2026-1pm-et` |
| 68 | bitcoin | 2026-03-30 | 14:00 ET | `2026-03-30T18:00:02.885326+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-30-2026-2pm-et` |
| 69 | bitcoin | 2026-03-30 | 16:00 ET | `2026-03-30T20:00:03.034802+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-30-2026-4pm-et` |
| 70 | ethereum | 2026-03-30 | 16:00 ET | `2026-03-30T20:00:03.034802+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-30-2026-4pm-et` |
| 71 | bitcoin | 2026-03-30 | 17:00 ET | `2026-03-30T21:00:03.441795+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-30-2026-5pm-et` |
| 72 | ethereum | 2026-03-30 | 17:00 ET | `2026-03-30T21:00:03.441795+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-30-2026-5pm-et` |
| 73 | ethereum | 2026-03-30 | 18:00 ET | `2026-03-30T22:00:03.690686+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-30-2026-6pm-et` |
| 74 | ethereum | 2026-03-30 | 22:00 ET | `2026-03-31T02:00:03.117381+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-30-2026-10pm-et` |
| 75 | bitcoin | 2026-03-31 | 00:00 ET | `2026-03-31T04:00:03.074235+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-31-2026-12am-et` |
| 76 | bitcoin | 2026-03-31 | 01:00 ET | `2026-03-31T05:00:03.435417+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-31-2026-1am-et` |
| 77 | bitcoin | 2026-03-31 | 02:00 ET | `2026-03-31T06:00:03.355604+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-31-2026-2am-et` |
| 78 | ethereum | 2026-03-31 | 02:00 ET | `2026-03-31T06:00:03.355604+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-31-2026-2am-et` |
| 79 | bitcoin | 2026-03-31 | 03:00 ET | `2026-03-31T07:00:03.670459+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-31-2026-3am-et` |
| 80 | ethereum | 2026-03-31 | 03:00 ET | `2026-03-31T07:00:03.670459+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-31-2026-3am-et` |
| 81 | bitcoin | 2026-03-31 | 05:00 ET | `2026-03-31T09:00:02.939929+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-31-2026-5am-et` |
| 82 | bitcoin | 2026-03-31 | 06:00 ET | `2026-03-31T10:00:02.812071+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-31-2026-6am-et` |
| 83 | bitcoin | 2026-03-31 | 10:00 ET | `2026-03-31T14:00:03.215963+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-31-2026-10am-et` |
| 84 | ethereum | 2026-03-31 | 12:00 ET | `2026-03-31T16:00:02.959551+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-31-2026-12pm-et` |
| 85 | ethereum | 2026-03-31 | 13:00 ET | `2026-03-31T17:00:02.739099+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-31-2026-1pm-et` |
| 86 | bitcoin | 2026-03-31 | 14:00 ET | `2026-03-31T18:00:03.458080+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-31-2026-2pm-et` |
| 87 | bitcoin | 2026-03-31 | 15:00 ET | `2026-03-31T19:00:03.228694+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-31-2026-3pm-et` |
| 88 | ethereum | 2026-03-31 | 15:00 ET | `2026-03-31T19:00:03.228694+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-31-2026-3pm-et` |
| 89 | bitcoin | 2026-03-31 | 16:00 ET | `2026-03-31T20:00:03.107118+00:00` | Başarılı | Evet | `bitcoin-up-or-down-march-31-2026-4pm-et` |
| 90 | ethereum | 2026-03-31 | 16:00 ET | `2026-03-31T20:00:03.107118+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-31-2026-4pm-et` |
| 91 | ethereum | 2026-03-31 | 17:00 ET | `2026-03-31T21:00:03.465194+00:00` | Başarısız | Evet | `ethereum-up-or-down-march-31-2026-5pm-et` |
| 92 | bitcoin | 2026-03-31 | 18:00 ET | `2026-03-31T22:00:02.651353+00:00` | Başarısız | Evet | `bitcoin-up-or-down-march-31-2026-6pm-et` |
| 93 | ethereum | 2026-03-31 | 20:00 ET | `2026-04-01T00:00:03.444444+00:00` | Başarılı | Evet | `ethereum-up-or-down-march-31-2026-8pm-et` |
| 94 | bitcoin | 2026-04-01 | 01:00 ET | `2026-04-01T05:13:17.872898+00:00` | Başarılı | Evet | `bitcoin-up-or-down-april-1-2026-1am-et` |
| 95 | ethereum | 2026-04-01 | 01:00 ET | `2026-04-01T05:13:17.872898+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-1-2026-1am-et` |
| 96 | bitcoin | 2026-04-01 | 03:00 ET | `2026-04-01T07:00:04.992359+00:00` | Başarısız | Evet | `bitcoin-up-or-down-april-1-2026-3am-et` |
| 97 | ethereum | 2026-04-01 | 03:00 ET | `2026-04-01T07:00:04.992359+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-1-2026-3am-et` |
| 98 | ethereum | 2026-04-01 | 04:00 ET | `2026-04-01T08:00:03.930833+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-1-2026-4am-et` |
| 99 | bitcoin | 2026-04-01 | 06:00 ET | `2026-04-01T10:00:03.142229+00:00` | Başarısız | Evet | `bitcoin-up-or-down-april-1-2026-6am-et` |
| 100 | bitcoin | 2026-04-01 | 07:00 ET | `2026-04-01T11:00:02.815505+00:00` | Başarılı | Evet | `bitcoin-up-or-down-april-1-2026-7am-et` |
| 101 | ethereum | 2026-04-01 | 07:00 ET | `2026-04-01T11:00:02.815505+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-1-2026-7am-et` |
| 102 | bitcoin | 2026-04-01 | 08:00 ET | `2026-04-01T12:00:02.854659+00:00` | Başarısız | Evet | `bitcoin-up-or-down-april-1-2026-8am-et` |
| 103 | bitcoin | 2026-04-01 | 09:00 ET | `2026-04-01T13:00:02.861316+00:00` | Başarısız | Evet | `bitcoin-up-or-down-april-1-2026-9am-et` |
| 104 | ethereum | 2026-04-01 | 09:00 ET | `2026-04-01T13:00:02.861316+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-1-2026-9am-et` |
| 105 | solana | 2026-04-01 | 09:00 ET | `2026-04-01T13:00:02.861316+00:00` | Başarılı | Evet | `solana-up-or-down-april-1-2026-9am-et` |
| 106 | ethereum | 2026-04-01 | 10:00 ET | `2026-04-01T14:00:03.822534+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-1-2026-10am-et` |
| 107 | solana | 2026-04-01 | 11:00 ET | `2026-04-01T15:00:03.160706+00:00` | Başarılı | Evet | `solana-up-or-down-april-1-2026-11am-et` |
| 108 | bitcoin | 2026-04-01 | 12:00 ET | `2026-04-01T16:00:02.938355+00:00` | Başarısız | Evet | `bitcoin-up-or-down-april-1-2026-12pm-et` |
| 109 | solana | 2026-04-01 | 12:00 ET | `2026-04-01T16:00:02.938355+00:00` | Başarılı | Evet | `solana-up-or-down-april-1-2026-12pm-et` |
| 110 | solana | 2026-04-01 | 13:00 ET | `2026-04-01T17:00:03.613935+00:00` | Başarısız | Evet | `solana-up-or-down-april-1-2026-1pm-et` |
| 111 | bitcoin | 2026-04-01 | 14:00 ET | `2026-04-01T18:00:03.277007+00:00` | Başarısız | Evet | `bitcoin-up-or-down-april-1-2026-2pm-et` |
| 112 | ethereum | 2026-04-01 | 15:00 ET | `2026-04-01T19:00:03.524537+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-1-2026-3pm-et` |
| 113 | bitcoin | 2026-04-01 | 16:00 ET | `2026-04-01T20:00:02.887129+00:00` | Başarısız | Evet | `bitcoin-up-or-down-april-1-2026-4pm-et` |
| 114 | solana | 2026-04-01 | 16:00 ET | `2026-04-01T20:00:02.887129+00:00` | Başarısız | Evet | `solana-up-or-down-april-1-2026-4pm-et` |
| 115 | bitcoin | 2026-04-01 | 17:00 ET | `2026-04-01T21:00:03.421624+00:00` | Başarısız | Evet | `bitcoin-up-or-down-april-1-2026-5pm-et` |
| 116 | ethereum | 2026-04-01 | 17:00 ET | `2026-04-01T21:00:03.421624+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-1-2026-5pm-et` |
| 117 | solana | 2026-04-01 | 17:00 ET | `2026-04-01T21:00:03.421624+00:00` | Başarılı | Evet | `solana-up-or-down-april-1-2026-5pm-et` |
| 118 | bitcoin | 2026-04-01 | 18:00 ET | `2026-04-01T22:00:02.459040+00:00` | Başarılı | Evet | `bitcoin-up-or-down-april-1-2026-6pm-et` |
| 119 | ethereum | 2026-04-01 | 18:00 ET | `2026-04-01T22:00:02.459040+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-1-2026-6pm-et` |
| 120 | bitcoin | 2026-04-01 | 20:00 ET | `2026-04-02T00:00:05.133497+00:00` | Başarısız | Evet | `bitcoin-up-or-down-april-1-2026-8pm-et` |
| 121 | ethereum | 2026-04-01 | 20:00 ET | `2026-04-02T00:00:05.133497+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-1-2026-8pm-et` |
| 122 | solana | 2026-04-01 | 20:00 ET | `2026-04-02T00:00:05.133497+00:00` | Başarısız | Evet | `solana-up-or-down-april-1-2026-8pm-et` |
| 123 | bitcoin | 2026-04-01 | 21:00 ET | `2026-04-02T01:00:03.379427+00:00` | Başarılı | Evet | `bitcoin-up-or-down-april-1-2026-9pm-et` |
| 124 | ethereum | 2026-04-01 | 21:00 ET | `2026-04-02T01:00:03.379427+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-1-2026-9pm-et` |
| 125 | solana | 2026-04-01 | 21:00 ET | `2026-04-02T01:00:03.379427+00:00` | Başarılı | Evet | `solana-up-or-down-april-1-2026-9pm-et` |
| 126 | bitcoin | 2026-04-01 | 22:00 ET | `2026-04-02T02:00:03.479587+00:00` | Başarılı | Evet | `bitcoin-up-or-down-april-1-2026-10pm-et` |
| 127 | solana | 2026-04-01 | 22:00 ET | `2026-04-02T02:00:03.479587+00:00` | Başarılı | Evet | `solana-up-or-down-april-1-2026-10pm-et` |
| 128 | bitcoin | 2026-04-01 | 23:00 ET | `2026-04-02T03:00:03.019877+00:00` | Başarılı | Evet | `bitcoin-up-or-down-april-1-2026-11pm-et` |
| 129 | solana | 2026-04-01 | 23:00 ET | `2026-04-02T03:00:03.019877+00:00` | Başarısız | Evet | `solana-up-or-down-april-1-2026-11pm-et` |
| 130 | bitcoin | 2026-04-01 | 00:00 ET | `2026-04-02T04:00:02.739944+00:00` | Başarılı | Evet | `bitcoin-up-or-down-april-2-2026-12am-et` |
| 131 | ethereum | 2026-04-01 | 00:00 ET | `2026-04-02T04:00:02.739944+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-2-2026-12am-et` |
| 132 | solana | 2026-04-01 | 00:00 ET | `2026-04-02T04:00:02.739944+00:00` | Başarılı | Evet | `solana-up-or-down-april-2-2026-12am-et` |
| 133 | ethereum | 2026-04-01 | 02:00 ET | `2026-04-02T06:00:03.525724+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-2-2026-2am-et` |
| 134 | solana | 2026-04-01 | 02:00 ET | `2026-04-02T06:00:03.525724+00:00` | Başarılı | Evet | `solana-up-or-down-april-2-2026-2am-et` |
| 135 | ethereum | 2026-04-01 | 03:00 ET | `2026-04-02T07:00:03.373992+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-2-2026-3am-et` |
| 136 | solana | 2026-04-01 | 03:00 ET | `2026-04-02T07:00:03.373992+00:00` | Başarısız | Evet | `solana-up-or-down-april-2-2026-3am-et` |
| 137 | ethereum | 2026-04-01 | 04:00 ET | `2026-04-02T08:00:02.907702+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-2-2026-4am-et` |
| 138 | solana | 2026-04-01 | 05:00 ET | `2026-04-02T09:00:02.800776+00:00` | Başarısız | Evet | `solana-up-or-down-april-2-2026-5am-et` |
| 139 | ethereum | 2026-04-01 | 08:00 ET | `2026-04-02T12:00:03.090872+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-2-2026-8am-et` |
| 140 | solana | 2026-04-01 | 08:00 ET | `2026-04-02T12:00:03.090872+00:00` | Başarılı | Evet | `solana-up-or-down-april-2-2026-8am-et` |
| 141 | ethereum | 2026-04-02 | 10:00 ET | `2026-04-02T14:00:03.591814+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-2-2026-10am-et` |
| 142 | solana | 2026-04-02 | 10:00 ET | `2026-04-02T14:00:03.591814+00:00` | Başarısız | Evet | `solana-up-or-down-april-2-2026-10am-et` |
| 143 | solana | 2026-04-02 | 11:00 ET | `2026-04-02T15:00:03.694244+00:00` | Başarılı | Evet | `solana-up-or-down-april-2-2026-11am-et` |
| 144 | ethereum | 2026-04-02 | 12:00 ET | `2026-04-02T16:00:03.284356+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-2-2026-12pm-et` |
| 145 | solana | 2026-04-02 | 12:00 ET | `2026-04-02T16:00:03.284356+00:00` | Başarılı | Evet | `solana-up-or-down-april-2-2026-12pm-et` |
| 146 | solana | 2026-04-02 | 14:00 ET | `2026-04-02T18:00:03.034484+00:00` | Başarısız | Evet | `solana-up-or-down-april-2-2026-2pm-et` |
| 147 | ethereum | 2026-04-02 | 15:00 ET | `2026-04-02T19:00:03.231512+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-2-2026-3pm-et` |
| 148 | solana | 2026-04-02 | 15:00 ET | `2026-04-02T19:00:03.231512+00:00` | Başarısız | Evet | `solana-up-or-down-april-2-2026-3pm-et` |
| 149 | solana | 2026-04-02 | 17:00 ET | `2026-04-02T21:00:02.828325+00:00` | Başarılı | Evet | `solana-up-or-down-april-2-2026-5pm-et` |
| 150 | ethereum | 2026-04-02 | 18:00 ET | `2026-04-02T22:00:03.303488+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-2-2026-6pm-et` |
| 151 | solana | 2026-04-02 | 18:00 ET | `2026-04-02T22:00:03.303488+00:00` | Başarısız | Evet | `solana-up-or-down-april-2-2026-6pm-et` |
| 152 | solana | 2026-04-02 | 19:00 ET | `2026-04-02T23:00:03.526806+00:00` | Başarılı | Evet | `solana-up-or-down-april-2-2026-7pm-et` |
| 153 | ethereum | 2026-04-02 | 20:00 ET | `2026-04-03T00:00:04.706453+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-2-2026-8pm-et` |
| 154 | ethereum | 2026-04-02 | 22:00 ET | `2026-04-03T02:00:03.062901+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-2-2026-10pm-et` |
| 155 | ethereum | 2026-04-02 | 23:00 ET | `2026-04-03T03:00:03.088788+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-2-2026-11pm-et` |
| 156 | ethereum | 2026-04-03 | 12:00 ET | `2026-04-03T16:00:03.171440+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-3-2026-12pm-et` |
| 157 | ethereum | 2026-04-03 | 16:00 ET | `2026-04-03T20:00:03.387884+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-3-2026-4pm-et` |
| 158 | solana | 2026-04-03 | 16:00 ET | `2026-04-03T20:00:03.387884+00:00` | Başarısız | Evet | `solana-up-or-down-april-3-2026-4pm-et` |
| 159 | ethereum | 2026-04-03 | 17:00 ET | `2026-04-03T21:00:03.461653+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-3-2026-5pm-et` |
| 160 | ethereum | 2026-04-03 | 18:00 ET | `2026-04-03T22:00:03.485777+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-3-2026-6pm-et` |
| 161 | solana | 2026-04-03 | 20:00 ET | `2026-04-04T00:00:04.478029+00:00` | Başarısız | Evet | `solana-up-or-down-april-3-2026-8pm-et` |
| 162 | solana | 2026-04-03 | 21:00 ET | `2026-04-04T01:00:02.745247+00:00` | Başarısız | Evet | `solana-up-or-down-april-3-2026-9pm-et` |
| 163 | ethereum | 2026-04-03 | 22:00 ET | `2026-04-04T02:00:03.086880+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-3-2026-10pm-et` |
| 164 | ethereum | 2026-04-03 | 23:00 ET | `2026-04-04T03:00:02.968758+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-3-2026-11pm-et` |
| 165 | solana | 2026-04-03 | 23:00 ET | `2026-04-04T03:00:02.968758+00:00` | Başarılı | Evet | `solana-up-or-down-april-3-2026-11pm-et` |
| 166 | ethereum | 2026-04-03 | 01:00 ET | `2026-04-04T05:00:03.395791+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-4-2026-1am-et` |
| 167 | ethereum | 2026-04-03 | 03:00 ET | `2026-04-04T07:00:03.380372+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-4-2026-3am-et` |
| 168 | ethereum | 2026-04-03 | 04:00 ET | `2026-04-04T08:00:03.439347+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-4-2026-4am-et` |
| 169 | ethereum | 2026-04-03 | 06:00 ET | `2026-04-04T10:00:03.250735+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-4-2026-6am-et` |
| 170 | solana | 2026-04-03 | 06:00 ET | `2026-04-04T10:00:03.250735+00:00` | Başarısız | Evet | `solana-up-or-down-april-4-2026-6am-et` |
| 171 | ethereum | 2026-04-03 | 07:00 ET | `2026-04-04T11:00:03.589101+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-4-2026-7am-et` |
| 172 | solana | 2026-04-04 | 09:00 ET | `2026-04-04T13:00:02.651718+00:00` | Başarılı | Evet | `solana-up-or-down-april-4-2026-9am-et` |
| 173 | solana | 2026-04-04 | 11:00 ET | `2026-04-04T15:00:03.470531+00:00` | Başarılı | Evet | `solana-up-or-down-april-4-2026-11am-et` |
| 174 | solana | 2026-04-04 | 12:00 ET | `2026-04-04T16:00:03.311987+00:00` | Başarısız | Evet | `solana-up-or-down-april-4-2026-12pm-et` |
| 175 | ethereum | 2026-04-04 | 14:00 ET | `2026-04-04T18:00:02.594814+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-4-2026-2pm-et` |
| 176 | ethereum | 2026-04-04 | 17:00 ET | `2026-04-04T21:00:03.728980+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-4-2026-5pm-et` |
| 177 | ethereum | 2026-04-04 | 18:00 ET | `2026-04-04T22:00:02.869575+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-4-2026-6pm-et` |
| 178 | ethereum | 2026-04-04 | 19:00 ET | `2026-04-04T23:00:02.853963+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-4-2026-7pm-et` |
| 179 | solana | 2026-04-04 | 19:00 ET | `2026-04-04T23:00:02.853963+00:00` | Başarısız | Evet | `solana-up-or-down-april-4-2026-7pm-et` |
| 180 | ethereum | 2026-04-04 | 20:00 ET | `2026-04-05T00:00:04.379656+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-4-2026-8pm-et` |
| 181 | solana | 2026-04-04 | 20:00 ET | `2026-04-05T00:00:04.379656+00:00` | Başarısız | Evet | `solana-up-or-down-april-4-2026-8pm-et` |
| 182 | solana | 2026-04-04 | 01:00 ET | `2026-04-05T05:00:03.067278+00:00` | Başarılı | Evet | `solana-up-or-down-april-5-2026-1am-et` |
| 183 | ethereum | 2026-04-04 | 02:00 ET | `2026-04-05T06:00:02.741857+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-5-2026-2am-et` |
| 184 | solana | 2026-04-04 | 03:00 ET | `2026-04-05T07:00:04.257662+00:00` | Başarısız | Evet | `solana-up-or-down-april-5-2026-3am-et` |
| 185 | ethereum | 2026-04-04 | 04:00 ET | `2026-04-05T08:00:04.330206+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-5-2026-4am-et` |
| 186 | solana | 2026-04-04 | 04:00 ET | `2026-04-05T08:00:04.330206+00:00` | Başarısız | Evet | `solana-up-or-down-april-5-2026-4am-et` |
| 187 | ethereum | 2026-04-04 | 06:00 ET | `2026-04-05T10:00:03.835984+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-5-2026-6am-et` |
| 188 | ethereum | 2026-04-05 | 09:00 ET | `2026-04-05T13:00:04.691392+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-5-2026-9am-et` |
| 189 | solana | 2026-04-05 | 09:00 ET | `2026-04-05T13:00:04.691392+00:00` | Başarısız | Evet | `solana-up-or-down-april-5-2026-9am-et` |
| 190 | ethereum | 2026-04-05 | 10:00 ET | `2026-04-05T14:00:05.016557+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-5-2026-10am-et` |
| 191 | solana | 2026-04-05 | 10:00 ET | `2026-04-05T14:00:05.016557+00:00` | Başarısız | Evet | `solana-up-or-down-april-5-2026-10am-et` |
| 192 | ethereum | 2026-04-05 | 11:00 ET | `2026-04-05T15:00:03.324801+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-5-2026-11am-et` |
| 193 | ethereum | 2026-04-05 | 12:00 ET | `2026-04-05T16:00:03.706868+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-5-2026-12pm-et` |
| 194 | solana | 2026-04-05 | 12:00 ET | `2026-04-05T16:00:03.706868+00:00` | Başarılı | Evet | `solana-up-or-down-april-5-2026-12pm-et` |
| 195 | ethereum | 2026-04-05 | 13:00 ET | `2026-04-05T17:00:03.479356+00:00` | Başarılı | Hayır | `ethereum-up-or-down-april-5-2026-1pm-et` |
| 196 | solana | 2026-04-05 | 13:00 ET | `2026-04-05T17:00:03.479356+00:00` | Başarısız | Hayır | `solana-up-or-down-april-5-2026-1pm-et` |
| 197 | ethereum | 2026-04-05 | 14:00 ET | `2026-04-05T18:00:03.299304+00:00` | Başarılı | Hayır | `ethereum-up-or-down-april-5-2026-2pm-et` |
| 198 | solana | 2026-04-05 | 14:00 ET | `2026-04-05T18:00:03.299304+00:00` | Başarısız | Hayır | `solana-up-or-down-april-5-2026-2pm-et` |
| 199 | ethereum | 2026-04-05 | 16:00 ET | `2026-04-05T20:00:03.463858+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-5-2026-4pm-et` |
| 200 | ethereum | 2026-04-05 | 18:00 ET | `2026-04-05T22:00:03.693553+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-5-2026-6pm-et` |
| 201 | ethereum | 2026-04-05 | 20:00 ET | `2026-04-06T00:00:04.123084+00:00` | Başarılı | Hayır | `ethereum-up-or-down-april-5-2026-8pm-et` |
| 202 | solana | 2026-04-05 | 20:00 ET | `2026-04-06T00:00:04.123084+00:00` | Başarılı | Hayır | `solana-up-or-down-april-5-2026-8pm-et` |
| 203 | ethereum | 2026-04-05 | 21:00 ET | `2026-04-06T01:00:02.583743+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-5-2026-9pm-et` |
| 204 | ethereum | 2026-04-05 | 23:00 ET | `2026-04-06T03:00:03.370640+00:00` | Başarısız | Evet | `ethereum-up-or-down-april-5-2026-11pm-et` |
| 205 | ethereum | 2026-04-05 | 00:00 ET | `2026-04-06T04:00:03.795002+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-6-2026-12am-et` |
| 206 | solana | 2026-04-05 | 00:00 ET | `2026-04-06T04:00:03.795002+00:00` | Başarısız | Evet | `solana-up-or-down-april-6-2026-12am-et` |
| 207 | solana | 2026-04-05 | 02:00 ET | `2026-04-06T06:00:04.114574+00:00` | Başarısız | Evet | `solana-up-or-down-april-6-2026-2am-et` |
| 208 | ethereum | 2026-04-05 | 03:00 ET | `2026-04-06T07:00:03.669248+00:00` | Başarılı | Hayır | `ethereum-up-or-down-april-6-2026-3am-et` |
| 209 | solana | 2026-04-05 | 03:00 ET | `2026-04-06T07:00:03.669248+00:00` | Başarılı | Hayır | `solana-up-or-down-april-6-2026-3am-et` |
| 210 | solana | 2026-04-05 | 04:00 ET | `2026-04-06T08:00:03.347936+00:00` | Başarılı | Evet | `solana-up-or-down-april-6-2026-4am-et` |
| 211 | ethereum | 2026-04-05 | 05:00 ET | `2026-04-06T09:00:03.777245+00:00` | Başarılı | Evet | `ethereum-up-or-down-april-6-2026-5am-et` |
| 212 | solana | 2026-04-05 | 05:00 ET | `2026-04-06T09:00:03.777245+00:00` | Başarılı | Evet | `solana-up-or-down-april-6-2026-5am-et` |
