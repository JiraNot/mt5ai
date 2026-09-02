"""Session Engine — tracks and manages trading sessions.

Sessions:
- Asia: 00:00 - 07:00 UTC
- London: 07:00 - 16:00 UTC
- New York: 12:00 - 21:00 UTC
- Overlap: 12:00 - 16:00 UTC

Tracks:
- Session high/low
- Session volume
- Session range
- Current session
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.core.types import Candle

logger = logging.getLogger(__name__)


class TradingSession(str, Enum):
    """Trading sessions."""
    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"
    OFF_HOURS = "off_hours"


class SessionData(BaseModel):
    """Data for a specific trading session."""
    session: TradingSession
    date: str

    # Price data
    open_price: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0

    # Volume
    volume: float = 0.0
    tick_count: int = 0

    # Derived
    range: float = 0.0
    body: float = 0.0
    body_ratio: float = 0.0

    # Candle count
    candle_count: int = 0

    # State
    is_active: bool = False
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class SessionEngine:
    """Tracks and manages trading sessions."""

    # Session times (UTC)
    SESSION_TIMES = {
        TradingSession.ASIAN: (time(0, 0), time(7, 0)),
        TradingSession.LONDON: (time(7, 0), time(16, 0)),
        TradingSession.NEW_YORK: (time(12, 0), time(21, 0)),
        TradingSession.OVERLAP: (time(12, 0), time(16, 0)),
    }

    def __init__(self):
        self._sessions: dict[str, SessionData] = {}
        self._current_session: Optional[TradingSession] = None

    def get_current_session(self, dt: datetime | None = None) -> TradingSession:
        """Get current trading session."""
        if dt is None:
            dt = datetime.utcnow()

        current_time = dt.time()

        # Check overlap first (highest priority)
        if self._is_in_session(TradingSession.OVERLAP, current_time):
            return TradingSession.OVERLAP

        # Check other sessions
        for session in [TradingSession.LONDON, TradingSession.NEW_YORK, TradingSession.ASIAN]:
            if self._is_in_session(session, current_time):
                return session

        return TradingSession.OFF_HOURS

    def _is_in_session(self, session: TradingSession, current_time: time) -> bool:
        """Check if time is within session."""
        start, end = self.SESSION_TIMES[session]
        return start <= current_time < end

    def update(self, candle: Candle) -> Optional[SessionData]:
        """
        Update session data with new candle.

        Returns SessionData if session changed, None otherwise.
        """
        session = self.get_current_session(candle.timestamp)
        date_str = candle.timestamp.strftime("%Y-%m-%d")
        session_key = f"{session.value}_{date_str}"

        # Check if session changed
        session_changed = self._current_session != session
        self._current_session = session

        # Get or create session data
        if session_key not in self._sessions:
            self._sessions[session_key] = SessionData(
                session=session,
                date=date_str,
                open_price=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                candle_count=1,
                is_active=True,
                started_at=candle.timestamp,
            )
        else:
            data = self._sessions[session_key]
            data.high = max(data.high, candle.high)
            data.low = min(data.low, candle.low)
            data.close = candle.close
            data.volume += candle.volume
            data.candle_count += 1
            data.tick_count += 1

        # Update derived values
        data = self._sessions[session_key]
        data.range = data.high - data.low
        data.body = abs(data.close - data.open)
        data.body_ratio = data.body / data.range if data.range > 0 else 0

        return data if session_changed else None

    def get_session_data(
        self,
        session: TradingSession,
        date_str: str | None = None,
    ) -> SessionData | None:
        """Get data for a specific session."""
        if date_str is None:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")

        session_key = f"{session.value}_{date_str}"
        return self._sessions.get(session_key)

    def get_today_sessions(self) -> list[SessionData]:
        """Get all sessions for today."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return [
            data for key, data in self._sessions.items()
            if data.date == today
        ]

    def is_session_active(self, session: TradingSession) -> bool:
        """Check if a session is currently active."""
        current = self.get_current_session()
        return current == session

    def get_session_stats(self, days: int = 7) -> dict:
        """Get session statistics for the last N days."""
        from datetime import timedelta

        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        stats = {}
        for session in TradingSession:
            if session == TradingSession.OFF_HOURS:
                continue

            sessions = [
                data for data in self._sessions.values()
                if data.session == session and data.date >= cutoff
            ]

            if sessions:
                avg_range = sum(s.range for s in sessions) / len(sessions)
                avg_volume = sum(s.volume for s in sessions) / len(sessions)
                avg_body_ratio = sum(s.body_ratio for s in sessions) / len(sessions)

                stats[session.value] = {
                    "session_count": len(sessions),
                    "avg_range": round(avg_range, 2),
                    "avg_volume": round(avg_volume, 2),
                    "avg_body_ratio": round(avg_body_ratio, 2),
                }
            else:
                stats[session.value] = {
                    "session_count": 0,
                    "avg_range": 0,
                    "avg_volume": 0,
                    "avg_body_ratio": 0,
                }

        return stats
