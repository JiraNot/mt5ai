"""
Real MT5 Gateway — connects to actual MetaTrader 5 Terminal.

This module handles:
- MT5 connection management
- Account info retrieval
- Symbol specification
- Real order execution (MARKET, LIMIT, STOP)
- Position management
- Order modification (SL/TP)
- Position closing

CRITICAL: All orders go through Risk Engine first.
           This module only executes APPROVED orders.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

logger = logging.getLogger(__name__)


@dataclass
class AccountInfo:
    login: int
    server: str
    name: str
    currency: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int
    profit: float


@dataclass
class SymbolSpec:
    symbol: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    contract_size: float
    min_volume: float
    max_volume: float
    volume_step: float
    trade_contract_size: float


@dataclass
class MT5OrderResult:
    success: bool
    ticket: Optional[int] = None
    price: Optional[float] = None
    volume: Optional[float] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None


class MT5Gateway:
    """
    Real MT5 connection and order execution.
    
    Usage:
        gateway = MT5Gateway()
        gateway.connect()
        
        account = gateway.get_account_info()
        spec = gateway.get_symbol_spec("XAUUSD")
        
        result = gateway.send_market_order(
            symbol="XAUUSD",
            direction="BUY",
            volume=0.01,
            stop_loss=3300.0,
            take_profit=3400.0,
        )
        
        gateway.close_position(ticket)
        gateway.disconnect()
    """

    def __init__(self, path: Optional[str] = None, timeout: int = 10000):
        """
        Initialize MT5 Gateway.
        
        Args:
            path: Path to MT5 terminal64.exe (optional, uses default if None)
            timeout: Connection timeout in milliseconds
        """
        self.path = path
        self.timeout = timeout
        self._connected = False
        self._account_info: Optional[AccountInfo] = None

    def connect(self) -> bool:
        """Connect to MT5 Terminal."""
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 package not installed")
            return False

        kwargs = {"timeout": self.timeout}
        if self.path:
            kwargs["path"] = self.path

        if not mt5.initialize(**kwargs):
            error = mt5.last_error()
            logger.error(f"MT5 initialize failed: {error}")
            return False

        self._connected = True
        self._account_info = None  # Refresh on next query

        info = self.get_account_info()
        if info:
            logger.info(f"MT5 connected: {info.server} | Login: {info.login} | Balance: {info.balance}")
        else:
            logger.warning("MT5 connected but could not read account info")

        return True

    def disconnect(self):
        """Disconnect from MT5 Terminal."""
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 disconnected")

    def is_connected(self) -> bool:
        """Check if connected to MT5."""
        return self._connected

    def get_account_info(self) -> Optional[AccountInfo]:
        """Get current account information."""
        if not self._connected or not MT5_AVAILABLE:
            return None

        info = mt5.account_info()
        if info is None:
            logger.error(f"Failed to get account info: {mt5.last_error()}")
            return None

        self._account_info = AccountInfo(
            login=info.login,
            server=info.server,
            name=info.name,
            currency=info.currency,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.free_margin,
            leverage=info.leverage,
            profit=info.profit,
        )
        return self._account_info

    def get_symbol_spec(self, symbol: str) -> Optional[SymbolSpec]:
        """Get symbol specification from MT5."""
        if not self._connected or not MT5_AVAILABLE:
            return None

        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Failed to get symbol info for {symbol}: {mt5.last_error()}")
            return None

        # Make sure symbol is visible in Market Watch
        if not info.visible:
            mt5.symbol_select(symbol, True)

        return SymbolSpec(
            symbol=info.name,
            digits=info.digits,
            point=info.point,
            tick_size=info.trade_tick_size,
            tick_value=info.trade_tick_value,
            contract_size=info.trade_contract_size,
            min_volume=info.volume_min,
            max_volume=info.volume_max,
            volume_step=info.volume_step,
            trade_contract_size=info.trade_contract_size,
        )

    def get_candles(
        self,
        symbol: str,
        timeframe: int,
        count: int = 100,
    ) -> Optional[List[Dict]]:
        """
        Get candle data from MT5.
        
        Timeframe constants:
            mt5.TIMEFRAME_M1, mt5.TIMEFRAME_M5, mt5.TIMEFRAME_M15
            mt5.TIMEFRAME_H1, mt5.TIMEFRAME_H4, mt5.TIMEFRAME_D1
        """
        if not self._connected or not MT5_AVAILABLE:
            return None

        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            logger.error(f"Failed to get candles: {mt5.last_error()}")
            return None

        candles = []
        for rate in rates:
            candles.append({
                "timestamp": datetime.fromtimestamp(rate["time"]),
                "open": rate["open"],
                "high": rate["high"],
                "low": rate["low"],
                "close": rate["close"],
                "tick_volume": int(rate["tick_volume"]),
                "spread": int(rate["spread"]),
                "real_volume": int(rate.get("real_volume", 0)),
            })

        return candles

    def get_tick(self, symbol: str) -> Optional[Dict]:
        """Get latest tick data."""
        if not self._connected or not MT5_AVAILABLE:
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "time": datetime.fromtimestamp(tick.time),
            "spread": round((tick.ask - tick.bid) / mt5.symbol_info(symbol).point) if mt5.symbol_info(symbol) else 0,
        }

    def get_positions(self) -> List[Dict]:
        """Get all open positions."""
        if not self._connected or not MT5_AVAILABLE:
            return []

        positions = mt5.positions_get()
        if positions is None:
            return []

        result = []
        for pos in positions:
            result.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "direction": "BUY" if pos.type == 0 else "SELL",
                "volume": pos.volume,
                "price_open": pos.price_open,
                "price_current": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "swap": pos.swap,
                "time": datetime.fromtimestamp(pos.time),
                "magic": pos.magic,
                "comment": pos.comment,
            })

        return result

    def send_market_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        stop_loss: float,
        take_profit: float,
        magic: int = 0,
        comment: str = "",
    ) -> MT5OrderResult:
        """
        Send a MARKET order to MT5.
        
        Args:
            symbol: Trading symbol (e.g., "XAUUSD")
            direction: "BUY" or "SELL"
            volume: Lot size
            stop_loss: Stop loss price
            take_profit: Take profit price
            magic: Magic number for identification
            comment: Order comment
        
        Returns:
            MT5OrderResult with success status and details
        """
        if not self._connected or not MT5_AVAILABLE:
            return MT5OrderResult(
                success=False,
                error_code=-1,
                error_message="MT5 not connected",
            )

        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return MT5OrderResult(
                success=False,
                error_code=-2,
                error_message=f"Failed to get tick for {symbol}",
            )

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return MT5OrderResult(
                success=False,
                error_code=-3,
                error_message=f"Failed to get symbol info for {symbol}",
            )

        # Determine order type and price
        if direction.upper() == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        elif direction.upper() == "SELL":
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            return MT5OrderResult(
                success=False,
                error_code=-4,
                error_message=f"Invalid direction: {direction}",
            )

        # Normalize prices to symbol digits
        digits = symbol_info.digits
        price = round(price, digits)
        stop_loss = round(stop_loss, digits)
        take_profit = round(take_profit, digits)

        # Build order request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": 20,  # Max slippage in points
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Send order
        result = mt5.order_send(request)

        if result is None:
            return MT5OrderResult(
                success=False,
                error_code=-5,
                error_message=f"order_send returned None: {mt5.last_error()}",
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                f"Order failed: {result.retcode} | {result.comment} | "
                f"Symbol: {symbol} | {direction} | Volume: {volume}"
            )
            return MT5OrderResult(
                success=False,
                error_code=result.retcode,
                error_message=result.comment,
            )

        logger.info(
            f"Order filled: Ticket={result.order} | {direction} {volume} {symbol} "
            f"@ {result.price} | SL={stop_loss} | TP={take_profit}"
        )

        return MT5OrderResult(
            success=True,
            ticket=result.order,
            price=result.price,
            volume=result.volume,
        )

    def modify_position(
        self,
        ticket: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> MT5OrderResult:
        """Modify SL/TP of an existing position."""
        if not self._connected or not MT5_AVAILABLE:
            return MT5OrderResult(success=False, error_code=-1, error_message="MT5 not connected")

        position = mt5.positions_get(ticket=ticket)
        if not position:
            return MT5OrderResult(success=False, error_code=-2, error_message=f"Position {ticket} not found")

        pos = position[0]
        symbol_info = mt5.symbol_info(pos.symbol)
        digits = symbol_info.digits if symbol_info else 2

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": pos.symbol,
            "sl": round(stop_loss, digits) if stop_loss is not None else pos.sl,
            "tp": round(take_profit, digits) if take_profit is not None else pos.tp,
        }

        result = mt5.order_send(request)

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error_msg = result.comment if result else str(mt5.last_error())
            return MT5OrderResult(success=False, error_code=getattr(result, 'retcode', -1), error_message=error_msg)

        logger.info(f"Position {ticket} modified: SL={request['sl']} TP={request['tp']}")
        return MT5OrderResult(success=True, ticket=ticket)

    def close_position(self, ticket: int) -> MT5OrderResult:
        """Close a specific position."""
        if not self._connected or not MT5_AVAILABLE:
            return MT5OrderResult(success=False, error_code=-1, error_message="MT5 not connected")

        position = mt5.positions_get(ticket=ticket)
        if not position:
            return MT5OrderResult(success=False, error_code=-2, error_message=f"Position {ticket} not found")

        pos = position[0]
        symbol_info = mt5.symbol_info(pos.symbol)
        if symbol_info is None:
            return MT5OrderResult(success=False, error_code=-3, error_message=f"Symbol info not found")

        # Determine close order type
        if pos.type == 0:  # BUY position -> close with SELL
            close_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(pos.symbol).bid
        else:  # SELL position -> close with BUY
            close_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": round(price, symbol_info.digits),
            "deviation": 20,
            "magic": pos.magic,
            "comment": "CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error_msg = result.comment if result else str(mt5.last_error())
            return MT5OrderResult(success=False, error_code=getattr(result, 'retcode', -1), error_message=error_msg)

        logger.info(f"Position {ticket} closed @ {result.price}")
        return MT5OrderResult(success=True, ticket=ticket, price=result.price, volume=result.volume)

    def close_all_positions(self, symbol: Optional[str] = None) -> List[MT5OrderResult]:
        """Close all open positions (optionally filtered by symbol)."""
        positions = self.get_positions()
        results = []

        for pos in positions:
            if symbol and pos["symbol"] != symbol:
                continue
            result = self.close_position(pos["ticket"])
            results.append(result)

        return results

    def move_to_breakeven(self, ticket: int, buffer_points: int = 10) -> MT5OrderResult:
        """Move stop loss to breakeven + buffer."""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return MT5OrderResult(success=False, error_message="Position not found")

        pos = position[0]
        symbol_info = mt5.symbol_info(pos.symbol)
        if not symbol_info:
            return MT5OrderResult(success=False, error_message="Symbol info not found")

        point = symbol_info.point

        if pos.type == 0:  # BUY
            new_sl = pos.price_open + (buffer_points * point)
        else:  # SELL
            new_sl = pos.price_open - (buffer_points * point)

        # Only move if new SL is better than current
        if pos.type == 0 and new_sl <= pos.sl:
            return MT5OrderResult(success=False, error_message="New SL not better than current")
        if pos.type == 1 and new_sl >= pos.sl:
            return MT5OrderResult(success=False, error_message="New SL not better than current")

        return self.modify_position(ticket, stop_loss=new_sl)

    def get_tick_count(self, symbol: str) -> int:
        """Get number of ticks received (for staleness check)."""
        if not self._connected or not MT5_AVAILABLE:
            return 0

        info = mt5.symbol_info(symbol)
        return info.volume_real if info else 0
