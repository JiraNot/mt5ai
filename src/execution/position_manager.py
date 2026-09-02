"""Position Manager — manages open positions.

Features:
- Move to breakeven
- Trailing stop loss
- Structure-based trailing
- Partial close
- Time-based exit
- Invalidation exit
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.core.types import Direction

logger = logging.getLogger(__name__)


class ExitReason(str, Enum):
    """Reason for closing a position."""
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    BREAKEVEN = "BREAKEVEN"
    TRAILING = "TRAILING"
    PARTIAL = "PARTIAL"
    TIME_EXIT = "TIME_EXIT"
    INVALIDATION = "INVALIDATION"
    MANUAL = "MANUAL"
    KILL_SWITCH = "KILL_SWITCH"


class PositionState(str, Enum):
    """Position lifecycle states."""
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    CLOSED = "CLOSED"


class Position(BaseModel):
    """Trading position with management rules."""

    # Identification
    id: str
    ticket: Optional[int] = None
    symbol: str
    direction: Direction
    strategy: str = ""

    # Entry
    entry_price: float
    volume: float
    original_volume: float

    # Risk
    sl: float
    tp: float
    tp2: Optional[float] = None
    tp3: Optional[float] = None

    # Management
    breakevenTriggered: bool = False
    breakevenLevel: float = 0.0
    trailingActive: bool = False
    trailingDistance: float = 0.0
    trailingStep: float = 0.0

    # Partial close
    partialCloseEnabled: bool = False
    partialClosePercent: float = 0.5  # Close 50% at TP1
    partialClosed: bool = False

    # Time-based exit
    maxHoldTime: Optional[timedelta] = None
    entryTime: datetime = Field(default_factory=datetime.utcnow)

    # State
    state: PositionState = PositionState.OPEN
    currentPrice: float = 0.0
    unrealizedPnL: float = 0.0
    realizedPnL: float = 0.0

    # Exit tracking
    exitPrice: Optional[float] = None
    exitTime: Optional[datetime] = None
    exitReason: Optional[ExitReason] = None

    # Performance
    mfe: float = 0.0  # Maximum Favorable Excursion
    mae: float = 0.0  # Maximum Adverse Excursion
    rMultiple: float = 0.0

    # Metadata
    magic: int = 20240101
    comment: str = ""

    @property
    def is_open(self) -> bool:
        return self.state != PositionState.CLOSED

    @property
    def risk_amount(self) -> float:
        """Calculate risk in price terms."""
        if self.direction == Direction.BUY:
            return self.entry_price - self.sl
        else:
            return self.sl - self.entry_price

    @property
    def currentR(self) -> float:
        """Calculate current R-multiple."""
        if self.risk_amount <= 0:
            return 0.0

        if self.direction == Direction.BUY:
            profit = self.currentPrice - self.entry_price
        else:
            profit = self.entry_price - self.currentPrice

        return profit / self.risk_amount


class PositionManager:
    """Manages open positions with various exit strategies."""

    def __init__(self):
        self._positions: dict[str, Position] = {}

    def open_position(
        self,
        symbol: str,
        direction: Direction,
        entry_price: float,
        volume: float,
        sl: float,
        tp: float,
        strategy: str = "",
        magic: int = 20240101,
        comment: str = "",
        breakeven_trigger: float = 0.0,
        trailing_distance: float = 0.0,
        partial_close: bool = False,
        max_hold_time: timedelta | None = None,
    ) -> Position:
        """Open a new position."""
        import time
        position_id = f"POS_{int(time.time() * 1000)}"

        position = Position(
            id=position_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            volume=volume,
            original_volume=volume,
            sl=sl,
            tp=tp,
            strategy=strategy,
            magic=magic,
            comment=comment,
            currentPrice=entry_price,
            breakevenTriggered=breakeven_trigger > 0,
            breakevenLevel=breakeven_trigger,
            trailingActive=trailing_distance > 0,
            trailingDistance=trailing_distance,
            partialCloseEnabled=partial_close,
            maxHoldTime=max_hold_time,
        )

        self._positions[position_id] = position
        logger.info(f"Position opened: {position_id} {direction.value} {symbol} @ {entry_price}")
        return position

    def update_price(self, position_id: str, current_price: float) -> list[dict]:
        """
        Update position with current price and check management rules.

        Returns list of actions to take (modify SL, partial close, etc.)
        """
        position = self._positions.get(position_id)
        if not position or not position.is_open:
            return []

        position.currentPrice = current_price
        actions = []

        # Update MFE/MAE
        if position.direction == Direction.BUY:
            unrealized = current_price - position.entry_price
        else:
            unrealized = position.entry_price - current_price

        if unrealized > position.mfe:
            position.mfe = unrealized
        if unrealized < position.mae:
            position.mae = unrealized

        # Update unrealized PnL
        position.unrealizedPnL = unrealized * position.volume * 100  # XAUUSD contract = 100

        # Check Breakeven
        if position.breakevenTriggered and not position.breakevenLevel:
            # Auto-calculate breakeven level (entry + spread offset)
            spread_offset = 0.5  # 0.5 points buffer
            if position.direction == Direction.BUY:
                position.breakevenLevel = position.entry_price + spread_offset
            else:
                position.breakevenLevel = position.entry_price - spread_offset

        if position.breakevenTriggered and position.breakevenLevel:
            if self._should_move_breakeven(position, current_price):
                actions.append({
                    "type": "MODIFY_SL",
                    "position_id": position_id,
                    "new_sl": position.breakevenLevel,
                    "reason": "Breakeven triggered",
                })

        # Check Trailing Stop
        if position.trailingActive:
            new_sl = self._calculate_trailing_sl(position, current_price)
            if new_sl and new_sl != position.sl:
                actions.append({
                    "type": "MODIFY_SL",
                    "position_id": position_id,
                    "new_sl": new_sl,
                    "reason": "Trailing stop update",
                })

        # Check Partial Close
        if position.partialCloseEnabled and not position.partialClosed:
            if self._should_partial_close(position, current_price):
                partial_volume = position.volume * position.partialClosePercent
                actions.append({
                    "type": "PARTIAL_CLOSE",
                    "position_id": position_id,
                    "volume": partial_volume,
                    "reason": "Partial close at TP1",
                })
                position.partialClosed = True

        # Check Time Exit
        if position.maxHoldTime:
            hold_time = datetime.utcnow() - position.entryTime
            if hold_time >= position.maxHoldTime:
                actions.append({
                    "type": "CLOSE",
                    "position_id": position_id,
                    "reason": "Max hold time exceeded",
                })

        return actions

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: ExitReason = ExitReason.MANUAL,
    ) -> bool:
        """Close a position."""
        position = self._positions.get(position_id)
        if not position or not position.is_open:
            return False

        position.state = PositionState.CLOSED
        position.exitPrice = exit_price
        position.exitTime = datetime.utcnow()
        position.exitReason = reason

        # Calculate final PnL
        if position.direction == Direction.BUY:
            pnl = (exit_price - position.entry_price) * position.volume * 100
        else:
            pnl = (position.entry_price - exit_price) * position.volume * 100

        position.realizedPnL = pnl
        position.rMultiple = pnl / (position.risk_amount * position.volume * 100) if position.risk_amount > 0 else 0

        logger.info(
            f"Position closed: {position_id} | "
            f"PnL: ${pnl:.2f} | R: {position.rMultiple:.2f} | "
            f"Reason: {reason.value}"
        )

        return True

    def _should_move_breakeven(self, position: Position, current_price: float) -> bool:
        """Check if SL should be moved to breakeven."""
        if position.direction == Direction.BUY:
            return current_price >= position.breakevenLevel and position.sl < position.breakevenLevel
        else:
            return current_price <= position.breakevenLevel and position.sl > position.breakevenLevel

    def _calculate_trailing_sl(self, position: Position, current_price: float) -> float | None:
        """Calculate new trailing stop level."""
        if position.trailingDistance <= 0:
            return None

        if position.direction == Direction.BUY:
            new_sl = current_price - position.trailingDistance
            # Only move SL up, never down
            if new_sl > position.sl:
                return new_sl
        else:
            new_sl = current_price + position.trailingDistance
            # Only move SL down, never up
            if new_sl < position.sl:
                return new_sl

        return None

    def _should_partial_close(self, position: Position, current_price: float) -> bool:
        """Check if partial close should be triggered."""
        # Simple implementation: partial close at 1R
        if position.direction == Direction.BUY:
            return current_price >= position.entry_price + position.risk_amount
        else:
            return current_price <= position.entry_price - position.risk_amount

    def get_position(self, position_id: str) -> Position | None:
        """Get position by ID."""
        return self._positions.get(position_id)

    def get_open_positions(self) -> list[Position]:
        """Get all open positions."""
        return [p for p in self._positions.values() if p.is_open]

    def get_positions_by_symbol(self, symbol: str) -> list[Position]:
        """Get all positions for a symbol."""
        return [p for p in self._positions.values() if p.symbol == symbol]

    def get_statistics(self) -> dict:
        """Get position statistics."""
        open_positions = self.get_open_positions()
        total_pnl = sum(p.realizedPnL for p in self._positions.values())
        total_trades = len([p for p in self._positions.values() if p.state == PositionState.CLOSED])
        winners = len([p for p in self._positions.values() if p.state == PositionState.CLOSED and p.realizedPnL > 0])

        return {
            "open_positions": len(open_positions),
            "total_pnl": round(total_pnl, 2),
            "total_trades": total_trades,
            "winners": winners,
            "win_rate": round(winners / total_trades * 100, 1) if total_trades > 0 else 0,
        }
