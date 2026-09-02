# BursaApp API v1

Taban: `https://bursaapp.com/api/v1`  
Hata: `{ "ok": false, "error": "..." }`  
Auth: cookie `bursaapp_session` **veya** `Authorization: Bearer <jwt>`

## Public

`GET /categories` · `GET /places` (`category`,`ilce`,`sub`,`q`,`from`,`to`)  
`GET /places/<slug>` · `GET /places/<slug>/reviews`  
`GET /events`  
`GET /discover/today|tonight|nearby|weekend`  
`GET /map` — koordinatlı mekanlar  
`GET /route?budget=&people=` — 1 günlük rota  
`POST /ai` `{prompt}` — kural tabanlı AI rota (gerçek mekanlar)

## HTML keşif (aynı sunucu)

`/` hub · `/bugun` `/bu-aksam` `/yakinimda` `/hafta-sonu`  
`/rota` `/ai` `/harita` `/kampanyalar` `/kuponlar` `/oneriyor`  
`/bursa-da-ne-yenir` · `/bursa-iskender` …  
`/ilce/<slug>` · `/bursa-restoranlari` · `/nilufer-restoranlari`  
`/premium` · `/etkinlik/ekle` · `/isletme`

## Üye

`POST /places/<slug>/reviews` · favori HTML `POST /favori/<slug>`  
Sahiplenme `POST /yer/<slug>/sahiplen` · bildirim `/hesap/bildirimler`

## Admin

`/admin` kuyruk · `/admin/dashboard` KPI · `/admin/claims` sahiplenme  
Kampanya/ödeme stub — gerçek tahsilat yok.
