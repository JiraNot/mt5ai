# Market Regime Engine

## Overview

Market Regime ระบุสภาวะตลาดปัจจุบันเพื่อให้ Strategy เลือก approach ที่เหมาะสม

## Classification

```python
class MarketRegime(Enum):
    STRONG_UPTREND = "STRONG_UPTREND"
    MODERATE_UPTREND = "MODERATE_UPTREND"
    STRONG_DOWNTREND = "STRONG_DOWNTREND"
    MODERATE_DOWNTREND = "MODERATE_DOWNTREND"
    RANGING = "RANGING"
    CHOPPY = "CHOPPY"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
```

## Detection Features

```
1. ADX (Average Directional Index)
   - ADX > 40: Strong trend
   - ADX 25-40: Moderate trend
   - ADX < 25: Weak/no trend

2. ATR Percentile
   - > 80th: High volatility
   - 20-80th: Normal
   - < 20th: Low volatility

3. Choppiness Index
   - > 61.8: Choppy (don't trade!)
   - < 38.2: Trending

4. Structure Analysis
   - HH/HL sequence: Uptrend
   - LH/LL sequence: Downtrend
   - Mixed: Range
```

## Trading Rules by Regime

| Regime | Strategy | Action |
|--------|----------|--------|
| Strong Uptrend | Trend following | BUY pullbacks |
| Strong Downtrend | Trend following | SELL rallies |
| Ranging | Mean reversion | Buy bottom, sell top |
| Choppy | **NO TRADE** | Stay out! |
| High Volatility | Reduced size | Trade with caution |
| Low Volatility | Wait | No clear direction |

## Output

```python
class RegimeResult(BaseModel):
    regime: MarketRegime
    confidence: float  # 0-1
    adx: float
    atr_percentile: float
    choppiness: float
    is_tradable: bool
```

## Acceptance Criteria

- [ ] ADX calculation working
- [ ] ATR percentile working
- [ ] Choppiness index working
- [ ] Regime classification accurate
- [ ] Choppy market filter working
- [ ] Integration with strategy working
