# Liquidity Engine

## Overview

Liquidity คือระดับราคาที่มี Stop Loss หรือ Buy/Sell orders จำนวนมาก

## Liquidity Sources

### MVP Detection

```
1. Swing High / Swing Low
2. Equal High / Equal Low
3. Previous Day High / Low (PDH/PDL)
4. Session High / Low
```

### Future Detection

```
5. Previous Week High / Low (PWH/PWL)
6. Weekly/Monthly levels
7. Round numbers
8. Volume profile levels
```

## Equal High / Equal Low

```python
# อย่าใช้ราคาต้องเท่ากันเป๊ะ — ใช้ tolerance

equal_level_tolerance_atr: 0.08

# distance <= ATR × tolerance
```

## Liquidity Sweep Detection

### Bullish Sweep (Sell-Side)

```
1. Price trades below Sell-Side Liquidity
2. Close back above level
3. Optional: Bullish displacement follows
```

### Bearish Sweep (Buy-Side)

```
1. Price trades above Buy-Side Liquidity
2. Close back below level
3. Optional: Bearish displacement follows
```

## Output

```python
class LiquiditySweep(BaseModel):
    symbol: str
    timeframe: str
    type: SweepType  # BUY_SIDE, SELL_SIDE
    level: Decimal
    penetration: Decimal  # How far below/above level
    reclaim_strength: int  # 0-100
    score: int  # 0-100
    timestamp: datetime
```

## Configuration

```yaml
liquidity:
  equal_level_tolerance_atr: 0.08
  detect_session_levels: true
  detect_previous_day: true
```

## Acceptance Criteria

- [ ] Swing liquidity detected
- [ ] Equal High/Low detected
- [ ] PDH/PDL detected
- [ ] Session levels detected
- [ ] Liquidity sweep detection working
- [ ] Sweep scoring functional
