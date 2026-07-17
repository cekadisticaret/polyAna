# Yama v1.1 Notları

## Değişiklikler

### 1. Simetrik Gate'ler
- Eski: 42/38 (asimetrik, DOWN kolay)
- Yeni: 50/50 (simetrik, daha seçici)

### 2. Trend Filtresi (KRİTİK)
- `_trend_filter()`: Güçlü trend'de MR'ı engelle
- ADX > 30 + DI spread > 10 = trend var
- Bullish HTF'de DOWN yasak
- Bearish HTF'de UP yasak

### 3. Dinamik Gate'ler
- `get_dynamic_gates()`: HTF bias + ADX + DI spread
- Bullish HTF: UP kolay, DOWN zor
- Bearish HTF: DOWN kolay, UP zor

### 4. CVD Momentum
- Eski: Mutlak değer
- Yeni: Değişim hızı (cvd_delta)
- Yavaşlayan momentum = erken reversal

### 5. Güven Hesaplama
- Eski: 50% + skor/200
- Yeni: 55% + gate aşımı * 0.3
- Daha agresif prob ayarı

## Beklenen Etki
- DOWN bias ortadan kalkar
- Trend karşıtı kayıplar azalır
- BEKLE oranı artar (kalite > miktar)

## Uygulama
```bash
cp config.py config.py.bak
cp scorer.py scorer.py.bak
cp predictor.py predictor.py.bak

# Yeni dosyaları kopyala
# (bu zip'teki dosyaları proje dizinine çıkar)
```
