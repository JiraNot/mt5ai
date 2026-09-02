# Liquidity Sweep Strategy

## Overview

策略ที่เข้าเมื่อเกิด liquidity sweep — ราคาทะลุระดับ liquidity แล้วกลับตัว

## LONG Setup (Sell-Side Sweep)

```
1. Identify Equal Lows / Swing Lows (sell-side liquidity)
2. Price sweeps below level
3. Close back above level
4. Bullish CHoCH or displacement
5. Bullish FVG formed
6. Retracement into FVG/OB
7. RR valid
→ BUY
```

## SHORT Setup (Buy-Side Sweep)

```
1. Identify Equal Highs / Swing Highs (buy-side liquidity)
2. Price sweeps above level
3. Close back below level
4. Bearish CHoCH or displacement
5. Bearish FVG formed
6. Retracement into FVG/OB
7. RR valid
→ SELL
```

## Sweep Strength

```python
class SweepStrength(BaseModel):
    penetration: Decimal  # How far beyond level
    reclaim_speed: int  # 0-100, how quickly price returned
    displacement: int  # 0-100, momentum after sweep
    score: int  # 0-100
```

## Configuration

```yaml
strategies:
  liquidity_sweep:
    enabled: true
    version: "1.0.0"
    min_score: 75
    min_penetration_atr: 0.05
    require_displacement: true
```

## Acceptance Criteria

- [ ] Sell-side sweep detected
- [ ] Buy-side sweep detected
- [ ] Sweep strength calculated
- [ ] CHoCH confirmation working
- [ ] FVG detection after sweep
