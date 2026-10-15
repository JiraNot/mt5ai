"""Unit tests for Walk-Forward Backtesting Suite."""

import pytest
from datetime import datetime, timezone, timedelta

from src.core.types import Candle
from src.strategies.registry import auto_discover
from src.analytics.walk_forward import WalkForwardAnalyzer, WalkForwardReport


def _generate_synthetic_candles(count: int = 120, base_price: float = 60000.0) -> list[Candle]:
    """Generate alternating trending and swinging candles for testing."""
    now = datetime.now(timezone.utc)
    candles = []
    p = base_price
    for i in range(count):
        t = now - timedelta(minutes=5 * (count - i))
        # Alternating up and down swings
        step = 25.0 if (i // 10) % 2 == 0 else -20.0
        p += step
        candles.append(
            Candle(
                timestamp=t,
                open=p - 10,
                high=p + 20,
                low=p - 20,
                close=p + 10,
                volume=150.0 + (i % 5) * 50,
            )
        )
    return candles


@pytest.fixture(autouse=True)
def init_strategies():
    auto_discover()


def test_walk_forward_execution():
    """Test Walk-Forward analysis across rolling segments."""
    m5_candles = _generate_synthetic_candles(150, base_price=64000.0)
    h1_candles = _generate_synthetic_candles(50, base_price=64000.0)

    candles_by_tf = {"M5": m5_candles, "H1": h1_candles}

    analyzer = WalkForwardAnalyzer()
    report = analyzer.run_walk_forward(
        strategy_id="fvg_final",
        symbol="BTCUSDT",
        candles_by_tf=candles_by_tf,
        n_windows=3,
        train_ratio=0.6,
        entry_tf="M5",
        htf="H1",
    )

    assert isinstance(report, WalkForwardReport)
    assert report.strategy_id == "fvg_final"
    assert report.symbol == "BTCUSDT"
    assert report.total_windows == 3
    assert len(report.windows) == 3

    # Check markdown generation
    md = report.summary_markdown
    assert "Walk-Forward Backtest Report" in md
    assert "Walk-Forward Efficiency (WFE)" in md
    assert "| Window |" in md


def test_walk_forward_insufficient_candles():
    """Test ValueError raised when candles are insufficient for multi-window split."""
    short_candles = _generate_synthetic_candles(40)
    analyzer = WalkForwardAnalyzer()

    with pytest.raises(ValueError, match="Insufficient candles"):
        analyzer.run_walk_forward(
            strategy_id="fvg_final",
            symbol="BTCUSDT",
            candles_by_tf={"M5": short_candles, "H1": short_candles},
            n_windows=3,
        )


def test_walk_forward_unknown_strategy():
    """Test ValueError on non-existent strategy."""
    candles = _generate_synthetic_candles(100)
    analyzer = WalkForwardAnalyzer()

    with pytest.raises(ValueError, match="not registered"):
        analyzer.run_walk_forward(
            strategy_id="non_existent_strat",
            symbol="BTCUSDT",
            candles_by_tf={"M5": candles, "H1": candles},
        )
