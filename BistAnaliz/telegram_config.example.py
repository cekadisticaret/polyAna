# Kök dizine kopyala: cp BistAnaliz/telegram_config.example.py telegram_config.py
BOT_TOKEN = "YOUR_BOT_TOKEN"

# Varsayılan hedef (ayrı kanal tanımlamazsan her iki betik buraya yazar)
CHAT_ID = "YOUR_GROUP_OR_CHANNEL_ID"

# İsteğe bağlı: hangisi doluysa o betik sadece o sohbete yollar (-100… süpergrup/kanal)
CHAT_ID_BIST_HOUR = ""    # BistHourSinyal (bist_visual_v2) — boşsa CHAT_ID
CHAT_ID_BIST_SIGNAL = ""  # bist_signal_hunter — örn. @KanalAdi veya -100…; boşsa CHAT_ID
