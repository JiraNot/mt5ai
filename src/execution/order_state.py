"""Order State Machine — manages order lifecycle.

States:
    CREATED → VALIDATED → SUBMITTED → FILLED → ACTIVE → CLOSED
                    ↓           ↓          ↓
                REJECTED    FAILED    PARTIAL

Each state transition is logged and auditable.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class OrderState(str, Enum):
    """Order lifecycle states."""
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


# Valid state transitions
VALID_TRANSITIONS = {
    OrderState.CREATED: [OrderState.VALIDATED, OrderState.REJECTED],
    OrderState.VALIDATED: [OrderState.SUBMITTED, OrderState.REJECTED],
    OrderState.SUBMITTED: [OrderState.FILLED, OrderState.PARTIAL, OrderState.FAILED, OrderState.CANCELLED],
    OrderState.FILLED: [OrderState.ACTIVE, OrderState.CLOSED],
    OrderState.PARTIAL: [OrderState.ACTIVE, OrderState.CLOSED],
    OrderState.ACTIVE: [OrderState.CLOSED, OrderState.PARTIAL],
    OrderState.CLOSED: [],  # Terminal state
    OrderState.REJECTED: [],  # Terminal state
    OrderState.FAILED: [OrderState.CREATED],  # Can retry
    OrderState.CANCELLED: [],  # Terminal state
    OrderState.EXPIRED: [],  # Terminal state
}


class OrderEvent(BaseModel):
    """Order state transition event."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    from_state: OrderState
    to_state: OrderState
    reason: str = ""
    metadata: dict = Field(default_factory=dict)


class Order(BaseModel):
    """Order with state machine management."""

    # Order identification
    id: str
    ticket: Optional[int] = None
    magic: int = 20240101

    # Order details
    symbol: str
    direction: str  # BUY/SELL
    volume: float
    order_type: str = "MARKET"  # MARKET/LIMIT/STOP
    price: Optional[float] = None
    sl: float = 0.0
    tp: float = 0.0
    deviation: int = 10
    comment: str = ""

    # State
    state: OrderState = OrderState.CREATED
    filled_price: Optional[float] = None
    filled_volume: float = 0.0
    remaining_volume: float = 0.0

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    # Error tracking
    error_code: Optional[int] = None
    error_message: Optional[str] = None

    # History
    events: list[OrderEvent] = Field(default_factory=list)

    # Fingerprint for duplicate detection
    fingerprint: str = ""

    def transition(self, new_state: OrderState, reason: str = "", **kwargs) -> bool:
        """
        Transition to a new state.

        Returns True if transition was successful.
        """
        # Check if transition is valid
        valid_next = VALID_TRANSITIONS.get(self.state, [])
        if new_state not in valid_next:
            logger.error(
                f"Invalid transition: {self.state.value} → {new_state.value} "
                f"(valid: {[s.value for s in valid_next]})"
            )
            return False

        # Record event
        event = OrderEvent(
            from_state=self.state,
            to_state=new_state,
            reason=reason,
            metadata=kwargs,
        )
        self.events.append(event)

        # Update state
        old_state = self.state
        self.state = new_state

        # Update timestamps
        now = datetime.utcnow()
        if new_state == OrderState.SUBMITTED:
            self.submitted_at = now
        elif new_state == OrderState.FILLED:
            self.filled_at = now
            self.filled_price = kwargs.get("price", self.price)
            self.filled_volume = kwargs.get("volume", self.volume)
            self.remaining_volume = 0
        elif new_state == OrderState.PARTIAL:
            self.filled_volume = kwargs.get("filled_volume", self.filled_volume)
            self.remaining_volume = self.volume - self.filled_volume
        elif new_state == OrderState.CLOSED:
            self.closed_at = now
        elif new_state == OrderState.REJECTED:
            self.error_code = kwargs.get("error_code")
            self.error_message = kwargs.get("error_message")
        elif new_state == OrderState.FAILED:
            self.error_code = kwargs.get("error_code")
            self.error_message = kwargs.get("error_message")

        logger.info(
            f"Order {self.id}: {old_state.value} → {new_state.value} "
            f"(reason: {reason})"
        )

        return True

    def can_modify(self) -> bool:
        """Check if order can be modified (SL/TP)."""
        return self.state in (OrderState.SUBMITTED, OrderState.FILLED, OrderState.ACTIVE, OrderState.PARTIAL)

    def can_close(self) -> bool:
        """Check if order can be closed."""
        return self.state in (OrderState.FILLED, OrderState.ACTIVE, OrderState.PARTIAL)

    def is_terminal(self) -> bool:
        """Check if order is in a terminal state."""
        return self.state in (
            OrderState.CLOSED,
            OrderState.REJECTED,
            OrderState.CANCELLED,
            OrderState.EXPIRED,
        )

    @property
    def is_active(self) -> bool:
        """Check if order is actively managing a position."""
        return self.state in (OrderState.ACTIVE, OrderState.PARTIAL)


class OrderManager:
    """Manages order lifecycle and state transitions."""

    def __init__(self):
        self._orders: dict[str, Order] = {}
        self._fingerprints: set[str] = set()

    def create_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        sl: float,
        tp: float,
        order_type: str = "MARKET",
        price: float | None = None,
        comment: str = "",
        magic: int = 20240101,
    ) -> Order:
        """Create a new order."""
        import hashlib
        import time

        # Generate order ID
        order_id = f"ORD_{int(time.time() * 1000)}"

        # Generate fingerprint for duplicate detection
        fingerprint_data = f"{symbol}_{direction}_{sl}_{tp}_{comment}"
        fingerprint = hashlib.md5(fingerprint_data.encode()).hexdigest()[:12]

        # Check for duplicate
        if fingerprint in self._fingerprints:
            logger.warning(f"Duplicate order detected: {fingerprint}")
            raise ValueError(f"Duplicate order: {fingerprint}")

        order = Order(
            id=order_id,
            symbol=symbol,
            direction=direction,
            volume=volume,
            order_type=order_type,
            price=price,
            sl=sl,
            tp=tp,
            comment=comment,
            magic=magic,
            fingerprint=fingerprint,
        )

        self._orders[order_id] = order
        self._fingerprints.add(fingerprint)

        logger.info(f"Order created: {order_id} {direction} {symbol} {volume}")
        return order

    def get_order(self, order_id: str) -> Order | None:
        """Get order by ID."""
        return self._orders.get(order_id)

    def get_active_orders(self) -> list[Order]:
        """Get all active orders."""
        return [o for o in self._orders.values() if o.is_active]

    def get_orders_by_symbol(self, symbol: str) -> list[Order]:
        """Get all orders for a symbol."""
        return [o for o in self._orders.values() if o.symbol == symbol]

    def close_order(self, order_id: str, reason: str = "") -> bool:
        """Close an order."""
        order = self.get_order(order_id)
        if not order:
            return False

        if not order.can_close():
            logger.warning(f"Cannot close order {order_id} in state {order.state.value}")
            return False

        return order.transition(OrderState.CLOSED, reason=reason)

    def get_statistics(self) -> dict:
        """Get order statistics."""
        total = len(self._orders)
        active = len([o for o in self._orders.values() if o.is_active])
        closed = len([o for o in self._orders.values() if o.state == OrderState.CLOSED])
        rejected = len([o for o in self._orders.values() if o.state == OrderState.REJECTED])

        return {
            "total_orders": total,
            "active_orders": active,
            "closed_orders": closed,
            "rejected_orders": rejected,
        }
