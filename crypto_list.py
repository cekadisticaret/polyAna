# Kripto Para Listesi - Cem'in tam listesi
# Son güncelleme: 2026-03-14
# Binance Futures'da USDT paritesiyle kullanılacak (örn: BTCUSDT)

CRYPTO_SYMBOLS = [
    "BTC", "ETH", "USDT", "BNB", "SOL", "XRP", "USDC", "ADA", "DOGE", "TRX",
    "TON", "LINK", "AVAX", "MATIC", "DOT", "LTC", "BCH", "SHIB", "DAI", "UNI",
    "APT", "ATOM", "ETC", "OP", "ARB", "FIL", "XLM", "NEAR", "ICP", "HBAR",
    "VET", "ALGO", "MKR", "AAVE", "INJ", "RNDR", "STX", "IMX", "THETA", "LDO",
    "SAND", "GRT", "RUNE", "EGLD", "KAS", "QNT", "FLOW", "XTZ", "AXS", "KAVA",
    "CHZ", "ZEC", "SNX", "CRV", "DYDX", "COMP", "SUSHI", "YFI", "BAL", "ENJ",
    "BAT", "ZIL", "IOTA", "HOT", "ICX", "DASH", "NEO", "OMG", "ONT", "QTUM",
    "LSK", "WAVES", "ARDR", "NANO", "SC", "DGB", "RVN", "CKB", "CELR", "ANKR",
    "ONE", "SKL", "STORJ", "BNT", "BAND", "OCEAN", "CTSI", "COTI", "KNC", "FET",
    "AGIX", "ROSE", "API3", "MASK", "PEOPLE", "GMX", "ILV", "MAGIC", "AUDIO", "JASMY",
    "GLM", "WAXP", "POWR", "ELF", "AR", "SFP", "LRC", "GALA", "BLUR", "FLUX",
    "PHA", "SSV", "ID", "ASTR", "MINA", "HOOK", "HIGH", "PORTAL", "ACE", "DYM",
    "TIA", "SEI", "ORDI", "PYTH", "JTO", "BONK", "WIF", "PEPE", "FLOKI", "BOME",
    "MEME", "TURBO", "AKT", "OSMO", "KSM", "MOVR", "KDA", "SCRT", "INTR", "XNO",
    "ERG", "TRB", "DODO", "PERP", "JOE", "SXP", "FXS", "LQTY", "RPL", "ENS",
    "CVX", "YGG", "ALPHA", "PENDLE", "SYN", "WOO", "RARE", "RLC", "BICO", "REQ",
    "MLN", "NMR", "KEEP", "NU", "STG", "RDNT", "VELO", "CEL", "SPELL", "TOMO",
    "STRAX", "HIVE", "STEEM", "GNO", "DCR", "SYS", "ZEN", "KMD", "BTG", "BCD",
    "VTHO", "IOST", "ELA", "NKN", "TEL", "WIN", "TWT", "CAKE", "BAKE", "BURGER",
    "ALPACA", "MDX", "AUTO", "BIFI", "DFI", "LINA", "PERL", "MBOX", "XVS", "TLM",
    "GHST", "SUPER", "NFT", "FORTH", "BADGER", "KP3R", "TORN", "REN", "RSR", "OGN",
    "STPT", "DATA", "VIDT", "POND", "FRONT", "AMB", "POLS", "UOS", "POLYX", "C98",
    "LIT", "TRU", "BEL", "HARD", "FARM", "TROY", "IRIS", "CTK", "MTL", "DENT",
    "KEY", "NULS", "WAN", "COS", "DOCK", "VITE", "GO", "QKC", "AKRO", "LTO",
    "MLK", "XPR", "BTS", "ARPA", "DIA", "CVC", "SNT", "STMX", "FUN", "REQT",
    "TCT", "IDEX", "GHX", "LAT", "CLV", "FIDA", "SRM", "OXT", "BOND", "ALICE",
    "DAR", "VRA", "PIVX", "FIRO", "NAV", "BTM", "NBS", "LOOM", "RIF", "FSN",
    "XVG", "STRK", "CSPR", "DUSK", "TRIAS", "VLX", "AERGO", "ATA", "MBL", "CTXC",
    "CREAM", "ORN", "DEXE", "KAR", "ACA", "GLMR", "SXP2", "RAY", "STEP", "MAPS",
    "KIN", "GFT", "VRSC", "XCAD", "WNCG", "MYRIA", "LPT", "AKRO2", "CUDOS", "DODO2",
    "KILT", "SD", "UNFI", "FIDA2", "NEST", "GNS", "LBR", "WLD", "ARKM", "CYBER",
    "PYR", "TLOS", "ALT", "NTRN", "STRD", "XAI", "MANTA", "JUP", "SAGA", "TAIKO",
    "ZETA", "PIXEL", "BEAM", "RON", "PROM", "MAV", "PRIME", "ZRX", "ACH", "TRAC",
    "ALCX", "BOBA", "CELO", "CORE", "HNT", "LQDR", "METIS", "NFP", "OM", "ORBS",
    "PHA2", "QANX", "REEF", "RLY", "SIS", "STOS", "SWEAT", "TARA", "TEMCO", "TNSR",
    "TRU2", "WAVES2", "XPLA", "ZBC", "ZIG", "ZTX", "AURY", "AVT", "BANANA", "BETA",
    "BOND2", "BRISE", "CANTO", "CAPO", "CGPT", "COMBO", "CTC", "DEGO", "DIONE", "ECOX",
    "EVER", "FLM", "FUSE", "GAL", "GODS", "HFT", "HOPR", "IDIA", "INSUR", "JST",
    "KLAY", "L3", "LAYER", "LEVER", "LINA2", "LQTY2", "MATH", "MAVIA", "MOBILE", "MUBI",
    "NEON", "NODL", "NYM", "OPUL", "PAAL", "PRQ", "PSG", "RAD", "RARI", "RGT",
    "SDAO", "SLP", "SNTVT", "SOV", "SPARTA", "STND", "TOKE", "TRVL", "UMA", "UQC",
    "UTK", "VAI", "VXV", "WAGMI", "WAXL", "WEETH", "WILD", "XAVA", "XDEFI", "XMON",
    "XRD", "XVS2", "YLD", "ZAM", "ZENI", "ZKF", "ZPAY",
]

# Binance Futures USDT paritesi için sembol üretici
def get_futures_symbol(coin):
    return coin.replace("2", "") + "USDT"

FUTURES_SYMBOLS = [get_futures_symbol(c) for c in CRYPTO_SYMBOLS
                   if c not in ("USDT", "USDC", "DAI")]  # Stableları çıkar
