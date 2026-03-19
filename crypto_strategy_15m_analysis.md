# Kripto Strateji + MACD Pro — 15 Dakika Analizi

## SORUNLAR VE DÜZELTMELER

### Strateji v1 (Ana Kod) — 15m Sorunları

| Parametre        | Mevcut | 15m'de Sorun | Düzeltme |
|------------------|--------|-------------|----------|
| EMA Uzun         | 200    | 200x15dk = 50 SAAT geriye bakar, çok yavaş | → 100 |
| EMA Kısa         | 50     | 50x15dk = 12.5 saat, yavaş              | → 21  |
| Cooldown         | 8 bar  | 8x15dk = 2 SAAT bekleme, fırsat kaçar  | → 4 bar (1 saat) |
| distThreshold    | 6%     | Kripto 15m'de EMA100'den %6 uzak = zaten geç | → 3.5% |
| ADX eşiği        | 16     | Kripto gürültüsünde çok düşük, sahte sinyal | → 22 |
| maxSLpct         | 0.6%   | 20x kaldıraçta iyi ✅ | değişmesin |
| ATR SL: 2.0      | 2.0    | Kripto 15m volatilite için biraz dar    | → 2.5 |
| ATR TP: 3.0      | 3.0    | Risk/ödül 1:1.2 → düşük               | → 4.0 (1:1.6) |
| volMult          | 1.3    | Kripto için zayıf filtre                | → 1.5 |

### MACD Pro v5.3 — 15m Sorunları

| Parametre    | Mevcut | 15m'de Sorun | Düzeltme |
|--------------|--------|-------------|----------|
| MACD 12/26/9 | 12/26/9 | 15m'de ~6.5 saat lag, yavaş ama kabul edilebilir | → 8/21/5 (daha hızlı) |
| RSI Min      | 55     | Long-only için iyi ama short tarafı kaçırır | → 52 (biraz gevşet) |
| ADX Eşiği    | 18     | Kripto 15m için düşük                  | → 22 |
| volMult      | 1.5    | İyi ✅                                  | değişmesin |
