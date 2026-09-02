"""Optimize FVG Reversal strategy parameters.

Tests different parameter combinations to find the optimal settings
for the strategy.

Usage:
    python scripts/optimize_strategy.py
    python scripts/optimize_strategy.py --days 30
    python scripts/optimize_strategy.py --optimize-all
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.types import Candle, Direction
from src.structure.context import ContextBuilder
from src.strategies.fvg_reversal import FVGReversalStrategy
from src.ai.scorer import RuleBasedScorer


class StrategyOptimizer:
    """Optimize strategy parameters through grid search."""

    def __init__(self):
        self.results = []

    def load_data(self, period: str = "6mo") -> list[Candle]:
        """Load gold data."""
        gold = yf.Ticker("GC=F")
        df = gold.history(period=period, interval="1d")

        candles = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime().replace(tzinfo=None)
            candles.append(Candle(
                timestamp=ts,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0)),
            ))
        return candles

    def test_parameters(
        self,
        candles: list[Candle],
        min_rr: float = 2.0,
        min_ai_score: int = 70,
        risk_per_trade: float = 0.01,
        max_trades_per_day: int = 1,
        lookback: int = 30,
    ) -> dict:
        """Test a specific parameter combination."""
        strategy = FVGReversalStrategy()
        context_builder = ContextBuilder()
        ai_scorer = RuleBasedScorer()

        initial_balance = 10000.0
        equity = initial_balance
        peak_equity = equity
        max_drawdown = 0
        trades = []
        daily_trades = {}  # Track trades per day

        for i in range(lookback, len(candles)):
            current_candle = candles[i]
            current_price = current_candle.close
            current_date = current_candle.timestamp.date()

            # Check daily trade limit
            if daily_trades.get(current_date, 0) >= max_trades_per_day:
                continue

            # Check if in trade
            for trade in trades[:]:
                if trade["status"] == "OPEN":
                    hit = False
                    exit_price = 0

                    if trade["direction"] == "BUY":
                        if current_candle.low <= trade["sl"]:
                            hit = True
                            exit_price = trade["sl"]
                        elif current_candle.high >= trade["tp"]:
                            hit = True
                            exit_price = trade["tp"]
                    else:
                        if current_candle.high >= trade["sl"]:
                            hit = True
                            exit_price = trade["sl"]
                        elif current_candle.low <= trade["tp"]:
                            hit = True
                            exit_price = trade["tp"]

                    if hit:
                        if trade["direction"] == "BUY":
                            pnl = (exit_price - trade["entry"]) * trade["volume"] * 100
                        else:
                            pnl = (trade["entry"] - exit_price) * trade["volume"] * 100

                        pnl -= 7.0 * trade["volume"]  # Commission
                        equity += pnl
                        trade["status"] = "CLOSED"
                        trade["pnl"] = round(pnl, 2)
                        trade["outcome"] = "WIN" if pnl > 0 else "LOSS"
                        trades.append(trade)
                        trades.remove(trade)

            # Build context
            available = candles[max(0, i-lookback):i+1]
            try:
                ctx = context_builder.build(
                    symbol="XAUUSD",
                    candles_by_tf={"M15": available, "H4": available, "H1": available},
                    primary_tf="M15",
                    htf="H4",
                )
            except Exception:
                continue

            # Run strategy
            try:
                candidate = strategy.analyze(
                    context=ctx,
                    current_candle=current_candle,
                    current_price=current_price,
                    spread=3.0,
                    session="london",
                )
            except Exception:
                continue

            if candidate and candidate.rr_ratio >= min_rr:
                # AI scoring
                ai_decision = ai_scorer.score(candidate, ctx, spread=3.0, session="london")

                if ai_decision.ai_score >= min_ai_score:
                    # Position sizing
                    risk_amount = equity * risk_per_trade
                    sl_distance = abs(candidate.entry_price - candidate.stop_loss)

                    if sl_distance > 0:
                        volume = risk_amount / (sl_distance * 100)
                        volume = max(0.01, round(volume, 2))

                        trade = {
                            "entry_time": current_candle.timestamp.isoformat(),
                            "direction": candidate.direction.value,
                            "entry": current_price,
                            "sl": candidate.stop_loss,
                            "tp": candidate.take_profit_1,
                            "volume": volume,
                            "status": "OPEN",
                        }
                        trades.append(trade)
                        daily_trades[current_date] = daily_trades.get(current_date, 0) + 1

            # Track drawdown
            if equity > peak_equity:
                peak_equity = equity
            dd = (peak_equity - equity) / peak_equity * 100
            if dd > max_drawdown:
                max_drawdown = dd

        # Close remaining trades
        for trade in trades:
            if trade["status"] == "OPEN":
                last_price = candles[-1].close
                if trade["direction"] == "BUY":
                    pnl = (last_price - trade["entry"]) * trade["volume"] * 100
                else:
                    pnl = (trade["entry"] - last_price) * trade["volume"] * 100
                pnl -= 7.0 * trade["volume"]
                equity += pnl
                trade["pnl"] = round(pnl, 2)

        # Calculate metrics
        closed_trades = [t for t in trades if t["status"] == "CLOSED"]
        winners = [t for t in closed_trades if t["pnl"] > 0]
        losers = [t for t in closed_trades if t["pnl"] <= 0]

        total_trades = len(closed_trades)
        win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0
        total_pnl = sum(t["pnl"] for t in closed_trades)
        profit_factor = sum(t["pnl"] for t in winners) / abs(sum(t["pnl"] for t in losers)) if losers else 0

        return {
            "min_rr": min_rr,
            "min_ai_score": min_ai_score,
            "risk_per_trade": risk_per_trade,
            "max_trades_per_day": max_trades_per_day,
            "total_trades": total_trades,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_drawdown, 1),
            "final_equity": round(equity, 2),
            "return_pct": round((equity - initial_balance) / initial_balance * 100, 1),
        }

    def optimize(self, candles: list[Candle]) -> list[dict]:
        """Run grid search optimization."""
        print("[OPTIMIZATION] Testing parameter combinations...")

        # Parameter grid
        min_rr_values = [1.5, 2.0, 2.5, 3.0]
        min_ai_scores = [60, 65, 70, 75, 80]
        risk_values = [0.005, 0.01, 0.015, 0.02]
        max_trades_values = [1, 2, 3]

        total_combinations = len(min_rr_values) * len(min_ai_scores) * len(risk_values) * len(max_trades_values)
        print(f"  Testing {total_combinations} combinations...")

        results = []
        count = 0

        for min_rr in min_rr_values:
            for min_ai in min_ai_scores:
                for risk in risk_values:
                    for max_trades in max_trades_values:
                        count += 1
                        if count % 50 == 0:
                            print(f"  Progress: {count}/{total_combinations}")

                        result = self.test_parameters(
                            candles=candles,
                            min_rr=min_rr,
                            min_ai_score=min_ai,
                            risk_per_trade=risk,
                            max_trades_per_day=max_trades,
                        )
                        results.append(result)

        # Sort by profit factor (best risk-adjusted metric)
        results.sort(key=lambda r: r["profit_factor"], reverse=True)

        return results


def main():
    parser = argparse.ArgumentParser(description="Optimize strategy parameters")
    parser.add_argument("--days", type=int, default=180, help="Days of data to use")
    parser.add_argument("--top", type=int, default=10, help="Show top N results")
    args = parser.parse_args()

    optimizer = StrategyOptimizer()

    # Load data
    print(f"[LOADING] {args.days} days of gold data...")
    candles = optimizer.load_data(period=f"{args.days}d")
    print(f"  Loaded {len(candles)} candles")

    # Run optimization
    results = optimizer.optimize(candles)

    # Show top results
    print(f"\n{'='*80}")
    print(f"[TOP {args.top}] Parameter Combinations")
    print(f"{'='*80}")
    print(f"{'Rank':<6} {'MinRR':<8} {'MinAI':<8} {'Risk':<8} {'MaxT':<8} {'Trades':<8} {'Win%':<8} {'P&L':<12} {'PF':<8} {'MaxDD%':<8} {'Return%':<8}")
    print(f"{'-'*80}")

    for i, r in enumerate(results[:args.top]):
        print(f"{i+1:<6} {r['min_rr']:<8} {r['min_ai_score']:<8} {r['risk_per_trade']:<8} {r['max_trades_per_day']:<8} {r['total_trades']:<8} {r['win_rate']:<8} ${r['total_pnl']:<11,.2f} {r['profit_factor']:<8} {r['max_drawdown']:<8} {r['return_pct']:<8}")

    # Show best parameters
    best = results[0]
    print(f"\n[BEST PARAMETERS]")
    print(f"  min_rr: {best['min_rr']}")
    print(f"  min_ai_score: {best['min_ai_score']}")
    print(f"  risk_per_trade: {best['risk_per_trade']}")
    print(f"  max_trades_per_day: {best['max_trades_per_day']}")
    print(f"\n[RESULTS]")
    print(f"  Total Trades: {best['total_trades']}")
    print(f"  Win Rate: {best['win_rate']}%")
    print(f"  Total P&L: ${best['total_pnl']:,.2f}")
    print(f"  Profit Factor: {best['profit_factor']}")
    print(f"  Max Drawdown: {best['max_drawdown']}%")
    print(f"  Return: {best['return_pct']}%")

    # Save results
    with open("optimization_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SAVED] All results saved to optimization_results.json")


if __name__ == "__main__":
    main()
