"""E-posta doğrulama + onaylanmayan üyelik temizliği."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta

VERIFY_DAYS = 7


def new_email_token() -> str:
    return secrets.token_urlsafe(32)


def send_verify_email(*, email: str, name: str, token: str) -> dict:
    """Onay maili dener. Dönüş: {ok, link, smtp}."""
    from notify import enqueue, send_email_now, smtp_ready, telegram_send

    base = (os.environ.get("BURSAAPP_PUBLIC_URL") or "https://bursaapp.com").rstrip("/")
    link = f"{base}/hesap/email-onay?token={token}"
    subject = "BursaApp e-posta onayı"
    body = (
        f"Merhaba {name},\n\n"
        f"BursaApp hesabını onaylamak için bağlantıya tıkla:\n{link}\n\n"
        f"Önemli: {VERIFY_DAYS} gün içinde onaylamazsan üyeliğin otomatik iptal edilir.\n"
        f"Bu isteği sen yapmadıysan yok say.\n"
    )
    enqueue(kind="verify", title=subject, body=body, url=link, user_emails=[email])
    ok = send_email_now(email, subject, body)
    if ok:
        # outbox satırını sent işaretle (son eklenen verify)
        try:
            from notify import flush_outbox

            flush_outbox(limit=20)
        except Exception:
            pass
    try:
        telegram_send(f"BursaApp e-posta onay linki\n{name} · {email}\n{link}")
    except Exception:
        pass
    return {"ok": bool(ok), "link": link, "smtp": smtp_ready()}


def mark_verified(db, user) -> None:
    user.email_verified = True
    user.email_token = ""
    db.commit()


def verify_banner(user) -> dict | None:
    """Onaysız üye için kırmızı şerit verisi; onaylı/admin/guest → None."""
    if user is None:
        return None
    if getattr(user, "role", "") in ("admin", "editor"):
        return None
    if bool(getattr(user, "email_verified", False)):
        return None
    created = getattr(user, "created_at", None) or datetime.utcnow()
    deadline = created + timedelta(days=VERIFY_DAYS)
    left = deadline - datetime.utcnow()
    secs = max(0, int(left.total_seconds()))
    days_left = secs // 86400
    hours_left = (secs % 86400) // 3600
    return {
        "days_left": days_left,
        "hours_left": hours_left,
        "deadline": deadline,
        "total_days": VERIFY_DAYS,
    }


def can_review(user) -> bool:
    if user is None:
        return False
    if getattr(user, "role", "") in ("admin", "editor"):
        return True
    return bool(getattr(user, "email_verified", False))


def _delete_user_data(db, user_id: int) -> None:
    from models import (
        ActivityLog,
        ClaimRequest,
        Coupon,
        EventGoing,
        Favorite,
        Place,
        PlacePhoto,
        PostLike,
        Review,
        SavedRoute,
        UserFollow,
        UserPost,
        UserVisit,
    )

    db.query(UserFollow).filter(
        (UserFollow.follower_id == user_id) | (UserFollow.following_id == user_id)
    ).delete(synchronize_session=False)
    # Post likes on this user's posts
    post_ids = [pid for (pid,) in db.query(UserPost.id).filter(UserPost.user_id == user_id).all()]
    if post_ids:
        db.query(PostLike).filter(PostLike.post_id.in_(post_ids)).delete(synchronize_session=False)
    db.query(PostLike).filter(PostLike.user_id == user_id).delete(synchronize_session=False)
    db.query(UserPost).filter(UserPost.user_id == user_id).delete(synchronize_session=False)
    db.query(Review).filter(Review.user_id == user_id).delete(synchronize_session=False)
    db.query(Favorite).filter(Favorite.user_id == user_id).delete(synchronize_session=False)
    db.query(PlacePhoto).filter(PlacePhoto.user_id == user_id).delete(synchronize_session=False)
    db.query(UserVisit).filter(UserVisit.user_id == user_id).delete(synchronize_session=False)
    db.query(EventGoing).filter(EventGoing.user_id == user_id).delete(synchronize_session=False)
    db.query(SavedRoute).filter(SavedRoute.user_id == user_id).delete(synchronize_session=False)
    db.query(Coupon).filter(Coupon.owner_user_id == user_id).delete(synchronize_session=False)
    db.query(ActivityLog).filter(ActivityLog.user_id == user_id).delete(synchronize_session=False)
    db.query(ClaimRequest).filter(ClaimRequest.user_id == user_id).delete(synchronize_session=False)
    # taslak yerler: sahipliği bırak
    db.query(Place).filter(Place.submitted_by_id == user_id).update(
        {Place.submitted_by_id: None}, synchronize_session=False
    )
    db.query(Place).filter(Place.owner_user_id == user_id).update(
        {Place.owner_user_id: None}, synchronize_session=False
    )
    db.query(Place).filter(Place.reviewed_by_id == user_id).update(
        {Place.reviewed_by_id: None}, synchronize_session=False
    )


def purge_unverified_users(db, *, days: int = VERIFY_DAYS) -> int:
    """Onaysız ve süresi dolmuş üyelikleri sil. Admin dokunulmaz."""
    from models import User, log_activity

    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(User)
        .filter(
            User.email_verified.is_(False),
            User.role == "user",
            User.created_at < cutoff,
        )
        .all()
    )
    n = 0
    for u in rows:
        uid, email, name = u.id, u.email, u.name
        _delete_user_data(db, uid)
        db.delete(u)
        try:
            log_activity(
                db,
                kind="purge_unverified",
                title="Onaysız üyelik iptal",
                detail=f"{name} · {email} · {days}g",
                user_id=None,
                email=email,
            )
        except Exception:
            pass
        n += 1
    if n:
        db.commit()
    return n


if __name__ == "__main__":
    from models import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        print("purged", purge_unverified_users(db))
    finally:
        db.close()
