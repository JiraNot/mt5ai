"""Custom exception hierarchy for the Freebuff Trading Platform."""

from __future__ import annotations


class FreebuffError(Exception):
    """Base exception for all Freebuff errors."""


class MT5ConnectionError(FreebuffError):
    """MT5 connection failed."""


class MT5OrderError(FreebuffError):
    """MT5 order execution failed."""


class DataFeedError(FreebuffError):
    """Market data feed error."""


class StrategyError(FreebuffError):
    """Strategy plugin error."""


class RiskLimitExceeded(FreebuffError):
    """Risk limit exceeded."""


class ConfigurationError(FreebuffError):
    """Configuration error."""


class DatabaseError(FreebuffError):
    """Database operation error."""


class CircuitBreakerTriggered(FreebuffError):
    """Emergency stop triggered."""
