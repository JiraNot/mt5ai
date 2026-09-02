# ADR-004: Risk Engine Final Authority

## Status

Accepted

## Context

ต้องตัดสินใจว่าใครมี authority สูงสุดในการ approve/reject trades

## Decision

**Risk Engine มี Authority สูงสุดเสมอ**

ไม่มี Strategy หรือ AI ใดสามารถ override Risk Engine ได้

## Rationale

### ข้อดี

1. **Safety**: ป้องกัน catastrophic loss
2. **Consistency**: Risk rules ไม่เปลี่ยนตามอารมณ์
3. **Auditability**: ทุก decision มีเหตุผล
4. **Compliance**: พร้อมสำหรับ regulation

### ข้อเสีย

1. **Over-conservative**: บางครั้งอาจ miss good trades
2. **Rigidity**: ไม่สามารถ override ได้แม้จำเป็น

## Decision Flow

```
Strategy
    ↓
AI (optional reject)
    ↓
Risk Engine (final authority)
    ↓
Execution
```

## Authority Hierarchy

```
Risk Engine > AI > Strategy
```

## Risk Engine Can:

```
- Reject any trade
- Reduce position size
- Limit daily exposure
- Activate kill switch
- Override AI recommendation
```

## Risk Engine Cannot:

```
- Be bypassed by any layer
- Be disabled without manual intervention
- Be overridden by AI
```

## Consequences

- ทุก order ต้องผ่าน Risk Engine
- Risk rules configurable แต่ enforceable
- Kill switch ทำงานตลอด
- ไม่มี backdoor

## Alternatives Considered

- **AI has authority**: อันตรายเกินไป, black box risk
- **Strategy has authority**: ไม่มี risk control
- **Manual approval**: ไม่ scalable
