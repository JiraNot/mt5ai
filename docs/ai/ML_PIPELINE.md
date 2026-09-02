# ML Pipeline

## Overview

ML Pipeline ฝึก model จาก Trade History เพื่อทำนาย win/loss

## Pipeline Stages

```
1. Dataset Builder
   - Collect TradeCandidates
   - Extract features
   - Label outcomes

2. Feature Pipeline
   - Feature extraction
   - Normalization
   - Train/validation split

3. Model Training
   - Baseline (Rule Score only)
   - Logistic Regression
   - Random Forest
   - LightGBM / XGBoost

4. Model Comparison
   - Accuracy
   - Precision/Recall
   - AUC-ROC
   - Feature importance

5. Model Registry
   - Version control
   - Metric tracking
   - Deployment status
```

## Features

```python
FEATURES = [
    "symbol",
    "strategy",
    "direction",
    "hour",
    "session",
    "day_of_week",
    "htf_bias",
    "market_regime",
    "atr",
    "atr_percentile",
    "spread",
    "swing_distance",
    "choch_strength",
    "bos_strength",
    "displacement_score",
    "fvg_present",
    "fvg_size_atr",
    "fvg_mitigation",
    "ob_present",
    "ob_score",
    "liquidity_sweep",
    "liquidity_type",
    "premium_discount",
    "rr",
    "rule_score",
]
```

## Labels

```python
LABELS = [
    "win",        # 0 or 1
    "loss",       # 0 or 1
    "r_multiple", # Actual R result
    "mfe",        # Maximum Favorable Excursion
    "mae",        # Maximum Adverse Excursion
]
```

## Validation Rules

```
1. ML model MUST beat Rule Score baseline
   If not → DO NOT DEPLOY

2. Walk-forward validation required
   Train: 6 months
   Validate: 2 months
   Test: 2 months

3. Feature importance must be interpretable
```

## Acceptance Criteria

- [ ] Dataset builder working
- [ ] Feature pipeline working
- [ ] Baseline established
- [ ] Models trained and compared
- [ ] Model registry functional
- [ ] Walk-forward validation passing
