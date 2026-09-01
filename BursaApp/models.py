"""SQLAlchemy User + Place. SQLite BursaApp/data/bursaapp.db."""
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
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_DIR, "data", "bursaapp.db")
SEED_JSON = os.path.join(_DIR, "data", "places.json")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    places: Mapped[list["Place"]] = relationship("Place", back_populates="submitter", foreign_keys="Place.submitted_by_id")

    def public(self) -> dict:
        return {"id": self.id, "email": self.email, "name": self.name, "role": self.role}


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(90), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
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

    submitter: Mapped[User | None] = relationship("User", foreign_keys=[submitted_by_id], back_populates="places")
    reviewer: Mapped[User | None] = relationship("User", foreign_keys=[reviewed_by_id])


engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    os.makedirs(os.path.join(_DIR, "data"), exist_ok=True)
    Base.metadata.create_all(engine)
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
