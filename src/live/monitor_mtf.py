"""Multi-timeframe live monitor for Binance USDT-M Futures.

Fetches multi-timeframe candle data directly from Binance Gateway
and evaluates SMC structure and strategy candidates.

Usage:
    python -m src.live.monitor_mtf --symbol BTCUSDT --once
    python -m src.live.monitor_mtf --symbol ETHUSDT --interval 300
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from src.ai.scorer import RuleBasedScorer
from src.core.config import settings
from src.core.types import Candle
from src.market.binance_gateway import BinanceGateway
from src.strategies.fvg_reversal import FVGReversalStrategy
from src.structure.context import ContextBuilder

logger = logging.getLogger(__name__)


class LiveMonitorMTF:
    """Monitor live Binance market with multi-timeframe SMC analysis."""

    def __init__(self, symbol: str = "BTCUSDT", interval_seconds: int = 300):
        self.symbol = symbol.upper()
        self.interval = interval_seconds
        self.strategy = FVGReversalStrategy()
        self.context_builder = ContextBuilder()
        self.ai_scorer = RuleBasedScorer()
        self.seen_setups: set[str] = set()
        self.gateway = BinanceGateway()

    async def fetch_data(self) -> dict[str, list[Candle]]:
        """Fetch multi-timeframe candles directly from Binance Gateway."""
        if not self.gateway.connected:
            await self.gateway.connect()

        m5_candles = await self.gateway.get_ohlcv(self.symbol, "M5", count=200)
        m15_candles = await self.gateway.get_ohlcv(self.symbol, "M15", count=200)
        h1_candles = await self.gateway.get_ohlcv(self.symbol, "H1", count=200)
        h4_candles = await self.gateway.get_ohlcv(self.symbol, "H4", count=100)

        return {
            "M5": m5_candles,
            "M15": m15_candles,
            "H1": h1_candles,
            "H4": h4_candles,
        }

    async def scan(self) -> list[dict]:
        """Scan for trading opportunities on the selected Binance symbol."""
        try:
            candles_by_tf = await self.fetch_data()
            h1_candles = candles_by_tf.get("H1", [])

            if len(h1_candles) < 30:
                logger.warning("Insufficient H1 candle history for %s", self.symbol)
                return []

            current_candle = h1_candles[-1]
            current_price = current_candle.close

            # Build multi-timeframe context
            ctx = self.context_builder.build(
                symbol=self.symbol,
                candles_by_tf=candles_by_tf,
                primary_tf="H1",
                htf="H4",
            )

            # Analyze with strategy
            candidate = self.strategy.analyze(
                context=ctx,
                current_candle=current_candle,
                current_price=current_price,
                spread=1.0,
                session="crypto_continuous",
            )

            if not candidate:
                return []

            # AI rule scoring
            ai_decision = self.ai_scorer.score(
                candidate, ctx, spread=1.0, session="crypto_continuous"
            )

            setup_key = f"{candidate.direction.value}_{candidate.entry_price:.1f}_{candidate.timestamp}"
            if setup_key in self.seen_setups:
                return []
            self.seen_setups.add(setup_key)

            if ai_decision.ai_score < 70:
                return []

            return [{
                "timestamp": datetime.now().isoformat(),
                "symbol": self.symbol,
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

        except Exception as exc:
            logger.error("Scan failed for %s: %s", self.symbol, exc, exc_info=True)
            return []

    def format_alert(self, setup: dict) -> str:
        """Format a setup as a readable alert."""
        direction = setup["direction"]
        lines = [
            "=" * 60,
            f"[BINANCE FUTURES ALERT] {direction} SIGNAL DETECTED: {setup['symbol']}",
            "=" * 60,
            f"  Symbol:        {setup['symbol']}",
            f"  Direction:     {setup['direction']}",
            f"  HTF Trend:     {setup.get('htf_trend', 'N/A')}",
            f"  Current Price: ${setup['current_price']:,.2f}",
            f"  Entry:         ${setup['entry']:,.2f}",
            f"  Stop Loss:     ${setup['sl']:,.2f}",
            f"  Take Profit 1: ${setup['tp1']:,.2f}",
            f"  Take Profit 2: ${setup['tp2']:,.2f}",
            f"  Risk/Reward:   1:{setup['rr_ratio']:.1f}",
            f"  Rule Score:    {setup['rule_score']}",
            f"  AI Score:      {setup['ai_score']}",
            f"  Confidence:    {setup['confidence']:.0%}",
            "  Confluences:",
        ]
        for c in setup.get("confluences", []):
            lines.append(f"    + {c}")
        if setup.get("risk_flags"):
            lines.append("  Risk Flags:")
            for f in setup["risk_flags"]:
                lines.append(f"    ! {f}")
        lines.append(f"  Time: {setup['timestamp']}")
        lines.append("=" * 60)
        return "\n".join(lines)

    def save_setup(self, setup: dict) -> None:
        """Save setup to jsonl audit log."""
        log_path = Path("live_setups_mtf.jsonl")
        with open(log_path, "a") as f:
            f.write(json.dumps(setup, default=str) + "\n")

    async def run_once(self) -> list[dict]:
        """Run a single scan cycle."""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning Binance {self.symbol} (MTF)...")
        setups = await self.scan()
        if setups:
            for s in setups:
                print(self.format_alert(s))
                self.save_setup(s)
        else:
            print(f"  No opportunities found on {self.symbol}")
        return setups

    async def run_continuous(self) -> None:
        """Run continuous monitoring loop."""
        print(f"Starting Binance MTF monitor on {self.symbol} (interval: {self.interval}s)")
        print(f"Strategy: {self.strategy.name}")
        print("Press Ctrl+C to stop\n")
        try:
            while True:
                await self.run_once()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            print("\nMonitor stopped")
        finally:
            await self.gateway.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Binance MTF live monitor")
    parser.add_argument("--symbol", type=str, default=settings.binance_symbol or "BTCUSDT", help="Trading symbol")
    parser.add_argument("--once", action="store_true", help="Scan once and exit")
    parser.add_argument("--interval", type=int, default=300, help="Scan interval in seconds")
    args = parser.parse_args()

    monitor = LiveMonitorMTF(symbol=args.symbol, interval_seconds=args.interval)

    if args.once:
        asyncio.run(monitor.run_once())
    else:
        try:
            asyncio.run(monitor.run_continuous())
        except KeyboardInterrupt:
            print("\nMonitor stopped by user")


if __name__ == "__main__":
    main()
