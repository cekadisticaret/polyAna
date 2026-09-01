"""Session + JWT. Cookie adı bursaapp_session — Poly ile karışmaz."""
from __future__ import annotations

import os
import time
from functools import wraps

import jwt
from flask import g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

JWT_ALG = "HS256"
_RATE: dict[str, list[float]] = {}


def jwt_secret() -> str:
    return os.environ.get("BURSAAPP_JWT_SECRET") or os.environ.get("BURSAAPP_SECRET_KEY") or "bursaapp-dev"


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return bool(hashed) and check_password_hash(hashed, password)


def make_token(user, hours: int = 24 * 30) -> str:
    now = int(time.time())
    payload = {
        "uid": user.id,
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": now + hours * 3600,
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALG)


def decode_token(token: str):
    try:
        return jwt.decode(token, jwt_secret(), algorithms=[JWT_ALG])
    except Exception:
        return None


def rate_ok(bucket: str, limit: int = 5, window: float = 60.0) -> bool:
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "?").split(",")[0].strip()
    key = f"{bucket}:{ip}"
    now = time.time()
    hits = [t for t in _RATE.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _RATE[key] = hits
        return False
    hits.append(now)
    _RATE[key] = hits
    return True


def load_user():
    from models import SessionLocal, User

    if getattr(g, "user_loaded", False):
        return g.user
    g.user_loaded = True
    g.user = None
    uid = session.get("uid")
    token = None
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    if not uid and token:
        payload = decode_token(token)
        if payload:
            uid = payload.get("uid")
    if not uid:
        return None
    db = SessionLocal()
    try:
        g.user = db.get(User, int(uid))
    except Exception:
        g.user = None
    finally:
        db.close()
    return g.user


def login_user(user) -> None:
    session.clear()
    session["uid"] = user.id
    session["role"] = user.role
    session.permanent = True


def logout_user() -> None:
    session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = load_user()
        if user is None:
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "giriş gerekli"}), 401
            return redirect(url_for("giris", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = load_user()
        if user is None:
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "giriş gerekli"}), 401
            return redirect(url_for("giris", next=request.path))
        if user.role != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "yetki yok"}), 403
            return redirect("/")
        return view(*args, **kwargs)

    return wrapped
