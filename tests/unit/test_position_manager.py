"""Unit tests for PositionManager (Break-Even & Partial Take-Profit) and PaperGateway partial close."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from src.core.types import Direction, Position as CorePosition, OrderResult, Tick
from src.execution.position_manager import PositionManager, PositionState
from src.execution.paper_gateway import PaperGateway
from src.market.binance_gateway import BinanceGateway


@pytest.fixture
def mock_binance():
    gateway = AsyncMock(spec=BinanceGateway)
    gateway.connected = True
    gateway.get_current_price = AsyncMock(
        return_value=Tick(timestamp=datetime.now(timezone.utc), bid=65000.0, ask=65001.0, last=65000.5)
    )
    return gateway


@pytest.mark.asyncio
async def test_paper_gateway_partial_close(mock_binance):
    """Test that PaperGateway.close_position can partially close volume."""
    paper = PaperGateway(mock_binance, initial_balance=10000.0)
    now = datetime.now(timezone.utc)
    # Open a position of 1.0 volume BTC @ 60,000, current = 65,000 (profit = +5,000 per lot)
    pos = CorePosition(
        ticket=101,
        identifier=101,
        symbol="BTCUSDT",
        direction=Direction.BUY,
        volume=1.0,
        open_price=60000.0,
        current_price=65000.0,
        sl=58000.0,
        tp=70000.0,
        open_time=now,
    )
    paper._positions[101] = pos

    # 1. Partial close 0.5 volume
    res1 = await paper.close_position(ticket=101, volume=0.5)
    assert res1.success is True
    assert res1.volume == 0.5
    assert res1.metadata.get("remaining_volume") == 0.5
    # PnL for 0.5 volume = (65000 - 60000) * 0.5 = +2500
    assert res1.metadata.get("pnl") == 2500.0
    assert 101 in paper._positions
    assert paper._positions[101].volume == 0.5

    # 2. Close remaining 0.5 volume
    res2 = await paper.close_position(ticket=101)
    assert res2.success is True
    assert res2.volume == 0.5
    assert res2.metadata.get("remaining_volume") == 0.0
    assert 101 not in paper._positions


@pytest.mark.asyncio
async def test_position_manager_break_even():
    """Test that PositionManager triggers Break-Even when profit reaches >= 1.0R."""
    pm = PositionManager()
    mock_om = AsyncMock()
    mock_om.modify_sl_tp.return_value = OrderResult(success=True, ticket=201)

    # Position: BUY BTC @ 60,000, SL=58,000 (Risk distance = 2,000)
    pos = CorePosition(
        ticket=201,
        symbol="BTCUSDT",
        direction=Direction.BUY,
        volume=0.2,
        open_price=60000.0,
        current_price=61000.0,  # +1000 profit = 0.5R (not yet BE)
        sl=58000.0,
        tp=66000.0,
    )

    # At 0.5R profit (price=61,000), no BE action
    actions = await pm.manage_active_positions([pos], {"BTCUSDT": 61000.0}, order_manager=mock_om)
    assert len(actions) == 0
    mock_om.modify_sl_tp.assert_not_called()

    # At 1.0R profit (price=62,000): should trigger BE
    with patch("src.notification.telegram_alert.alert_break_even", new_callable=AsyncMock) as mock_alert:
        actions = await pm.manage_active_positions([pos], {"BTCUSDT": 62000.0}, order_manager=mock_om)
        assert len(actions) == 1
        assert actions[0]["type"] == "BREAK_EVEN"
        assert actions[0]["new_sl"] == 60000.0
        mock_om.modify_sl_tp.assert_called_once_with(ticket=201, sl=60000.0, tp=66000.0)
        mock_alert.assert_called_once()

    # Subsequent call should not re-trigger BE (already triggered)
    mock_om.modify_sl_tp.reset_mock()
    actions_repeat = await pm.manage_active_positions([pos], {"BTCUSDT": 62500.0}, order_manager=mock_om)
    assert len(actions_repeat) == 0
    mock_om.modify_sl_tp.assert_not_called()


@pytest.mark.asyncio
async def test_position_manager_partial_tp():
    """Test that PositionManager triggers Partial TP when profit reaches >= 1.5R."""
    pm = PositionManager()
    mock_om = AsyncMock()
    mock_om.modify_sl_tp.return_value = OrderResult(success=True, ticket=301)
    mock_om.close_position.return_value = OrderResult(success=True, ticket=301, volume=0.1)

    # SELL Position: ETH @ 3,000, SL=3,100 (Risk distance = 100)
    # At 1.5R profit: price = 3,000 - 150 = 2,850
    pos = CorePosition(
        ticket=301,
        symbol="ETHUSDT",
        direction=Direction.SELL,
        volume=0.2,
        open_price=3000.0,
        current_price=2840.0,  # 1.6R profit
        sl=3000.0,  # already at BE
        tp=2700.0,
    )
    pm._initial_risks[301] = 100.0
    pm._be_tickets.add(301)  # BE already processed

    with patch("src.notification.telegram_alert.alert_partial_tp", new_callable=AsyncMock) as mock_alert:
        actions = await pm.manage_active_positions([pos], {"ETHUSDT": 2840.0}, order_manager=mock_om)
        assert len(actions) == 1
        assert actions[0]["type"] == "PARTIAL_TP"
        assert actions[0]["closed_volume"] == 0.1  # 50% of 0.2
        mock_om.close_position.assert_called_once_with(ticket=301, volume=0.1)
        mock_alert.assert_called_once()

    # Subsequent call should not re-trigger partial TP
    mock_om.close_position.reset_mock()
    actions_repeat = await pm.manage_active_positions([pos], {"ETHUSDT": 2800.0}, order_manager=mock_om)
    assert len(actions_repeat) == 0
    mock_om.close_position.assert_not_called()
