"""Event bus for inter-module communication."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """All event types in the system."""

    # Market data events
    NEW_CANDLE = "new_candle"
    NEW_TICK = "new_tick"

    # Structure events
    STRUCTURE_DETECTED = "structure_detected"
    SWING_DETECTED = "swing_detected"
    FVG_DETECTED = "fvg_detected"
    ORDER_BLOCK_DETECTED = "order_block_detected"
    LIQUIDITY_SWEEP_DETECTED = "liquidity_sweep_detected"

    # Strategy events
    CANDIDATE_FOUND = "candidate_found"
    NO_CANDIDATE = "no_candidate"

    # AI events
    AI_DECIDED = "ai_decided"
    AI_SKIPPED = "ai_skipped"

    # Risk events
    RISK_APPROVED = "risk_approved"
    RISK_REJECTED = "risk_rejected"

    # Execution events
    ORDER_SENT = "order_sent"
    ORDER_FILLED = "order_filled"
    ORDER_FAILED = "order_failed"
    ORDER_CANCELLED = "order_cancelled"

    # Position events
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_UPDATED = "position_updated"

    # Trade events
    TRADE_JOURNALED = "trade_journaled"
    SETUP_LOGGED = "setup_logged"

    # System events
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    CIRCUIT_BREAKER = "circuit_breaker"
    ERROR = "error"


# Type alias for event handlers
EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """
    Async event bus for decoupled communication between modules.

    Usage:
        bus = EventBus()
        bus.subscribe(EventType.NEW_CANDLE, my_handler)
        await bus.publish(EventType.NEW_CANDLE, data=candle)
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._event_count: dict[EventType, int] = {}

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug(f"Handler {handler.__name__} subscribed to {event_type.value}")

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    async def publish(self, event_type: EventType, data: Any = None) -> None:
        """Publish an event to all subscribed handlers."""
        self._event_count[event_type] = self._event_count.get(event_type, 0) + 1
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            return

        logger.debug(
            f"Publishing {event_type.value} to {len(handlers)} handlers "
            f"(total: {self._event_count[event_type]})"
        )

        for handler in handlers:
            try:
                await handler(data)
            except Exception as e:
                logger.error(
                    f"Error in handler {handler.__name__} for {event_type.value}: {e}",
                    exc_info=True,
                )
                # Publish error event (avoid infinite recursion)
                if event_type != EventType.ERROR:
                    await self.publish(EventType.ERROR, {"error": str(e), "event": event_type.value})

    def get_stats(self) -> dict[str, int]:
        """Get event publish counts."""
        return {k.value: v for k, v in self._event_count.items()}

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
        self._event_count.clear()


# Global event bus instance
event_bus = EventBus()
