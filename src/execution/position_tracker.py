"""Position tracking — syncs open positions from MT5."""

from __future__ import annotations

import logging
from typing import Optional

from src.core.events import EventType, event_bus
from src.core.types import Position
from src.execution.outcomes import reconcile_deals
from src.market.mt5_connection import MT5Connection

logger = logging.getLogger(__name__)


class PositionTracker:
    """
    Tracks all open positions in real-time.

    - Syncs positions from MT5
    - Detects position changes
    - Publishes position events
    """

    def __init__(self, mt5: MT5Connection) -> None:
        self._mt5 = mt5
        self._positions: dict[int, Position] = {}  # ticket -> Position

    async def sync_positions(self, symbol: Optional[str] = None) -> list[Position]:
        """
        Sync positions from MT5.

        Returns list of current open positions.
        """
        positions = await self._mt5.get_positions(symbol)

        # Track new/updated/closed positions
        current_tickets = {p.ticket for p in positions}

        # Missing from a successful snapshot is only a closure candidate.
        for ticket, previous in list(self._positions.items()):
            if symbol and previous.symbol != symbol:
                continue
            if ticket not in current_tickets:
                try:
                    position_id = previous.identifier or ticket
                    deals = await self._mt5.get_position_deals(position_id)
                    outcome = reconcile_deals(position_id, deals)
                    if outcome is None:
                        continue  # History may be delayed; retry next poll.
                    closed_pos = previous.model_copy(update={
                        "current_price": outcome.close_price,
                        "profit": outcome.net_profit, "swap": 0.0, "commission": 0.0,
                    })
                    await event_bus.publish(EventType.POSITION_CLOSED, {
                        "position": closed_pos, "outcome": outcome,
                    })
                    self._positions.pop(ticket, None)
                except Exception:
                    logger.exception("Closure reconciliation pending for %s", ticket)

        # Detect new/updated positions
        for pos in positions:
            if pos.ticket in self._positions:
                # Position updated
                old = self._positions[pos.ticket]
                if old.current_price != pos.current_price or old.profit != pos.profit:
                    await event_bus.publish(EventType.POSITION_UPDATED, {
                        "position": pos,
                        "previous": old,
                    })
            else:
                # New position
                logger.info(
                    f"New position: {pos.ticket} {pos.direction.value} "
                    f"{pos.volume} {pos.symbol} @ {pos.open_price:.2f}"
                )
                await event_bus.publish(EventType.POSITION_OPENED, {
                    "position": pos,
                })

            self._positions[pos.ticket] = pos

        return positions

    def get_position(self, ticket: int) -> Optional[Position]:
        """Get a specific position by ticket."""
        return self._positions.get(ticket)

    def get_all_positions(self) -> list[Position]:
        """Get all tracked positions."""
        return list(self._positions.values())

    def get_positions_by_symbol(self, symbol: str) -> list[Position]:
        """Get positions for a specific symbol."""
        return [p for p in self._positions.values() if p.symbol == symbol]

    def get_total_exposure(self) -> float:
        """Get total exposure across all positions."""
        return sum(p.volume * p.open_price for p in self._positions.values())

    def get_total_profit(self) -> float:
        """Get total unrealized P&L."""
        return sum(p.profit for p in self._positions.values())
