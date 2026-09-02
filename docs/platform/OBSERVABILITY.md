# Observability

## Overview

Observability ประกอบด้วย Logging, Metrics, และ Tracing

## Structured Logging

```python
# ทุก Event มี correlation_id
log_entry = {
    "timestamp": "2026-09-02T10:30:00Z",
    "level": "INFO",
    "correlation_id": "abc-123",
    "candidate_id": "cand-456",
    "trade_id": "trade-789",
    "symbol": "XAUUSD",
    "strategy": "choch_order_block",
    "event": "TRADE_OPENED",
    "message": "BUY order filled at 3350.25"
}
```

## Event Types

```
STRUCTURE_DETECTED
SWING_CONFIRMED
BOS_DETECTED
CHOCH_DETECTED
FVG_CREATED
OB_CREATED
SETUP_REJECTED
SETUP_APPROVED
RISK_APPROVED
RISK_REJECTED
ORDER_SUBMITTED
ORDER_FILLED
ORDER_CLOSED
SL_HIT
TP_HIT
KILL_SWITCH_TRIGGERED
```

## Runtime Health Checks

```
- MT5 heartbeat
- Latest tick age
- Latest candle age
- DB heartbeat
- Worker heartbeat
- Execution queue depth
```

## Metrics (Future)

```
- Trade latency
- Signal generation time
- Risk evaluation time
- Order execution time
- System resource usage
```

## Acceptance Criteria

- [ ] Structured logging working
- [ ] Correlation IDs propagated
- [ ] Health checks implemented
- [ ] Log rotation configured
