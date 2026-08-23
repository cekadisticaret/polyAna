/**
 * elo.js
 * -----------------------------------------------------------------
 * Futbol için uyarlanmış ELO rating sistemi (Glicko benzeri
 * güven aralığı eklentisiyle). Dixon-Coles modeliyle paralel
 * çalıştırılıp "iki model aynı fikirde mi" kontrolü için idealdir.
 *
 * Klasik ELO'dan farkı:
 *  - Gol farkına göre K-faktör ağırlıklandırma (büyük skorlar daha
 *    çok puan taşır ama sqrt ile aşırıya kaçmaz - "gol farmalama"
 *    etkisini sınırlar)
 *  - Ev sahibi avantajı sabit offset olarak eklenir
 *  - RD (rating deviation) ile "bu takımın reytingi ne kadar
 *    güvenilir" bilgisi tutulur - az maç oynayan takımlarda RD
 *    yüksek kalır, tahminlere daha az güvenirsin
 * -----------------------------------------------------------------
 */

class EloModel {
  /**
   * @param {Array} matches - [{ home, away, homeGoals, awayGoals, date }]
   *   (Dixon-Coles ile aynı formatta veri kullanabilirsin)
   * @param {Object} opts
   */
  constructor(matches, opts = {}) {
    this.matches = [...matches].sort((a, b) => new Date(a.date) - new Date(b.date));
    this.baseElo = opts.baseElo || 1500;
    this.baseK = opts.baseK || 20;
    this.homeAdv = opts.homeAdv || 65; // ELO puanı cinsinden ev sahibi avantajı
    this.baseRD = opts.baseRD || 350; // yeni takım / az veri belirsizliği
    this.minRD = opts.minRD || 60;

    this.ratings = {}; // { team: { elo, rd, matchCount } }
  }

  _get(team) {
    if (!this.ratings[team]) {
      this.ratings[team] = { elo: this.baseElo, rd: this.baseRD, matchCount: 0 };
    }
    return this.ratings[team];
  }

  // Beklenen kazanma olasılığı (klasik ELO formülü, ev avantajı dahil)
  expectedScore(ratingA, ratingB) {
    return 1 / (1 + Math.pow(10, (ratingB - ratingA) / 400));
  }

  // Gol farkına göre K çarpanı - 1 fark ile 4 fark aynı ağırlıkta olmasın
  // ama sınırsız da büyümesin diye sqrt kullanılıyor (yaygın bir pratik)
  goalDiffMultiplier(goalDiff) {
    return Math.sqrt(Math.max(goalDiff, 1));
  }

  fit() {
    for (const m of this.matches) {
      const home = this._get(m.home);
      const away = this._get(m.away);

      // Maç sonucu: 1 = ev kazandı, 0.5 = berabere, 0 = deplasman kazandı
      let actualHome;
      if (m.homeGoals > m.awayGoals) actualHome = 1;
      else if (m.homeGoals === m.awayGoals) actualHome = 0.5;
      else actualHome = 0;

      const expectedHome = this.expectedScore(
        home.elo + this.homeAdv,
        away.elo
      );

      const goalDiff = Math.abs(m.homeGoals - m.awayGoals);
      const mult = this.goalDiffMultiplier(goalDiff);

      // RD arttıkça (belirsizlik yüksekken) K-faktör büyür - yeni takımlar
      // gerçek seviyesine daha hızlı yaklaşır
      const kHome = this.baseK * mult * (home.rd / this.baseRD);
      const kAway = this.baseK * mult * (away.rd / this.baseRD);

      home.elo += kHome * (actualHome - expectedHome);
      away.elo += kAway * ((1 - actualHome) - (1 - expectedHome));

      // RD zamanla daralır (daha çok maç = daha güvenilir reyting)
      home.matchCount++;
      away.matchCount++;
      home.rd = Math.max(this.minRD, this.baseRD / Math.sqrt(home.matchCount));
      away.rd = Math.max(this.minRD, this.baseRD / Math.sqrt(away.matchCount));
    }
    return this.ratings;
  }

