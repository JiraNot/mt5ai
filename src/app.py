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
from datetime import datetime
from typing import Any

from src.core.config import settings
from src.core.ratios import reward_risk
from src.core.events import EventType, event_bus
from src.core.logger import get_logger, setup_logging
from src.core.runtime_control import get_candidate_policy, get_runtime_trading_mode
from src.core.runtime_provider_settings import sync_codex_auth_file
from src.core.runtime_status import update_runtime_status
from src.core.types import (
    OrderRequest,
    RiskDecision,
    StrategyCandidate,
)
from src.market.data_feed import DataFeed
from src.market.session_tracker import get_current_session
from src.market.spread_monitor import SpreadMonitor

# Phase 2: Structure Engine
from src.structure.context import ContextBuilder, MultiTimeframeContext

# Phase 3: Strategy Engine
from src.strategies.meta_engine import MetaDecisionEngine
from src.strategies.registry import auto_discover, get_strategy_ids

# Phase 5: AI Scorer
from src.ai.ai_council import AICouncil
from src.ai.candidate_triage import CandidateTriage
from src.ai.trade_learner import TradeLearner
from src.ai.snapshot import build_snapshot
from src.structure.equal_highs_lows import EqualHighsLowsDetector
from src.notification.telegram_alert import TradeAlert, alert_trade_opened, alert_trade_skipped
from src.ai.scorer import RuleBasedScorer
from src.ai.context_analyzer import ContextAnalyzer

# Phase 1: Risk Engine
from src.risk.manager import RiskEngine

# Phase 1: Execution
from src.execution.order_manager import OrderManager
from src.execution.position_tracker import PositionTracker

# Phase 6: Setup Logger
from src.storage.models import get_engine, get_session_factory, Base
from src.storage.additive_schema import ensure_additive_schema
from src.storage.setup_logger import SetupLogger
from src.storage.repository import Repository

logger = get_logger(__name__)


def current_trading_mode() -> str:
    """Read the dashboard-controlled mode, falling back to deployment config."""
    return get_runtime_trading_mode(settings.trading_mode)



def setup_auth_credentials() -> None:
    """Materialize an existing dashboard-managed Codex login for the CLI."""
    try:
        if sync_codex_auth_file():
            logger.info("Codex auth session loaded from dashboard settings")
    except OSError as exc:
        logger.error("Failed to initialize Codex auth session: %s", exc)

