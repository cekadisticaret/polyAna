# Crypto News Monitor

Kripto piyasasını kısa vadede etkileyebilecek haber/tweet'leri **30 dakikalık periyotlarla**
tarayan, kural filtresi + Claude (LLM) doğrulaması ile "bu kesin etkiler" kararı veren ve
Telegram üzerinden bildiren sistem.

## Nasıl Çalışır

```
RSS feed'ler ──┐
               ├──> anahtar kelime filtresi ──> Claude API (skorlama) ──> skor >= 7 ise Telegram'a gönder
Twitter/X ─────┘
```

1. Her 30 dakikada bir (cron ile) RSS kaynakları ve takip edilen Twitter/X hesapları taranır.
2. Daha önce görülmüş içerikler SQLite üzerinden elenir (tekrar bildirim yapılmaz).
3. Kalan içerikler anahtar kelime listesinden geçirilir (Fed, SEC, ETF, halving, hack, whale vb.)
   — bu, her şeyi Claude'a göndermemek için ucuz ve hızlı bir ön elek.
4. Filtreden geçenler Claude API'ye gönderilir; 1-10 arası "etki skoru", yön (bullish/bearish/
   nötr) ve kısa Türkçe gerekçe döner.
5. Skor eşiği (varsayılan 7) geçilirse Telegram'a alarm mesajı gider.

## Kurulum

```bash
cd crypto-news-monitor
npm install
cp .env.example .env
```

`.env` dosyasını doldur:

- **TELEGRAM_BOT_TOKEN**: BotFather'dan aldığın token (senin var olan botunu da kullanabilirsin,
  ayrı bir komut/handler olarak entegre edilebilir — aşağıda not var).
- **TELEGRAM_CHAT_ID**: Alarmların gideceği chat/kanal ID'si.
- **ANTHROPIC_API_KEY**: console.anthropic.com üzerinden API key.
- **ANTHROPIC_MODEL**: Kod içinde bir varsayılan değer var, ama kullanmadan önce
  https://docs.claude.com/en/docs/about-claude/models adresinden güncel model adını
  kontrol et — model isimlendirmeleri zamanla değişiyor.
- **TWITTER_BEARER_TOKEN**: Twitter/X taraması istiyorsan gerekli (aşağıdaki maliyet notuna bak).
  Boş bırakırsan sistem sadece RSS ile çalışır, hata vermez.

## Twitter/X API — Önemli Maliyet Notu

`recent search` endpoint'i (son 7 gün içindeki tweetleri arama) artık **ücretsiz tier'da yok**.
X'in "Basic" paketi aylık yaklaşık $200 civarında (fiyatlar değişebilir, developer.x.com/en/products/x-api
üzerinden kontrol et). Bearer token'ı olmadan sistem otomatik olarak Twitter taramasını atlar
ve sadece RSS ile devam eder — yani bunu sonradan da ekleyebilirsin, sistemi bozmaz.

Alternatif: Eğer bütçe bir sorunsa, başlangıçta sadece RSS ile çalıştırıp (haber siteleri zaten
çoğu büyük gelişmeyi dakikalar içinde yazıyor), Twitter'ı ihtiyaç oldukça sonra eklemeni öneririm.

## Test Çalıştırma (tek seferlik, cron beklemeden)

```bash
node index.js --once
```

Konsolda hangi kaynaklardan kaç içerik çekildiğini, kaçının filtreden geçtiğini ve
kaç alarm gönderildiğini görürsün.

## Sürekli Çalıştırma (PM2 ile)

```bash
npm install -g pm2   # yoksa
pm2 start index.js --name crypto-news-monitor
pm2 save
pm2 startup          # sunucu yeniden başlayınca otomatik ayağa kalksın diye
```

Logları izlemek için:
```bash
pm2 logs crypto-news-monitor
```

## Ayarları Değiştirme (`config.js`)

- **RSS_FEEDS**: İstediğin kadar RSS kaynağı ekleyebilirsin (herhangi bir haber sitesinin
  RSS linkini bulup ekle).
- **TWITTER_ACCOUNTS**: Takip edilecek hesap listesi (kullanıcı adı, @ olmadan).
- **KEYWORDS**: Ön filtre anahtar kelimeleri. Çok fazla alarm geliyorsa listeyi daraltabilir,
  az geliyorsa genişletebilirsin.
- **MIN_IMPACT_SCORE**: Varsayılan 7. Daha az ama daha kesin alarm istersen 8-9 yap;
  daha erken/geniş uyarı istersen 5-6'ya çek.
- **CRON_SCHEDULE**: Varsayılan `*/30 * * * *` (her 30 dakikada bir). 15 dakikada bir için
  `*/15 * * * *` yeterli.

## Mevcut Telegram Botuna Entegrasyon

Eğer BTC/ETH/SOL özet botun zaten çalışıyorsa, bu sistemi ayrı bir process olarak (ayrı PM2
kaydı) çalıştırman en temizi — ikisi de aynı bot token'ını kullanabilir, farklı chat_id'lere
mesaj atabilir ya da aynı kanala atıp mesaj başlığından ayırt edebilirsin (bu yapıda zaten
"KRIPTO ETKI ALARMI" başlığı ile diğer mesajlardan ayrılıyor).

## Bilinen Sınırlamalar / Sonraki Adımlar (istersen ekleriz)

- Şu an tek yönlü bildirim var; "bu haberi neden önemli bulmadın" gibi bir geri bildirim/
  öğrenme döngüsü yok.
- Duplicate/benzer haberlerin farklı kaynaklardan aynı anda gelmesi durumunda şu an her biri
  ayrı değerlendiriliyor (aynı olayın 3 farklı siteden gelen haberi 3 ayrı alarm olabilir).
  İstersen başlık benzerliğine göre gruplama eklenebilir.
- Skor ve gerekçe geçmişi SQLite'ta tutuluyor ama görüntülemek için şu an bir arayüz yok —
  istersen küçük bir web paneli (senin salon-panel/şirket-panel tarzı) ekleyebiliriz.
