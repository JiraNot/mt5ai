"""Unit tests for BTCRegimeAnalyzer and CryptoScreener."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.types import Candle, Direction
from src.market.btc_regime import BTCRegimeAnalyzer, BTCRegimeReport
from src.market.crypto_screener import CryptoCandidate, CryptoScreener, CryptoWatchlist
from src.structure.regime import MarketRegime


def _create_mock_candles(trend: str = "bullish", count: int = 40) -> list[Candle]:
    """Generate synthetic candles for regime testing."""
    candles = []
    base_price = 60000.0
    for i in range(count):
        if trend == "bullish":
            price = base_price + i * 200.0
        elif trend == "bearish":
            price = base_price - i * 200.0
        else:
            price = base_price + (100.0 if i % 2 == 0 else -100.0)

        candles.append(
            Candle(
                timestamp=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
                open=price - 50.0,
                high=price + 100.0,
                low=price - 80.0,
                close=price,
                volume=1000.0,
            )
        )
    return candles


def test_btc_regime_analyzer_empty():
    analyzer = BTCRegimeAnalyzer()
    report = analyzer.analyze([])
    assert report.regime == MarketRegime.UNKNOWN
    assert report.is_tradable is False
    assert "ไม่มีข้อมูล" in report.recommendation_th


def test_btc_regime_analyzer_uptrend_and_funding():
    analyzer = BTCRegimeAnalyzer()
    candles = _create_mock_candles(trend="bullish", count=50)

    # Normal funding
    report = analyzer.analyze(candles, funding_rate=0.0001)
    assert report.symbol == "BTCUSDT"
    assert report.funding_bias == "NEUTRAL"
    assert report.current_price > 0
    ctx_dict = report.to_context_dict()
    assert "btc_regime" in ctx_dict
    assert ctx_dict["btc_funding_bias"] == "NEUTRAL"

    # High funding (Long crowded)
    report_crowded = analyzer.analyze(candles, funding_rate=0.0004)
    assert report_crowded.funding_bias == "LONG_CROWDED"
    assert "ระวัง" in report_crowded.recommendation_th


def test_btc_regime_analyzer_short_crowded():
    analyzer = BTCRegimeAnalyzer()
    candles = _create_mock_candles(trend="bearish", count=50)
    report = analyzer.analyze(candles, funding_rate=-0.0002)
    assert report.funding_bias == "SHORT_CROWDED"


def test_crypto_screener_filtering():
    raw_tickers = [
        # Valid high volume USDT pair
        {
            "symbol": "BTCUSDT",
            "lastPrice": "65000.0",
            "priceChangePercent": "3.5",
            "quoteVolume": "800000000.0",
            "highPrice": "66000.0",
            "lowPrice": "64000.0",
        },
        # Valid high volatility USDT pair
        {
            "symbol": "SOLUSDT",
            "lastPrice": "150.0",
            "priceChangePercent": "8.5",
            "quoteVolume": "120000000.0",
            "highPrice": "158.0",
            "lowPrice": "142.0",
        },
        # Low volume pair (< 30M)
        {
            "symbol": "LOWVOLUSDT",
            "lastPrice": "1.0",
            "priceChangePercent": "1.0",
            "quoteVolume": "5000000.0",
            "highPrice": "1.05",
            "lowPrice": "0.95",
        },
        # Non-USDT pair (BUSD or quarterly contract)
        {
            "symbol": "BTCUSDT_241227",
            "lastPrice": "66000.0",
            "priceChangePercent": "2.0",
            "quoteVolume": "50000000.0",
            "highPrice": "67000.0",
            "lowPrice": "65000.0",
        },
    ]

    screener = CryptoScreener(min_24h_volume_usdt=30_000_000.0, top_n=5)
    candidates = screener.screen_tickers(raw_tickers)

    symbols = [c.symbol for c in candidates]
    assert "BTCUSDT" in symbols
    assert "SOLUSDT" in symbols
    assert "LOWVOLUSDT" not in symbols
    assert "BTCUSDT_241227" not in symbols

    # Check tags and formatting
    sol = next(c for c in candidates if c.symbol == "SOLUSDT")
    assert "High Momentum" in sol.tags
    assert sol.formatted_volume == "$120.0M"


@pytest.mark.asyncio
async def test_crypto_screener_run_homework_mock():
    mock_gateway = MagicMock()
    mock_gateway.connected = True
    mock_gateway.get_ohlcv = AsyncMock(return_value=_create_mock_candles("bullish", 40))
    mock_gateway.get_funding_rate = AsyncMock(return_value=0.0001)
    mock_gateway.get_24hr_tickers = AsyncMock(
        return_value=[
            {
                "symbol": "BTCUSDT",
                "lastPrice": "65000.0",
                "priceChangePercent": "2.0",
                "quoteVolume": "1000000000.0",
                "highPrice": "66000.0",
                "lowPrice": "64000.0",
            },
            {
                "symbol": "ETHUSDT",
                "lastPrice": "3500.0",
                "priceChangePercent": "4.5",
                "quoteVolume": "500000000.0",
                "highPrice": "3600.0",
                "lowPrice": "3400.0",
            },
        ]
    )

    screener = CryptoScreener(gateway=mock_gateway, min_24h_volume_usdt=10_000_000.0, top_n=2)
    watchlist = await screener.run_homework()

    assert isinstance(watchlist, CryptoWatchlist)
    assert len(watchlist.candidates) == 2
    assert watchlist.btc_report is not None
    summary_text = watchlist.summary()
    assert "CRYPTO WATCHLIST & HOMEWORK" in summary_text
    assert "BTCUSDT" in summary_text
