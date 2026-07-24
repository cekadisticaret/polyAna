const Parser = require('rss-parser');
const crypto = require('crypto');
const config = require('../../config');

const parser = new Parser({ timeout: 10000 });

function makeId(url, title) {
  return crypto.createHash('sha256').update((url || '') + (title || '')).digest('hex').slice(0, 24);
}

async function fetchAllRssItems() {
  const cutoff = Date.now() - config.LOOKBACK_MINUTES * 60 * 1000;
  const results = [];

  for (const feed of config.RSS_FEEDS) {
    try {
      const parsed = await parser.parseURL(feed.url);
      for (const item of parsed.items || []) {
        const pubDate = item.isoDate ? new Date(item.isoDate).getTime() : Date.now();
        if (pubDate < cutoff) continue;

        results.push({
          id: makeId(item.link, item.title),
          source: `RSS:${feed.name}`,
          title: item.title || '',
          summary: (item.contentSnippet || item.content || '').slice(0, 500),
          url: item.link || '',
          publishedAt: pubDate,
        });
      }
    } catch (err) {
      console.error(`[RSS] ${feed.name} cekilemedi:`, err.message);
    }
  }

  return results;
}

module.exports = { fetchAllRssItems };
