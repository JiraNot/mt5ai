"""Unit tests for MT5Connection without mock fallback."""

import pytest
from unittest.mock import MagicMock, patch
from src.core.exceptions import MT5ConnectionError
from src.core.types import Direction, OrderRequest
from src.market.mt5_connection import MT5Connection


@pytest.mark.asyncio
async def test_mt5_connection_not_connected_raises_error():
    conn = MT5Connection()
    assert not conn.connected

    with pytest.raises(MT5ConnectionError):
        conn._ensure_connected()

    with pytest.raises(MT5ConnectionError):
        await conn.get_ohlcv("XAUUSD", "M5", 100)

    with pytest.raises(MT5ConnectionError):
        await conn.get_current_price("XAUUSD")

    with pytest.raises(MT5ConnectionError):
        await conn.get_account_info()

    with pytest.raises(MT5ConnectionError):
        await conn.get_symbol_info("XAUUSD")

    with pytest.raises(MT5ConnectionError):
        await conn.send_order(
            OrderRequest(
                symbol="XAUUSD",
                direction=Direction.BUY,
                volume=0.01,
                sl=2300.0,
                tp=2400.0,
            )
        )

    with pytest.raises(MT5ConnectionError):
        await conn.get_positions()


@pytest.mark.asyncio
async def test_mt5_connection_fails_cleanly_when_mt5_unavailable():
    with patch("src.market.mt5_connection.MT5_AVAILABLE", False):
        conn = MT5Connection()
        success = await conn.connect()
        assert success is False
        assert not conn.connected
