# Sistemde Kullanılan ATR Mantığı

## ATR Nedir?

**Average True Range (ATR)** — Fiyatın ortalama volatilitesini ölçen indikatör. Bir bar içinde fiyatın ne kadar hareket ettiğini gösterir.

## Hesaplama (paper_trader / binance_trader)

### 1. True Range (TR)

Her bar için TR, şu üç değerin **en büyüğü**:

```
TR = max(
  High - Low,                    # Bar içi en yüksek-en düşük
  |Close_önceki - High|,         # Önceki kapanış ile bugünkü tepe
  |Close_önceki - Low|           # Önceki kapanış ile bugünkü dip
)
```

### 2. ATR

- **Periyot:** 14 bar (standart)
- **Yöntem:** TR değerlerinin 14 periyotluk EMA’sı
- **Veri:** 15 dakikalık barlar (high, low, close)

```
ATR = EMA(TR, 14)
```

## Sistemde Kullanımı

### SL (Stop Loss)

```
LONG  → SL = Giriş - (ATR × 2.0)
SHORT → SL = Giriş + (ATR × 2.0)
```

- **STOP_ATR_MULT = 2.0** — SL, giriş fiyatından 2 ATR uzakta
- **MAX_SL_PCT = %0.8** — SL, girişten en fazla %0.8 uzakta olabilir (sert hareketleri sınırlar)

Gerçek SL = `max(ATR tabanlı SL, MAX_SL_PCT tabanlı SL)` (LONG için en düşük, SHORT için en yüksek)

### TP (Take Profit)

```
LONG  → TP = Giriş + (ATR × 4.5)
SHORT → TP = Giriş - (ATR × 4.5)
```

- **TAKE_ATR_MULT = 4.5** — TP, girişten 4.5 ATR uzakta
- **R:R ≈ 1:2.25** (SL 2 ATR, TP 4.5 ATR)

### Ek: is_hot_vol (Giriş Filtresi)

`calc_atr_pct_hot()` — ATR’nin fiyata oranı (ATR%) son 100 bar ortalamasının 1.8 katından büyükse **giriş yapılmaz** (aşırı volatilite).

## Özet Akış

1. 15m barlardan High, Low, Close alınır
2. Her bar için TR hesaplanır
3. TR’lerin 14 periyotluk EMA’sı = ATR
4. Giriş anında ATR ile SL ve TP hesaplanır
5. ATR, pozisyonda `entry_atr` olarak saklanır (kapanış bildiriminde gösterilir)
