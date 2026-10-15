"""Order management — send, modify, cancel orders."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from src.core.config import settings
from src.core.events import EventType, event_bus
from src.core.runtime_control import get_runtime_trading_mode, is_live_armed
from src.core.types import OrderRequest, OrderResult
from src.execution.paper_gateway import PaperGateway
from src.market.binance_gateway import BinanceGateway

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages order lifecycle.

    - Validates orders before sending
    - Sends orders to Binance
    - Publishes events on success/failure
    - Tracks order history
    """

    def __init__(self, gateway: BinanceGateway | PaperGateway) -> None:
        self._gateway = gateway
        self._order_history: list[OrderResult] = []

    async def send_market_order(self, request: OrderRequest) -> OrderResult:
        """
        Send a market order after validation.

        Args:
            request: Order details

        Returns:
            OrderResult with execution details
        """
        # Runtime mode is persisted separately so the dashboard can change it
        # without restarting the deployment. LIVE additionally requires an
        # explicit arm action; it must never be enabled by a mode label alone.
        trading_mode = get_runtime_trading_mode(settings.trading_mode)
        venue = getattr(self._gateway, "venue", "binance")
        paper_binance = (
            venue == "binance"
            and settings.binance_mode == "paper"
            and trading_mode == "paper"
        )
        if trading_mode == "live" and venue == "binance":
            return OrderResult(
                success=False,
                error_message="Binance LIVE execution is disabled; use DEMO with Binance testnet safeguards",
            )
        broker_mode_allowed = trading_mode == "demo" or (trading_mode == "live" and is_live_armed())
        if not broker_mode_allowed and not paper_binance:
            return OrderResult(
                success=False,
                error_message="Broker execution requires DEMO or explicitly armed LIVE; PAPER is analysis-only",
            )

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

        # Send through the Binance gateway
        logger.info(
            f"Sending order: {request.direction.value} {request.volume} "
            f"{request.symbol} @ market, SL={request.sl:.2f}, TP={request.tp:.2f}"
        )

        result = await self._gateway.send_order(request)

        if result.success:
            fill_price_str = f"{result.price:.2f}" if isinstance(result.price, (int, float)) else str(result.price)
            logger.info(
                f"Order filled: ticket={result.ticket}, price={fill_price_str}, "
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
        result = await self._gateway.modify_position(ticket, sl, tp)

        if result.success:
            logger.info(f"Position {ticket} modified: SL={sl}, TP={tp}")
        else:
            logger.error(f"Modify failed for {ticket}: {result.error_message}")

        return result

    async def close_position(self, ticket: int, volume: Optional[float] = None) -> OrderResult:
        """Close a specific position."""
        import inspect
        sig = inspect.signature(self._gateway.close_position)
        if "volume" in sig.parameters:
            result = await self._gateway.close_position(ticket, volume=volume)
        else:
            result = await self._gateway.close_position(ticket)

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
