/**
 * dixonColes.js
 * -----------------------------------------------------------------
 * Dixon-Coles Poisson modeli: takım atak/defans gücü + ev sahibi
 * avantajı + düşük skor korelasyon düzeltmesi (rho).
 *
 * Girdi: geçmiş maç sonuçları (ev takım, deplasman takım, skorlar)
 * Çıktı: her takım için attack/defense parametreleri + istediğin
 *        maç için tüm pazarların olasılıkları (1X2, alt/üst, KG,
 *        çifte şans, doğru skor, İY/MS vb.)
 *
 * Bağımlılık yok, saf JS. better-sqlite3 ile veri çekip buraya
 * besleyebilirsin.
 * -----------------------------------------------------------------
 */

// ---------- 1) Yardımcı fonksiyonlar ----------

function factorial(n) {
  let r = 1;
  for (let i = 2; i <= n; i++) r *= i;
  return r;
}

function poissonPmf(lambda, k) {
  return (Math.exp(-lambda) * Math.pow(lambda, k)) / factorial(k);
}

// Dixon-Coles düşük skor düzeltme fonksiyonu (tau)
// 0-0, 1-0, 0-1, 1-1 skorlarında Poisson'un bağımsızlık varsayımını
// gerçek veriyle uyumlu hale getirir.
function tau(x, y, lambda, mu, rho) {
  if (x === 0 && y === 0) return 1 - lambda * mu * rho;
  if (x === 0 && y === 1) return 1 + lambda * rho;
  if (x === 1 && y === 0) return 1 + mu * rho;
  if (x === 1 && y === 1) return 1 - rho;
  return 1;
}

// ---------- 2) Model sınıfı ----------

class DixonColesModel {
  /**
   * @param {Array} matches - [{ home, away, homeGoals, awayGoals, date }]
   * @param {Object} opts - { halfLifeDays, maxIter, rhoInit }
   */
  constructor(matches, opts = {}) {
    this.matches = matches;
    this.halfLifeDays = opts.halfLifeDays || 180; // form ağırlığı: 6 ay yarı ömür
    this.maxIter = opts.maxIter || 300;
    this.teams = [...new Set(matches.flatMap(m => [m.home, m.away]))];
    this.params = {}; // { teamName: { attack, defense } }
    this.homeAdv = 0.25; // ln skalasında başlangıç ev sahibi avantajı
    this.rho = -0.05;
  }

  // Zamana göre ağırlık (yakın maçlar daha önemli)
  timeWeight(matchDate, refDate = new Date()) {
    const days = (refDate - new Date(matchDate)) / (1000 * 60 * 60 * 24);
    const lambda = Math.log(2) / this.halfLifeDays;
    return Math.exp(-lambda * Math.max(days, 0));
  }

  // Basit ama etkili: iteratif MM (moment matching) tahmini.
  // Tam MLE yerine hızlı, prod'a uygun bir yaklaşım.
  fit() {
    const teams = this.teams;
    const att = {}, def = {};
    teams.forEach(t => { att[t] = 1; def[t] = 1; });

    const avgGoals =
      this.matches.reduce((s, m) => s + m.homeGoals + m.awayGoals, 0) /
      (this.matches.length * 2);

    for (let iter = 0; iter < this.maxIter; iter++) {
      const attNum = {}, attDen = {}, defNum = {}, defDen = {};
      teams.forEach(t => { attNum[t] = 0; attDen[t] = 0; defNum[t] = 0; defDen[t] = 0; });

      for (const m of this.matches) {
        const w = this.timeWeight(m.date);
        // Ev sahibi gol beklentisi = attack(home) * defense(away) * homeAdv * ortalama
        const lambda = att[m.home] * def[m.away] * Math.exp(this.homeAdv) * avgGoals;
        const mu = att[m.away] * def[m.home] * avgGoals;

        attNum[m.home] += w * m.homeGoals;
        attDen[m.home] += w * (def[m.away] * Math.exp(this.homeAdv) * avgGoals);
        defNum[m.away] += w * m.homeGoals;
        defDen[m.away] += w * (att[m.home] * Math.exp(this.homeAdv) * avgGoals);

        attNum[m.away] += w * m.awayGoals;
        attDen[m.away] += w * (def[m.home] * avgGoals);
        defNum[m.home] += w * m.awayGoals;
        defDen[m.home] += w * (att[m.away] * avgGoals);
      }

      teams.forEach(t => {
        if (attDen[t] > 0) att[t] = attNum[t] / attDen[t];
        if (defDen[t] > 0) def[t] = defNum[t] / defDen[t];
      });

      // normalize (ortalama attack/defense = 1 olsun, kimlik problemi için)
      const meanAtt = teams.reduce((s, t) => s + att[t], 0) / teams.length;
      const meanDef = teams.reduce((s, t) => s + def[t], 0) / teams.length;
      teams.forEach(t => { att[t] /= meanAtt; def[t] /= meanDef; });
    }

    teams.forEach(t => { this.params[t] = { attack: att[t], defense: def[t] }; });
    this.avgGoals = avgGoals;
    return this.params;
  }

  // İki takımın beklenen gol sayıları (lambda = ev, mu = deplasman)
  expectedGoals(home, away) {
    const h = this.params[home], a = this.params[away];
    if (!h || !a) throw new Error(`Takım bulunamadı: ${home} veya ${away}`);
    const lambda = h.attack * a.defense * Math.exp(this.homeAdv) * this.avgGoals;
    const mu = a.attack * h.defense * this.avgGoals;
    return { lambda, mu };
  }

