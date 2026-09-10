"""
Freebuff Trading Platform — Main Entry Point

Usage:
    python -m src.app              # Start the platform
    python -m src.app --backtest   # Run backtesting mode
    python -m src.app --status     # Show system status
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

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
from src.strategies.registry import auto_discover, get_strategy_ids

# Phase 5: AI Scorer
from src.ai.scorer import RuleBasedScorer
from src.ai.context_analyzer import ContextAnalyzer

# Phase 1: Risk Engine
from src.risk.manager import RiskEngine

# Phase 1: Execution
from src.execution.order_manager import OrderManager
from src.execution.position_tracker import PositionTracker

# Phase 6: Setup Logger
from src.storage.models import get_engine, get_session_factory, Base
from src.storage.setup_logger import SetupLogger

logger = get_logger(__name__)



def setup_auth_credentials() -> None:
    """Setup Auth Login credentials on remote server from environment variables."""
    codex_auth = os.getenv("CODEX_AUTH_JSON", "").strip()
    if codex_auth:
        target_dir = os.path.expanduser("~/.codex")
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, "auth.json")
        try:
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(codex_auth)
            logger.info("✅ CODEX_AUTH_JSON successfully initialized in %s", target_file)
        except Exception as e:
            logger.error("Failed writing CODEX_AUTH_JSON: %s", e)

    adc_json = os.getenv("GOOGLE_ADC_JSON", "").strip()
    if adc_json:
        target_dir = os.path.expanduser("~/.config/gcloud")
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, "application_default_credentials.json")
        try:
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(adc_json)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = target_file
            logger.info("✅ GOOGLE_ADC_JSON successfully initialized in %s", target_file)
        except Exception as e:
            logger.error("Failed writing GOOGLE_ADC_JSON: %s", e)


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
        setup_auth_credentials()
        logger.info(
            f"Starting Freebuff Trading Platform v{settings.app.version} "
            f"(mode={settings.trading_mode})"
        )
        logger.info(f"Strategies loaded: {get_strategy_ids()}")

        # Setup event handlers
        self._setup_event_handlers()

        # Initialize database (risk engine + setup logger)
        engine = get_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._session_factory = get_session_factory(engine)
        self._db_session = self._session_factory()
        self._risk_engine = RiskEngine(
            self._db_session, spread_monitor=self._spread_monitor
        )
        self._setup_logger = SetupLogger(self._db_session)
        logger.info(f"Database connected: {settings.database_url}")

        # Connect to MT5 (retry loop so the process stays alive)
        logger.info("Connecting to MT5...")
        while True:
            connected = await self._mt5.connect()
            if connected:
                logger.info("✅ MT5 Connected successfully!")
                break
            if settings.mt5_mode == "bridge":
                logger.warning(
                    f"⏳ Waiting for MT5 Bridge at {settings.bridge_url}... "
                    "Ensure MT5 terminal is running and logged in. Retrying in 10s..."
                )
            else:
                logger.warning(
                    "⏳ Waiting for MT5 terminal to start and log in. Retrying in 10s..."
                )
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                return

        self._running = True

        # Initialize data feed
        symbol = settings.primary_symbol
        logger.info(f"Initializing data feed for {symbol}...")
        await self._data_feed.initialize(symbol)
        asyncio.create_task(self._data_feed.start_polling(symbol))

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
        if self._db_session:
            self._db_session.close()
        await self._mt5.disconnect()
        logger.info("Platform stopped cleanly")

    def _setup_event_handlers(self) -> None:
        """Wire event bus subscriptions."""

        async def on_circuit_breaker(data: Any) -> None:
            reason = data.get("reason") if isinstance(data, dict) else str(data)
            logger.critical(
                f"🚨 EMERGENCY: Circuit breaker triggered! "
                f"Reason: {reason}. Halting trading."
            )
            await self.stop()

        async def on_order_filled(data: Any) -> None:
            if isinstance(data, dict):
                logger.info(
                    f"💰 Order filled: {data.get('symbol')} "
                    f"{data.get('volume')} lots @ {data.get('price')}"
                )

        event_bus.subscribe(EventType.CIRCUIT_BREAKER, on_circuit_breaker)
        event_bus.subscribe(EventType.ORDER_FILLED, on_order_filled)

    async def _main_loop(self, symbol: str) -> None:
        """Main evaluation loop: runs on each polling cycle."""
        logger.info(f"Main trading loop started for {symbol}")

        while self._running:
            try:
                # Check session
                session = get_current_session()

                # Get current tick & spread
                tick = await self._mt5.get_current_price(symbol)
                spread_pips = self._spread_monitor.get_spread_pips(
                    tick.bid, tick.ask
                )

                # Build multi-timeframe context
                candles_by_tf = {
                    "M5": self._data_feed.get_cached_candles("M5"),
                    "M15": self._data_feed.get_cached_candles("M15"),
                    "H1": self._data_feed.get_cached_candles("H1"),
                    "H4": self._data_feed.get_cached_candles("H4"),
                }

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

        # Step 2a: Rule-based AI Scoring (fast, no API call)
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

        # Step 2b: EQH/EQL Detection (ตรวจ Liquidity Pools)
        h1_candles = ctx.candles_by_tf.get("H1", [])
        eql_result = self._eql_detector.detect(h1_candles)
        logger.info(f"EQL: {eql_result.summary}")

        # Step 2c: AI Council Debate (Gemini Bull vs GPT Bear)
        setup_context = {
            "symbol": candidate.symbol,
            "direction": candidate.direction.value,
            "entry_price": float(candidate.entry_price or current_price),
            "stop_loss": float(candidate.stop_loss or 0),
            "take_profit": float(candidate.take_profit_1 or 0),
            "rr_ratio": float(candidate.rr_ratio or 0),
            "rule_score": ai_decision.rule_score,
            "confluences": candidate.confluences or [],
            "h4_bias": str(ctx.htf_bias) if hasattr(ctx, "htf_bias") else "N/A",
            "h1_structure": str(ctx.primary_structure) if hasattr(ctx, "primary_structure") else "N/A",
            "m5_entry": candidate.strategy_id,
            "eql_summary": eql_result.summary,
            "displacement_detected": bool(getattr(candidate, "displacement", False)),
        }

        council = await self._ai_council.evaluate(setup_context)

        logger.info(
            f"AI Council: {council.final_verdict} "
            f"(Gemini={council.gemini_verdict.verdict}, "
            f"GPT={council.gpt_verdict.verdict}, "
            f"Score={council.combined_score})"
        )

        # Council said SKIP or HARD_SKIP
        if not council.should_execute:
            logger.info(f"Council SKIP: {council.debate_summary_th}")
            if self._setup_logger:
                await self._setup_logger.log_skipped(
                    candidate,
                    reason=council.recommendation,
                    gemini_verdict=council.gemini_verdict.verdict,
                    gemini_score=council.gemini_verdict.confidence,
                    gemini_narrative=council.gemini_verdict.narrative_th,
                    gpt_verdict=council.gpt_verdict.verdict,
                    gpt_score=council.gpt_verdict.confidence,
                    gpt_narrative=council.gpt_verdict.narrative_th,
                    debate_summary=council.debate_summary_th,
                    eql_summary=eql_result.summary,
                )
            # Telegram alert for disagreement
            if council.final_verdict == "SKIP":  # Disagreement
                import asyncio
                asyncio.create_task(alert_trade_skipped(
                    symbol=candidate.symbol,
                    reason=council.recommendation,
                    gemini_say=council.gemini_verdict.narrative_th,
                    gpt_say=council.gpt_verdict.narrative_th,
                ))
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
                        candidate=candidate,
                        ai_decision=ai_decision,
                        risk_decision=risk_decision,
                        gemini_verdict=council.gemini_verdict.verdict,
                        gemini_score=council.gemini_verdict.confidence,
                        gemini_narrative=council.gemini_verdict.narrative_th,
                        gpt_verdict=council.gpt_verdict.verdict,
                        gpt_score=council.gpt_verdict.confidence,
                        gpt_narrative=council.gpt_verdict.narrative_th,
                        debate_summary=council.debate_summary_th,
                        eql_summary=eql_result.summary,
                    )
                logger.info(
                    f"✅ TRADE EXECUTED: ticket={result.ticket} "
                    f"price={result.price} volume={result.volume} "
                    f"SL={request.sl:.2f} TP={request.tp:.2f}"
                )
                # Telegram alert
                import asyncio as _asyncio
                _asyncio.create_task(alert_trade_opened(TradeAlert(
                    symbol=candidate.symbol,
                    direction=candidate.direction.value,
                    entry_price=float(result.price or current_price),
                    stop_loss=float(request.sl),
                    take_profit=float(request.tp),
                    rule_score=ai_decision.rule_score,
                    gemini_score=council.gemini_verdict.confidence,
                    gpt_score=council.gpt_verdict.confidence,
                    gemini_verdict=council.gemini_verdict.verdict,
                    gpt_verdict=council.gpt_verdict.verdict,
                    combined_verdict=council.final_verdict,
                    narrative_th=council.debate_summary_th,
                )))
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
                    candidate=candidate,
                    ai_decision=ai_decision,
                    risk_decision=risk_decision,
                    gemini_verdict=council.gemini_verdict.verdict,
                    gemini_score=council.gemini_verdict.confidence,
                    gemini_narrative=council.gemini_verdict.narrative_th,
                    gpt_verdict=council.gpt_verdict.verdict,
                    gpt_score=council.gpt_verdict.confidence,
                    gpt_narrative=council.gpt_verdict.narrative_th,
                    debate_summary=council.debate_summary_th,
                    eql_summary=eql_result.summary,
                )


async def _run_status() -> None:
    """Print system status and exit."""
    auto_discover()
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
