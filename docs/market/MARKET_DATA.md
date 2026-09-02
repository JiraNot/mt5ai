# Market Data Engine

## Responsibilities

- MT5 data acquisition (candles, ticks, spread)
- Historical data loading
- Multi-timeframe candle cache
- New candle detection
- Symbol specification retrieval

## Interface

```python
class MarketDataEngine:
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime
    ) -> List[Candle]:
        ...
    
    def get_latest_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int
    ) -> List[Candle]:
        ...
    
    def get_tick(self, symbol: str) -> Tick:
        ...
    
    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        ...
    
    def get_spread(self, symbol: str) -> int:
        ...
```

## Candle Finalization Rule

**CLOSED CANDLES ONLY** (default for MVP)

```
10:00 candle
10:05 candle closes
→ process
```

ห้าม Strategy วิเคราะห์ candle ที่ยังไม่ปิดเป็น default เพื่อลด repaint และ ambiguity

## Multi-Timeframe Cache

```
XAUUSD:M1
XAUUSD:M5
XAUUSD:M15
XAUUSD:H1
XAUUSD:H4
```

- Update เฉพาะ candle ใหม่
- Cache invalidation บน new candle detection
- Thread-safe access

## Data Schema

```python
class Candle(BaseModel):
    symbol: str
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    tick_volume: int = 0
    real_volume: int = 0
    spread: int = 0
```

## Spread Tracking

```python
class SpreadMonitor:
    def get_current_spread(self, symbol: str) -> int
    def get_spread_percentile(self, symbol: str, lookback: int) -> float
    def is_spread_abnormal(self, symbol: str, multiplier: float = 3.0) -> bool
```

## Session Clock

```
ASIA:      00:00 - 08:00 UTC
LONDON:    07:00 - 16:00 UTC
NEW_YORK:  12:00 - 21:00 UTC
OVERLAP:   12:00 - 16:00 UTC
```

## Acceptance Criteria

- [ ] H1/M15/M5 synchronized
- [ ] Closed candles processed once only
- [ ] Spread tracking functional
- [ ] Session detection working
