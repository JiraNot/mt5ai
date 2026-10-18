"""Trade filters — spread, slippage, news, session, RR checks."""

from __future__ import annotations

import logging
from src.core.config import settings
from src.core.types import StrategyCandidate, AIDecision
from src.market.session_tracker import get_current_session, is_preferred_session
from src.market.spread_monitor import SpreadMonitor

from src.market.news_filter import NewsFilter

logger = logging.getLogger(__name__)


class TradeFilter:
    """
    Pre-trade filters applied before position sizing.
    Each filter returns (passed: bool, reason: str).
    """

    def __init__(
        self,
        spread_monitor: SpreadMonitor | None = None,
        news_filter: NewsFilter | None = None,
    ) -> None:
        self._spread_monitor = spread_monitor
        self._news_filter = news_filter or NewsFilter()

    def check_rr(self, candidate: StrategyCandidate) -> tuple[bool, str | None]:
        """Minimum risk-reward ratio check."""
        if candidate.rr_ratio < settings.risk.min_rr:
            return False, (
                f"RR too low: 1:{candidate.rr_ratio:.1f} "
                f"< minimum 1:{settings.risk.min_rr}"
            )
        return True, None

    def check_session(
        self, session: str | None = None, is_crypto: bool = False
    ) -> tuple[bool, str | None]:
        """Check if trading session is preferred."""
        # 24/7 Crypto markets have no session lockout
        if is_crypto:
            return True, None

        if session is None:
            session = get_current_session()

        if session == "off":
            return False, "Market closed"

        if not is_preferred_session(session):
            if session == "asian":
                return False, f"Asian session — not in preferred list"
        return True, None

    def check_spread(
        self, current_spread: float | None = None, is_crypto: bool = False, is_paper: bool = False
    ) -> tuple[bool, str | None]:
        """Check current spread against limits."""
        if current_spread is None and self._spread_monitor:
            current_spread = self._spread_monitor.get_current_spread()
        if current_spread is None:
            return False, "Spread unavailable"

        max_allowed = settings.risk.max_spread_pips
        if self._spread_monitor and hasattr(self._spread_monitor, "max_spread"):
            max_allowed = max(max_allowed, self._spread_monitor.max_spread)
        if is_crypto and is_paper:
            max_allowed = max(max_allowed, 150.0)

        if current_spread > max_allowed:
            return False, (
                f"Spread {current_spread:.1f} > max {max_allowed:.1f} pips"
            )
        return True, None

    def check_slippage(
        self, expected_price: float, actual_price: float
    ) -> tuple[bool, str | None]:
        """Check if slippage is within tolerance."""
        slippage = abs(expected_price - actual_price)
        max_slip = settings.risk.max_slippage_pips * 0.1  # Convert pips to price

        if slippage > max_slip:
            return False, (
                f"Slippage {slippage:.2f} > max {max_slip:.2f}"
            )
        return True, None

    def check_ai_confidence(
        self, decision: AIDecision, is_paper: bool = False
    ) -> tuple[bool, str | None]:
        """Check if AI confidence meets threshold."""
        min_score = settings.ai.min_combined_score
        # In Paper Mode, use 58 to encourage exploration and continuous learning
        threshold = 58 if is_paper else min_score
        if decision.combined_score < threshold:
            return False, (
                f"AI score {decision.combined_score} < threshold {threshold}"
            )
        return True, None

    def check_news(self, dt: datetime | None = None) -> tuple[bool, str | None]:
        """Check if trading is blocked by a high-impact economic news window."""
        res = self._news_filter.check_news_window(dt)
        if res.is_blocked:
            return False, res.reason
        return True, None

    def check_all(
        self,
        candidate: StrategyCandidate,
        decision: AIDecision | None = None,
        current_spread: float | None = None,
        session: str | None = None,
    ) -> tuple[bool, str | None]:
        """Run all filters. Returns first failure or (True, None)."""
        is_crypto = candidate.symbol.upper().endswith(("USDT", "BUSD", "USDC", "BTC", "ETH"))
        from src.core.runtime_control import get_runtime_trading_mode
        is_paper = get_runtime_trading_mode() == "paper"

        filters = [
            self.check_rr(candidate),
            self.check_session(session, is_crypto=is_crypto),
            self.check_spread(current_spread, is_crypto=is_crypto, is_paper=is_paper),
            self.check_news(candidate.timestamp),
        ]

        if decision:
            filters.append(self.check_ai_confidence(decision, is_paper=is_paper))

        for passed, reason in filters:
            if not passed:
                logger.info(f"Trade filtered: {reason}")
                return False, reason

        return True, None
