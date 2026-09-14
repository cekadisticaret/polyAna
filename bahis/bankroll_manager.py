"""
bankroll_manager.py
-----------------------------------------------------------------
Value bet bulunduğunda ne kadar stake konacağını hesaplayan katman.
trade_manager.py'deki ATR-bazlı pozisyon boyutlandırma mantığının
bahis karşılığı: risk limitleri, drawdown koruması, günlük/haftalık
tavan ve fractional Kelly ile agresifliği kontrol altına alıyor.

Bağımlılık yok, saf Python. dixonColes.js / elo.js çıktısını
(model olasılığı + piyasa oranı) buraya JSON/dict olarak ver.
-----------------------------------------------------------------
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
import json
import math


class BetStatus(Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"


@dataclass
class BetRecord:
    id: str
    match: str
    market: str          # örn "1X2", "2.5_ust", "KG_var"
    selection: str        # örn "1", "over", "yes"
    model_prob: float
    market_odds: float
    edge: float
    stake: float
    kelly_fraction: float
    placed_at: str
    status: BetStatus = BetStatus.PENDING
    result_pnl: float = 0.0


class BankrollManager:
    """
    Kelly Criterion + risk limitleri ile stake hesaplama ve
    bankroll takibi.
    """

    def __init__(
        self,
        starting_bankroll: float,
        kelly_multiplier: float = 0.25,      # fractional Kelly (full Kelly çok agresif)
        max_stake_pct: float = 0.03,          # tek bahiste bankroll'un max %'si
        max_daily_risk_pct: float = 0.08,     # günlük toplam risk tavanı
        max_open_positions: int = 5,          # aynı anda açık bahis sayısı limiti
        min_edge: float = 0.04,               # fair kenar eşiği (3–5 bant)
        max_drawdown_pct: float = 0.25,       # bu kadar kaybedince sistem durur
        min_odds: float = 1.30,               # çok düşük oranlı bahisleri ele
        max_odds: float = 6.00,               # çok yüksek oran = model güvenilirliği düşük
        max_weekly_risk_pct: float = 0.20,    # haftalık risk tavanı
        use_circuit: bool = True,
    ):
        self.starting_bankroll = starting_bankroll
        self.bankroll = starting_bankroll
        self.peak_bankroll = starting_bankroll

        self.kelly_multiplier = kelly_multiplier
        self.max_stake_pct = max_stake_pct
        self.max_daily_risk_pct = max_daily_risk_pct
        self.max_open_positions = max_open_positions
        self.min_edge = min_edge
        self.max_drawdown_pct = max_drawdown_pct
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.max_weekly_risk_pct = max_weekly_risk_pct
        self.use_circuit = use_circuit

        self.bets: list[BetRecord] = []
        self.halted = False
        self.halt_reason = ""

    # ---------- 1) Kelly hesaplama ----------

    def kelly_fraction(self, model_prob: float, odds: float) -> float:
        """
        Full Kelly formülü: f* = (bp - q) / b
        b = net oran (odds - 1), p = kazanma olasılığı, q = 1 - p
        """
        b = odds - 1
        if b <= 0:
            return 0.0
        p = model_prob
        q = 1 - p
        f_star = (b * p - q) / b
        return max(f_star, 0.0)

    # ---------- 2) Güvenlik / risk kontrolleri ----------

    def current_drawdown_pct(self) -> float:
        if self.peak_bankroll <= 0:
            return 0.0
        return (self.peak_bankroll - self.bankroll) / self.peak_bankroll

    def open_positions_count(self) -> int:
        return sum(1 for b in self.bets if b.status == BetStatus.PENDING)

    def today_risked_amount(self) -> float:
        today = date.today().isoformat()
        return sum(
            b.stake for b in self.bets
            if b.placed_at.startswith(today) and b.status != BetStatus.VOID
        )

    def _check_halt_conditions(self):
        dd = self.current_drawdown_pct()
        if dd >= self.max_drawdown_pct:
            self.halted = True
            self.halt_reason = f"Max drawdown aşıldı: %{dd*100:.1f} (limit %{self.max_drawdown_pct*100:.0f})"

    # ---------- 3) Stake önerisi ----------

    def evaluate_bet(
        self,
        match: str,
        market: str,
        selection: str,
        model_prob: float,
        market_odds: float,
        fair_implied: float | None = None,
        n_legs: int = 1,
    ) -> dict:
        """
        Bir bahis fırsatını değerlendirir, alınmalı mı, ne kadar
        stake konmalı bilgisini döner. Bahsi otomatik kaydetmez -
        onay için ayrı çağrı gerekir (place_bet).
        """
        self._check_halt_conditions()

        result = {
            "match": match,
            "market": market,
            "selection": selection,
            "model_prob": model_prob,
            "market_odds": market_odds,
            "should_bet": False,
            "reject_reason": None,
            "suggested_stake": 0.0,
            "kelly_fraction_raw": 0.0,
            "kelly_fraction_applied": 0.0,
            "edge": 0.0,
        }

        if self.use_circuit:
            from bahis.risk import snapshot
            rs = snapshot()
            if rs.get("halted"):
                result["reject_reason"] = f"Kesici: {rs.get('halt_reason')}"
                return result

        if self.halted:
            result["reject_reason"] = f"Sistem durduruldu: {self.halt_reason}"
            return result

        if not (self.min_odds <= market_odds <= self.max_odds):
            result["reject_reason"] = f"Oran aralık dışı ({self.min_odds}-{self.max_odds})"
            return result

        implied_raw = 1 / market_odds
        implied_prob = fair_implied if fair_implied is not None else implied_raw
        edge = model_prob - implied_prob
        result["edge"] = edge
        result["implied_raw"] = implied_raw
        result["implied_fair"] = implied_prob

        if edge < self.min_edge:
            result["reject_reason"] = f"Fair kenar yetersiz ({edge:.3f} < {self.min_edge})"
            return result

        if self.open_positions_count() >= self.max_open_positions:
            result["reject_reason"] = "Açık pozisyon limiti doldu"
            return result

        # Fractional Kelly — kupon ayak sayısı varyansı 1/√n
        f_raw = self.kelly_fraction(model_prob, market_odds)
        n = max(int(n_legs or 1), 1)
        f_applied = f_raw * self.kelly_multiplier / (n ** 0.5)
        f_applied = min(f_applied, self.max_stake_pct)  # tek bahis tavanı

        stake = self.bankroll * f_applied

        remaining_daily_budget = (self.bankroll * self.max_daily_risk_pct) - self.today_risked_amount()
        if remaining_daily_budget <= 0:
            result["reject_reason"] = "Günlük risk tavanı doldu"
            return result
        stake = min(stake, remaining_daily_budget)

        if self.use_circuit:
            from bahis.risk import allow
            ok, why, clipped = allow(stake)
            if not ok:
                result["reject_reason"] = why or "kesici"
                return result
            stake = min(stake, clipped)

        if stake <= 0:
            result["reject_reason"] = "Hesaplanan stake sıfır veya negatif"
            return result

        result.update({
            "should_bet": True,
            "suggested_stake": round(stake, 2),
            "kelly_fraction_raw": round(f_raw, 4),
            "kelly_fraction_applied": round(f_applied, 4),
        })
        return result

    # ---------- 4) Bahis kaydı ve sonuçlandırma ----------

    def place_bet(self, evaluation: dict) -> BetRecord:
        if not evaluation["should_bet"]:
            raise ValueError(f"Bu bahis reddedildi: {evaluation.get('reject_reason')}")

        bet_id = f"bet_{len(self.bets) + 1}_{int(datetime.now().timestamp())}"
        record = BetRecord(
            id=bet_id,
            match=evaluation["match"],
            market=evaluation["market"],
            selection=evaluation["selection"],
            model_prob=evaluation["model_prob"],
            market_odds=evaluation["market_odds"],
            edge=evaluation["edge"],
            stake=evaluation["suggested_stake"],
            kelly_fraction=evaluation["kelly_fraction_applied"],
            placed_at=datetime.now().isoformat(),
        )
        self.bets.append(record)
        return record

    def settle_bet(self, bet_id: str, won: bool, void: bool = False):
        bet = next((b for b in self.bets if b.id == bet_id), None)
        if not bet:
            raise ValueError(f"Bahis bulunamadı: {bet_id}")

        if void:
            bet.status = BetStatus.VOID
            bet.result_pnl = 0.0
        elif won:
            pnl = bet.stake * (bet.market_odds - 1)
            bet.status = BetStatus.WON
            bet.result_pnl = pnl
            self.bankroll += pnl
        else:
            bet.status = BetStatus.LOST
            bet.result_pnl = -bet.stake
            self.bankroll -= bet.stake

        self.peak_bankroll = max(self.peak_bankroll, self.bankroll)
        self._check_halt_conditions()

    # ---------- 5) Raporlama ----------

    def stats(self) -> dict:
        settled = [b for b in self.bets if b.status in (BetStatus.WON, BetStatus.LOST)]
        won = [b for b in settled if b.status == BetStatus.WON]

        total_staked = sum(b.stake for b in settled)
        total_pnl = sum(b.result_pnl for b in settled)

        return {
            "starting_bankroll": self.starting_bankroll,
            "current_bankroll": round(self.bankroll, 2),
            "peak_bankroll": round(self.peak_bankroll, 2),
            "current_drawdown_pct": round(self.current_drawdown_pct() * 100, 2),
            "roi_pct": round((total_pnl / total_staked * 100), 2) if total_staked else 0.0,
            "total_bets": len(settled),
            "win_rate_pct": round(len(won) / len(settled) * 100, 2) if settled else 0.0,
            "total_pnl": round(total_pnl, 2),
            "open_positions": self.open_positions_count(),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }

    def export_json(self, path: str):
        data = {
            "stats": self.stats(),
            "bets": [
                {**b.__dict__, "status": b.status.value}
                for b in self.bets
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- Kullanım örneği ----------
if __name__ == "__main__":
    bm = BankrollManager(
        starting_bankroll=10000,
        kelly_multiplier=0.25,   # quarter Kelly - temkinli
        max_stake_pct=0.03,
        min_edge=0.03,
    )

    # dixonColes.js / elo.js modelinden gelen bir sonucu simüle ediyoruz
    # (gerçek kullanımda Node servisinden JSON olarak alırsın)
    evaluation = bm.evaluate_bet(
        match="Galatasaray - Fenerbahçe",
        market="1X2",
        selection="1",
        model_prob=0.714,   # Dixon-Coles çıktısı
        market_odds=1.85,   # bahis sitesindeki oran
    )
    print("Değerlendirme:", evaluation)

    if evaluation["should_bet"]:
        bet = bm.place_bet(evaluation)
        print(f"\nBahis alındı: {bet.id}, stake: {bet.stake} TL")

        # Maç sonucu geldiğinde:
        bm.settle_bet(bet.id, won=True)
        print("\nGüncel durum:", bm.stats())

    # Örnek: ikinci bir bahis, edge yetersiz olduğu için reddedilecek
    weak_bet = bm.evaluate_bet(
        match="Beşiktaş - Trabzonspor",
        market="2.5_ust",
        selection="over",
        model_prob=0.52,
        market_odds=1.95,   # implied ~0.513, edge çok düşük
    )
    print("\nZayıf edge örneği:", weak_bet)
