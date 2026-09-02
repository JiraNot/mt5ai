"""Backtest using multi-timeframe data for proper trend detection.

Uses hourly data for H4/H1 structure and daily data for HTF context.

Usage:
    python scripts/backtest_mtf.py
"""

from __future__ import annotations

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


def load_csv_to_candles(filename: str) -> list[Candle]:
    """Load CSV data into Candle objects."""
    df = pd.read_csv(filename, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    df.index = df.index.tz_localize(None)
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


def resample_candles(candles: list[Candle], hours: int) -> list[Candle]:
    """Resample candles to higher timeframe."""
    if not candles:
        return []

    resampled = []
    group = []
    current_ts = candles[0].timestamp

    for candle in candles:
        # Check if we've moved to a new group
        time_diff = (candle.timestamp - current_ts).total_seconds() / 3600
        if time_diff >= hours:
            if group:
                # Create resampled candle
                resampled.append(Candle(
                    timestamp=group[0].timestamp,
                    open=group[0].open,
                    high=max(c.high for c in group),
                    low=min(c.low for c in group),
                    close=group[-1].close,
                    volume=sum(c.volume for c in group),
                ))
            group = [candle]
            current_ts = candle.timestamp
        else:
            group.append(candle)

    # Don't forget the last group
    if group:
        resampled.append(Candle(
            timestamp=group[0].timestamp,
            open=group[0].open,
            high=max(c.high for c in group),
            low=min(c.low for c in group),
            close=group[-1].close,
            volume=sum(c.volume for c in group),
        ))

    return resampled


def main():
    print("[BACKTEST] Multi-timeframe FVG Reversal")

    # Load data
    print("\n[LOADING] Data...")
    h1_candles = load_csv_to_candles("gold_1h.csv")
    daily_candles = load_csv_to_candles("gold_1d.csv")

    print(f"  H1 candles: {len(h1_candles)}")
    print(f"  Daily candles: {len(daily_candles)}")

    # Create H4 from hourly (group by 4 hours)
    h4_candles = resample_candles(h1_candles, 4)
    print(f"  H4 candles: {len(h4_candles)}")

    # Initialize components
    strategy = FVGReversalStrategy()
    context_builder = ContextBuilder()
    ai_scorer = RuleBasedScorer()

    # Backtest parameters
    initial_balance = 10000.0
    risk_per_trade = 0.01
    spread = 3.0
    lookback = 50

    equity = initial_balance
    peak_equity = equity
    max_drawdown = 0
    trades = []
    equity_curve = [{"date": h1_candles[lookback].timestamp.isoformat(), "equity": equity}]

    # Run backtest on hourly data
    print(f"\n[BACKTESTING] Running strategy...")

    for i in range(lookback, len(h1_candles)):
        current_candle = h1_candles[i]
        current_price = current_candle.close

        # Build context with multi-timeframe data
        available_h1 = h1_candles[max(0, i-lookback):i+1]

        # Get proportional H4 data
        h4_idx = int(i * len(h4_candles) / len(h1_candles))
        available_h4 = h4_candles[max(0, h4_idx-20):h4_idx+1]

        # Get proportional daily data
        daily_idx = int(i * len(daily_candles) / len(h1_candles))
        available_daily = daily_candles[max(0, daily_idx-10):daily_idx+1]

        try:
            ctx = context_builder.build(
                symbol="XAUUSD",
                candles_by_tf={
                    "M15": available_h1,
                    "H1": available_h1,
                    "H4": available_h4,
                    "D1": available_daily,
                },
                primary_tf="H1",
                htf="H4",
            )
        except Exception:
            equity_curve.append({"date": current_candle.timestamp.isoformat(), "equity": equity})
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
                    trade["exit_price"] = exit_price
                    trade["exit_time"] = current_candle.timestamp.isoformat()
                    trade["pnl"] = round(pnl, 2)
                    trade["outcome"] = "WIN" if pnl > 0 else "LOSS"
                    trades.append(trade)
                    trades.remove(trade)

        # Look for new entries
        try:
            candidate = strategy.analyze(
                context=ctx,
                current_candle=current_candle,
                current_price=current_price,
                spread=spread,
                session="london",
            )
        except Exception:
            equity_curve.append({"date": current_candle.timestamp.isoformat(), "equity": equity})
            continue

        if candidate and candidate.rr_ratio >= 2.0:
            # AI scoring
            ai_decision = ai_scorer.score(candidate, ctx, spread=spread, session="london")

            if ai_decision.ai_score >= 70:
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
                        "risk_amount": risk_amount,
                        "status": "OPEN",
                        "ai_score": ai_decision.ai_score,
                        "confluences": candidate.confluences,
                    }
                    trades.append(trade)

        # Track drawdown
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity * 100
        if dd > max_drawdown:
            max_drawdown = dd

        equity_curve.append({"date": current_candle.timestamp.isoformat(), "equity": equity})

    # Close any remaining open trades
    for trade in trades:
        if trade["status"] == "OPEN":
            last_price = h1_candles[-1].close
            if trade["direction"] == "BUY":
                pnl = (last_price - trade["entry"]) * trade["volume"] * 100
            else:
                pnl = (trade["entry"] - last_price) * trade["volume"] * 100
            pnl -= 7.0 * trade["volume"]
            equity += pnl
            trade["status"] = "CLOSED"
            trade["exit_price"] = last_price
            trade["pnl"] = round(pnl, 2)
            trade["outcome"] = "WIN" if pnl > 0 else "LOSS"

    # Calculate metrics
    closed_trades = [t for t in trades if t["status"] == "CLOSED"]
    winners = [t for t in closed_trades if t["pnl"] > 0]
    losers = [t for t in closed_trades if t["pnl"] <= 0]

    total_trades = len(closed_trades)
    win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0
    total_pnl = sum(t["pnl"] for t in closed_trades)
    avg_win = sum(t["pnl"] for t in winners) / len(winners) if winners else 0
    avg_loss = abs(sum(t["pnl"] for t in losers) / len(losers)) if losers else 0
    profit_factor = sum(t["pnl"] for t in winners) / abs(sum(t["pnl"] for t in losers)) if losers else 0
    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)

    # Count BUY vs SELL trades
    buy_trades = [t for t in closed_trades if t["direction"] == "BUY"]
    sell_trades = [t for t in closed_trades if t["direction"] == "SELL"]

    # Print results
    print(f"\n{'='*60}")
    print(f"[RESULTS] Multi-timeframe Backtest")
    print(f"{'='*60}")
    print(f"  Total Trades: {total_trades}")
    print(f"  BUY trades: {len(buy_trades)} ({len([t for t in buy_trades if t['pnl'] > 0])} winners)")
    print(f"  SELL trades: {len(sell_trades)} ({len([t for t in sell_trades if t['pnl'] > 0])} winners)")
    print(f"  Win Rate: {win_rate:.1f}%")
    print(f"  Total P&L: ${total_pnl:,.2f}")
    print(f"  Return: {(equity - initial_balance) / initial_balance * 100:.1f}%")
    print(f"  Profit Factor: {profit_factor:.2f}")
    print(f"  Expectancy: ${expectancy:,.2f}")
    print(f"  Max Drawdown: {max_drawdown:.1f}%")
    print(f"  Final Equity: ${equity:,.2f}")

    if closed_trades:
        print(f"\n  [TRADE LOG]")
        for t in closed_trades[-20:]:
            emoji = "WIN" if t["outcome"] == "WIN" else "LOSS"
            print(f"  [{emoji}] {t['direction']} @ {t['entry']:.2f} -> {t['exit_price']:.2f} | P&L: ${t['pnl']:,.2f}")

    # Save results
    result = {
        "total_trades": total_trades,
        "buy_trades": len(buy_trades),
        "sell_trades": len(sell_trades),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "return_pct": round((equity - initial_balance) / initial_balance * 100, 1),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "max_drawdown": round(max_drawdown, 1),
        "final_equity": round(equity, 2),
        "trades": closed_trades,
    }

    with open("backtest_mtf_results.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n[SAVED] Results saved to backtest_mtf_results.json")


if __name__ == "__main__":
    main()
