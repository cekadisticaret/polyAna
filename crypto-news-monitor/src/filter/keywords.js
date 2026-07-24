const config = require('../../config');

function passesKeywordFilter(item) {
  const text = `${item.title} ${item.summary}`.toLowerCase();
  return config.KEYWORDS.some((kw) => text.includes(kw.toLowerCase()));
}

function filterCandidates(items) {
  return items.filter(passesKeywordFilter);
}

module.exports = { filterCandidates };
