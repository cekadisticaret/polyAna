"""
Analiz31 - Yapılandırma (Yama v1.1)
"""

from zoneinfo import ZoneInfo

# Zaman
_ET_ZONE = ZoneInfo("America/New_York")

# Semboller
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# Zaman dilimleri (Multi-TF)
TIMEFRAMES = {
    "15m": {"limit": 96, "weight": 0.20},
    "1h": {"limit": 60, "weight": 0.50},
    "4h": {"limit": 42, "weight": 0.25},
    "1d": {"limit": 30, "weight": 0.05},
}

# Simetrik gate'ler (v1.2 — yükseltilmiş taban)
_MR_UP_GATE = 75
_MR_DOWN_GATE = 75
_MR_UP_GATE_KILLZONE = 75
_MR_DOWN_GATE_KILLZONE = 75
_GATE_FLOOR = 75

_KILL_ZONE_ET_HOURS = frozenset({9, 10, 11})

# Trend rejimi — ADX yüksek + DI spread geniş → MR kapalı
_TREND_REGIME_ADX = 28
_TREND_REGIME_DI_SPREAD = 12

# SOL sembol ayrımı
_SOL_ALLOWED_HOURS_IST = frozenset({6, 7, 21, 22, 23, 0, 1, 2})
_SOL_DOWN_EXTRA_GATE = 15
_SOL_MOMENTUM_CVD_MIN = 0.02
_SOL_MOMENTUM_RSI_MIN = 52

# Crash kapısı
_CRASH_EMA50_PCT = -8.0

# Güven seviyeleri
_CONF_HIGH = 0.70
_CONF_MED = 0.60

# Backtest
WALK_FORWARD_TRAIN_DAYS = 30
WALK_FORWARD_TEST_DAYS = 7

# Kayıt dosyaları
STATE_FILE = "/opt/cripto/poly_state.json"
HISTORY_FILE = "/opt/cripto/poly_history.jsonl"
PREDICTION_LOG = "/opt/cripto/prediction_log.jsonl"

# API
BINANCE_FAPI = "https://fapi.binance.com"

# Risk yönetimi
_RISK_PER_TRADE = 0.02
_MIN_RR_RATIO = 1.5
