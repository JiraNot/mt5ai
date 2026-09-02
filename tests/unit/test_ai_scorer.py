"""Unit tests for RuleBasedScorer — validates AI scoring logic."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.ai.scorer import RuleBasedScorer
from src.core.types import Direction, StrategyCandidate
from src.structure.context import MultiTimeframeContext


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_candidate(
    direction: Direction = Direction.BUY,
    rule_score: int = 60,
    rr_ratio: float = 2.5,
    confluences: list[str] | None = None,
    risk_flags: list[str] | None = None,
) -> StrategyCandidate:
    """Create a test candidate with configurable properties."""
    entry = 2350.0 if direction == Direction.BUY else 2350.0
    sl = entry - 10 if direction == Direction.BUY else entry + 10
    tp = entry + 25 if direction == Direction.BUY else entry - 25

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
        risk_flags=risk_flags or [],
    )


def make_context(
    htf_trend: Direction | None = None,
) -> MultiTimeframeContext:
    """Create a test MultiTimeframeContext."""
    return MultiTimeframeContext(
        symbol="XAUUSD",
        current_price=2350.0,
        htf_trend=htf_trend,
    )


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestRuleBasedScorer:
    """Test the AI scoring engine."""

    def setup_method(self):
        self.scorer = RuleBasedScorer()

    def test_base_score_preserved(self):
        """Strategy's rule_score should be the starting point."""
        candidate = make_candidate(rule_score=60)
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx)
        # Score starts at 60, no bonuses/penalties applied
        assert decision.ai_score >= 60

    def test_htf_aligned_bonus(self):
        """HTF aligned with trade direction should add +15."""
        candidate = make_candidate(direction=Direction.BUY, rule_score=50)
        ctx = make_context(htf_trend=Direction.BUY)
        decision = self.scorer.score(candidate, ctx, session="london")

        assert decision.ai_score >= 50 + 15  # htf_aligned bonus
        assert any("HTF" in r and "aligned" in r for r in decision.reasons)

    def test_htf_conflict_penalty(self):
        """HTF conflicting with trade direction should subtract -20."""
        candidate = make_candidate(direction=Direction.BUY, rule_score=80)
        ctx = make_context(htf_trend=Direction.SELL)
        decision = self.scorer.score(candidate, ctx, spread=5.0)
        # 80 - 20(htf_conflict) + 0(spread=5.0 is not > 8.0, not <= 2.5) = 60
        assert decision.ai_score <= 60
        assert any("conflicts" in f for f in decision.risk_flags)

    def test_london_session_bonus(self):
        """London session should add +10."""
        candidate = make_candidate(rule_score=55)
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx, session="london")
        assert decision.ai_score >= 55 + 10

    def test_new_york_session_bonus(self):
        """New York session should add +10."""
        candidate = make_candidate(rule_score=55)
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx, session="new_york")
        assert decision.ai_score >= 55 + 10

    def test_overlap_session_bonus(self):
        """Overlap session should add +10."""
        candidate = make_candidate(rule_score=55)
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx, session="overlap")
        assert decision.ai_score >= 55 + 10

    def test_asian_session_penalty(self):
        """Asian session should subtract -5."""
        candidate = make_candidate(rule_score=55)
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx, session="asian", spread=5.0)
        # 55 - 5(asian) + 0(spread=5.0 is between normal and max) = 50
        assert decision.ai_score <= 50

    def test_normal_spread_bonus(self):
        """Normal spread should add +5."""
        candidate = make_candidate(rule_score=55)
        ctx = make_context()
        # XAUUSD normal_spread = 2.5, so spread=2.0 is normal
        decision = self.scorer.score(candidate, ctx, spread=2.0, session="london")
        assert decision.ai_score >= 55 + 5

    def test_high_spread_penalty(self):
        """Abnormal spread should subtract -30."""
        candidate = make_candidate(rule_score=80)
        ctx = make_context()
        # XAUUSD max_spread = 8.0, so spread=10.0 is high
        decision = self.scorer.score(candidate, ctx, spread=10.0)
        assert decision.ai_score <= 80 - 30
        assert any("abnormal" in f for f in decision.risk_flags)

    def test_excellent_rr_bonus(self):
        """RR >= 3.0 should add +10."""
        candidate = make_candidate(rule_score=55, rr_ratio=3.5)
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx)
        assert decision.ai_score >= 55 + 10
        assert any("Excellent" in r for r in decision.reasons)

    def test_low_rr_flagged(self):
        """RR < 2.0 should add a risk flag."""
        candidate = make_candidate(rule_score=55, rr_ratio=1.5)
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx)
        assert any("Low RR" in f for f in decision.risk_flags)

    def test_liquidity_sweep_bonus(self):
        """Liquidity sweep confluence should add +15."""
        candidate = make_candidate(rule_score=50, confluences=["liquidity_sweep"])
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx)
        assert decision.ai_score >= 50 + 15

    def test_fvg_confluence_bonus(self):
        """FVG present should add +15."""
        candidate = make_candidate(rule_score=50, confluences=["fvg_present"])
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx)
        assert decision.ai_score >= 50 + 15

    def test_ob_fvg_overlap_bonus(self):
        """OB/FVG overlap should add +20."""
        candidate = make_candidate(rule_score=50, confluences=["ob_fvg_overlap"])
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx)
        assert decision.ai_score >= 50 + 20

    def test_choch_confirmed_bonus(self):
        """CHoCH confirmed should add +10."""
        candidate = make_candidate(rule_score=50, confluences=["choch_confirmed"])
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx)
        assert decision.ai_score >= 50 + 10

    def test_news_penalty(self):
        """Near news should subtract -25."""
        candidate = make_candidate(rule_score=80)
        ctx = make_context()
        decision = self.scorer.score(candidate, ctx, news_nearby=True, spread=5.0)
        # 80 - 25(news) + 0(spread) = 55
        assert decision.ai_score <= 55
        assert any("news" in f for f in decision.risk_flags)

    def test_score_clamped_to_100(self):
        """Score should not exceed 100."""
        candidate = make_candidate(
            rule_score=95,
            rr_ratio=4.0,
            confluences=["liquidity_sweep", "fvg_present", "ob_fvg_overlap", "choch_confirmed"],
        )
        ctx = make_context(htf_trend=Direction.BUY)
        decision = self.scorer.score(candidate, ctx, session="london", spread=1.0)
        assert decision.ai_score <= 100
        assert decision.combined_score <= 100

    def test_score_clamped_to_zero(self):
        """Score should not go below 0."""
        candidate = make_candidate(rule_score=5)
        ctx = make_context(htf_trend=Direction.SELL)
        decision = self.scorer.score(
            candidate, ctx, session="asian", spread=15.0, news_nearby=True
        )
        assert decision.ai_score >= 0

    def test_decision_buy_above_threshold(self):
        """BUY decision when score >= threshold (70)."""
        candidate = make_candidate(direction=Direction.BUY, rule_score=70)
        ctx = make_context(htf_trend=Direction.BUY)
        decision = self.scorer.score(candidate, ctx, session="london")
        assert decision.decision == "BUY"

    def test_decision_sell_above_threshold(self):
        """SELL decision when score >= threshold."""
        candidate = make_candidate(direction=Direction.SELL, rule_score=70)
        ctx = make_context(htf_trend=Direction.SELL)
        decision = self.scorer.score(candidate, ctx, session="london")
        assert decision.decision == "SELL"

    def test_decision_wait_below_threshold(self):
        """WAIT decision when score < threshold."""
        candidate = make_candidate(rule_score=30)
        ctx = make_context(htf_trend=Direction.SELL)
        decision = self.scorer.score(candidate, ctx, session="asian", spread=10.0)
        assert decision.decision == "WAIT"

    def test_confidence_matches_score(self):
        """Confidence should equal score / 100."""
        candidate = make_candidate(rule_score=80)
        ctx = make_context(htf_trend=Direction.BUY)
        decision = self.scorer.score(candidate, ctx, session="london")
        assert decision.confidence == pytest.approx(decision.ai_score / 100.0, abs=0.01)

    def test_risk_flags_accumulated(self):
        """Risk flags from candidate + scorer should be combined."""
        candidate = make_candidate(rule_score=50, risk_flags=["existing_flag"])
        ctx = make_context(htf_trend=Direction.SELL)
        decision = self.scorer.score(candidate, ctx, session="asian")
        assert "existing_flag" in decision.risk_flags

    def test_reasons_list_populated(self):
        """Reasons list should contain explanations for bonuses."""
        candidate = make_candidate(rule_score=50)
        ctx = make_context(htf_trend=Direction.BUY)
        decision = self.scorer.score(candidate, ctx, session="london")
        assert len(decision.reasons) > 0

    def test_multiple_confluences_compound(self):
        """Multiple confluences should compound bonuses."""
        candidate = make_candidate(
            rule_score=40,
            rr_ratio=3.5,
            confluences=["liquidity_sweep", "fvg_present", "choch_confirmed"],
        )
        ctx = make_context(htf_trend=Direction.BUY)
        decision = self.scorer.score(candidate, ctx, session="london", spread=1.0)
        assert decision.ai_score >= 80
        assert decision.decision == "BUY"

    def test_no_htf_trend_no_penalty(self):
        """When htf_trend is None, no HTF bonus or penalty."""
        candidate = make_candidate(rule_score=60)
        ctx = make_context(htf_trend=None)
        decision = self.scorer.score(candidate, ctx, spread=5.0)
        assert decision.ai_score == 60
