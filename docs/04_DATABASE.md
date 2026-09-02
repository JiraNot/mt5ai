# Database Specification

## Overview

ระบบใช้ PostgreSQL สำหรับ Production และ SQLite สำหรับ Development/Testing

## Core Tables

### accounts

```sql
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    broker VARCHAR(100) NOT NULL,
    login VARCHAR(50) NOT NULL,
    server VARCHAR(100),
    currency VARCHAR(10) DEFAULT 'USD',
    created_at TIMESTAMP DEFAULT NOW()
);
```

ไม่เก็บ password plain-text

---

### symbols

```sql
CREATE TABLE symbols (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) UNIQUE NOT NULL,
    digits INTEGER DEFAULT 2,
    point DECIMAL(10,8),
    tick_size DECIMAL(10,8),
    tick_value DECIMAL(10,4),
    contract_size DECIMAL(10,2),
    min_volume DECIMAL(10,4),
    max_volume DECIMAL(10,4),
    volume_step DECIMAL(10,4)
);
```

---

### candles

```sql
CREATE TABLE candles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    open DECIMAL(20,8) NOT NULL,
    high DECIMAL(20,8) NOT NULL,
    low DECIMAL(20,8) NOT NULL,
    close DECIMAL(20,8) NOT NULL,
    tick_volume BIGINT DEFAULT 0,
    real_volume BIGINT DEFAULT 0,
    spread INTEGER DEFAULT 0,
    UNIQUE(symbol, timeframe, timestamp)
);
```

---

### structure_events

```sql
CREATE TABLE structure_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    type VARCHAR(20) NOT NULL,  -- BOS, CHOCH
    direction VARCHAR(10) NOT NULL,  -- BULLISH, BEARISH
    price DECIMAL(20,8) NOT NULL,
    strength INTEGER DEFAULT 0,
    version VARCHAR(20) DEFAULT '1.0.0'
);
```

---

### swing_points

```sql
CREATE TABLE swing_points (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    type VARCHAR(10) NOT NULL,  -- HIGH, LOW
    price DECIMAL(20,8) NOT NULL,
    strength INTEGER DEFAULT 0,
    confirmed BOOLEAN DEFAULT FALSE,
    confirmed_at TIMESTAMP
);
```

---

### fair_value_gaps

```sql
CREATE TABLE fair_value_gaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    upper_price DECIMAL(20,8) NOT NULL,
    lower_price DECIMAL(20,8) NOT NULL,
    mid_price DECIMAL(20,8) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    initial_size DECIMAL(20,8),
    size_atr DECIMAL(10,4),
    mitigation_percent DECIMAL(5,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    -- ACTIVE, PARTIALLY_MITIGATED, FILLED, INVALIDATED
    version VARCHAR(20) DEFAULT '1.0.0'
);
```

---

### order_blocks

```sql
CREATE TABLE order_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    high DECIMAL(20,8) NOT NULL,
    low DECIMAL(20,8) NOT NULL,
    body_high DECIMAL(20,8),
    body_low DECIMAL(20,8),
    created_at TIMESTAMP NOT NULL,
    origin_candle_index INTEGER,
    strength INTEGER DEFAULT 0,
    caused_bos BOOLEAN DEFAULT FALSE,
    caused_choch BOOLEAN DEFAULT FALSE,
    mitigation_percent DECIMAL(5,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    version VARCHAR(20) DEFAULT '1.0.0'
);
```

---

### liquidity_zones

```sql
CREATE TABLE liquidity_zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    type VARCHAR(30) NOT NULL,
    -- SWING_HIGH, SWING_LOW, EQUAL_HIGH, EQUAL_LOW
    -- PDL, PDH, PWL, PWH, SESSION_HIGH, SESSION_LOW
    direction VARCHAR(10) NOT NULL,
    price DECIMAL(20,8) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    swept BOOLEAN DEFAULT FALSE,
    swept_at TIMESTAMP
);
```

