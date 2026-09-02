# Architecture

## High-Level Architecture

```
                     ┌─────────────────┐
                     │ MetaTrader 5    │
                     └────────┬────────┘
                              │
                       MT5 Gateway
                              │
                              ▼
                   ┌───────────────────┐
                   │ Market Data       │
                   └─────────┬─────────┘
                             ▼
                   ┌───────────────────┐
                   │ Structure Engine  │
                   └─────────┬─────────┘
                             ▼
                   ┌───────────────────┐
                   │ Feature Engine    │
                   └─────────┬─────────┘
                             ▼
                   ┌───────────────────┐
                   │ Strategy Engine   │
                   └─────────┬─────────┘
                             ▼
                       Candidate Pool
                             │
                             ▼
                   ┌───────────────────┐
                   │ Decision Engine   │
                   └─────────┬─────────┘
                             ▼
                   ┌───────────────────┐
                   │ Risk Engine       │
                   └─────────┬─────────┘
                             ▼
                   ┌───────────────────┐
                   │ Execution Engine  │
                   └─────────┬─────────┘
                             ▼
                         MetaTrader

                              │
                              ▼
                    Journal / Analytics
```

## Layer Authority

```
Risk > AI > Strategy
```

In terms of order authorization:

```
Strategy
   ↓
AI may reject
   ↓
Risk may reject
   ↓
Execution
```

No layer can bypass Risk Engine.

## Core Principles

1. **Deterministic First** — All logic must be reproducible
2. **Data Second** — Decisions based on structured data, not feelings
3. **AI Third** — AI evaluates, doesn't execute
4. **Risk Always First** — Risk Engine has final authority

## Module Structure

```
src/
├── core/           # Types, config, events, logging
├── market/         # MT5 connection, data feed, sessions
├── structure/      # Market structure analysis
├── strategies/     # Strategy plugin system
├── ai/             # AI decision layer
├── risk/           # Risk engine
├── execution/      # Order management
├── storage/        # Database models
├── analytics/      # Backtesting
├── live/           # Live monitoring
└── dashboard/      # UI
```

## Data Flow

1. **Market Data** → Raw OHLCV from MT5
2. **Structure Engine** → Swing, BOS, CHoCH, FVG, OB, Liquidity
3. **Feature Engine** → Extract ML-ready features
4. **Strategy Engine** → Detect setups, score confluences
5. **Candidate Pool** → TradeCandidate objects
6. **Decision Engine** → Rule + AI scoring
7. **Risk Engine** → Validate, position size, approve/reject
8. **Execution Engine** → Send orders to MT5
9. **Position Manager** → Manage open positions
10. **Journal** → Log everything for analytics

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python | MT5 integration, ML ecosystem |
| Database | PostgreSQL | Reliability, JSON support |
| API | FastAPI | Async, type-safe |
| Dashboard | Next.js | Real-time updates |
| Strategy System | Plugin | Easy to add new strategies |
| Risk Engine | Separate layer | Cannot be bypassed |
| AI Mode | Shadow first | Safe deployment |

## Safety Architecture

- **Default Mode:** PAPER
- **Kill Switch:** Emergency stop on anomalies
- **Circuit Breaker:** Auto-pause on drawdown
- **Duplicate Protection:** Fingerprint-based
- **Audit Trail:** Every decision logged

## Future Architecture

```
MARKET DATA
     │
     ▼
MARKET UNDERSTANDING
     │
     ▼
STRATEGY POOL
     │
     ▼
CANDIDATE POOL
     │
┌────┴────┐
▼         ▼
RULE    AI/ML
└────┬────┘
     ▼
META DECISION
     │
     ▼
RISK ENGINE
     │
     ▼
EXECUTION
     │
     ▼
MT5
     │
     ▼
RESULT
     │
     ▼
DATA / JOURNAL
     │
     ▼
STRATEGY INTELLIGENCE
```
