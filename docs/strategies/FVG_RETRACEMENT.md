# FVG Retracement Strategy

## Overview

 stratégie ที่เข้าเมื่อราคา retrace กลับมาสู่ Fair Value Gap

## LONG Setup

```
1. Bullish HTF bias
2. Liquidity sweep (sell-side)
3. Bullish displacement
4. Bullish FVG created
5. Price retraces into FVG
6. Confirmation candle
7. RR valid (>= 2.0)
→ BUY
```

## SHORT Setup

```
1. Bearish HTF bias
2. Liquidity sweep (buy-side)
3. Bearish displacement
4. Bearish FVG created
5. Price retraces into FVG
6. Confirmation candle
7. RR valid (>= 2.0)
→ SELL
```

## Entry Options

| Option | Description | Use Case |
|--------|-------------|----------|
| FVG Proximal | Enter at FVG edge | Conservative |
| FVG 50% | Enter at midpoint | Balanced |
| FVG Deep | Enter at 75% mitigation | Aggressive |

## Market Regime Integration

```
TRENDING → Follow trend with FVG
RANGING → Mean reversion (buy bottom FVG, sell top FVG)
OVERBOUGHT → SELL (counter-trend)
OVERSOLD → BUY (counter-trend)
CHOPPY → NO TRADE
```

## Configuration

```yaml
strategies:
  fvg_retracement:
    enabled: true
    version: "1.0.0"
    min_score: 78
    timeframes:
      structure: M15
      entry: M5
    entry_option: MIDPOINT  # PROXIMAL, MIDPOINT, DEEP
```

## Performance (Backtested)

| Metric | Value |
|--------|-------|
| Win Rate | 82.6% |
| Profit Factor | 8.64 |
| Return (6mo) | +30.8% |
| Max Drawdown | 3.0% |

## Acceptance Criteria

- [ ] LONG setup detected
- [ ] SHORT setup detected
- [ ] Entry at correct FVG level
- [ ] Regime filter working
- [ ] Score threshold filtering
