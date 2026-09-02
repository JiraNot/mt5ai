# Breakout Retest Strategy

## Overview

 stratégie ที่เข้าเมื่อราคา breakout แล้ว retest ระดับเดิม

## LONG Setup

```
1. Identify Resistance / Swing High
2. Strong candle close above level
3. Breakout with displacement
4. Price retests breakout level
5. Level holds (support)
6. Bullish rejection candle
7. RR valid (>= 2.0)
→ BUY
```

## SHORT Setup

```
1. Identify Support / Swing Low
2. Strong candle close below level
3. Breakout with displacement
4. Price retests breakout level
5. Level holds (resistance)
6. Bearish rejection candle
7. RR valid (>= 2.0)
→ SELL
```

## Filters

```
REJECT if:
- Breakout too extended (> 2 ATR from level)
- Weak close (body < 50% of range)
- Price closes deeply below breakout zone
- Spread abnormal
- Late retest (> 10 candles)
```

## Configuration

```yaml
strategies:
  breakout_retest:
    enabled: true
    version: "1.0.0"
    min_score: 80
    timeframes:
      structure: M15
      entry: M5
    max_extension_atr: 2.0
    max_retest_candles: 10
```

## Acceptance Criteria

- [ ] LONG breakout detected
- [ ] SHORT breakout detected
- [ ] Retest detection working
- [ ] Extension filter working
- [ ] Rejection candle detection
- [ ] Spread filter working