---

### trade_candidates

```sql
CREATE TABLE trade_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy VARCHAR(50) NOT NULL,
    strategy_version VARCHAR(20) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    setup_time TIMESTAMP NOT NULL,
    rule_score INTEGER DEFAULT 0,
    entry_min DECIMAL(20,8),
    entry_max DECIMAL(20,8),
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    rr DECIMAL(10,4),
    status VARCHAR(20) DEFAULT 'CREATED',
    -- CREATED, AI_EVALUATED, RISK_EVALUATED, APPROVED
    -- REJECTED, EXPIRED, CANCELLED
    market_context_json JSONB,
    evidence_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### ai_decisions

```sql
CREATE TABLE ai_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES trade_candidates(id),
    provider VARCHAR(50) NOT NULL,  -- RULE, LLM, ML, ENSEMBLE
    model VARCHAR(50),
    model_version VARCHAR(20),
    score INTEGER DEFAULT 0,
    confidence DECIMAL(5,4),
    decision VARCHAR(20) NOT NULL,  -- APPROVE, REJECT, UNCERTAIN
    reason_codes JSONB,
    raw_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### risk_decisions

```sql
CREATE TABLE risk_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES trade_candidates(id),
    approved BOOLEAN NOT NULL,
    risk_percent DECIMAL(5,4),
    risk_amount DECIMAL(20,4),
    position_size DECIMAL(10,4),
    calculated_sl_distance DECIMAL(20,8),
    projected_rr DECIMAL(10,4),
    rejection_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### orders

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES trade_candidates(id),
    risk_decision_id UUID REFERENCES risk_decisions(id),
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    volume DECIMAL(10,4) NOT NULL,
    order_type VARCHAR(20) NOT NULL,  -- MARKET, LIMIT, STOP
    price DECIMAL(20,8),
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    status VARCHAR(20) DEFAULT 'CREATED',
    -- CREATED, VALIDATED, SUBMITTED, FILLED, ACTIVE
    -- PARTIAL, CLOSED, REJECTED, EXPIRED, CANCELLED, FAILED
    mt5_ticket BIGINT,
    filled_price DECIMAL(20,8),
    filled_at TIMESTAMP,
    execution_key VARCHAR(100) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### positions

```sql
CREATE TABLE positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id),
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    volume DECIMAL(10,4) NOT NULL,
    entry_price DECIMAL(20,8) NOT NULL,
    current_price DECIMAL(20,8),
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    unrealized_pnl DECIMAL(20,4) DEFAULT 0,
    realized_pnl DECIMAL(20,4) DEFAULT 0,
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'OPEN',
    -- OPEN, CLOSED, PARTIAL
    mt5_ticket BIGINT
);
```

---

### trades

```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES trade_candidates(id),
    order_id UUID REFERENCES orders(id),
    position_id UUID REFERENCES positions(id),
    symbol VARCHAR(20) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    volume DECIMAL(10,4) NOT NULL,
    entry_price DECIMAL(20,8) NOT NULL,
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    exit_price DECIMAL(20,8),
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    profit DECIMAL(20,4) DEFAULT 0,
    r_multiple DECIMAL(10,4) DEFAULT 0,
    mfe DECIMAL(20,4) DEFAULT 0,  -- Maximum Favorable Excursion
    mae DECIMAL(20,4) DEFAULT 0,  -- Maximum Adverse Excursion
    spread_at_entry INTEGER,
    slippage INTEGER,
    status VARCHAR(20) DEFAULT 'OPEN',
    -- OPEN, CLOSED, CANCELLED
    strategy_version VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### trade_events

