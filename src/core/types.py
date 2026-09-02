"""Shared data models for the Freebuff Trading Platform."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────────

class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Timeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


class Session(str, Enum):
    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"


class TradingMode(str, Enum):
    PAPER = "paper"
    DEMO = "demo"
    LIVE = "live"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class SetupDecision(str, Enum):
    TRADED = "TRADED"
    SKIPPED = "SKIPPED"
    REJECTED = "REJECTED"


# ─── Market Data ──────────────────────────────────────────────────────────────

class Candle(BaseModel):
    """Single OHLCV candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def total_range(self) -> float:
        return self.high - self.low


class Tick(BaseModel):
    """Real-time tick data."""

    timestamp: datetime
    bid: float
    ask: float
    last: float = 0.0
    volume: float = 0.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


# ─── Market Structure ─────────────────────────────────────────────────────────

class SwingPoint(BaseModel):
    """Detected swing high or low."""

    timestamp: datetime
    price: float
    direction: Direction  # BUY = swing low (support), SELL = swing high (resistance)
    strength: int = Field(ge=1, le=5, default=1)
    timeframe: str = "H1"
    tested: bool = False
    mitigated: bool = False


class MarketStructure(BaseModel):
    """Current structure state for one timeframe."""

    timeframe: str
    trend: Optional[Direction] = None
    bos: Optional[datetime] = None  # Last Break of Structure
    choch: Optional[datetime] = None  # Last Change of Character
    last_swing_high: Optional[SwingPoint] = None
    last_swing_low: Optional[SwingPoint] = None
    liquidity_sweep: bool = False
    premium_discount: str = "neutral"  # premium / discount / neutral


class FairValueGap(BaseModel):
    """Detected Fair Value Gap zone."""

    timestamp: datetime
    direction: Direction
    upper_price: float
    lower_price: float
    timeframe: str
    mitigated_percent: float = 0.0
    market_structure: Optional[str] = None
    valid: bool = True

    @property
    def midpoint(self) -> float:
        return (self.upper_price + self.lower_price) / 2

    @property
    def zone_size(self) -> float:
        return self.upper_price - self.lower_price


class OrderBlock(BaseModel):
    """Detected Order Block zone."""

    timestamp: datetime
    direction: Direction  # BUY = bullish OB, SELL = bearish OB
    upper_price: float
    lower_price: float
    timeframe: str
    strength: int = Field(ge=1, le=5, default=1)
    mitigated: bool = False
    fvg_overlap: bool = False  # Does this OB overlap with an FVG?

    @property
    def midpoint(self) -> float:
        return (self.upper_price + self.lower_price) / 2


# ─── Strategy ─────────────────────────────────────────────────────────────────

class StrategyCandidate(BaseModel):
    """Output from each strategy plugin — a potential trade setup."""

    strategy_id: str
    strategy_name: str
    symbol: str
    timeframe: str
    direction: Direction
    rule_score: int = Field(ge=0, le=100, default=50)

    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    rr_ratio: float = 0.0

    confluences: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Auto-calculate RR if not set."""
        if self.rr_ratio == 0.0 and self.entry_price != self.stop_loss:
            risk = abs(self.entry_price - self.stop_loss)
            reward = abs(self.take_profit_1 - self.entry_price)
            self.rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0


# ─── AI Decision ──────────────────────────────────────────────────────────────

class AIDecision(BaseModel):
    """AI scoring output for a candidate setup."""

    candidate: StrategyCandidate
    ai_score: int = Field(ge=0, le=100, default=0)
    combined_score: int = Field(ge=0, le=100, default=0)
    decision: str = "WAIT"  # BUY / SELL / WAIT / REJECT
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    reasons: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─── Risk Engine ──────────────────────────────────────────────────────────────

class RiskDecision(BaseModel):
    """Risk engine approval or rejection."""

    approved: bool = False
    position_size_lots: float = 0.0
    risk_amount: float = 0.0
    risk_pct: float = 0.0
    adjusted_sl: float = 0.0
    adjusted_tp1: float = 0.0
    adjusted_tp2: Optional[float] = None
    rejection_reason: Optional[str] = None

    daily_loss_remaining: float = 0.0
    trades_today: int = 0
    exposure_current: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─── Execution ────────────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    """Final order to send to MT5."""

    symbol: str
    direction: Direction
    volume: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None  # For limit/stop orders
    sl: float
    tp: float
    magic: int = 20240101
    comment: str = ""
    deviation: int = 10  # Max slippage in points


class OrderResult(BaseModel):
    """Result of an order submission."""

    success: bool
    ticket: Optional[int] = None
    price: Optional[float] = None
    volume: Optional[float] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Position(BaseModel):
    """Live position from MT5."""

    ticket: int
    symbol: str
    direction: Direction
    volume: float
    open_price: float
    current_price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    magic: int = 0
    open_time: datetime = Field(default_factory=datetime.utcnow)
    comment: str = ""


class AccountInfo(BaseModel):
    """MT5 account information."""

    login: int = 0
    name: str = ""
    server: str = ""
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    free_margin: float = 0.0
    margin_level: float = 0.0
    profit: float = 0.0
    currency: str = "USD"
    leverage: int = 0
    mode: TradingMode = TradingMode.PAPER


# ─── Analytics ────────────────────────────────────────────────────────────────

class TradeRecord(BaseModel):
    """Completed trade for journaling."""

    id: Optional[int] = None
    setup_id: Optional[int] = None
    symbol: str
    direction: Direction
    volume: float
    entry_price: float
    sl: float
    tp1: float
    tp2: Optional[float] = None
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    profit: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    net_profit: float = 0.0
    outcome_r: Optional[float] = None
    outcome_pips: Optional[float] = None
    status: PositionStatus = PositionStatus.OPEN
    magic: int = 0
    comment: str = ""
    open_time: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BacktestResult(BaseModel):
    """Results from a backtest run."""

    strategy_id: str
    symbol: str
    period_start: datetime
    period_end: datetime
    total_trades: int = 0
    winners: int = 0
    losers: int = 0
    win_rate: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    expectancy: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    avg_rr_achieved: float = 0.0
    total_pnl_r: float = 0.0
    equity_curve: list[float] = Field(default_factory=list)


class DailyRisk(BaseModel):
    """Daily risk tracking."""

    trade_date: datetime
    total_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    max_drawdown: float = 0.0
    circuit_breaker: bool = False
    notes: str = ""
