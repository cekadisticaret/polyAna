#!/usr/bin/env python3
"""BursaApp marka ikonu — lacivert zemin, lime B, krem konum noktası."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
MOBILE_ICON = ROOT / "mobile" / "assets" / "branding" / "app_icon.png"

NAV = (26, 46, 36, 255)
LIME = (184, 233, 134, 255)
CREAM = (246, 243, 236, 255)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = int(size * 0.08)
    radius = int(size * 0.22)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=radius,
        fill=NAV,
    )

    font_size = int(size * 0.50)
    font = ImageFont.truetype(FONT, font_size)
    text = "B"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    ty = (size - th) // 2 - bbox[1] - int(size * 0.03)
    draw.text((tx, ty), text, fill=LIME, font=font)

    dot_r = int(size * 0.055)
    cx = size - margin - int(dot_r * 2.4)
    cy = size - margin - int(dot_r * 2.4)
    draw.ellipse((cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r), fill=CREAM)
    return img


def main() -> None:
    targets = {
        STATIC / "logo.png": 512,
        STATIC / "logo-512.png": 512,
        STATIC / "logo-192.png": 192,
        STATIC / "apple-touch-icon.png": 180,
        STATIC / "favicon-32.png": 32,
        STATIC / "favicon-16.png": 16,
        MOBILE_ICON: 1024,
    }
    for path, size in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        render(size).save(path, format="PNG", optimize=True)
        print(f"wrote {path} ({size}px)")

    ico_sizes = [render(s) for s in (16, 32, 48)]
    ico_sizes[0].save(
        STATIC / "favicon.ico",
        format="ICO",
        sizes=[(im.width, im.height) for im in ico_sizes],
        append_images=ico_sizes[1:],
    )
    print(f"wrote {STATIC / 'favicon.ico'}")


if __name__ == "__main__":
    main()
