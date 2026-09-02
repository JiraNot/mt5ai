# Execution Engine

## Overview

Execution Engine รับเฉพาะ **ApprovedOrderIntent** จาก Risk Engine — ไม่รับ raw Candidate

## Input

```python
class OrderIntent(BaseModel):
    candidate_id: str
    symbol: str
    direction: Direction
    volume: Decimal
    order_type: OrderType  # MARKET, LIMIT, STOP
    price: Optional[Decimal]
    stop_loss: Decimal
    take_profit: Decimal
    risk_decision_id: str
    execution_key: str  # Idempotency key
```

## Pre-Flight Check

ก่อน order ทุกครั้ง:

```
[ ] MT5 connected
[ ] Account matches config
[ ] Trading allowed
[ ] Symbol tradable
[ ] Market open
[ ] Spread valid
[ ] Candidate not expired
[ ] No duplicate (execution_key check)
[ ] Risk approval valid
[ ] Price deviation acceptable
```

Fail หนึ่งข้อ → **DO NOT EXECUTE**

## Order State Machine

```
CREATED
    ↓
VALIDATED
    ↓
SUBMITTED
    ↓
FILLED
    ↓
ACTIVE
    ↓
PARTIAL (optional)
    ↓
CLOSED

Error states:
REJECTED
EXPIRED
CANCELLED
FAILED
```

## Idempotency

```python
execution_key = f"{candidate_id}_{execution_version}"
```

ป้องกัน retry แล้วเปิดหลาย order

## Initial SL Requirement

**ห้ามให้ position ค้างโดยไม่มี SL เป็นสภาวะปกติ**

ทุก Market Order ต้องส่ง SL ไปพร้อมหรือทันทีหลัง fill

## Configuration

```yaml
execution:
  mode: PAPER
  max_price_deviation_pips: 5
  require_sl: true
  duplicate_protection: true
  execution_timeout_seconds: 30
```

## Acceptance Criteria

- [ ] Pre-flight checks working
- [ ] Order state machine complete
- [ ] Idempotency working
- [ ] SL always set
- [ ] Duplicate protection working
- [ ] Timeout handling working
