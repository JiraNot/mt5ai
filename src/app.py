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
import signal

from src.core.config import settings
from src.core.events import EventType, event_bus
from src.core.logger import get_logger, setup_logging
from src.core.types import (
    AIDecision,
    Direction,
    OrderRequest,
    RiskDecision,
    SetupDecision,
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
from src.storage.setup_logger import SetupLogger

logger = get_logger(__name__)


class TradingPlatform:
    """
    Main orchestrator — wires all components together.

    Pipeline on each new candle:
        MT5 Data → Structure Engine → Strategy Plugins → AI Scorer → Risk Engine → Execute
    """

    def __init__(self) -> None:
        # MT5
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
        logger.info("Platform stopped")

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
                f"✅ TRADE 
