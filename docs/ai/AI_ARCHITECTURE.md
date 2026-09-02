# AI Architecture

## Overview

AI V1 ไม่ใช่ executor — AI เป็น **Trade Candidate Evaluator**

## AI Roles

```
Pattern Context Evaluation
+ Setup Quality Scoring
+ Trade Filtering
+ Regime Classification
```

AI ไม่ได้ทำหน้าที่:

```
- Risk Controller
- Order Execution
- Position Management
- SL Emergency Handling
```

## Decision Layers

```
Strategy
    ↓
Rule Candidate (Score 0-100)
    ↓
AI Decision (Score 0-100, optional)
    ↓
Meta Decision (Ensemble)
    ↓
Risk Engine (Final Authority)
```

## Layer Authority

```
Risk > AI > Strategy
```

ไม่มี Layer ใดสามารถ bypass Risk ได้

## AI Types

| Type | Description | Phase |
|------|-------------|-------|
| RULE | Weighted scoring (current) | Phase 10 |
| LLM | LLM context analysis | Phase 10 |
| ML | Machine learning prediction | Phase 11 |
| ENSEMBLE | Combined scoring | Phase 11 |

## Input Schema

```json
{
  "symbol": "XAUUSD",
  "timeframe": "M15",
  "market_regime": "bullish",
  "htf": {
    "H4": "bullish",
    "H1": "bullish"
  },
  "structure": {
    "choch": true,
    "bos": true,
    "last_swing_low": 3321.40,
    "last_swing_high": 3342.10
  },
  "liquidity": {
    "sell_side_sweep": true,
    "buy_side_sweep": false
  },
  "fvg": {
    "exists": true,
    "direction": "bullish",
    "mitigation": 0.42
  },
  "order_block": {
    "exists": true,
    "direction": "bullish"
  },
  "rr": 3.2
}
```

## Output Schema

```json
{
  "decision": "APPROVE",
  "score": 86,
  "confidence": 0.82,
  "risk_flags": [],
  "reason_codes": [
    "HTF_ALIGNMENT",
    "LIQUIDITY_SWEEP",
    "CHOCH_CONFIRMED",
    "OB_FVG_OVERLAP"
  ]
}
```

## Acceptance Criteria

- [ ] Rule-based scoring working
- [ ] Input schema validated
- [ ] Output schema validated
- [ ] Shadow mode functional
- [ ] Decision logged
