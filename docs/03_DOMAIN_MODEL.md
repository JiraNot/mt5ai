# Domain Model

## Core Entities

### Market Data

```
Candle
├── timestamp
├── open
├── high
├── low
├── close
├── volume
└── spread

Tick
├── timestamp
├── bid
├── ask
└── volume
```

### Market Structure

```
SwingPoint
├── timestamp
├── price
├── direction (HIGH/LOW)
├── strength
└── confirmed_at

StructureEvent
├── timestamp
├── type (BOS/CHOCH)
├── direction
├── price
└── strength
```

### SMC Elements

```
FairValueGap
├── timestamp
├── direction
├── upper_price
├── lower_price
├── midpoint
├── size
├── mitigation_percent
└── status (ACTIVE/MITIGATED/FILLED)

OrderBlock
├── timestamp
├── direction
├── high/low
├── body_high/body_low
├── strength
├── caused_bos
├── caused_choch
├── mitigation_percent
└── status

LiquidityZone
├── timestamp
├── type (SWING/EQUAL_HIGH/PREVIOUS_DAY/SESSION)
├── level
├── direction
└── strength
```

### Trading

```
TradeCandidate
├── id
├── strategy_id
├── strategy_version
├── symbol
├── direction
├── entry_zone
├── stop_loss
├── take_profit
├── rr_ratio
├── rule_score
├── evidence[]
├── warnings[]
└── status

Decision
├── candidate_id
├── score
├── confidence
├── decision (APPROVE/REJECT)
├── reason_codes[]
└── risk_flags[]

RiskDecision
├── candidate_id
├── approved
├── risk_percent
├── risk_amount
├── position_size
└── rejection_reason

Order
├── id
├── ticket
├── symbol
├── direction
├── volume
├── price
├── sl
├── tp
├── state
└── events[]

Position
├── id
├── ticket
├── symbol
├── direction
├── entry_price
├── volume
├── sl
├── tp
├── pnl
└── r_multiple

Trade
├── id
├── candidate_id
├── symbol
├── strategy
├── direction
├── entry
├── exit
├── profit
├── r_multiple
├── mfe
└── mae
```

## MarketContext

Central object passed to all strategies:

```
MarketContext
├── symbol
├── timestamp
├── timeframes
├── htf_bias
├── current_price
├── atr
├── volatility
├── market_regime
├── session
├── swings
├── bos_events
├── choch_events
├── active_fvgs
├── active_order_blocks
├── liquidity_zones
├── liquidity_sweeps
└── spread
```

**Rule:** Strategy must never query MT5 directly. Strategy must use MarketContext.

## Lifecycle States

### TradeCandidate

```
CREATED
    ↓
AI_EVALUATED
    ↓
RISK_EVALUATED
    ↓
APPROVED / REJECTED / EXPIRED
```

### Order

```
CREATED
    ↓
VALIDATED
    ↓
SUBMITTED
    ↓
FILLED / FAILED
    ↓
ACTIVE
    ↓
CLOSED
```

### Position

```
OPEN
    ↓
PARTIAL (optional)
    ↓
CLOSED
```
