"""Spread health monitoring."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime

from src.core.config import settings

logger = logging.getLogger(__name__)


class SpreadMonitor:
    """
    Monitors spread health for a symbol.

    Tracks spread history and detects abnormal spread conditions.
    """

    def __init__(self, symbol: str, history_size: int = 100) -> None:
        self.symbol = symbol
        self._history: deque[tuple[datetime, float]] = deque(maxlen=history_size)
        self._symbol_config = settings.symbols.get(symbol)

    @property
    def normal_spread(self) -> float:
        if self._symbol_config:
            return self._symbol_config.normal_spread
        return settings.risk.max_spread_pips

    @property
    def max_spread(self) -> float:
        if self._symbol_config:
            return self._symbol_config.max_spread
        return settings.risk.max_spread_pips * 2

    def update(self, spread: float) -> None:
        """Record a new spread reading."""
        self._history.append((datetime.utcnow(), spread))

    def get_current_spread(self) -> float | None:
        """Get the most recent spread reading."""
        if self._history:
            return self._history[-1][1]
        return None

    def get_average_spread(self, periods: int = 20) -> float:
        """Get average spread over recent periods."""
        if not self._history:
            return 0.0

        recent = list(self._history)[-periods:]
        return sum(s for _, s in recent) / len(recent)

    def is_spread_healthy(self, current_spread: float | None = None) -> bool:
        """Check if current spread is within acceptable range."""
        if current_spread is None:
            current_spread = self.get_current_spread()
        if current_spread is None:
            return False

        return current_spread <= self.normal_spread

    def is_spread_extreme(self, current_spread: float | None = None) -> bool:
        """Check if spread is abnormally wide (news event, etc.)."""
        if current_spread is None:
            current_spread = self.get_current_spread()
        if current_spread is None:
            return False

        return current_spread > self.max_spread

    def get_spread_status(self, current_spread: float | None = None) -> str:
        """Get human-readable spread status."""
        if current_spread is None:
            current_spread = self.get_current_spread()
        if current_spread is None:
            return "unknown"

        avg = self.get_average_spread()
        if current_spread > self.max_spread:
            return "extreme"
        elif current_spread > self.normal_spread * 1.5:
            return "wide"
        elif current_spread <= avg * 0.8:
            return "tight"
        else:
            return "normal"
