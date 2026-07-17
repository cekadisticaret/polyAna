#!/usr/bin/env python3
"""
Analiz31 - Ana çalıştırma
"""

import asyncio
import argparse
from datetime import datetime

from data_fetcher import fetch_all_data
from features import extract_all_features
from predictor import predict, Prediction
from tracker import PredictionTracker
from backtest import walk_forward_backtest
from config import SYMBOLS, PREDICTION_LOG


async def run_once(symbol: str, tracker: PredictionTracker):
    print(f"\n{'='*50}")
    print(f"🔮 {symbol} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    raw_data = await fetch_all_data(symbol)
    if not raw_data.get("timeframes", {}).get("1h"):
        print("❌ Veri alınamadı")
        return

    features = extract_all_features(raw_data)
    pred = predict(symbol, {"features": features})

    if not pred:
        print("❌ Tahmin üretilemedi")
        return

    print(f"\n💰 Fiyat: ${pred.current_price:,.2f}")
    print(f"📊 HTF Bias: {pred.htf_bias}")
    print(f"\n🎯 Tahmin: {pred.predicted_dir or 'BEKLE'}")
    print(f"   UP: {pred.prob_up:.1%} | DOWN: {pred.prob_down:.1%}")
    print(f"   Güven: {pred.confidence:.1%}")
    print(f"\n📈 Skorlar: UP={pred.up_score}/{pred.up_gate} | DOWN={pred.down_score}/{pred.down_gate}")
    print(f"\n📝 Faktörler:")
    for f in pred.factors:
        print(f"   • {f}")

    tracker.log(pred)
    print(f"\n✅ Kaydedildi")


async def run_loop():
    tracker = PredictionTracker()

    while True:
        for symbol in SYMBOLS:
            await run_once(symbol, tracker)

        stats = tracker.get_stats(last_n=50)
        print(f"\n{'='*50}")
        print(f"📊 Son 50 Tahmin İstatistiği:")
        print(f"   Doğruluk: {stats['accuracy']}% ({stats['correct']}/{stats['total']})")
        print(f"   Ort. PnL: {stats['avg_pnl']}%")
        print(f"{'='*50}")

        await asyncio.sleep(3600)


async def backtest_mode(history_file: str):
    with open(history_file) as f:
        data = [json.loads(line) for line in f if line.strip()]

    results = walk_forward_backtest(data)

    print(f"\n{'='*50}")
    print("WALK-FORWARD BACKTEST SONUÇLARI")
    print(f"{'='*50}")

    total_acc = []
    for i, r in enumerate(results):
        print(f"\nDönem {i+1}:")
        print(f"  Trades: {r.total_trades}")
        print(f"  Doğruluk: {r.accuracy}%")
        print(f"  Ort. PnL: {r.avg_pnl}%")
        print(f"  Sharpe: {r.sharpe}")
        print(f"  Max DD: {r.max_drawdown}%")
        total_acc.append(r.accuracy)

    print(f"\n{'='*50}")
    print(f"ORTALAMA DOĞRULUK: {sum(total_acc)/len(total_acc):.1f}%")
    print(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(description="Analiz31")
    parser.add_argument("--once", action="store_true", help="Tek çalıştırma")
    parser.add_argument("--loop", action="store_true", help="Sürekli çalışma")
    parser.add_argument("--backtest", type=str, help="Backtest dosyası")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Sembol")

    args = parser.parse_args()

    if args.backtest:
        import json
        asyncio.run(backtest_mode(args.backtest))
    elif args.loop:
        asyncio.run(run_loop())
    else:
        tracker = PredictionTracker()
        asyncio.run(run_once(args.symbol, tracker))


if __name__ == "__main__":
    main()
