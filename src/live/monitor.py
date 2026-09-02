"""Live market monitor — scans for trading opportunities in real-time.

Downloads live gold data, runs strategy analysis, and logs potential trades.
Designed to run continuously and alert when setups appear.

Usage:
    python -m src.live.monitor              # Run continuous monitor
    python -m src.live.monitor --once       # Scan once and exit
    python -m src.live.monitor --interval 60  # Check every 60 seconds
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.types import Candle, Direction
from src.structure.context import ContextBuilder, MultiTimeframeContext
from src.strategies.fvg_reversal import FVGReversalStrategy
from src.ai.scorer import RuleBasedScorer


class LiveMonitor:
    """Monitor live market for trading opportunities."""

    def __init__(self, interval_seconds: int = 60):
        self.interval = interval_seconds
        self.strategy = FVGReversalStrategy()  # Best performing strategy
        self.context_builder = ContextBuilder()
        self.ai_scorer = RuleBasedScorer()
        self.seen_setups = set()  # Track already-seen setups

    def fetch_latest_data(self) -> pd.DataFrame:
        """Fetch latest gold data from Yahoo Finance."""
        gold = yf.Ticker("GC=F")
        # Get 3 months of daily data for structure analysis
        df = gold.history(period="3mo", interval="1d")
        return df

    def df_to_candles(self, df: pd.DataFrame) -> list[Candle]:
        """Convert DataFrame to Candle objects."""
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

    def scan(self) -> list[dict]:
        """Scan for trading opportunities."""
        try:
            df = self.fetch_latest_data()
            candles = self.df_to_candles(df)

            if len(candles) < 30:
                return []

            # Build context
            ctx = self.context_builder.build(
                symbol="XAUUSD",
                candles_by_tf={"M15": candles, "H1": candles, "H4": candles},
                primary_tf="M15",
                htf="H4",
            )

            current_price = candles[-1].close
            current_candle = candles[-1]

            # Run strategy
            candidate = self.strategy.analyze(
                context=ctx,
                current_candle=current_candle,
                current_price=current_price,
                spread=3.0,
                session="london",
            )

            if not candidate:
                return []

            # AI scoring
            ai_decision = self.ai_scorer.score(
                candidate, ctx, spread=3.0, session="london"
            )

            # Create unique key for this setup
            setup_key = f"{candidate.direction.value}_{candidate.entry_price:.0f}_{candidate.timestamp}"

            if setup_key in self.seen_setups:
                return []

            self.seen_setups.add(setup_key)

            # Only report high-confidence setups
            if ai_decision.ai_score < 70:
                return []

            return [{
                "timestamp": datetime.now().isoformat(),
                "symbol": "XAUUSD",
                "direction": candidate.direction.value,
                "entry": candidate.entry_price,
                "sl": candidate.stop_loss,
                "tp1": candidate.take_profit_1,
                "tp2": candidate.take_profit_2,
                "rr_ratio": candidate.rr_ratio,
                "rule_score": candidate.rule_score,
                "ai_score": ai_decision.ai_score,
                "confidence": ai_decision.confidence,
                "confluences": candidate.confluences,
                "reasons": ai_decision.reasons,
                "risk_flags": ai_decision.risk_flags,
                "current_price": current_price,
                "gold_price": current_price,
            }]

        except Exception as e:
            print(f"[ERROR] Scan failed: {e}")
            return []

    def format_alert(self, setup: dict) -> str:
        """Format a setup as a readable alert."""
        direction_emoji = "BUY" if setup["direction"] == "BUY" else "SELL"

        alert = f"""
{'='*60}
[ALERT] {direction_emoji} SIGNAL DETECTED
{'='*60}

  Symbol: {setup['symbol']}
  Direction: {setup['direction']}
  Current Price: ${setup['current_price']:,.2f}

  Entry: ${setup['entry']:,.2f}
  Stop Loss: ${setup['sl']:,.2f}
  Take Profit 1: ${setup['tp1']:,.2f}
  Take Profit 2: ${setup['tp2']:,.2f}
  Risk/Reward: 1:{setup['rr_ratio']:.1f}

  Rule Score: {setup['rule_score']}
  AI Score: {setup['ai_score']}
  Confidence: {setup['confidence']:.0%}

  Confluences:
"""
        for c in setup["confluences"]:
            alert += f"    + {c}\n"

        if setup["reasons"]:
            alert += "\n  Reasons:\n"
            for r in setup["reasons"][:3]:
                alert += f"    - {r}\n"

        if setup["risk_flags"]:
            alert += "\n  Risk Flags:\n"
            for f in setup["risk_flags"]:
                alert += f"    ! {f}\n"

        alert += f"\n  Time: {setup['timestamp']}\n"
        alert += "=" * 60

        return alert

    def save_setup(self, setup: dict):
        """Save setup to log file."""
        log_path = Path("live_setups.jsonl")
        with open(log_path, "a") as f:
            f.write(json.dumps(setup, default=str) + "\n")

    def run_once(self):
        """Run a single scan."""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning for opportunities...")

        setups = self.scan()

        if setups:
            for setup in setups:
                alert = self.format_alert(setup)
                print(alert)
                self.save_setup(setup)
        else:
            print(f"  No opportunities found")

        return setups

    def run_continuous(self):
        """Run continuous monitoring."""
        print(f"Starting live monitor (interval: {self.interval}s)")
        print(f"Strategy: {self.strategy.name}")
        print(f"Press Ctrl+C to stop\n")

        try:
            while True:
                self.run_once()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            print("\nMonitor stopped")


def main():
    parser = argparse.ArgumentParser(description="Live market monitor")
    parser.add_argument("--once", action="store_true", help="Scan once and exit")
    parser.add_argument("--interval", type=int, default=60, help="Scan interval in seconds")
    args = parser.parse_args()

    monitor = LiveMonitor(interval_seconds=args.interval)

    if args.once:
        monitor.run_once()
    else:
        monitor.run_continuous()


if __name__ == "__main__":
    main()
