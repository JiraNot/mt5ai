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

- Binance gateway disconnected repeatedly
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
from math import floor

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

    # Floor to volume step so broker rounding cannot exceed the risk budget.
    volume = floor(volume / symbol_info.volume_step) * symbol_info.volume_step

    # Reject if the broker minimum would exceed the risk budget; otherwise cap max.
    if volume < symbol_info.min_volume:
        minimum_risk = symbol_info.min_volume * sl_distance * symbol_info.contract_size
        if minimum_risk > risk_amount:
            return 0.0
        volume = symbol_info.min_volume
    volume = min(symbol_info.max_volume, volume)

    return volume
```

## Binance DEMO Limits

- Runtime `entry_min_score` controls candidate triage, AI Council, and Risk Engine confidence together. DEMO can use 50–90; the Risk Engine remains the final authority.
- `max_open_positions` maps to concurrent open positions and does not change `max_trades_per_day`.
- Binance order quantity is additionally capped by available Testnet margin, configured leverage, and the selected margin-utilization ceiling. Quantity is floored to the exchange market-lot step.
- Runtime volume and RSI switches are read by CHoCH+OB and Breakout Retest momentum confirmation. Disabling them removes only those optional confirmations; it does not bypass stop, RR, daily loss, exposure, or position limits.
