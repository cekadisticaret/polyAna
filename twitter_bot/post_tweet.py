#!/usr/bin/env python3
"""@tradecomio — X/Twitter otomatik tweet gönderici (OAuth1.0a user context, v2 API)."""
from __future__ import annotations

import os
import sys

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

import tweepy  # noqa: E402

API_KEY = os.environ.get("TWITTER_API_KEY", "")
API_SECRET = os.environ.get("TWITTER_API_SECRET", "")
ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN", "")
ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET", "")
TWITTER_HANDLE = os.environ.get("TWITTER_HANDLE", "tradecomio").strip().lstrip("@")


def _check_keys() -> None:
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET]):
        raise RuntimeError("Twitter API anahtarları .env içinde eksik (TWITTER_API_KEY/SECRET/ACCESS_TOKEN/SECRET)")


def get_client() -> "tweepy.Client":
    _check_keys()
    return tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_SECRET,
    )


def get_media_api() -> "tweepy.API":
    """Medya yükleme v2'de yok — v1.1 (OAuth1UserHandler) gerekiyor."""
    _check_keys()
    auth = tweepy.OAuth1UserHandler(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET)
    return tweepy.API(auth)


def post_tweet(text: str) -> dict:
    client = get_client()
    resp = client.create_tweet(text=text)
    return resp.data


def post_tweet_with_image(text: str, image_path: str) -> str:
    media_api = get_media_api()
    media = media_api.media_upload(filename=image_path)
    client = get_client()
    resp = client.create_tweet(text=text, media_ids=[media.media_id])
    tid = resp.data.get("id")
    return f"https://x.com/{TWITTER_HANDLE}/status/{tid}"


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Tradecom.io devrede 🤖📊 Kripto analizleri otomatik olarak burada paylaşılacak."
    try:
        data = post_tweet(msg)
        tid = data.get("id")
        print(f"Tweet atıldı: https://x.com/{TWITTER_HANDLE}/status/{tid}")
    except Exception as e:
        print(f"HATA: {e}")
        sys.exit(1)
