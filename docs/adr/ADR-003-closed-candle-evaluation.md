# ADR-003: Closed Candle Strategy Evaluation

## Status

Accepted

## Context

ต้องตัดสินใจว่า Strategy ควร evaluation candle ที่กำลัง forming หรือเฉพาะ closed candles

## Decision

MVP: **CLOSED CANDLES ONLY**

Strategy ห้ามวิเคราะห์ candle ที่ยังไม่ปิดเป็น default

## Rationale

### ข้อดี

1. **No Repaint**: Candle ที่ปิดแล้วจะไม่เปลี่ยน
2. **Deterministic**: ผลลัพธ์ consistent
3. **Backtest Accuracy**: จำลองได้เหมือน live
4. **Reduced Ambiguity**: ไม่ต้องเดาว่า candle จะปิดยังไง

### ข้อเสีย

1. **Delayed Entry**: ต้องรอ candle ปิด
2. **Missed Moves**: บางครั้ง price ไปไกลแล้ว

## Consequences

- Strategy ได้รับ candles ที่ปิดแล้วเท่านั้น
- Backtest ใช้ logic เดียวกับ live
- ไม่มี repaint issues
- Entry อาจช้ากว่า 1-2 candles

## Future Consideration

```
สามารถเพิ่ม realtime strategy ในอนาคตได้
แต่ต้อง flag ว่าเป็น "unconfirmed candle evaluation"
และต้อง test แยกจาก closed candle strategy
```

## Alternatives Considered

- **Real-time (tick-by-tick)**: เร็วแต่ backtest ยาก, repaint risk
- **Hybrid**: Closed + realtime (เพิ่ม complexity)