  // Maç öncesi olasılık tahmini (1X2)
  predictMatch(home, away) {
    const h = this._get(home);
    const a = this._get(away);

    const pHomeWin = this.expectedScore(h.elo + this.homeAdv, a.elo);
    // Beraberlik olasılığını basit bir yaklaşımla ELO farkından türetiyoruz:
    // fark küçükse beraberlik ihtimali yüksek, fark büyüdükçe düşer
    const eloDiff = Math.abs(h.elo + this.homeAdv - a.elo);
    const pDraw = Math.max(0.18, 0.32 - eloDiff / 1000);

    // pHomeWin aslında "ev kazanır ya da berabere" tipi bir skor değil,
    // düzeltip üç olasılığı normalize ediyoruz
    let pHome = pHomeWin - pDraw / 2;
    let pAway = (1 - pHomeWin) - pDraw / 2;
    pHome = Math.max(pHome, 0.02);
    pAway = Math.max(pAway, 0.02);

    const total = pHome + pDraw + pAway;
    return {
      "1": pHome / total,
      X: pDraw / total,
      "2": pAway / total,
      confidence: {
        home: { elo: h.elo, rd: h.rd, matches: h.matchCount },
        away: { elo: a.elo, rd: a.rd, matches: a.matchCount },
        // rd toplamı yüksekse (az veri) bu tahmine az güven
        reliable: h.rd < 150 && a.rd < 150,
      },
    };
  }

  // Dixon-Coles çıktısıyla karşılaştırıp uyum kontrolü yapar
  static agreementCheck(eloProbs, dixonColesProbs, threshold = 0.15) {
    const diffs = {
      "1": Math.abs(eloProbs["1"] - dixonColesProbs["1"]),
      X: Math.abs(eloProbs.X - dixonColesProbs.X),
      "2": Math.abs(eloProbs["2"] - dixonColesProbs["2"]),
    };
    const maxDiff = Math.max(diffs["1"], diffs.X, diffs["2"]);
    return {
      diffs,
      maxDiff,
      // iki model de benzer sonuca varıyorsa güven yüksek
      agree: maxDiff <= threshold,
    };
  }

  ranking() {
    return Object.entries(this.ratings)
      .sort((a, b) => b[1].elo - a[1].elo)
      .map(([team, r]) => ({ team, elo: Math.round(r.elo), rd: Math.round(r.rd), matches: r.matchCount }));
  }
}

module.exports = { EloModel };

// ---------- Kullanım örneği ----------
if (require.main === module) {
  const sampleMatches = [
    { home: "Galatasaray", away: "Fenerbahçe", homeGoals: 2, awayGoals: 1, date: "2026-03-01" },
    { home: "Fenerbahçe", away: "Beşiktaş", homeGoals: 1, awayGoals: 1, date: "2026-02-20" },
    { home: "Beşiktaş", away: "Trabzonspor", homeGoals: 0, awayGoals: 2, date: "2026-02-10" },
    { home: "Trabzonspor", away: "Galatasaray", homeGoals: 1, awayGoals: 3, date: "2026-01-25" },
    { home: "Galatasaray", away: "Beşiktaş", homeGoals: 3, awayGoals: 0, date: "2026-01-10" },
    { home: "Fenerbahçe", away: "Trabzonspor", homeGoals: 2, awayGoals: 0, date: "2025-12-15" },
  ];

  const elo = new EloModel(sampleMatches);
  elo.fit();

  console.log("Sıralama:");
  console.table(elo.ranking());

  const pred = elo.predictMatch("Galatasaray", "Fenerbahçe");
  console.log("\nGalatasaray - Fenerbahçe (ELO):", pred);

  // Dixon-Coles çıktısıyla karşılaştırma örneği (dixonColes.js'den gelen sonuç)
  const dcProbs = { "1": 0.714, X: 0.173, "2": 0.113 };
  const check = EloModel.agreementCheck(
    { "1": pred["1"], X: pred.X, "2": pred["2"] },
    dcProbs
  );
  console.log("\nİki model uyum kontrolü:", check);
}
