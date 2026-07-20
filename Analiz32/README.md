# Analiz32 — FeatureEngine v2 + Poly sanal trader

Indikatör/feature kütüphanesi (`core/`, `features/`) **dokunulmaz**.
Trader bağlantısı ince adaptörlerle yapılır:

| Dosya | Rol |
|---|---|
| `core/`, `features/` | Algo kütüphanesi (Poly Faz1 v2) |
| `predictor.py` | `composite_signal` → UP/DOWN (gate ±15) |
| `data_fetcher.py` | Binance 1h kline |
| `temmuzPoly/poly_trader_analiz32.py` | Saatlik sanal trader ($300, $12/16/20) |

## Trader

```bash
python3 temmuzPoly/poly_trader_analiz32.py open
python3 temmuzPoly/poly_trader_analiz32.py close
python3 temmuzPoly/poly_trader_analiz32.py weekly
```

Cron: `0 * * * *` close · `5 * * * *` open · `0 21 * * 6` weekly

## Kütüphane quick start

```python
from core.base import OHLCV
from features.engine import FeatureEngine
import numpy as np

engine = FeatureEngine()
# ohlcv = OHLCV(...)
features = engine.compute(ohlcv)
```

```bash
pip install -r Analiz32/requirements.txt
pytest Analiz32/tests/test_indicators.py -v
```
