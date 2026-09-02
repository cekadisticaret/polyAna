"""1 günlük rota + otobüs/araç + kural tabanlı AI öneri."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from catalog import place_public, tags_load
from models import Place

_TZ = ZoneInfo("Europe/Istanbul")

# Bilinen Burulaş / yürüyüş ipuçları (yaklaşık — resmi hat değişebilir)
BUS_LEGS = {
    ("ulu-cami", "koza-han"): "Yürüyüş 3–5 dk · Hanlar içi",
    ("koza-han", "ulu-cami"): "Yürüyüş 3–5 dk",
    ("ulu-cami", "tophane"): "Yürüyüş ~10–15 dk · Hisar yokuşu / dolmuş",
    ("koza-han", "tophane"): "Yürüyüş ~12 dk · Hisar",
    ("tophane", "cumalikizik"): "Minibüs / 1F–2F hattı yönü · ~25–40 dk (timetable değişir)",
    ("ulu-cami", "cumalikizik"): "Heykel → Cumalıkızık minibüs · ~30–45 dk",
    ("cumalikizik", "ulu-cami"): "Dönüş minibüs Heykel · ~30–45 dk",
    ("tophane", "golyazi"): "Toplu taşımada uzun · otobüs+aktarma; mümkünse sabah erken",
    ("ulu-cami", "teleferik"): "Bursaray / otobüs Teferrüç · Teleferik hattı",
    ("teleferik", "uludag"): "Teleferik hat · bilet gişeden",
}


def _rating(p: Place) -> float:
    if p.rating_avg is not None:
        return float(p.rating_avg)
    if p.rating_admin is not None:
        return float(p.rating_admin)
    return 0.0


def _pick(rows: list[Place], *, exclude: set[int] | None = None) -> Place | None:
    exclude = exclude or set()
    ranked = sorted((p for p in rows if p.id not in exclude), key=_rating, reverse=True)
    return ranked[0] if ranked else None


def _meal_cost(p: Place | None, default: int) -> int:
    if p is None:
        return default
    if p.est_meal_tl and p.est_meal_tl > 0:
        return int(p.est_meal_tl)
    return default


def _bus_tip(a: Place | None, b: Place | None) -> str:
    if not a or not b:
        return ""
    key = (a.slug, b.slug)
    if key in BUS_LEGS:
        return BUS_LEGS[key]
    # aynı ilçe → yürüyüş / kısa otobüs
    if (a.ilce or "") and a.ilce == b.ilce:
        return f"Aynı ilçe ({a.ilce}) · yürüyüş veya kısa otobüs"
    return "Burulaş / minibüs · Google Maps toplu taşıma ile doğrula"


def _pack_slots(slots_spec: list, *, transport: str) -> list[dict]:
    slots = []
    prev = None
    est_total = 0
    for t, lab, pl, cost in slots_spec:
        if pl is None:
            continue
        est_total += cost
        d = place_public(pl)
        d["slot_time"] = t
        d["slot_label"] = lab
        d["slot_cost_tl"] = cost
        if transport == "bus" and prev is not None:
            tip = _bus_tip(prev, pl)
            d["transit_from_prev"] = tip
            d["transit_mode"] = "otobüs / yürüyüş"
        elif transport == "walk" and prev is not None:
            d["transit_from_prev"] = "Yürüyüş (mesafe uzunsa otobüse geç)"
            d["transit_mode"] = "yürüyüş"
        elif transport == "car" and prev is not None:
            d["transit_from_prev"] = "Araç / taksi"
            d["transit_mode"] = "araç"
        slots.append(d)
        prev = pl
    return slots, est_total


def build_day_route(
    db,
    *,
    budget_tl: int = 0,
    people: int = 2,
    quiet: bool = False,
    transport: str = "car",
    family: bool = False,
    romantic: bool = False,
    cheap: bool = False,
) -> dict:
    """Klasik Bursa 1 gün. transport: car|bus|walk."""
    transport = transport if transport in ("car", "bus", "walk") else "car"
    visit = db.query(Place).filter(Place.status == "approved", Place.category == "visit").all()
    food = db.query(Place).filter(Place.status == "approved", Place.category == "food").all()

    def by_slug(*slugs):
        for s in slugs:
            for p in visit:
                if p.slug == s:
                    return p
        return None

    used: set[int] = set()
    ulu = by_slug("ulu-cami") or _pick(visit, exclude=used)
    if ulu:
        used.add(ulu.id)
    koza = by_slug("koza-han") or _pick(visit, exclude=used)
    if koza:
        used.add(koza.id)
    isk = _pick(
        [p for p in food if (p.subcategory or "") == "iskender" or "iskender" in tags_load(p.tags)],
        exclude=used,
    )
    if not isk:
        isk = _pick(food, exclude=used)
    if isk:
        used.add(isk.id)
    tophane = by_slug("tophane") or _pick(visit, exclude=used)
    if tophane:
        used.add(tophane.id)

    # Otobüs/yürüyüşte Cumalıkızık yerine merkeze yakın alternatif (Muradiye / Yeşil)
    if transport in ("bus", "walk"):
        cumali = by_slug("muradiye", "yesil-turbe", "yesil-cami", "emir-sultan") or _pick(visit, exclude=used)
        village_label = "Yakın tarihî aks"
        village_cost = 0
    else:
        cumali = by_slug("cumalikizik") or _pick(
            [p for p in visit if "cumali" in (p.slug or "") or "koy" in tags_load(p.tags)],
            exclude=used,
        ) or _pick(visit, exclude=used)
        village_label = "Köy / doğa"
        village_cost = 50 * people
    if cumali:
        used.add(cumali.id)

    cafe = _pick([p for p in food if (p.subcategory or "") == "cafe"], exclude=used) or _pick(food, exclude=used)
    if cafe:
        used.add(cafe.id)
    dinner_pool = [p for p in food if (p.subcategory or "") not in ("cafe", "tatli", "pastane")]
    if quiet or romantic:
        dinner_pool = [
            p
            for p in dinner_pool
            if {"sakin", "manzarali", "aile", "romantik"} & {t.lower() for t in tags_load(p.tags)}
        ] or dinner_pool
    if family:
        dinner_pool = [
            p for p in dinner_pool if {"aile", "cocuk"} & {t.lower() for t in tags_load(p.tags)}
        ] or dinner_pool
    if cheap:
        dinner_pool = sorted(dinner_pool, key=lambda p: _meal_cost(p, 300))
    dinner = _pick(dinner_pool, exclude=used) or _pick(food, exclude=used)

    # Otobüs rotasında daha sıkı saat (aktarma payı)
    if transport == "bus":
        slots_spec = [
            ("10:00", "Gezilecek", ulu, 0),
            ("11:00", "Gezilecek", koza, 0),
            ("12:30", "Öğle yemeği", isk, _meal_cost(isk, 450) * people),
            ("14:15", "Gezilecek", tophane, 0),
            ("16:00", village_label, cumali, village_cost),
            ("18:15", "Cafe", cafe, _meal_cost(cafe, 150) * people),
            ("20:00", "Akşam yemeği", dinner, _meal_cost(dinner, 400) * people),
        ]
        title = "Bursa'da 1 gün · otobüs / yürüyüş"
    elif transport == "walk":
        slots_spec = [
            ("10:00", "Gezilecek", ulu, 0),
            ("11:00", "Gezilecek", koza, 0),
            ("12:30", "Öğle yemeği", isk, _meal_cost(isk, 450) * people),
            ("14:00", "Gezilecek", tophane, 0),
            ("16:00", village_label, cumali, village_cost),
            ("18:00", "Cafe", cafe, _meal_cost(cafe, 150) * people),
            ("20:00", "Akşam yemeği", dinner, _meal_cost(dinner, 400) * people),
        ]
        title = "Bursa'da 1 gün · yürüyüş ağırlıklı"
    else:
        slots_spec = [
            ("10:00", "Gezilecek", ulu, 0),
            ("11:00", "Gezilecek", koza, 0),
            ("12:30", "Öğle yemeği", isk, _meal_cost(isk, 450) * people),
            ("14:00", "Gezilecek", tophane, 0),
            ("15:30", village_label, cumali, village_cost),
            ("18:00", "Cafe", cafe, _meal_cost(cafe, 150) * people),
            ("20:00", "Akşam yemeği", dinner, _meal_cost(dinner, 400) * people),
        ]
        title = "Bursa'da 1 gün · araçlı"

    if budget_tl and budget_tl > 0:
        total = sum(c for *_, c in slots_spec)
        if total > budget_tl or cheap:
            cheap_food = sorted(food, key=lambda p: (_meal_cost(p, 300), -_rating(p)))
            for i, (t, lab, pl, cost) in enumerate(slots_spec):
                if lab in ("Öğle yemeği", "Akşam yemeği", "Cafe") and (total > budget_tl or cheap):
                    for alt in cheap_food:
                        if alt.id in used and alt.id != (pl.id if pl else -1):
                            continue
                        new_cost = _meal_cost(alt, 200) * people
                        if new_cost < cost:
                            if pl:
                                used.discard(pl.id)
                            used.add(alt.id)
                            slots_spec[i] = (t, lab, alt, new_cost)
                            total = sum(c for *_, c in slots_spec)
                            break

    slots, est_total = _pack_slots(slots_spec, transport=transport)
    tips = []
    if transport == "bus":
        tips.append("Burulaş kartı / QR bilet kullan. Cumalıkızık yerine merkez tarihî aks seçildi (aktarma az).")
        tips.append("Hat numaraları değişebilir — Maps’te “toplu taşıma” ile doğrula.")
    elif transport == "walk":
        tips.append("Rahat ayakkabı · öğlen gölge / su.")
    if family:
        tips.append("Çocuklu tempo: öğle sonrası kısa mola.")

    return {
        "title": title,
        "people": people,
        "budget_tl": budget_tl or None,
        "est_total_tl": est_total,
        "within_budget": (not budget_tl) or est_total <= budget_tl,
        "slots": slots,
        "transport": transport,
        "tips": tips,
    }


def _nature_route(db, *, people: int, budget: int, transport: str) -> dict:
    visit = db.query(Place).filter(Place.status == "approved", Place.category == "visit").all()
    food = db.query(Place).filter(Place.status == "approved", Place.category == "food").all()
    used: set[int] = set()

    def find(*keys):
        for p in visit + food:
            blob = f"{p.slug} {p.title} {p.tags}".lower()
            if any(k in blob for k in keys) and p.id not in used:
                return p
        return None

    # Arabasız: gölyazı zor → botanik / misi yerine yeşil-emir sultan
    if transport in ("bus", "walk"):
        first = find("soganli", "botanik", "misi") or _pick(visit, exclude=used)
        if first:
            used.add(first.id)
        kahvalti = _pick(
            [p for p in food if (p.subcategory or "") in ("kahvalti", "cafe")], exclude=used
        ) or _pick(food, exclude=used)
        if kahvalti:
            used.add(kahvalti.id)
        second = find("misi", "golyazi") or _pick(visit, exclude=used)
        if second:
            used.add(second.id)
        title = "Doğa / sakin · toplu taşıma uyumlu"
    else:
        first = find("golyazi", "gölyazı") or _pick(visit, exclude=used)
        if first:
            used.add(first.id)
        kahvalti = _pick(
            [p for p in food if (p.subcategory or "") in ("kahvalti", "cafe")], exclude=used
        ) or _pick(food, exclude=used)
        if kahvalti:
            used.add(kahvalti.id)
        second = find("misi") or _pick(visit, exclude=used)
        if second:
            used.add(second.id)
        title = "Doğa / sakin rota"

    cafe = _pick([p for p in food if (p.subcategory or "") == "cafe"], exclude=used)
    if cafe:
        used.add(cafe.id)
    dinner = _pick(food, exclude=used)
    slots_raw = [
        ("10:00", "Doğa", first, 0),
        ("12:30", "Kahvaltı / öğle", kahvalti, _meal_cost(kahvalti, 250) * people),
        ("15:00", "Köy / park", second, 0),
        ("17:30", "Cafe", cafe, _meal_cost(cafe, 150) * people),
        ("20:00", "Akşam yemeği", dinner, _meal_cost(dinner, 350) * people),
    ]
    slots, total = _pack_slots(slots_raw, transport=transport)
    if budget and total > budget:
        return build_day_route(db, budget_tl=budget, people=people, quiet=True, transport=transport)
    return {
        "title": title,
        "people": people,
        "budget_tl": budget or None,
        "est_total_tl": total,
        "within_budget": (not budget) or total <= budget,
        "slots": slots,
        "transport": transport,
        "tips": ["Sakin tempo · gün batımı için erken çık."] if transport == "car" else [
            "Gölyazı arabasız zor olabilir — Botanik/Misi tercih edildi."
        ],
    }


def _tonight_events(db) -> list[dict]:
    now = datetime.now(_TZ)
    end = now + timedelta(hours=36)
    rows = (
        db.query(Place)
        .filter(
            Place.status == "approved",
            Place.category.in_(("concert", "event", "theater")),
            Place.starts_at != None,  # noqa: E711
            Place.starts_at >= now.replace(tzinfo=None),
            Place.starts_at <= end.replace(tzinfo=None),
        )
        .order_by(Place.starts_at.asc())
        .limit(5)
        .all()
    )
    out = []
    for p in rows:
        d = place_public(p)
        d["slot_time"] = p.starts_at.strftime("%H:%M") if p.starts_at else ""
        d["slot_label"] = "Etkinlik"
        d["slot_cost_tl"] = 0
        out.append(d)
    return out


def ai_suggest(db, prompt: str) -> dict:
    """Anahtar kelime + niyet → gerçek mekanlarla rota (LLM değil, çalışır kural seti)."""
    text = (prompt or "").lower().strip()
    if not text:
        return {
            "title": "BursaApp AI",
            "people": 2,
            "est_total_tl": 0,
            "slots": [],
            "tips": ["Ne istediğini yaz: kişi, bütçe, araç var mı, sakin/aile/tarih…"],
            "prompt": prompt,
        }

    people = 2
    m = re.search(r"(\d+)\s*kişi", text)
    if m:
        people = max(1, min(int(m.group(1)), 8))
    budget = 0
    m = re.search(r"(\d[\d\.]*)\s*(tl|₺)", text)
    if m:
        budget = int(m.group(1).replace(".", ""))

    quiet = any(w in text for w in ("sakin", "huzur", "sessiz", "doğal", "doga", "doğa"))
    family = any(w in text for w in ("aile", "çocuk", "cocuk", "bebek"))
    romantic = any(w in text for w in ("romantik", "sevgili", "çift", "cift", "balayı"))
    cheap = any(w in text for w in ("ucuz", "ekonomik", "öğrenci", "ogrenci", "az bütçe"))
    luxury = any(w in text for w in ("lüks", "luks", "premium", "fine"))
    historic = any(w in text for w in ("tarih", "han", "cami", "unesco", "müze", "muze"))
    foodie = any(w in text for w in ("yemek", "iskender", "kebap", "lezzet", "aç", "ac"))
    night = any(w in text for w in ("akşam", "aksam", "gece", "bu akşam", "konser", "etkinlik"))
    rain = any(w in text for w in ("yağmur", "yagmurlu", "ıslak", "kapalı hava"))

    # ulaşım
    no_car = any(
        w in text
        for w in (
            "araba yok",
            "araç yok",
            "arac yok",
            "otomobil yok",
            "otobüs",
            "otobus",
            "toplu",
            "metro",
            "bursaray",
            "yürüyerek",
            "yuruyerek",
        )
    )
    has_car = any(w in text for w in ("araba", "araç", "arac", "otomobil", "arabamız", "arabamiz")) and not no_car
    if no_car:
        transport = "bus"
    elif has_car:
        transport = "car"
    elif "yürü" in text or "walk" in text:
        transport = "walk"
    else:
        transport = "bus"  # varsayılan: arabasız varsay (şehir içi)

    # Bu akşam etkinlik
    if night and any(w in text for w in ("konser", "tiyatro", "etkinlik", "ne var", "bu akşam", "bu aksam")):
        evs = _tonight_events(db)
        if evs:
            return {
                "title": "Yaklaşan etkinlikler",
                "people": people,
                "budget_tl": budget or None,
                "est_total_tl": 0,
                "within_budget": True,
                "slots": evs,
                "transport": transport,
                "tips": ["Bilet BursaApp’ten satılmaz — linkten al.", "Kapıdan 30 dk önce ol."],
                "prompt": prompt,
            }

    # Yağmur → kapalı mekan (han, müze, cafe)
    if rain:
        visit = db.query(Place).filter(Place.status == "approved", Place.category == "visit").all()
        food = db.query(Place).filter(Place.status == "approved", Place.category == "food").all()
        used: set[int] = set()
        koza = next((p for p in visit if p.slug == "koza-han"), None) or _pick(visit)
        if koza:
            used.add(koza.id)
        muze = next((p for p in visit if "panorama" in (p.slug or "") or "muze" in tags_load(p.tags)), None)
        if muze:
            used.add(muze.id)
        cafe = _pick([p for p in food if (p.subcategory or "") == "cafe"], exclude=used)
        dinner = _pick(food, exclude=used)
        slots_raw = [
            ("11:00", "Han / kapalı", koza, 0),
            ("13:00", "Müze", muze, 80 * people),
            ("15:30", "Cafe", cafe, _meal_cost(cafe, 150) * people),
            ("19:30", "Akşam", dinner, _meal_cost(dinner, 400) * people),
        ]
        slots, total = _pack_slots(slots_raw, transport=transport)
        return {
            "title": "Yağmurlu gün planı",
            "people": people,
            "budget_tl": budget or None,
            "est_total_tl": total,
            "within_budget": (not budget) or total <= budget,
            "slots": slots,
            "transport": transport,
            "tips": ["Kapalı mekan ağırlıklı.", "Şemsiye + kaygan taş."],
            "prompt": prompt,
        }

    # Doğa / göl
    if any(w in text for w in ("göl", "golyazi", "gölyazı", "misi", "uludağ", "uludag")) or (quiet and has_car):
        route = _nature_route(db, people=people, budget=budget, transport=transport)
        route["prompt"] = prompt
        route["title"] = "BursaApp AI · doğa"
        return route

    # Klasik / tarih / yemek — varsayılan
    route = build_day_route(
        db,
        budget_tl=budget,
        people=people,
        quiet=quiet,
        transport=transport,
        family=family,
        romantic=romantic,
        cheap=cheap or (budget > 0 and budget < 1200),
    )
    intents = []
    if transport == "bus":
        intents.append("otobüs")
    if family:
        intents.append("aile")
    if romantic:
        intents.append("romantik")
    if cheap:
        intents.append("ekonomik")
    if quiet:
        intents.append("sakin")
    if historic:
        intents.append("tarih")
    if foodie:
        intents.append("yemek")
    route["title"] = f"BursaApp AI · {', '.join(intents)}" if intents else "BursaApp AI önerisi"
    route["prompt"] = prompt
    route.setdefault("tips", [])
    route["tips"] = list(route.get("tips") or []) + [
        "Ulu Cami ve Koza Han merkez — yürüyüş mesafesi.",
        f"Anladığım: {people} kişi"
        + (f", ~{budget} TL" if budget else "")
        + f", ulaşım={transport}",
    ]
    return route