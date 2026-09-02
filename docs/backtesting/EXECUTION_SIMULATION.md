# Execution Simulation

## Overview

จำลองการ execute order ใน backtest

## Models

### Spread Model

```python
class SpreadModel(Enum):
    FIXED = "FIXED"         # Constant spread
    VARIABLE = "VARIABLE"   # Based on ATR
    HISTORICAL = "HISTORICAL"  # Use actual spread data
```

### Commission Model

```python
class CommissionModel:
    per_lot: Decimal  # Commission per lot
    per_trade: Decimal  # Fixed per trade
```

### Slippage Model

```python
class SlippageModel:
    fixed_pips: int
    random_slippage: bool
    max_slippage_pips: int
```

## Fill Simulation

### Normal Fill

```
Entry price = Signal price + slippage
```

### SL/TP Hit

```
ถ้า candle เดียวแตะทั้ง SL และ TP:

Option 1: Pessimistic fill (SL hit)
Option 2: Use lower timeframe data
Option 3: Use tick data if available

MVP: Use pessimistic fill
```

### Partial Fill

```
ถ้า volume ไม่พอ:
  Fill what's available
  Log partial fill event
```

## Acceptance Criteria

- [ ] Spread applied correctly
- [ ] Commission deducted correctly
- [ ] Slippage applied correctly
- [ ] SL/TP pessimistic fill working
- [ ] Partial fill handling
