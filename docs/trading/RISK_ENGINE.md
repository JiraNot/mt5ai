# Risk Engine

## Authority

**Risk Engine has final authority.**

No Strategy or AI can override Risk Engine decisions.

## Inputs

```
TradeCandidate
AccountState
PortfolioState
SymbolInfo
```

## Outputs

```
RiskDecision
```

## RiskDecision Schema

```json
{
  "approved": "boolean",
  "risk_percent": "number",
  "risk_amount": "number",
  "position_size": "number",
  "calculated_sl_distance": "number",
  "projected_rr": "number",
  "reasons": ["string"]
}
```

## Absolute Risk Rules (MVP Defaults)

| Rule | Default | Range |
|------|---------|-------|
| Risk per trade | 0.25% | 0.1% - 1% |
| Max daily loss | 1.5% | 0.5% - 3% |
| Max weekly loss | 4% | 2% - 6% |
| Max concurrent positions | 2 | 1 - 5 |
| Max trades per day | 5 | 3 - 10 |
| Max consecutive losses | 3 | 2 - 5 |
| Minimum RR | 2.0 | 1.5 - 3.0 |

**All configurable via YAML.**

## Risk Checks

### 1. Daily Loss Limit

```
realized_loss + open_position_worst_case_risk > daily_limit
→ NO NEW ENTRY
```

### 2. Consecutive Loss Protection

```
consecutive_losses >= threshold
→ PAUSE NEW ENTRY
→ Reset on: next session or manual resume
```

### 3. Position Sizing

```python
risk_amount = account_equity * risk_per_trade
position_size = risk_amount / (sl_distance * contract_size)
```

**Must use real broker specifications:**
- tick_value
- tick_size
- contract_size
- volume_step
- currency conversion

### 4. Minimum RR Check

```
projected_rr < min_rr
→ REJECT
```

### 5. Spread Filter

```
current_spread > max_spread
→ REJECT
```

### 6. Session Filter

```
session not in preferred_sessions
→ REJECT
```

## Kill Switch

### Triggers

- MT5 disconnected repeatedly
- Data stale
- Database unavailable
- Unexpected account
- Abnormal spread
- Daily DD exceeded
- Weekly DD exceeded
- Duplicate trade detected
- Execution inconsistency

### Levels

```
WARNING → Log only
PAUSE_NEW_ENTRIES → Stop new trades
EMERGENCY_STOP → Close all positions
```

## Daily Lock

When daily risk limit is reached:

```
NO NEW ENTRY
```

System still:
- Monitors open positions
- Manages SL/TP
- Logs events

## Position Size Calculation

```python
def calculate_position_size(
    balance: float,
    risk_percent: float,
    sl_distance: float,
    symbol_info: SymbolInfo
) -> float:
    """
    Calculate position size using real broker specifications.

    Returns: Volume in lots
    """
    risk_amount = balance * risk_percent

    # Use real tick value
    tick_value = symbol_info.tick_value
    tick_size = symbol_info.tick_size

    # Calculate pip value
    pip_value = tick_value * (1 / tick_size)

    # Calculate position size
    volume = risk_amount / (sl_distance * pip_value * symbol_info.contract_size)

    # Round to volume step
    volume = round(volume / symbol_info.volume_step) * symbol_info.volume_step

    # Clamp to min/max
    volume = max(symbol_info.min_volume, min(symbol_info.max_volume, volume))

    return volume
```
