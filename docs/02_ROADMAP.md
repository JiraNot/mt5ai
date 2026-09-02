# Development Roadmap

## Phase 00 — Foundation

**Status:** ✅ Complete

- [x] Repository structure
- [x] Config system
- [x] Logging
- [x] Database models
- [x] Docker environment

## Phase 01 — MT5 Gateway

**Status:** ⚠️ Mock Only

- [x] MT5 connection (mock)
- [ ] Real MT5 connection
- [ ] Account info
- [ ] Symbol info
- [ ] Candle reading
- [ ] Tick reading
- [ ] Order send
- [ ] Order modify
- [ ] Order close
- [ ] Position reading

## Phase 02 — Market Data

**Status:** ✅ Complete

- [x] Candle models
- [x] Multi-timeframe cache
- [x] New candle detection
- [x] Historical loader
- [x] Spread tracking
- [x] Session clock

## Phase 03 — Structure Engine

**Status:** ✅ Complete

- [x] Swing High/Low
- [x] HH/HL/LH/LL
- [x] BOS
- [x] CHoCH
- [x] Displacement
- [x] Structure Context
- [x] Golden tests (partial)

## Phase 04 — SMC Engine

**Status:** ✅ Complete

- [x] FVG detection
- [x] FVG lifecycle
- [x] Order Block
- [x] OB lifecycle
- [x] Liquidity zones
- [x] Equal H/L
- [x] Sweep
- [x] Premium/Discount
- [x] Market Regime

## Phase 05 — Strategy Framework

**Status:** ✅ Complete

- [x] Strategy interface
- [x] TradeCandidate
- [x] Evidence schema
- [x] Scoring engine
- [x] Candidate lifecycle
- [x] CHoCH + OB Strategy
- [x] FVG Retracement Strategy
- [x] Breakout Retest Strategy
- [x] Optimized FVG Strategy

## Phase 06 — Risk & Execution

**Status:** ✅ Complete

- [x] Risk state
- [x] Daily limit
- [x] Position size
- [x] Minimum RR
- [x] Trade limit
- [x] Consecutive losses
- [x] Execution state machine
- [x] Duplicate protection
- [x] Kill Switch
- [x] Position Manager

## Phase 07 — Backtest

**Status:** ⚠️ Basic

- [x] Historical event loop
- [x] Basic simulation
- [ ] Simulated broker
- [ ] Spread model
- [ ] Commission model
- [ ] Slippage model
- [ ] Full position simulation
- [x] Basic metrics
- [ ] Full report
- [ ] Walk forward

## Phase 08 — Dashboard

**Status:** ⚠️ Streamlit Only

- [x] Streamlit dashboard
- [ ] FastAPI backend
- [ ] Authentication
- [ ] Next.js dashboard
- [ ] Trade analytics
- [ ] Strategy analytics
- [ ] Risk monitor
- [ ] System health
- [ ] Emergency controls

## Phase 09 — Paper Trading

**Status:** ✅ Complete

- [x] Live monitor
- [x] Paper trader
- [x] Signal logging
- [ ] Full pipeline validation

## Phase 10 — AI Shadow

**Status:** ⚠️ Rule-based Only

- [x] Rule-based scoring
- [ ] Structured feature payload
- [ ] LLM provider abstraction
- [ ] Response schema validation
- [ ] AI journal
- [ ] Shadow evaluation
- [ ] Rule vs AI comparison

## Phase 11 — ML

**Status:** ⚠️ Feature Engine Ready

- [x] Feature Engine
- [ ] Candidate dataset builder
- [ ] Feature pipeline
- [ ] Train/validation split
- [ ] Baseline
- [ ] Logistic Regression
- [ ] Random Forest
- [ ] Gradient Boosting
- [ ] Model comparison
- [ ] Model registry

## Phase 12 — Demo

**Status:** ❌ Not Started

- [ ] Demo mode
- [ ] Continuous running
- [ ] Performance monitoring
- [ ] Drawdown tracking

## Phase 13 — Limited Live

**Status:** ❌ Not Started

- [ ] Live mode (limited)
- [ ] Minimum position
- [ ] Low risk
- [ ] Limited symbols
- [ ] Manual approval required

## Phase 14 — Production

**Status:** ❌ Not Started

- [ ] Full live mode
- [ ] Portfolio management
- [ ] Multi-symbol
- [ ] Advanced ML
- [ ] Ensemble engine
