const axios = require('axios');
const crypto = require('crypto');
const config = require('../../config');

function makeId(tweetId) {
  return crypto.createHash('sha256').update('tw_' + tweetId).digest('hex').slice(0, 24);
}

// Twitter/X API v2 recent search: son 7 gun icindeki tweetleri arar.
// "from:kullanici1 OR from:kullanici2 ..." seklinde sorgu olusturuyoruz.
// NOT: Bu endpoint icin en az "Basic" ucretli erisim gerekir (developer.x.com/en/products/x-api).
async function fetchAllTweets() {
  if (!config.TWITTER_BEARER_TOKEN) {
    console.warn('[Twitter] TWITTER_BEARER_TOKEN tanimli degil, Twitter taramasi atlaniyor.');
    return [];
  }

  const cutoff = new Date(Date.now() - config.LOOKBACK_MINUTES * 60 * 1000).toISOString();
  const accountsQuery = config.TWITTER_ACCOUNTS.map((u) => `from:${u}`).join(' OR ');
  const query = `(${accountsQuery}) -is:retweet`;

  try {
    const resp = await axios.get('https://api.twitter.com/2/tweets/search/recent', {
      headers: { Authorization: `Bearer ${config.TWITTER_BEARER_TOKEN}` },
      params: {
        query,
        start_time: cutoff,
        max_results: 50,
        'tweet.fields': 'created_at,author_id,public_metrics',
        expansions: 'author_id',
        'user.fields': 'username',
      },
    });

    const users = {};
    for (const u of resp.data.includes?.users || []) {
      users[u.id] = u.username;
    }

    return (resp.data.data || []).map((tweet) => ({
      id: makeId(tweet.id),
      source: `Twitter:@${users[tweet.author_id] || tweet.author_id}`,
      title: tweet.text.slice(0, 120),
      summary: tweet.text,
      url: `https://x.com/${users[tweet.author_id] || 'i'}/status/${tweet.id}`,
      publishedAt: new Date(tweet.created_at).getTime(),
    }));
  } catch (err) {
    console.error('[Twitter] Cekme hatasi:', err.response?.data || err.message);
    return [];
  }
}

module.exports = { fetchAllTweets };
