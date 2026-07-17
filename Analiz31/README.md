# Analiz31 — Multi-Timeframe Tahmin Motoru

## Özellikler
- **Multi-Timeframe**: 15m, 1h, 4h, 1d veri entegrasyonu
- **Walk-Forward Backtest**: Overfitting önleme
- **HTF Bias**: Üst zaman dilimi trend onayı
- **Kill Zone + Dinamik Gate**: ET saati + HTF/ADX/DI spread (v1.1)
- **Trend Filtresi**: Güçlü trendde MR karşıt sinyal engeli (v1.1)
- **Crash Kapısı**: EMA50 %8 sapma koruması

## Kurulum
```bash
pip install -r requirements.txt
```

## Kullanım
```bash
# Tek tahmin
python main.py --once --symbol BTCUSDT

# Sürekli çalışma (her 1h)
python main.py --loop

# Backtest
python main.py --backtest /opt/cripto/poly_history.jsonl
```

## Dosya Yapısı
```
Analiz31/
├── config.py          # Ayarlar
├── data_fetcher.py    # Binance API
├── technicals.py      # İndikatörler
├── features.py         # Feature engineering
├── scorer.py           # MR skorlama
├── predictor.py        # Tahmin motoru
├── tracker.py          # Kayıt ve takip
├── backtest.py         # Walk-forward test
├── main.py             # CLI
└── requirements.txt
```
