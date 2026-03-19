# Kripto Strateji v1 - Pine Script Analizi

## Kod (Ham)
İlk indikatör - Long + Short destekli kripto stratejisi.
Risk yönetimi, cooldown ve volatilite filtresi içeriyor.

## Bileşenler
- EMA 50 / EMA 200
- RSI 14
- ADX + DMI
- MACD (12,26,9)
- ATR tabanlı SL/TP
- Hacim Spike
- Cooldown (stop sonrası 8 bar bekleme)
- ATR% volatilite filtresi
- Max SL% koruması (%0.6 - 20x kaldıraç için)
