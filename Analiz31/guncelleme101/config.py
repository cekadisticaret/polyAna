"""
Polymarket Faz 1 - Yapılandırma (Yama v1.1)
"""

from zoneinfo import ZoneInfo

# Zaman
_ET_ZONE = ZoneInfo("America/New_York")

# Semboller
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# Zaman dilimleri
TIMEFRAMES = {
    "15m": {"limit": 96, "weight": 0.20},
    "1h": {"limit": 60, "weight": 0.50},
    "4h": {"limit": 42, "weight": 0.25},
    "1d": {"limit": 30, "weight": 0.05},
}

# ── YAMA: Simetrik ve daha yüksek gate'ler ───────────────
_MR_UP_GATE = 50           # 42 → 50
_MR_DOWN_GATE = 50         # 38 → 50 (simetrik!)
_MR_UP_GATE_KILLZONE = 65  # 58 → 65
_MR_DOWN_GATE_KILLZONE = 65 # 55 → 65 (simetrik!)

_KILL_ZONE_ET_HOURS = frozenset({9, 10, 11})

# Crash kapısı
_CRASH_EMA50_PCT = -8.0

# Güven seviyeleri
_CONF_HIGH = 0.70          # 0.65 → 0.70
_CONF_MED = 0.60           # 0.55 → 0.60

# Backtest
WALK_FORWARD_TRAIN_DAYS = 30
WALK_FORWARD_TEST_DAYS = 7

# Kayıt dosyaları
STATE_FILE = "/opt/cripto/poly_state.json"
HISTORY_FILE = "/opt/cripto/poly_history.jsonl"
PREDICTION_LOG = "/opt/cripto/prediction_log.jsonl"

# API
BINANCE_FAPI = "https://fapi.binance.com"

# ── YAMA: Risk yönetimi ───────────────────────────────────
_RISK_PER_TRADE = 0.02
_MIN_RR_RATIO = 1.5
