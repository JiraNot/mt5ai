"""MT5 connection manager with auto-reconnect."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from src.core.config import settings
from src.core.exceptions import MT5ConnectionError, MT5OrderError
from src.core.types import (
    AccountInfo,
    Candle,
    Direction,
    OrderRequest,
    OrderResult,
    OrderType,
    Position,
    Tick,
    TradingMode,
)

logger = logging.getLogger(__name__)

# Try to import MetaTrader5 — may not be available on non-Windows
try:
    import MetaTrader5 as mt5

    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 package not available. MT5 features will be mocked.")


class MT5Connection:
    """
    Manages connection to MetaTrader 5 terminal.

    Features:
    - Auto-connect / reconnect
    - OHLCV data fetching
    - Tick data
    - Order execution
    - Position management
    - Account info

    When MT5 is not available (e.g., non-Windows), operates in mock mode.
    """

    def __init__(self) -> None:
        self._connected = False
        self._mock_mode = not MT5_AVAILABLE
        self._last_error: Optional[str] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def mock_mode(self) -> bool:
        return self._mock_mode

    async def connect(self) -> bool:
        """
        Initialize connection to MT5 terminal.

        Returns True if successful, False otherwise.
        """
        if self._mock_mode:
            logger.info("MT5 running in mock mode (package not available)")
            self._connected = True
            return True

        try:
            if not mt5.initialize(
                login=settings.mt5.login,
                password=settings.mt5.password,
                server=settings.mt5.server,
                timeout=settings.mt5.timeout,
            ):
                error = mt5.last_error()
                self._last_error = str(error)
                logger.error(f"MT5 initialization failed: {error}")
                return False

            self._connected = True
            account_info = mt5.account_info()
            if account_info:
                logger.info(
                    f"MT5 connected: {account_info.login} @ {account_info.server} "
                    f"(balance: {account_info.balance:.2f} {account_info.currency})"
                )
            return True

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"MT5 connection error: {e}")
            return False

    async def disconnect(self) -> None:
        """Shutdown MT5 connection."""
        if self._mock_mode:
            self._connected = False
            return

        mt5.shutdown()
        self._connected = False
        logger.info("MT5 disconnected")

    async def reconnect(self) -> bool:
        """Attempt to reconnect to MT5."""
        logger.info("Attempting MT5 reconnection...")
        await self.disconnect()
        await asyncio.sleep(2)  # Brief delay before reconnect
        return await self.connect()

    def _ensure_connected(self) -> None:
        """Raise if not connected."""
        if not self._connected:
            raise MT5ConnectionError("Not connected to MT5")

    # ─── Market Data ──────────────────────────────────────────────────────────

    async def get_ohlcv(
        self, symbol: str, timeframe: str, count: int = 500, start: datetime | None = None
    ) -> list[Candle]:
        """
        Fetch OHLCV data from MT5.

        Args:
            symbol: Trading symbol (e.g., "XAUUSD")
            timeframe: Timeframe string (e.g., "M5", "H1")
            count: Number of candles to fetch
            start: Start datetime (None = from present backwards)

        Returns:
            List of Candle objects
        """
        if self._mock_mode:
            return self._mock_ohlcv(symbol, timeframe, count)

        self._ensure_connected()

        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }

        if timeframe not in tf_map:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, count)
        if rates is None or len(rates) == 0:
            logger.warning(f"No OHLCV data returned for {symbol} {timeframe}")
            return []

        candles = []
        for rate in rates:
            candle = Candle(
                timestamp=datetime.fromtimestamp(rate["time"]),
                open=rate["open"],
                high=rate["high"],
                low=rate["low"],
                close=rate["close"],
                volume=rate["tick_volume"],
            )
            candles.append(candle)

        return candles

    async def get_current_price(self, symbol: str) -> Tick:
        """Get current bid/ask tick."""
        if self._mock_mode:
            return Tick(
                timestamp=datetime.utcnow(),
                bid=2350.00,
                ask=2350.25,
            )

        self._ensure_connected()

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5ConnectionError(f"Failed to get tick for {symbol}")

        return Tick(
            timestamp=datetime.fromtimestamp(tick.time),
            bid=tick.bid,
            ask=tick.ask,
            last=tick.last,
            volume=tick.volume,
        )

    async def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        """Get symbol trading conditions."""
        if self._mock_mode:
            return {
                "digits": 2,
                "point": 0.01,
                "spread": 25,
                "volume_min": 0.01,
                "volume_max": 100.0,
                "volume_step": 0.01,
            }

        self._ensure_connected()

        info = mt5.symbol_info(symbol)
        if info is None:
            raise MT5ConnectionError(f"Failed to get symbol info for {symbol}")

        return {
            "digits": info.digits,
            "point": info.point,
            "spread": info.spread,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_contract_size": info.trade_contract_size,
            "margin_initial": info.margin_initial,
        }

    # ─── Account ──────────────────────────────────────────────────────────────

    async def get_account_info(self) -> AccountInfo:
        """Get current account information."""
        if self._mock_mode:
            return AccountInfo(
                login=99999,
                name="Mock Account",
                server="MockServer",
                balance=10000.00,
                equity=10000.00,
                margin=0.0,
                free_margin=10000.00,
                margin_level=0.0,
                profit=0.0,
                currency="USD",
                leverage=100,
                mode=TradingMode.PAPER,
            )

        self._ensure_connected()

        info = mt5.account_info()
        if info is None:
            raise MT5ConnectionError("Failed to get account info")

        return AccountInfo(
            login=info.login,
            name=info.name,
            server=info.server,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.free_margin,
            margin_level=info.margin_level,
            profit=info.profit,
            currency=info.currency,
            leverage=info.leverage,
        )

    # ─── Orders ───────────────────────────────────────────────────────────────

    async def send_order(self, request: OrderRequest) -> OrderResult:
        """
        Send an order to MT5.

        Args:
            request: OrderRequest with all order details

        Returns:
            OrderResult with success status and details
        """
        if self._mock_mode:
            return OrderResult(
                success=True,
                ticket=12345678,
                price=request.price or 2350.00,
                volume=request.volume,
            )

        self._ensure_connected()

        # Get current price if not specified
        if request.price is None:
            tick = await self.get_current_price(request.symbol)
            price = tick.ask if request.direction == Direction.BUY else tick.bid
        else:
            price = request.price

        mt5_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": request.symbol,
            "volume": request.volume,
            "type": (
                mt5.ORDER_TYPE_BUY
                if request.direction == Direction.BUY
                else mt5.ORDER_TYPE_SELL
            ),
            "price": price,
            "sl": request.sl,
            "tp": request.tp,
            "magic": request.magic,
            "comment": request.comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
            "deviation": request.deviation,
        }

        result = mt5.order_send(mt5_request)
        if result is None:
            error = mt5.last_error()
            return OrderResult(
                success=False,
                error_code=error[0] if error else -1,
                error_message=str(error),
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                success=False,
                error_code=result.retcode,
                error_message=result.comment,
            )

        return OrderResult(
            success=True,
            ticket=result.order,
            price=result.price,
            volume=result.volume,
        )

    async def modify_position(
        self, ticket: int, sl: float | None = None, tp: float | None = None
    ) -> OrderResult:
        """Modify SL/TP of an existing position."""
        if self._mock_mode:
            return OrderResult(success=True, ticket=ticket)

        self._ensure_connected()

        position = mt5.positions_get(ticket=ticket)
        if position is None or len(position) == 0:
            return OrderResult(
                success=False, error_message=f"Position {ticket} not found"
            )

        pos = position[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": sl if sl is not None else pos.sl,
            "tp": tp if tp is not None else pos.tp,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error = result.comment if result else "Unknown error"
            return OrderResult(success=False, error_message=error)

        return OrderResult(success=True, ticket=ticket)

    async def close_position(self, ticket: int) -> OrderResult:
        """Close a specific position."""
        if self._mock_mode:
            return OrderResult(success=True, ticket=ticket)

        self._ensure_connected()

        position = mt5.positions_get(ticket=ticket)
        if position is None or len(position) == 0:
            return OrderResult(
                success=False, error_message=f"Position {ticket} not found"
            )

        pos = position[0]
        close_type = (
            mt5.ORDER_TYPE_SELL
            if pos.type == mt5.ORDER_TYPE_BUY
            else mt5.ORDER_TYPE_BUY
        )
        tick = mt5.symbol_info_tick(pos.symbol)
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": settings.mt5.deviation,
            "magic": settings.mt5.magic,
            "comment": "close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error = result.comment if result else "Unknown error"
            return OrderResult(success=False, error_message=error)

        return OrderResult(success=True, ticket=ticket, price=result.price)

    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        """Get all open positions, optionally filtered by symbol."""
        if self._mock_mode:
            return []

        self._ensure_connected()

        if symbol:
            raw_positions = mt5.positions_get(symbol=symbol)
        else:
            raw_positions = mt5.positions_get()

        if raw_positions is None:
            return []

        positions = []
        for pos in raw_positions:
            positions.append(
                Position(
                    ticket=pos.ticket,
                    symbol=pos.symbol,
                    direction=(
                        Direction.BUY if pos.type == mt5.ORDER_TYPE_BUY else Direction.SELL
                    ),
                    volume=pos.volume,
                    open_price=pos.price_open,
                    current_price=pos.price_current,
                    sl=pos.sl,
                    tp=pos.tp,
                    profit=pos.profit,
                    swap=pos.swap,
                    commission=pos.commission,
                    magic=pos.magic,
                    open_time=datetime.fromtimestamp(pos.time),
                    comment=pos.comment,
                )
            )

        return positions

    def _mock_ohlcv(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        """Generate mock OHLCV data for testing."""
        import random

        base_price = 2350.0 if "XAU" in symbol else 1.10000
        candles = []
        now = datetime.utcnow()

        for i in range(count):
            open_price = base_price + random.uniform(-5, 5)
            close_price = open_price + random.uniform(-3, 3)
            high_price = max(open_price, close_price) + random.uniform(0, 2)
            low_price = min(open_price, close_price) - random.uniform(0, 2)

            candles.append(
                Candle(
                    timestamp=now,
                    open=round(open_price, 2),
                    high=round(high_price, 2),
                    low=round(low_price, 2),
                    close=round(close_price, 2),
                    volume=random.randint(100, 1000),
                )
            )
            base_price = close_price

        return candles
