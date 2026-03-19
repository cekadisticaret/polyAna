# Binance Futures Kaldıraç Listesi
# Cem'in listesinden Binance Futures'da aktif olanlar
# Son güncelleme: 2026-03-14
# Toplam: 202 coin

FUTURES_SYMBOLS = [
    "AAVE", "ACE", "ACH", "ADA", "AERGO", "AKT", "ALGO", "ALICE", "ALT", "ANKR",
    "API3", "APT", "AR", "ARB", "ARKM", "ARPA", "ASTR", "ATA", "ATOM", "AVAX",
    "AXS", "BANANA", "BAND", "BAT", "BCH", "BEL", "BICO", "BLUR", "BNB", "BNT",
    "BOME", "BTC", "C98", "CAKE", "CELO", "CELR", "CGPT", "CHZ", "CKB", "COMP",
    "COS", "COTI", "CRV", "CTK", "CTSI", "CVC", "CVX", "CYBER", "DASH", "DEGO",
    "DENT", "DEXE", "DIA", "DOGE", "DOT", "DUSK", "DYDX", "DYM", "EGLD", "ENJ",
    "ENS", "ETC", "ETH", "FET", "FIDA", "FIL", "FLOW", "FLUX", "FORTH", "FUN",
    "GALA", "GLM", "GMX", "GRT", "HBAR", "HFT", "HIGH", "HIVE", "HOOK", "HOT",
    "ICP", "ICX", "ID", "ILV", "IMX", "INJ", "IOST", "IOTA", "JASMY", "JOE",
    "JST", "JTO", "JUP", "KAS", "KAVA", "KNC", "KSM", "LAYER", "LDO", "LINK",
    "LIT", "LPT", "LQTY", "LRC", "LSK", "LTC", "MAGIC", "MANTA", "MASK", "MAV",
    "MAVIA", "MBOX", "MEME", "METIS", "MINA", "MLN", "MOVR", "MTL", "NEAR", "NEO",
    "NFP", "NMR", "NTRN", "OGN", "ONE", "ONT", "OP", "ORDI", "OXT", "PENDLE",
    "PEOPLE", "PHA", "PIXEL", "POLYX", "PORTAL", "POWR", "PROM", "PYTH", "QNT", "QTUM",
    "RARE", "RDNT", "RIF", "RLC", "ROSE", "RPL", "RSR", "RUNE", "RVN", "SAGA",
    "SAND", "SCRT", "SEI", "SFP", "SKL", "SLP", "SNX", "SOL", "SPELL", "SSV",
    "STEEM", "STG", "STORJ", "STRK", "STX", "SUPER", "SUSHI", "SYN", "SYS", "TAIKO",
    "THETA", "TIA", "TLM", "TNSR", "TON", "TRB", "TRU", "TRX", "TURBO", "TWT",
    "UMA", "UNI", "VET", "VTHO", "WAXP", "WIF", "WLD", "WOO", "XAI", "XLM",
    "XRP", "XTZ", "XVG", "XVS", "YFI", "YGG", "ZEC", "ZEN", "ZETA", "ZIL", "ZRX",
]

# Binance futures sembol formatı (BTCUSDT gibi)
def get_symbol(coin):
    return coin + "USDT"

TRADING_PAIRS = [get_symbol(c) for c in FUTURES_SYMBOLS]