```sql
CREATE TABLE trade_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id UUID REFERENCES trades(id),
    event_type VARCHAR(30) NOT NULL,
    -- OPENED, CLOSED, SL_HIT, TP_HIT, BE_MOVED, TRAILING_MOVED
    -- PARTIAL_CLOSE, MANUAL_CLOSE, TIME_EXIT, INVALIDATION_EXIT
    price DECIMAL(20,8),
    volume DECIMAL(10,4),
    pnl DECIMAL(20,4),
    timestamp TIMESTAMP DEFAULT NOW(),
    details JSONB
);
```

---

### daily_risk_records

```sql
CREATE TABLE daily_risk_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    starting_balance DECIMAL(20,4),
    ending_balance DECIMAL(20,4),
    daily_pnl DECIMAL(20,4) DEFAULT 0,
    realized_loss DECIMAL(20,4) DEFAULT 0,
    open_position_risk DECIMAL(20,4) DEFAULT 0,
    trades_count INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    consecutive_losses INTEGER DEFAULT 0,
    max_drawdown DECIMAL(10,4) DEFAULT 0,
    risk_used_percent DECIMAL(5,4) DEFAULT 0,
    kill_switch_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### account_snapshots

```sql
CREATE TABLE account_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    balance DECIMAL(20,4) NOT NULL,
    equity DECIMAL(20,4) NOT NULL,
    margin DECIMAL(20,4) DEFAULT 0,
    free_margin DECIMAL(20,4) DEFAULT 0,
    timestamp TIMESTAMP DEFAULT NOW()
);
```

---

### setup_logs

```sql
CREATE TABLE setup_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    direction VARCHAR(10),
    rule_score INTEGER DEFAULT 0,
    ai_score INTEGER DEFAULT 0,
    decision VARCHAR(20),  -- TRADED, SKIPPED, REJECTED
    reason TEXT,
    hypothetical_outcome_r DECIMAL(10,4),
    timestamp TIMESTAMP DEFAULT NOW(),
    context_json JSONB
);
```

---

### backtests

```sql
CREATE TABLE backtests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy VARCHAR(50) NOT NULL,
    strategy_version VARCHAR(20),
    symbol VARCHAR(20) NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    initial_balance DECIMAL(20,4),
    final_balance DECIMAL(20,4),
    total_trades INTEGER,
    win_rate DECIMAL(5,4),
    profit_factor DECIMAL(10,4),
    max_drawdown DECIMAL(10,4),
    sharpe_ratio DECIMAL(10,4),
    params_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### backtest_trades

```sql
CREATE TABLE backtest_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backtest_id UUID REFERENCES backtests(id),
    trade_id UUID REFERENCES trades(id),
    strategy VARCHAR(50),
    symbol VARCHAR(20),
    direction VARCHAR(10),
    entry_price DECIMAL(20,8),
    exit_price DECIMAL(20,8),
    profit DECIMAL(20,4),
    r_multiple DECIMAL(10,4),
    mfe DECIMAL(20,4),
    mae DECIMAL(20,4),
    opened_at TIMESTAMP,
    closed_at TIMESTAMP
);
```

---

### model_versions

```sql
CREATE TABLE model_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name VARCHAR(100) NOT NULL,
    version VARCHAR(20) NOT NULL,
    model_type VARCHAR(50),  -- RULE, LLM, ML, ENSEMBLE
    metrics_json JSONB,
    artifact_path TEXT,
    status VARCHAR(20) DEFAULT 'STAGING',
    -- STAGING, ACTIVE, ARCHIVED
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Indexes

```sql
CREATE INDEX idx_candles_symbol_tf_ts ON candles(symbol, timeframe, timestamp);
CREATE INDEX idx_structure_events_symbol_ts ON structure_events(symbol, timestamp);
CREATE INDEX idx_trade_candidates_symbol ON trade_candidates(symbol, created_at);
CREATE INDEX idx_trades_strategy ON trades(strategy, created_at);
CREATE INDEX idx_trades_symbol ON trades(symbol, created_at);
CREATE INDEX idx_daily_risk_date ON daily_risk_records(date);
```

## Migration Strategy

使用 Alembic สำหรับ database migration

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```
