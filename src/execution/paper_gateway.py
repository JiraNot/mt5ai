"""Deterministic paper execution wrapper for any venue market-data gateway."""

from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import AsyncIterator

from src.core.config import settings
from src.core.types import AccountInfo, Candle, Deal, Direction, OrderRequest, OrderResult, Position, TradingMode, Tick
from src.market.venue_gateway import VenueGateway


class PaperGateway:
    """Simulate fills while reusing the selected venue's market data."""

    venue = "binance"

    def __init__(self, market: VenueGateway, initial_balance: float | None = None) -> None:
        self._market = market
        self._balance = initial_balance if initial_balance is not None else settings.paper_initial_balance
        self._positions: dict[int, Position] = {}
        self._deals: dict[int, list[Deal]] = {}
        self._execution_keys: dict[str, int] = {}
        self._next_ticket = 1

    @property
    def connected(self) -> bool:
        return self._market.connected

    async def connect(self) -> bool:
        return await self._market.connect()

    async def disconnect(self) -> None:
        await self._market.disconnect()

    async def reconnect(self) -> bool:
        return await self._market.reconnect()

    async def get_ohlcv(self, symbol: str, timeframe: str, count: int = 500, start: datetime | None = None) -> list[Candle]:
        return await self._market.get_ohlcv(symbol, timeframe, count, start)

    async def get_current_price(self, symbol: str) -> Tick:
        return await self._market.get_current_price(symbol)

    async def stream_klines(self, symbol: str, timeframe: str) -> AsyncIterator[tuple[str, Candle, bool]]:
        stream = getattr(self._market, "stream_klines", None)
        if stream is None:
            raise RuntimeError("Selected market gateway does not support streaming")
        async for event in stream(symbol, timeframe):
            yield event

    async def get_symbol_info(self, symbol: str) -> dict:
        return await self._market.get_symbol_info(symbol)

    async def get_account_info(self) -> AccountInfo:
        unrealized = sum(position.profit for position in self._positions.values())
        return AccountInfo(
            login=0, name="Paper Binance", server="paper", balance=self._balance,
            equity=self._balance + unrealized, free_margin=self._balance + unrealized,
            currency="USDT", leverage=1, mode=TradingMode.PAPER,
        )

    async def send_order(self, request: OrderRequest) -> OrderResult:
        if request.execution_key and request.execution_key in self._execution_keys:
            ticket = self._execution_keys[request.execution_key]
            position = self._positions.get(ticket)
            return OrderResult(
                success=position is not None, ticket=ticket,
                price=position.open_price if position else None,
                volume=position.volume if position else None,
                venue=self.venue, status=(OrderResult.model_fields["status"].default),
                error_message="duplicate execution key" if position is None else "duplicate ignored",
                metadata={"duplicate": True},
            )
        if request.volume <= 0 or request.sl <= 0 or request.tp <= 0:
            return OrderResult(success=False, venue=self.venue, error_message="Paper order requires positive volume, SL, and TP")
        tick = await self._market.get_current_price(request.symbol)
        price = request.price or (tick.ask if request.direction == Direction.BUY else tick.bid)
        ticket = self._next_ticket
        self._next_ticket += 1
        now = datetime.now(timezone.utc)
        position = Position(
            ticket=ticket, identifier=ticket, symbol=request.symbol, direction=request.direction,
            volume=request.volume, open_price=price, current_price=price, sl=request.sl, tp=request.tp,
            magic=request.magic, open_time=now, comment=request.comment,
        )
        self._positions[ticket] = position
        self._deals[ticket] = [Deal(
            ticket=ticket * 10, order=ticket, position_id=ticket, time=now,
            entry=0, type=0 if request.direction == Direction.BUY else 1,
            volume=request.volume, price=price, profit=0, symbol=request.symbol,
        )]
        if request.execution_key:
            self._execution_keys[request.execution_key] = ticket
        return OrderResult(
            success=True, ticket=ticket, price=price, volume=request.volume,
            venue=self.venue, external_order_id=str(ticket), metadata={"paper": True},
        )

    async def modify_position(self, ticket: int, sl: float | None = None, tp: float | None = None) -> OrderResult:
        position = self._positions.get(ticket)
        if position is None:
            return OrderResult(success=False, ticket=ticket, venue=self.venue, error_message="Position not found")
        if sl is not None and sl <= 0 or tp is not None and tp <= 0:
            return OrderResult(success=False, ticket=ticket, venue=self.venue, error_message="SL/TP must be positive")
        self._positions[ticket] = position.model_copy(update={"sl": sl or position.sl, "tp": tp or position.tp})
        return OrderResult(success=True, ticket=ticket, venue=self.venue, metadata={"paper": True})

    async def close_position(self, ticket: int) -> OrderResult:
        position = self._positions.get(ticket)
        if position is None:
            return OrderResult(success=False, ticket=ticket, venue=self.venue, error_message="Position not found")
        tick = await self._market.get_current_price(position.symbol)
        exit_price = tick.bid if position.direction == Direction.BUY else tick.ask
        pnl = (exit_price - position.open_price) * position.volume
        if position.direction == Direction.SELL:
            pnl = -pnl
        now = datetime.now(timezone.utc)
        self._deals[ticket].append(Deal(
            ticket=ticket * 10 + 1, order=ticket, position_id=ticket, time=now,
            entry=1, type=1 if position.direction == Direction.BUY else 0,
            volume=position.volume, price=exit_price, profit=pnl, symbol=position.symbol,
        ))
        self._balance += pnl
        self._positions.pop(ticket)
        return OrderResult(success=True, ticket=ticket, price=exit_price, volume=position.volume, venue=self.venue, metadata={"paper": True, "pnl": pnl})

    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        positions = list(self._positions.values())
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        refreshed: list[Position] = []
        for position in positions:
            tick = await self._market.get_current_price(position.symbol)
            current = tick.bid if position.direction == Direction.BUY else tick.ask
            pnl = (current - position.open_price) * position.volume
            if position.direction == Direction.SELL:
                pnl = -pnl
            refreshed.append(position.model_copy(update={"current_price": current, "profit": pnl}))
        for position in refreshed:
            self._positions[position.ticket] = position
        return refreshed

    async def get_position_deals(self, position_id: int) -> list[Deal]:
        return list(self._deals.get(position_id, []))
