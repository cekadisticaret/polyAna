const config = require('../config');
const db = require('./db');
const { fetchAllRssItems } = require('./fetchers/rss');
const { fetchAllTweets } = require('./fetchers/twitter');
const { filterCandidates } = require('./filter/keywords');
const { verifyImpact } = require('./llm/verify');
const { sendAlert } = require('./telegram/notify');

async function runScan() {
  const startedAt = new Date().toISOString();
  console.log(`\n[Scan] Baslatildi: ${startedAt}`);

  const [rssItems, tweetItems] = await Promise.all([
    fetchAllRssItems(),
    fetchAllTweets(),
  ]);

  const allItems = [...rssItems, ...tweetItems];
  console.log(`[Scan] Toplam ${allItems.length} yeni icerik cekildi (RSS: ${rssItems.length}, Twitter: ${tweetItems.length})`);

  // daha once gorulenleri ele
  const freshItems = allItems.filter((item) => !db.isSeen(item.id));
  console.log(`[Scan] ${freshItems.length} tanesi daha once gorulmemis`);

  // kural tabanli on-filtre
  const candidates = filterCandidates(freshItems);
  console.log(`[Scan] ${candidates.length} tanesi anahtar kelime filtresinden gecti`);

  let alertCount = 0;

  for (const item of candidates) {
    const verdict = await verifyImpact(item);

    db.markSeen({
      id: item.id,
      source: item.source,
      title: item.title,
      url: item.url,
      impact_score: verdict.impact_score,
      notified: verdict.impact_score >= config.MIN_IMPACT_SCORE,
    });

    if (verdict.impact_score >= config.MIN_IMPACT_SCORE) {
      await sendAlert(item, verdict);
      alertCount++;
      console.log(`[Scan] ALARM -> ${item.source} | skor:${verdict.impact_score} | ${item.title}`);
    }
  }

  // filtreden gecmeyenleri de "gorulmus" olarak isaretle ki tekrar tekrar islenmesin
  const nonCandidates = freshItems.filter((f) => !candidates.includes(f));
  for (const item of nonCandidates) {
    db.markSeen({ id: item.id, source: item.source, title: item.title, url: item.url });
  }

  db.cleanup();
  console.log(`[Scan] Tamamlandi. ${alertCount} alarm gonderildi.`);
}

module.exports = { runScan };
