"""
Freebuff Trading Platform — Main Entry Point

Usage:
    python -m src.app              # Start the platform (paper mode)
    python -m src.app --backtest   # Run backtesting mode
    python -m src.app --status     # Show system status
"""

from __future__ import annotations

import argparse
import asyncio

from src.core.config import settings
from src.core.events import EventType, event_bus
from src.core.logger import get_logger, setup_logging
from src.core.types import (
    OrderRequest,
    RiskDecision,
    StrategyCandidate,
)
from src.market.data_feed import DataFeed
from src.market.mt5_connection import MT5Connection
from src.market.session_tracker import get_current_session
from src.market.spread_monitor import SpreadMonitor

# Phase 2: Structure Engine
from src.structure.context import ContextBuilder, MultiTimeframeContext

# Phase 3: Strategy Engine
from src.strategies.meta_engine import MetaDecisionEngine
from src.strategies.registry import auto_discover

# Phase 5: AI Scorer
from src.ai.scorer import RuleBasedScorer
from src.ai.context_analyzer import ContextAnalyzer

# Phase 1: Risk Engine
from src.risk.manager import RiskEngine

# Phase 1: Execution
from src.execution.order_manager import OrderManager
from src.execution.position_tracker import PositionTracker

# Phase 6: Setup Logger
from src.storage.models import get_engine, get_session_factory
from src.storage.setup_logger import SetupLogger

logger = get_logger(__name__)


