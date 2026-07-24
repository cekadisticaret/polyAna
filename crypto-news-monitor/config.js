const path = require('path');
require('dotenv').config();
// Proje kokundeki .env (TELEGRAM_TOKEN / TELEGRAM_CHAT vb.)
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

module.exports = {
  // ---- Tarama periyodu ----
  // node-cron formatinda. Varsayilan: her 30 dakikada bir (saat basi ve 30'da)
  CRON_SCHEDULE: process.env.CRON_SCHEDULE || '*/30 * * * *',

  // ---- Telegram ----
  TELEGRAM_BOT_TOKEN:
    process.env.TELEGRAM_BOT_TOKEN ||
    process.env.TELEGRAM_TOKEN ||
    process.env.TELEGRAM_LAB_BOT_TOKEN ||
    '',
  TELEGRAM_CHAT_ID:
    process.env.TELEGRAM_CHAT_ID ||
    process.env.TELEGRAM_CHAT ||
    process.env.TELEGRAM_LAB_CHAT_ID ||
    '',

  // ---- Anthropic (Claude) API - LLM dogrulama icin ----
  ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY || '',
  // NOT: Model stringini kullanmadan once https://docs.claude.com/en/docs/about-claude/models
  // adresinden guncel model adini kontrol et. Asagidaki deger yaklasik/placeholder'dir.
  ANTHROPIC_MODEL: process.env.ANTHROPIC_MODEL || 'claude-sonnet-4-5-20250929',

  // ---- Twitter/X API v2 (Recent Search) ----
  // Bearer token icin en az "Basic" ucretli tier gerekiyor (aylik ~$200, 15 Temmuz 2026 itibariyle
  // fiyatlar degismis olabilir, developer.x.com/en/products/x-api uzerinden kontrol et)
  TWITTER_BEARER_TOKEN: process.env.TWITTER_BEARER_TOKEN || '',

  // Takip edilecek Twitter/X hesaplari (kullanici adi, @ olmadan)
  TWITTER_ACCOUNTS: [
    'federalreserve',
    'SECGov',
    'coindesk',
    'Cointelegraph',
    'WhaleAlert',
    'DocumentingBTC',
    'BitcoinMagazine',
    // kendi listene gore ekle/cikar
  ],

  // RSS kaynaklari (haber siteleri)
  RSS_FEEDS: [
    { name: 'CoinDesk', url: 'https://www.coindesk.com/arc/outboundfeeds/rss/' },
    { name: 'Cointelegraph', url: 'https://cointelegraph.com/rss' },
    { name: 'Decrypt', url: 'https://decrypt.co/feed' },
    { name: 'The Block', url: 'https://www.theblock.co/rss.xml' },
    { name: 'Reuters Business', url: 'https://feeds.reuters.com/reuters/businessNews' },
    { name: 'Federal Reserve Press Releases', url: 'https://www.federalreserve.gov/feeds/press_all.xml' },
    { name: 'SEC Press Releases', url: 'https://www.sec.gov/news/pressreleases.rss' },
  ],

  // ---- Kural tabanli on-filtre: bu kelimelerden biri gecmiyorsa LLM'e gonderilmez ----
  // (maliyet ve gurultu azaltmak icin ilk elek)
  KEYWORDS: [
    // Makro / merkez bankasi
    'fed', 'federal reserve', 'interest rate', 'faiz', 'powell', 'fomc',
    'inflation', 'enflasyon', 'cpi', 'recession',
    // Regulasyon
    'sec', 'cftc', 'regulation', 'regulasyon', 'lawsuit', 'dava', 'ban', 'yasak',
    'etf', 'approval', 'onay', 'reject', 'red',
    // Kripto-spesifik buyuk olaylar
    'halving', 'hack', 'exploit', 'rugpull', 'bankruptcy', 'iflas',
    'whale', 'liquidation', 'likidasyon', 'delisting', 'listing',
    'bitcoin', 'ethereum', 'btc', 'eth', 'sol', 'solana', 'stablecoin',
    'tether', 'usdt', 'usdc', 'binance', 'coinbase', 'blackrock',
    // Jeopolitik / genel piyasa sokları
    'war', 'savas', 'sanctions', 'yaptirim', 'tariff', 'gumruk vergisi',
  ],

  // Kac dakikadan eski haberler/tweetler yok sayilsin (tekrar taramada eskiyi tekrar bildirmemek icin)
  LOOKBACK_MINUTES: 35,

  // LLM'in "kesin etkiler" demesi icin minimum skor (1-10 arasi)
  MIN_IMPACT_SCORE: 7,

  DB_PATH: process.env.DB_PATH || './data/monitor.db',
};
