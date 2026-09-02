"""Unit tests for Risk Engine — filters, limits, circuit breaker, full pipeline."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.scorer import RuleBasedScorer
from src.core.types import (
    AIDecision,
    Direction,
    RiskDecision,
    StrategyCandidate,
)
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.filters import TradeFilter
from src.risk.limits import LimitChecker
from src.structure.context import MultiTimeframeContext


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_candidate(
    direction: Direction = Direction.BUY,
    rule_score: int = 75,
    rr_ratio: float = 2.5,
    entry: float = 2350.0,
    sl_distance: float = 10.0,
    confluences: list[str] | None = None,
) -> StrategyCandidate:
    sl = entry - sl_distance if direction == Direction.BUY else entry + sl_distance
    tp = entry + sl_distance * 2.5 if direction == Direction.BUY else entry - sl_distance * 2.5
    return StrategyCandidate(
        strategy_id="test_strategy",
        strategy_name="Test Strategy",
        symbol="XAUUSD",
        timeframe="M15",
        direction=direction,
        rule_score=rule_score,
        entry_price=entry,
        stop_loss=sl,
        take_profit_1=tp,
        rr_ratio=rr_ratio,
        confluences=confluences or [],
    )


def make_ai_decision(
    candidate: StrategyCandidate | None = None,
    combined_score: int = 80,
    decision: str = "BUY",
) -> AIDecision:
    if candidate is None:
        candidate = make_candidate()
    return AIDecision(
        candidate=candidate,
        ai_score=combined_score,
        combined_score=combined_score,
        decision=decision,
        confidence=combined_score / 100.0,
    )


# ─── TradeFilter Tests ───────────────────────────────────────────────────────

class TestTradeFilter:
    """Test individual trade filters."""

    def setup_method(self):
        self.filter = TradeFilter()

    def test_rr_pass_above_minimum(self):
        candidate = make_candidate(rr_ratio=2.5)
        passed, reason = self.filter.check_rr(candidate)
        assert passed is True

    def test_rr_fail_below_minimum(self):
        candidate = make_candidate(rr_ratio=1.5)
        passed, reason = self.filter.check_rr(candidate)
        assert passed is False
        assert "RR too low" in reason

    def test_rr_fail_at_minimum(self):
        candidate = make_candidate(rr_ratio=2.0)
        passed, _ = self.filter.check_rr(candidate)
        # min_rr = 2.0, candidate.rr_ratio = 2.0 → 2.0 < 2.0 is False → passes
        assert passed is True

    def test_session_london_passes(self):
        passed, _ = self.filter.check_session("london")
        assert passed is True

    def test_session_new_york_passes(self):
        passed, _ = self.filter.check_session("new_york")
        assert passed is True

    def test_session_overlap_passes(self):
        passed, _ = self.filter.check_session("overlap")
        assert passed is True

    def test_session_off_fails(self):
        passed, reason = self.filter.check_session("off")
        assert passed is False
        assert "closed" in reason

    def test_session_asian_fails(self):
        passed, reason = self.filter.check_session("asian")
        assert passed is False
        assert "Asian" in reason

    def test_spread_within_limit(self):
        passed, _ = self.filter.check_spread(3.0)
        assert passed is True

    def test_spread_exceeds_limit(self):
        passed, reason = self.filter.check_spread(10.0)
        assert passed is False
        assert "Spread" in reason

    def test_spread_exact_limit(self):
        # max_spread_pips = 5.0, so 5.0 should pass (not > 5.0)
        passed, _ = self.filter.check_spread(5.0)
        assert passed is True

    def test_spread_none_fails(self):
        passed, reason = self.filter.check_spread(None)
        assert passed is False
        assert "unavailable" in reason

    def test_slippage_within_tolerance(self):
        passed, _ = self.filter.check_slippage(2350.0, 2350.2)
        assert passed is True

    def test_slippage_exceeds_tolerance(self):
        passed, _ = self.filter.check_slippage(2350.0, 2351.0)
        assert passed is False

    def test_ai_confidence_above_threshold(self):
        decision = make_ai_decision(combined_score=80)
        passed, _ = self.filter.check_ai_confidence(decision)
        assert passed is True

    def test_ai_confidence_below_threshold(self):
        decision = make_ai_decision(combined_score=50)
        passed, reason = self.filter.check_ai_confidence(decision)
        assert passed is False
        assert "AI score" in reason

    def test_check_all_passes(self):
        candidate = make_candidate(rr_ratio=2.5)
        ai_decision = make_ai_decision(combined_score=80)
        passed, _ = self.filter.check_all(
            candidate, decision=ai_decision, current_spread=3.0, session="london"
        )
        assert passed is True

    def test_check_all_fails_on_rr(self):
        candidate = make_candidate(rr_ratio=1.0)
        ai_decision = make_ai_decision(combined_score=80)
        passed, reason = self.filter.check_all(
            candidate, decision=ai_decision, current_spread=3.0, session="london"
        )
        assert passed is False
        assert "RR" in reason

    def test_check_all_fails_on_session(self):
        candidate = make_candidate(rr_ratio=2.5)
        ai_decision = make_ai_decision(combined_score=80)
        passed, reason = self.filter.check_all(
            candidate, decision=ai_decision, current_spread=3.0, session="asian"
        )
        assert passed is False


# ─── CircuitBreaker Tests ────────────────────────────────────────────────────

class TestCircuitBreaker:
    """Test emergency stop mechanism."""

    def setup_method(self):
        self.cb = CircuitBreaker()

    @pytest.mark.asyncio
    async def test_safe_when_no_drawdown(self):
        result = await self.cb.check(balance=10000, equity=10000)
        assert result is True
        assert self.cb.is_triggered is False

    @pytest.mark.asyncio
    async def test_triggers_on_emergency_drawdown(self):
        # emergency_stop_loss_pct = 0.05 (5%)
        # balance=10000, equity=9400 → dd = 600/10000 = 6% > 5%
        result = await self.cb.check(balance=10000, equity=9400)
        assert result is False
        assert self.cb.is_triggered is True
        assert "drawdown" in self.cb.trigger_reason.lower()

    @pytest.mark.asyncio
    async def test_safe_under_threshold(self):
        # balance=10000, equity=9600 → dd = 400/10000 = 4% < 5%
        result = await self.cb.check(balance=10000, equity=9600)
        assert result is True

    @pytest.mark.asyncio
    async def test_stays_triggered(self):
        """Once triggered, circuit breaker stays triggered."""
        await self.cb.check(balance=10000, equity=9400)
        assert self.cb.is_triggered is True

        # Even with recovered equity, still triggered
        result = await self.cb.check(balance=10000, equity=10500)
        assert result is False

    def test_reset_clears_trigger(self):
        self.cb._triggered = True
        self.cb._trigger_reason = "test"
        self.cb.reset()
        assert self.cb.is_triggered is False
        assert self.cb.trigger_reason == ""

    @pytest.mark.asyncio
    async def test_zero_balance_safe(self):
        """Zero balance should not cause division by zero."""
        result = await self.cb.check(balance=0, equity=0)
        assert result is True


# ─── LimitChecker Tests (with mock session) ─────────────────────────────────

class TestLimitChecker:
    """Test risk limit checks with mocked DB session."""

    def setup_method(self):
        self.mock_session = AsyncMock()
        self.checker = LimitChecker(self.mock_session)

    @pytest.mark.asyncio
    async def test_daily_loss_pass_when_no_record(self):
        """No daily record → passes."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.mock_session.execute.return_value = mock_result

        passed, reason = await self.checker.check_daily_loss(10000)
        assert passed is True

    @pytest.mark.asyncio
    async def test_consecutive_losses_pass_under_limit(self):
        self.checker._consecutive_losses = 2
        passed, _ = self.checker.check_consecutive_losses()
        assert passed is True

    @pytest.mark.asyncio
    async def test_consecutive_losses_fail_at_limit(self):
        self.checker._consecutive_losses = 3
        passed, reason = self.checker.check_consecutive_losses()
        assert passed is False
        assert "Consecutive losses" in reason

    def test_record_win_resets_losses(self):
        self.checker._consecutive_losses = 3
        self.checker.record_win()
        assert self.checker._consecutive_losses == 0

    def test_record_loss_increments(self):
        self.checker.record_loss()
        self.checker.record_loss()
        assert self.checker._consecutive_losses == 2

    def test_exposure_pass_under_limit(self):
        # max_exposure_pct = 0.10, balance=10000 → max = 1000
        passed, _ = self.checker.check_exposure(10000, 500)
        assert passed is True

    def test_exposure_fail_at_limit(self):
        passed, reason = self.checker.check_exposure(10000, 1000)
        assert passed is False
        assert "exposure" in reason.lower()

    def test_spread_pass_within_limit(self):
        passed, _ = self.checker.check_spread(3.0)
        assert passed is True

    def test_spread_fail_exceeds_limit(self):
        passed, reason = self.checker.check_spread(10.0)
        assert passed is False
        assert "Spread" in reason


