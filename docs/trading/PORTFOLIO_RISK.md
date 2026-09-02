# Portfolio Risk

## Overview

Portfolio Risk ดูแล exposure รวมของทุก position

## Metrics

```
Total Exposure: Sum of all position values
Long Exposure: Sum of long positions
Short Exposure: Sum of short positions
Net Exposure: Long - Short
Correlated Exposure: Exposure to correlated symbols
```

## Limits

```yaml
risk:
  max_open_positions: 2
  max_symbol_exposure: 1  # Max positions per symbol
  max_correlated_exposure: 2  # Max correlated exposure
```

## Correlation Matrix (Future)

```python
# Example correlation
correlations = {
    ("EURUSD", "GBPUSD"): 0.85,
    ("XAUUSD", "USDJPY"): -0.45,
    ("US100", "US500"): 0.95,
}
```

## Daily Risk Tracking

```python
class DailyRiskRecord:
    date: date
    starting_balance: Decimal
    ending_balance: Decimal
    daily_pnl: Decimal
    realized_loss: Decimal
    open_position_risk: Decimal
    trades_count: int
    wins: int
    losses: int
    consecutive_losses: int
    max_drawdown: Decimal
    risk_used_percent: Decimal
    kill_switch_active: bool
```

## Acceptance Criteria

- [ ] Exposure calculation working
- [ ] Position limit enforcement
- [ ] Daily risk tracking
- [ ] Correlation check (basic)
