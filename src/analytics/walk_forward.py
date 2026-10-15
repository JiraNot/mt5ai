"""Walk-Forward Backtesting Suite for Binance AI Platform.

Splits historical data into rolling In-Sample (Train) and Out-of-Sample (Test)
windows to evaluate strategy robustness, prevent overfitting, and measure
Walk-Forward Efficiency (WFE) before deployment to Demo/Live trading.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.core.types import BacktestResult, Candle, Direction, StrategyCandidate
from src.strategies.meta_engine import MetaDecisionEngine
from src.structure.context import ContextBuilder

logger = logging.getLogger(__name__)


@dataclass
class WindowResult:
    """Performance metrics for a single Walk-Forward window."""

    window_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    in_sample: BacktestResult
    out_of_sample: BacktestResult
    wfe_pct: float  # Walk-Forward Efficiency (OOS Profit Factor / IS Profit Factor)
    robustness: str  # "ROBUST", "MODERATE", "OVERFITTED"


@dataclass
class WalkForwardReport:
    """Consolidated Walk-Forward validation report."""

    strategy_id: str
    symbol: str
    total_windows: int
    windows: list[WindowResult]
    total_oos_trades: int
    oos_win_rate_pct: float
    oos_profit_factor: float
    oos_net_pnl: float
    oos_max_drawdown_pct: float
    oos_expectancy: float
    average_wfe_pct: float
    verdict: str  # "PASS (ROBUST MODEL)", "CAUTION (HIGH VARIANCE)", "FAIL (OVERFITTED)"
    summary_markdown: str = ""

    def generate_markdown(self) -> str:
        lines = [
            f"# 🧪 Walk-Forward Backtest Report — {self.strategy_id} ({self.symbol})",
            "",
            "## 📊 Overall Out-Of-Sample (Unseen Data) Performance",
            f"- **Verdict:** **{self.verdict}**",
            f"- **Walk-Forward Efficiency (WFE):** **{self.average_wfe_pct:.1f}%** (Target >= 50%)",
            f"- **Total OOS Trades:** {self.total_oos_trades} trades across {self.total_windows} rolling windows",
            f"- **OOS Win Rate:** **{self.oos_win_rate_pct:.1f}%**",
            f"- **OOS Profit Factor:** **{self.oos_profit_factor:.2f}**",
            f"- **OOS Net PnL:** **${self.oos_net_pnl:+,.2f}**",
            f"- **Max OOS Drawdown:** **{self.oos_max_drawdown_pct:.2f}%**",
            f"- **Expectancy Per Trade:** **${self.oos_expectancy:+,.2f}**",
            "",
            "## 🪟 Rolling Windows Performance Breakdown",
            "",
            "| Window | In-Sample PF | OOS PF | OOS Trades | OOS Win Rate | OOS Net PnL | WFE % | Robustness |",
            "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
        for w in self.windows:
            lines.append(
                f"| #{w.window_index} | {w.in_sample.profit_factor:.2f} | {w.out_of_sample.profit_factor:.2f} | "
                f"{w.out_of_sample.total_trades} | {w.out_of_sample.win_rate * 100:.1f}% | "
                f"${w.out_of_sample.total_pnl_r:+,.2f} | {w.wfe_pct:.1f}% | {w.robustness} |"
            )

        lines.extend([
            "",
            "> [!NOTE]",
            "> Walk-Forward Efficiency (WFE) measures how well strategy performance holds up on unseen future market data. A WFE > 50% with positive OOS Profit Factor is the benchmark for graduating to Demo/Live.",
        ])
        return "\n".join(lines)


class WalkForwardAnalyzer:
    """Runs rolling multi-window backtests on Binance USDT-M Futures data."""

    def __init__(
        self,
        spread_pips: float = 1.0,
        slippage_pips: float = 0.5,
        commission_per_lot: float = 0.8,
    ) -> None:
        self.spread = spread_pips
        self.slippage = slippage_pips
        self.commission = commission_per_lot
        self.context_builder = ContextBuilder()

    def simulate_segment(
        self,
        strategy: Any,
        symbol: str,
        candles_by_tf: dict[str, list[Candle]],
        entry_tf: str = "M5",
        htf: str = "H1",
        start_idx: int = 20,
    ) -> BacktestResult:
        """Simulate strategy execution on a specific candle segment."""
        entry_candles = candles_by_tf.get(entry_tf, [])
        if len(entry_candles) <= start_idx:
            now = datetime.now(timezone.utc)
            return BacktestResult(
                strategy_id=getattr(strategy, "id", "unknown"),
                symbol=symbol,
                period_start=now,
                period_end=now,
            )

        trades: list[dict[str, Any]] = []
        equity = 10000.0
        equity_curve = [equity]
        max_equity = equity
        max_dd = 0.0

        in_trade = False
        trade_entry = 0.0
        trade_sl = 0.0
        trade_tp = 0.0
        trade_direction: Direction | None = None
        trade_volume = 0.1

        # Crypto contract size = 1.0
        contract_size = 1.0

        for i in range(start_idx, len(entry_candles)):
            current_candle = entry_candles[i]
            current_price = current_candle.close

            # Context slice up to current index
            sliced = {
                tf: all_c[: max(10, int(len(all_c) * (i / len(entry_candles))))]
                for tf, all_c in candles_by_tf.items()
            }
            ctx = self.context_builder.build(
                symbol=symbol,
                candles_by_tf=sliced,
                primary_tf=entry_tf,
                htf=htf,
            )
            ctx.current_price = current_price
            ctx.spread = self.spread

            if in_trade:
                # Check SL / TP
                if trade_direction == Direction.BUY:
                    if current_candle.low <= trade_sl:
                        pnl = (trade_sl - trade_entry - self.spread * 0.1) * trade_volume * contract_size
                        pnl -= self.commission * trade_volume
                        equity += pnl
                        in_trade = False
                        trades.append({"direction": "BUY", "entry": trade_entry, "exit": trade_sl, "pnl": pnl})
                    elif current_candle.high >= trade_tp:
                        pnl = (trade_tp - trade_entry - self.spread * 0.1) * trade_volume * contract_size
                        pnl -= self.commission * trade_volume
                        equity += pnl
                        in_trade = False
                        trades.append({"direction": "BUY", "entry": trade_entry, "exit": trade_tp, "pnl": pnl})
                else:  # SELL
                    if current_candle.high >= trade_sl:
                        pnl = (trade_entry - trade_sl - self.spread * 0.1) * trade_volume * contract_size
                        pnl -= self.commission * trade_volume
                        equity += pnl
                        in_trade = False
                        trades.append({"direction": "SELL", "entry": trade_entry, "exit": trade_sl, "pnl": pnl})
                    elif current_candle.low <= trade_tp:
                        pnl = (trade_entry - trade_tp - self.spread * 0.1) * trade_volume * contract_size
                        pnl -= self.commission * trade_volume
                        equity += pnl
                        in_trade = False
                        trades.append({"direction": "SELL", "entry": trade_entry, "exit": trade_tp, "pnl": pnl})

                if equity > max_equity:
                    max_equity = equity
                dd = (max_equity - equity) / max_equity if max_equity > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd

            else:
                # Look for setup entry
                candidates = strategy.analyze(
                    context=ctx,
                    current_candle=current_candle,
                    current_price=current_price,
                    spread=self.spread,
                    session="london",
                )
                if candidates:
                    cand = candidates[0] if isinstance(candidates, list) else candidates
                    if isinstance(cand, StrategyCandidate):
                        in_trade = True
                        trade_entry = current_price
                        trade_direction = cand.direction
                        trade_sl = cand.stop_loss
                        trade_tp = cand.take_profit_1

            equity_curve.append(equity)

        # Calculate metrics
        winners = [t for t in trades if t["pnl"] > 0]
        losers = [t for t in trades if t["pnl"] <= 0]
        total_trades = len(trades)
        win_rate = (len(winners) / total_trades) if total_trades > 0 else 0.0
        tot_win_pnl = sum(t["pnl"] for t in winners)
        tot_loss_pnl = abs(sum(t["pnl"] for t in losers))
        pf = (tot_win_pnl / tot_loss_pnl) if tot_loss_pnl > 0 else (99.0 if tot_win_pnl > 0 else 0.0)
        net_pnl = tot_win_pnl - tot_loss_pnl
        expectancy = (net_pnl / total_trades) if total_trades > 0 else 0.0

        return BacktestResult(
            strategy_id=getattr(strategy, "id", "unknown"),
            symbol=symbol,
            period_start=entry_candles[start_idx].timestamp,
            period_end=entry_candles[-1].timestamp,
            total_trades=total_trades,
            winners=len(winners),
            losers=len(losers),
            win_rate=round(win_rate, 4),
            expectancy=round(expectancy, 2),
            max_drawdown=round(max_dd * 100, 2),
            profit_factor=round(pf, 2),
            total_pnl_r=round(net_pnl, 2),
            equity_curve=equity_curve,
        )

    def run_walk_forward(
        self,
        strategy_id: str,
        symbol: str,
        candles_by_tf: dict[str, list[Candle]],
        n_windows: int = 3,
        train_ratio: float = 0.65,
        entry_tf: str = "M5",
        htf: str = "H1",
    ) -> WalkForwardReport:
        """Execute rolling Walk-Forward analysis across historical candles."""
        from src.strategies.registry import get_strategy

        strategy = get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not registered")

        entry_candles = candles_by_tf.get(entry_tf, [])
        if len(entry_candles) < 60:
            raise ValueError(f"Insufficient candles for Walk-Forward analysis (found {len(entry_candles)}, need >= 60)")

        # Determine segment length
        n_windows = max(2, min(n_windows, 6))
        total_len = len(entry_candles)
        window_size = total_len // n_windows

        windows: list[WindowResult] = []
        all_oos_trades = 0
        all_oos_wins = 0
        all_oos_pnl = 0.0
        all_oos_loss = 0.0
        max_oos_dd = 0.0
        wfe_list: list[float] = []

        for w_idx in range(n_windows):
            w_start = w_idx * window_size
            w_end = (w_idx + 1) * window_size if w_idx < n_windows - 1 else total_len

            window_entry = entry_candles[w_start:w_end]
            split_idx = int(len(window_entry) * train_ratio)

            train_entry = window_entry[:split_idx]
            test_entry = window_entry[split_idx:]

            # Sliced higher timeframe candles proportionally
            def slice_htf(source_list: list[Candle], seg_start: int, seg_end: int) -> list[Candle]:
                if not source_list:
                    return []
                ratio_s = seg_start / total_len
                ratio_e = seg_end / total_len
                idx_s = int(ratio_s * len(source_list))
                idx_e = max(idx_s + 10, int(ratio_e * len(source_list)))
                return source_list[idx_s:idx_e]

            # 1. In-Sample (Train) Run
            train_tf = {
                entry_tf: train_entry,
                htf: slice_htf(candles_by_tf.get(htf, []), w_start, w_start + split_idx),
            }
            res_is = self.simulate_segment(
                strategy, symbol, train_tf, entry_tf=entry_tf, htf=htf, start_idx=10
            )

            # 2. Out-of-Sample (Test) Run
            test_tf = {
                entry_tf: test_entry,
                htf: slice_htf(candles_by_tf.get(htf, []), w_start + split_idx, w_end),
            }
            res_oos = self.simulate_segment(
                strategy, symbol, test_tf, entry_tf=entry_tf, htf=htf, start_idx=10
            )

            # Compute WFE
            if res_is.profit_factor > 0:
                wfe = (res_oos.profit_factor / res_is.profit_factor) * 100.0
            else:
                wfe = 100.0 if res_oos.profit_factor > 1.0 else 0.0
            wfe = min(150.0, max(0.0, wfe))
            wfe_list.append(wfe)

            if wfe >= 60.0 and res_oos.profit_factor >= 1.2:
                robustness = "ROBUST"
            elif wfe >= 40.0:
                robustness = "MODERATE"
            else:
                robustness = "OVERFITTED"

            windows.append(
                WindowResult(
                    window_index=w_idx + 1,
                    train_start=train_entry[0].timestamp if train_entry else datetime.now(timezone.utc),
                    train_end=train_entry[-1].timestamp if train_entry else datetime.now(timezone.utc),
                    test_start=test_entry[0].timestamp if test_entry else datetime.now(timezone.utc),
                    test_end=test_entry[-1].timestamp if test_entry else datetime.now(timezone.utc),
                    in_sample=res_is,
                    out_of_sample=res_oos,
                    wfe_pct=round(wfe, 1),
                    robustness=robustness,
                )
            )

            # Aggregate stats
            all_oos_trades += res_oos.total_trades
            all_oos_wins += res_oos.winners
            all_oos_pnl += res_oos.total_pnl_r
            if res_oos.max_drawdown > max_oos_dd:
                max_oos_dd = res_oos.max_drawdown

        avg_wfe = sum(wfe_list) / len(wfe_list) if wfe_list else 0.0
        oos_win_rate = (all_oos_wins / all_oos_trades * 100.0) if all_oos_trades > 0 else 0.0
        oos_pf = (
            sum(w.out_of_sample.total_pnl_r for w in windows if w.out_of_sample.total_pnl_r > 0)
            / abs(sum(w.out_of_sample.total_pnl_r for w in windows if w.out_of_sample.total_pnl_r < 0))
            if abs(sum(w.out_of_sample.total_pnl_r for w in windows if w.out_of_sample.total_pnl_r < 0)) > 0
            else (99.0 if all_oos_pnl > 0 else 0.0)
        )
        oos_expectancy = (all_oos_pnl / all_oos_trades) if all_oos_trades > 0 else 0.0

        if avg_wfe >= 50.0 and oos_pf >= 1.3:
            verdict = "PASS (ROBUST MODEL)"
        elif avg_wfe >= 35.0:
            verdict = "CAUTION (HIGH VARIANCE)"
        else:
            verdict = "FAIL (OVERFITTED)"

        report = WalkForwardReport(
            strategy_id=strategy_id,
            symbol=symbol,
            total_windows=n_windows,
            windows=windows,
            total_oos_trades=all_oos_trades,
            oos_win_rate_pct=round(oos_win_rate, 1),
            oos_profit_factor=round(oos_pf, 2),
            oos_net_pnl=round(all_oos_pnl, 2),
            oos_max_drawdown_pct=round(max_oos_dd, 2),
            oos_expectancy=round(oos_expectancy, 2),
            average_wfe_pct=round(avg_wfe, 1),
            verdict=verdict,
        )
        report.summary_markdown = report.generate_markdown()
        return report
