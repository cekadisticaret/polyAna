"""
Analiz31 - Yapılandırma
"""

from zoneinfo import ZoneInfo

# Zaman
_ET_ZONE = ZoneInfo("America/New_York")

# Semboller
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# Zaman dilimleri (Multi-Timeframe)
TIMEFRAMES = {
    "15m": {"limit": 96, "weight": 0.20},
    "1h": {"limit": 60, "weight": 0.50},
    "4h": {"limit": 42, "weight": 0.25},
    "1d": {"limit": 30, "weight": 0.05},
}

# Kapılar
_MR_UP_GATE = 42
_MR_DOWN_GATE = 38
_MR_UP_GATE_KILLZONE = 58
_MR_DOWN_GATE_KILLZONE = 52

_KILL_ZONE_ET_HOURS = frozenset({9, 10, 11})

# Crash kapısı
_CRASH_EMA50_PCT = -8.0

# Güven seviyeleri
_CONF_HIGH = 0.65
_CONF_MED = 0.55

# Backtest
WALK_FORWARD_TRAIN_DAYS = 30
WALK_FORWARD_TEST_DAYS = 7

# Kayıt dosyaları
STATE_FILE = "/opt/cripto/poly_state.json"
HISTORY_FILE = "/opt/cripto/poly_history.jsonl"
PREDICTION_LOG = "/opt/cripto/prediction_log.jsonl"

# API
BINANCE_FAPI = "https://fapi.binance.com"
