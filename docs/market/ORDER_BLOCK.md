# Order Block

## Overview

Order Block (OB) คือ candle สุดท้ายก่อนเกิด displacement ที่ทำให้เกิด BOS หรือ CHoCH

## Detection

### Bullish Order Block

```
1. Bearish candle (close < open)
2. ก่อน bullish displacement
3. Displacement ทำให้เกิด BOS หรือ CHoCH
4. OB = bearish candle ตัวนั้น
```

### Bearish Order Block

```
1. Bullish candle (close > open)
2. ก่อน bearish displacement
3. Displacement ทำให้เกิด BOS หรือ CHoCH
4. OB = bullish candle ตัวนั้น
```

## Output

```python
class OrderBlock(BaseModel):
    symbol: str
    timeframe: str
    direction: Direction  # BULLISH, BEARISH
    high: Decimal
    low: Decimal
    body_high: Decimal
    body_low: Decimal
    created_at: datetime
    origin_candle_index: Optional[int] = None
    strength: int = 0
    caused_bos: bool = False
    caused_choch: bool = False
    mitigation_percent: Decimal = 0
    status: OBStatus = OBStatus.ACTIVE
    version: str = "1.0.0"
```

## Strength Scoring

```
Base: 0

+ Displacement strength: +25
+ Caused CHoCH: +30
+ Caused BOS: +20
+ FVG formed after OB: +15
+ Fresh (not mitigated): +10

Total: 0-100
```

## Invalidation

```
Bullish OB: Close below OB low
Bearish OB: Close above OB high
```

Configurable between wick and close break.

## States

| Status | Description |
|--------|-------------|
| ACTIVE | Untouched |
| PARTIALLY_MITIGATED | Price entered OB zone |
| FILLED | Price filled entire OB |
| INVALIDATED | Price closed beyond OB |

## Acceptance Criteria

- [ ] Bullish OB detected correctly
- [ ] Bearish OB detected correctly
- [ ] Strength scoring works
- [ ] Invalidation detection works
- [ ] Caused BOS/CHoCH tracking works