class TestRiskEnginePipeline:
    """Test the full risk evaluation pipeline with mocked DB."""

    @pytest.mark.asyncio
    async def test_full_approval_flow(self):
        """Everything passes → approved with correct position size."""
        from src.risk.manager import RiskEngine

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        engine = RiskEngine(mock_session)
        candidate = make_candidate(
            direction=Direction.BUY,
            rr_ratio=2.5,
            entry=2350.0,
            sl_distance=10.0,
        )
        ai_decision = make_ai_decision(combined_score=80)

        result = await engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000,
            account_equity=10000,
            open_positions_count=0,
            total_exposure=0,
            current_spread=2.0,
            session="london",
        )

        assert result.approved is True
        assert result.position_size_lots > 0
        assert result.risk_pct == 0.01

    @pytest.mark.asyncio
    async def test_rejection_on_low_rr(self):
        """Low RR → rejected by filter."""
        from src.risk.manager import RiskEngine

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        engine = RiskEngine(mock_session)
        candidate = make_candidate(rr_ratio=1.0)
        ai_decision = make_ai_decision(combined_score=80)

        result = await engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000,
            account_equity=10000,
            current_spread=2.0,
            session="london",
        )

        assert result.approved is False
        assert "RR" in result.rejection_reason

    @pytest.mark.asyncio
    async def test_rejection_on_high_spread(self):
        """Wide spread → rejected."""
        from src.risk.manager import RiskEngine

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        engine = RiskEngine(mock_session)
        candidate = make_candidate(rr_ratio=2.5)
        ai_decision = make_ai_decision(combined_score=80)

        result = await engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000,
            account_equity=10000,
            current_spread=15.0,
            session="london",
        )

        assert result.approved is False
        assert "Spread" in result.rejection_reason

    @pytest.mark.asyncio
    async def test_rejection_on_circuit_breaker(self):
        """Circuit breaker triggered → all trades rejected."""
        from src.risk.manager import RiskEngine

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        engine = RiskEngine(mock_session)
        engine.circuit_breaker._triggered = True
        engine.circuit_breaker._trigger_reason = "test"

        candidate = make_candidate(rr_ratio=2.5)
        ai_decision = make_ai_decision(combined_score=90)

        result = await engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000,
            account_equity=10000,
            current_spread=2.0,
            session="london",
        )

        assert result.approved is False
        assert "Circuit breaker" in result.rejection_reason

    @pytest.mark.asyncio
    async def test_rejection_on_low_ai_score(self):
        """AI score below threshold → rejected."""
        from src.risk.manager import RiskEngine

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        engine = RiskEngine(mock_session)
        candidate = make_candidate(rr_ratio=2.5)
        ai_decision = make_ai_decision(combined_score=50)

        result = await engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000,
            account_equity=10000,
            current_spread=2.0,
            session="london",
        )

        assert result.approved is False
        assert "AI score" in result.rejection_reason

    @pytest.mark.asyncio
    async def test_position_sizing_correct(self):
        """Position size should be risk_amount / (sl_distance * contract_size)."""
        from src.risk.manager import RiskEngine

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        engine = RiskEngine(mock_session)
        candidate = make_candidate(
            direction=Direction.BUY,
            rr_ratio=2.5,
            entry=2350.0,
            sl_distance=10.0,
        )
        ai_decision = make_ai_decision(combined_score=80)

        result = await engine.evaluate(
            candidate=candidate,
            ai_decision=ai_decision,
            account_balance=10000,
            account_equity=10000,
            current_spread=2.0,
            session="london",
        )

        assert result.approved is True
        assert result.position_size_lots == pytest.approx(0.1, abs=0.01)
        assert result.risk_amount == pytest.approx(100.0, abs=0.01)

    def test_on_trade_result_win(self):
        """Winning trade should reset consecutive losses."""
        from src.risk.manager import RiskEngine

        mock_session = AsyncMock()
        engine = RiskEngine(mock_session)
        engine._limits._consecutive_losses = 3

        engine.on_trade_result(50.0)
        assert engine._limits._consecutive_losses == 0

    def test_on_trade_result_loss(self):
        """Losing trade should increment consecutive losses."""
        from src.risk.manager import RiskEngine

        mock_session = AsyncMock()
        engine = RiskEngine(mock_session)

        engine.on_trade_result(-30.0)
        assert engine._limits._consecutive_losses == 1

    def test_on_trade_result_breakeven(self):
        """Breakeven trade (profit=0) counts as win."""
        from src.risk.manager import RiskEngine

        mock_session = AsyncMock()
        engine = RiskEngine(mock_session)
        engine._limits._consecutive_losses = 2

        engine.on_trade_result(0.0)
        assert engine._limits._consecutive_losses == 0
