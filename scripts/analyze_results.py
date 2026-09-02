"""Analyze backtest results and provide optimization recommendations.

Reads backtest_results.json and provides detailed analysis.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def analyze_results(results_path: str = "backtest_results.json"):
    """Analyze backtest results in detail."""
    with open(results_path) as f:
        results = json.load(f)

    print("=" * 70)
    print("DETAILED BACKTEST ANALYSIS")
    print("=" * 70)

    for r in results:
        strategy = r["strategy"]
        trades = r["trades"]

        print(f"\n{'='*70}")
        print(f"STRATEGY: {strategy}")
        print(f"{'='*70}")

        if not trades:
            print("  No trades generated")
            continue

        # Basic metrics
        print(f"\n  [BASIC METRICS]")
        print(f"    Total Trades: {r['total_trades']}")
        print(f"    Win Rate: {r['win_rate']}%")
        print(f"    Total P&L: ${r['total_pnl']:,.2f}")
        print(f"    Return: {r['return_pct']}%")
        print(f"    Profit Factor: {r['profit_factor']}")
        print(f"    Expectancy: ${r['expectancy']:,.2f}")
        print(f"    Max Drawdown: {r['max_drawdown']}%")
        print(f"    Avg R: {r['avg_r']:.2f}")

        # Trade analysis
        winners = [t for t in trades if t["pnl"] > 0]
        losers = [t for t in trades if t["pnl"] <= 0]

        print(f"\n  [TRADE ANALYSIS]")
        print(f"    Winners: {len(winners)}")
        print(f"    Losers: {len(losers)}")

        if winners:
            avg_win_r = np.mean([t["r_multiple"] for t in winners])
            max_win = max(t["pnl"] for t in winners)
            print(f"    Avg Winner: ${np.mean([t['pnl'] for t in winners]):,.2f} ({avg_win_r:.1f}R)")
            print(f"    Max Winner: ${max_win:,.2f}")

        if losers:
            avg_loss_r = np.mean([t["r_multiple"] for t in losers])
            max_loss = min(t["pnl"] for t in losers)
            print(f"    Avg Loser: ${np.mean([t['pnl'] for t in losers]):,.2f} ({avg_loss_r:.1f}R)")
            print(f"    Max Loss: ${max_loss:,.2f}")

        # Direction analysis
        buys = [t for t in trades if t["direction"] == "BUY"]
        sells = [t for t in trades if t["direction"] == "SELL"]

        print(f"\n  [DIRECTION ANALYSIS]")
        print(f"    BUY trades: {len(buys)} ({len([t for t in buys if t['pnl'] > 0])} winners)")
        print(f"    SELL trades: {len(sells)} ({len([t for t in sells if t['pnl'] > 0])} winners)")

        # R-multiple distribution
        r_multiples = [t["r_multiple"] for t in trades]
        print(f"\n  [R-MULTIPLE DISTRIBUTION]")
        print(f"    Min: {min(r_multiples):.2f}R")
        print(f"    Max: {max(r_multiples):.2f}R")
        print(f"    Mean: {np.mean(r_multiples):.2f}R")
        print(f"    Median: {np.median(r_multiples):.2f}R")
        print(f"    Std: {np.std(r_multiples):.2f}R")

        # Win streak analysis
        streaks = []
        current_streak = 0
        for t in trades:
            if t["pnl"] > 0:
                current_streak = max(0, current_streak) + 1
            else:
                current_streak = min(0, current_streak) - 1
            streaks.append(current_streak)

        max_win_streak = max(streaks) if streaks else 0
        max_loss_streak = abs(min(streaks)) if streaks else 0

        print(f"\n  [STREAK ANALYSIS]")
        print(f"    Max Win Streak: {max_win_streak}")
        print(f"    Max Loss Streak: {max_loss_streak}")

        # Equity curve analysis
        equity = r["equity_curve"]
        print(f"\n  [EQUITY CURVE]")
        print(f"    Start: ${equity[0]:,.2f}")
        print(f"    End: ${equity[-1]:,.2f}")
        print(f"    Peak: ${max(equity):,.2f}")
        print(f"    Trough: ${min(equity):,.2f}")

    # Overall comparison
    print(f"\n{'='*70}")
    print(f"OVERALL RECOMMENDATION")
    print(f"{'='*70}")

    # Find best strategy
    best = max(results, key=lambda r: r.get("total_pnl", 0))
    worst = min(results, key=lambda r: r.get("total_pnl", 0))

    print(f"\n  Best Strategy: {best['strategy']}")
    print(f"    P&L: ${best['total_pnl']:,.2f}")
    print(f"    Win Rate: {best['win_rate']}%")
    print(f"    Profit Factor: {best['profit_factor']}")

    if best["total_pnl"] > 0:
        print(f"\n  [VERDICT] {best['strategy']} shows PROFITABLE edge on real data")
        print(f"  RECOMMENDATION: Use this strategy for paper trading")
    else:
        print(f"\n  [VERDICT] No strategy shows consistent edge on real data")
        print(f"  RECOMMENDATION: Need more data or strategy optimization")

    # Optimization suggestions
    print(f"\n  [OPTIMIZATION SUGGESTIONS]")

    for r in results:
        if r["total_trades"] < 10:
            print(f"    {r['strategy']}: Too few trades - consider relaxing entry conditions")
        if r["win_rate"] < 40:
            print(f"    {r['strategy']}: Low win rate - tighten entry filters")
        if r["profit_factor"] < 1.0:
            print(f"    {r['strategy']}: PF < 1.0 - strategy loses money overall")
        if r["max_drawdown"] > 10:
            print(f"    {r['strategy']}: High drawdown - reduce position size")


if __name__ == "__main__":
    analyze_results()
