"""Multi-timeframe live monitor — uses hourly data for proper structure analysis.

Downloads hourly gold data and runs strategy analysis with proper
multi-timeframe context.

Usage:
    python -m src.live.monitor_mtf              # Run continuous monitor
    python -m src.live.monitor_mtf --once       # Scan once and exit
    python -m src.live.monitor_mtf --interval 300  # Check every 5 minutes
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.types import Candle, Direction
from src.structure.context import ContextBuilder
from src.strategies.fvg_reversal import FVGReversalStrategy
from src.ai.scorer import RuleBasedScorer


class LiveMonitorMTF:
    """Monitor live market with multi-timeframe analysis."""

    def __init__(self, interval_seconds: int = 300):
        self.interval = interval_seconds
        self.strategy = FVGReversalStrategy()
        self.context_builder = ContextBuilder()
        self.ai_scorer = RuleBasedScorer()
        self.seen_setups = set()

    def fetch_data(self) -> dict[str, list[Candle]]:
        """Fetch multi-timeframe gold data."""
        # Hourly data (for H1, M15)
        gold_h1 = yf.Ticker("GC=F")
        df_h1 = gold_h1.history(period="1mo", interval="60m")

        # Daily data (for D1)
        gold_d1 = yf.Ticker("GC=F")
        df_d1 = gold_d1.history(period="3mo", interval="1d")

        # Convert to candles
        h1_candles = self._df_to_candles(df_h1)
        daily_candles = self._df_to_candles(df_d1)

        # Create H4 from hourly (group by 4)
        h4_candles = self._resample(h1_candles, 4)

        # Use H1 as M15 proxy (we don't have true M15 data from Yahoo)
        m15_candles = h1_candles

        return {
            "M15": m15_candles,
            "H1": h1_candles,
            "H4": h4_candles,
            "D1": daily_candles,
        }

    def _df_to_candles(self, df: pd.DataFrame) -> list[Candle]:
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

    def _resample(self, candles: list[Candle], hours: int) -> list[Candle]:
        """Resample candles to higher timeframe."""
        if not candles:
            return []

        resampled = []
        group = []
        current_ts = candles[0].timestamp

        for candle in candles:
            time_diff = (candle.timestamp - current_ts).total_seconds() / 3600
            if time_diff >= hours:
                if group:
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

    def scan(self) -> list[dict]:
        """Scan for trading opportunities."""
        try:
            candles_by_tf = self.fetch_data()
            h1_candles = candles_by_tf["H1"]

            if len(h1_candles) < 50:
                return []

            current_candle = h1_candles[-1]
            current_price = current_candle.close

            # Build context
            ctx = self.context_builder.build(
                symbol="XAUUSD",
                candles_by_tf=candles_by_tf,
                primary_tf="H1",
                htf="H4",
            )

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

            # Create unique key
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
                "htf_trend": ctx.htf_trend.value if ctx.htf_trend else "NONE",
            }]

        except Exception as e:
            print(f"[ERROR] Scan failed: {e}")
            return []

    def format_alert(self, setup: dict) -> str:
        """Format a setup as a readable alert."""
        direction = setup["direction"]

        alert = f"""
{'='*60}
[ALERT] {direction} SIGNAL DETECTED
{'='*60}

  Symbol: {setup['symbol']}
  Direction: {setup['direction']}
  HTF Trend: {setup.get('htf_trend', 'N/A')}
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

        if setup["risk_flags"]:
            alert += "\n  Risk Flags:\n"
            for f in setup["risk_flags"]:
                alert += f"    ! {f}\n"

        alert += f"\n  Time: {setup['timestamp']}\n"
        alert += "=" * 60

        return alert

    def save_setup(self, setup: dict):
        """Save setup to log file."""
        log_path = Path("live_setups_mtf.jsonl")
        with open(log_path, "a") as f:
            f.write(json.dumps(setup, default=str) + "\n")

    def run_once(self):
        """Run a single scan."""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning (MTF)...")

        setups = self.scan()

        if setups:
            for setup in setups:
                alert = self.format_alert(setup)
                print(alert)
                self.save_setup(setup)
        else:
            print("  No opportunities found")

        return setups

    def run_continuous(self):
        """Run continuous monitoring."""
        print(f"Starting MTF monitor (interval: {self.interval}s)")
        print(f"Strategy: {self.strategy.name}")
        print(f"Press Ctrl+C to stop\n")

        try:
            while True:
                self.run_once()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            print("\nMonitor stopped")


def main():
    parser = argparse.ArgumentParser(description="MTF live monitor")
    parser.add_argument("--once", action="store_true", help="Scan once and exit")
    parser.add_argument("--interval", type=int, default=300, help="Scan interval in seconds")
    args = parser.parse_args()

    monitor = LiveMonitorMTF(interval_seconds=args.interval)

    if args.once:
        monitor.run_once()
    else:
        monitor.run_continuous()


if __name__ == "__main__":
    main()
