"""SQLAlchemy ORM models for the Freebuff Trading Platform."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class OHLCV(Base):
    """OHLCV candle data (TimescaleDB hypertable)."""
    __tablename__ = "ohlcv"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(5), nullable=False)
    ts = Column(DateTime, nullable=False, index=True)
    open = Column(Numeric(12, 5), nullable=False)
    high = Column(Numeric(12, 5), nullable=False)
    low = Column(Numeric(12, 5), nullable=False)
    close = Column(Numeric(12, 5), nullable=False)
    volume = Column(Numeric(15, 2), default=0)


class StructureDetection(Base):
    """Market structure detections (swing, BOS, CHoCH, FVG, OB, liquidity)."""
    __tablename__ = "structure_detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(5), nullable=False)
    ts = Column(DateTime, nullable=False, index=True)
    detection_type = Column(String(30), nullable=False)  # swing_high, swing_low, bos, choch, fvg, order_block, liquidity_sweep
    direction = Column(String(5))  # BUY/SELL/NULL
    price = Column(Numeric(12, 5))
    upper_price = Column(Numeric(12, 5))
    lower_price = Column(Numeric(12, 5))
    strength = Column(Integer, default=0)
    mitigated = Column(Boolean, default=False)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class SetupLog(Base):
    """Every candidate setup (traded + skipped + rejected)."""
    __tablename__ = "setup_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(5), nullable=False)
    strategy_id = Column(String(50), nullable=False, index=True)
    direction = Column(String(5), nullable=False)
    rule_score = Column(Integer, nullable=False)
    ai_score = Column(Integer)
    combined_score = Column(Integer)
    decision = Column(String(10), nullable=False, index=True)  # TRADED/SKIPPED/REJECTED
    entry_price = Column(Numeric(12, 5))
    stop_loss = Column(Numeric(12, 5))
    take_profit_1 = Column(Numeric(12, 5))
    take_profit_2 = Column(Numeric(12, 5))
    rr_ratio = Column(Numeric(5, 2))
    confluences = Column(Text, default="[]")
    risk_flags = Column(Text, default="[]")
    rejection_reason = Column(Text)
    outcome_r = Column(Numeric(5, 2))
    outcome_pips = Column(Numeric(8, 2))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    trades = relationship("Trade", back_populates="setup")


class Trade(Base):
    """Executed trades."""
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    setup_id = Column(Integer, ForeignKey("setup_log.id"))
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(5), nullable=False)
    volume = Column(Numeric(8, 4), nullable=False)
    entry_price = Column(Numeric(12, 5), nullable=False)
    sl = Column(Numeric(12, 5), nullable=False)
    tp1 = Column(Numeric(12, 5), nullable=False)
    tp2 = Column(Numeric(12, 5))
    exit_price = Column(Numeric(12, 5))
    exit_time = Column(DateTime)
    profit = Column(Numeric(12, 2), default=0)
    commission = Column(Numeric(10, 2), default=0)
    swap = Column(Numeric(10, 2), default=0)
    net_profit = Column(Numeric(12, 2), default=0)
    outcome_r = Column(Numeric(5, 2))
    outcome_pips = Column(Numeric(8, 2))
    status = Column(String(15), nullable=False, default="OPEN")
    magic = Column(Integer)
    comment = Column(Text)
    open_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    setup = relationship("SetupLog", back_populates="trades")


class DailyRisk(Base):
    """Daily risk tracking."""
    __tablename__ = "daily_risk"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(DateTime, nullable=False, unique=True)
    total_pnl = Column(Numeric(12, 2), default=0)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    max_drawdown = Column(Numeric(12, 2), default=0)
    circuit_breaker = Column(Boolean, default=False)
    notes = Column(Text)


class AccountSnapshot(Base):
    """Periodic account snapshots."""
    __tablename__ = "account_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    balance = Column(Numeric(12, 2), nullable=False)
    equity = Column(Numeric(12, 2), nullable=False)
    margin = Column(Numeric(12, 2), default=0)
    free_margin = Column(Numeric(12, 2), default=0)
    open_positions = Column(Integer, default=0)
    daily_pnl = Column(Numeric(12, 2), default=0)


class ModelVersion(Base):
    """ML model versions (Phase5+)."""
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(20), nullable=False, unique=True)
    strategy_id = Column(String(50))
    accuracy = Column(Numeric(5, 4))
    precision_score = Column(Numeric(5, 4))
    recall = Column(Numeric(5, 4))
    f1_score = Column(Numeric(5, 4))
    sharpe_ratio = Column(Numeric(5, 2))
    max_drawdown = Column(Numeric(5, 2))
    training_samples = Column(Integer)
    model_path = Column(Text)
    config = Column(Text, default="{}")
    deployed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Database Setup ───────────────────────────────────────────────────────────

def get_engine(database_url: str):
    """Create async SQLAlchemy engine."""
    return create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
    )


def get_session_factory(engine):
    """Create async session factory."""
    return sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
