"""Backtest all strategies on real XAUUSD data.

Downloads real gold data from Yahoo Finance and runs each strategy
through the full pipeline: Structure → Strategy → AI → Risk → Simulated Execution.

Usage:
    python scripts/backtest_real.py
    python scripts/backtest_real.py --period 1y
    python scripts/backtest_real.py --period 6mo --strategies choch_orderblock
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.types import Candle, Direction, MarketStructure, SwingPoint
from src.structure.swing_detector import SwingDetector
from src.structure.structure_analyzer import StructureAnalyzer
from src.structure.fvg_detector import FVGDetector
from src.structure.order_block_detector import OrderBlockDetector
from src.structure.context import ContextBuilder, MultiTimeframeContext
from src.strategies.base import StrategyPlugin
from src.strategies.choch_orderblock import CHOCHOrderBlockStrategy
from src.strategies.fvg_reversal import FVGReversalStrategy
from src.strategies.breakout_retest import BreakoutRetestStrategy
from src.strategies.fvg_optimized import FVGOptimizedStrategy
from src.strategies.fvg_final import FVGFinalStrategy
from src.ai.scorer import RuleBasedScorer


# ─── Data Download ────────────────────────────────────────────────────────────

def download_gold_data(period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Download XAUUSD data from Yahoo Finance."""
    print(f"[DOWNLOAD] gold data (period={period}, interval={interval})...")
    gold = yf.Ticker("GC=F")
    df = gold.history(period=period, interval=interval)
    print(f"   Downloaded {len(df)} candles")
    print(f"   Range: {df.index[0].date()} to {df.index[-1].date()}")
    return df


def df_to_candles(df: pd.DataFrame) -> list[Candle]:
    """Convert pandas DataFrame to list of Candle objects."""
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


def resample_to_tf(candles: list[Candle], target_tf: str) -> list[Candle]:
    """Resample candles to a higher timeframe."""
    if target_tf == "D1":
        return candles  # Already daily

    # For simplicity, group candles by N
    tf_map = {"H4": 4, "H1": 1, "M15": 0.25, "M5": 5/60}
    factor = tf_map.get(target_tf, 1)

    if factor >= 1:
        # Group N daily candles into higher TF
        group_size = int(factor)
        resampled = []
        for i in range(0, len(candles), group_size):
            group = candles[i:i+group_size]
            if len(group) < 2:
                continue
            resampled.append(Candle(
                timestamp=group[0].timestamp,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
            ))
        return resampled
    else:
        # Split daily candles into intraday (simplified)
        return candles


# ─── Backtester ───────────────────────────────────────────────────────────────

