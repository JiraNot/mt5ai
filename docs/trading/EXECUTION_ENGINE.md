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
[ ] Binance gateway connected
[ ] Account matches config
[ ] Trading allowed
[ ] Symbol tradable
[ ] Market open
[ ] Spread valid
[ ] Candidate not expired
[x] No duplicate (execution_key check, including Binance client-order recovery)
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

## Binance Testnet DEMO Execution

- DEMO must use `BINANCE_MODE=testnet` and the official `testnet.binancefuture.com` host. Missing or invalid credentials block execution and remain visible; DEMO must not silently switch to Paper.
- Reject unsupported symbols, Hedge Mode, untradable contracts, stale SL/TP brackets, and quantities outside exchange lot, tick, and minimum-notional filters before opening a position.
- Set Isolated margin and configured leverage before entry, then cap quantity by both Risk Engine size and available Testnet margin.
- Market entry requests use `newOrderRespType=RESULT` so fill price and executed quantity are available for the journal.
- Place `STOP_MARKET` and `TAKE_PROFIT_MARKET` close-position orders through `POST /fapi/v1/algoOrder`; `/fapi/v1/order` no longer accepts conditional protective orders.
- If the server-side SL cannot be installed, submit a reduce-only market close immediately and surface an emergency error if that close also fails. A TP failure can proceed only when the server-side SL is active.
- Reconcile active algo orders with positions. Position modification replaces protection by placing the replacement first, then canceling the old algo order. Close orders are reduce-only, report success only after the requested quantity is confirmed, and remove stale close-position algo orders after a full close.
- This describes implementation only, not a successful exchange fill. DEMO acceptance still requires an observed Testnet entry with its broker-side SL.
