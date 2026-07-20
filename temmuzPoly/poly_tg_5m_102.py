"""5M/15M gerçek PM saatlik özet + işlem bildirimleri (8799859033 bot)."""
import json
import urllib.request

BOT_TOKEN = "8799859033:AAHjOkEDP7W5sk97lFknakMokgoKBf62Ssg"
CHAT_ID   = "830754964"


def tg_send(text: str) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                resp = json.loads(r.read())
            if not resp.get("ok"):
                print(f"[5M 102 TG] API hata: {resp.get('description', resp)}")
                return False
            return True
        except Exception as e:
            print(f"[5M 102 TG] Hata ({attempt + 1}/3): {e}")
            if attempt < 2:
                import time
                time.sleep(2)
    return False


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            img_data = f.read()
        boundary = "----102Boundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"heatmap.png\"\r\n"
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except Exception as e:
        print(f"[5M 102 TG photo] Hata: {e}")
