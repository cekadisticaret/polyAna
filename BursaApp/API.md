# BursaApp API v1

Taban: `https://bursaapp.com/api/v1`  
Hata: `{ "ok": false, "error": "..." }`  
Sayfalama: `limit` (max 100) · `offset`  
Auth: cookie `bursaapp_session` **veya** `Authorization: Bearer <jwt>`

## Public (onaylı)

`GET /categories`  
`GET /places?category=food|visit|hotel|camp|concert|theater|cinema|fun|event|org|hospital|doctor|vet&ilce=&spec=&q=&from=&to=`  
`spec` = doktor branşı (Kalp, Göz…) veya konser türü. Doktor kaydında `venue_name` = hastane slug.
`GET /places/<slug>`  
`GET /events?from=&to=`  
Tarihli kayıt: `theater` / `concert` / `cinema` / `event` · `starts_at` · Keşfet takvimi bunları birleştirir.

Yalnız `status=approved`. Yayınlanmayan kayıt dönmez.

## Üye

`POST /auth/register` `{email,password,name}` → `{user, token}`  
`POST /auth/login` `{email,password}` → `{user, token}`  
`POST /places` taslak (`pending`). Etkinlikte `starts_at` zorunlu.  
`GET /me/places`

Place gövdesi: `title, category, ilce, address, lat, lng, phone, web, hours_text, price_band, blurb, body, img_url, tags, starts_at, ends_at, venue_name`

## Admin (`role=admin`)

`GET /admin/queue?status=pending|approved|rejected|all`  
`POST /admin/places/<id>/approve`  
`POST /admin/places/<id>/reject` `{reason}`  
`PATCH /admin/places/<id>`

Kayıt / ekle: IP başına dakikada 5.
