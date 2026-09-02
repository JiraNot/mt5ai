# Fair Value Gap (FVG)

## Overview

FVG เกิดขึ้นเมื่อมี gap ระหว่าง candle 3 ตัว แสดงถึง imbalance ของราคา

## Detection

### Bullish FVG

```
Candle 1 High < Candle 3 Low

Gap:
  lower = Candle 1 High
  upper = Candle 3 Low
```

### Bearish FVG

```
Candle 1 Low > Candle 3 High

Gap:
  lower = Candle 3 High
  upper = Candle 1 Low
```

## Output

```python
class FairValueGap(BaseModel):
    symbol: str
    timeframe: str
    direction: Direction  # BULLISH, BEARISH
    upper_price: Decimal
    lower_price: Decimal
    mid_price: Decimal
    created_at: datetime
    initial_size: Decimal
    size_atr: Decimal  # Size in ATR units
    mitigation_percent: Decimal = 0
    status: FVGStatus = FVGStatus.ACTIVE
    version: str = "1.0.0"
```

## FVG States

| Status | Description |
|--------|-------------|
| ACTIVE | Not yet mitigated |
| PARTIALLY_MITIGATED | Price entered FVG zone |
| FILLED | Price filled entire FVG |
| INVALIDATED | Price closed beyond FVG |

## Mitigation Levels

```
0%: Untouched
25%: Price entered FVG
50%: Price reached midpoint
75%: Mostly filled
100%: Fully filled
```

## Configuration

```yaml
fvg:
  min_size_atr: 0.10      # Minimum gap size in ATR
  max_mitigation_percent: 50  # Maximum mitigation before invalid
```

## Filter

```
Gap Size / ATR >= min_size_atr
```

## Acceptance Criteria

- [ ] Bullish FVG detected correctly
- [ ] Bearish FVG detected correctly
- [ ] Mitigation tracking works
- [ ] Status transitions working
- [ ] Size filter functional
