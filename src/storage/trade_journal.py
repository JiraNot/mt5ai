"""Trade Journal v2 — logs ALL candidates (traded + rejected + expired).

This is critical for ML training and strategy evaluation.
Every candidate setup is logged, regardless of whether it was traded.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.core.types import StrategyCandidate, AIDecision, RiskDecision

logger = logging.getLogger(__name__)


class CandidateStatus(str, Enum):
    """Status of a trade candidate."""
    CREATED = "CREATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"


class OutcomeStatus(str, Enum):
    """Outcome of a traded candidate."""
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


class TradeCandidate(BaseModel):
    """Complete record of a trade candidate."""

    # Identification
    id: str = Field(default_factory=lambda: f"CAND_{int(datetime.utcnow().timestamp() * 1000)}")
    symbol: str
    strategy: str
    strategy_version: str = "1.0.0"
    direction: str
    timeframe: str = "M15"

    # Setup details
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float] = None
    rr_ratio: float = 0.0

    # Scores
    rule_score: int = 0
    ai_score: int = 0
    ml_score: Optional[float] = None
    combined_score: int = 0

    # Decision
    status: CandidateStatus = CandidateStatus.CREATED
    rejection_reason: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    confluences: list[str] = Field(default_factory=list)

    # Market context
    htf_trend: str = ""
    market_regime: str = ""
    session: str = ""
    spread: float = 0.0

    # Execution
    executed_price: Optional[float] = None
    executed_volume: Optional[float] = None
    executed_at: Optional[datetime] = None
    slippage: float = 0.0

    # Outcome (filled after trade closes)
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: str = ""
    profit: float = 0.0
    r_multiple: float = 0.0
    mfe: float = 0.0  # Maximum Favorable Excursion
    mae: float = 0.0  # Maximum Adverse Excursion
    outcome: OutcomeStatus = OutcomeStatus.PENDING

    # Hypothetical outcome (for rejected trades)
    hypothetical_outcome: Optional[float] = None
    hypothetical_r: Optional[float] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Metadata
    metadata: dict = Field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        data = self.model_dump()
        # Convert datetime to string
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
        return data


class TradeJournal:
    """
    Comprehensive trade journal that logs ALL candidates.

    Key principle: Log everything, even rejected trades.
    This data is invaluable for ML training and strategy evaluation.
    """

    def __init__(self, db_session=None):
        self._candidates: dict[str, TradeCandidate] = {}
        self._db_session = db_session

    def log_candidate(
        self,
        candidate: StrategyCandidate,
        ai_decision: Optional[AIDecision] = None,
        risk_decision: Optional[RiskDecision] = None,
        market_context: dict = None,
    ) -> TradeCandidate:
        """Log a new trade candidate."""

        journal_entry = TradeCandidate(
            symbol=candidate.symbol,
            strategy=candidate.strategy_id,
            direction=candidate.direction.value,
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            take_profit_1=candidate.take_profit_1,
            take_profit_2=candidate.take_profit_2,
            rr_ratio=candidate.rr_ratio,
            rule_score=candidate.rule_score,
            confluences=candidate.confluences,
            risk_flags=candidate.risk_flags,
        )

        # Add AI decision
        if ai_decision:
            journal_entry.ai_score = ai_decision.ai_score
            journal_entry.combined_score = ai_decision.combined_score
            journal_entry.risk_flags.extend(ai_decision.risk_flags)

        # Add risk decision
        if risk_decision:
            if not risk_decision.approved:
                journal_entry.status = CandidateStatus.REJECTED
                journal_entry.rejection_reason = risk_decision.rejection_reason or "Risk rejected"
            else:
                journal_entry.status = CandidateStatus.APPROVED

        # Add market context
        if market_context:
            journal_entry.htf_trend = market_context.get("htf_trend", "")
            journal_entry.market_regime = market_context.get("market_regime", "")
            journal_entry.session = market_context.get("session", "")
            journal_entry.spread = market_context.get("spread", 0.0)

        self._candidates[journal_entry.id] = journal_entry

        logger.info(
            f"Candidate logged: {journal_entry.id} | "
            f"{journal_entry.direction} {journal_entry.symbol} | "
            f"Rule: {journal_entry.rule_score} | AI: {journal_entry.ai_score} | "
            f"Status: {journal_entry.status.value}"
        )

        return journal_entry

    def update_execution(
        self,
        candidate_id: str,
        executed_price: float,
        executed_volume: float,
        slippage: float = 0.0,
    ) -> bool:
        """Update candidate with execution details."""
        candidate = self._candidates.get(candidate_id)
        if not candidate:
            return False

        candidate.executed_price = executed_price
        candidate.executed_volume = executed_volume
        candidate.executed_at = datetime.utcnow()
        candidate.slippage = slippage
        candidate.status = CandidateStatus.EXECUTED
        candidate.updated_at = datetime.utcnow()

        return True

    def update_outcome(
        self,
        candidate_id: str,
        exit_price: float,
        exit_reason: str,
        profit: float,
        r_multiple: float,
        mfe: float = 0.0,
        mae: float = 0.0,
    ) -> bool:
        """Update candidate with trade outcome."""
        candidate = self._candidates.get(candidate_id)
        if not candidate:
            return False

        candidate.exit_price = exit_price
        candidate.exit_time = datetime.utcnow()
        candidate.exit_reason = exit_reason
        candidate.profit = profit
        candidate.r_multiple = r_multiple
        candidate.mfe = mfe
        candidate.mae = mae

        # Determine outcome
        if profit > 0:
            candidate.outcome = OutcomeStatus.WIN
        elif profit < 0:
            candidate.outcome = OutcomeStatus.LOSS
        else:
            candidate.outcome = OutcomeStatus.BREAKEVEN

        candidate.updated_at = datetime.utcnow()

        logger.info(
            f"Trade outcome: {candidate_id} | "
            f"{candidate.outcome.value} | "
            f"PnL: ${profit:.2f} | R: {r_multiple:.2f}"
        )

        return True

    def update_hypothetical(
        self,
        candidate_id: str,
        hypothetical_r: float,
        hypothetical_outcome: str = "",
    ) -> bool:
        """Update rejected candidate with hypothetical outcome."""
        candidate = self._candidates.get(candidate_id)
        if not candidate:
            return False

        candidate.hypothetical_r = hypothetical_r
        candidate.hypothetical_outcome = hypothetical_outcome
        candidate.updated_at = datetime.utcnow()

        return True

    def expire_candidate(self, candidate_id: str, reason: str = "Expired") -> bool:
        """Mark a candidate as expired."""
        candidate = self._candidates.get(candidate_id)
        if not candidate:
            return False

        candidate.status = CandidateStatus.EXPIRED
        candidate.rejection_reason = reason
        candidate.updated_at = datetime.utcnow()

        return True

    def get_candidate(self, candidate_id: str) -> TradeCandidate | None:
        """Get candidate by ID."""
        return self._candidates.get(candidate_id)

    def get_candidates_by_status(self, status: CandidateStatus) -> list[TradeCandidate]:
        """Get all candidates with a specific status."""
        return [c for c in self._candidates.values() if c.status == status]

    def get_candidates_by_strategy(self, strategy: str) -> list[TradeCandidate]:
        """Get all candidates for a specific strategy."""
        return [c for c in self._candidates.values() if c.strategy == strategy]

    def get_statistics(self) -> dict:
        """Get comprehensive statistics."""
        total = len(self._candidates)
        approved = len([c for c in self._candidates.values() if c.status == CandidateStatus.APPROVED])
        rejected = len([c for c in self._candidates.values() if c.status == CandidateStatus.REJECTED])
        executed = len([c for c in self._candidates.values() if c.status == CandidateStatus.EXECUTED])
        expired = len([c for c in self._candidates.values() if c.status == CandidateStatus.EXPIRED])

        # Outcome statistics
        winners = len([c for c in self._candidates.values() if c.outcome == OutcomeStatus.WIN])
        losers = len([c for c in self._candidates.values() if c.outcome == OutcomeStatus.LOSS])
        total_trades = winners + losers
        win_rate = winners / total_trades * 100 if total_trades > 0 else 0

        total_pnl = sum(c.profit for c in self._candidates.values())
        avg_r = sum(c.r_multiple for c in self._candidates.values() if c.outcome != OutcomeStatus.PENDING) / max(1, total_trades)

        # False reject analysis
        false_rejects = len([
            c for c in self._candidates.values()
            if c.status == CandidateStatus.REJECTED and c.hypothetical_r and c.hypothetical_r > 0
        ])

        return {
            "total_candidates": total,
            "approved": approved,
            "rejected": rejected,
            "executed": executed,
            "expired": expired,
            "total_trades": total_trades,
            "winners": winners,
            "losers": losers,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_r": round(avg_r, 2),
            "false_rejects": false_rejects,
            "approval_rate": round(approved / total * 100, 1) if total > 0 else 0,
        }

    def export_for_ml(self) -> list[dict]:
        """Export all candidates as feature vectors for ML training."""
        features = []
        for candidate in self._candidates.values():
            if candidate.status in (CandidateStatus.EXECUTED, CandidateStatus.REJECTED):
                features.append({
                    "symbol": candidate.symbol,
                    "strategy": candidate.strategy,
                    "direction": candidate.direction,
                    "rule_score": candidate.rule_score,
                    "ai_score": candidate.ai_score,
                    "rr_ratio": candidate.rr_ratio,
                    "htf_trend": candidate.htf_trend,
                    "market_regime": candidate.market_regime,
                    "session": candidate.session,
                    "spread": candidate.spread,
                    "confluences": candidate.confluences,
                    "risk_flags": candidate.risk_flags,
                    "outcome": candidate.outcome.value if candidate.outcome else "UNKNOWN",
                    "r_multiple": candidate.r_multiple,
                    "profit": candidate.profit,
                    "mfe": candidate.mfe,
                    "mae": candidate.mae,
                })
        return features
