# BIST Tarayıcı Bot — Kurulum Kılavuzu

## 1. Gereksinimler
Python 3.10+ yüklü olmalı.

## 2. Kütüphaneleri Kur
```bash
pip install -r requirements.txt --break-system-packages
```

## 3. Telegram Ayarları
scanner.py dosyasını aç, en üstteki iki satırı doldur:
```python
TELEGRAM_TOKEN   = "1234567890:ABCdef..."   # BotFather'dan aldığın token
TELEGRAM_CHAT_ID = "123456789"              # Kendi chat ID'n
```

### Chat ID Nasıl Öğrenilir?
Tarayıcıda şu adrese git:
https://api.telegram.org/bot<TOKEN>/getUpdates
Bota bir mesaj at, gelen JSON'da "chat":{"id": XXXXX} kısmındaki sayı senin Chat ID'n.

## 4. Çalıştır
```bash
python3 scanner.py
```

## 5. Arka Planda 7/24 Çalıştır (systemd)
```bash
# Servis dosyası oluştur
sudo nano /etc/systemd/system/bist-scanner.service
```

İçine yapıştır:
```ini
[Unit]
Description=BIST Tarayıcı Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/bist_scanner
ExecStart=/usr/bin/python3 /home/ubuntu/bist_scanner/scanner.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Servisi başlat:
```bash
sudo systemctl daemon-reload
sudo systemctl enable bist-scanner
sudo systemctl start bist-scanner
sudo systemctl status bist-scanner
```

Log takibi:
```bash
tail -f scanner.log
# veya
sudo journalctl -u bist-scanner -f
```

## 6. Parametreleri Değiştirme
scanner.py içinde şu değerleri istediğin gibi ayarlayabilirsin:
- RSI_THRESHOLD  = 55   (RSI eşiği)
- ADX_THRESHOLD  = 25   (ADX eşiği)
- VOL_MULT       = 1.5  (Hacim spike çarpanı)
- DIST_THRESHOLD = 5.0  (EMA uzaklık %)
- SCAN_INTERVAL_15M     (Kaç saniyede bir tara)
