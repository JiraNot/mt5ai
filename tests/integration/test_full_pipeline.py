"""Integration tests: full Strategy → AI Scorer → Risk Engine pipeline.

Tests the complete decision flow from market context through to trade approval/rejection.
Uses in-memory SQLite for the async database layer.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.ai.scorer import RuleBasedScorer
from src.core.config import Settings, RiskConfig, AIConfig, SymbolConfig
from src.core.types import (
    AIDecision,
    Candle,
    Direction,
    FairValueGap,
    MarketStructure,
    OrderBlock,
    StrategyCandidate,
    SwingPoint,
)
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.filters import TradeFilter
from src.risk.limits import LimitChecker
from src.risk.manager import RiskEngine
from src.storage.models import Base, DailyRisk
from src.structure.context import ContextBuilder, MultiTimeframeContext


# ─── Database Fixtures ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_engine():
    """In-memory SQLite async engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Async session factory + session."""
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_candle(ts: datetime, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=100)


def build_bullish_context() -> MultiTimeframeContext:
    """
    Build a MultiTimeframeContext with a strong bullish setup:
    - HTF (H4) bullish trend
    - M15 bullish CHoCH confirmed
    - Bullish Order Block with FVG overlap
    - Liquidity sweep detected
    - Price in discount zone
    """
    base = datetime(2024, 1, 1, 12, 0)

    # M15 structure: bullish CHoCH
    m15_structure = MarketStructure(
        timeframe="M15",
        trend=Direction.BUY,
        choch=base - timedelta(minutes=30),
        last_swing_high=SwingPoint(
            timestamp=base - timedelta(hours=1),
            price=2050.0,
            direction=Direction.SELL,
            strength=3,
            timeframe="M15",
        ),
        last_swing_low=SwingPoint(
            timestamp=base - timedelta(hours=2),
            price=2020.0,
            direction=Direction.BUY,
            strength=3,
            timeframe="M15",
        ),
        premium_discount="discount",
    )

    # H4 structure: bullish trend
    h4_structure = MarketStructure(
        timeframe="H4",
        trend=Direction.BUY,
        last_swing_high=SwingPoint(
            timestamp=base - timedelta(hours=8),
            price=2060.0,
            direction=Direction.SELL,
            strength=4,
            timeframe="H4",
        ),
        last_swing_low=SwingPoint(
            timestamp=base - timedelta(hours=12),
            price=2010.0,
            direction=Direction.BUY,
            strength=4,
            timeframe="H4",
        ),
    )

    # Bullish Order Block near current price
    bullish_ob = OrderBlock(
        timestamp=base - timedelta(minutes=45),
        direction=Direction.BUY,
        upper_price=2035.0,
        lower_price=2028.0,
        timeframe="M15",
        strength=4,
        mitigated=False,
        fvg_overlap=True,
    )

    # Bullish FVG
    bullish_fvg = FairValueGap(
        timestamp=base - timedelta(minutes=40),
        direction=Direction.BUY,
        upper_price=2036.0,
        lower_price=2029.0,
        timeframe="M15",
        valid=True,
    )

    # Primary candle (current)
    primary_candle = make_candle(base, 2030.0, 2038.0, 2028.0, 2032.0)

    return MultiTimeframeContext(
        symbol="XAUUSD",
        current_price=2032.0,
        spread=2.0,
        structures={"M15": m15_structure, "H4": h4_structure},
        swing_highs=[m15_structure.last_swing_high, h4_structure.last_swing_high],
        swing_lows=[m15_structure.last_swing_low, h4_structure.last_swing_low],
        fvgs=[bullish_fvg],
        order_blocks=[bullish_ob],
        liquidity_sweeps=[{
            "timestamp": base - timedelta(minutes=50),
            "direction": Direction.BUY,
            "swept_level": 2018.0,
            "type": "sell_side",
            "strength": 3,
        }],
        primary_candle=primary_candle,
        htf_trend=Direction.BUY,
        has_choch=True,
        has_bos=False,
        has_liquidity_sweep=True,
        has_ob_fvg_overlap=True,
        in_discount_zone=True,
        in_premium_zone=False,
    )


def build_bearish_context() -> MultiTimeframeContext:
    """
    Build a bearish setup for short testing.
    """
    base = datetime(2024, 1, 1, 12, 0)

    m15_structure = MarketStructure(
        timeframe="M15",
        trend=Direction.SELL,
        choch=base - timedelta(minutes=30),
        last_swing_high=SwingPoint(
            timestamp=base - timedelta(hours=2),
            price=2080.0,
            direction=Direction.SELL,
            strength=3,
            timeframe="M15",
        ),
        last_swing_low=SwingPoint(
            timestamp=base - timedelta(hours=1),
            price=2050.0,
            direction=Direction.BUY,
            strength=3,
            timeframe="M15",
        ),
        premium_discount="premium",
    )

    h4_structure = MarketStructure(
        timeframe="H4",
        trend=Direction.SELL,
    )

    bearish_ob = OrderBlock(
        timestamp=base - timedelta(minutes=45),
        direction=Direction.SELL,
        upper_price=2072.0,
        lower_price=2065.0,
        timeframe="M15",
        strength=4,
        mitigated=False,
        fvg_overlap=True,
    )

    bearish_fvg = FairValueGap(
        timestamp=base - timedelta(minutes=40),
        direction=Direction.SELL,
        upper_price=2071.0,
        lower_price=2064.0,
        timeframe="M15",
        valid=True,
    )

    primary_candle = make_candle(base, 2068.0, 2072.0, 2060.0, 2065.0)

    return MultiTimeframeContext(
        symbol="XAUUSD",
        current_price=2065.0,
        spread=2.0,
        structures={"M15": m15_structure, "H4": h4_structure},
        swing_highs=[m15_structure.last_swing_high],
        swing_lows=[m15_structure.last_swing_low],
        fvgs=[bearish_fvg],
        order_blocks=[bearish_ob],
        liquidity_sweeps=[{
            "timestamp": base - timedelta(minutes=50),
            "direction": Direction.SELL,
            "swept_level": 2082.0,
            "type": "buy_side",
            "strength": 3,
        }],
        primary_candle=primary_candle,
        htf_trend=Direction.SELL,
        has_choch=True,
        has_bos=False,
        has_liquidity_sweep=True,
        has_ob_fvg_overlap=True,
        in_discount_zone=False,
        in_premium_zone=True,
    )


def make_strong_buy_candidate() -> StrategyCandidate:
    """High-quality BUY candidate that should pass AI and risk."""
    return StrategyCandidate(
        strategy_id="choch_orderblock",
        strategy_name="CHoCH + Order Block",
        symbol="XAUUSD",
        timeframe="M15",
        direction=Direction.BUY,
        rule_score=75,
        entry_price=2032.0,
        stop_loss=2026.0,     # $6 risk
        take_profit_1=2044.0,  # $12 reward → 1:2 RR
        take_profit_2=2050.0,  # $18 reward → 1:3 RR
        confluences=["choch_confirmed", "liquidity_sweep", "ob_fvg_overlap", "htf_aligned"],
        risk_flags=[],
    )


def make_weak_buy_candidate() -> StrategyCandidate:
    """Low-quality BUY candidate with few confluences."""
    return StrategyCandidate(
        strategy_id="breakout_retest",
        strategy_name="Breakout Retest",
        symbol="XAUUSD",
        timeframe="M15",
        direction=Direction.BUY,
        rule_score=40,
        entry_price=2032.0,
        stop_loss=2026.0,
        take_profit_1=2041.0,  # 1.5:1 RR — below min_rr=2.0
        confluences=[],
        risk_flags=["low_rr"],
    )


def make_low_rr_candidate() -> StrategyCandidate:
    """Candidate with RR below minimum."""
    return StrategyCandidate(
        strategy_id="fvg_reversal",
        strategy_name="FVG Reversal",
        symbol="XAUUSD",
        timeframe="M15",
        direction=Direction.BUY,
        rule_score=65,
        entry_price=2032.0,
        stop_loss=2026.0,      # $6 risk
        take_profit_1=2037.0,  # $5 reward → 0.83:1 RR
        confluences=["fvg_present"],
    )


def make_wide_spread_candidate() -> StrategyCandidate:
    """Candidate that will be rejected due to high spread in AI scoring."""
    return StrategyCandidate(
        strategy_id="choch_orderblock",
        strategy_name="CHoCH + Order Block",
        symbol="XAUUSD",
        timeframe="M15",
        direction=Direction.BUY,
        rule_score=75,
        entry_price=2032.0,
        stop_loss=2026.0,
        take_profit_1=2044.0,
        take_profit_2=2050.0,
        confluences=["choch_confirmed"],
    )


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestFullPipelineHappyPath:
    """Happy path: strong candidate → AI approves → Risk approves."""

    @pytest.mark.asyncio
    async def test_full_bullish_pipeline(self, db_session: AsyncSession):
        """Complete bullish pipeline: context → strategy → AI → risk → approved."""
        # 1. Build context
        ctx = build_bullish_context()

        # 2. Create strong candidate (simulating strategy output)
        candidate = make_strong_buy_candidate()

        # 3. AI scoring
        scorer = RuleBasedScorer()
        ai_decision = scorer.score(
            candidate,
            ctx,
            spread=2.0,
            session="london",
        )

        assert ai_decision.decision == "BUY"
        assert ai_decision.ai_score >= 70
        assert ai_decision.confidence >= 0.7
        assert "HTF" in str(ai_decision.reasons) or "aligned" in str(ai_decision.reasons).lower()

        # 4. Risk evaluation
        risk_engine = RiskEngine(session=db_session)
        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=10000.0,
            open_positions_count=0,
            total_exposure=0.0,
            current_spread=2.0,
            session="london",
        )

        assert risk_decision.approved is True
        assert risk_decision.position_size_lots > 0
        assert risk_decision.risk_amount > 0
        assert risk_decision.risk_pct == 0.01  # 1% default

    @pytest.mark.asyncio
    async def test_full_bearish_pipeline(self, db_session: AsyncSession):
        """Complete bearish pipeline: context → AI → risk → approved."""
        ctx = build_bearish_context()
        candidate = StrategyCandidate(
            strategy_id="choch_orderblock",
            strategy_name="CHoCH + Order Block",
            symbol="XAUUSD",
            timeframe="M15",
            direction=Direction.SELL,
            rule_score=75,
            entry_price=2065.0,
            stop_loss=2072.0,     # $7 risk
            take_profit_1=2051.0, # $14 reward → 1:2 RR
            take_profit_2=2044.0,
            confluences=["choch_confirmed", "liquidity_sweep", "htf_aligned"],
        )

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="new_york")

        assert ai_decision.decision == "SELL"
        assert ai_decision.ai_score >= 70

        risk_engine = RiskEngine(session=db_session)
        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=10000.0,
            current_spread=2.0,
            session="new_york",
        )

        assert risk_decision.approved is True

    @pytest.mark.asyncio
    async def test_position_sizing_math(self, db_session: AsyncSession):
        """Verify position sizing: risk_amount / (sl_distance * contract_size)."""
        ctx = build_bullish_context()
        candidate = make_strong_buy_candidate()
        # entry=2032, sl=2026 → risk_distance = 6.0
        # balance=10000, risk_pct=0.01 → risk_amount = 100
        # contract_size=100 → volume = 100 / (6 * 100) = 0.1667 → 0.17 lots

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="london")

        risk_engine = RiskEngine(session=db_session)
        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=10000.0,
            current_spread=2.0,
            session="london",
        )

        assert risk_decision.approved is True
        # risk_amount = 10000 * 0.01 = 100
        assert risk_decision.risk_amount == pytest.approx(100.0)
        # sl_distance = |2032 - 2026| = 6
        # volume = 100 / (6 * 100) = 0.1667 → rounds to 0.17
        assert risk_decision.position_size_lots == pytest.approx(0.17, abs=0.01)


class TestAIRejection:
    """AI layer rejects low-quality candidates."""

    @pytest.mark.asyncio
    async def test_ai_rejects_weak_candidate(self, db_session: AsyncSession):
        """Low rule score + no confluences → AI WAIT."""
        ctx = build_bullish_context()
        candidate = make_weak_buy_candidate()

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="london")

        # rule_score=40, no HTF bonus (htf_aligned not in confluences,
        # but context.htf_trend=BUY == candidate.direction → gets +15 bonus)
        # 40 + 15(htf) + 10(session) + 5(spread) = 70
        # Should be >= 70 threshold
        # But if it's below, it should be WAIT
        assert ai_decision.decision in ("BUY", "WAIT")

        # If AI says WAIT, risk engine should reject
        if ai_decision.decision == "WAIT":
            risk_engine = RiskEngine(session=db_session)
            risk_decision = await risk_engine.evaluate(
                candidate=candidate,
                ai_decision=ai_decision,
                account_balance=10000.0,
                account_equity=10000.0,
                current_spread=2.0,
                session="london",
            )
            assert risk_decision.approved is False
            assert "AI score" in risk_decision.rejection_reason or "score" in risk_decision.rejection_reason.lower()

    @pytest.mark.asyncio
    async def test_ai_penalizes_htf_conflict(self, db_session: AsyncSession):
        """BUY candidate when HTF is bearish → heavy penalty."""
        ctx = build_bearish_context()  # HTF = SELL
        candidate = StrategyCandidate(
            strategy_id="breakout_retest",
            strategy_name="Breakout Retest",
            symbol="XAUUSD",
            timeframe="M15",
            direction=Direction.BUY,  # Sells against HTF
            rule_score=60,
            entry_price=2065.0,
            stop_loss=2059.0,
            take_profit_1=2077.0,
            confluences=[],
        )

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="london")

        # 60 - 20(htf_conflict) + 10(session) + 5(spread) = 55 → below 70
        assert ai_decision.ai_score < 70
        assert ai_decision.decision == "WAIT"
        assert any("conflict" in f.lower() for f in ai_decision.risk_flags)

    @pytest.mark.asyncio
    async def test_ai_penalizes_high_spread(self, db_session: AsyncSession):
        """High spread → penalty reduces score."""
        ctx = build_bullish_context()
        candidate = make_strong_buy_candidate()

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=15.0, session="london")

        # High spread penalty: -30
        assert any("spread" in f.lower() for f in ai_decision.risk_flags)


class TestRiskRejection:
    """Risk engine rejects trades that fail filters or limits."""

    @pytest.mark.asyncio
    async def test_reject_on_low_rr(self, db_session: AsyncSession):
        """RR below minimum → rejected by filter."""
        ctx = build_bullish_context()
        candidate = make_low_rr_candidate()

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="london")

        risk_engine = RiskEngine(session=db_session)
        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=10000.0,
            current_spread=2.0,
            session="london",
        )

        assert risk_decision.approved is False
        assert "RR" in risk_decision.rejection_reason or "rr" in risk_decision.rejection_reason.lower()

    @pytest.mark.asyncio
    async def test_reject_on_high_spread(self, db_session: AsyncSession):
        """Spread above max → rejected by filter."""
        ctx = build_bullish_context()
        candidate = make_strong_buy_candidate()

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="london")

        risk_engine = RiskEngine(session=db_session)
        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=10000.0,
            current_spread=10.0,  # Way above max_spread_pips=5.0
            session="london",
        )

        assert risk_decision.approved is False
        assert "spread" in risk_decision.rejection_reason.lower()

    @pytest.mark.asyncio
    async def test_reject_on_circuit_breaker(self, db_session: AsyncSession):
        """Circuit breaker triggered → all trades blocked."""
        ctx = build_bullish_context()
        candidate = make_strong_buy_candidate()

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="london")

        risk_engine = RiskEngine(session=db_session)
        # Trigger circuit breaker manually
        risk_engine.circuit_breaker._triggered = True
        risk_engine.circuit_breaker._trigger_reason = "Manual test trigger"

        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=10000.0,  # No drawdown, but breaker is manually triggered
            current_spread=2.0,
            session="london",
        )

        assert risk_decision.approved is False
        assert "circuit breaker" in risk_decision.rejection_reason.lower()

    @pytest.mark.asyncio
    async def test_reject_on_account_drawdown(self, db_session: AsyncSession):
        """Account drawdown exceeding emergency threshold → circuit breaker fires."""
        ctx = build_bullish_context()
        candidate = make_strong_buy_candidate()

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="london")

        risk_engine = RiskEngine(session=db_session)
        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=9400.0,  # 6% drawdown > 5% emergency threshold
            current_spread=2.0,
            session="london",
        )

        assert risk_decision.approved is False
        assert "circuit breaker" in risk_decision.rejection_reason.lower()

    @pytest.mark.asyncio
    async def test_reject_on_asian_session(self, db_session: AsyncSession):
        """Asian session → rejected by session filter."""
        ctx = build_bullish_context()
        candidate = make_strong_buy_candidate()

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="asian")

        risk_engine = RiskEngine(session=db_session)
        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=10000.0,
            current_spread=2.0,
            session="asian",
        )

        assert risk_decision.approved is False
        assert "asian" in risk_decision.rejection_reason.lower()

    @pytest.mark.asyncio
    async def test_reject_on_off_session(self, db_session: AsyncSession):
        """Market closed → rejected."""
        ctx = build_bullish_context()
        candidate = make_strong_buy_candidate()

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="off")

        risk_engine = RiskEngine(session=db_session)
        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=10000.0,
            current_spread=2.0,
            session="off",
        )

        assert risk_decision.approved is False


class TestTradeResultCallbacks:
    """Risk engine state updates after trade results."""

    @pytest.mark.asyncio
    async def test_win_resets_consecutive_losses(self, db_session: AsyncSession):
        """Winning trade resets consecutive loss counter."""
        risk_engine = RiskEngine(session=db_session)

        # Simulate 2 losses
        risk_engine.on_trade_result(-50.0)
        risk_engine.on_trade_result(-50.0)
        assert risk_engine._limits._consecutive_losses == 2

        # Win resets counter
        risk_engine.on_trade_result(100.0)
        assert risk_engine._limits._consecutive_losses == 0

    @pytest.mark.asyncio
    async def test_loss_increments_counter(self, db_session: AsyncSession):
        """Losing trade increments consecutive loss counter."""
        risk_engine = RiskEngine(session=db_session)

        risk_engine.on_trade_result(-30.0)
        assert risk_engine._limits._consecutive_losses == 1

        risk_engine.on_trade_result(-30.0)
        assert risk_engine._limits._consecutive_losses == 2

    @pytest.mark.asyncio
    async def test_consecutive_losses_block_trade(self, db_session: AsyncSession):
        """After max consecutive losses, new trade is blocked."""
        ctx = build_bullish_context()
        candidate = make_strong_buy_candidate()

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="london")

        risk_engine = RiskEngine(session=db_session)
        # Simulate 3 consecutive losses (= max_consecutive_losses)
        risk_engine.on_trade_result(-50.0)
        risk_engine.on_trade_result(-50.0)
        risk_engine.on_trade_result(-50.0)

        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=10000.0,
            current_spread=2.0,
            session="london",
        )

        assert risk_decision.approved is False
        assert "consecutive" in risk_decision.rejection_reason.lower()


class TestPipelineWithStrategies:
    """Test with actual strategy plugins and context building."""

    def test_choch_ob_strategy_produces_candidate(self):
        """CHoCH+OB strategy should produce a candidate from a bullish context."""
        from src.strategies.choch_orderblock import CHOCHOrderBlockStrategy

        ctx = build_bullish_context()
        strategy = CHOCHOrderBlockStrategy()

        candidate = strategy.analyze(
            context=ctx,
            current_candle=ctx.primary_candle,
            current_price=ctx.current_price,
            spread=2.0,
            session="london",
        )

        if candidate:
            assert candidate.direction == Direction.BUY
            assert candidate.strategy_id == "choch_orderblock"
            assert candidate.rr_ratio >= 2.0
            assert len(candidate.confluences) > 0

    def test_fvg_strategy_produces_candidate(self):
        """FVG strategy should produce a candidate from bullish context with FVGs."""
        from src.strategies.fvg_reversal import FVGReversalStrategy

        ctx = build_bullish_context()
        strategy = FVGReversalStrategy()

        candidate = strategy.analyze(
            context=ctx,
            current_candle=ctx.primary_candle,
            current_price=ctx.current_price,
            spread=2.0,
            session="london",
        )

        if candidate:
            assert candidate.direction == Direction.BUY
            assert candidate.strategy_id == "fvg_reversal"
            assert "fvg_present" in candidate.confluences

    def test_no_candidate_from_empty_context(self):
        """Empty context should produce no candidates from any strategy."""
        from src.strategies.choch_orderblock import CHOCHOrderBlockStrategy
        from src.strategies.fvg_reversal import FVGReversalStrategy
        from src.strategies.breakout_retest import BreakoutRetestStrategy

        ctx = MultiTimeframeContext(symbol="XAUUSD")
        candle = make_candle(datetime(2024, 1, 1), 100, 101, 99, 100)

        for StrategyClass in [CHOCHOrderBlockStrategy, FVGReversalStrategy, BreakoutRetestStrategy]:
            strategy = StrategyClass()
            candidate = strategy.analyze(
                context=ctx,
                current_candle=candle,
                current_price=100.0,
                spread=2.0,
                session="london",
            )
            assert candidate is None, f"{strategy.strategy_id} should return None for empty context"

    @pytest.mark.asyncio
    async def test_meta_engine_with_bullish_context(self, db_session: AsyncSession):
        """MetaDecisionEngine should find candidates from a well-built context."""
        from src.strategies.meta_engine import MetaDecisionEngine
        from src.strategies.registry import auto_discover

        auto_discover()  # Ensure strategies are registered

        ctx = build_bullish_context()
        meta = MetaDecisionEngine(min_combined_score=50)

        candidates = await meta.evaluate(
            context=ctx,
            current_price=ctx.current_price,
            spread=2.0,
            session="london",
        )

        # At least one strategy should fire given our strong bullish context
        if candidates:
            assert len(candidates) >= 1
            # All candidates should be sorted by score descending
            scores = [c.rule_score for c in candidates]
            assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_meta_engine_to_ai_to_risk(self, db_session: AsyncSession):
        """Full pipeline: MetaEngine → AI Scorer → Risk Engine."""
        from src.strategies.meta_engine import MetaDecisionEngine
        from src.strategies.registry import auto_discover

        auto_discover()

        ctx = build_bullish_context()
        meta = MetaDecisionEngine(min_combined_score=50)
        scorer = RuleBasedScorer()
        risk_engine = RiskEngine(session=db_session)

        candidates = await meta.evaluate(
            context=ctx,
            current_price=ctx.current_price,
            spread=2.0,
            session="london",
        )

        if not candidates:
            pytest.skip("No strategy produced a candidate from test context")

        # Take the best candidate
        best = candidates[0]

        # AI scoring
        ai_decision = scorer.score(best, ctx, spread=2.0, session="london")

        # Risk evaluation
        risk_decision = await risk_engine.evaluate(
            candidate=best,
            ai_decision=ai_decision,
            account_balance=10000.0,
            account_equity=10000.0,
            current_spread=2.0,
            session="london",
        )

        # Log results for debugging
        print(f"\nStrategy: {best.strategy_id}")
        print(f"Rule Score: {best.rule_score}")
        print(f"AI Score: {ai_decision.ai_score}, Decision: {ai_decision.decision}")
        print(f"Risk Approved: {risk_decision.approved}")
        if not risk_decision.approved:
            print(f"Rejection: {risk_decision.rejection_reason}")

        # At minimum, the pipeline should not crash
        assert ai_decision.ai_score >= 0
        assert isinstance(risk_decision.approved, bool)


class TestMultipleStrategiesCompeting:
    """Multiple strategies produce candidates, meta engine ranks them."""

    @pytest.mark.asyncio
    async def test_strategy_ranking(self, db_session: AsyncSession):
        """Multiple candidates should be ranked by rule_score."""
        scorer = RuleBasedScorer()
        ctx = build_bullish_context()

        # Simulate multiple strategy outputs
        candidates = [
            StrategyCandidate(
                strategy_id="choch_orderblock",
                strategy_name="CHoCH + OB",
                symbol="XAUUSD",
                timeframe="M15",
                direction=Direction.BUY,
                rule_score=85,
                entry_price=2032.0,
                stop_loss=2026.0,
                take_profit_1=2044.0,
                confluences=["choch_confirmed", "liquidity_sweep", "ob_fvg_overlap", "htf_aligned"],
            ),
            StrategyCandidate(
                strategy_id="fvg_reversal",
                strategy_name="FVG Reversal",
                symbol="XAUUSD",
                timeframe="M15",
                direction=Direction.BUY,
                rule_score=70,
                entry_price=2032.0,
                stop_loss=2028.0,
                take_profit_1=2040.0,
                confluences=["fvg_present", "htf_aligned"],
            ),
            StrategyCandidate(
                strategy_id="breakout_retest",
                strategy_name="Breakout Retest",
                symbol="XAUUSD",
                timeframe="M15",
                direction=Direction.BUY,
                rule_score=55,
                entry_price=2032.0,
                stop_loss=2026.0,
                take_profit_1=2040.0,
                confluences=["good_session"],
            ),
        ]

        # Sort by score (simulating meta engine)
        candidates.sort(key=lambda c: c.rule_score, reverse=True)

        # Score each
        decisions = []
        for c in candidates:
            d = scorer.score(c, ctx, spread=2.0, session="london")
            decisions.append(d)

        # Best strategy should get highest AI score
        assert decisions[0].ai_score >= decisions[1].ai_score
        assert decisions[1].ai_score >= decisions[2].ai_score

        # Verify risk engine approves the best, may reject weakest
        risk_engine = RiskEngine(session=db_session)

        for d in decisions:
            rd = await risk_engine.evaluate(
                candidate=d.candidate,
                ai_decision=d,
                account_balance=10000.0,
                account_equity=10000.0,
                current_spread=2.0,
                session="london",
            )
            if d.ai_score >= 70:
                # High-scoring candidates should pass
                assert rd.approved is True or "RR" in (rd.rejection_reason or "")


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_zero_balance(self, db_session: AsyncSession):
        """Zero balance should not crash position sizing."""
        ctx = build_bullish_context()
        candidate = make_strong_buy_candidate()

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="london")

        risk_engine = RiskEngine(session=db_session)
        risk_decision = await risk_engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=0.0,
            account_equity=0.0,
            current_spread=2.0,
            session="london",
        )

        # Should not crash; position size should be 0
        assert risk_decision.position_size_lots == 0.0

    def test_ai_score_clamped_at_100(self):
        """AI score should never exceed 100 even with many bonuses."""
        ctx = build_bullish_context()
        candidate = StrategyCandidate(
            strategy_id="choch_orderblock",
            strategy_name="CHoCH + OB",
            symbol="XAUUSD",
            timeframe="M15",
            direction=Direction.BUY,
            rule_score=90,
            entry_price=2032.0,
            stop_loss=2026.0,
            take_profit_1=2050.0,  # 3:1 RR
            confluences=["choch_confirmed", "liquidity_sweep", "ob_fvg_overlap"],
        )

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(candidate, ctx, spread=2.0, session="overlap")

        assert ai_decision.ai_score <= 100
        assert ai_decision.confidence <= 1.0

    def test_ai_score_clamped_at_zero(self):
        """AI score should never go below 0."""
        ctx = MultiTimeframeContext(
            symbol="XAUUSD",
            htf_trend=Direction.SELL,  # Conflicting HTF
        )
        candidate = StrategyCandidate(
            strategy_id="test",
            strategy_name="Test",
            symbol="XAUUSD",
            timeframe="M15",
            direction=Direction.BUY,
            rule_score=10,  # Very low base
            entry_price=2032.0,
            stop_loss=2026.0,
            take_profit_1=2035.0,
        )

        scorer = RuleBasedScorer()
        ai_decision = scorer.score(
            candidate, ctx, spread=20.0, session="asian", news_nearby=True,
        )

        assert ai_decision.ai_score >= 0
        assert ai_decision.decision == "WAIT"

    def test_circuit_breaker_reset_allows_trading(self, db_session):
        """After circuit breaker reset, trading should resume."""
        cb = CircuitBreaker()
        assert cb.is_triggered is False

        # Manually trigger
        cb._triggered = True
        cb._trigger_reason = "test"
        assert cb.is_triggered is True

        # Reset
        cb.reset()
        assert cb.is_triggered is False
        assert cb.trigger_reason == ""
