const axios = require('axios');
const config = require('../../config');

const SYSTEM_PROMPT = `Sen bir kripto para piyasasi analiz uzmanisin. Sana bir haber basligi/tweet metni verilecek.
Gorevin bu icerigin kripto para piyasasini (Bitcoin, Ethereum, Solana ve genel kripto piyasasi)
KISA VADEDE (saatler-gunler icinde) NE KADAR ETKILEYECEGINI degerlendirmek.

SADECE asagidaki JSON formatinda cevap ver, baska hicbir metin ekleme:
{
  "impact_score": <1-10 arasi tam sayi, 10=kesinlikle buyuk etki, 1=alakasiz>,
  "direction": "<bullish|bearish|neutral|belirsiz>",
  "reasoning_tr": "<1-2 cumlelik Turkce kisa aciklama>"
}

Yuksek skor (8-10) ornekleri: Fed faiz karari, buyuk bir borsa hack'i, SEC'in ETF onayi/reddi,
buyuk bir ulkenin kripto yasagi/yasallastirmasi, buyuk whale hareketi, stablecoin depeg'i.
Dusuk skor (1-4) ornekleri: genel piyasa yorumlari, kucuk projelerle ilgili haberler,
spekulatif fikir yazilari, gecmis olaylarin tekrar hatirlatilmasi.`;

async function verifyImpact(item) {
  if (!config.ANTHROPIC_API_KEY) {
    console.warn('[LLM] ANTHROPIC_API_KEY tanimli degil, LLM dogrulama atlaniyor.');
    return { impact_score: 0, direction: 'belirsiz', reasoning_tr: 'LLM dogrulama yapilamadi (API key yok).' };
  }

  try {
    const resp = await axios.post(
      'https://api.anthropic.com/v1/messages',
      {
        model: config.ANTHROPIC_MODEL,
        max_tokens: 300,
        system: SYSTEM_PROMPT,
        messages: [
          {
            role: 'user',
            content: `Kaynak: ${item.source}\nBaslik: ${item.title}\nOzet: ${item.summary}`,
          },
        ],
      },
      {
        headers: {
          'x-api-key': config.ANTHROPIC_API_KEY,
          'anthropic-version': '2023-06-01',
          'content-type': 'application/json',
        },
        timeout: 20000,
      }
    );

    const text = resp.data.content?.[0]?.text || '{}';
    const clean = text.replace(/```json|```/g, '').trim();
    const parsed = JSON.parse(clean);
    return parsed;
  } catch (err) {
    console.error('[LLM] Dogrulama hatasi:', err.response?.data || err.message);
    return { impact_score: 0, direction: 'belirsiz', reasoning_tr: 'LLM cagrisi basarisiz oldu.' };
  }
}

module.exports = { verifyImpact };
