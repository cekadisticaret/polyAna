#!/usr/bin/env python3
"""Bota özelden /start veya herhangi bir mesaj attıktan sonra çalıştır — chat_id yazdırır."""
import json
import urllib.request

try:
    from bist_scalping_config import BOT_TOKEN
except ImportError:
    print("bist_scalping_config.py yok veya BOT_TOKEN eksik")
    raise SystemExit(1)

r = urllib.request.urlopen(
    f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", timeout=15
)
d = json.loads(r.read().decode())
if not d.get("ok") or not d.get("result"):
    print("Henüz güncelleme yok. @Bist15DakikaBot'a özelden /start gönder, sonra tekrar dene.")
    raise SystemExit(0)
for u in d["result"]:
    msg = u.get("message") or u.get("edited_message")
    if not msg:
        continue
    chat = msg.get("chat") or {}
    uid = chat.get("id")
    typ = chat.get("type")
    un = chat.get("username") or ""
    print(f"chat_id={uid}  type={typ}  @{un}" if un else f"chat_id={uid}  type={typ}")
print("\nbist_scalping_config.py içinde CHAT_ID = \"<yukarıdaki sayı>\" yap.")