class TradingPlatform:
    """
    Main orchestrator — wires all components together.

    Pipeline on each new candle:
        MT5 Data → Structure Engine → Strategy Plugins → AI Scorer → Risk Engine → Execute
    """

    def __init__(self) -> None:
        # MT5 — local MetaTrader5 package / Wine, or remote Windows bridge
        if settings.mt5_mode == "bridge":
            from src.market.bridge_gateway import BridgeGateway

            self._mt5: MT5Connection | BridgeGateway = BridgeGateway()
            logger.info(f"MT5 mode: bridge ({settings.bridge_url})")
        else:
            self._mt5 = MT5Connection()

        self._data_feed = DataFeed(self._mt5)
        self._spread_monitor = SpreadMonitor(settings.primary_symbol)

        # Structure
        self._context_builder = ContextBuilder()

        # Strategies
        auto_discover()  # Auto-register all strategy plugins
        self._meta_engine = MetaDecisionEngine()

        # AI
        self._ai_scorer = RuleBasedScorer()
        self._context_analyzer = ContextAnalyzer()

        # Execution
        self._order_manager = OrderManager(self._mt5)
        self._position_tracker = PositionTracker(self._mt5)

        # Risk (initialized after DB connection)
        self._risk_engine: RiskEngine | None = None
        self._setup_logger: SetupLogger | None = None

        # Database
        self._db_session = None
        self._session_factory = None

        self._running = False

    async def start(self) -> None:
        """Start the trading platform."""
        logger.info(
            f"Starting Freebuff Trading Platform v{settings.app.version} "
            f"(mode={settings.trading_mode})"
        )
        logger.info(f"Strategies loaded: {list(self._meta_engine._min_score)}")

        # Setup event handlers
        self._setup_event_handlers()

        # Initialize database (risk engine + setup logger)
        engine = get_engine(settings.database_url)
        self._session_factory = get_session_factory(engine)
        self._db_session = self._session_factory()
        self._risk_engine = RiskEngine(
            self._db_session, spread_monitor=self._spread_monitor
        )
        self._setup_logger = SetupLogger(self._db_session)
        logger.info(f"Database connected: {settings.database_url}")

        # Connect to MT5
        connected = await self._mt5.connect()
        if not connected:
            logger.error("Failed to connect to MT5. Exiting.")
            return

        self._running = True

        # Initialize data feed
        symbol = settings.primary_symbol
        logger.info(f"Initializing data feed for {symbol}...")
        await self._data_feed.initialize(symbol)

        # Start main loop
        session = get_current_session()
        logger.info(f"Current session: {session}")

        try:
            await self._main_loop(symbol)
        except asyncio.CancelledError:
            logger.info("Platform shutdown requested")
        except Exception as e:
            logger.error(f"Platform error: {e}", exc_info=True)
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the trading platform."""
        self._running = False
        logger.info("Stopping platform...")
        await self._data_feed.stop_polling()
        await self._mt5.disconnect()
        if self._db_session is not None:
            await self._db_session.close()
            self._db_session = None
        logger.info("Platform stopped")

    def _setup_event_handlers(self) -> None:
        """Subscribe platform-level event handlers for observability."""

        async def on_order_failed(payload: dict) -> None:
            result = payload.get("result")
            logger.error(f"EVENT order_failed: {result}")

        async def on_position_opened(payload: dict) -> None:
            position = payload.get("position")
            logger.info(f"EVENT position_opened: {position}")

        async def on_position_closed(payload: dict) -> None:
            position = payload.get("position")
            logger.info(f"EVENT position_closed: {position}")

        event_bus.subscribe(EventType.ORDER_FAILED, on_order_failed)
        event_bus.subscribe(EventType.POSITION_OPENED, on_position_opened)
        event_bus.subscribe(EventType.POSITION_CLOSED, on_position_closed)

    async def _main_loop(self, symbol: str) -> None:
        """Main trading loop — processes each tick/candle."""
        logger.info("Entering main loop...")

        while self._running:
            try:
                # Get current tick
                tick = await self._mt5.get_current_price(symbol)
                spread_pips = tick.spread / 0.1  # Convert to pips for XAUUSD
                self._spread_monitor.update(spread_pips)
                session = get_current_session()

                logger.debug(
                    f"Session={session} | Spread={spread_pips:.1f} "
                    f"({self._spread_monitor.get_spread_status(spread_pips)}) "
                    f"| Bid={tick.bid:.2f}"
                )

                # Build context from cached data
                candles_by_tf = {}
                for tf in settings.data.timeframes.get("structure", ["H4", "H1", "M15", "M5"]):
                    candles = self._data_feed.get_candles(symbol, tf)
                    if candles:
                        candles_by_tf[tf] = candles

                if not candles_by_tf:
                    await asyncio.sleep(5)
                    continue

                ctx = self._context_builder.build(
                    symbol=symbol,
                    candles_by_tf=candles_by_tf,
                    primary_tf="M5",
                    htf="H4",
                )
                ctx.current_price = tick.mid
                ctx.spread = spread_pips

                # Run strategy pipeline
                await self._process_strategies(ctx, tick.mid, spread_pips, session)

                # Sync positions
                await self._position_tracker.sync_positions(symbol)

                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _process_strategies(
        self,
        ctx: MultiTimeframeContext,
        current_price: float,
        spread: float,
        session: str,
    ) -> None:
        """Full strategy pipeline: Strategies → AI → Risk → Execute."""

        # Step 1: Run all strategies
        candidates = await self._meta_engine.evaluate(
            context=ctx,
            current_price=current_price,
            spread=spread,
            session=session,
        )

        if not candidates:
            return

        # Process top candidate
        for candidate in candidates[:3]:  # Process top 3 candidates
            await self._process_candidate(candidate, ctx, current_price, spread, session)

    async def _process_candidate(
        self,
        candidate: StrategyCandidate,
        ctx: MultiTimeframeContext,
        current_price: float,
        spread: float,
        session: str,
    ) -> None:
        """Process a single candidate through AI → Risk → Execute."""

        # Step 2: AI Scoring
        ai_decision = self._ai_scorer.score(
            candidate=candidate,
            context=ctx,
            spread=spread,
            session=session,
        )

        if ai_decision.decision == "WAIT":
            logger.info(
                f"AI SKIP: {candidate.strategy_id} "
                f"score={ai_decision.combined_score} — below threshold"
            )
            if self._setup_logger:
                await self._setup_logger.log_skipped(
                    candidate,
                    reason=(
                        f"AI score {ai_decision.combined_score} "
                        f"< {settings.ai.min_combined_score}"
                    ),
                )
            return

        # Step 3: Risk Engine Evaluation
        account = await self._mt5.get_account_info()
        positions = await self._position_tracker.sync_positions(candidate.symbol)

        risk_decision = RiskDecision(approved=False)  # Default rejection
        if self._risk_engine:
            risk_decision = await self._risk_engine.evaluate(
                candidate=candidate,
                ai_decision=ai_decision,
                account_balance=account.balance,
                account_equity=account.equity,
                open_positions_count=len(positions),
                total_exposure=self._position_tracker.get_total_exposure(),
                current_spread=spread,
                session=session,
            )

        # Step 4: Execute or log rejection
        if risk_decision.approved:
            logger.info(
                f"✅ TRADE APPROVED: {candidate.strategy_id} "
                f"{candidate.direction.value} {candidate.symbol} | "
                f"lots={risk_decision.position_size_lots} "
                f"risk=${risk_decision.risk_amount:.2f} "
                f"({risk_decision.risk_pct * 100:.2f}%)"
            )

            request = OrderRequest(
                symbol=candidate.symbol,
                direction=candidate.direction,
                volume=risk_decision.position_size_lots,
                sl=risk_decision.adjusted_sl or candidate.stop_loss,
                tp=risk_decision.adjusted_tp1 or candidate.take_profit_1,
                comment=f"{candidate.strategy_id}",
            )
            result = await self._order_manager.send_market_order(request)

            if result.success:
                if self._setup_logger:
                    await self._setup_logger.log_traded(
                        candidate, ai_decision, risk_decision
                    )
                logger.info(
                    f"✅ TRADE EXECUTED: ticket={result.ticket} "
                    f"price={result.price} volume={result.volume} "
                    f"SL={request.sl:.2f} TP={request.tp:.2f}"
                )
            else:
                logger.error(
                    f"❌ ORDER FAILED: {candidate.strategy_id} — "
                    f"{result.error_message}"
                )
        else:
            reason = risk_decision.rejection_reason or "unknown"
            logger.info(
                f"❌ RISK REJECTED: {candidate.strategy_id} — {reason}"
            )
            if self._setup_logger:
                await self._setup_logger.log_rejected(
                    candidate, ai_decision, risk_decision
                )


async def _run_status() -> None:
    """Print system status and exit."""
    auto_discover()
    from src.strategies.registry import get_strategy_ids  # noqa: PLC0415

    print("🏦 Freebuff Trading Platform — Status")
    print("=====================================")
    print(f"Version:        {settings.app.version}")
    print(f"Mode:           {settings.trading_mode}")
    print(f"Symbol:         {settings.primary_symbol}")
    print(f"Database:       {settings.database_url}")
    print(f"Risk per trade: {settings.risk.risk_per_trade_pct * 100:.1f}%")
    print(f"Max daily loss: {settings.risk.max_daily_loss_pct * 100:.1f}%")
    print(f"Min R:R:        1:{settings.risk.min_rr}")
    print(f"AI min score:   {settings.ai.min_combined_score}")
    print(f"Strategies:     {', '.join(get_strategy_ids())}")
    print(f"Session (now):  {get_current_session()}")


async def _run_backtest() -> None:
    """Run backtesting mode over local CSV data."""
    import pandas as pd  # noqa: PLC0415

    from src.analytics.backtester import Backtester  # noqa: PLC0415
    from src.core.types import Candle  # noqa: PLC0415

    csv_path = "gold_1h.csv"
    logger.info(f"Backtest mode — loading {csv_path}...")

    df = pd.read_csv(csv_path, parse_dates=["Datetime"])
    candles = [
        Candle(
            timestamp=row.Datetime.to_pydatetime(),
            open=float(row.Open),
            high=float(row.High),
            low=float(row.Low),
            close=float(row.Close),
            volume=float(row.Volume),
        )
        for row in df.itertuples(index=False)
    ]
    logger.info(f"Loaded {len(candles)} H1 candles")

    backtester = Backtester()
    result = backtester.run(
        strategy_id="fvg_final",
        symbol=settings.primary_symbol,
        candles_by_tf={"H1": candles},
        entry_tf="H1",
        htf="H1",
    )
    logger.info(f"Backtest complete: {result}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Freebuff Trading Platform")
    parser.add_argument("--backtest", action="store_true", help="Run backtesting mode")
    parser.add_argument("--status", action="store_true", help="Show system status")
    args = parser.parse_args()

    setup_logging(
        level=settings.log_level,
        log_format=settings.logging_config.format,
        log_file=settings.logging_config.file,
    )

    if args.status:
        asyncio.run(_run_status())
    elif args.backtest:
        asyncio.run(_run_backtest())
    else:
        platform = TradingPlatform()
        try:
            asyncio.run(platform.start())
        except KeyboardInterrupt:
            logger.info("Interrupted by user")


if __name__ == "__main__":
    main()
