"""BursaApp üye puanı — loyalty_points tek kaynak; bu modül kazan/harca kuralları."""
from __future__ import annotations

from models import User, UserPointLog

POINTS_SIGNUP = 20
POINTS_EMAIL_VERIFY = 30
POINTS_REVIEW_APPROVED = 10
POINTS_ACTIVITY_JOIN = 5
POINTS_ACTIVITY_HOST = 3
POINTS_COUPON_COST = 100


def user_points(user: User | None) -> int:
    if user is None:
        return 0
    return max(0, int(getattr(user, "loyalty_points", 0) or 0))


def points_level(pts: int) -> str:
    if pts >= 500:
        return "Usta gezgin"
    if pts >= 200:
        return "Deneyimli"
    if pts >= 50:
        return "Keşifçi"
    return "Yeni üye"


def _log_exists(db, user_id: int, reason: str, ref_type: str, ref_id: int) -> bool:
    if not ref_type:
        return False
    return (
        db.query(UserPointLog.id)
        .filter(
            UserPointLog.user_id == user_id,
            UserPointLog.reason == reason,
            UserPointLog.ref_type == ref_type,
            UserPointLog.ref_id == ref_id,
        )
        .first()
        is not None
    )


def award_points(
    db,
    user_id: int,
    amount: int,
    *,
    reason: str,
    ref_type: str = "",
    ref_id: int = 0,
) -> bool:
    """Puan ekle. Aynı ref için tekrar vermez → True yalnızca işlendiyse."""
    if amount <= 0:
        return False
    if ref_type and _log_exists(db, user_id, reason, ref_type, ref_id):
        return False
    u = db.get(User, user_id)
    if not u:
        return False
    u.loyalty_points = user_points(u) + amount
    db.add(
        UserPointLog(
            user_id=user_id,
            delta=amount,
            reason=reason,
            ref_type=ref_type or "",
            ref_id=int(ref_id or 0),
        )
    )
    return True


def spend_points(
    db,
    user: User,
    amount: int,
    *,
    reason: str,
    ref_type: str = "",
    ref_id: int = 0,
) -> tuple[bool, str | None]:
    if amount <= 0:
        return False, "Geçersiz tutar"
    pts = user_points(user)
    if pts < amount:
        return False, f"Yetersiz puan ({pts}/{amount})"
    u = db.get(User, user.id)
    if not u:
        return False, "Kullanıcı yok"
    u.loyalty_points = pts - amount
    db.add(
        UserPointLog(
            user_id=u.id,
            delta=-amount,
            reason=reason,
            ref_type=ref_type or "",
            ref_id=int(ref_id or 0),
        )
    )
    return True, None


def award_signup(db, user_id: int) -> None:
    award_points(db, user_id, POINTS_SIGNUP, reason="signup", ref_type="user", ref_id=user_id)


def award_email_verified(db, user_id: int) -> None:
    award_points(db, user_id, POINTS_EMAIL_VERIFY, reason="email_verified", ref_type="user", ref_id=user_id)


def award_review_approved(db, user_id: int, review_id: int) -> None:
    award_points(
        db,
        user_id,
        POINTS_REVIEW_APPROVED,
        reason="review_approved",
        ref_type="review",
        ref_id=review_id,
    )


def award_activity_join_approved(db, *, join_user_id: int, seek_id: int, host_id: int) -> None:
    award_points(
        db,
        join_user_id,
        POINTS_ACTIVITY_JOIN,
        reason="activity_join",
        ref_type="seek_join",
        ref_id=seek_id,
    )
    award_points(
        db,
        host_id,
        POINTS_ACTIVITY_HOST,
        reason="activity_host",
        ref_type="seek_host",
        ref_id=seek_id,
    )
