# Scoring Engine

## Overview

Scoring Engine คำนวณ Rule Score 0-100 สำหรับทุก Trade Candidate

## Scoring Method

```
base_score = 50

+ Positive Evidence
- Negative Evidence

Final Score = clamp(0, 100, base + sum(evidence))
```

## Positive Evidence

| Evidence | Score | Description |
|----------|-------|-------------|
| HTF_ALIGNED | +15 | Higher TF confirms direction |
| LIQUIDITY_SWEEP | +20 | Liquidity sweep occurred |
| BULLISH_CHOCH / BEARISH_CHOCH | +20 | CHoCH confirmed |
| STRONG_DISPLACEMENT | +15 | Strong momentum candle |
| ORDER_BLOCK | +10 | Fresh order block present |
| FVG_PRESENT | +10 | Fair value gap present |
| OB_FVG_OVERLAP | +10 | OB and FVG overlap |
| DISCOUNT_ZONE | +5 | Price in discount zone |
| PREFERRED_SESSION | +5 | Trading in preferred session |

## Negative Evidence

| Evidence | Score | Description |
|----------|-------|-------------|
| HTF_CONFLICT | -25 | Higher TF opposes direction |
| HIGH_SPREAD | -20 | Spread above threshold |
| NEWS_EVENT | -30 | Major news approaching |
| WEAK_DISPLACEMENT | -10 | Weak momentum |
| CHOPPY_REGIME | -50 | Market in choppy regime |
| AGAINST_TREND | -15 | Counter-trend setup |

## Evidence Schema

```python
class Evidence(BaseModel):
    code: str
    score: int
    timeframe: Optional[str] = None
    description: Optional[str] = None
```

## Output

```python
class ScoringResult(BaseModel):
    rule_score: int  # 0-100
    evidence: List[Evidence]
    warnings: List[str]
```

## Acceptance Criteria

- [ ] Base score = 50
- [ ] Positive evidence adds correctly
- [ ] Negative evidence subtracts correctly
- [ ] Final score clamped to 0-100
- [ ] Evidence list complete