class TradingPlatform:
    """
    Main orchestrator — wires all components together.

    Pipeline on each new candle:
        Binance Data → Structure Engine → Strategy Plugins → AI Scorer → Risk Engine → Execute
    """

    def __init__(self, max_cycles: int | None = None, gateway: Any | None = None) -> None:
        self._max_cycles = max_cycles
        self._cycle_count = 0
        self._cycle_errors = 0
        self._venue_name = "binance"
        self._trading_symbol = settings.binance_symbol
        from src.execution.paper_gateway import PaperGateway
        from src.market.binance_gateway import BinanceGateway

        if gateway is not None:
            self._gateway = gateway
            is_paper = isinstance(gateway, PaperGateway)
        else:
            raw_binance = BinanceGateway()
            has_credentials = bool(settings.binance_api_key.strip() and settings.binance_api_secret.strip())
            is_paper = settings.binance_mode == "paper" or not has_credentials
            self._gateway = (
                PaperGateway(raw_binance) if is_paper else raw_binance
            )
            if not has_credentials and settings.binance_mode != "paper":
                logger.warning(
                    "BINANCE_MODE=%s but credentials are empty; defaulting execution to safe PAPER mode.",
                    settings.binance_mode,
                )
        logger.info("Market venue enabled: Binance (%s, execution=%s)", settings.binance_mode, "paper" if is_paper else "exchange")

        self._data_feed = DataFeed(self._gateway)
        self._spread_monitor = SpreadMonitor(self._trading_symbol)
        self._spread_monitors: dict[str, SpreadMonitor] = {self._trading_symbol: self._spread_monitor}

        # Structure
        self._context_builder = ContextBuilder()

        # Strategies
        auto_discover()  # Auto-register all strategy plugins
        self._meta_engine = MetaDecisionEngine()

        # AI
        self._ai_council = AICouncil()
        self._eql_detector = EqualHighsLowsDetector()
        self._ai_scorer = RuleBasedScorer()
        self._context_analyzer = ContextAnalyzer()
        self._candidate_triage = CandidateTriage()

        # BTC Macro Homework
        from src.market.btc_regime import BTCRegimeAnalyzer
        self._btc_analyzer = BTCRegimeAnalyzer()
        self._btc_macro_context: dict[str, Any] = {}

        # Execution
        self._order_manager = OrderManager(self._gateway)
        self._position_tracker = PositionTracker(self._gateway)
        from src.execution.position_manager import PositionManager
        self._position_manager = PositionManager(gateway=self._gateway, order_manager=self._order_manager)

        # Scheduler & Telegram Bot
        self._scheduler: Any | None = None
        self._telegram_bot: Any | None = None

        # AI Vision Confirmation
        from src.ai.vision_analyst import AIVisionAnalyst
        self._vision_analyst = AIVisionAnalyst()

        # Risk (initialized after DB connection)
        self._risk_engine: RiskEngine | None = None
        self._setup_logger: SetupLogger | None = None

        # Database
        self._trade_learner: TradeLearner | None = None
        self._last_evaluated_bar: dict[str, datetime] = {}
        self._db_session = None
        self._session_factory = None

        self._running = False
        self._poll_task = None
        self._poll_tasks: list[asyncio.Task] = []
        self._event_handlers = []

    def _get_spread_monitor(self, symbol: str) -> SpreadMonitor:
        """Get or initialize SpreadMonitor for a given symbol."""
        if symbol not in self._spread_monitors:
            try:
                self._spread_monitors[symbol] = SpreadMonitor(symbol)
            except Exception:
                return self._spread_monitor
        return self._spread_monitors[symbol]

    def _get_active_trading_symbols(self) -> list[str]:
        """Resolve active symbols to monitor: primary symbol + top Watchlist candidates."""
        from pathlib import Path
        import json

        symbols = [self._trading_symbol]
        watchlist_file = (
            Path("/app/data/crypto_watchlist.json")
            if Path("/app/data/crypto_watchlist.json").is_file()
            else Path("data/crypto_watchlist.json")
        )
        if watchlist_file.exists():
            try:
                with open(watchlist_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    candidates = data.get("candidates", [])
                    for cand in candidates:
                        sym = cand.get("symbol")
                        if sym and sym not in symbols and len(symbols) < 5:
                            symbols.append(sym)
            except Exception as exc:
                logger.warning("Failed to load watchlist for active symbols: %s", exc)

        # Fallback to configured Binance symbols if watchlist has only 1
        if len(symbols) == 1:
            try:
                from src.core.runtime_settings import get_runtime_settings
                active_cfg = get_runtime_settings(mask_secrets=False).get("active_symbols", [])
                for s in active_cfg:
                    s_up = str(s).strip().upper()
                    if s_up and s_up not in symbols and len(symbols) < 5:
                        symbols.append(s_up)
            except Exception:
                pass

        if len(symbols) == 1:
            for s in ["ETHUSDT", "SOLUSDT"]:
                if s not in symbols and s in settings.symbols and len(symbols) < 3:
                    symbols.append(s)

        return symbols

    async def start(self) -> None:
        """Always release sessions/tasks, including failures during startup."""
        try:
            await self._start()
        finally:
            await self.stop()

    async def _start(self) -> None:
        """Start the trading platform."""
        setup_auth_credentials()
        trading_mode = current_trading_mode()
        update_runtime_status(
            state="starting", mode=trading_mode.upper(),
            venue=self._venue_name, symbol=self._trading_symbol,
            cycle_count=0, cycle_errors=0,
        )
        logger.info(
            f"Starting Freebuff Trading Platform v{settings.app.version} "
            f"(mode={trading_mode}, venue={self._venue_name})"
        )
        logger.info(f"Strategies loaded: {get_strategy_ids()}")

        # Setup event handlers
        self._setup_event_handlers()

        # Initialize database (risk engine + setup logger)
        engine = get_engine(settings.database_url)
        self._engine = engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_additive_schema(conn)
        self._session_factory = get_session_factory(engine)
        self._db_session = self._session_factory()
        self._risk_engine = RiskEngine(
            self._db_session, spread_monitor=self._spread_monitor
        )
        self._setup_logger = SetupLogger(self._db_session)
        self._trade_learner = TradeLearner(
            repository_factory=self._session_factory,
            gemini_evaluator=self._ai_council.gemini,
            gpt_evaluator=self._ai_council.gpt,
        )
        logger.info(f"Database connected: {settings.database_url}")

        # Connect to the selected venue (retry loop keeps this venue alive).
        logger.info("Connecting to %s...", self._venue_name.upper())
        while True:
            connected = await self._gateway.connect()
            if connected:
                update_runtime_status(
                    state="connected", venue=self._venue_name,
                    binance_connected=True,
                )
                logger.info("✅ %s connected successfully!", self._venue_name.upper())
                break
            logger.warning("⏳ Waiting for Binance API... Retrying in 10s...")
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                return

        sync_retries = 0
        while True:
            try:
                account = await self._gateway.get_account_info()
                break
            except Exception as exc:
                sync_retries += 1
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                is_auth_error = (
                    status_code in (401, 403)
                    or "401" in str(exc)
                    or "credentials" in str(exc).lower()
                    or "unauthorized" in str(exc).lower()
                )
                if is_auth_error and sync_retries >= 2 and not isinstance(self._gateway, PaperGateway):
                    logger.warning(
                        "⚠️ Binance account sync unauthorized (401/403: %s). "
                        "Auto-switching execution to safe PAPER mode so trading engine, candles, and AI scoring operate normally.",
                        exc,
                    )
                    from src.execution.paper_gateway import PaperGateway
                    raw_binance = self._gateway if not isinstance(self._gateway, PaperGateway) else self._gateway._market
                    self._gateway = PaperGateway(raw_binance)
                    self._data_feed = DataFeed(self._gateway)
                    self._order_manager = OrderManager(self._gateway)
                    self._position_tracker = PositionTracker(self._gateway)
                    from src.execution.position_manager import PositionManager
                    self._position_manager = PositionManager(gateway=self._gateway, order_manager=self._order_manager)
                    account = await self._gateway.get_account_info()
                    update_runtime_status(last_error="Binance API 401 Unauthorized: Auto-switched to safe PAPER mode")
                    break

                logger.warning(
                    "Account sync failed for %s: %s. "
                    "Change the runtime mode in the dashboard if this is a credentials check; retrying in 10s...",
                    self._venue_name.upper(), exc,
                )
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    return
        self._trade_learner.account_key = f"{account.server}/{account.login}"
        self._running = True
        update_runtime_status(state="running", mode=current_trading_mode().upper(), last_error=None)

        # Initialize data feeds for active trading symbols
        active_symbols = self._get_active_trading_symbols()
        logger.info(f"Initializing data feeds for active symbols: {active_symbols}")
        for sym in active_symbols:
            await self._data_feed.initialize(sym)
            task = asyncio.create_task(self._data_feed.start_polling(sym))
            self._poll_tasks.append(task)
        if self._poll_tasks:
            self._poll_task = self._poll_tasks[0]

        # Background Scheduler (08:00 Morning Briefing, 20:00 Daily Reflection, 4H BTC Macro)
        from src.live.scheduler import BackgroundScheduler
        self._scheduler = BackgroundScheduler(
            gateway=self._gateway,
            db_session_factory=self._session_factory,
            btc_analyzer=self._btc_analyzer,
        )
        await self._scheduler.start()

        # Interactive Telegram Bot Listener (2-way remote commands)
        from src.notification.telegram_bot import TelegramBotListener
        self._telegram_bot = TelegramBotListener(
            gateway=self._gateway,
            order_manager=self._order_manager,
            screener=self._scheduler.screener if self._scheduler else None,
            platform_stop_callback=self.stop,
        )
        await self._telegram_bot.start()

        # Start main loop
        session = get_current_session()
        logger.info(f"Current session: {session}")

        try:
            await self._main_loop(active_symbols)
        except asyncio.CancelledError:
            logger.info("Platform shutdown requested")
        except Exception as e:
            logger.error(f"Platform error: {e}", exc_info=True)

    async def stop(self) -> None:
        """Stop the trading platform."""
        self._running = False
        status_fields: dict[str, Any] = {"state": "stopped", "venue": self._venue_name}
        status_fields[f"{self._venue_name}_connected"] = False
        update_runtime_status(**status_fields)
        logger.info("Stopping %s platform...", self._venue_name.upper())
        await self._data_feed.stop_polling()
        for task in self._poll_tasks:
            task.cancel()
        if self._poll_tasks:
            await asyncio.gather(*self._poll_tasks, return_exceptions=True)
        self._poll_tasks.clear()
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            await asyncio.gather(self._poll_task, return_exceptions=True)
        for event, handler in self._event_handlers:
            event_bus.unsubscribe(event, handler)
        self._event_handlers.clear()
        if self._trade_learner:
            self._trade_learner.close()
        if getattr(self, "_telegram_bot", None):
            await self._telegram_bot.stop()
        if getattr(self, "_scheduler", None):
            await self._scheduler.stop()
        if self._db_session:
            await self._db_session.close()
        if hasattr(self, "_engine"):
            await self._engine.dispose()
        await self._gateway.disconnect()
        logger.info("%s platform stopped cleanly", self._venue_name.upper())

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
        self._event_handlers = [(EventType.CIRCUIT_BREAKER, on_circuit_breaker),
                                (EventType.ORDER_FILLED, on_order_filled)]

    async def _main_loop(self, symbols: str | list[str] | None = None) -> None:
        """Main evaluation loop: runs on each polling cycle across active symbols."""
        if isinstance(symbols, str):
            target_symbols = [symbols]
        elif isinstance(symbols, list):
            target_symbols = symbols
        else:
            target_symbols = self._get_active_trading_symbols()

        logger.info(f"Main trading loop started for symbols: {target_symbols}")

        while self._running and (self._max_cycles is None or self._cycle_count < self._max_cycles):
            self._cycle_count += 1
            try:
                session = get_current_session()
                update_runtime_status(
                    state="running", cycle_count=self._cycle_count,
                    cycle_errors=self._cycle_errors, venue=self._venue_name,
                    symbol=",".join(target_symbols), mode=current_trading_mode().upper(),
                )

                for symbol in target_symbols:
                    try:
                        tick = await self._gateway.get_current_price(symbol)
                        monitor = self._get_spread_monitor(symbol)
                        spread_pips = monitor.get_spread_pips(tick.bid, tick.ask)

                        candles_by_tf = {
                            "M5": self._data_feed.get_cached_candles("M5", symbol)[:-1],
                            "M15": self._data_feed.get_cached_candles("M15", symbol)[:-1],
                            "H1": self._data_feed.get_cached_candles("H1", symbol)[:-1],
                            "H4": self._data_feed.get_cached_candles("H4", symbol)[:-1],
                        }

                        if not all(candles_by_tf.get(tf) for tf in ("M5", "M15", "H1")):
                            update_runtime_status(last_decision=f"WAITING_FOR_CANDLES_{symbol}")
                            continue

                        ctx = self._context_builder.build(
                            symbol=symbol,
                            candles_by_tf=candles_by_tf,
                            primary_tf="M5",
                            htf="H1",
                        )
                        ctx.current_price = tick.mid
                        ctx.spread = spread_pips

                        if symbol == "BTCUSDT" and candles_by_tf.get("H4"):
                            try:
                                btc_report = self._btc_analyzer.analyze(candles_by_tf["H4"])
                                self._btc_macro_context = btc_report.to_context_dict()
                            except Exception as exc:
                                logger.debug("BTC macro update skipped: %s", exc)

                        # Run strategy pipeline
                        await self._process_strategies(ctx, tick.mid, spread_pips, session)

                        # Sync and manage positions (Break-Even & Partial TP)
                        positions = await self._position_tracker.sync_positions(symbol)
                        if positions:
                            try:
                                await self._position_manager.manage_active_positions(
                                    positions=positions,
                                    current_prices={symbol: tick.mid},
                                    order_manager=self._order_manager,
                                )
                            except Exception as pm_err:
                                logger.warning("Position manager error for %s: %s", symbol, pm_err)

                    except Exception as sym_err:
                        logger.warning("Error evaluating symbol %s: %s", symbol, sym_err)

                if self._trade_learner:
                    await self._trade_learner.reconcile_pending(self._gateway)

                await asyncio.sleep(5)

            except Exception as e:
                self._cycle_errors += 1
                update_runtime_status(
                    state="error", cycle_count=self._cycle_count,
                    cycle_errors=self._cycle_errors, last_error=str(e)[:500],
                )
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
            update_runtime_status(last_decision="NO_CANDIDATE", candidate_count=0)
            return

        update_runtime_status(candidate_count=len(candidates))

        # Run cheap local triage for every candidate. Only the configured
        # number of immediate candidates may continue to the AI Council;
        # observe/batch candidates are still recorded for research.
        max_immediate = get_candidate_policy()["max_immediate_per_bar"]
        immediate_seen = 0
        for candidate in candidates:
            allow_immediate = immediate_seen < max_immediate
            update_runtime_status(
                last_candidate=f"{candidate.strategy_id}:{candidate.direction.value}",
            )
            await self._process_candidate(
                candidate, ctx, current_price, spread, session,
                allow_immediate=allow_immediate,
            )
            if candidate.metadata.get("triage_priority") == "immediate":
                immediate_seen += 1

    async def _process_candidate(
        self,
        candidate: StrategyCandidate,
        ctx: MultiTimeframeContext,
        current_price: float,
        spread: float,
        session: str,
        allow_immediate: bool = True,
    ) -> None:
        """Process a single candidate through AI → Risk → Execute."""

        # Reconcile derived RR before AI/Risk even for third-party strategies.
        sign = 1 if candidate.direction.value == "BUY" else -1
        candidate.rr_ratio = round(reward_risk(
            sign * (candidate.take_profit_1 - candidate.entry_price),
            sign * (candidate.entry_price - candidate.stop_loss),
        ), 2)

        # Deduplicate every candidate before scoring. This prevents a low-score
        # setup from being recorded repeatedly while the same candle is open.
        current_bar_ts = ctx.primary_candle.timestamp if ctx.primary_candle else None
        bar_key = f"{candidate.symbol}_{candidate.strategy_id}"
        if current_bar_ts and self._last_evaluated_bar.get(bar_key) == current_bar_ts:
            logger.debug(f"Candidate {bar_key} already evaluated on bar {current_bar_ts} — skipping repeat")
            return
        if current_bar_ts:
            self._last_evaluated_bar[bar_key] = current_bar_ts

        # Step 2a: Rule-based AI Scoring (fast, no API call)
        ai_decision = self._ai_scorer.score(
            candidate=candidate,
            context=ctx,
            spread=spread,
            session=session,
        )
        triage_priority = self._candidate_triage.observe(
            candidate, ai_decision.combined_score, session
        )

        if ai_decision.decision == "WAIT":
            update_runtime_status(
                last_decision="AI_SKIP",
                last_reason=f"priority={triage_priority} score={ai_decision.combined_score}",
            )
            logger.info(
                f"AI SKIP: {candidate.strategy_id} "
                f"score={ai_decision.combined_score} priority={triage_priority}"
            )
            if self._setup_logger:
                await self._setup_logger.log_skipped(
                    candidate,
                    reason=(
                        f"AI score {ai_decision.combined_score} "
                        f"< {get_candidate_policy()['immediate_min_score']} "
                        f"(triage={triage_priority})"
                    ),
                )
            return

        if not allow_immediate:
            if self._setup_logger:
                await self._setup_logger.log_skipped(
                    candidate,
                    reason="Immediate AI review budget reached for this candle",
                )
            logger.info(
                "AI SKIP: %s score=%s — immediate review budget reached",
                candidate.strategy_id, ai_decision.combined_score,
            )
            return

        # Step 2c: EQH/EQL Detection (ตรวจ Liquidity Pools)
        h1_candles = ctx.candles_by_tf.get("H1", [])
        eql_result = self._eql_detector.detect(h1_candles)
        logger.info(f"EQL: {eql_result.summary}")

        # Step 2d: Retrieve Past Experience / Lessons Learned (Continuous Learning)
        past_lessons = []
        if self._trade_learner:
            past_lessons = await self._trade_learner.get_lessons_for_prompt(
                symbol=candidate.symbol,
                strategy_id=candidate.strategy_id,
                limit=3,
            )

        # Step 2e: Candlestick Visual Confirmation (AI Vision Analyst)
        primary_candles = ctx.candles_by_tf.get("M5", [])
        vision_verdict = self._vision_analyst.analyze_candlestick_setup(
            candles=primary_candles,
            direction=candidate.direction,
            entry_price=float(candidate.entry_price or current_price),
            sl=float(candidate.stop_loss or 0),
            tp=float(candidate.take_profit_1 or 0),
            symbol=candidate.symbol,
            timeframe="M5",
        )
        if vision_verdict.trap_risk and vision_verdict.risks:
            candidate.risk_flags.append(f"Vision Trap Warning: {vision_verdict.risks[0]}")
        if vision_verdict.rejection_wick:
            candidate.confluences.append("Vision Confirmed: Rejection Wick")
        if vision_verdict.displacement:
            candidate.confluences.append("Vision Confirmed: Displacement Body")

        # Step 2f: AI Council Debate (Gemini Bull vs GPT Bear)
        setup_context = {
            "symbol": candidate.symbol,
            "direction": candidate.direction.value,
            "entry_price": float(candidate.entry_price or current_price),
            "stop_loss": float(candidate.stop_loss or 0),
            "take_profit": float(candidate.take_profit_1 or 0),
            "rr_ratio": float(candidate.rr_ratio or 0),
            "rule_score": candidate.rule_score,
            "confluences": candidate.confluences or [],
            "h4_bias": ctx.get_trend("H4").value if ctx.get_trend("H4") else "UNKNOWN",
            "h1_structure": ctx.get_structure("H1").model_dump_json() if ctx.get_structure("H1") else "UNKNOWN",
            "m15_structure": ctx.get_structure("M15").model_dump_json() if ctx.get_structure("M15") else "UNKNOWN",
            "m5_entry": candidate.strategy_id,
            "eql_summary": eql_result.summary,
            "displacement_detected": bool(getattr(candidate, "displacement", False)),
            "vision_confirmation": {
                "verdict": vision_verdict.verdict,
                "score": vision_verdict.vision_score,
                "rejection_wick": vision_verdict.rejection_wick,
                "displacement": vision_verdict.displacement,
                "trap_risk": vision_verdict.trap_risk,
                "summary_th": vision_verdict.summary_th,
                "chart_image": vision_verdict.chart_image_path,
            },
            "past_lessons": past_lessons,
            "btc_macro": self._btc_macro_context,
            "candidate_digest": {
                key: value for key, value in self._candidate_triage.summary().items()
                if key in {"total", "by_priority", "by_strategy", "by_session", "updated_at"}
            },
            "evidence": {
                "strategy_version": candidate.metadata.get("version", "unknown"),
                "has_choch": ctx.has_choch, "has_bos": ctx.has_bos,
                "liquidity_sweep": ctx.has_liquidity_sweep,
                "fvgs": [f.model_dump(mode="json") for f in ctx.fvgs
                         if f.direction == candidate.direction and f.valid][:5],
                "order_blocks": [o.model_dump(mode="json") for o in ctx.order_blocks
                                 if o.direction == candidate.direction and not o.mitigated][:5],
                "closed_m5_bars": [c.model_dump(mode="json") for c in ctx.candles_by_tf.get("M5", [])[-5:]],
            },
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
            update_runtime_status(last_decision="COUNCIL_SKIP", last_reason=council.recommendation)
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
                asyncio.create_task(alert_trade_skipped(
                    symbol=candidate.symbol,
                    reason=council.recommendation,
                    gemini_say=council.gemini_verdict.narrative_th,
                    gpt_say=council.gpt_verdict.narrative_th,
                ))
            return

        # Step 3: Risk Engine Evaluation
        account = await self._gateway.get_account_info()
        positions = await self._position_tracker.sync_positions(candidate.symbol)
        all_open_positions = self._position_tracker.get_all_positions()

        risk_decision = RiskDecision(approved=False)  # Default rejection
        if self._risk_engine:
            risk_decision = await self._risk_engine.evaluate(
                candidate=candidate,
                ai_decision=ai_decision,
                account_balance=account.balance,
                account_equity=account.equity,
                open_positions_count=len(all_open_positions),
                total_exposure=self._position_tracker.get_total_exposure(),
                current_spread=spread,
                session=session,
            )

        # Step 4: Execute or log rejection
        if risk_decision.approved:
            update_runtime_status(last_decision="RISK_APPROVED", last_reason="risk approved")
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
                venue="binance",
                execution_key=f"{candidate.id}:{candidate.strategy_version}:binance",
            )
            candidate.metadata["venue"] = request.venue
            snapshot = build_snapshot(candidate, ctx, spread, session)
            result = await self._order_manager.send_market_order(request)

            if result.success:
                update_runtime_status(last_decision="TRADE_EXECUTED", last_ticket=result.ticket, last_error=None)
                setup_id = None
                if self._trade_learner and result.ticket:
                    snapshot["fill_price"] = result.price
                    snapshot["initial_sl"] = request.sl
                    snapshot["fill_volume"] = result.volume
                    symbol_config = settings.symbols.get(candidate.symbol)
                    initial_risk = (abs(result.price - request.sl) * result.volume * symbol_config.contract_size
                                    if result.price and result.volume and symbol_config else None)
                    await self._trade_learner.record_entry(
                        account_key=f"{account.server}/{account.login}",
                        opening_order=result.ticket, snapshot=snapshot,
                        initial_risk=initial_risk, setup_id=setup_id,
                    )
                if self._setup_logger:
                    setup_id = await self._setup_logger.log_traded(
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
                if self._db_session and result.ticket and result.price and result.volume:
                    from src.core.types import PositionStatus, TradeRecord
                    await Repository(self._db_session).log_trade(
                        TradeRecord(
                            setup_id=setup_id, symbol=candidate.symbol,
                            direction=candidate.direction, volume=result.volume,
                            entry_price=result.price, sl=request.sl, tp1=request.tp,
                            status=PositionStatus.OPEN, magic=request.magic,
                            comment=request.comment, venue=request.venue,
                            external_order_id=result.external_order_id,
                            execution_key=request.execution_key,
                        ),
                        setup_id=setup_id,
                    )
                if self._trade_learner and result.ticket and setup_id:
                    await self._trade_learner.link_setup(
                        f"{account.server}/{account.login}", result.ticket, setup_id)
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
                    rule_score=candidate.rule_score,
                    gemini_score=council.gemini_verdict.confidence,
                    gpt_score=council.gpt_verdict.confidence,
                    gemini_verdict=council.gemini_verdict.verdict,
                    gpt_verdict=council.gpt_verdict.verdict,
                    combined_verdict=council.final_verdict,
                    narrative_th=council.debate_summary_th,
                )))
            else:
                update_runtime_status(last_decision="ORDER_FAILED", last_error=result.error_message)
                logger.error(
                    f"❌ ORDER FAILED: {candidate.strategy_id} — "
                    f"{result.error_message}"
                )
        else:
            reason = risk_decision.rejection_reason or "unknown"
            update_runtime_status(last_decision="RISK_REJECTED", last_reason=reason)
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
    print(f"Mode:           {current_trading_mode()}")
    print("Venue:          Binance USDT-M Futures")
    print(f"Symbol:         {settings.binance_symbol}")
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
    parser.add_argument("--cycles", type=int, default=None, help="Stop after N evaluation cycles")
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
        try:
            asyncio.run(TradingPlatform(max_cycles=args.cycles).start())
        except KeyboardInterrupt:
            logger.info("Interrupted by user")


if __name__ == "__main__":
    main()
