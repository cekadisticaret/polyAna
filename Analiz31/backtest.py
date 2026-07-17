"""
Walk-forward backtest
"""

import json
from typing import List, Dict, Tuple
from dataclasses import dataclass


@dataclass
class BacktestResult:
    total_trades: int
    accuracy: float
    avg_pnl: float
    sharpe: float
    max_drawdown: float
    monthly_returns: Dict[str, float]


def walk_forward_backtest(historical_data: List[Dict], train_days=30, test_days=7, step_days=7):
    sorted_data = sorted(historical_data, key=lambda x: x["timestamp"])
    results = []
    start_idx = 0

    while True:
        train_end = start_idx + train_days * 24
        test_end = train_end + test_days * 24

        if test_end > len(sorted_data):
            break

        train_data = sorted_data[start_idx:train_end]
        test_data = sorted_data[train_end:test_end]

        best_gates = optimize_gates(train_data)
        result = evaluate_period(test_data, best_gates)
        results.append(result)

        start_idx += step_days * 24

    return results


def optimize_gates(train_data: List[Dict]) -> Tuple[int, int]:
    best_acc = 0
    best_gates = (42, 38)

    for up_gate in range(30, 65, 3):
        for down_gate in range(25, 60, 3):
            correct = total = 0
            for record in train_data:
                if not record.get("predicted_dir"):
                    continue

                pred = record["predicted_dir"]
                actual = record.get("actual_dir")
                up_score = record.get("up_score", 0)
                down_score = record.get("down_score", 0)

                if up_score >= up_gate or down_score >= down_gate:
                    if pred == actual:
                        correct += 1
                    total += 1

            if total > 0:
                acc = correct / total
                if acc > best_acc:
                    best_acc = acc
                    best_gates = (up_gate, down_gate)

    return best_gates


def evaluate_period(test_data: List[Dict], gates: Tuple[int, int]) -> BacktestResult:
    up_gate, down_gate = gates
    trades = []
    pnls = []

    for record in test_data:
        if not record.get("predicted_dir"):
            continue

        up_score = record.get("up_score", 0)
        down_score = record.get("down_score", 0)

        if up_score < up_gate and down_score < down_gate:
            continue

        trades.append(record)
        pnls.append(record.get("pnl_pct", 0))

    if not trades:
        return BacktestResult(0, 0, 0, 0, 0, {})

    correct = sum(1 for t in trades if t.get("correct"))

    return BacktestResult(
        total_trades=len(trades),
        accuracy=round(correct / len(trades) * 100, 1),
        avg_pnl=round(sum(pnls) / len(pnls), 3),
        sharpe=calculate_sharpe(pnls),
        max_drawdown=calculate_max_dd(pnls),
        monthly_returns={},
    )


def calculate_sharpe(pnls: List[float], risk_free=0) -> float:
    if not pnls:
        return 0.0
    avg = sum(pnls) / len(pnls)
    variance = sum((p - avg) ** 2 for p in pnls) / len(pnls)
    std = variance ** 0.5
    return round((avg - risk_free) / std if std > 0 else 0, 2)


def calculate_max_dd(pnls: List[float]) -> float:
    cumulative = []
    running = 0
    for p in pnls:
        running += p
        cumulative.append(running)

    peak = 0
    max_dd = 0
    for c in cumulative:
        if c > peak:
            peak = c
        dd = peak - c
        if dd > max_dd:
            max_dd = dd

    return round(max_dd, 3)
