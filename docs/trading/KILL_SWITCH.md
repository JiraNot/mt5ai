# Kill Switch

## Overview

Kill Switch หยุดระบบเมื่อเกิดสถานการณ์อันตราย

## Trigger Conditions

```
1. MT5 disconnected repeatedly
2. Data stale (> 5 minutes)
3. Database unavailable
4. Unexpected account
5. Abnormal spread (> 3x normal)
6. Daily drawdown exceeded
7. Weekly drawdown exceeded
8. Duplicate trade detected
9. Execution inconsistency
10. Manual emergency stop
```

## Levels

```python
class KillSwitchLevel(Enum):
    WARNING = "WARNING"  # Log alert, continue
    PAUSE_NEW_ENTRIES = "PAUSE_NEW_ENTRIES"  # No new trades
    EMERGENCY_STOP = "EMERGENCY_STOP"  # Close all positions
```

## Configuration

```yaml
kill_switch:
  enabled: true
  mt5_disconnect_threshold: 3
  stale_data_seconds: 300
  abnormal_spread_multiplier: 3.0
  daily_dd_action: PAUSE_NEW_ENTRIES
  weekly_dd_action: EMERGENCY_STOP
```

## State Management

```python
class KillSwitch:
    level: KillSwitchLevel = KillSwitchLevel.WARNING
    triggered_at: Optional[datetime] = None
    trigger_reason: Optional[str] = None
    
    def trigger(self, level, reason):
        ...
    
    def reset(self):
        # Only manual reset allowed
        ...
    
    def is_trading_allowed(self) -> bool:
        return self.level == KillSwitchLevel.WARNING
```

## Important Rules

```
1. LIVE trading must be disabled by default
2. Kill switch can only be reset manually
3. EMERGENCY_STOP closes all positions
4. All triggers logged with audit trail
```

## Acceptance Criteria

- [ ] All trigger conditions detected
- [ ] Level escalation working
- [ ] Trading blocked when active
- [ ] Manual reset required
- [ ] Audit trail complete
