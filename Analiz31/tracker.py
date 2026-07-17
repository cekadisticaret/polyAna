"""
Tahmin takip ve kayıt
"""

import json
import os
from typing import List
from config import PREDICTION_LOG, HISTORY_FILE


class PredictionTracker:
    def __init__(self):
        self.pending: List[dict] = []

    def log(self, prediction):
        record = {
            "timestamp": prediction.timestamp,
            "symbol": prediction.symbol,
            "predicted_dir": prediction.predicted_dir,
            "prob_up": prediction.prob_up,
            "prob_down": prediction.prob_down,
            "confidence": prediction.confidence,
            "entry_price": prediction.current_price,
            "factors": prediction.factors,
            "htf_bias": prediction.htf_bias,
            "resolved": False,
            "actual_dir": None,
            "exit_price": None,
            "pnl_pct": None,
            "correct": None,
        }
        self.pending.append(record)
        self._append(record, PREDICTION_LOG)

    def resolve(self, symbol: str, klines: List[dict]):
        if not klines:
            return

        next_candle = klines[-1]
        actual_dir = "UP" if next_candle["close"] > next_candle["open"] else "DOWN"

        for record in self.pending[:]:
            if record["symbol"] != symbol or record["resolved"]:
                continue

            if next_candle["open_time"] >= record["timestamp"] * 1000:
                record["resolved"] = True
                record["actual_dir"] = actual_dir
                record["exit_price"] = next_candle["close"]
                record["correct"] = record["predicted_dir"] == actual_dir

                if record["predicted_dir"] == "UP":
                    pnl = (next_candle["close"] - record["entry_price"]) / record["entry_price"]
                else:
                    pnl = (record["entry_price"] - next_candle["close"]) / record["entry_price"]
                record["pnl_pct"] = round(pnl * 100, 3)

                self.pending.remove(record)
                self._append(record, HISTORY_FILE)

    def get_stats(self, last_n: int = 100) -> dict:
        try:
            with open(HISTORY_FILE) as f:
                lines = [json.loads(line) for line in f if line.strip()]
        except FileNotFoundError:
            return {"total": 0, "accuracy": 0, "avg_pnl": 0}

        recent = [r for r in lines if r.get("resolved")][-last_n:]
        if not recent:
            return {"total": 0, "accuracy": 0, "avg_pnl": 0}

        correct = sum(1 for r in recent if r.get("correct"))
        total = len(recent)
        avg_pnl = sum(r.get("pnl_pct", 0) for r in recent) / total

        return {
            "total": total,
            "accuracy": round(correct / total * 100, 1),
            "correct": correct,
            "wrong": total - correct,
            "avg_pnl": round(avg_pnl, 3),
        }

    def _append(self, record: dict, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")
