"""Paper trading tracker for Binance USDT-M Futures.

Simulates strategy execution and risk accounting against historical
Binance candle data using Binance contract size and fee models.

Usage:
    python -m src.live.paper_trader --symbol BTCUSDT --days 30
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


class PaperTrader:
    """Simulate paper trading on Binance USDT-M Futures."""

    def __init__(self, symbol: str = "BTCUSDT", initial_balance: float = 10000.0, risk_per_trade: float = 0.01):
        self.symbol = symbol.upper()
        self.strategy = FVGReversalStrategy()
        self.context_builder = ContextBuilder()
        self.ai_scorer = RuleBasedScorer()
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade  # default 1%
        self.taker_fee_pct = 0.0005  # 0.05% Binance Futures taker fee
        self.gateway = BinanceGateway()

    async def fetch_historical_candles(self, days: int = 30) -> list[Candle]:
        """Fetch daily/hourly candles from Binance."""
        if not self.gateway.connected:
            await self.gateway.connect()
        # Fetch H1 candles for the period (24 * days)
        limit = min(days * 24 + 50, 1500)
        return await self.gateway.get_ohlcv(self.symbol, "H1", count=limit)

    def run_simulation_on_candles(self, candles: list[Candle], days: int = 30) -> dict:
        """Run paper trading simulation on provided candle list."""
        if len(candles) < 30:
            return {"error": "Insufficient data"}

        equity = self.initial_balance
        peak_equity = equity
        max_drawdown = 0.0
        trades: list[dict] = []
        equity_curve = [{"date": candles[0].timestamp.isoformat(), "equity": equity}]

        start_idx = 30
        for i in range(start_idx, len(candles)):
            current_candle = candles[i]
            current_price = current_candle.close

            # Check open positions
            for trade in trades:
                if trade["status"] == "OPEN":
                    hit = False
                    exit_price = 0.0

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
                            gross_pnl = (exit_price - trade["entry"]) * trade["volume"]
                        else:
                            gross_pnl = (trade["entry"] - exit_price) * trade["volume"]

                        # Binance fee model: entry + exit taker fee
                        entry_fee = trade["entry"] * trade["volume"] * self.taker_fee_pct
                        exit_fee = exit_price * trade["volume"] * self.taker_fee_pct
                        pnl = gross_pnl - (entry_fee + exit_fee)

                        equity += pnl
                        trade["status"] = "CLOSED"
                        trade["exit_price"] = exit_price
                        trade["exit_time"] = current_candle.timestamp.isoformat()
                        trade["pnl"] = round(pnl, 2)
                        trade["outcome"] = "WIN" if pnl > 0 else "LOSS"

            # Check for new entry setup
            available = candles[max(0, i - 30):i + 1]
            if len(available) < 20:
                equity_curve.append({"date": current_candle.timestamp.isoformat(), "equity": equity})
                continue

            try:
                ctx = self.context_builder.build(
                    symbol=self.symbol,
                    candles_by_tf={"M15": available, "H1": available, "H4": available},
                    primary_tf="H1",
                    htf="H4",
                )
            except Exception:
                equity_curve.append({"date": current_candle.timestamp.isoformat(), "equity": equity})
                continue

            candidate = self.strategy.analyze(
                context=ctx,
                current_candle=current_candle,
                current_price=current_price,
                spread=1.0,
                session="crypto_continuous",
            )

            if candidate and candidate.rr_ratio >= 2.0:
                ai_decision = self.ai_scorer.score(candidate, ctx, spread=1.0, session="crypto_continuous")
                if ai_decision.ai_score >= 70:
                    risk_amount = equity * self.risk_per_trade
                    sl_distance = abs(candidate.entry_price - candidate.stop_loss)
                    if sl_distance > 0:
                        volume = risk_amount / sl_distance
                        volume = max(0.001, round(volume, 3))
                        trades.append({
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
                        })

            if equity > peak_equity:
                peak_equity = equity
            dd = (peak_equity - equity) / peak_equity * 100.0 if peak_equity > 0 else 0.0
            if dd > max_drawdown:
                max_drawdown = dd

            equity_curve.append({"date": current_candle.timestamp.isoformat(), "equity": round(equity, 2)})

        # Close any open trades at last candle close
        for trade in trades:
            if trade["status"] == "OPEN":
                last_price = candles[-1].close
                if trade["direction"] == "BUY":
                    gross_pnl = (last_price - trade["entry"]) * trade["volume"]
                else:
                    gross_pnl = (trade["entry"] - last_price) * trade["volume"]
                fee = (trade["entry"] + last_price) * trade["volume"] * self.taker_fee_pct
                pnl = gross_pnl - fee
                equity += pnl
                trade["status"] = "CLOSED"
                trade["exit_price"] = last_price
                trade["exit_time"] = candles[-1].timestamp.isoformat()
                trade["pnl"] = round(pnl, 2)
                trade["outcome"] = "WIN" if pnl > 0 else "LOSS"

        closed_trades = [t for t in trades if t["status"] == "CLOSED"]
        wins = [t for t in closed_trades if t["outcome"] == "WIN"]
        losses = [t for t in closed_trades if t["outcome"] == "LOSS"]

        total_profit = sum(t["pnl"] for t in wins)
        total_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = total_profit / total_loss if total_loss > 0 else (99.0 if total_profit > 0 else 0.0)

        return {
            "symbol": self.symbol,
            "initial_balance": self.initial_balance,
            "final_equity": round(equity, 2),
            "net_profit": round(equity - self.initial_balance, 2),
            "return_pct": round((equity - self.initial_balance) / self.initial_balance * 100.0, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "total_trades": len(closed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed_trades) * 100.0, 1) if closed_trades else 0.0,
            "profit_factor": round(profit_factor, 2),
            "trades": closed_trades,
            "equity_curve": equity_curve,
        }

    async def run_simulation(self, days: int = 30) -> dict:
        """Fetch candles and run simulation."""
        print(f"\n[BINANCE PAPER TRADING] Simulating {self.symbol} for last {days} days...")
        candles = await self.fetch_historical_candles(days=days)
        result = self.run_simulation_on_candles(candles, days=days)
        await self.gateway.disconnect()
        return result


def main():
    parser = argparse.ArgumentParser(description="Binance Paper Trading Simulator")
    parser.add_argument("--symbol", type=str, default=settings.binance_symbol or "BTCUSDT", help="Trading symbol")
    parser.add_argument("--days", type=int, default=30, help="Days to simulate")
    args = parser.parse_args()

    trader = PaperTrader(symbol=args.symbol)
    result = asyncio.run(trader.run_simulation(days=args.days))

    print("\n" + "=" * 50)
    print(f"📊 BINANCE PAPER TRADING RESULTS: {result.get('symbol')}")
    print("=" * 50)
    print(f"Initial Balance:  ${result.get('initial_balance'):,.2f}")
    print(f"Final Equity:     ${result.get('final_equity'):,.2f}")
    print(f"Net Profit:       ${result.get('net_profit'):+,.2f} ({result.get('return_pct'):+.2f}%)")
    print(f"Max Drawdown:     {result.get('max_drawdown_pct'):.2f}%")
    print(f"Total Trades:     {result.get('total_trades')}")
    print(f"Win Rate:         {result.get('win_rate')}% ({result.get('wins')}W / {result.get('losses')}L)")
    print(f"Profit Factor:    {result.get('profit_factor')}")
    print("=" * 50)


if __name__ == "__main__":
    main()