  // Skor matrisi (0..maxGoals x 0..maxGoals) olasılıkları
  scoreMatrix(home, away, maxGoals = 8) {
    const { lambda, mu } = this.expectedGoals(home, away);
    const matrix = [];
    for (let x = 0; x <= maxGoals; x++) {
      const row = [];
      for (let y = 0; y <= maxGoals; y++) {
        let p = poissonPmf(lambda, x) * poissonPmf(mu, y) * tau(x, y, lambda, mu, this.rho);
        row.push(Math.max(p, 0));
      }
      matrix.push(row);
    }
    // normalize (tau düzeltmesi toplamı hafif bozabilir)
    const total = matrix.flat().reduce((s, p) => s + p, 0);
    return matrix.map(row => row.map(p => p / total));
  }

  // ---------- 3) Pazar hesaplamaları ----------

  markets(home, away, maxGoals = 8) {
    const M = this.scoreMatrix(home, away, maxGoals);
    const n = M.length;

    let pHome = 0, pDraw = 0, pAway = 0;
    let btts = 0; // karşılıklı gol var
    const totalGoalsDist = {}; // toplam gol -> olasılık
    let scoreProbs = [];

    for (let x = 0; x < n; x++) {
      for (let y = 0; y < n; y++) {
        const p = M[x][y];
        if (x > y) pHome += p;
        else if (x === y) pDraw += p;
        else pAway += p;

        if (x > 0 && y > 0) btts += p;

        const tot = x + y;
        totalGoalsDist[tot] = (totalGoalsDist[tot] || 0) + p;

        scoreProbs.push({ score: `${x}-${y}`, p });
      }
    }

    scoreProbs.sort((a, b) => b.p - a.p);

    // Toplam gol alt/üst çizgileri
    const overUnder = {};
    [0.5, 1.5, 2.5, 3.5, 4.5].forEach(line => {
      let under = 0;
      for (let g = 0; g <= Math.floor(line); g++) under += totalGoalsDist[g] || 0;
      overUnder[line] = { under: under, over: 1 - under };
    });

    return {
      matchResult: { "1": pHome, "X": pDraw, "2": pAway },
      doubleChance: {
        "1X": pHome + pDraw,
        "12": pHome + pAway,
        "X2": pDraw + pAway,
      },
      bttsYes: btts,
      bttsNo: 1 - btts,
      overUnder, // { "2.5": { under, over }, ... }
      correctScoreTop5: scoreProbs.slice(0, 5),
      expectedGoals: this.expectedGoals(home, away),
    };
  }

  // Bahis şirketi oranından implied probability + vig temizleme (2 veya 3 yönlü)
  static devig(odds) {
    // odds: [oran1, oran2, ...] -> normalize edilmiş gerçek olasılıklar
    const implied = odds.map(o => 1 / o);
    const sum = implied.reduce((a, b) => a + b, 0); // 1'den büyükse vig var
    return implied.map(p => p / sum);
  }

  // Value bet tespiti: model olasılığı vs piyasa (devig edilmiş) olasılığı
  static findValue(modelProb, marketOdds, minEdge = 0.03) {
    const impliedProb = 1 / marketOdds;
    const edge = modelProb - impliedProb;
    return {
      edge,
      isValue: edge >= minEdge,
      kellyFraction: edge > 0 ? edge / (marketOdds - 1) : 0, // full Kelly
    };
  }
}

module.exports = { DixonColesModel, poissonPmf, tau };

// ---------- 4) Kullanım örneği ----------
if (require.main === module) {
  // Örnek: kendi SQLite'ından çektiğin maçları bu formata sok
  const sampleMatches = [
    { home: "Galatasaray", away: "Fenerbahçe", homeGoals: 2, awayGoals: 1, date: "2026-03-01" },
    { home: "Fenerbahçe", away: "Beşiktaş", homeGoals: 1, awayGoals: 1, date: "2026-02-20" },
    { home: "Beşiktaş", away: "Trabzonspor", homeGoals: 0, awayGoals: 2, date: "2026-02-10" },
    { home: "Trabzonspor", away: "Galatasaray", homeGoals: 1, awayGoals: 3, date: "2026-01-25" },
    { home: "Galatasaray", away: "Beşiktaş", homeGoals: 3, awayGoals: 0, date: "2026-01-10" },
    { home: "Fenerbahçe", away: "Trabzonspor", homeGoals: 2, awayGoals: 0, date: "2025-12-15" },
    // ... gerçek kullanımda tüm sezon / birkaç sezon verisi (100+ maç önerilir)
  ];

  const model = new DixonColesModel(sampleMatches, { halfLifeDays: 200 });
  model.fit();

  console.log("Takım güçleri:", model.params);

  const result = model.markets("Galatasaray", "Fenerbahçe");
  console.log("\nGalatasaray - Fenerbahçe tahmini:");
  console.log("1X2:", result.matchResult);
  console.log("Çifte şans:", result.doubleChance);
  console.log("KG var/yok:", { var: result.bttsYes, yok: result.bttsNo });
  console.log("2.5 alt/üst:", result.overUnder["2.5"]);
  console.log("En olası 5 skor:", result.correctScoreTop5);

  // Value bet örneği: bahis sitesi Galatasaray kazanır'a 1.85 veriyor diyelim
  const value = DixonColesModel.findValue(result.matchResult["1"], 1.85);
  console.log("\nValue bet analizi (GS kazanır @1.85):", value);
}