class RealBacktester:
    """Backtest strategies on real market data."""

    def __init__(
        self,
        strategy: StrategyPlugin,
        spread_pips: float = 3.0,
        commission_per_lot: float = 7.0,
        risk_per_trade: float = 0.01,
        min_rr: float = 2.0,
    ):
        self.strategy = strategy
        self.spread = spread_pips
        self.commission = commission_per_lot
        self.risk_per_trade = risk_per_trade
        self.min_rr = min_rr
        self.context_builder = ContextBuilder()
        self.ai_scorer = RuleBasedScorer()

    def run(
        self,
        candles: list[Candle],
        h4_candles: list[Candle] | None = None,
        h1_candles: list[Candle] | None = None,
        initial_balance: float = 10000.0,
        lookback: int = 50,
    ) -> dict:
        """Run backtest on real data."""
        if len(candles) < lookback + 10:
            return {"error": "Insufficient data"}

        equity = initial_balance
        peak_equity = equity
        max_drawdown = 0
        trades = []
        equity_curve = [equity]
        in_trade = False
        trade_entry = 0.0
        trade_sl = 0.0
        trade_tp = 0.0
        trade_direction = None
        trade_volume = 0.0
        trade_risk_amount = 0.0

        for i in range(lookback, len(candles)):
            current_candle = candles[i]
            current_price = current_candle.close

            # Build context with available data
            available_candles = candles[max(0, i-lookback):i+1]

            # Build multi-TF context
            candles_by_tf = {"M15": available_candles}

            if h4_candles:
                # Get proportional H4 data
                h4_idx = int(i * len(h4_candles) / len(candles))
                candles_by_tf["H4"] = h4_candles[max(0, h4_idx-20):h4_idx+1]

            if h1_candles:
                h1_idx = int(i * len(h1_candles) / len(candles))
                candles_by_tf["H1"] = h1_candles[max(0, h1_idx-30):h1_idx+1]

            try:
                ctx = self.context_builder.build(
                    symbol="XAUUSD",
                    candles_by_tf=candles_by_tf,
                    primary_tf="M15",
                    htf="H4" if h4_candles else "M15",
                )
            except Exception:
                equity_curve.append(equity)
                continue

            # Check if in trade
            if in_trade:
                hit_sl = False
                hit_tp = False

                if trade_direction == Direction.BUY:
                    if current_candle.low <= trade_sl:
                        hit_sl = True
                        exit_price = trade_sl
                    elif current_candle.high >= trade_tp:
                        hit_tp = True
                        exit_price = trade_tp
                else:  # SELL
                    if current_candle.high >= trade_sl:
                        hit_sl = True
                        exit_price = trade_sl
                    elif current_candle.low <= trade_tp:
                        hit_tp = True
                        exit_price = trade_tp

                if hit_sl or hit_tp:
                    if trade_direction == Direction.BUY:
                        pnl = (exit_price - trade_entry) * trade_volume * 100
                    else:
                        pnl = (trade_entry - exit_price) * trade_volume * 100

                    pnl -= self.commission * trade_volume
                    pnl -= self.spread * 0.1 * trade_volume * 100  # Spread cost

                    equity += pnl
                    r_multiple = pnl / trade_risk_amount if trade_risk_amount > 0 else 0

                    trades.append({
                        "entry_time": trade_entry_time,
                        "exit_time": current_candle.timestamp,
                        "direction": trade_direction.value,
                        "entry": trade_entry,
                        "exit": exit_price,
                        "sl": trade_sl,
                        "tp": trade_tp,
                        "pnl": round(pnl, 2),
                        "r_multiple": round(r_multiple, 2),
                        "outcome": "WIN" if pnl > 0 else "LOSS",
                    })

                    in_trade = False

                # Track drawdown
                if equity > peak_equity:
                    peak_equity = equity
                dd = (peak_equity - equity) / peak_equity * 100
                if dd > max_drawdown:
                    max_drawdown = dd

            else:
                # Look for entry
                try:
                    candidate = self.strategy.analyze(
                        context=ctx,
                        current_candle=current_candle,
                        current_price=current_price,
                        spread=self.spread,
                        session="london",
                    )
                except Exception:
                    equity_curve.append(equity)
                    continue

                if candidate and candidate.rr_ratio >= self.min_rr:
                    # AI scoring
                    ai_decision = self.ai_scorer.score(
                        candidate, ctx, spread=self.spread, session="london"
                    )

                    # Only trade if AI score >= 70
                    if ai_decision.ai_score >= 70:
                        # Position sizing
                        risk_amount = equity * self.risk_per_trade
                        sl_distance = abs(candidate.entry_price - candidate.stop_loss)

                        if sl_distance > 0:
                            volume = risk_amount / (sl_distance * 100)  # XAUUSD contract = 100
                            volume = max(0.01, round(volume, 2))

                            in_trade = True
                            trade_entry = current_price
                            trade_direction = candidate.direction
                            trade_sl = candidate.stop_loss
                            trade_tp = candidate.take_profit_1
                            trade_volume = volume
                            trade_risk_amount = risk_amount
                            trade_entry_time = current_candle.timestamp

            equity_curve.append(equity)

        # Calculate final metrics
        winners = [t for t in trades if t["pnl"] > 0]
        losers = [t for t in trades if t["pnl"] <= 0]
        total_trades = len(trades)
        win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0
        total_pnl = sum(t["pnl"] for t in trades)
        avg_win = np.mean([t["pnl"] for t in winners]) if winners else 0
        avg_loss = abs(np.mean([t["pnl"] for t in losers])) if losers else 0
        profit_factor = sum(t["pnl"] for t in winners) / abs(sum(t["pnl"] for t in losers)) if losers else 0
        expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)
        avg_r = np.mean([t["r_multiple"] for t in trades]) if trades else 0

        return {
            "strategy": self.strategy.strategy_id,
            "total_trades": total_trades,
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy": round(expectancy, 2),
            "max_drawdown": round(max_drawdown, 1),
            "avg_r": round(avg_r, 2),
            "final_equity": round(equity, 2),
            "return_pct": round((equity - 10000) / 10000 * 100, 1),
            "trades": trades,
            "equity_curve": equity_curve,
        }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backtest strategies on real XAUUSD data")
    parser.add_argument("--period", default="2y", help="Data period (1y, 2y, 5y)")
    parser.add_argument("--strategies", nargs="+", default=["choch_orderblock", "fvg_reversal", "breakout_retest"],
                       help="Strategies to test")
    parser.add_argument("--spread", type=float, default=3.0, help="Spread in pips")
    parser.add_argument("--risk", type=float, default=0.01, help="Risk per trade (0.01 = 1%%)")
    parser.add_argument("--min-rr", type=float, default=2.0, help="Minimum RR ratio")
    parser.add_argument("--lookback", type=int, default=50, help="Candle lookback for structure")
    args = parser.parse_args()

    # Download real data
    df = download_gold_data(period=args.period)
    candles = df_to_candles(df)

    # Create higher TF data
    h4_candles = resample_to_tf(candles, "H4")
    h1_candles = resample_to_tf(candles, "H1")

    print(f"\n[DATA SUMMARY]")
    print(f"[DATA] M15={len(candles)}, H1={len(h1_candles)}, H4={len(h4_candles)}")

    # Strategy mapping
    strategy_map = {
        "choch_orderblock": CHOCHOrderBlockStrategy(),
        "fvg_reversal": FVGReversalStrategy(),
        "fvg_optimized": FVGOptimizedStrategy(),
        "fvg_final": FVGFinalStrategy(),
        "breakout_retest": BreakoutRetestStrategy(),
    }

    results = []

    for strategy_id in args.strategies:
        if strategy_id not in strategy_map:
            print(f"\n[ERROR] Unknown strategy: {strategy_id}")
            continue

        strategy = strategy_map[strategy_id]
        print(f"\n{'='*60}")
        print(f"[BACKTEST] {strategy.name} ({strategy_id})")
        print(f"{'='*60}")

        backtester = RealBacktester(
            strategy=strategy,
            spread_pips=args.spread,
            risk_per_trade=args.risk,
            min_rr=args.min_rr,
        )

        result = backtester.run(
            candles=candles,
            h4_candles=h4_candles,
            h1_candles=h1_candles,
            lookback=args.lookback,
        )

        if "error" in result:
            print(f"   [ERROR] {result['error']}")
            continue

        results.append(result)

        # Print results
        print(f"\n[RESULTS]")
        print(f"   Total Trades: {result['total_trades']}")
        print(f"   Win Rate: {result['win_rate']}%")
        print(f"   Total P&L: ${result['total_pnl']:,.2f}")
        print(f"   Return: {result['return_pct']}%")
        print(f"   Profit Factor: {result['profit_factor']}")
        print(f"   Expectancy: ${result['expectancy']:,.2f}")
        print(f"   Max Drawdown: {result['max_drawdown']}%")
        print(f"   Avg R: {result['avg_r']:.2f}")
        print(f"   Final Equity: ${result['final_equity']:,.2f}")

        if result["trades"]:
            print(f"\n   Trade Examples:")
            for t in result["trades"][:5]:
                emoji = "WIN" if t["outcome"] == "WIN" else "LOSS"
                print(f"   [{emoji}] {t['direction']} @ {t['entry']:.2f} -> {t['exit']:.2f} | P&L: ${t['pnl']:,.2f} | {t['r_multiple']:.1f}R")

    # Summary comparison
    if len(results) > 1:
        print(f"\n{'='*60}")
        print(f"[SUMMARY] Strategy Comparison")
        print(f"{'='*60}")
        print(f"{'Strategy':<20} {'Trades':<8} {'Win%':<8} {'P&L':<12} {'PF':<8} {'MaxDD%':<8}")
        print(f"{'-'*64}")
        for r in results:
            print(f"{r['strategy']:<20} {r['total_trades']:<8} {r['win_rate']:<8} ${r['total_pnl']:<11,.2f} {r['profit_factor']:<8} {r['max_drawdown']:<8}")

    # Save results
    output_path = Path("backtest_results.json")
    with open(output_path, "w") as f:
        # Convert trades to serializable format
        serializable_results = []
        for r in results:
            sr = {k: v for k, v in r.items() if k != "equity_curve"}
            sr["equity_curve"] = r["equity_curve"][-100:]  # Last 100 points only
            serializable_results.append(sr)
        json.dump(serializable_results, f, indent=2, default=str)
    print(f"\n[SAVED] Results saved to {output_path}")


if __name__ == "__main__":
    main()
