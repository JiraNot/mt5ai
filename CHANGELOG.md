# Changelog

All notable changes to the MT5 AI Trading Platform will be documented in this file.

## [0.5.0] - 2026-09-02

### Added

- **Feature Engine** — ML-ready feature extraction from market state
- **Order State Machine** — Full order lifecycle (CREATED→VALIDATED→SUBMITTED→FILLED→CLOSED)
- **Position Manager** — Breakeven, trailing stop, partial close, time-based exit
- **Trade Journal v2** — Logs ALL candidates (traded + rejected + expired)
- **Displacement Detection** — Impulsive movement scoring (0-100)
- **Session Engine** — Asia/London/NY session tracking
- **Market Regime Filter** — ADX/ATR/Choppiness-based regime detection
- **FVG Optimized Strategy** — 82.6% win rate, PF 8.64
- **FVG Final Strategy** — With proper regime filtering
- **Multi-timeframe Backtester** — Using hourly data
- **Live Monitor MTF** — Real-time scanning with SELL capability
- **Gap Analysis** — Documented current state vs master plan
- **Documentation Structure** — AGENTS.md, PROJECT_STATUS.md, Architecture docs

### Performance

- FVG Optimized: 82.6% win rate, +30.8% return (6 months)
- FVG Reversal: 61.5% win rate, +10.8% return (2 years)
- SELL capability added — 100% win rate on counter-trend trades

### Tests

- 166 tests passing (unit + integration)

## [0.4.0] - 2026-09-01

### Added

- **Market Structure Engine** — Swing, BOS, CHoCH detection
- **FVG Detection** — With mitigation tracking
- **Order Block Detection** — With strength scoring
- **Liquidity Sweep Detection** — Buy/sell side
- **Strategy Plugin System** — Registry + base class
- **3 Strategies** — CHoCH+OB, FVG, Breakout Retest
- **AI Scoring** — Rule-based context analysis
- **Risk Engine** — Filters, limits, circuit breaker
- **Database Models** — 7 ORM models
- **Backtester** — Basic version
- **Dashboard** — Streamlit interactive
- **104 Tests** — Unit tests for detectors

## [0.3.0] - 2026-08-31

### Added

- **Core Types** — 30+ Pydantic models
- **Config System** — YAML + env vars
- **Event Bus** — Async pub-sub
- **Logger** — structlog
- **MT5 Connection** — Mock mode
- **Data Feed** — OHLCV polling
- **Session Tracker** — London/NY/Asian
- **Spread Monitor** — Health tracking

## [0.2.0] - 2026-08-30

### Added

- **Repository Structure** — Initial project layout
- **pyproject.toml** — Dependencies
- **Docker Compose** — PostgreSQL + Redis
- **Alembic** — Migration setup

## [0.1.0] - 2026-08-29

### Added

- **Initial Commit** — Project skeleton
