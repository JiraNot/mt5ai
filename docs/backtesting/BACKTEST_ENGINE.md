# Backtest Engine

## Overview

Backtest Engine ต้องใช้ domain logic เดียวกับ Live — เปลี่ยนเพียง Data Provider และ Execution Adapter

## Architecture

```
Historical Data
    ↓
Market Structure
    ↓
Strategy
    ↓
Candidate
    ↓
Risk
    ↓
Execution Simulation
    ↓
Trade
    ↓
Metrics
```

## Components

```python
class BacktestEngine:
    def __init__(
        self,
        data_provider: HistoricalDataProvider,
        execution_adapter: SimulatedExecutionAdapter,
        strategies: List[TradingStrategy],
        risk_engine: RiskEngine,
    ):
        ...
    
    async def run(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> BacktestResult:
        ...
```

## Configuration

```yaml
backtesting:
  spread_model: VARIABLE
  commission_per_lot: 7.0
  slippage_pips: 1.0
  start_balance: 10000
  currency: USD
```

## Candle-by-Candle Processing

```
For each closed candle:
    1. Update MarketContext
    2. Run Structure Engine
    3. Run Strategy.detect()
    4. If candidate found:
        a. Run AI.score()
        b. Run Risk.evaluate()
        c. If approved: Execute simulated order
    5. Monitor open positions
    6. Check SL/TP hits
    7. Record trade events
```

## Acceptance Criteria

- [ ] Uses same domain logic as live
- [ ] Spread model working
- [ ] Commission model working
- [ ] Slippage model working
- [ ] Position simulation working
- [ ] Metrics calculated correctly
- [ ] Results reproducible
