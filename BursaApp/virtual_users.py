"""Sanal topluluk üyeleri — feed/ziyaret/beğeni üretimi."""
from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta

from auth import hash_password
from feed_social import EVENT_CATS, set_post_images
from sqlalchemy import or_
from models import (
    EventGoing,
    Favorite,
    Place,
    PostLike,
    Review,
    User,
    UserPost,
    UserVisit,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
PERSONAS_PATH = os.path.join(_DIR, "data", "virtual_users.json")
AVATAR_DIR = os.path.join(_DIR, "static", "virtual", "avatars")
STATE_PATH = os.path.join(_DIR, "data", "virtual_users_state.json")

SANAL_EMAIL_SUFFIX = ".sanal@bursaapp.com"  # eski kayıtlar — migrate edilir
DEFAULT_PASSWORD = os.environ.get("BURSAAPP_VIRTUAL_PASS") or "BursaAppSanal2026!"

POST_TEMPLATES: dict[str, list[str]] = {
    "cozy": [
        "{place} tam hafta sonu kaçamağıydı ☀️",
        "Bugün {place} — huzur dolu bir gün",
        "{place} fotoğrafları için birikmiştim, paylaşıyorum",
        "Bursa'da böyle köşeler keşfetmek güzel · {place}",
    ],
    "culture": [
        "{place} mutlaka görülmeli — tarih kokuyor",
        "Müze günü: {place} · rehber notlarım ayrı yazıda",
        "{place} ziyaretimden kısa not: erken gidin, kalabalık oluyor",
        "Bursa'nın tarih rotasında {place} duraklarından biri",
    ],
    "adventure": [
        "{place} kamp için harika — sabah sis manzarası 🔥",
        "Gece {place} · yıldızlar inanılmazdı",
        "Karavan rotamızda {place} — tavsiye ederim",
        "{place} — doğa sesleri + temiz hava",
    ],
    "foodie": [
        "{place} denedim, gerçekten iyi 👌",
        "Brunch için {place} · manzara da bonus",
        "Arkadaşlarla {place} — fiyat/performans tam yerinde",
        "Bursa lezzet rotası: {place} ✓",
    ],
    "family": [
        "Çocuklarla {place} — keyifli bir gün",
        "Aile rotası: {place} · park alanı geniş",
        "Pazar gezisi {place} · herkes mutlu döndük",
        "{place} aileler için uygun, tavsiye",
    ],
    "hike": [
        "{place} yürüyüş rotası zorlayıcı ama değer",
        "Uludağ tarafında {place} — nefes kesici",
        "{place} şelalesi bu mevsimde harika",
        "Doğa yürüyüşü: {place} · 2 saat sürdü",
    ],
    "casual": [
        "{place} mola vermek için ideal",
        "Motor rotasında {place} — manzara süper",
        "Kısa gezi: {place} · foto çektim",
        "{place} — Bursa'da favori duraklarımdan",
    ],
    "photo": [
        "{place} gün batımı için mükemmel 📷",
        "Golden hour · {place}",
        "Gölyazı tarafında {place} — kareler birikti",
        "{place} fotoğraf turu tamamlandı",
    ],
    "events": [
        "{place} etkinliğine gidiyorum — kimler var?",
        "Bu hafta sonu {place} · biletler alındı",
        "{place} için heyecanlıyım 🎭",
        "Bursa kültür takvimi: {place}",
    ],
}

VISIT_NOTES: dict[str, list[str]] = {
    "cozy": ["Harika bir gün geçirdim", "Tekrar gelirim", "Sakin ve güzel"],
    "culture": ["Rehberli tur aldım", "Tarih sevenlere tavsiye", "2 saat ayırın"],
    "adventure": ["Kamp için uygun", "Gece soğuk, hazırlıklı gidin", "Manzara efsane"],
    "foodie": ["Lezzetli", "Servis iyiydi", "Tekrar geliriz"],
    "family": ["Çocuklar sevdi", "Park alanı geniş", "Aile dostu"],
    "hike": ["Yürüyüş orta zor", "Su götürün", "Manzara değdi"],
    "casual": ["Güzel mola", "Tavsiye", "Kısa ziyaret yeterli"],
    "photo": ["Fotoğraf için ideal", "Gün batımı süper", "Tripod getirin"],
    "events": ["Etkinlik güzeldi", "Tekrar gelirim", "Organizasyon iyiydi"],
}

REVIEW_TEMPLATES: dict[str, list[str]] = {
    "foodie": [
        "Lezzet ve ortam dengesi iyi. {place} için tekrar geliriz.",
        "Servis hızlı, porsiyon doyurucu. {place} tavsiye.",
        "Fiyat performans tam yerinde — {place}.",
    ],
    "family": [
        "Ailece rahat ettik. {place} çocuklu gruplar için uygun.",
        "Menü çeşitli, personel ilgili. {place} güzel.",
    ],
    "casual": [
        "{place} — beklediğimden iyiydi.",
        "Arkadaşlarla gittik, memnun kaldık.",
    ],
}


def load_personas() -> list[dict]:
    with open(PERSONAS_PATH, encoding="utf-8") as f:
        return json.load(f)


def virtual_persona_emails() -> set[str]:
    return {p["email"].lower() for p in load_personas()}


def legacy_sanal_email(slug: str) -> str:
    return f"{slug}.sanal@bursaapp.com"


def is_sanal_email(email: str) -> bool:
    em = (email or "").lower()
    if em.endswith(SANAL_EMAIL_SUFFIX):
        return True
    return em in virtual_persona_emails()


def migrate_legacy_sanal_emails(db) -> int:
    """Eski emre.sanal@… adreslerini gerçekçi e-postaya taşır."""
    moved = 0
    for p in load_personas():
        old = legacy_sanal_email(p["slug"])
        new = p["email"].lower()
        u = db.query(User).filter(User.email == old).first()
        if not u:
            continue
        clash = db.query(User).filter(User.email == new, User.id != u.id).first()
        if clash:
            continue
        u.email = new
        moved += 1
    return moved


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "BA"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def ensure_avatar(slug: str, name: str, color: str) -> str:
    os.makedirs(AVATAR_DIR, exist_ok=True)
    rel = f"/static/virtual/avatars/{slug}.svg"
    path = os.path.join(AVATAR_DIR, f"{slug}.svg")
    if os.path.isfile(path):
        return rel
    initials = _initials(name)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="64" fill="{color}"/>
  <text x="64" y="72" text-anchor="middle" font-family="system-ui,sans-serif" font-size="42" font-weight="700" fill="#fff">{initials}</text>
</svg>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return rel


def _load_state() -> dict:
    if not os.path.isfile(STATE_PATH):
        return {"last_tick": None, "actions": 0}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_tick": None, "actions": 0}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_virtual_users(db) -> list[User]:
    emails = list(virtual_persona_emails())
    legacy = [legacy_sanal_email(p["slug"]) for p in load_personas()]
    return (
        db.query(User)
        .filter(or_(User.email.in_(emails), User.email.in_(legacy)))
        .order_by(User.id.asc())
        .all()
    )


def persona_for_user(user: User, personas: list[dict] | None = None) -> dict | None:
    personas = personas or load_personas()
    em = (user.email or "").lower()
    for p in personas:
        if p["email"].lower() == em:
            return p
        if legacy_sanal_email(p["slug"]) == em:
            return p
    return None


def seed_virtual_users(db, *, bootstrap_posts: int = 2) -> dict:
    """10 sanal üyeyi oluştur/güncelle; ilk gönderileri ekle."""
    personas = load_personas()
    migrated = migrate_legacy_sanal_emails(db)
    created = updated = 0
    posts = visits = 0
    pw = hash_password(DEFAULT_PASSWORD)

    for p in personas:
        avatar = ensure_avatar(p["slug"], p["name"], p.get("avatar_color") or "#1a5c45")
        u = db.query(User).filter(User.email == p["email"]).first()
        if not u:
            u = db.query(User).filter(User.email == legacy_sanal_email(p["slug"])).first()
        if u:
            u.email = p["email"]
            u.name = p["name"]
            u.email_verified = True
            u.email_token = ""
            u.avatar_url = avatar
            u.show_full_name = True
            updated += 1
        else:
            u = User(
                email=p["email"],
                password_hash=pw,
                name=p["name"],
                role="user",
                email_verified=True,
                email_token="",
                avatar_url=avatar,
                show_full_name=True,
            )
            db.add(u)
            db.flush()
            created += 1

    db.commit()

    for u in get_virtual_users(db):
        p = persona_for_user(u, personas)
        if not p:
            continue
        for _ in range(bootstrap_posts):
            if _post_for_user(db, u, p):
                posts += 1
            if random.random() < 0.6 and _visit_for_user(db, u, p):
                visits += 1

    # sanal üyeler birbirini beğensin
    _cross_like_recent(db, limit=12)

    return {"created": created, "updated": updated, "migrated": migrated, "posts": posts, "visits": visits}


def _places_for_persona(db, persona: dict, *, limit: int = 80) -> list[Place]:
    cats = persona.get("cats") or ["visit"]
    q = db.query(Place).filter(Place.status == "approved", Place.category.in_(cats))
    rows = q.order_by(Place.featured.desc(), Place.rating_count.desc(), Place.id.desc()).limit(limit * 3).all()
    if not rows:
        rows = (
            db.query(Place)
            .filter(Place.status == "approved", Place.category.in_(("visit", "camp", "food")))
            .limit(limit)
            .all()
        )
    random.shuffle(rows)
    return rows[:limit]


def _pick_place(db, persona: dict, user_id: int, *, exclude_visited: bool = False) -> Place | None:
    candidates = _places_for_persona(db, persona)
    if exclude_visited:
        visited = {
            v.place_id
            for v in db.query(UserVisit.place_id).filter(UserVisit.user_id == user_id).all()
        }
        candidates = [p for p in candidates if p.id not in visited]
    return random.choice(candidates) if candidates else None


def _render_body(templates: list[str], place: Place) -> str:
    title = (place.title or "Bursa").strip()
    if len(title) > 48:
        title = title[:45] + "…"
    tpl = random.choice(templates)
    return tpl.format(place=title)


def _post_for_user(db, user: User, persona: dict) -> bool:
    place = _pick_place(db, persona, user.id)
    if not place:
        return False
    tone = persona.get("tone") or "casual"
    templates = POST_TEMPLATES.get(tone) or POST_TEMPLATES["casual"]
    body = _render_body(templates, place)
    imgs: list[str] = []
    if place.img_url and random.random() < 0.55:
        imgs = [place.img_url]
    post = UserPost(
        user_id=user.id,
        place_id=place.id,
        body=body,
        privacy="public",
        status="approved",
        created_at=datetime.utcnow() - timedelta(minutes=random.randint(1, 180)),
    )
    set_post_images(post, imgs)
    db.add(post)
    db.commit()
    return True


def _visit_for_user(db, user: User, persona: dict) -> bool:
    place = _pick_place(db, persona, user.id, exclude_visited=True)
    if not place:
        place = _pick_place(db, persona, user.id)
    if not place:
        return False
    return _ensure_visit(db, user.id, place, persona)


def _ensure_visit(db, user_id: int, place: Place, persona: dict) -> bool:
    tone = persona.get("tone") or "casual"
    notes = VISIT_NOTES.get(tone) or VISIT_NOTES["casual"]
    note = random.choice(notes)
    existing = (
        db.query(UserVisit)
        .filter(UserVisit.user_id == user_id, UserVisit.place_id == place.id)
        .first()
    )
    if existing:
        existing.note = note
        existing.status = "approved"
        existing.created_at = datetime.utcnow() - timedelta(minutes=random.randint(5, 240))
        db.commit()
        return False
    db.add(
        UserVisit(
            user_id=user_id,
            place_id=place.id,
            note=note,
            status="approved",
            created_at=datetime.utcnow() - timedelta(minutes=random.randint(5, 240)),
        )
    )
    db.commit()
    return True


def _like_for_user(db, user: User) -> bool:
    posts = (
        db.query(UserPost)
        .filter(UserPost.user_id != user.id, UserPost.privacy == "public")
        .order_by(UserPost.id.desc())
        .limit(40)
        .all()
    )
    if not posts:
        return False
    post = random.choice(posts)
    exists = (
        db.query(PostLike)
        .filter(PostLike.user_id == user.id, PostLike.post_id == post.id)
        .first()
    )
    if exists:
        return False
    db.add(PostLike(user_id=user.id, post_id=post.id))
    post.likes_count = int(post.likes_count or 0) + 1
    db.commit()
    return True


def _going_for_user(db, user: User, persona: dict) -> bool:
    cats = [c for c in (persona.get("cats") or []) if c in EVENT_CATS] or list(EVENT_CATS)
    now = datetime.utcnow()
    events = (
        db.query(Place)
        .filter(
            Place.status == "approved",
            Place.category.in_(cats),
        )
        .order_by(Place.starts_at.desc().nullslast(), Place.id.desc())
        .limit(30)
        .all()
    )
    events = [e for e in events if not e.ends_at or e.ends_at >= now - timedelta(days=1)]
    if not events:
        return False
    place = random.choice(events)
    exists = (
        db.query(EventGoing)
        .filter(EventGoing.user_id == user.id, EventGoing.place_id == place.id)
        .first()
    )
    if exists:
        return False
    db.add(EventGoing(user_id=user.id, place_id=place.id))
    db.commit()
    return True


def _review_for_user(db, user: User, persona: dict) -> bool:
    if "food" not in (persona.get("cats") or []):
        return False
    tone = persona.get("tone") or "foodie"
    templates = REVIEW_TEMPLATES.get(tone) or REVIEW_TEMPLATES["foodie"]
    place = (
        db.query(Place)
        .filter(Place.status == "approved", Place.category == "food")
        .order_by(Place.rating_count.desc(), Place.id.desc())
        .offset(random.randint(0, 20))
        .first()
    )
    if not place:
        return False
    exists = db.query(Review).filter(Review.user_id == user.id, Review.place_id == place.id).first()
    if exists:
        return False
    body = _render_body(templates, place)
    scores = {
        "score_food": random.randint(4, 5),
        "score_service": random.randint(3, 5),
        "score_atmosphere": random.randint(4, 5),
        "score_price": random.randint(3, 5),
    }
    db.add(
        Review(
            user_id=user.id,
            place_id=place.id,
            body=body,
            status="approved",
            **scores,
        )
    )
    db.commit()
    return True


def _favorite_for_user(db, user: User, persona: dict) -> bool:
    place = _pick_place(db, persona, user.id)
    if not place:
        return False
    exists = (
        db.query(Favorite)
        .filter(Favorite.user_id == user.id, Favorite.place_id == place.id)
        .first()
    )
    if exists:
        return False
    db.add(Favorite(user_id=user.id, place_id=place.id))
    place.fav_count = int(place.fav_count or 0) + 1
    db.commit()
    return True


def _cross_like_recent(db, limit: int = 8) -> None:
    users = get_virtual_users(db)
    if len(users) < 2:
        return
    posts = db.query(UserPost).filter(UserPost.privacy == "public").order_by(UserPost.id.desc()).limit(limit).all()
    for post in posts:
        candidates = [u for u in users if u.id != post.user_id]
        if not candidates:
            continue
        liker = random.choice(candidates)
        exists = (
            db.query(PostLike)
            .filter(PostLike.user_id == liker.id, PostLike.post_id == post.id)
            .first()
        )
        if exists:
            continue
        db.add(PostLike(user_id=liker.id, post_id=post.id))
        post.likes_count = int(post.likes_count or 0) + 1
    db.commit()


def run_activity(db, *, max_actions: int = 3) -> dict:
    """Cron tick — rastgele sanal aktivite."""
    users = get_virtual_users(db)
    if not users:
        return {"ok": False, "reason": "no_virtual_users", "done": 0}

    personas = {p["email"].lower(): p for p in load_personas()}
    weights = [
        ("post", 0.48),
        ("visit", 0.22),
        ("like", 0.14),
        ("going", 0.06),
        ("review", 0.05),
        ("favorite", 0.05),
    ]
    actions = ["post"] * max_actions
    # gerçekçi: her tick'te 1-3 aksiyon, ağırlıklı
    n = random.randint(1, max_actions)
    actions = []
    for _ in range(n):
        r = random.random()
        acc = 0.0
        for name, w in weights:
            acc += w
            if r <= acc:
                actions.append(name)
                break

    done: dict[str, int] = {}
    for act in actions:
        user = random.choice(users)
        persona = personas.get((user.email or "").lower())
        if not persona:
            continue
        ok = False
        if act == "post":
            ok = _post_for_user(db, user, persona)
        elif act == "visit":
            ok = _visit_for_user(db, user, persona)
        elif act == "like":
            ok = _like_for_user(db, user)
        elif act == "going":
            ok = _going_for_user(db, user, persona)
        elif act == "review":
            ok = _review_for_user(db, user, persona)
        elif act == "favorite":
            ok = _favorite_for_user(db, user, persona)
        if ok:
            done[act] = done.get(act, 0) + 1

    state = _load_state()
    state["last_tick"] = datetime.utcnow().isoformat()
    state["actions"] = int(state.get("actions") or 0) + sum(done.values())
    _save_state(state)
    return {"ok": True, "done": done, "total": sum(done.values())}


def stats(db) -> dict:
    users = get_virtual_users(db)
    uids = [u.id for u in users]
    if not uids:
        return {"users": 0}
    posts = db.query(UserPost).filter(UserPost.user_id.in_(uids)).count()
    visits = db.query(UserVisit).filter(UserVisit.user_id.in_(uids)).count()
    likes = db.query(PostLike).filter(PostLike.user_id.in_(uids)).count()
    reviews = db.query(Review).filter(Review.user_id.in_(uids)).count()
    state = _load_state()
    return {
        "users": len(users),
        "posts": posts,
        "visits": visits,
        "likes": likes,
        "reviews": reviews,
        "last_tick": state.get("last_tick"),
        "total_actions": state.get("actions"),
        "female": sum(1 for u in users if persona_for_user(u) and persona_for_user(u).get("gender") == "f"),
        "male": sum(1 for u in users if persona_for_user(u) and persona_for_user(u).get("gender") == "m"),
    }
