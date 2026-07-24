const TelegramBot = require('node-telegram-bot-api');
const config = require('../../config');

let bot = null;
function getBot() {
  if (!config.TELEGRAM_BOT_TOKEN) return null;
  if (!bot) bot = new TelegramBot(config.TELEGRAM_BOT_TOKEN, { polling: false });
  return bot;
}

const DIRECTION_EMOJI = {
  bullish: '🟢',
  bearish: '🔴',
  neutral: '🟡',
  belirsiz: '⚪',
};

async function sendAlert(item, verdict) {
  const b = getBot();
  if (!b || !config.TELEGRAM_CHAT_ID) {
    console.warn('[Telegram] Bot token / chat id eksik, mesaj gonderilemedi.');
    return;
  }

  const emoji = DIRECTION_EMOJI[verdict.direction] || '⚪';

  const message = [
    `${emoji} *KRIPTO ETKI ALARMI* (skor: ${verdict.impact_score}/10)`,
    ``,
    `*Kaynak:* ${item.source}`,
    `*Baslik:* ${item.title}`,
    ``,
    `*Neden:* ${verdict.reasoning_tr}`,
    ``,
    item.url ? `[Habere git](${item.url})` : '',
  ]
    .filter(Boolean)
    .join('\n');

  try {
    await b.sendMessage(config.TELEGRAM_CHAT_ID, message, {
      parse_mode: 'Markdown',
      disable_web_page_preview: false,
    });
  } catch (err) {
    console.error('[Telegram] Gonderim hatasi:', err.message);
  }
}

module.exports = { sendAlert };
