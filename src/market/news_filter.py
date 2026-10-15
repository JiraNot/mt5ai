"""Macroeconomic & Crypto High-Impact News Filter.

Guards trading entries against extreme volatility and slippage during
scheduled high-impact economic releases (FOMC, CPI, NFP, GDP, Crypto ETF/SEC decisions).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EconomicEvent:
    """A scheduled economic news release event."""

    name: str
    impact: str  # "HIGH", "MEDIUM", "LOW"
    event_time: datetime
    currency: str = "USD"
    description: str = ""


@dataclass
class NewsFilterResult:
    """Outcome of news window evaluation."""

    is_blocked: bool
    event: EconomicEvent | None = None
    minutes_relative: int = 0
    reason: str = ""


class NewsFilter:
    """Evaluates whether current time falls within a high-impact news blackout window."""

    def __init__(
        self,
        events: list[EconomicEvent] | None = None,
        minutes_before: int | None = None,
        minutes_after: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.enabled = settings.risk.news_filter_enabled if enabled is None else enabled
        self.minutes_before = settings.risk.news_minutes_before if minutes_before is None else minutes_before
        self.minutes_after = settings.risk.news_minutes_after if minutes_after is None else minutes_after
        self._events: list[EconomicEvent] = events or []
        if not self._events:
            self._load_cached_events()

    def add_event(self, event: EconomicEvent) -> None:
        """Add an event to the filter schedule."""
        self._events.append(event)
        self._events.sort(key=lambda e: e.event_time)

    def check_news_window(self, dt: datetime | None = None) -> NewsFilterResult:
        """Check if dt is within blackout window of any high-impact event."""
        if not self.enabled:
            return NewsFilterResult(is_blocked=False, reason="News filter disabled")

        now = dt or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        for event in self._events:
            if event.impact.upper() != "HIGH":
                continue

            event_time = event.event_time
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            window_start = event_time - timedelta(minutes=self.minutes_before)
            window_end = event_time + timedelta(minutes=self.minutes_after)

            if window_start <= now <= window_end:
                diff_minutes = int((event_time - now).total_seconds() / 60)
                if diff_minutes >= 0:
                    status_desc = f"in {diff_minutes} minutes"
                else:
                    status_desc = f"{abs(diff_minutes)} minutes ago"

                reason = (
                    f"High-impact news blackout: '{event.name}' ({event.currency}) release {status_desc}. "
                    f"Trading paused ({self.minutes_before}m before / {self.minutes_after}m after)."
                )
                logger.warning(reason)
                return NewsFilterResult(
                    is_blocked=True,
                    event=event,
                    minutes_relative=diff_minutes,
                    reason=reason,
                )

        return NewsFilterResult(is_blocked=False, reason="No active high-impact news window")

    def get_upcoming_events(self, within_hours: int = 24) -> list[EconomicEvent]:
        """Get high-impact events scheduled within the next N hours."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=within_hours)
        return [
            e for e in self._events
            if e.impact.upper() == "HIGH" and now <= (e.event_time.replace(tzinfo=timezone.utc) if e.event_time.tzinfo is None else e.event_time) <= cutoff
        ]

    def _load_cached_events(self) -> None:
        """Load stored economic events from local JSON file if available."""
        calendar_file = Path("data/economic_calendar.json")
        if not calendar_file.exists():
            return
        try:
            with open(calendar_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("events", []):
                self._events.append(
                    EconomicEvent(
                        name=item["name"],
                        impact=item.get("impact", "HIGH"),
                        event_time=datetime.fromisoformat(item["time"]),
                        currency=item.get("currency", "USD"),
                        description=item.get("description", ""),
                    )
                )
        except Exception as exc:
            logger.warning("Could not parse economic calendar cache: %s", exc)
