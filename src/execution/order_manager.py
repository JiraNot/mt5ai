"""Order management — send, modify, cancel orders."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from src.core.config import settings
from src.core.events import EventType, event_bus
from src.core.types import OrderRequest, OrderResult
from src.market.mt5_connection import MT5Connection

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages order lifecycle.

    - Validates orders before sending
    - Sends orders to MT5
    - Publishes events on success/failure
    - Tracks order history
    """

    def __init__(self, mt5: MT5Connection) -> None:
        self._mt5 = mt5
        self._order_history: list[OrderResult] = []

    async def send_market_order(self, request: OrderRequest) -> OrderResult:
        """
        Send a market order after validation.

        Args:
            request: Order details

        Returns:
            OrderResult with execution details
        """
        # Validate
        validation_error = self._validate_order(request)
        if validation_error:
            logger.warning(f"Order validation failed: {validation_error}")
            result = OrderResult(
                success=False,
                error_message=validation_error,
            )
            await event_bus.publish(EventType.ORDER_FAILED, {
                "request": request,
                "result": result,
            })
            return result

        # Set magic from config
        if request.magic == 20240101:  # Default
            request.magic = settings.mt5.magic

        # Send to MT5
        logger.info(
            f"Sending order: {request.direction.value} {request.volume} "
            f"{request.symbol} @ market, SL={request.sl:.2f}, TP={request.tp:.2f}"
        )

        result = await self._mt5.send_order(request)

        if result.success:
            logger.info(
                f"Order filled: ticket={result.ticket}, price={result.price:.2f}, "
                f"volume={result.volume}"
            )
            await event_bus.publish(EventType.ORDER_FILLED, {
                "request": request,
                "result": result,
            })
        else:
            logger.error(
                f"Order failed: code={result.error_code}, "
                f"message={result.error_message}"
            )
            await event_bus.publish(EventType.ORDER_FAILED, {
                "request": request,
                "result": result,
            })

        self._order_history.append(result)
        return result

    async def modify_sl_tp(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> OrderResult:
        """Modify SL/TP of an existing position."""
        result = await self._mt5.modify_position(ticket, sl, tp)

        if result.success:
            logger.info(f"Position {ticket} modified: SL={sl}, TP={tp}")
        else:
            logger.error(f"Modify failed for {ticket}: {result.error_message}")

        return result

    async def close_position(self, ticket: int) -> OrderResult:
        """Close a specific position."""
        result = await self._mt5.close_position(ticket)

        if result.success:
            logger.info(f"Position {ticket} closed")
            await event_bus.publish(EventType.POSITION_CLOSED, {
                "ticket": ticket,
                "result": result,
            })
        else:
            logger.error(f"Close failed for {ticket}: {result.error_message}")

        return result

    def _validate_order(self, request: OrderRequest) -> Optional[str]:
        """Validate order before sending. Returns error message or None."""
        if request.volume <= 0:
            return f"Invalid volume: {request.volume}"

        if request.sl <= 0:
            return f"Invalid SL: {request.sl}"

        if request.tp <= 0:
            return f"Invalid TP: {request.tp}"

        if request.direction.value not in ("BUY", "SELL"):
            return f"Invalid direction: {request.direction}"

        return None

    def get_order_history(self) -> list[OrderResult]:
        """Get all past order results."""
        return list(self._order_history)
