#!/usr/bin/env python3
"""Statik görselleri küçült + kart thumbnail üret.

  python3 BursaApp/optimize_images.py
  python3 BursaApp/optimize_images.py --dirs hotel visit food camp market

Kalıcı çözüm:
- Orijinal dosyaları max 1400px / JPEG q=82 ile sıkıştırır (çok büyük PNG/JPG).
- Kartlar için /static/cache/thumbs/<path-hash>-640.jpg üretir.
- place_public → img_url olarak thumb varsa onu verir (liste hızlı açılır).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(_DIR, "static")
THUMB_ROOT = os.path.join(STATIC, "cache", "thumbs")

try:
    from PIL import Image, ImageOps
except ImportError:
    print("Pillow yok: pip install Pillow")
    sys.exit(1)

# Kart listeleri için
CARD_W = 640
CARD_H = 480  # 4:3
# Detay / orijinal tavan
MAX_W = 1400
JPEG_Q = 82
MIN_BYTES_TO_TOUCH = 180_000  # bundan küçükse orijinale dokunma (zaten hafif)


def _thumb_name(rel: str) -> str:
    h = hashlib.sha1(rel.encode()).hexdigest()[:16]
    base = os.path.splitext(os.path.basename(rel))[0][:40]
    return f"{base}-{h}-{CARD_W}.jpg"


def public_thumb_url(rel_static: str) -> str | None:
    """rel_static: 'hotel/foo.jpg' veya '/static/hotel/foo.jpg' → thumb URL."""
    rel = rel_static.lstrip("/")
    if rel.startswith("static/"):
        rel = rel[len("static/") :]
    abs_path = os.path.join(STATIC, rel)
    if not os.path.isfile(abs_path):
        return None
    return ensure_thumb(abs_path, rel)


def ensure_thumb(abs_path: str, rel: str) -> str | None:
    dest = os.path.join(THUMB_ROOT, _thumb_name(rel))
    thumb_url = f"/static/cache/thumbs/{_thumb_name(rel)}"
    if os.path.isfile(dest) and os.path.getsize(dest) > 1000:
        # kaynak daha yeni mi?
        try:
            if os.path.getmtime(dest) >= os.path.getmtime(abs_path):
                return thumb_url
        except OSError:
            return thumb_url
    os.makedirs(THUMB_ROOT, exist_ok=True)
    try:
        im = Image.open(abs_path)
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "P"):
            bg = Image.new("RGB", im.size, (232, 242, 234))
            if im.mode == "P":
                im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        # cover 4:3
        im = ImageOps.fit(im, (CARD_W, CARD_H), Image.Resampling.LANCZOS, centering=(0.5, 0.45))
        tmp = dest + ".tmp"
        im.save(tmp, "JPEG", quality=JPEG_Q, optimize=True, progressive=True)
        os.replace(tmp, dest)
        return thumb_url
    except Exception as e:
        print("thumb fail", rel, e)
        return None


def compress_original(abs_path: str) -> str | None:
    """Büyük dosyayı küçült. Dönüş: yeni abs path (jpg'ye çevrildiyse) veya aynı path; None=dokunulmadı."""
    try:
        size = os.path.getsize(abs_path)
    except OSError:
        return None
    if size < MIN_BYTES_TO_TOUCH:
        return None
    ext = os.path.splitext(abs_path)[1].lower()
    try:
        im = Image.open(abs_path)
        im = ImageOps.exif_transpose(im)
        w, h = im.size
        if max(w, h) <= MAX_W and size < 400_000 and ext in (".jpg", ".jpeg"):
            return None
        if im.mode in ("RGBA", "P"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            if im.mode == "P":
                im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        if max(w, h) > MAX_W:
            im.thumbnail((MAX_W, MAX_W), Image.Resampling.LANCZOS)
        out_path = abs_path
        if ext not in (".jpg", ".jpeg"):
            out_path = os.path.splitext(abs_path)[0] + ".jpg"
        tmp = out_path + ".tmp"
        im.save(tmp, "JPEG", quality=JPEG_Q, optimize=True, progressive=True)
        os.replace(tmp, out_path)
        if out_path != abs_path and os.path.isfile(abs_path):
            try:
                os.remove(abs_path)
            except OSError:
                pass
        return out_path
    except Exception as e:
        print("compress fail", abs_path, e)
        return None


def walk_dirs(dirs: list[str]) -> list[tuple[str, str]]:
    out = []
    for d in dirs:
        root = os.path.join(STATIC, d)
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for fn in files:
                if not fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    continue
                abs_p = os.path.join(dirpath, fn)
                rel = os.path.relpath(abs_p, STATIC).replace("\\", "/")
                out.append((abs_p, rel))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dirs",
        nargs="*",
        default=["hotel", "visit", "food", "camp", "market", "sport", "family", "shop", "hospital", "concert", "cinema", "theater", "event", "fun", "org", "vet", "doctor", "album"],
    )
    ap.add_argument("--no-compress", action="store_true")
    ap.add_argument("--update-db", action="store_true", help="png→jpg path değişimini Place.img_url'e yaz")
    args = ap.parse_args()
    files = walk_dirs(list(args.dirs))
    n_thumb = n_comp = 0
    before = 0
    renames: list[tuple[str, str]] = []  # old /static/... → new
    for abs_p, rel in files:
        try:
            before += os.path.getsize(abs_p)
        except OSError:
            continue
        cur = abs_p
        if not args.no_compress:
            newp = compress_original(abs_p)
            if newp:
                n_comp += 1
                cur = newp
                if newp != abs_p:
                    old_url = "/static/" + rel
                    new_rel = os.path.relpath(newp, STATIC).replace("\\", "/")
                    renames.append((old_url, "/static/" + new_rel))
                    rel = new_rel
        if ensure_thumb(cur, rel):
            n_thumb += 1
    after = 0
    for abs_p, _ in walk_dirs(list(args.dirs)):
        try:
            after += os.path.getsize(abs_p)
        except OSError:
            pass
    if args.update_db and renames:
        sys.path.insert(0, _DIR)
        from models import Place, SessionLocal, init_db

        init_db()
        db = SessionLocal()
        try:
            n = 0
            for old, new in renames:
                for p in db.query(Place).filter(Place.img_url == old).all():
                    p.img_url = new
                    n += 1
            db.commit()
            print(f"db_img_url_updates={n}")
        finally:
            db.close()
    print(f"files={len(files)} thumbs={n_thumb} compressed={n_comp} renames={len(renames)} bytes_before={before} after={after}")


if __name__ == "__main__":
    main()
