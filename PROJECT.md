# aiProject — Proje Yapısı

## Genel Bakış
BIST Telegram betikleri `BistAnaliz/` altında. Ortak motor: `BistAnaliz/bist_scanner.py`. Gizli ayar proje kökünde: `telegram_config.py` (şablon: `BistAnaliz/telegram_config.example.py`).

| Klasör | Açıklama |
|---|---|
| `BistAnaliz/` | `bist_scanner.py`, `backup.py`, Telegram şablonu; alt klasörlerde saatlik ve güçlü AL betikleri. |
| `BistAnaliz/BistHourSinyal/` | `bist_visual_v2.py` — trend + momentum metin bildirimi. |
| `BistAnaliz/BistYapayAnaliz/` | `bist_signal_hunter.py` — 15m/1h güçlü AL; geçmiş: `bist_signal_hunter_history.json`. |
| `BistAnaliz/yuzdeBist.py` | BIST 5dk güven tarayıcı — **PASIF** (crontab yorum satırı). |
| `temmuzPoly/chart_algo_overlay.py` | Grafik overlay — 5M110Analiz EMA/composite/sinyal serileri (110/111). |
| `temmuzPoly/chart_multi_confirm_signals.py` | Grafik MC teyit — pattern+hacim+seviye+momentum (Pine portu; rozet, oklar kapalı). |
| `temmuzPoly/chart_signal_accuracy.py` | Grafik MC/YT/TAHMİN/TAHMİN2 saatlik WR takibi + pill’lerde gösterim |
| `temmuzPoly/chart_tahmin2_signals.py` | Grafik TAHMİN2 — LM+ST+ADX+LZ+CVD oylaması (TAHMİN yanında). |
| `temmuzPoly/weekly_slot_heatmap_all.py` | Son 7g saatlik slot ısı haritası → A15/A4 TG; cron her gece 00:00 İST |
| `temmuzPoly/slot_data_archive.py` | Saatlik slot arşivi → `temmuzPoly/slot_data/` (latest/daily/hourly/events) |
| `temmuzPoly/hourly_path_log.py` | BTC/ETH/SOL saatlik dakika yolu · referans=1h açılış · **WS** (`binance_ws_marks` → `apply_prices`) · `backfill N` · `/saatlik-yol` · emir yok |
| `temmuzPoly/chart_hourly_signals.py` | Grafik overlay — 1. Analiz (A1) saatlik UP/DOWN okları. |
| `temmuzPoly/a3a8_signal_mode.py` | A3/A8 sıkı (filtreli) vs gevşek mod (`a3a8_signal_strict`; sıkı=entry/kesişim veya momentum+RSI teyit) |
| `temmuzPoly/chart_algo_panel.py` | Grafik ALG1/ALG2 — 5m/15m konsensüs + slot WR takibi (`update_wr` cron */5). |
| `ALGO3/` | F1 motorları — HMM · MVRV · SOPR · OI · KAMA · Chandelier · Funding |
| `temmuzPoly/f1_signal.py` | ALGO3 → UP/DOWN · `/tmp/f1_signals.json` · `:01` + `:04:40` |
| `temmuzPoly/poly_trader_f1.py` | **F1-01…07** sanal ($1000 · $24/36/48) · `live_mirror=False` · `:01` close / `:02` open |
| `Sonnet/candle_pattern_engine1.py` | Mum pattern + S/D + confluence + `generate_report()` (grafik raporu) |
| `Sonnet/candle_pattern_engine.py` | v1 motor (yedek; grafik engine1 kullanır) |
| `web/dash_chrome.py` | Ortak üst bar POLY / KRİPTO / **BAHİS** — dünya aksanı; login hariç HTML yaması; **mobilde (≤800px) gizli**; `#fapi-ban-bar` medya kuralında `{ #` boşluğu (Jinja `{#` yorumu `/algoritma` `/harita` 500 yapmasın) |
| `bahis/` | Bahis paketi — TR + EPL + La Liga + Serie A + Bundesliga + Ligue 1 + Brasileirão |
| `bahis/pages.py` | **BAHİS** Green Betting — maç + oyuncu + motor başına tahmin sekmesi; üstte **SITE** → `/site` |
| `bahis/engines.py` | Motorlar: Dixon · Poisson · Elo · xG · Ensemble · Bankroll · Kupon · Backtest; `GET /bahis/api/engines` |
| `bahis/dixon_coles.py` | Dixon-Coles + ELO λ karışımı — 1X2 / 2.5 / KG; emir yok |
| `bahis/elo.py` | ELO + RD (`elo.js`) — 1X2; emir yok |
| `bahis/bankroll_preds.py` | ¼ Kelly — Dixon × vig’siz (fair) implied; min kenar %4; emir yok |
| `bahis/dixonColes.js` | Dixon-Coles JS kaynağı |
| `bahis/elo.js` | ELO JS kaynağı |
| `bahis/bankroll_manager.py` | ¼ Kelly + fair kenar + kupon 1/√n; emir yok |
| `bahis/site.py` | Herkese açık `/site` — MATCHDAY; maç kartı → `/site/mac/<id>`; emir yok |
| `bahis/site_match.py` | Maç detay — Poisson/Elo/xG/ensemble/MC + tüm İddaa pazarları |
| `bahis/site_results.py` | `/site/biten` — bitmiş maç + TUTTU/TUTMADI |
| `bahis/results.py` | Tahmin defteri okuma · `GET /site/api/finished` |
| `bahis/results_fetch.py` | Saatlik 7 lig skor + Fotmob fikstür yenileme · `results_book.json` · FD 300/404 = henüz yok |
| `bahis/features.py` | 5 sezon gol/xG/şut/korner/kart · oran açılış-kapanış · dinlenme · Fotmob sakatlık; DC+ELO λ |
| `bahis/value.py` | Overround (de-vig) · fair kenar ≥%4 · CLV günlüğü `data/clv_log.jsonl` |
| `bahis/coupon.py` | Greedy kâğıt kupon · aynı maç matris birleşik · Kelly /√n · emir yok |
| `bahis/coupon_book.py` | Sanal kupon · 5 gün · 200 TL · settle skorla · AÇIK/BİTEN · emir yok |
| `bahis/site_coupons.py` | `/site/kuponlar` · AÇIK/BİTEN sekmeleri · ayak TUTTU/TUTMADI; canlı bahis yok |
| `bahis/calib.py` | Walk-forward (ELO maç-maç · DC sezon) · Brier / log-loss · oranlı P&L |
| `bahis/risk.py` | Circuit breaker · günlük %8 · haftalık %20 · DD %25 |
| `bahis/notify.py` | Value Telegram (LAB) · ANALİZ1’e düşmez · emir yok |
| `bahis/match_intel.py` | DC+ELO λ ensemble + MC + value/Kelly + dinlenme/sakatlık uyarısı; log `preds_log.csv` |
| `temmuzPoly/pm_trader_helpers.py` | Sanal açıkta CLOB `pm_sanal_fill` + `pm_win_profit`; giriş kapısı net kâr ≥ stake × %50 (sinyale dokunmaz) |
| `bahis/league.py` | Lig başına 10 sezon + güncel fikstür; `?league=`; H2H + form; emir yok |
| `bahis/leagues_cfg.py` | 7 lig kaydı (TR/EPL/ES/IT/DE/FR/BR) + Fotmob/football-data kodları |
| `bahis/fetch_leagues.py` | CSV + Fotmob fikstür çekimi — `python3 bahis/fetch_leagues.py` |
| `bahis/players.py` | Oyuncu API — `data/players.json` (Fotmob 10 sezon) |
| `bahis/players_fetch.py` | Fotmob oyuncu çekici — `python3 bahis/players_fetch.py [epl …]` |
| `bahis/data/` | football-data CSV (T1/E0/SP1/I1/D1/F1/BRA) + fikstür + oyuncu JSON |
| `web/poly_dashboard.py` | Poly dashboard **5050** — `/poly/grafik` mum analizi; `/algoritma-islemler/saatlik-yol` BTC/ETH/SOL yol grafiği; `/algoritma-islemler` A1 Top-34 + A2 Top-17 + A6/V2/V3/A15/B1 (7/24 sanal), **bakiye ≥ $500** olanlar listelenir (cron durmaz) (X1#01 + COMBO + COMBO2 + **F1-01…07** dahil); **Algoritma oyu şeridi yok** (2026-09-01); `GET /poly/api/consensus` duruyor; kartta **durgun=yeşil / trend=sarı / canlı=mor** dış bant (motor tipi); **Kupon sonuçları** sekmesi MATCHDAY bitmiş kuponları gösterir + **:02/:05/:07 WR** çipleri, detayda dilim butonları; liste **iki sütun**: sol tüm defterler net P&L · sağ WR (her biri 3’lü ızgara); üstte F16 · A2#03 · A2#05 · F16V2 + 1Y aylık net $ kenarı (TOP1–4 kartı yok); `/poly/yapay-zeka-analiz` Poly Algo Analist bildirim akışı + Lider Analizi; `/kripto/yapay-zeka-analiz` Kripto Test AI Analist bildirim akışı; **`/kripto/lider-analiz`** Kripto Test lider tablosu (`day_movers` aktif 30+30, genel + coin bazlı PnL/WR); **`/kripto/jarvis`** JARVIS denetim ekranı (cyan/magenta/gold HUD, iki sekme: Kripto Test Analizi + Kripto Sistem Denetimi; veri `/kripto/api/jarvis` → `jarvis_report.json` + `jarvis_audit.json`, gece 00:00 tazelenir, CSS sınıfları `j-` önekli); `/kripto` coin liderleri **SKILL + t** ile sıralanır (WR değil); **`/bahis`** BAHİS kabuğu; **`/site`** herkese açık Green Casino + kupon (şifre yok); **`/forex` yok** (CoptC) |
| `web/poly_dashboard.py` `/forex` | **Yok** — `/forex` ve `/xau` → `/poly`; motor CoptC |
| `BursaApp/` |
| `BursaApp/enrich_camps.py` | 42 kamp yeri upsert + Wikimedia/visit foto (çift görsel engeli) |
| `BursaApp/templates/visits_list.html` | Gezilecek — kenar filtre (tür/giriş/UNESCO/ilçe) + dikey kart listesi |
| `BursaApp/seed_visit_expand.py` | Gezilecek · `import_osm_delta` (yeni OSM, mahalle camisi/zirve atlanır) + meşhur müzeler |
| `BursaApp/templates/foods_list.html` | Yeme-içme — kenar filtre (tür/mutfak/yemek/fiyat/ilçe) + dikey restoran kartları |
| `BursaApp/seed_panorama_food.py` | Bursapanorama restoran delta · `--refresh` HTML yeniler · `data/panorama_restoranlar.json` |
| `BursaApp/seed_food_expand.py` | Yeme-içme · `import_osm_delta` (yeni kayıt, kopya atlanır) · kahvaltı/meyhane/cantık · kafe→cafe |
| `BursaApp/enrich_visit_gallery.py` | Gezilecek kapak+galeri (Wikimedia) · `extra.gallery` · Instagram scrape yok |
| `BursaApp/templates/camps.html` | Kamp keşif — Airbnb tarzı grid · kategori şeridi · harita FAB |
| `BursaApp/enrich_food_venues.py` | Yeme-içme kapak+menü enrich (Commons · top ~80 · `static/cache/food-venue/`) |
| `BursaApp/templates/_shell.html` | Site kabuğu · GA4 `G-HTBTD54V3D` · WhatsApp destek · e-posta onay şeridi |
 Bursa dijital şehir — `bursaapp.com/` · Flask **5051** · Bugün/Akşam/Yakınımda/Hafta sonu · üye puan/yorum · `/poly` ayrı |
| `BursaApp/feed_social.py` | Feed birleşik akış · ziyaret→post beğeni/yorum · takip listesi · takipçi sayacı |
| `BursaApp/templates/profile_feed.html` | 3 sütun feed UI — sonsuz kaydırma · stories · sticky compose |
| `BursaApp/virtual_users.py` | 10 sanal üye (6K/4E) · feed/ziyaret/beğeni · `*.sanal@bursaapp.com` |
| `BursaApp/virtual_users_seed.py` | Sanal üye oluştur · `seed` / `stats` / `tick` |
| `BursaApp/virtual_users_activity.py` | Cron aktivite · `25 */3 * * *` · log `/tmp/bursaapp_virtual_users.log` |
| `BursaApp/schools_fetch.py` | Bursa okulları OSM + curated + MEB dershane/özel eğitim → `data/schools.json` · etkinlikler |
| `BursaApp/dershane_fetch.py` | MEB Bursa dershane listesi (125) → `data/meb_dershaneler_bursa.json` |
| `BursaApp/ozel_egitim_fetch.py` | MEB rehabilitasyon merkezleri → `data/meb_ozel_egitim_bursa.json` |
| `BursaApp/seed_schools.py` | Okul + okul etkinliği seed · `python3 BursaApp/seed_schools.py` |
| `BursaApp/data/schools_curated.json` | Özel kolej / üniversite zengin kayıt (program, kayıt, etkinlik) |
| `BursaApp/templates/school_detail.html` | Okul detay — program · olanak · etkinlik takvimi |
| `BursaApp/app.py` | Keşfet hub + `/album` + `/hesap/profil` Feeds + `/hesap/ayarlar` + e-posta onay + yer foto + `/yer/<slug>/gidecegim` |
| `BursaApp/analytics.py` | Tekil ziyaretçi (`ba_vid`) · bot/GoogleOther/crawler elenir · Accept-Language zorunlu · localhost/urllib sayılmaz · `--reset` |
| `BursaApp/mail_verify.py` | E-posta onay (Brevo SMTP) · kırmızı şerit · 7g purge · siteden bypass yok |
| `BursaApp/notify.py` | Outbox + SMTP (`SMTP_HOST/USER/PASS`) · Telegram kayıt |
| `BursaApp/enrich_media_content.py` | Kafe/bar/meyhane/aile doğa + spor ücret + otel oda + film fragman zenginleştirme |
| `BursaApp/bursaapp_nightly.py` | Gece turu · OSM+Panorama delta · ≤80 onarım · seo + görsel · **02:30 İST** (`30 23 * * *`) · log `/tmp/bursaapp_nightly.log` |
| `BursaApp/ai_seo.py` | Yapay zeka SEO — dinamik `llms.txt` / `llms-full.txt` · AI bot robots · admin denetim |
| `BursaApp/seo_arch.py` | Hub/dikey/blog/KVKK SEO mimarisi · JSON-LD graph · `llms.txt` köprü |
| `BursaApp/seo.py` | Meta, canonical, OG, sitemap · ürün OG `og-bursa.jpg` · `/tesekkur` noindex |
| `BursaApp/templates/404.html` | Markalı Türkçe 404 — arama + dikey linkler |
| `BursaApp/templates/tesekkur.html` | Dönüşüm teşekkür sayfası — kayıt / e-posta / yorum / sahiplen |
| `BursaApp/seo_status.py` | Google/GSC + teknik SEO checklist · dashboard kartı · `/admin/seo` token kaydı |
| `BursaApp/fetch_film_posters.py` | Film afişleri (Wikimedia) · `static/cinema/film-*.jpg` |
| `BursaApp/enrich_doctors.py` | Acıbadem kadro özgeçmiş + foto URL · `templates/doctor_detail.html` |
| `BursaApp/fix_seo_content.py` | Yanlış kapak (Yeşil Türbe vb.) + eksik img/blurb/ilçe düzeltmesi |
| `BursaApp/ensure_up.py` | 5051 düşerse `systemctl restart bursaapp` (yoksa tek orphan) · cron her dk · log `/tmp/bursaapp_ensure.log` |
| `BursaApp/discover.py` | Bugün / bu akşam / yakınımda / hafta sonu sorguları (Haversine, kural tabanlı plan) |
| `BursaApp/features.py` | Rota · AI · yemek SEO · ilçe portal · harita · `/etrafimda` (konum + yarıçap filtre) · kampanya · sahiplenme · işletme · SEO landing |
| `BursaApp/itinerary.py` | 1 günlük rota + bütçe + kural tabanlı AI |
| `BursaApp/foods.py` | Bursa meşhur yemekler · Wikimedia gerçek ürün foto (`static/food/ne-yenir-*.jpg`) |
| `BursaApp/seo_pages.py` | SEO landing + ilçe slug haritası |
| `BursaApp/seed_platform.py` | Kampanya/kupon/editoryal/est_meal seed |
| `BursaApp/catalog.py` | Kategoriler + `MEKAN_TAXONOMY` alt türler + `place_public` puan |
| `BursaApp/data/restaurants.json` | Yeme-içme: ilçe + liste puanı · alt tür · foto `static/food/` · Google Places meşhur noktalar (Selçuk, Double F, Vertice, Han 1426…) |
| `BursaApp/data/shops.json` | Alışveriş: AVM, outlet, hediyelik, yerel · `/alisveris` |
| `BursaApp/data/markets.json` | Marketler: zincir başına 1 kayıt (BİM, Özhan, File…) · logo + aktüel URL · `/marketler` |
| `BursaApp/data/sports.json` | Spor: fitness, yoga, yüzme, tenis, halı saha · `/spor` |
| `BursaApp/data/family.json` | Aile: park, piknik, zoo, çocuk · `/aile` |
| `BursaApp/data/album.json` | Bursa albüm görselleri · `/album` |
| `BursaApp/data/bursaspor_standings.json` | 1. Lig puan durumu tablosu · `/bursaspor` |
| `BursaApp/bursaspor_feed.py` | Bursaspor haber RSS + özgün özet + maç masası · `data/bursaspor_feed.json` · cron **06:00/18:00 İST** (`0 3,15 * * *` UTC) · log `/tmp/bursaspor_feed.log` |
| `BursaApp/data/bursaspor_feed.json` | `/bursaspor` gündem + maç masası çıktısı |
| `BursaApp/bursa_news_fetch.py` | Bursa şehir haberleri RSS + özgün özet + detay gövdesi · `data/bursa_news.json` · cron **≈2 saatte bir** (`20 */2 * * *` UTC) · log `/tmp/bursa_news.log` |
| `BursaApp/news_pages.py` | Haber JSON okuma, filtre, sayfalama · `/haberler` · `/haber/<slug>` |
| `BursaApp/bursa_youtube_fetch.py` | Bursa YouTube RSS (Bursaspor · BBT · Haber TV) · embed · `data/bursa_news_videos.json` · haber cron ile birlikte |
| `BursaApp/data/bursa_news_videos.json` | Haber sayfası YouTube embed listesi |
| `BursaApp/templates/news_index.html` | Haber listesi + konu filtreleri |
| `BursaApp/templates/news_detail.html` | Haber detay sayfası |
| `BursaApp/blog_weekend_cron.py` | Perşembe hafta sonu rota blogu (1–2 yazı) · `data/blog_generated/*.json` · cron **09:00 İST Perşembe** (`0 6 * * 4` UTC) · log `/tmp/blog_weekend_cron.log` |
| `BursaApp/weekend_blog.py` | Rota temaları + gerçek mekanlarla blog gövdesi üretimi |
| `BursaApp/data/blog_generated/` | Cron ile üretilen hafta sonu blog JSON dosyaları |
| `BursaApp/nobetci_eczane_fetch.py` | Bursa nöbetçi eczane · asıl kaynak **beo.org.tr** (API yedek) · `data/nobetci_eczaneler.json` · cron **07:00 / 12:00 / 15:00 / 18:45 / 19:00 İST** · log `/tmp/nobetci_eczane.log` |
| `BursaApp/utilities_fetch.py` | BUSKİ su · UEDAŞ elektrik · Bursagaz doğalgaz tarife + 17 ilçe ofis · `data/utilities.json` · cron **06:00 İST** · `/faturalar` |
| `BursaApp/teleferik_fetch.py` | Uludağ teleferik bilet/saat/indirim/otobüs · `data/teleferik.json` · cron **06:15 İST** · `/uludag-teleferik` |
| `BursaApp/utilities_pages.py` | JSON yükleyici · ilçe gruplama · şablon yardımcıları |
| `BursaApp/optimize_images.py` | Statik görsel sıkıştırma + 640×480 kart thumb (`static/cache/thumbs`) · `place_public` thumb tercih eder |
| `BursaApp/seed_city.py` | shop/sport/family/**market** seed + market kampanya + food subcategory + koordinat backfill |
| `BursaApp/data/places_visit.json` | Gezilecek: UNESCO + köy + dağ + İznik · Wikimedia gerçek foto · Bursaray yok |
| `BursaApp/data/hotels.json` | Oteller (eski çekirdek liste) · `/oteller` |
| `BursaApp/data/hotels_enuygun.json` | Enuygun MCP Bursa otel envanteri (foto + örnek fiyat) |
| `BursaApp/seed_hotels_enuygun.py` | Enuygun otelleri seed · `static/hotel/` galeri · Yalova elenir |
| `BursaApp/templates/hotels.html` | Oteller landing: hero + arama + kart grid (mockup düzeni) |
| `BursaApp/data/camps.json` | 42 kamp: Uludağ, kıyı, gölet, Longoz, Balıkesir · `/kamp` |
| `BursaApp/data/burgers_bursa.json` | 40 burger mekanı (Too/Otto/Burgy + zincir şubeler) · `/yeme-icme?dish=burger` |
| `BursaApp/seed_burger_bursa.py` | Burger seed + işletme/web/Commons foto zenginleştirme |
| `BursaApp/data/concerts.json` | Konser salonları: Merinos, Kültürpark, Tayyare, Timsah Arena · `/konserler` |
| `BursaApp/data/shows_theater.json` | Yakın tiyatro: Baba, Hamlet, Don Kişot… · `/tiyatro` |
| `BursaApp/data/shows_concert.json` | Eylül–Ekim konser: Sibel Can, Grinko, Sertab… · `/konserler` |
| `BursaApp/data/films.json` | Vizyon + Korupark/Marka/Podyumpark · `/sinema` |
| `BursaApp/data/events.json` | Junioshow, Kahve Festivali, Altın Biber · `/etkinlikler` takvim |
| `BursaApp/data/hospitals.json` | Hastaneler: Şehir, Acıbadem, Medical Park, BUÜ, Jimer, Doruk · `/hastaneler` |
| `BursaApp/data/doctors.json` | Hekim: resmi kadro · `venue_name` = hastane slug · `/doktorlar` |
| `BursaApp/health_refresh.py` | Cron: Doruk kadro + diş (MHRS/resmi) + `seed_health` + `enrich_doctors` · **08:30 İST** · log `/tmp/health_refresh.log` |
| `BursaApp/mhrs_dental.py` | Resmi ADSM: bursaism tablo + saglik.gov.tr iletişim + hospitals Diş · SKRS önbellek |
| `BursaApp/dentists_fetch.py` | MHRS/resmi + OSM + el seçimi → `data/dentists.json` · teyit filtresi · `--seed` · `--geocode` |
| `BursaApp/data/dentists.json` | Diş: ADSM + özel klinik + Dt. · `/dis-hekimleri` · eczane tarzı hero/liste |
| `BursaApp/data/vets.json` | Veteriner: BUÜ + VHO kayıtlı klinik · `/veterinerler` · hero/liste + yakın bul |
| `BursaApp/data/fun.json` | Eğlence: bowling, escape, canlı müzik, bar, AVM · `/eglence` |
| `BursaApp/data/orgs.json` | Organizasyon: belediye kültür, BAOB, TÜYAP, KFA · `/organizasyonlar` |
| `BursaApp/models.py` | User (avatar/email_verified/show_full_name) · PlacePhoto · SeoAudit · Review.img_url · SQLite |
| `BursaApp/auth.py` | Session `bursaapp_session` + JWT · Poly cookie’ye karışmaz |
| `BursaApp/api_v1.py` | `GET/POST /api/v1/*` · discover + reviews · `BursaApp/API.md` |
| `BursaApp/admin.py` | KPI (üye/restoran/market/hastane) · günlük giriş grafiği · üye foto onay · SEO panel · Bursaspor maç |
| `BursaApp/admin_forms.py` | Admin form parse + `static/uploads/` dosya yükleme |
| `BursaApp/itinerary.py` | 1 günlük rota · **otobüs/araç/yürüyüş** · AI niyet anahtarları (aile/yağmur/konser…) |
| `BursaApp/seo_urls.py` | `/bursa-{slug}` SEO yolları (ulu-cami → `/bursa-ulu-cami`) |
| `BursaApp/media_cache.py` | Uzak görsel disk önbelleği (TTL 30g) · static max-age 7g |
| `BursaApp/static/admin/` | Event-ticketing (Ventic) CSS/JS — Flask admin UI |
| `BursaApp/static/app.css` | WanderAsia public UI (krem / orman yeşili / turuncu) · restoran detay `rd-*` |
| `BursaApp/templates/event_detail.html` | Tiyatro/konser/etkinlik detay — hero · geri sayım · platform bilet · hakkında · kurallar · mekan etkinlikleri |
| `BursaApp/templates/detail.html` | Genel yer detay · **film** için Hikaye/Oyunculuk/Görsellik/Tempo yıldız değerlendirme |
| `BursaApp/templates/restaurant_detail.html` | Yeme-içme detay — hero · menü kartları · bilgi grid · galeri · yorum |
| `BursaApp/templates/hospital_detail.html` | Hastane detay — hero · hizmet · ücret · hekimler (branş açılır seçici) · hasta deneyimi (Doktor/Personel/Temizlik/Bekleme) |
| `BursaApp/events_fetch.py` | Etkinlinkler Bursa çekimi · detay enrich (about/platform/kurallar) · `backfill-details` | Etkinlinkler Bursa liste + gerçek kapak foto · upsert Place · wiki yedek · gece **00:00 İST** (`0 21 * * *` UTC) · log `/tmp/bursaapp_events_fetch.log` |
| `BursaApp/notify.py` | Bildirim outbox + **Telegram kayıt bildirimi** (`BURSAAPP_TG_*`) |
| `BursaApp/static/favicon.ico` | Marka “b” favicon + `logo-*.png` · `_shell` tüm sayfalar · `/robots.txt` `/sitemap.xml` (Search Console) |
| `BursaApp/seo.py` | Meta/OG/canonical · JSON-LD graph (hub) · dikey Service+Offer · sitemap |
| `BursaApp/uploads/` | Şablon ZIP / yüklemeler — içerik git’e alınmaz (`*` ignore) |
| `AgustosKripto/binance_um_wallet.py` | Tek USDT-M cüzdan önbelleği (CEBU / user-ws); REST yok |
| `temmuzPoly/repair_a2_sanal_settlement.py` | A2 sanal geçmişi PM slot open/close ile yeniden hesaplar (Binance 1h). |
| `scripts/watch_critical_files.py` | Kritik kaynak inotify izleyici — silinmede `ops/incidents/` olay kaydı |
| `ops/CRITICAL_FILE_RESTORE.md` | 2026-08-02 kaynak silinme / geri yükleme zaman çizelgesi |
| `ops/gpsusdt_close_retry.py` | GPSUSDT canlı kapanış tekrarı — CoptC `live_close_fail` olunca MARKET reduceOnly, 4×6sn; emir açmaz |
| `ops/incidents/` | Silinme/eksik olay JSON+txt (process, git D, audit) |
| `AgustosKripto/` | Kripto Future — CR6/A139/B1#03 Live + sanal Test (`bursaapp.com/kripto` · `/kripto/test`) |
| `AgustosKripto/binance_um.py` | Binance USD-M gerçeği — bid/ask/mark, step/tick, taker %0,05, izolе liq, funding, PnL; sinyal/ATR yok |
| `AgustosKripto/virtual_book.py` | Sanal futures — `binance_um` dolum/fee/liq/funding; ATR kâr kilidi + `exit_policy`; cache + `/tmp/agustos_snap` |
| `AgustosKripto/exit_policy.py` | **Çıkış rejimi tek kaynağı** — zaman kapanışı yok · 24s tavan · **3×ATR** zarar stop. Kâr kilidi ARM **0.5×ATR** (`atr_profit_lock.py`). `exit_policy.json` ile kod değişmeden kapatılır |
| `AgustosKripto/orphan_scan.py` | Sahipsiz defter taraması — hiçbir runner'ın işlemediği `*_state.json` (açık pozisyon tutar, sessizce muhasebe dışı kalır); `--archive` |
| `AgustosKripto/Test/exit_lab.py` | Çıkış rejimi laboratuvarı — girişler sabit, gerçek 1m veriyle yeniden oynatma; `--validate` (kayıtlı sonucu üretiyor mu) · `--sweep` · `--deep` (gün-kümelenmiş t) · `--realistic` · `--walkforward` |
| `AgustosKripto/Test/exit_1h_close_ab.py` | 1h_close A/B backtest — `ENABLE_1H_CLOSE_EXIT` sarmalayıcı; çekirdek/canlı dosyaya dokunmaz; çıktı `Test/out_1h_close_ab/` |
| `AgustosKripto/Test/exit_ab_long.py` | Uzun pencere A/B/C (1h+4h / yalnız 4h / zaman yok ATR trail) + Mayıs–Ağu hist giriş; `minute_data.py fetch_vision` |
| `AgustosKripto/Test/exit_ab_d.py` | Run D rejim filtresi — trend→ATR trail, chop→4h_close; eşik May–Tem, Ağustos OOS; canlıya dokunmaz |
| `AgustosKripto/Test/exit_diag.py` | Kapanış-sebebi tablosunun seçilim yanlılığı teşhisi (MFE + silahlanma oranı kırılımı) |
| `AgustosKripto/atr_profit_lock.py` | ATR trailing kâr kilidi (**arm 1.0 / trail 0.5** — MFE'de işlemlerin %79'u 0.5 ATR'yi geçmiyordu) + zarar-stop; modül varsayılanı `2.0×ATR$` **değişmedi** (gerçek para yolu `crypto_futures_cr6` bunu doğrudan import ediyor), sanal defterler `exit_policy` ile pozisyon başına `6.0` kullanır |
| `AgustosKripto/Test/` | Tek kripto sanal ekran (`/kripto/test`); `$100×6x`; **max 8**; **14 defter** (bakiye ≥ $1005); evren `um_universe.txt`; tarama `day_movers` aktif 30+30 (~60); BTC/ETH yok |
| `AgustosKripto/Test/day_movers.py` | USDT-M evreninde 24s en çok artan/azalan 30+30; fapi yok (spot ticker); cron `*/30`; `data/day_movers.json` → Test `scan_symbols` |
| `AgustosKripto/Test/leader_mapping.py` | Lider Analiz + JARVIS_V1 ortak sıralama (PnL→WR→işlem); tablo değişince JARVIS eşlemesi geçmiş mtime ile yenilenir |
| `AgustosKripto/Test/jarvis_v1.py` | JARVIS_V1 — `leader_mapping` üzerinden coin→motor; ARB→A1#33 · OP→B1#03 pin; kaynak TF kopyası; max 10 pozisyon |
| `AgustosKripto/Test/cebu.py` | CEBU sanal — Lider Analiz 1. sıra motor · `/kripto/cebu` · max 8 · Binance live kapalı |
| `AgustosKripto/Test/kripto_test_analyst.py` | Kripto Test AI Analist — **DURDURULDU** (`kripto_analyst_control.json` paused · cron yorum) |
| `AgustosKripto/Test/jarvis_report.py` | **JARVIS motoru (1. sekme)** — 69 Test defterini tarar, drift-nötr SKILL + t, komisyon/brüt/net kırılımı, kapanış-sebebi ve coin dökümü üretir; bulgular veriden otomatik yazılır. Çıktı `jarvis_report.json` + `jarvis_history.jsonl` (gün gün). Gece **00:00** cron aynı turda `jarvis_audit.py`'yi de çalıştırır; `bursaapp.com/kripto/jarvis` |
| `AgustosKripto/Test/jarvis_audit.py` | **JARVIS sistem denetimi (2. sekme)** — yalnız Test defterleri `skill_audit.py` ile taranır; MFE, kapanış-sebebi, drift, konsensüs, CR6 hayaletleri. Çıktı `jarvis_audit.json` |
| `AgustosKripto/Test/analog.py` | Analog pencere eşleştirme — son 48 mum z-score şekli → 270k geçmiş pencerede korelasyon → ileri getiri dağılımı + güven skoru; `build`/`query`/`eval` |
| `AgustosKripto/Test/backtest_fast.py` | `backtest_1y` ile birebir aynı sonuç, ön hesaplı dilim (4 faz hizalı 4h + normalize 1h + ATR memo); A2'de 34x, A6'da 5.4x; `--books`/`--source`/`--verify` |
| `AgustosKripto/Test/horizon_sweep.py` | Tutma süresi taraması — sinyal → 1/2/4/8/12/24/48s getiri; imzalı brüt **ve** drift-nötr SKILL (küme-dayanıklı SE); `--symbols` evren kısıtı, `--per-symbol` coin kırılımı (edge_gate girdisi) |
| `AgustosKripto/Test/edge_gate.py` | **Ölçülen kenar kapısı** — (defter, coin) çifti yalnız 1Y SKILL komisyonu aşarsa ve t eşiğini geçerse işlem açar; `proven` t≥3 tam kademe · `candidate` t≥2 çeyrek kademe · diğer kapalı. Tablo yoksa **kapalı** (varsayılan güvenli). `--build` / `--show` |
| `AgustosKripto/Test/backtest_pro4.py` | Çıkış rejimi taraması (A2#05·A6V3·B1#03·MELEZ) — saatlik zorunlu kapanış vs sinyal-dönene-kadar, taker/maker, 4h, majör evren; SKILL/t + kapanış gerekçesi dökümü |
| `AgustosKripto/Test/minute_data.py` | Maker fill sim için 1m OHLC cache — `fetch`/`info`; `data/minute_cache/*_1m.npz` (30 coin × 90g ≈ 3.9M mum, ~28 MB) |
| `AgustosKripto/Test/maker_sim.py` | Limit emir fill simülasyonu — analog sinyal + 1m low/high; offset × pencere × ters seçilim; taker vs maker karşılaştırma |
| `AgustosKripto/fee_utils.py` | Binance komisyon — estimate + userTrades; brüt→net; `get_taker_rate` / `get_maker_rate` |
| `AgustosKripto/skill_audit.py` | Kalıcı denetim — drift-nötr `SKILL` = (ort. LONG% + ort. SHORT%)/2, `DRIFT`, t-istatistiği; defter/coin/konsensüs/güven kırılımı + MFE dağılımı + maker senaryosu. `--leaders` `--mfe` `--consensus` `--conviction` `--all` |
| `AgustosKripto/conviction_filter.py` | Yüksek güven vetosu — oy birliği (4/4) sinyalleri açılmaz; ölçülen SKILL −0.065% (t=−3.89, 5/5 dilim). Vetolananlar `conviction_shadow.jsonl` gölge defterine yazılır; ters açma **kapalı** (kanıt yetersiz). Ayar: `conviction_filter.json` |
| `AgustosKripto/funding_harvest.py` | Funding hasadı tarayıcı (delta-nötr) — perp funding oranı + `fundingIntervalHours` (4h/8h sembole göre) → yıllık %, başabaş süre, likidite skoru; **emir açmaz**, `--tg` ile rapor |
| `AgustosKripto/algo_tg_notify.py` | Kripto sanal algo TG — **10. ANALİZ kanalı** (`poly_analiz_dual_core` bot); close/open özeti 🔶 SANAL |
| `AgustosKripto/Algoritmalar/` | Sinyal kataloğu (CR6 + Test A1/A2). Sanal sayfa `/kripto/algoritmalar` kaldırıldı (2026-08-22); runner cron'u durdu |
| `AgustosKripto/Analizler/` | A10 Dual + Supertrend sinyal kaynağı. Sanal sayfa `/kripto/analizler` kaldırıldı; A10/ST Test'e taşındı |
| `AgustosKripto/binance_futures_client.py` | Binance USD-M REST — emir, bakiye, commissionRate, userTrades, `book_ticker`, `query_order`, `premium_index`, `funding_info` |
| `AgustosKripto/crypto_futures_trader.py` | Futures open/close + `dust` süpürme (|notional|≤$2); brüt/komisyon/net; `open_maker` (post-only GTX limit, tick yuvarlama, dolmazsa iptal) |
| `AgustosKripto/crypto_futures_cr6.py` | **Algoritmalar Live** (gerçek Binance) — Hurst+A1#11 MR+Z-Score MR+Mean Reversion çoğunluk oyu; top-N; $7×20x; **yeni open BTC/ETH/BNB yok**; ATR/hard SL; `fcntl` state kilidi + atomik yazım, `order_id` idempotency (hayalet pozisyon temizliği), `MAX_HOLD_HOURS` · **şu an paused** |
| `AgustosKripto/crypto_futures_a139.py` | **A1#39 Live** (gerçek Binance) — Test `a1_39` (H1 Kombinasyon) ile aynı sinyal/TF/çıkış; $20×7x; max 4; 30 coin; `/kripto` kartları yerel defterden (Binance 418/yasak ekranı boşaltmaz); USDT son okunan cache |
| `AgustosKripto/crypto_futures_b1_mum.py` | CEBU Binance ayna — **kapalı** (`.CEBU_VIRTUAL_ONLY`) |
| `AgustosKripto/crypto_futures_live_control.json` | CR6 Binance Live — `live_paused` (yeni açılış) + `top_n`; **paused kalır**, A1#39 ayrı kontrol |
| `AgustosKripto/crypto_futures_a139_control.json` | A1#39 Live — `live_paused` + `top_n` (1–4); **19.08 durduruldu** · `/kripto` çubuğu A1#39 sanal |
| `AgustosKripto/crypto_futures_b1_mum_control.json` | CEBU Live — `live_paused`; `/kripto/cebu` |
| `temmuzPoly/pm_home_display.json` | Poly `/poly` overview'da gösterilecek tek sanal defter (`book_key`; şu an `a2_05` · en iyi dilim :02/:05/:07) — `/algoritma-islemler` kartından "Poly overview'da aktif et" |
| `AgustosKripto/kaito_paper.py` | **KAITO kağıt defteri** — cr6 kararları, gerçek emir yok; `/kripto` overview'dan kaldırıldı (cron hâlâ ölçer) |
| `AgustosKripto/cr6_tg_card.py` | Algoritmalar Live TG sarı kart (ALGO2 stili) — açılış/kapanış/ATR photo |
| `AgustosKripto/crypto_futures_config.json` | Sembol allowlist + default $6 / 10x; `CRYPTO_FUTURES_LIVE` + CR6 canlı; `entry_mode: maker` + `maker_wait_sec: 90` |
| `temmuzPoly/analiz5_settings.json` | A1/A2/A10/A6 Live WR giriş tutarları (düşük/orta/yüksek) |
| `temmuzPoly/pm_profit_baseline.json` | PM Kar başlangıç bakiyesi (varsayılan $314); Toplam Kar = nakit − baseline. |
| `temmuzPoly/` | Poly trader'lar, algo motorları, backtest; dashboard port **5050**. |
| `crypto-news-monitor/` | Kripto haber/tweet tarayıcı — RSS + opsiyonel Twitter, Claude skor, Telegram alarm (30 dk cron) |
| `twitter_bot/` | @tradecomio otomatik tweet — `tweet_trade_card.py` (saatlik kripto kart) + `tweet_forex_wins.py` (30 dk: CEM01 kazananları + WR, birden fazlaysa aynı görsel) |
| `5M110Analiz/` | FeatureEngine v2 indikatör kütüphanesi (110/111/210 adaptörleri) |
| `5M110Analiz/predictor.py` | composite_signal → UP/DOWN (gate ±15; algo kütüphanesine dokunmaz) |
| `temmuzPoly/poly_predictor_analysis.py` | A1/A2 ortak `predict`; Kill Zone (ET 9–11, gate 62/55) varsayılan açık |
| `temmuzPoly/btc_5m_105_algo.py` | 5M ortak sinyal motoru (15M adaptörleri; 4-algo + MR veto) |
| `temmuzPoly/poly_trader_5m_common.py` | 5M BTC ortak yardımcılar (Binance, 4-algo, PM emir) |
| `binance_fapi_guard.py` | fapi **okuma kapalı**; mum spot/data-api; emir/listenKey POST-PUT-DELETE + GET yalnız `/fapi/v1/order` teyidi; hesap/pozisyon/fiyat WS; ban şerit `/poly/api/fapi-status` |
| `binance_ws_marks.py` | `/market` mark+last · `/public` GPS/XAU book · `/private` pozisyon+cüzdan · **saatlik yol** (`hourly_path/`) |
| `temmuzPoly/pm_trader_helpers.py` | PM emir + sanal kotasyon. Saatlik kapanış mumu `pm_sanal_slot_candle`: önce `fapi`, 418 olursa spot data API. **Sanal dolum canlı emirle birebir aynı formül** (`pm_sanal_fill`): `pm_order_book` (CLOB defteri, 20 sn önbellek, borsanın `min_order_size`/`tick_size`'ı) → `pm_book_vwap` (derinlik yürüyüşü) → 2 haneye yuvarla → min adet → `pm_fit_buy`. 63 senaryoda canlı `pm_place_order` ile sıfır sapma. **PM taker ücreti** `fee = C×0,07×p×(1−p)` (`pm_taker_fee`) tüm P&L'den düşülür; gerçek PM WR giriş (`load_pm_live_amounts` / `analiz5_settings.json`); slot tutarı: zayıf saat -%30, hot-hour büyütme **kapalı** (`HOT_HOUR_BOOST=1.0`) |
| `temmuzPoly/telegram_poly_channels.py` | Poly TG kanal yönlendirme — `TELEGRAM_ANALIZ1_CHAT_ID` yalnızca 1. ANALİZ; diğer trader'lar `TELEGRAM_POLY_TRADERS_CHAT_ID` / `TELEGRAM_PM_LIVE_CHAT_ID` vb. (analiz1 kanalına asla düşmez) |
| `temmuzPoly/pm_manual_sync.py` | Manuel PM — Polymarket activity → manual state senkron (5/15dk + saatlik) |
| `temmuzPoly/poly_trader_manual.py` | Manuel PM slot-sonu otomatik settle (`close`) — 5m/15m/1h |
| `temmuzPoly/pm_orphan_sync.py` | Ghost PM — zincirde açık ama state'te yok pozisyonları live trader'a yazar (trader sembol allowlist) |
| `temmuzPoly/pm_poly_history.py` | Polymarket data-api activity → slug bazlı gerçek PM geçmişi + açık (bekleyen) işlemler |
| `temmuzPoly/pm_balance_guard.py` | PM USDC bakiye + Live anahtarları; **`user_live_hold`** gerçek PM'i kullanıcı açana kadar kilitler (hafta sonu / dashboard Aç aşamaz) |
| `temmuzPoly/pm_weekend_sync.py` | Cum 22:00 / Pzt 11:00 İST — A1 Live + A2 dashboard anahtarlarını otomatik kapat/aç |
| `temmuzPoly/btc_analiz1_algo.py` | 1. Analiz tam algoritma (standalone kopya, poly_predictor ile aynı) |
| `temmuzPoly/poly_trader_analiz1.py` | **F16** sanal (eski 1. Analiz · BTC+SOL); **$1000** · $24/36/48 WR; PM net kazanç ≥%50 yoksa giriş yok; top-3 saatte +%50; 12:00 yarı; **hafta sonu da açık** |
| `temmuzPoly/f16v2_signal.py` | F16V2 sinyal — BTC/SOL `predict()` · ETH A2#03 `stoch_rsi` |
| `temmuzPoly/poly_trader_f16v2.py` | **F16V2** sanal (BTC/SOL F16 · ETH A2#03); **$1000** · $24/36/48; kâr kapısı; gerçek PM yok |
| `temmuzPoly/poly_trader_analiz2.py` | 2. Analiz sanal (SOL only; $300; PM net kazanç ≥%50 yoksa giriş yok; **ALLOW_FALLBACK=False**) |
| `temmuzPoly/poly_trader_analiz2_live.py` | 2. Analiz **canlı PM** SOL; slot gate zayıf saat -%30; PM net ≥%50 |
| `temmuzPoly/backtest_common.py` | 1Y walk-forward backtest ortak yardımcılar |
| `temmuzPoly/backtest_analiz2.py` | 2. Analiz 1Y walk-forward backtest (SOL, predict motoru) |
| `temmuzPoly/backtest_analiz1.py` | 1. Analiz 1Y walk-forward backtest (BTC+SOL, predict motoru) |
| `temmuzPoly/backtest_analiz_suite.py` | Eski 10. Analiz 1Y backtest (defter kaldırıldı — canlıya dokunmaz) |
| `temmuzPoly/analiz15_signal.py` | 15. Analiz sinyal — BTC→A6 MACD, ETH→A8 Jesse, SOL→A2 predictor |
| `temmuzPoly/poly_trader_analiz15.py` | 15. Analiz sanal (BTC+ETH+SOL); Cum 22:00–Pzt 11:00 open kapalı; TG A4 botu; $300 |
| `temmuzPoly/backtest_algo_catalog.py` | 78 algo 1Y yön backtest (BTC+ETH+SOL 1h) → `backtest_algo_catalog_1y.json` |
| `temmuzPoly/backtest_algo_catalog_notify.py` | Top-30 algo 1Y P&L özeti + Telegram (`--send`) |
| `temmuzPoly/poly_trader_analiz5_midcheck.py` | A1 Live açık pozisyon :30 anlık değer + PM kotasyon görseli (TG) |
| `temmuzPoly/poly_trader_analiz5.py` | **A1 Live** — gerçek PM; slot gate: zayıf saat -%30 (hot-hour büyütme kapalı) |
| `temmuzPoly/poly_analiz_dual_core.py` | Çift konsensüs motor (A1+A4) — Poly 10. Analiz kaldırıldı; kripto Test A10 Dual + TG notify hâlâ kullanır |
| `temmuzPoly/poly_trader_analiz6.py` | 6. Analiz sanal (BTC+SOL+ETH); TG=15. Analiz (A4 botu); A6 Live eşleme; **hafta sonu da açık** |
| `temmuzPoly/poly_trader_analiz6_v2.py` | 6. Analiz V2 sanal (BTC+ETH only); A6V2 Live eşleme; **hafta sonu da açık** |
| `temmuzPoly/poly_trader_analiz6_v3.py` | 6. Analiz V3 sanal (BTC/ETH→A6 · SOL→A2); A6V3 Live eşleme; **hafta sonu da açık** |
| `temmuzPoly/poly_trader_analiz6_v4.py` | **A2#05 X A6V3 MELEZ** sanal — V3 iskeletini import edip globalleri yönlendirir (V3 dosyası dokunulmaz); BTC→MACD Div #26 · ETH/SOL→Mean Rev ($300); defter anahtarı `melez` · URL `/algoritma-islemler/melez` |
| `temmuzPoly/poly_trader_b1_01.py` | B1#01 sanal — sembol bazlı en iyi motor birleşimi ($300); **hafta sonu da açık** |
| `temmuzPoly/b1_01_signal.py` | B1#01 motor seçimi — algoritma-islemler WR taraması |
| `temmuzPoly/poly_trader_b1_02.py` | B1#02 sanal — sabit BTC→A15 · ETH→A6 · SOL→A2#01 ($300); **hafta sonu da açık** |
| `temmuzPoly/poly_trader_b1_mum.py` | B1#03 MUM ANALİZ sanal — Sonnet mum confluence 1h ±15 ($300); TG; **hafta sonu açık** |
| `temmuzPoly/poly_trader_b1_04.py` | B1#04 sanal — 23 birincil motorun edge-ağırlıklı küme konsensüsü ($1000); :01 close / :02:30 open |
| `temmuzPoly/b1_04_signal.py` | B1#04 karar motoru — kopya defterleri tek oya indirir, oyları başabaşa göre ölçülmüş edge ile ağırlıklandırır; eşik `B1_04_MIN_EDGE` (varsayılan **0.0** = oylama yön gösterince gir) |
| `temmuzPoly/b1_04_backfill.py` | B1#04 geçmişini A2#05 slotlarında walk-forward simüle edip doldurur (`--write`); kayıtlar `backfill: true` |
| `temmuzPoly/poly_trader_b1_05.py` | **B1#05** sanal — coin başına en iyi motor ($1000); B1#01 iskeletini import edip globalleri yönlendirir (B1#01 dosyası dokunulmaz); :01 close / :02:30 open · URL `/algoritma-islemler/b1_05` |
| `temmuzPoly/b1_05_signal.py` | B1#05 eşleme motoru — B1#01 ile aynı fikir ama havuzda **b1_mum + melez** da var (dashboard "coin başına en iyi" kartıyla birebir); türev defterler (b1_01/02/04/05, analiz2) havuz dışı; eşleme her open turunda yeniden hesaplanır → `b1_05_mapping.json` |
| `temmuzPoly/b1_05_backfill.py` | B1#05 geçmişini A2#05 slotlarında walk-forward doldurur (`--write`); seçilen motorun o slottaki gerçek kaydından yön/fiyat/sonuç alır, motor o slotta işlem açmamışsa atlar; `algo_name` = `B1#05←<motor>` (motor bazlı isabet dökümü için) |
| `temmuzPoly/poly_trader_b1_05_live.py` | **B1#05 Live** — gerçek PM, kademe `/ayarlar` → İşlem Miktarları'ndan ayarlanır (varsayılan $4/5/6); sanal B1#05'i aynalar (bağımsız sinyal yok); tek otorite dashboard Ayarlar anahtarı, **varsayılan kapalı**; :02+:12 close / **:06:30** open (`sleep 30`; sanal :06 sonrası); `min_profit_ratio=None` → PM kâr kapısı yok, **sanal ne açarsa aynısı**. ⚠️ Backfill kenar bulamadı — kademe bilerek en düşük |
| `temmuzPoly/poly_trader_b1_mum_live.py` | **B1#03 MUM Live** — gerçek PM, kademe `/ayarlar` (varsayılan $6/8/10); sanal B1#03 MUM'u aynalar; dashboard anahtarı, **varsayılan kapalı**; :02+:12 close / :06 open (sanal :05 state sonrası) |
| `temmuzPoly/poly_trader_c101.py` | **C1#01 · OPUS-OHLCV** sanal (**$1000**) — yön tahmin etmez; 5 puan kenar; kademe **$24/36/48** WR; :01 close / :02 open / :25 backfill · URL `/algoritma-islemler/c101`. Gerçek para yolu yok |
| `temmuzPoly/poly_trader_c101_v2.py` | **C1#01 V2 · GERÇEK ASK** sanal (**$1000**) — C1#01 ile **tek farkı kotasyon kaynağı ve eşik**: iki tarafın CLOB `best_ask`'i + **3 puan** kenar (`C101_V2_EDGE_MIN`). Model/veri/Kelly/settle birebir aynı. `poly_trader_c101.py`'yi import edip globallerini yönlendirir (`analiz6_v4` kalıbı) — **C1#01 dosyası dokunulmaz**. Ayrı state/history/kalibrasyon dosyaları; :01 close / :02 open / :25 backfill · URL `/algoritma-islemler/c101_v2` |
| `temmuzPoly/c101_signal.py` | C1#01 **ve V2'nin ortak** modeli — `P(UP)=Φ(ln(S/PTB)/(σ·√T_kalan))`, sürüklenme sıfır; σ = Parkinson H/L (12s/72s harman) × emir defteri derinlik çarpanı × saat içi aralık çarpanı; funding/OI/taker akışından ±0,05 sınırlı yön eğimi; binary Kelly `(P−p)/(1−p)`. `evaluate(..., edge_min=)` ile defter başına eşik |
| `temmuzPoly/c101_data.py` | C1#01 **OHLCV dışı** veri toplayıcı (Binance Futures public, urllib, /tmp TTL cache): `/fapi/v1/depth` ±%0,1 derinlik+dengesizlik · kline `takerBuyBase` (CVD vekili) · `premiumIndex` funding+z · `openInterestHist` |
| `temmuzPoly/c101_calibration.jsonl` | C1#01 kalibrasyon günlüğü — açılan **ve açılmayan** her değerlendirme (saatte 3 satır); `calib` modu model vs piyasa **Brier skoru** verir. Defterin asıl ölçüm çıktısı. **14.08.2026 15:10–21:20 arası satırlar CLOB ask'e karşı ölçüldü**, öncesi ve sonrası Gamma mid — piyasa Brier'ini karşılaştırırken bu pencereyi ayır |
| `temmuzPoly/c101_v2_calibration.jsonl` | C1#01 V2 kalibrasyon günlüğü — aynı biçim, kotasyon hep ask. `pm_up`/`pm_down` ask, `up_mid`/`down_mid` Gamma mid; iki defterin aynı slotta neye baktığı buradan karşılaştırılır |
| `temmuzPoly/c101_depth_baseline.json` | Sembol başına likidite oranı EWMA referansı; ilk 20 tur derinlik çarpanı 1,0 (etkisiz) |
| `temmuzPoly/algo_islemler_fresh_start.py` | Algoritma-islemler close + **79 defterin** bakiyesini $1000'e sıfırla + **TOP1–4 oy defteri** damgası (cron open bekler, manuel open yok). **t05/t07 kopyaları** da $1000 (yoksa oluşturur). Liste dashboard `_ALGO_ISLEMLER_KEYS` ile birebir; `melez` dosya adı farklı olduğu için `_STATE_FILE_KEY` ile eşlenir. Bayraklar: `--check` (yazmadan eksik dosya raporu) · `--reset-only` · `--wipe-history` (geçmişi `_archive_<tarih>/` klasörüne taşır, silmez) |
| `temmuzPoly/poly_trader_jarvis2026.py` | **JARVIS2026** sanal $1000 · $16/24/32 · evrilen fikir · her dk open · kâr kapısı **%35** (diğer defterler %50) · `:01` close · gerçek PM yok |
| `temmuzPoly/poly_trader_ref01.py` | **REF01** sanal $1000 · $24/36/48 · kâr kapısı **%25** · ask ≤0,75 · her dk open · `:01` close · `daily` 00:00 İST TG (F16 ile aynı format) · gerçek PM yok |
| `temmuzPoly/ref01_signal.py` | REF01 — ilk 6 bps · TREND ≥18 kesişsiz · FADE kesiş <:15 + ters ≥10 · ask_max 0,75 |
| `temmuzPoly/poly_trader_ref02.py` | **REF02** sanal $1000 · trend only · kâr kapısı **%35** · ask ≤0,75 · her dk open · `:01` close · gerçek PM yok |
| `temmuzPoly/ref02_signal.py` | REF02 — aynı yol verisi · yalnız TREND ≥18 kesişsiz · fade yok · ask_max 0,75 |
| `temmuzPoly/poly_trader_ref04.py` | **REF04** sanal $1000 · uç nokta dönüşü + **F16** onayı · ask 0.20–0.35 · her dk open · `:01` close · gerçek PM yok |
| `temmuzPoly/ref04_signal.py` | REF04 — saatlik yol ekstrem ≥25 bps + geri çekilme ≥10 bps · ters yön |
| `temmuzPoly/poly_trader_ref05.py` | **REF05** sanal $1000 · uç nokta dönüşü + **F1#01** onayı · ask 0.20–0.35 · her dk open · `:01` close · gerçek PM yok |
| `temmuzPoly/ref05_signal.py` | REF05 — REF04 ile aynı yol mantığı (import) · F1#01 filtresi trader'da |
| `temmuzPoly/f1_01_signal.py` | F1#01 HMM yönü — `/tmp/f1_signals.json` |
| `temmuzPoly/jarvis2026_signal.py` | Fikir kuralları · `ask_max` taban **0.50** · yol eşiği tavan **6 bps** (evrim daha sıkamaz) |
| `temmuzPoly/jarvis2026_evolve.py` | 2 saatte fikir üretir (`30 */2`); ask_max <0.50 / path_abs >6 yazsa bile sinyal katmanı düzeltir |
| `temmuzPoly/backtest_watch_1y.py` | İzleme 5’li 1Y · F16 = BTC+SOL `predict()` · 00:00 İST · `backtest_watch_1y.json` |
| `temmuzPoly/slot_trader.py` | **:05 / :07 sanal kopya** — aynı 69 algoritma (35 + A1 Top-34), `STATE_FILE`/`HISTORY_FILE` `*_t05_*` / `*_t07_*`; `live_mirror=False`; `close\|open --slot 05\|07`. :02 dosyalarına dokunmaz. Cron :01 close · :05/:07 open |
| `temmuzPoly/algo_consensus_log.py` | Algoritma-islemler **:05 ortak oy** saatlik kayıt + 1h mum sonucu · `algo_consensus.json` · cron `:08` · emir yok; aynı turda `vote_paper` $48 defterini işler |
| `temmuzPoly/algo_consensus.json` | Saat-coin ortak karar geçmişi (BTC/ETH/SOL winner + actual + win) |
| `temmuzPoly/vote_paper.py` | İlk 10 rejim oyu — grup çoğunluğuna **$48** sanal Poly dolum; TOP1 Durgun / TOP2 Trend / TOP3 Canlı / **TOP4 Sembol** · `vote_paper.json` · `balance_reset_at_tr` damgasından sonrası skora girer · gerçek emir yok |
| `temmuzPoly/vote_paper.json` | Rejim başına $48 oy defteri (saat · yön · actual · pnl) |
| `temmuzPoly/poly_slot_paths.py` | Dilim yol eki + `mirror_slot.json` okuma/yazma |
| `temmuzPoly/mirror_slot.json` | Eski manuel dilim dosyası; yayın artık defterin en çok kazandıran :02/:05/:07’si |
| `temmuzPoly/poly_trader_x101.py` | **X1#01 - 13Analiz** — sanal $1000 · BTC/ETH/SOL saatlik; 13 katman + ask kenarı; **`:01` close / `:02` open**; gerçek PM yok |
| `temmuzPoly/x101_signal.py` | X1#01 kontrol listesi (skor ≥64 · MTF 2/3 · ask kenarı ≥3p) |
| `temmuzPoly/poly_trader_e01.py` | **COMBO** — sanal $1000 · A1 + C1#01 + A2#05 V2 oy; çatışmada açmaz; kademe **sembol WR $16 / $24 / $32**; **ask ≤ 0,50** (üstünde kazanç < zarar); **`:01` close / `:02:25` open**; gerçek PM yok · URL `/algoritma-islemler/combo` |
| `temmuzPoly/e01_signal.py` | COMBO oy okuyucu — üç kaynağın o saat açık pozisyonuna bakar, sinyal üretmez |
| `temmuzPoly/poly_trader_e02.py` | **COMBO2** — sanal $1000 · BTC←C1#01 · ETH/SOL←COMBO; **sabit $64**; **`:01` close / `:02:40` open**; gerçek PM yok · URL `/algoritma-islemler/combo2` |
| `temmuzPoly/e02_signal.py` | COMBO2 ayna — BTC C101, ETH/SOL COMBO state; sinyal üretmez |
| `temmuzPoly/pm_fee_backfill.py` | (ops, tek sefer koştu) Geçmiş defterlere PM taker ücretini işler — `pm_fee` yazar, `pnl`'i düşürür, bakiyeyi ücret kadar azaltır. Varsayılan kuru çalışma, `--apply` ile yazar; yedek `_fee_backfill_backup/`. İdempotent (`pm_fee` dolu kaydı atlar) |
| `temmuzPoly/algo_islemler_defer_to_next_hour.py` | (ops) open erteleme — normalde kullanma |
| `temmuzPoly/b1_02_signal.py` | B1#02 sabit sembol→motor eşlemesi |
| `temmuzPoly/analiz6_v3_signal.py` | A6V3 sinyal — BTC/ETH A6, SOL A2 (algo→predict kline dönüşümü) |
| `temmuzPoly/analiz6_v4_signal.py` | MELEZ sinyal — her sembolde uzun dönem isabeti en yüksek motor: BTC→`macd_histogram_div` (%55,0), ETH/SOL→`mean_reversion` (%54,2 / %53,2) |
| `temmuzPoly/analiz6_v4_backfill.py` | MELEZ geçmişini A6V3 (BTC) + A2#05 (ETH/SOL) defterlerinin gerçek kararlarından walk-forward kurar (`--write`); kayıtlar `backfilled: true` |
| `temmuzPoly/backtest_a2_a6_melez_1y.py` | A2#05 · A6V3 · MELEZ — 1Y walk-forward backtest (BTC/ETH/SOL); ay ay Telegram (`--telegram`) |
| `temmuzPoly/backtest_selected_algos_1y.py` | Seçili 8 defter — 1Y walk-forward; $1000 · $24/36/48; model ask + PM ücreti; aylık P&L Telegram |
| `temmuzPoly/backtest_algo_islemler_1y.py` | `/algoritma-islemler` 1Y Poly walk-forward — ask+fee · $24/36/48; çıktı `backtest_algo_islemler_1y.json` |
| `temmuzPoly/algoritma-islemler-1y-poly.pdf` | 1Y sıralama PDF — indir `https://bursaapp.com/download/algoritma-islemler-1y-poly.pdf` |
| `/algoritma-islemler` izleme | Üst sıra F16 · A2#03 · A2#05 · F16V2 · JARVIS2026 · REF01; her kartın altında yıllık backtest (`backtest_watch_1y.json`) |
| `temmuzPoly/pdf_a203_a205_f16_aylik.py` | A2#03 · A2#05 · F16 1Y aylık PDF — `a203-a205-f16-aylik.pdf` |
| `temmuzPoly/backtest_e01_family_1y.py` | A1 · C101 · A2#05 · COMBO — 1Y walk-forward, $1000 · $24/36/48, aylık P&L |
| `temmuzPoly/poly_trader_analiz6_v2_live.py` | A6V2 Live gerçek PM (BTC+ETH); dashboard toggle |
| `temmuzPoly/poly_trader_analiz6_v3_live.py` | A6V3 Live gerçek PM (BTC+ETH+SOL); dashboard toggle |
| `temmuzPoly/poly_trader_analiz6_live.py` | A6 Live gerçek PM; slot gate zayıf saat -%30; sanal A6 adayları |
| `temmuzPoly/poly_live_hourly_common.py` | Saatlik gerçek PM ortak açılış yardımcıları |
| `temmuzPoly/poly_trader_manual_state.json` | Manuel PM işlemleri state (dashboard açık pozisyon) |
| `temmuzPoly/analiz32_5m_adapter.py` | 5M110Analiz → 5m sinyal adaptörü (algo bozulmaz) |
| `temmuzPoly/analiz32_15m_adapter.py` | 5M110Analiz → 15m sinyal adaptörü (110 SOL) |
| `temmuzPoly/pm_balance_hourly.py` | PM portföy saatlik kayıt + 00:00 Telegram özeti + 3 saat peş peşe düşüş ALERT |
| `temmuzPoly/poly_algo_analyst.py` | Poly Algo Analist — **DURDURULDU** (`analyst_control.json` paused · cron yorum) |
| `temmuzPoly/algo_pattern_stats.py` | Defterler arası kalıp istatistikleri — Wilson güven aralığıyla "ikisi aynı yönde açtığında kazanma oranı" ve "indikatör oybirliği" hesaplar (N>=8 izlemede, N>=20 güvenilir); `pattern_stats.json` |
| `temmuzPoly/analyst_common.py` | Analist scriptleri ortak yardımcıları (.env, dashboard API, Telegram, Claude çağrısı) |
| `temmuzPoly/analyst_control.json` | Poly Algo Analist pause (`paused: true` = 3s + günlük kapalı) |
| `temmuzPoly/poly_algo_daily_report.py` | Poly Algo Analist Günlük Rapor — **DURDURULDU** (aynı pause) |
| `temmuzPoly/market_regime.py` | BTC/ETH/SOL 1s ADX+ATR bandı — `/algoritma-islemler` üst şerit · `GET /poly/api/market-regime` |
| `temmuzPoly/algo_signals.py` | 36 saatlik algo sinyali (BTC/ETH/SOL); `/tmp/algo_signals.json` · **:01** (A1 :02 open) + **:04:40** |
| `temmuzPoly/algo_signals_v2.py` | 17 kârlı algo (Analiz 2 sekmesi); `/tmp/algo_signals_v2.json` + `algo_accuracy_v2.json` |
| `temmuzPoly/poly_trader_a1.py` | **A1 Top-34** sanal ($1000 · $24/36/48) — ALGO1 motorları (Grid/LSTM hariç); `live_mirror=False`; `:01 close` / `:02 open` |
| `temmuzPoly/poly_trader_a2.py` | A2 Top 17 sanal trader ($1000, $24/$36/$48 WR); `poly_trader_a2_XX_{state,history}.json` |
| `temmuzPoly/poly_a2_algo_live_core.py` | A2 Live ortak çekirdek — gerçek PM open/close |
| `temmuzPoly/poly_trader_a2_02_live.py` | A2#02 RSI Div Live — $4/5/6; sanal #02 ayrı; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_08_live.py` | A2#08 Williams Live — $4/5/6; sanal #08 ayrı; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_03_live.py` | A2#03 Stoch RSI Live — $4/5/6; sanal #03 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_trader_a2_04_live.py` | A2#04 Schaff Live — $4/5/6; sanal #04 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_a2_algo_live_core.py` | A2 Live çekirdeği — sanal defter mirror/sync (309 gibi); open :07; `A2LiveSpec.min_profit_ratio` ile PM kâr kapısı defter bazlı (`None` = tam ayna) |
| `temmuzPoly/poly_trader_a2_05_live.py` | A2#05 Mean Rev Live — sanal #05 ile birebir sync; $4/5/6; ayarlar aç/kapa |
| `temmuzPoly/poly_trader_a2_06_live.py` | A2#06 Z-Score MR Live — $4/5/6; sanal #06 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_trader_a2_07_live.py` | A2#07 Hurst Live — $4/5/6; sanal #07 ayrı; ayarlar aç/kapa (varsayılan kapalı) |
| `temmuzPoly/poly_a2_algo_trader_core.py` | A2 sanal Top17 ($300); Cum 22:00–Pzt 11:00 open kapalı; #09/#16/#17 → eski ALFA kanalı. `A2Config`'te türev defterler için iki opsiyonel alan: `min_entry_price` (None = taban yok) · `live_mirror` (False = gerçek para aynası hiç çağrılmaz) — **varsayılanlar mevcut 17 defterin davranışı** |
| `temmuzPoly/poly_trader_a2_05_v2.py` | **A2#05 V2 · Z KAPISI** sanal ($1000 · $24/36/48) — A2#05 ile aynı sinyal, **1,0 ≤ \|z\| < 1,5** + **bilet tabanı 0,40**. `live_mirror=False`; **:01 close / :02 open** · URL `/algoritma-islemler/a2_05_v2` |
| `temmuzPoly/a2_05_v2_zlog.py` | A2#05 V2 gölge günlüğü — açılan **ve** z kapısına takılan slotların sonucunu Binance 1h mumundan doldurur (`zbackfill`) ve \|z\| kovası bazında kenar tablosu basar (`zstats`). Komşu bantların cevabı işlem açmadan gelir; günlük `a2_05_v2_zlog.jsonl` |
**Test:** `python3 BistAnaliz/BistHourSinyal/bist_visual_v2.py --test` — örnek BIST Analiz metni.  
`python3 BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py --test` — örnek GÜÇLÜ AL metni (tarama/seans yok).

## Cron
- `BistAnaliz/BistHourSinyal/bist_visual_v2.py 1h` — `1 7-15` + `31 14` iş günü → `/tmp/bist_visual.log`
- `BistAnaliz/BistYapayAnaliz/bist_signal_hunter.py` — `*/5` iş günü → `/tmp/bist_signal_hunter.log`
- ~~`BistAnaliz/backup.py` — `59 23 * * *`~~ **KALDIRILDI (2026-09-09)** — disk doldu; günlük `backups/` arşivi iptal
- `/algoritma-islemler` sanal: `close` **:01** / `open` **:02** (B1#04/#05 `:02:30`, COMBO `:02:25`, COMBO2 `:02:40`). Aynı defterlerin **:05/:07 kopyaları** (F1 dahil) (`slot_trader.py`): close **:01** / open **:05** / **:07**. A5 + Live PM: `close` **:02** / `open` **:05**
- `temmuzPoly/poly_trader_a1.py close/open` — A1 Top-34 sanal ($1000 · $24/36/48); gerçek PM yok; hafta sonu da çalışır
- `temmuzPoly/poly_trader_analiz1.py close/open` — **F16** BTC+SOL **sanal** ($1000 · $24/36/48); hafta sonu da çalışır
- `temmuzPoly/poly_trader_f16v2.py close/open` — **F16V2** BTC/SOL F16 · ETH A2#03 **sanal** ($1000 · $24/36/48); `:01` close / `:02` open; gerçek PM yok
- `temmuzPoly/poly_trader_analiz1.py weekly` — Cumartesi 21:00 haftalık 1 ısı haritası
- `temmuzPoly/poly_trader_analiz1.py daily` — her gün 00:00 İST günlük işlem geçmişi (TG)
- `temmuzPoly/poly_trader_analiz2.py close/open` — 2. Analiz **SOL only** sanal ($300, $12-16-20 WR); open Cum 22:00–Paz 18:00 İST kapalı
- `temmuzPoly/poly_trader_analiz2_live.py close/open` — 2. Analiz **canlı PM** SOL $6-7-8 WR (`PM_ANALIZ2_REAL_ENABLED`; :02/:05; hafta sonu dashboard anahtarı)
- `temmuzPoly/poly_trader_analiz2.py weekly` — Cumartesi 21:00 haftalık 2 ısı haritası
- `temmuzPoly/poly_trader_analiz6.py close/open` — 6. Analiz sanal; **open** aynı adayda A6 Live gerçek PM dener (`PM_ANALIZ6_LIVE_ENABLED` + dashboard)
- `temmuzPoly/poly_trader_analiz6_v2.py close/open` — 6. Analiz V2 sanal (BTC+ETH); A6 ile aynı indikatör; SOL yok; Live yok
- `temmuzPoly/poly_trader_analiz6_live.py close` — A6 Live kapanış :02; open sanal A6 open ile tetiklenir
- `AgustosKripto/crypto_futures_cr6.py close/open/trail` — **Algoritmalar Live** (gerçek Binance); Hurst+A1#11 MR+Z-Score MR+MR çoğunluk oyu; top-4 majors önce; $7×20x; **şu an paused**
- `AgustosKripto/crypto_futures_a139.py close/open/trail/scan` — **A1#39 Live** (gerçek Binance); Test `/kripto/test/a1_39` motoru; $20×7x; **paused**
- **CEBU** — `/kripto/test/cebu` + `/kripto/cebu` sanal; Binance live kapalı. Manuel open yok
- **`/kripto` overview** — MELEZ Test defteri (algoritma 1. sıra; sanal $100×6x, emir yok). Detay `/kripto/test/melez`. A139 Live hâlâ paused
- `AgustosKripto/kaito_paper.py close/open/trail` — **KAITO kağıt defteri**; cr6 ile aynı 4 algo oyu + `conviction_filter` vetosu + $7×20x + ATR kilidi/`exit_policy`, ama **gerçek emir yok** (dosyada emir fonksiyonu geçmez; KAITO zaten `FG_SYMBOLS`'te değil). Amaç: "canlıda sadece KAITO açalım" fikrini kasa riske girmeden ölçmek — Kripto Test'teki +$1.272 rakamı **başka bir stratejiye** ait ($100×6x, 69 defter) ve kenar değil düşen coine short kalmak (t_gün +0,76 · kârın %63'ü 5 işlemde · KAITO 11 günde −%61,3). `stats` ile oku
- `AgustosKripto/skill_audit.py` — elle; **20.826 işlem / 5,2 gün** denetimi: brüt PnL −$694 (t=−0,91 ≈ sıfır), komisyon $9.334 → net **−$10.027**. Eşiği geçen defter **2/103** (şans beklentisi ~26 → gerçek kenar yok). Konsensüs ters çalışıyor: **tam uzlaşı ≥%95 SKILL −%0,066 t=−2,15**, bölünmüş <%65 pozitif. MFE: işlemlerin **%79'u 0,5 ATR'yi geçmiyor** ve tüm zararı bu bant yapıyor (−$19.984)
- **Ölü bant filtresi kurulamaz:** MFE ancak kapanışta bilinir, giriş anında vekil değişken aranmalı. Denenen tüm giriş özellikleri (ATR%, saat, interval, tutma süresi) ileri testte çöktü — eğitimin seçtiği "en iyi 6 saat" testte t=−1,85'e döndü (aşırı uydurma kanıtı). LONG/SHORT asimetrisi drift, yetenek değil
- **Yerine kurulan — güven vetosu:** algo içi skor yüzdeliğinin **üst %20'si** SKILL −%0,065 · t=−3,89 · **5/5 zaman diliminde negatif** · DRIFT yalnız +%0,014 (yani piyasa yönü değil). 52 defterin 37'sinde (%71) mevcut. Konsensüs kesitiyle bağımsız olarak aynı sayı (−0,065 / −0,066). Üst kova atılınca kalanın SKILL'i **−0,000%** — zarar durur, kâr başlamaz. Ters açmanın maker sonrası beklentisi +%0,025 ama **%95 aralık [−0,007%, +0,057%] sıfırı kesiyor** → gerçek parayla ters işlem yok, gölge defter toplanıyor
- `AgustosKripto/funding_harvest.py` — elle / `--tg`; funding oranı taraması, yön riski yok; sembol başına gerçek `fundingIntervalHours` (4h/8h) ile yıllıklandırma
- `AgustosKripto/Algoritmalar/runner.py` · `Analizler/runner.py` — **sayfa yok, cron yok** (2026-08-22). Sinyal modülleri duruyor; sanal defterler `/kripto/test`
- `AgustosKripto/Test/runner.py close/open/trail/scan` — tek kripto sanal runner; `$100×6x`; **max 8**; zaman kapanışı yok · 24s · 3×ATR · ATR kilit; `scan` */10, evren `day_movers` aktif 30+30. PRO: `edge_gate` + süre tavanı, saatlik settle yok. `hero_book("melez")` → `/kripto` overview
- `AgustosKripto/Test/day_movers.py` — `*/30`; 24s en çok artan/azalan 30+30; `data/day_movers.json`; emir yok
- **Forex cron + sayfa bu sunucuda yok** (2026-08-22) — `EylulForex/` silindi; `/forex` → `/poly`; motor CoptC. Manuel open yok
- **Poly→Kripto uyumsuzluğu (ölçüldü, 2026-08-12):** Aynı sinyal Poly'de kâr, kriptoda zarar. Sebep komisyon oranı değil **başabaş eşiği**: Poly'de başabaş = piyasa fiyatı ≈ %49,8 (binary 1:1 ödeme), kriptoda = komisyon + ödeme şekli ⇒ A2#05 %61,7 · A6V3 %70,4 · B1#03 %44,6. Yani kriptoda kâr için ~12 puan daha isabet gerekiyor. 1Y ölçüm (181 bin sinyal, 7 ufuk, drift-nötr SKILL) 4 defterin hiçbirinde komisyonu aşan kenar bulamadı — tek yakın aday A6V3 majör 48s (+%0,109 · t=+2,65) ve o da 840 testlik çoklu-test düzeltmesini geçmiyor. Çözüm bu yüzden "daha iyi ayar" değil **kanıt şartı** (`edge_gate`): kenar yoksa pozisyon açılmaz
- **Çıkış rejimi ölçümü (1Y, `backtest_pro4.py`):** saatlik zorunlu kapanış A2#05'e 34.692 işlem yükledi (−$26.552); aynı sinyal sinyal-dönene-kadar tutulunca 5.841 işlem (−$11.811) → komisyonun **%83'ü** kalkıyor. Kayıp küçülüyor ama kenar olmadığı için kâra dönmüyor; bu yüzden PRO rejimi kapı ile birlikte çalışır
- **Çıkış rejimi TÜM sanal defterlerde değişti (2026-08-15):** … yeni rejim **zaman kapanışı yok · 24s tavan · 3×ATR stop** (canlı ince ayar: önce 6×→4×→3×). **ATR kâr kilidi ARM 0.5** (önce 1.0→0.7→0.5).
 - **Kapanış-sebebi tablosu yanıltıcıydı.** "1h_close −$17.756" satırı sebebi değil sonucu gösteriyordu: ATR kâr kilidi kazananları erken alıp götürünce saatlik kapanışa artık kaybedenler kalıyordu. Ölçüldü (`exit_diag.py`): `atr_stop` işlemlerinin MFE ortalaması 2,26 ATR ve %100'ü silahlanmış; `1h_close` işlemlerinin %83,5'i 0,5 ATR'yi bile görmemiş.
 - **Kanıt yöntemi:** `exit_lab.py` her gerçek işlemi girişi sabit tutup 1m fiyat verisiyle yeniden oynatıyor. Simülatör kayıtlı sonucu **işlem başına medyan $0,000 · p90 $0,030** sapmayla üretiyor (47.371 işlem, sebep örtüşmesi %92,4) — alternatif rejimler bu yüzden güvenilir.
 - **Gerçekçi replay** ((defter, coin) başına tek pozisyon): eski **46.305 işlem · net −$20.255 · komisyon $19.052**; yeni **9.542 işlem · net −$1.916 · komisyon $4.378**. Zararın **%90'ı** siliniyor, komisyonun %77'si.
 - **Ama kâr etmiyor:** en iyi rejimin brüt kenarı %0,059, taker gidiş-dönüş maliyeti %0,100. Gün bazlı kümelenmiş t = **+0,85** (sıfırdan ayırt edilemez). İşlem düzeyi t=+10,5 sahte hassasiyet — 118 defter aynı 30 coinde aynı saatte işlem açıyor, bağımsız birim gün.
 - **Eski rejimin zararı ise istatistiksel olarak gerçekti:** SKILL −0,0126 · t_gün **−3,42**. Yani değişiklik "belki daha iyi" değil, ölçülen bir kanamayı durduruyor.
 - **Elenen alternatifler (aynı veri):** zorunlu kapanışı 2/4/8/12 saate uzatmak (hepsi negatif) · zarar stopunu sıkmak 1×ATR (daha kötü) · ATR kilit parametreleri (fark gürültü) · **geçmiş başarıya göre defter seçmek** — walk-forward'da TERS çalıştı (eğitimde SKILL>0,10 seçilenler testte %0,062 kenar, filtresiz %0,084).
 - **Geri alma:** `exit_policy.json` → `{"enabled": false}`. Kod değişmeden bir sonraki cron turunda eski davranışa döner. `virtual_book.close_all_positions/trail_positions` `policy=None` ile çağrıldığında **eski davranışı korur** (geriye uyumluluk test edildi).
 - `atr_profit_lock.py` modül varsayılanları **değiştirilmedi** — gerçek para yolu (`crypto_futures_cr6`) onu doğrudan import ediyor; yeni eşik pozisyon başına `loss_stop_atr` alanıyla veriliyor.
- **Sahipsiz defter temizlendi (2026-08-15):** `Analizler/data/a4` kataloğdan (`ANALIZ_META`) kaldırılmış ama dosyası kalmıştı; hiçbir `close`/`trail` turu görmediği için **6 pozisyon 55 saattir açıktı** ve ne kapanıyor ne de zarar olarak sayılıyordu. `orphan_scan.py --archive` ile `_archive_orphan_20260815/`'e taşındı (353 kapanmış işlem, bakiye $106,06 / $300). Tarama tüm sistemde başka sahipsiz defter bulmadı.
- **`LEADER_MIN_SKILL` düzeltildi (2026-08-15):** %0,04 → **%0,10**. Eski değerin yorumu "maker gidiş-dönüş" diyordu ama defterler taker ödüyor; 50.554 gerçek işlemden ölçülen fiili maliyet %0,10. Kapı gerçeğin 2,5 katı altında olduğu için masrafını çıkaramayan (defter, coin) çiftlerini "nitelikli" gösteriyordu
- `temmuzPoly/backtest_watch_1y.py` — `0 21 * * *` (00:00 İST); izleme 6’lı 1Y walk-forward → `backtest_watch_1y.json`; sayı her izleme kartının altında; emir yok
- `AgustosKripto/Test/jarvis_report.py` — `0 21 * * *` (00:00 İST); `/kripto/jarvis` sayfasını besler (1. sekme Test + 2. sekme sistem denetimi), veri `/kripto/api/jarvis`. **İlk ölçüm (7 gün · 22.092 işlem):** brüt −$166 · komisyon $13.046 · net −$13.211 — kayıp tamamen komisyon; ortalama SKILL %−0,0044, 24/54 defter pozitif (yazı-tura), Bonferroni |t|≈3,8'i geçen yok. İşlemlerin %79'u süre dolduğu için kapanıyor ve zarar orada; ATR katmanı tek pozitif bileşen (+$1.392). **Sistem denetimi (118 defter · 50.801 işlem):** net −$21.709. 2. sekmede ayrıca **çıkış rejimi paneli** var: eski/yeni rejim karşılaştırması + geçiş sonrası biriken canlı veri (`jarvis_audit._rejim`). **Bulgu kapandı:** `LEADER_MIN_SKILL` %0,04 → %0,10 düzeltildi
- `AgustosKripto/Test/analog.py build/query/eval` — cron yok, elle çalışır; indeks `data/analog_index.npz` (52 MB, 270k pencere). **180g eval** (k=5000, step=4): isabet %49, ort. imzalı getiri **−%0,0023**; üst güven kovasında en fazla +%0,03 — komisyon sonrası işe yaramaz
- `AgustosKripto/Test/backtest_fast.py` — elle; profil sürenin %92'sinin format dönüşümünde geçtiğini gösterdi (`_resample_4h` %59, `_bars_ohlc` %33) → coin başına bir kez ön hesap. A2 Top-17 1Y: 6541s → dakikalar. Sonuçlar `backtest_1y` ile birebir (`--verify`)
- `AgustosKripto/Test/horizon_sweep.py` — elle; A1/A6/A6V2/A6V3 1Y taraması: **hiçbir ufuk %0,10 komisyonu aşmıyor**; edge süreyle büyümüyor, azalıyor (A1 4s'te −%0,056 t=−2,33; A6V3 8s'te −%0,048 t=−2,64). En iyi brüt A6 2s +%0,008 — komisyonun 12'de biri. **A6 = A6V2 birebir aynı** (30 coinlik evrende 27 coin aynı varsayılana düşüyor)
- `AgustosKripto/Test/minute_data.py fetch` — elle; 30 coin × 90g 1m OHLC (`data/minute_cache/`, ~28 MB)
- `AgustosKripto/Test/maker_sim.py` — elle; 88g üst %10 (3180 sinyal): taker net/sinyal **−%0,095**; maker fill **ters seçilim** (dolanlar kötü, kaçanlar brüt +%0,13…+%0,76); limit emir kurtarmıyor
- `twitter_bot/tweet_trade_card.py` — `20 * * * *` saatlik: son 3 saatteki en yüksek %kârlı Test işlemi → giriş/kapanış/kâr görsel kart → @tradecomio tweet; yeni kazanan yoksa atlar (`/tmp/twitter_trade_card.log`)
- `twitter_bot/tweet_forex_wins.py` — `*/30 * * * *`: CEM01 (`/forex/grafik`) son 30 dk kazananları + defter WR, birden fazlaysa aynı görsel (`/tmp/twitter_forex_wins.log`)
- `temmuzPoly/poly_trader_analiz15.py close/open` — **15. Analiz** BTC→A6 · ETH→A8 · SOL→A2 sanal ($300); Cum 22:00–Pzt 11:00 open kapalı
- `temmuzPoly/poly_trader_analiz6.py weekly` — Cumartesi 21:00 haftalık 6 ısı haritası
- `temmuzPoly/poly_trader_analiz15.py weekly` — Cumartesi 21:00 haftalık 15 ısı haritası
- `temmuzPoly/poly_trader_analiz5.py close/open` — **A1 Live**; slot gate: zayıf saat -%30 (hot-hour büyütme kapalı)
- `temmuzPoly/poly_trader_analiz2_live.py close/open` — **A2 Live**; aynı slot gate (zayıf saat -%30)
- `temmuzPoly/pm_weekend_sync.py close/open` — Cum **22:00** / Pzt **11:00** İST erken açılış; A1/A2 Live Pzt **12:00**
- `temmuzPoly/poly_trader_analiz5_midcheck.py` — saat **:30** o saatin açık pozisyonu anlık değer + kotasyon görseli (TG)
- `temmuzPoly/poly_trader_analiz5.py weekly` — Cumartesi 21:00 haftalık 5 ısı haritası
- `temmuzPoly/pm_balance_hourly.py` — saat başı PM portföy kaydı; **00:00 İST** Telegram bakiye özeti; 3 saat peş peşe düşüşte 🔴 ALERT
- `temmuzPoly/algo_signals.py` — `:01` + `:04:40`: 36 algo sinyali → `/tmp/algo_signals.json` (aynı saat refresh accuracy yazmaz)
- `temmuzPoly/algo_signals_v2.py` — `:01` + `:04:40` her saat: 17 kârlı algo (Analiz 2) → `/tmp/algo_signals_v2.json` (`:01` A2#05/:02 open için)
- `temmuzPoly/poly_trader_a2.py` — A2 Top-17 **`:01 close` / `:02 open`** (ayna penceresi ile aynı); A2#05 **bilet tabanı 0,40**; Cmt 21:00 weekly
- `temmuzPoly/poly_trader_a2_{02,03,04,06,07,08,16}_live.py` — `:02 close` / `:05:10 open`: sanal :05:00 sonrası mirror
- `temmuzPoly/poly_trader_a2_05_live.py` — **`:01 close` / `:02:10 open`** (sanal A2#05 :02 sonrası)
# PASIF: `BistAnaliz/yuzdeBist.py` — crontab yorum satırı
# PASIF: `BistAnaliz/bist_scanner.py` — BIST Sinyal bildirim kapalı
# KALDIRILDI: `run_alfa.sh`, `poly_trader_alfa.py`, `alfa_signal.py`, `poly_trader_5m_sol_109.py`, `poly_trader_5m_sol_210.py`, …
# KALDIRILDI (2026-08-14, dosyalar da silindi): `poly_trader_5m_sol_110.py`, `poly_trader_15m_a2.py`, `poly_15m_a2_algo_trader_core.py`, `poly_trader_15m_309_live.py`, `poly_trader_5m_real_stats.py`, `analiz32_15m_signal_snapshot.py` — 15M/5M defterleri (110 · 309 · 316 · 317 + 309 Live) tamamen kaldırıldı
# YOK (disk/crontab): `polyManuel/sol_bot.py`, `temmuzPoly/poly_trader.py`

## Sürekli Çalışan Servisler
- `web/poly_dashboard.py` — port **5050**, **yalnız `127.0.0.1`** (2026-08-14; eskiden `0.0.0.0` idi ve panel `http://IP:5050` ile TLS'siz açılıyordu). Dışarıya nginx `443` üzerinden `bursaapp.com/poly` olarak çıkar; farklı bir arayüze bağlamak gerekirse `POLY_DASHBOARD_HOST`. `/poly` HTML history taramaz; defter geçmişi mtime cache. `systemctl restart poly-dashboard.service` (PID izlemek için: `pgrep -af poly_dashboard.py`)
- `BursaApp/app.py` — port **5051**, `127.0.0.1`; nginx `location /` → rehber (ziyaretçi şifresiz; üye/admin ayrı). `/poly` `/kripto` `/bahis` `/site` hâlâ 5050. `bursaapp.service` · log `/tmp/bursaapp.log` · `ensure_up.py` cron her dk (`systemctl restart`, orphan yedek; eski SIGKILL döngüsü 502 yapıyordu) · nginx `/harita`→5051 (poly ısı `/poly/harita`) · log `/tmp/bursaapp_ensure.log`
- `binance_ws_marks.py` — `binance-ws-marks.service`; tüm perp mark + last. Saatlik yol (BTC/ETH/SOL) aynı WS’ten `apply_prices` (~15 sn). Dashboard yedek thread (flock). Kart / canlı `mark_price` REST'e gitmez.
- Sunucuda `ufw` **aktif**: yalnız **22/80/443** girişe açık, gerisi `deny`. Yeni bir servisi dışarı açacaksanız kural eklemeniz gerekir (`ufw allow …`).

### Ayarlar Live anahtarları (`/ayarlar`)
- 15 satır, `pm_balance_guard._VALID_GROUPS` ile birebir: A1 · A2 · A10 · A6 · A6V2 · A6V3 · A2#16 · A2#02 · A2#03 · A2#04 · A2#05 · A2#06 · A2#07 · A2#08 · A15
- `POST /poly/api/pm-system` **grup adı geldiyse asla ana şaltere düşmez**; bilinmeyen ad `400` döner. Grup adı hiç yoksa (eski çağrı) ana şalter çalışır — hepsini birlikte çevirir
- **2026-08-12 hatası:** POST'ta ayrı bir sabit grup listesi vardı ve `analiz6_v2_live` / `analiz6_v3_live` bu listede yoktu. A6V3'e basınca istek `else` dalına düşüp `toggle_pm_open_paused()` çağırıyor, yani **15 Live defterin hepsini birlikte** açıp kapatıyordu. Liste kaldırıldı; doğrulama tek kaynağa (`_VALID_GROUPS`) bağlandı. A2#16 ve A2#02'nin ayar satırı da yoktu (kaza ile kapanıp geri açılamıyorlardı) — eklendi

## Ayna API — dış sunucu (2026-08-13)
Başka bir sunucunun ":06'da A6V3 ne açtı?" diye sorup aynı işlemi kendi tarafında açması için **salt okunur** uç. Emir tetiklemez, hiçbir state dosyasına yazmaz.

| Uç | Ne döner |
|---|---|
| `GET /kripto/api/lider` | Lider Analiz — Genel ilk 3 + her coin ilk 3 (`overall` · `coins`); `X-Lider-Token` / `?token=` · `.env` `LIDER_API_TOKEN` (yoksa `401`); CORS `*`; `?top=` 1–10. Aynı uç `/site/api/lider` |
| `GET /poly/api/mirror` | 78 defter + **TOP1–4** (hepsi net P&L çoktan aza, `vote_paper: true`); `featured`: COMBO · C101 · A2#05 V2 · F16 · COMBO2 · **F16V2** |
| `GET /poly/api/mirror/<defter>` | Aktif slot pozisyonları + defter özeti; `top1`–`top4` $48 kâğıt açıklar; pozisyonda `slot_tr` · `entry_hour_tr` · `prediction_tr` |
| `GET /poly/api/consensus` | Algoritma oyu şeridi — :05 BTC/ETH/SOL çoğunluk + başarı %; `X-Mirror-Token` / `?token=` · `MIRROR_API_TOKEN`; CORS `*` |

- **Kimlik:** `X-Mirror-Token` başlığı (ya da `?token=`), `.env` → `MIRROR_API_TOKEN`, `secrets.compare_digest`. **Token tanımlı değilse uç tamamen kapalı** (`401`) — yanlışlıkla açık kalmaz.
- **Defter adı esnek:** `a6v3` · `A6V3` · `analiz6_v3` · `b1#05` · `a2#05` · `5` · `top1`–`top4` hepsi çözülür. Takma adlar `_OVERVIEW_SHORT_LABELS`'tan **türetilir** (`_ALGO_SHORT_ALIASES`), elle ikinci liste tutulmaz — yeni defter eklenince kısa adı kendiliğinden çalışır.
- **Slot filtresi:** Her defterin `:02` / `:05` / `:07` kopyasından en yüksek net P&L’li dilim (`best_slot`). `13:05` open → ertesi saat `14:01` close arası `slot_tr: "13:05-14:01"`. Cevapta `open_minute` + `slot_open_tr`. `?slot=02` yalnız teşhis. Önceki saatten kalan stale pozisyonlar **dahil edilmez**. `?all=1` ile hepsi (stale işaretli) gelir.
- **`active_slot.status`:** her zaman `active` (ayna turu atlamasın). **`slot_phase`:** `open` (seçili dakika+) · `pre_open` (`:01`–open öncesi) · `closing` (`:00`). :01'de yeni open yok (settle çakışması).
- **API dilimi:** `GET/POST /poly/api/mirror-slot` (dashboard auth). Detay sayfasından 02/05/07 seçilir.
- **Pozisyon alanları:** `symbol` · `dir` · `amount_usd` · `pm_slug` · `pm_title` · `pm_entry_price` · `slot_tr` · `entry_hour_tr` · `prediction_tr` · `entry_time_tr` · `is_current_slot` · `position_id` (`defter:tarih:saat:sembol` — ayna mükerrer kontrolü için sabit kimlik). `?market=1` (varsayılan) ile `pm_token_id`, `pm_price_now`, `pm_mid_price`, `pm_quote_src`, `pm_price_drift_pct`. `age_sec` gecikme kontrolü için.
- **Kopyalama kararı kaynakta verilir (2026-08-14):** her pozisyonda `copyable` + `block_reason` + `block_detail`; ayna yalnız uygular, eşikleri yeniden yorumlamaz. Engel kodları: `stale_slot` · `stale` · `missing_dir` · `too_old` · `market_closed` · `missing_token` · `no_price` · `price_above_cap` · `price_below_floor` · `adverse_drift` · `no_market_data`. Defter ucunda ayrıca `copyable_count`. **`?market=0` ile karar hesaplanamaz** → alan yazılmamak yerine `no_market_data` ile **kapalı** döner (eksik alan aynada "engel yok" diye okunabiliyordu).
- **Eşikler `policy` altında yayınlanır:** `entry_price_min` 0.40 · `entry_price_max` 0.75 · `max_age_sec` **1200** (20 dk — ayna zinciri ~12 dk gecikmeli; 600 yetmiyordu) · `max_adverse_drift_pct` 40 · `max_spend_ratio` 1.15 · `min_shares` 5.0 (Polymarket alım minimumu). `min_stake_usd` = `5×fiyat/oran`, harcama toleransını aşmayan en küçük niyet tutarı. Her eşik `.env` ile ezilir; **`policy.sources` hangi env anahtarının geçerli olduğunu söyler**, çünkü fiyat eşiklerinin iki adı var: burada `MIRROR_ENTRY_PRICE_MIN/MAX`, ayna sunucusunun kendi kodunda `MIRROR_MIN/MAX_ENTRY_PRICE`. İkisi de okunur, ilki öncelikli.
- **Gece yarısı slot:** `23:02–00:01` kapanırken `00:00` hâlâ 23 slotu; `00:01` pre_open (01:02 beklenir); `00:02+` yeni slot. Pozisyon eşlemesi `_mirror_pos_slot_date` ile giriş gününe sabitlenir.
- **Fiyat = gerçek CLOB best_ask** (`_mirror_ask` → `pm_best_ask`), Gamma mid'i **değil**. Ölçüldü: mid ile ask arası 13 puana kadar açılabiliyor, yani ayna alamayacağı fiyata göre tavan/taban kararı veriyordu (2026-08-13'te ETH 0.77'den doldu, tavan 0.75 iken). Ask okunamazsa mid'e düşülür ve `pm_quote_src` bunu söyler; mid ayrıca `pm_mid_price` alanında durur.
- Kod: `poly_dashboard.py::_mirror_active_slot` · `_mirror_slot_fields` · `_mirror_rows` · `_mirror_market` / `_mirror_ask` · `_mirror_policy` / `_mirror_copy_decision` / `_mirror_min_stake` + iki rota.

## GPSUSDT işlemler API (2026-08-21)
`/forex/gpsusdt/islemler` ekranının salt okunur kopyası. Emir yok, state yazılmaz.

| Uç | Ne döner |
|---|---|
| `GET /forex/api/gpsusdt` | bakiye · açık pozisyon · geçmiş · last_reject · canlı cüzdan |
| `GET /forex/api/gpsusdt/islemler` | aynı |
| `GET /poly/api/forex/gpsusdt` | aynı (eski `/poly/api` yolu) |

- **Kimlik:** `X-Gpsusdt-Token` veya `X-Api-Token` (ya da `?token=`), `.env` → `GPSUSDT_API_TOKEN`. Token yoksa `401`.
- `?limit=` geçmiş satır sayısı (varsayılan 50, tavan 200).

## BIN_XAUUSDT işlemler API (2026-08-21)
`/forex/bin-b103/islemler` ekranının salt okunur kopyası. GPSUSDT API ile aynı biçim. Emir yok.

| Uç | Ne döner |
|---|---|
| `GET /forex/api/bin-b103` | bakiye · açık pozisyon · geçmiş · last_reject · motor · canlı/sanal |
| `GET /forex/api/bin-b103/islemler` | aynı |
| `GET /poly/api/forex/bin-b103` | aynı (eski `/poly/api` yolu) |

- **Kimlik:** `X-Bin-B103-Token` veya `X-Api-Token` (ya da `?token=`), `.env` → `BIN_B103_API_TOKEN`. Yoksa `GPSUSDT_API_TOKEN` kabul. Token yoksa `401`.
- `?limit=` geçmiş satır sayısı (varsayılan 50, tavan 200).

## Telegram
Kök `telegram_config.py`: `BOT_TOKEN`, `CHAT_ID` (varsayılan). İsteğe bağlı `CHAT_ID_BIST_HOUR` (saatlik analiz) ve `CHAT_ID_BIST_SIGNAL` (`bist_signal_hunter` — güçlü AL, örn. 15DakikaYapayZeka; boşsa `CHAT_ID`) ile kanallar ayrılır; hedef `@ad` veya `-100…` grup/kanal ID.

**Poly analiz TG kuralı:** Tüm analizlerde Telegram yalnızca gerçek açılış veya kapanışta gider; “pozisyon yok / sinyal yok / skip / önizleme” log’a yazılır.
