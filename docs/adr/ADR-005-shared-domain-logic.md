# ADR-005: Shared Live/Backtest Domain Logic

## Status

Accepted

## Context

ต้องตัดสินใจว่า Backtest และ Live ใช้ code base เดียวกันหรือแยกกัน

## Decision

**Backtest และ Live ใช้ Domain Logic เดียวกัน**

เปลี่ยนเพียง Data Provider และ Execution Adapter

## Rationale

### ข้อดี

1. **Consistency**: Backtest ผลลัพธ์เหมือน live behavior
2. **Maintainability**: แก้ logic ที่เดียว
3. **Testing**: ทดสอบ logic ได้ในทุก mode
4. **Confidence**: ถ้า backtest ดี, live ก็ควรดี

### ข้อเสีย

1. **Coupling**: Live code ต้อง test ดี
2. **Complexity**: Adapter pattern เพิ่ม abstraction

## Architecture

```python
# Domain Logic (shared)
class StrategyEngine:
    def detect(self, context: MarketContext) -> List[TradeCandidate]:
        ...

class RiskEngine:
    def evaluate(self, candidate: TradeCandidate) -> RiskDecision:
        ...

# Adapters (different)
class LiveDataProvider:  # MT5
    def get_candles(self, ...) -> List[Candle]:
        ...

class BacktestDataProvider:  # Historical
    def get_candles(self, ...) -> List[Candle]:
        ...

class LiveExecutionAdapter:  # Real orders
    def execute(self, intent: OrderIntent) -> Order:
        ...

class SimulatedExecutionAdapter:  # Simulated
    def execute(self, intent: OrderIntent) -> Order:
        ...
```

## Consequences

- Strategy code ใช้ร่วมกัน
- Risk engine ใช้ร่วมกัน
- Market structure engine ใช้ร่วมกัน
- เปลี่ยนเฉพาะ adapter layer

## What Changes Between Modes

| Component | Live | Backtest |
|-----------|------|----------|
| Data Provider | MT5 real-time | Historical CSV/DB |
| Execution | Real orders | Simulated |
| Position | Real positions | Simulated |
| Spread | Real spread | Model spread |
| Slippage | Real slippage | Model slippage |

## What Stays the Same

```
- Strategy detection logic
- Scoring engine
- Risk evaluation
- Position sizing calculation
- Market structure analysis
- Trade journal logging
```

## Alternatives Considered

- **Separate codebases**: aintenance nightmare, bugs from divergence
- **Shared but with flags**: Messy, hard to test
