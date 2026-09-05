"""Harita döşeme katmanları — Carto (key varsa) veya Esri açık gri."""
from __future__ import annotations

import os


def leaflet_tile_layers() -> list[dict]:
    key = (os.environ.get("CARTO_API_KEY") or "").strip()
    if key:
        return [
            {
                "url": (
                    "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                    f"?key={key}"
                ),
                "attribution": "&copy; OpenStreetMap &copy; CARTO",
                "subdomains": "abcd",
                "maxZoom": 19,
            }
        ]
    return [
        {
            "url": (
                "https://server.arcgisonline.com/ArcGIS/rest/services/"
                "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
            ),
            "attribution": "Tiles &copy; Esri",
            "maxZoom": 16,
        },
        {
            "url": (
                "https://server.arcgisonline.com/ArcGIS/rest/services/"
                "Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
            ),
            "attribution": "",
            "maxZoom": 16,
            "opacity": 0.9,
        },
    ]
