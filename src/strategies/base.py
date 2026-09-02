"""Base class for all strategy plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.core.types import Candle, Direction, StrategyCandidate
from src.structure.context import MultiTimeframeContext


class StrategyPlugin(ABC):
    """
    Base class for all strategy plugins.

    Each strategy must:
    - Have a unique strategy_id
    - Implement analyze() to produce StrategyCandidate
    - Define min_rr() for minimum risk-reward
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique identifier, e.g. 'breakout_retest'"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version"""
        pass

    @abstractmethod
    def analyze(
        self,
        context: MultiTimeframeContext,
        current_candle: Candle,
        current_price: float,
        spread: float,
        session: str,
    ) -> Optional[StrategyCandidate]:
        """
        Analyze current market state and return a candidate if setup exists.

        Returns None if no valid setup found.
        """
        pass

    @abstractmethod
    def min_rr(self) -> float:
        """Minimum risk-reward ratio for this strategy."""
        pass

    def get_config(self) -> dict:
        """Override to provide strategy-specific config."""
        return {}
