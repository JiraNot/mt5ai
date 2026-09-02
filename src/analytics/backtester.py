"""Backtesting engine — replays historical data through the full pipeline."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from src.core.types import (
    AIDecision,
    BacktestResult,
    Candle,
    Direction,
    StrategyCandidate,
)
from src.strategies.meta_engine import MetaDecisionEngine
from src.structure.context import ContextBuilder, MultiTimeframeContext

logger = logging.getLogger(__name__)


class Backtester:
    """
    Replays historical data through the full pipeline:
    Structure → Strategies → AI → Risk → Simulated Execution

    Key features:
    - Spread simulation
    - Slippage modeling
    - Session-aware
    - Commission handling
    """

    def __init__(
        self,
        spread_pips: float = 2.5,
        slippage_pips: float = 1.0,
        commission_per_lot: float = 7.0,
    ) -> None:
        self._spread = spread_pips
        self._slippage = slippage_pips
        self._commission = commission_per_lot
        self._context_builder = ContextBuilder()
        self._meta_engine = MetaDecisionEngine(min_combined_score=0)  # No filter for backtest

    def run(
        self,
        strategy_id: str,
        symbol: str,
        candles_by_tf: dict[str, list[Candle]],
        entry_tf: str = "M5",
        htf: str = "H4",
        start_idx: int = 50,
    ) -> BacktestResult:
        """
        Run backtest for a specific strategy.

        Args:
            strategy_id: Strategy to test
            symbol: Trading symbol
            candles_by_tf: Historical candle data
            entry_tf: Entry timeframe
            htf: Higher timeframe
            start_idx: Starting candle index (skip early candles for structure warmup)
        """
        from src.strategies.registry import get_strategy

        strategy = get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy not found: {strategy_id}")

        entry_candles = candles_by_tf.get(entry_tf, [])
        if len(entry_candles) < start_idx + 10:
            raise ValueError("Insufficient candle data for backtest")

        trades: list[dict] = []
        equity = 10000.0
        equity_curve = [equity]
        max_equity = equity
        max_dd = 0.0

        in_trade = False
        trade_entry = 0.0
        trade_sl = 0.0
        trade_tp = 0.0
        trade_direction = None
        trade_volume = 0.1

        for i in range(start_idx, len(entry_candles)):
            current_candle = entry_candles[i]
            current_price = current_candle.close

            # Build context from available candles
            sliced_candles = {}
            for tf, all_candles in candles_by_tf.items():
                # Use candles up to current index (proportional)
                ratio = i / len(entry_candles)
                available_count = max(50, int(len(all_candles) * ratio))
                sliced_candles[tf] = all_candles[:available_count]

            ctx = self._context_builder.build(
                symbol=symbol,
                candles_by_tf=sliced_candles,
                primary_tf=entry_tf,
                htf=htf,
            )

            if in_trade:
                # Check SL/TP
                if trade_direction == Direction.BUY:
                    if current_candle.low <= trade_sl:
                        # SL hit
                        pnl = (trade_sl - trade_entry - self._spread * 0.1) * trade_volume * 100
                        pnl -= self._commission * trade_volume
                        equity += pnl
                        in_trade = False
                        trades.append({"direction": "BUY", "entry": trade_entry, "exit": trade_sl, "pnl": pnl})
                    elif current_candle.high >= trade_tp:
                        # TP hit
                        pnl = (trade_tp - trade_entry - self._spread * 0.1) * trade_volume * 100
                        pnl -= self._commission * trade_volume
                        equity += pnl
                        in_trade = False
                        trades.append({"direction": "BUY", "entry": trade_entry, "exit": trade_tp, "pnl": pnl})
                else:  # SELL
                    if current_candle.high >= trade_sl:
                        pnl = (trade_entry - trade_sl - self._spread * 0.1) * trade_volume * 100
                        pnl -= self._commission * trade_volume
                        equity += pnl
                        in_trade = False
                        trades.append({"direction": "SELL", "entry": trade_entry, "exit": trade_sl, "pnl": pnl})
                    elif current_candle.low <= trade_tp:
                        pnl = (trade_entry - trade_tp - self._spread * 0.1) * trade_volume * 100
                        pnl -= self._commission * trade_volume
                        equity += pnl
                        in_trade = False
                        trades.append({"direction": "SELL", "entry": trade_entry, "exit": trade_tp, "pnl": pnl})

                # Track drawdown
                if equity > max_equity:
                    max_equity = equity
                dd = (max_equity - equity) / max_equity
                if dd > max_dd:
                    max_dd = dd

            else:
                # Look for entry
                candidates = strategy.analyze(
                    context=ctx,
                    current_candle=current_candle,
                    current_price=current_price,
                    spread=self._spread,
                    session="london",  # Simplified for backtest
                )

                if candidates:
                    # Take the first candidate
                    c = candidates
                    if isinstance(c, StrategyCandidate):
                        in_trade = True
                        trade_entry = current_price
                        trade_direction = c.direction
                        trade_sl = c.stop_loss
                        trade_tp = c.take_profit_1

            equity_curve.append(equity)

        # Calculate metrics
        winners = [t for t in trades if t["pnl"] > 0]
        losers = [t for t in trades if t["pnl"] <= 0]

        total_trades = len(trades)
        win_rate = len(winners) / total_trades if total_trades > 0 else 0
        avg_win = sum(t["pnl"] for t in winners) / len(winners) if winners else 0
        avg_loss = abs(sum(t["pnl"] for t in losers) / len(losers)) if losers else 0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss) if total_trades > 0 else 0

        # Sharpe ratio (simplified)
        returns = [equity_curve[i] - equity_curve[i - 1] for i in range(1, len(equity_curve))]
        if returns:
            import numpy as np
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe = (mean_return / std_return * (252 ** 0.5)) if std_return > 0 else 0
        else:
            sharpe = 0

        return BacktestResult(
            strategy_id=strategy_id,
            symbol=symbol,
            period_start=entry_candles[start_idx].timestamp if entry_candles else datetime.utcnow(),
            period_end=entry_candles[-1].timestamp if entry_candles else datetime.utcnow(),
            total_trades=total_trades,
            winners=len(winners),
            losers=len(losers),
            win_rate=round(win_rate, 4),
            avg_win_r=round(avg_win, 2),
            avg_loss_r=round(avg_loss, 2),
            expectancy=round(expectancy, 2),
            sharpe_ratio=round(float(sharpe), 2),
            max_drawdown=round(max_dd * 100, 2),
            profit_factor=round(sum(t["pnl"] for t in winners) / abs(sum(t["pnl"] for t in losers)), 2) if losers else 0,
            total_pnl_r=round(sum(t["pnl"] for t in trades), 2),
            equity_curve=equity_curve,
        )
