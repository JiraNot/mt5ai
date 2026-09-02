"""Trading session detection — London, New York, Asian, Overlap."""

from __future__ import annotations

from datetime import datetime, timezone

from src.core.config import settings


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' to (hour, minute)."""
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


def get_current_session(now: datetime | None = None) -> str:
    """
    Determine which trading session is currently active.

    Returns: "asian", "london", "new_york", "overlap", or "off"
    """
    if now is None:
        now = datetime.now(timezone.utc)

    hour = now.hour
    minute = now.minute
    current_minutes = hour * 60 + minute

    sess = settings.sessions

    london_start_h, london_start_m = _parse_time(sess.london_start)
    london_end_h, london_end_m = _parse_time(sess.london_end)
    ny_start_h, ny_start_m = _parse_time(sess.new_york_start)
    ny_end_h, ny_end_m = _parse_time(sess.new_york_end)

    london_start = london_start_h * 60 + london_start_m
    london_end = london_end_h * 60 + london_end_m
    ny_start = ny_start_h * 60 + ny_start_m
    ny_end = ny_end_h * 60 + ny_end_m

    in_london = london_start <= current_minutes < london_end
    in_ny = ny_start <= current_minutes < ny_end

    if in_london and in_ny:
        return "overlap"
    elif in_london:
        return "london"
    elif in_ny:
        return "new_york"
    elif current_minutes < london_start:
        return "asian"
    else:
        return "off"


def is_preferred_session(session: str | None = None) -> bool:
    """Check if current session is in the preferred list."""
    if session is None:
        session = get_current_session()
    return session in settings.sessions.preferred_sessions


def get_session_times(session: str) -> tuple[str, str]:
    """Get start/end times for a session."""
    sess = settings.sessions
    times = {
        "london": (sess.london_start, sess.london_end),
        "new_york": (sess.new_york_start, sess.new_york_end),
        "overlap": (sess.new_york_start, sess.london_end),
        "asian": ("00:00", sess.london_start),
    }
    return times.get(session, ("00:00", "00:00"))
