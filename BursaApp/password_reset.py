"""Şifre sıfırlama — yeni geçici şifre e-posta ile."""
from __future__ import annotations

import secrets
import string

from auth import hash_password


def _new_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def send_new_password_email(db, email: str) -> bool:
    """Kayıtlı aktif üyeye yeni şifre üretir ve mail atar. Yoksa sessizce False."""
    from models import User
    from notify import enqueue, send_email_now

    email = (email or "").strip().lower()
    if "@" not in email:
        return False

    u = db.query(User).filter(User.email == email).first()
    if u is None or not bool(getattr(u, "is_active", True)):
        return False

    plain = _new_password()
    u.password_hash = hash_password(plain)
    db.commit()

    name = (u.name or "").strip() or "Üye"
    subject = "BursaApp yeni şifren"
    body = (
        f"Merhaba {name},\n\n"
        f"Şifre sıfırlama talebin alındı. Yeni geçici şifren:\n\n"
        f"  {plain}\n\n"
        f"Uygulama veya sitede bu şifreyle giriş yapıp profilden değiştirebilirsin.\n"
        f"Bu isteği sen yapmadıysan hemen bizimle iletişime geç.\n\n"
        f"— BursaApp\n"
    )
    enqueue(kind="password_reset", title=subject, body=body, user_emails=[email])
    sent = send_email_now(email, subject, body)
    if sent:
        try:
            from models import log_activity

            log_activity(
                db,
                kind="password_reset",
                title="Şifre sıfırlandı (e-posta)",
                detail=name,
                user_id=u.id,
                email=u.email,
                user_role=u.role,
            )
            db.commit()
        except Exception:
            pass
    return sent
