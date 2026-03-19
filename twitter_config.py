# Twitter/X API Konfigürasyonu - @ZekaChain
import os

def _env(key):
    val = os.environ.get(key)
    if not val:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip()
            val = os.environ.get(key)
    return val

API_KEY             = _env("TWITTER_API_KEY")
API_SECRET          = _env("TWITTER_API_SECRET")
ACCESS_TOKEN        = _env("TWITTER_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = _env("TWITTER_ACCESS_TOKEN_SECRET")
