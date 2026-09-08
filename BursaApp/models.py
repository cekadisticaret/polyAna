"""SQLAlchemy modelleri — Place + Review + işletme/kampanya/favori."""
from __future__ import annotations

import json
import os
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_DIR, "data", "bursaapp.db")
SEED_JSON = os.path.join(_DIR, "data", "places.json")

PLAN_TIERS = {
    "free": {"label": "Ücretsiz", "photos": 5, "price_tl": 0},
    "pro": {"label": "PRO", "photos": 30, "price_tl": 499},
    "premium": {"label": "Premium", "photos": 99, "price_tl": 999},
}


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    loyalty_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notify_concert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_theater: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_festival: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_campaign: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_new_place: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_token: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    show_full_name: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    permissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    places: Mapped[list["Place"]] = relationship("Place", back_populates="submitter", foreign_keys="Place.submitted_by_id")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="user")
    owned_places: Mapped[list["Place"]] = relationship("Place", back_populates="owner", foreign_keys="Place.owner_user_id")

    def display_name(self) -> str:
        name = (self.name or "").strip() or "Üye"
        if self.show_full_name:
            return name
        parts = [p for p in name.split() if p]
        if not parts:
            return "Üye"
        return " ".join(f"{p[0].upper()}.." for p in parts)

    def handle(self) -> str:
        base = (self.email or "").split("@")[0].strip().lower()
        if base.endswith(".sanal"):
            base = base[: -len(".sanal")]
        base = "".join(c for c in base if c.isalnum() or c in "._")[:24] or f"uye{self.id}"
        return f"@{base}"

    def public(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "handle": self.handle(),
            "display_name": self.display_name(),
            "avatar_url": self.avatar_url or "",
            "email_verified": bool(self.email_verified),
            "show_full_name": bool(self.show_full_name),
            "role": self.role,
            "loyalty_points": self.loyalty_points,
        }


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(90), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    subcategory: Mapped[str] = mapped_column(String(48), nullable=False, default="", index=True)
    ilce: Mapped[str] = mapped_column(String(48), nullable=False, default="")
    address: Mapped[str] = mapped_column(String(280), nullable=False, default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    web: Mapped[str] = mapped_column(String(280), nullable=False, default="")
    hours_text: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    price_band: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    blurb: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    img_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    rating_admin: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    submitted_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str] = mapped_column(String(280), nullable=False, default="")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    venue_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # işletme / premium
    owner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    claim_status: Mapped[str] = mapped_column(String(16), nullable=False, default="")  # ""|pending|approved|rejected
    plan_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="free")
    plan_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    boost_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ticket_price: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    ticket_url: Mapped[str] = mapped_column(String(280), nullable=False, default="")
    instagram: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    whatsapp: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    menu_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    phone_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maps_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    web_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fav_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    est_meal_tl: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # kişi başı tahmini
    # esnek alan: menu, gallery, services, fees, staff, specialty_detail …
    extra_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    submitter: Mapped[User | None] = relationship("User", foreign_keys=[submitted_by_id], back_populates="places")
    reviewer: Mapped[User | None] = relationship("User", foreign_keys=[reviewed_by_id])
    owner: Mapped[User | None] = relationship("User", foreign_keys=[owner_user_id], back_populates="owned_places")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="place", cascade="all, delete-orphan")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("place_id", "user_id", name="uq_review_place_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[int] = mapped_column(Integer, ForeignKey("places.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    score_food: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    score_service: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    score_atmosphere: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    score_price: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    img_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)  # pending|approved|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    place: Mapped[Place] = relationship("Place", back_populates="reviews")
    user: Mapped[User] = relationship("User", back_populates="reviews")

    def overall(self) -> float:
        return (self.score_food + self.score_service + self.score_atmosphere + self.score_price) / 4.0

    def public(self) -> dict:
        uname = "Üye"
        if self.user:
            uname = self.user.display_name()
        return {
            "id": self.id,
            "place_id": self.place_id,
            "user_id": self.user_id,
            "user_name": uname,
            "score_food": self.score_food,
            "score_service": self.score_service,
            "score_atmosphere": self.score_atmosphere,
            "score_price": self.score_price,
            "overall": round(self.overall(), 1),
            "body": self.body,
            "img_url": self.img_url or "",
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "place_id", name="uq_fav_user_place"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    place_id: Mapped[int] = mapped_column(Integer, ForeignKey("places.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PlacePhoto(Base):
    """Üye yer fotoğrafı (kamp vb.) — admin onayından sonra galeriye düşer."""

    __tablename__ = "place_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[int] = mapped_column(Integer, ForeignKey("places.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    img_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    caption: Mapped[str] = mapped_column(String(280), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class UserPost(Base):
    """Üye feed gönderisi — metin + foto + isteğe bağlı yer etiketi."""

    __tablename__ = "user_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    place_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("places.id"), nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    images_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    privacy: Mapped[str] = mapped_column(String(16), nullable=False, default="public")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)  # pending|approved|rejected
    likes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class UserVisit(Base):
    """Üyenin gittiği yerler (check-in / albüm)."""

    __tablename__ = "user_visits"
    __table_args__ = (UniqueConstraint("user_id", "place_id", name="uq_visit_user_place"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    place_id: Mapped[int] = mapped_column(Integer, ForeignKey("places.id"), nullable=False, index=True)
    note: Mapped[str] = mapped_column(String(280), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="approved", index=True)  # pending|approved|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class EventGoing(Base):
    """Etkinliğe gideceğim — ileride tanışma sistemi için temel."""

    __tablename__ = "event_going"
    __table_args__ = (UniqueConstraint("user_id", "place_id", name="uq_going_user_place"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    place_id: Mapped[int] = mapped_column(Integer, ForeignKey("places.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_like_user_post"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_posts.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class PostComment(Base):
    """Feed gönderisi yorumu — küfür filtresinden sonra doğrudan yayın."""

    __tablename__ = "post_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_posts.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="approved", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User")

    def public(self) -> dict:
        uname = self.user.display_name() if self.user else "Üye"
        return {
            "id": self.id,
            "user_name": uname,
            "body": self.body,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserFollow(Base):
    """Kullanıcı takip — feed Friends sekmesi."""

    __tablename__ = "user_follows"
    __table_args__ = (UniqueConstraint("follower_id", "following_id", name="uq_follow_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    follower_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    following_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SeoAudit(Base):
    __tablename__ = "seo_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    summary: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    issues_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    ok_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[int] = mapped_column(Integer, ForeignKey("places.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    badge: Mapped[str] = mapped_column(String(80), nullable=False, default="")  # %20 indirim
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="approved", index=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    place_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("places.id"), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    discount_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SavedRoute(Base):
    __tablename__ = "saved_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="1 günlük rota")
    budget_tl: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    slots_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class Editorial(Base):
    __tablename__ = "editorials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(90), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    blurb: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    place_slugs: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="approved")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ClaimRequest(Base):
    __tablename__ = "claim_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[int] = mapped_column(Integer, ForeignKey("places.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    note: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    tax_doc_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    id_doc_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ActivityLog(Base):
    """Admin paneli: kayıt, giriş, yer ekleme vb. olaylar."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # register|login|logout|place_submit|…
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(190), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    detail: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    path: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class SiteDayStat(Base):
    """Günlük site trafiği (İstanbul günü)."""

    __tablename__ = "site_day_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)  # YYYY-MM-DD
    pageviews: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visitors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SiteVisitorDay(Base):
    """Aynı ziyaretçiyi günde bir kez saymak için."""

    __tablename__ = "site_visitor_days"
    __table_args__ = (UniqueConstraint("day", "vid", name="uq_site_visitor_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    vid: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class SitePageStat(Base):
    """Sayfa bazlı günlük görüntüleme."""

    __tablename__ = "site_page_stats"
    __table_args__ = (UniqueConstraint("day", "path", name="uq_site_page_day_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    pageviews: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visitors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SitePageVisitorDay(Base):
    """Sayfa + gün + ziyaretçi tekilliği."""

    __tablename__ = "site_page_visitor_days"
    __table_args__ = (UniqueConstraint("day", "path", "vid", name="uq_site_page_visitor_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    vid: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class SiteClickStat(Base):
    """Günlük tıklama özeti — kind: phone|maps|web|nav|cta."""

    __tablename__ = "site_click_stats"
    __table_args__ = (UniqueConstraint("day", "kind", "target", name="uq_site_click_day_kind_target"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SiteEngagementDay(Base):
    """Günlük sayfa süresi + scroll derinliği."""

    __tablename__ = "site_engagement_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scroll_25: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scroll_50: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scroll_75: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scroll_100: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SiteSessionDay(Base):
    """Ziyaretçi başına günlük oturum süresi (saniye, max)."""

    __tablename__ = "site_session_days"
    __table_args__ = (UniqueConstraint("day", "vid", name="uq_site_session_day_vid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    vid: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SportMatch(Base):
    """Bursaspor (ve ileride diğer kulüp) maç fikstürü."""

    __tablename__ = "sport_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club: Mapped[str] = mapped_column(String(48), nullable=False, default="bursaspor", index=True)
    season: Mapped[str] = mapped_column(String(16), nullable=False, default="2026-27", index=True)
    week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    competition: Mapped[str] = mapped_column(String(80), nullable=False, default="1. Lig")
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    home_team: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    away_team: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ticket_price: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    ticket_url: Mapped[str] = mapped_column(String(280), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="scheduled")  # scheduled|played|postponed
    note: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _table_cols(conn, table: str) -> set[str]:
    if not conn.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")).fetchone():
        return set()
    return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}


def _migrate_sqlite() -> None:
    place_cols = (
        ("subcategory", "VARCHAR(48) DEFAULT ''"),
        ("rating_avg", "FLOAT"),
        ("rating_count", "INTEGER DEFAULT 0"),
        ("owner_user_id", "INTEGER"),
        ("claim_status", "VARCHAR(16) DEFAULT ''"),
        ("plan_tier", "VARCHAR(16) DEFAULT 'free'"),
        ("plan_until", "DATETIME"),
        ("boost_until", "DATETIME"),
        ("ticket_price", "VARCHAR(80) DEFAULT ''"),
        ("ticket_url", "VARCHAR(280) DEFAULT ''"),
        ("instagram", "VARCHAR(120) DEFAULT ''"),
        ("whatsapp", "VARCHAR(40) DEFAULT ''"),
        ("menu_text", "TEXT DEFAULT ''"),
        ("views", "INTEGER DEFAULT 0"),
        ("phone_clicks", "INTEGER DEFAULT 0"),
        ("maps_clicks", "INTEGER DEFAULT 0"),
        ("web_clicks", "INTEGER DEFAULT 0"),
        ("fav_count", "INTEGER DEFAULT 0"),
        ("est_meal_tl", "INTEGER DEFAULT 0"),
        ("extra_json", "TEXT DEFAULT '{}'"),
    )
    user_cols = (
        ("loyalty_points", "INTEGER DEFAULT 0"),
        ("notify_concert", "BOOLEAN DEFAULT 1"),
        ("notify_theater", "BOOLEAN DEFAULT 1"),
        ("notify_festival", "BOOLEAN DEFAULT 1"),
        ("notify_campaign", "BOOLEAN DEFAULT 1"),
        ("notify_new_place", "BOOLEAN DEFAULT 0"),
        ("avatar_url", "VARCHAR(500) DEFAULT ''"),
        ("email_verified", "BOOLEAN DEFAULT 0"),
        ("email_token", "VARCHAR(64) DEFAULT ''"),
        ("show_full_name", "BOOLEAN DEFAULT 0"),
        ("is_active", "BOOLEAN DEFAULT 1"),
        ("permissions_json", "TEXT DEFAULT '[]'"),
    )
    with engine.begin() as conn:
        existing = _table_cols(conn, "places")
        for col, typedef in place_cols:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE places ADD COLUMN {col} {typedef}"))
        uex = _table_cols(conn, "users")
        for col, typedef in user_cols:
            if col not in uex:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {typedef}"))
        cex = _table_cols(conn, "coupons")
        if cex and "owner_user_id" not in cex:
            conn.execute(text("ALTER TABLE coupons ADD COLUMN owner_user_id INTEGER"))
        rex = _table_cols(conn, "reviews")
        if rex and "status" not in rex:
            conn.execute(text("ALTER TABLE reviews ADD COLUMN status VARCHAR(16) DEFAULT 'approved'"))
            conn.execute(text("UPDATE reviews SET status='approved' WHERE status IS NULL OR status=''"))
        if rex and "img_url" not in rex:
            conn.execute(text("ALTER TABLE reviews ADD COLUMN img_url VARCHAR(500) DEFAULT ''"))
        pex = _table_cols(conn, "user_posts")
        if pex and "status" not in pex:
            conn.execute(text("ALTER TABLE user_posts ADD COLUMN status VARCHAR(16) DEFAULT 'approved'"))
            conn.execute(text("UPDATE user_posts SET status='approved' WHERE status IS NULL OR status=''"))
        vex = _table_cols(conn, "user_visits")
        if vex and "status" not in vex:
            conn.execute(text("ALTER TABLE user_visits ADD COLUMN status VARCHAR(16) DEFAULT 'approved'"))
            conn.execute(text("UPDATE user_visits SET status='approved' WHERE status IS NULL OR status=''"))
        clx = _table_cols(conn, "claim_requests")
        if clx and "tax_doc_url" not in clx:
            conn.execute(text("ALTER TABLE claim_requests ADD COLUMN tax_doc_url VARCHAR(500) DEFAULT ''"))
        if clx and "id_doc_url" not in clx:
            conn.execute(text("ALTER TABLE claim_requests ADD COLUMN id_doc_url VARCHAR(500) DEFAULT ''"))
        # admin hesabı e-posta doğrulanmış sayılsın
        conn.execute(text("UPDATE users SET email_verified=1 WHERE role='admin' AND (email_verified IS NULL OR email_verified=0)"))
        conn.execute(text("UPDATE users SET email_verified=1 WHERE role='editor' AND (email_verified IS NULL OR email_verified=0)"))
        conn.execute(text("UPDATE users SET is_active=1 WHERE is_active IS NULL"))


def place_extra(p: Place | None) -> dict:
    """Place.extra_json → dict (menu/gallery/services/fees/staff)."""
    if p is None:
        return {}
    raw = getattr(p, "extra_json", None) or "{}"
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def set_place_extra(p: Place, data: dict) -> None:
    p.extra_json = json.dumps(data or {}, ensure_ascii=False)


def merge_place_extra(p: Place, patch: dict) -> dict:
    cur = place_extra(p)
    cur.update(patch or {})
    set_place_extra(p, cur)
    return cur


def clamp_score(val, default: int = 5) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        return default
    return max(1, min(5, n))


def recompute_place_rating(db, place: Place) -> None:
    rows = db.query(Review).filter(Review.place_id == place.id, Review.status == "approved").all()
    if not rows:
        place.rating_avg = None
        place.rating_count = 0
        return
    total = sum(r.overall() for r in rows)
    place.rating_avg = round(total / len(rows), 2)
    place.rating_count = len(rows)


def review_dimension_avgs(db, place_id: int) -> dict:
    rows = db.query(Review).filter(Review.place_id == place_id, Review.status == "approved").all()
    if not rows:
        return {"food": None, "service": None, "atmosphere": None, "price": None, "count": 0}
    n = len(rows)
    return {
        "food": round(sum(r.score_food for r in rows) / n, 1),
        "service": round(sum(r.score_service for r in rows) / n, 1),
        "atmosphere": round(sum(r.score_atmosphere for r in rows) / n, 1),
        "price": round(sum(r.score_price for r in rows) / n, 1),
        "count": n,
    }


def init_db() -> None:
    os.makedirs(os.path.join(_DIR, "data"), exist_ok=True)
    Base.metadata.create_all(engine)
    _migrate_sqlite()
    db = SessionLocal()
    try:
        seed_admin(db)
        seed_places(db)
        db.commit()
    finally:
        db.close()


def seed_admin(db) -> None:
    from auth import hash_password

    email = (os.environ.get("BURSAAPP_ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("BURSAAPP_ADMIN_PASSWORD") or ""
    if not email or not password:
        return
    u = db.query(User).filter(User.email == email).first()
    if u is None:
        db.add(User(email=email, password_hash=hash_password(password), name="Admin", role="admin"))
        return
    if u.role != "admin":
        u.role = "admin"
    if not u.password_hash:
        u.password_hash = hash_password(password)


def _infer_category(row: dict) -> str:
    tags = row.get("tags") or []
    if "yemek" in tags:
        return "food"
    return "visit"


def seed_places(db) -> None:
    from catalog import tags_dump
    from zoneinfo import ZoneInfo

    if db.query(Place).count() > 0:
        return
    try:
        data = json.loads(open(SEED_JSON, encoding="utf-8").read())
    except Exception:
        data = {}
    for row in data.get("places") or []:
        slug = (row.get("id") or "").strip()
        title = (row.get("title") or "").strip()
        if not slug or not title:
            continue
        if db.query(Place).filter(Place.slug == slug).first():
            continue
        db.add(
            Place(
                title=title,
                slug=slug,
                category=_infer_category(row),
                ilce=row.get("ilce") or "",
                address=f"{row.get('ilce') or ''}, Bursa".strip(", "),
                hours_text=row.get("sure") or "",
                price_band=row.get("list_price") or "",
                blurb=row.get("blurb") or "",
                body=row.get("blurb") or "",
                img_url=row.get("img") or "",
                tags=tags_dump(row.get("tags") or []),
                rating_admin=float(row.get("rating") or 0) or None,
                featured=bool(row.get("featured")),
                status="approved",
            )
        )
    tz = ZoneInfo("Europe/Istanbul")
    now = datetime.now(tz)
    for ev in data.get("events") or []:
        day = int(ev.get("day") or 0)
        title = (ev.get("title") or "").strip()
        if not day or not title:
            continue
        try:
            starts = datetime(now.year, now.month, day, 10, 0)
        except ValueError:
            continue
        slug = f"etkinlik-{now.year}-{now.month:02d}-{day:02d}"
        if db.query(Place).filter(Place.slug == slug).first():
            continue
        db.add(
            Place(
                title=title,
                slug=slug,
                category="event",
                ilce="Osmangazi",
                address="Bursa",
                blurb=title,
                body=title,
                hours_text="10:00",
                featured=False,
                status="approved",
                starts_at=starts,
                ends_at=starts.replace(hour=18),
                tags=tags_dump(["etkinlik"]),
            )
        )


STAFF_ROLES = frozenset({"admin", "editor"})


def is_staff_role(role: str | None) -> bool:
    return (role or "").strip().lower() in STAFF_ROLES


def member_login_query(db):
    """Üye giriş kayıtları — admin/editör panel girişleri hariç."""
    from sqlalchemy import or_

    return (
        db.query(ActivityLog)
        .outerjoin(User, ActivityLog.user_id == User.id)
        .filter(
            ActivityLog.kind == "login",
            or_(User.id.is_(None), User.role.notin_(tuple(STAFF_ROLES))),
        )
    )


def log_activity(
    db,
    *,
    kind: str,
    title: str,
    detail: str = "",
    user_id: int | None = None,
    email: str = "",
    path: str = "",
    meta: dict | None = None,
    user_role: str | None = None,
) -> None:
    """Admin paneli aktivite kaydı — hata yutmaz."""
    if kind == "login" and is_staff_role(user_role):
        return
    try:
        from flask import request as _req

        ip = (_req.headers.get("X-Forwarded-For") or _req.remote_addr or "").split(",")[0].strip()
        path = path or (_req.path or "")
    except Exception:
        ip = ""
    try:
        db.add(
            ActivityLog(
                kind=(kind or "info")[:32],
                user_id=user_id,
                email=(email or "")[:190],
                title=(title or "")[:200],
                detail=(detail or "")[:500],
                ip=ip[:64],
                path=(path or "")[:200],
                meta_json=json.dumps(meta or {}, ensure_ascii=False),
            )
        )
        db.flush()
    except Exception:
        pass
