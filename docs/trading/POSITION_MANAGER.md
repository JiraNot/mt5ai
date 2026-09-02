# Position Manager

## Overview

Position Manager ดูแล position ที่เปิดอยู่ — TP, SL, Break-even, Trailing, Partial Close

## Responsibilities

```
1. Monitor open positions
2. TP handling (fixed TP hit)
3. SL handling (fixed SL hit)
4. Break-even move
5. Trailing stop
6. Partial close
7. Time-based exit
8. Invalidation exit
```

## MVP Features

```yaml
position_management:
  break_even_enabled: true
  break_even_trigger_rr: 1.0
  trailing_enabled: false
  trailing_type: FIXED
  trailing_distance_atr: 1.0
  partial_close_enabled: false
  time_exit_hours: 24
```

## Break-even Logic

```
When unrealized P&L >= BE trigger:
  Move SL to entry price + buffer
  
buffer = spread + small profit
```

## Trailing Stop (Future)

```
FIXED: Trail by fixed pips
ATR: Trail by ATR multiple
STRUCTURE: Trail to next swing point
```

## Partial Close (Future)

```
TP1: Close 50% at 1R
TP2: Close 25% at 2R
TP3: Trail remaining 25%
```

## Time Exit

```
If position open > time_exit_hours:
  Close at market
  Log reason: TIME_EXIT
```

## Acceptance Criteria

- [ ] Fixed SL/TP working
- [ ] Break-even move working
- [ ] Time exit working
- [ ] Position monitoring active
- [ ] Trade event logging
