"""Unit tests for NewsFilter and TradeFilter news integration."""

from datetime import datetime, timedelta, timezone
import pytest

from src.core.types import Direction, StrategyCandidate
from src.market.news_filter import EconomicEvent, NewsFilter, NewsFilterResult
from src.risk.filters import TradeFilter


def _make_candidate(timestamp: datetime | None = None) -> StrategyCandidate:
    ts = timestamp or datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    return StrategyCandidate(
        strategy_id="fvg_test",
        strategy_name="FVG Test",
        symbol="BTCUSDT",
        timeframe="M15",
        direction=Direction.BUY,
        rule_score=80,
        entry_price=65000.0,
        stop_loss=64500.0,
        take_profit_1=66500.0,
        rr_ratio=3.0,
        timestamp=ts,
    )


def test_news_filter_disabled():
    event = EconomicEvent(
        name="FOMC Decision",
        impact="HIGH",
        event_time=datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc),
    )
    nf = NewsFilter(events=[event], enabled=False)
    res = nf.check_news_window(datetime(2026, 10, 15, 17, 50, tzinfo=timezone.utc))
    assert res.is_blocked is False


def test_news_filter_high_impact_window():
    event_time = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)
    event = EconomicEvent(
        name="US CPI YoY",
        impact="HIGH",
        event_time=event_time,
        currency="USD",
    )
    nf = NewsFilter(events=[event], minutes_before=30, minutes_after=15, enabled=True)

    # 40 min before -> Safe
    res_safe_before = nf.check_news_window(event_time - timedelta(minutes=40))
    assert res_safe_before.is_blocked is False

    # 20 min before -> BLOCKED
    res_blocked_before = nf.check_news_window(event_time - timedelta(minutes=20))
    assert res_blocked_before.is_blocked is True
    assert "US CPI YoY" in res_blocked_before.reason
    assert res_blocked_before.minutes_relative == 20

    # 5 min after -> BLOCKED
    res_blocked_after = nf.check_news_window(event_time + timedelta(minutes=5))
    assert res_blocked_after.is_blocked is True
    assert res_blocked_after.minutes_relative == -5

    # 25 min after -> Safe
    res_safe_after = nf.check_news_window(event_time + timedelta(minutes=25))
    assert res_safe_after.is_blocked is False


def test_news_filter_medium_low_impact_ignored():
    event_time = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)
    event_med = EconomicEvent(name="Minor Survey", impact="MEDIUM", event_time=event_time)
    event_low = EconomicEvent(name="Jobless Claims Low", impact="LOW", event_time=event_time)
    nf = NewsFilter(events=[event_med, event_low], minutes_before=30, minutes_after=15, enabled=True)

    # During event time, medium and low should not block
    res = nf.check_news_window(event_time)
    assert res.is_blocked is False


def test_trade_filter_integration_with_news():
    event_time = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)
    event = EconomicEvent(name="US CPI YoY", impact="HIGH", event_time=event_time)
    nf = NewsFilter(events=[event], minutes_before=30, minutes_after=15, enabled=True)
    tf = TradeFilter(news_filter=nf)

    # Candidate at 13:45 (15m before CPI) -> Should be rejected
    candidate_blocked = _make_candidate(timestamp=event_time - timedelta(minutes=15))
    passed, reason = tf.check_all(candidate_blocked, session="london", current_spread=1.0)
    assert passed is False
    assert "High-impact news blackout" in reason
    assert "US CPI YoY" in reason

    # Candidate at 12:30 (1h30m before CPI) -> Should pass
    candidate_safe = _make_candidate(timestamp=event_time - timedelta(minutes=90))
    passed_safe, reason_safe = tf.check_all(candidate_safe, session="london", current_spread=1.0)
    assert passed_safe is True
    assert reason_safe is None
