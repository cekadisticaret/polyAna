"""BursaApp blog yazıları — SEO how-to / rota içerikleri."""
from __future__ import annotations

from typing import Any

BLOG_KINDS: dict[str, str] = {
    "plan": "Rota planı",
    "gezi": "Gezilecek",
    "yeme": "Yeme-içme",
    "otel": "Konaklama",
    "howto": "Nasıl yapılır",
    "ornek": "Örnek rota",
}

BLOG_POSTS: dict[str, dict[str, Any]] = {
    "bursa-da-kahvalti-nerede": {
        "title": "Bursa’da kahvaltı nerede yapılır?",
        "h1": "Bursa’da kahvaltı nerede yapılır?",
        "desc": "Serpme, köy kahvaltısı ve merkez adresleri — nasıl seçilir, nereye bakılır. BursaApp yeme-içme listesine köprü.",
        "date": "2026-09-03",
        "image": "/static/food/kahvalti-1.jpg",
        "cta_path": "/yeme-icme?kind=kahvalti",
        "cta_label": "Kahvaltı listesi",
        "kind": "yeme",
        "sections": [
            {
                "h2": "Bursa kahvaltısı üç kümeye ayrılır",
                "paras": [
                    "Köy hattı (Cumalıkızık, Hamamlıkızık, Misi): taş ev avlusu, serpme sofra, hafta sonu kalabalık — erken gitmek şart.",
                    "Nilüfer / FSM: uzun oturmalık serpme, rezervasyon telefonla; BursaApp’ten rezervasyon yapılmaz.",
                    "Merkez hızlı kahvaltı: iş günü kısa mola; puan ve ilçe filtresiyle daralt.",
                ],
            },
            {
                "h2": "Listede nasıl filtrelenir?",
                "paras": [
                    '<a href="/yeme-icme?kind=kahvalti">Yeme-içme</a> sayfasında kuruluş türü = kahvaltı, ilçe = Yıldırım veya Nilüfer seç.',
                    "Puana göre sırala; öne çıkanlar editör önceliğidir. Aynı kayıtlar <a href=\"/harita?cat=food\">haritada</a> da görünür.",
                ],
            },
            {
                "h2": "Hafta sonu ipuçları",
                "paras": [
                    "Cumalıkızık’ta 09:00 öncesi veya 14:00 sonrası daha sakin. Araba parkı köy girişinde; yürüyüş için rahat ayakkabı.",
                    "Kalabalık gruplarda işletmeyi önceden ara; BursaApp yalnızca rehberdir, masa ayırtmaz.",
                ],
            },
        ],
        "related": [
            ("bursa-1-gunluk-gezi-plani", "1 günde Bursa"),
            ("bursa-hafta-sonu-2-gun", "Hafta sonu 2 gün"),
        ],
    },
    "bursa-1-gunluk-gezi-plani": {
        "title": "1 günde Bursa: Ulu Cami, hanlar, Cumalıkızık",
        "h1": "1 günde Bursa gezisi: örnek rota",
        "desc": "Ulu Cami–Hanlar–Cumalıkızık sırası, mola ve foto durakları. BursaApp gezilecek listesine köprü.",
        "date": "2026-09-03",
        "image": "/static/visit/ulu-cami.jpg",
        "cta_path": "/gezilecek",
        "cta_label": "Gezilecek yerler",
        "kind": "plan",
        "sections": [
            {
                "h2": "Sabah: tarihi çekirdek",
                "paras": [
                    "09:00 Ulu Cami ve şadırvan avlusu → Koza Han çay molası → Uzun Çarşı kısa tur.",
                    "Tophane saat kulesi ve Osman–Orhan Gazi türbeleri: gün batımı fotoğrafı için akşam da dönebilirsin.",
                ],
            },
            {
                "h2": "Öğle: İskender molası",
                "paras": [
                    "Heykel–Tuzpazarı hattında <a href=\"/blog/bursa-iskender-nerede-yenir\">İskender</a> veya pideli köfte. Öğle sıcağında hanlar gölgesinde yürümek daha konforlu.",
                ],
            },
            {
                "h2": "Öğleden sonra: Cumalıkızık",
                "paras": [
                    "Metro + dolmuş veya araçla Yıldırım’a geç; UNESCO köy sokakları, Cin Aralığı fotoğrafı.",
                    "Uludağ teleferik ayrı güne kalır — 1 günde hem köy hem dağ genelde yetişmez.",
                ],
            },
            {
                "h2": "Listede nereden bakılır?",
                "paras": [
                    '<a href="/gezilecek?tag=unesco">Gezilecek</a> sayfasında UNESCO çipi ve Osmangazi–Yıldırım ilçe filtresi kullan.',
                    "Rotaya eklemek için yer detayından “rotaya ekle” veya <a href=\"/rota\">/rota</a> planlayıcı.",
                ],
            },
        ],
        "related": [
            ("bursa-da-kahvalti-nerede", "Bursa kahvaltı"),
            ("cumalikizik-gezi-rehberi", "Cumalıkızık rehberi"),
        ],
    },
    "bursa-iskender-nerede-yenir": {
        "title": "Bursa İskender nerede yenir? Adres ve seçim rehberi",
        "h1": "Bursa İskender nerede yenir?",
        "desc": "Tereyağlı pide üstü döner: Tuzpazarı, Heykel ve çarşı hattı. Fiyat bandı ve liste filtresi.",
        "date": "2026-09-04",
        "image": "/static/food/iskender-1.jpg",
        "cta_path": "/yeme-icme?q=iskender",
        "cta_label": "İskender araması",
        "kind": "yeme",
        "sections": [
            {
                "h2": "İskender nedir, neden Bursa?",
                "paras": [
                    "Pide dilimleri üzerinde döner, domates sosu, eritilmiş tereyağı ve yoğurt — 19. yüzyıldan beri Bursa imzası.",
                    "Menüde “Bursa kebabı” veya “İskender” yazan yerler aynı aileden; porsiyon ve tereyağ oranı değişir.",
                ],
            },
            {
                "h2": "Hangi semt?",
                "paras": [
                    "Osmangazi merkez (Tuzpazarı, Heykel, Kayhan): yürüyüş turuyla birleşir.",
                    "Nilüfer / Odunluk: park sorunu daha az; aile işletmeleri yoğun.",
                    "Detay: <a href=\"/bursa-iskender\">Bursa İskender</a> yemek sayfası.",
                ],
            },
            {
                "h2": "Listede filtrele",
                "paras": [
                    '<a href="/yeme-icme?dish=iskender">Yemekler → İskender</a> veya arama kutusuna “iskender” yaz.',
                    "Puana göre sırala; fiyat bandı $$–$$$ çoğu klasik ustanın aralığı. Rezervasyon yok — telefon yer detayında.",
                ],
            },
        ],
        "related": [
            ("bursa-da-kahvalti-nerede", "Kahvaltı rehberi"),
            ("bursa-meyhane-ve-raki", "Meyhane ve rakı"),
        ],
    },
    "cumalikizik-gezi-rehberi": {
        "title": "Cumalıkızık gezi rehberi: UNESCO köyü",
        "h1": "Cumalıkızık gezi rehberi",
        "desc": "Osmanlı köy mimarisi, Cin Aralığı, kahvaltı ve ulaşım. Hafta sonu kalabalığına karşı saat önerisi.",
        "date": "2026-09-04",
        "image": "/static/visit/cumalikizik.jpg",
        "cta_path": "/gezilecek?q=cumalıkızık",
        "cta_label": "Cumalıkızık kayıtları",
        "kind": "gezi",
        "sections": [
            {
                "h2": "Neden gidilir?",
                "paras": [
                    "700 yıllık taş ev dokusu, UNESCO listesi, dar sokak fotoğrafları ve köy kahvaltısı.",
                    "Hamamlıkızık komşu köy — daha sakin alternatif; aynı gün ikisi birleştirilebilir.",
                ],
            },
            {
                "h2": "Ne kadar sürer?",
                "paras": [
                    "Yürüyüş + kahvaltı: yarım gün. Sadece fotoğraf turu: 1,5–2 saat.",
                    "Kestane mevsimi (sonbahar) ekstra kalabalık yaratır.",
                ],
            },
            {
                "h2": "Ulaşım",
                "paras": [
                    "Bursaray Uludağ Üniversitesi hattı + dolmuş; özel araçta köy giriş otoparkı.",
                    "Yıldırım ilçe filtresi: <a href=\"/gezilecek?ilce=Y%C4%B1ld%C4%B1r%C4%B1m\">gezilecek liste</a>.",
                ],
            },
        ],
        "related": [
            ("bursa-da-kahvalti-nerede", "Köy kahvaltısı"),
            ("bursa-1-gunluk-gezi-plani", "1 günlük rota"),
        ],
    },
    "golyazi-gezi-rehberi": {
        "title": "Gölyazı gezi rehberi: yarımada ve gün batımı",
        "h1": "Gölyazı gezi rehberi",
        "desc": "Nilüfer’de yarımada köyü, göl manzarası, nilüfer çiçeği mevsimi ve balık molası.",
        "date": "2026-09-04",
        "image": "/static/visit/golyazi.jpg",
        "cta_path": "/gezilecek?q=gölyazı",
        "cta_label": "Gölyazı kayıtları",
        "kind": "gezi",
        "sections": [
            {
                "h2": "Köyün özü",
                "paras": [
                    "Uluabat Gölü yarımadası; taş evler, dar sokak, gün batımı fotoğrafı.",
                    "Apollonia antik izi ve Rum mimarisi hikâyesi yer detaylarında.",
                ],
            },
            {
                "h2": "Ne zaman?",
                "paras": [
                    "Nilüfer çiçeği (yaz): göl yüzeyi yeşil tabaka — erken akşam ışığı ideal.",
                    "Hafta sonu öğleden sonra en yoğun saat; sabah veya gün batımı daha sakin.",
                ],
            },
            {
                "h2": "Yemek molası",
                "paras": [
                    "Sahil balıkçıları Nilüfer yarımadasında; <a href=\"/yeme-icme?q=gölyazı\">yeme-içme araması</a> ile filtrele.",
                    "Merkezden ~40 dk araç; toplu taşıma sınırlı — günü bütün ayır.",
                ],
            },
        ],
        "related": [
            ("bursa-da-kahvalti-nerede", "Misi kahvaltı"),
            ("mudanya-sahil-gezisi", "Mudanya sahil"),
        ],
    },
    "uludag-gezi-rehberi": {
        "title": "Uludağ gezi rehberi: kış kayak, yaz yayla",
        "h1": "Uludağ gezi rehberi",
        "desc": "Teleferik, Sarıalan, kayak sezonu ve yaz yürüyüşü. Bilet ve otel ayrı planlanır.",
        "date": "2026-09-04",
        "image": "/static/visit/uludag.jpg",
        "cta_path": "/gezilecek?q=uludağ",
        "cta_label": "Uludağ kayıtları",
        "kind": "gezi",
        "sections": [
            {
                "h2": "Kış: kayak",
                "paras": [
                    "Oteller bölgesi pistleri; ekipman kiralama otel veya teleskiya yakın.",
                    "Hafta sonu yoğunluk yüksek — konaklama erken ayarlanmalı.",
                ],
            },
            {
                "h2": "Yaz: teleferik ve yayla",
                "paras": [
                    "<a href=\"/gezilecek?q=teleferik\">Bursa Teleferik</a> Teferrüç–Sarıalan; manzara için sabah tercih edilir.",
                    "Piknik ve kısa yürüyüş; sıcak günlerde su ve şapka.",
                ],
            },
            {
                "h2": "Konaklama",
                "paras": [
                    "Dağ otelleri ayrı kategori: <a href=\"/oteller?q=uludağ\">Uludağ otelleri</a>. BursaApp rezervasyon yapmaz.",
                    "Günübirlik için teleferik + Sarıalan yeter; gece kalacaksan otel listesinden telefon al.",
                ],
            },
        ],
        "related": [
            ("bursa-termal-otel-rehberi", "Termal otel"),
            ("bursa-1-gunluk-gezi-plani", "1 günlük merkez"),
        ],
    },
    "iznik-gezi-rehberi": {
        "title": "İznik gezi rehberi: sur, göl ve çini",
        "h1": "İznik gezi rehberi",
        "desc": "Antik Nikaia surları, Ayasofya, göl kenarı ve çini atölyeleri — tam gün rota.",
        "date": "2026-09-04",
        "image": "/static/visit/iznik-surlar.jpg",
        "cta_path": "/gezilecek?ilce=%C4%B0znik",
        "cta_label": "İznik gezilecek",
        "kind": "gezi",
        "sections": [
            {
                "h2": "Tam gün sırası",
                "paras": [
                    "Sabah sur yürüyüşü (Lefke veya İstanbul Kapısı) → İznik Ayasofya → Yeşil Cami çini detayı.",
                    "Öğleden sonra göl kenarı gün batımı; çini atölyesi ziyareti alışveriş değil kültür durak.",
                ],
            },
            {
                "h2": "Bursa merkezden mesafe",
                "paras": [
                    "Otoban ile ~1–1,5 saat; günübirlik ideal. Konaklama gerekmez ama sakin akşam isteyenler İznik’te kalabilir.",
                ],
            },
            {
                "h2": "Listede filtre",
                "paras": [
                    '<a href="/gezilecek?ilce=İznik">İznik ilçe filtresi</a> tüm durakları toplar; harita modu rotayı görselleştirir.',
                ],
            },
        ],
        "related": [
            ("tirilye-zeytinbagi-gezi", "Tirilye"),
            ("mudanya-sahil-gezisi", "Mudanya"),
        ],
    },
    "mudanya-sahil-gezisi": {
        "title": "Mudanya sahil gezisi: yürüyüş ve balık",
        "h1": "Mudanya sahil gezisi",
        "desc": "Sahil yürüyüşü, Mütareke Evi, Tirilye’ye köprü ve balık–rakı molası.",
        "date": "2026-09-04",
        "image": "/static/visit/mudanya-mutareke-evi.jpg",
        "cta_path": "/gezilecek?ilce=Mudanya",
        "cta_label": "Mudanya gezilecek",
        "kind": "gezi",
        "sections": [
            {
                "h2": "Sahil hattı",
                "paras": [
                    "Merkez sahil promenade; bisiklet ve yürüyüş. 1922 Mütareke Evi müze ziyareti kısa durak.",
                    "Güzelyalı ve Trilye aynı gün kombine edilebilir (araç şart).",
                ],
            },
            {
                "h2": "Ne yenir?",
                "paras": [
                    "Balık ve meyhane hattı: <a href=\"/yeme-icme?kind=meyhane&ilce=Mudanya\">Mudanya yeme-içme</a>.",
                    "Akşam rakı sofrası yoğun — cumartesi erken masa için ara.",
                ],
            },
            {
                "h2": "Ulaşım",
                "paras": [
                    "Bursa–Mudanya otobüs/dolmuş; hafta sonu trafik artar. Tirilye için ayrı 20 dk sahil yolu.",
                ],
            },
        ],
        "related": [
            ("tirilye-zeytinbagi-gezi", "Tirilye (Zeytinbağı)"),
            ("bursa-meyhane-ve-raki", "Meyhane rehberi"),
        ],
    },
    "tirilye-zeytinbagi-gezi": {
        "title": "Tirilye (Zeytinbağı) gezi rehberi",
        "h1": "Tirilye (Zeytinbağı) gezi rehberi",
        "desc": "Taş Rum evleri, zeytinlik manzarası, Fatih Camii ve sahil köy atmosferi.",
        "date": "2026-09-04",
        "image": "/static/visit/tirilye.jpg",
        "cta_path": "/gezilecek?q=tirilye",
        "cta_label": "Tirilye kayıtları",
        "kind": "gezi",
        "sections": [
            {
                "h2": "Köyde ne yapılır?",
                "paras": [
                    "Dar taş sokaklar, eski kilise–cami dönüşümü Fatih Camii, zeytinyağı tadımı (sezonunda).",
                    "Fotoğraf için sabah ışığı; öğle güneşi sokaklar sert gölgeli.",
                ],
            },
            {
                "h2": "Mudanya ile birleştir",
                "paras": [
                    "Öğle Mudanya balığı, akşam Tirilye gün batımı — veya tersi. Toplu taşıma zayıf, araç önerilir.",
                ],
            },
            {
                "h2": "Liste",
                "paras": [
                    '<a href="/gezilecek?kind=koy">Köy/kasaba filtresi</a> ve arama “tirilye”.',
                ],
            },
        ],
        "related": [
            ("mudanya-sahil-gezisi", "Mudanya sahil"),
            ("golyazi-gezi-rehberi", "Gölyazı"),
        ],
    },
    "bursa-termal-otel-rehberi": {
        "title": "Bursa termal otel rehberi: Çekirge kaplıca",
        "h1": "Bursa termal otel rehberi",
        "desc": "Çekirge kaplıca hattı, Eski–Yeni Kaplıca ve termal otel seçimi. Rezervasyon otelden.",
        "date": "2026-09-04",
        "image": "/static/visit/eski-kaplica.jpg",
        "cta_path": "/oteller?q=termal",
        "cta_label": "Termal oteller",
        "kind": "otel",
        "sections": [
            {
                "h2": "Çekirge hattı",
                "paras": [
                    "Osmanlı hamam geleneği; kükürtlü su. Eski Kaplıca tarihi yapı, Yeni Kaplıca daha modern tesis.",
                    "Otellerin çoğu hamam + konaklama paketi sunar — fiyat telefonla netleşir.",
                ],
            },
            {
                "h2": "Kimler için?",
                "paras": [
                    "Hafta sonu kaçamağı, romatizma–wellness turu, aile termal tatili.",
                    "Gezi ile birleştirmek: sabah Ulu Cami, öğleden sonra kaplıca.",
                ],
            },
            {
                "h2": "Listede bak",
                "paras": [
                    '<a href="/oteller">Oteller</a> sayfasında arama “termal” veya “çekirge”; örnek gecelik tutar fikir verir, kart çekilmez.',
                ],
            },
        ],
        "related": [
            ("uludag-gezi-rehberi", "Uludağ"),
            ("bursa-hafta-sonu-2-gun", "2 günlük plan"),
        ],
    },
    "bursa-meyhane-ve-raki": {
        "title": "Bursa meyhane ve rakı sofrası rehberi",
        "h1": "Bursa meyhane ve rakı sofrası",
        "desc": "Meze, rakı, Kayhan ve sahil hattı. Kuruluş türü filtresi ve ilçe önerileri.",
        "date": "2026-09-04",
        "image": "/static/food/balikci-raki-mudanya.jpg",
        "cta_path": "/yeme-icme?kind=meyhane",
        "cta_label": "Meyhane listesi",
        "kind": "yeme",
        "sections": [
            {
                "h2": "Semt seçimi",
                "paras": [
                    "Osmangazi (Kayhan, Hisar): klasik meze–rakı, turist–yerel karışık.",
                    "Mudanya / Nilüfer sahil: balık ağırlıklı meyhane.",
                ],
            },
            {
                "h2": "Nasıl seçilir?",
                "paras": [
                    "Meze vitrinini gör, fiyat bandı $$ çoğu sofra için yeterli gösterge.",
                    '<a href="/yeme-icme?kind=meyhane">Kuruluş türü → Meyhane</a> + puana göre sırala.',
                ],
            },
            {
                "h2": "Not",
                "paras": [
                    "BursaApp masa rezervasyonu yapmaz; kalabalık cuma–cumartesi için işletmeyi ara.",
                ],
            },
        ],
        "related": [
            ("bursa-iskender-nerede-yenir", "İskender"),
            ("mudanya-sahil-gezisi", "Mudanya"),
        ],
    },
    "bursa-cafe-rehberi-nilufer": {
        "title": "Bursa cafe rehberi: Nilüfer ve FSM",
        "h1": "Bursa cafe rehberi: Nilüfer",
        "desc": "3. nesil kahve, laptop dostu mekanlar ve FSM–Görükle hattı.",
        "date": "2026-09-04",
        "image": "/static/food/gloria-jeans-nilufer.jpg",
        "cta_path": "/yeme-icme?kind=cafe&ilce=Nil%C3%BCfer",
        "cta_label": "Nilüfer cafeler",
        "kind": "yeme",
        "sections": [
            {
                "h2": "Nilüfer neden ayrı liste?",
                "paras": [
                    "Üniversite ve ofis yoğunluğu → specialty kahve, uzun oturma, priz ve Wi-Fi beklentisi.",
                    "FSM, Görükle, Özlüce farklı kümelenmeler; ilçe filtresi şart.",
                ],
            },
            {
                "h2": "Filtre",
                "paras": [
                    '<a href="/bursa-cafeler">Bursa cafeler</a> landing veya <a href="/yeme-icme?kind=cafe">cafe türü</a>.',
                    "Puana göre sırala; “liste puanı” Google yoğunluklu yerlerde güncellenir.",
                ],
            },
            {
                "h2": "Kahvaltı değil cafe",
                "paras": [
                    "Serpme kahvaltı ayrı kategori — <a href=\"/blog/bursa-da-kahvalti-nerede\">kahvaltı rehberi</a> ile karıştırma.",
                ],
            },
        ],
        "related": [
            ("bursa-da-kahvalti-nerede", "Kahvaltı"),
            ("bursa-iskender-nerede-yenir", "İskender"),
        ],
    },
    "bursa-hafta-sonu-2-gun": {
        "title": "Bursa hafta sonu 2 gün: örnek plan",
        "h1": "Bursa hafta sonu: 2 günlük plan",
        "desc": "Cumartesi merkez + hanlar, Pazar köy veya sahil. Konaklama ve yemek molaları dahil.",
        "date": "2026-09-05",
        "image": "/static/visit/hanlar-kapalicarsi.jpg",
        "cta_path": "/hafta-sonu",
        "cta_label": "Hafta sonu fikirleri",
        "kind": "plan",
        "sections": [
            {
                "h2": "1. gün — tarihi Bursa",
                "paras": [
                    "Kahvaltı merkez veya Çekirge → Ulu Cami, hanlar, Yeşil Türbe → akşam Tophane manzarası.",
                    "Konaklama: Osmangazi oteller veya Çekirge termal.",
                ],
            },
            {
                "h2": "2. gün — köy veya sahil",
                "paras": [
                    "Seçenek A: Cumalıkızık kahvaltı + köy turu.",
                    "Seçenek B: Mudanya–Tirilye sahil (balık öğle, gün batımı).",
                    "Seçenek C: Uludağ teleferik (yaz) veya Gölyazı (göl).",
                ],
            },
            {
                "h2": "Araçlar",
                "paras": [
                    '<a href="/rota">Rota planlayıcı</a>, <a href="/gezilecek">gezilecek</a> ve <a href="/yeme-icme">yeme-içme</a> listelerini birleştir.',
                    "BursaApp bilet veya oda satmaz; tüm rezervasyon işletme/otel telefonu.",
                ],
            },
        ],
        "related": [
            ("bursa-1-gunluk-gezi-plani", "1 gün"),
            ("bursa-termal-otel-rehberi", "Termal otel"),
        ],
    },
    "bursa-hanlar-ve-ulucami": {
        "title": "Bursa hanlar ve Ulu Cami yürüyüş rotası",
        "h1": "Hanlar ve Ulu Cami yürüyüş rotası",
        "desc": "Koza Han, Irgandı, Kapalıçarşı ve Ulu Cami — 2–3 saatlik yürüyüş sırası.",
        "date": "2026-09-05",
        "image": "/static/visit/koza-han.jpg",
        "cta_path": "/gezilecek?q=han",
        "cta_label": "Han ve çarşı",
        "kind": "gezi",
        "sections": [
            {
                "h2": "Rota sırası",
                "paras": [
                    "Ulu Cami avlusu → Koza Han çay → Orhan Camii → Irgandı Köprüsü (akşam ışığı güzel) → Setbaşı.",
                    "Kapalıçarşı ve Uzun Çarşı alışveriş iç içe; pazar günü bazı dükkanlar kapalı.",
                ],
            },
            {
                "h2": "UNESCO",
                "paras": [
                    "Hanlar Bölgesi UNESCO kapsamında; <a href=\"/gezilecek?tag=unesco\">UNESCO filtresi</a> ile tüm duraklar.",
                ],
            },
            {
                "h2": "Yemek molasu",
                "paras": [
                    "Kayhan cantık veya Tuzpazarı İskender — yürüyüş mesafesinde. <a href=\"/blog/bursa-iskender-nerede-yenir\">İskender rehberi</a>.",
                ],
            },
        ],
        "related": [
            ("bursa-1-gunluk-gezi-plani", "1 günlük plan"),
            ("bursa-iskender-nerede-yenir", "İskender"),
        ],
    },
}


def all_blog_posts() -> dict[str, dict[str, Any]]:
    """Statik + cron ile üretilmiş blog yazıları."""
    out = dict(BLOG_POSTS)
    for slug, post in load_generated_posts().items():
        out[slug] = post
    return out


def load_generated_posts() -> dict[str, dict[str, Any]]:
    from weekend_blog import load_generated_posts as _load

    return _load()


def blog_posts_sorted(*, kind: str | None = None) -> list[tuple[str, dict[str, Any]]]:
    items = list(all_blog_posts().items())
    if kind:
        items = [(s, p) for s, p in items if p.get("kind") == kind]
    items.sort(key=lambda x: x[1].get("date", ""), reverse=True)
    return items
