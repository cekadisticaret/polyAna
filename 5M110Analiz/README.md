# 5M110Analiz — FeatureEngine v2

Indikatör/feature kütüphanesi (`core/`, `features/`) **dokunulmaz**.
15M trader bağlantısı ince adaptörlerle yapılır:

| Dosya | Rol |
|---|---|
| `core/`, `features/` | Algo kütüphanesi (Poly Faz1 v2) |
| `predictor.py` | `composite_signal` → UP/DOWN (gate ±15) |
| `data_fetcher.py` | Binance 1h kline |
| `temmuzPoly/analiz32_15m_adapter.py` | 110 SOL 15m sinyal |
| `temmuzPoly/analiz32_15m_adapter_111.py` | 111 SOL filtreli sinyal |

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
pip install -r 5M110Analiz/requirements.txt
pytest 5M110Analiz/tests/test_indicators.py -v
```
