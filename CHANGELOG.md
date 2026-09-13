# Changelog

## Unreleased

- Docker image now installs the Codex and Antigravity CLIs for AI Council deployment.
- Coolify can initialize Codex/ChatGPT login from the `CODEX_AUTH_JSON` secret;
  Antigravity uses the `GEMINI_API_KEY` secret through its supported Gemini
  provider, without gcloud or Vertex AI.
- Added a scheduled research-only trainer that retrains after new verified Demo
  outcomes and persists artifacts separately from the trading database.
- Dashboard now refreshes live status and database metrics every 10 seconds by default.
- Dashboard status now includes the trading mode, worker state, cycle count, and
  last engine decision. The worker publishes an atomic heartbeat at
  `/app/data/runtime_status.json`; diagnostic write failures cannot interrupt the
  trading loop.
- Coolify Compose persists research models and runs the verified-outcome trainer
  daily. `TRADING_MODE=PAPER` remains the safe default; set `TRADING_MODE=DEMO`
  explicitly when demo broker orders are intended.
- Docker runtime now includes `libgomp1` for LightGBM and creates the data/model
  volume directories before starting the worker, dashboard, or trainer.
- SQLite startup now creates the configured database parent from both the async
  worker and synchronous dashboard paths.
- Coolify/Traefik router labels now explicitly select their named backend service,
  avoiding automatic-linking conflicts with Coolify's generated HTTP/HTTPS services.

All notable changes to the MT5 AI Trading Platform will be documented in this file.

## [Unreleased] - 2026-09-10

### Fixed

- Real-feed smoke exposed inflated BUY and inverted SELL R:R formulas; shared
  distance arithmetic now feeds strategy scoring and AI/Risk, with strategy version bumps.
- AI audit: strict fail-closed provider parsing; complete main-app wiring and actual
  MTF context; use closed candles and refresh finalized bars.
- Reconcile closed trades from broker deals, including costs and partial exits;
  retry unavailable history instead of labelling floating PnL.
- Persist entry evidence and idempotent, factual outcome memories; calculate R
  from initial monetary risk; stop unvalidated per-trade score adjustments.
- ML dataset/schema mismatch and preprocessing leakage; purged walk-forward
  selection plus untouched holdout; research models never auto-enable.
- Main OrderManager blocks broker execution in PAPER/LIVE; only explicit DEMO
  may submit orders after Risk approval. Added bounded `--cycles` smoke runs.

### Added

- Additive `learning_evidence` table and AI/learning/ML regression tests.
- Matched local/bridge deal-history interface and separate bridge server tests.
- Details and remaining research boundaries: `docs/ai/AUDIT_FIXES_2026_09_10.md`.

## [0.6.0] - 2026-09-09

### Added

- **MT5 Bridge mode** (`MT5_MODE=bridge`) — connect the Linux bot to a real MT5
  terminal hosted on a separate Windows machine over HTTP
- **`src/market/bridge_gateway.py`** — `MT5Connection`-compatible adapter
  (connect, get_ohlcv, get_current_price, get_account_info, send_order,
  modify/close position, get_positions) with injectable HTTP transport for tests
- **Bridge settings** — `mt5_mode`, `bridge_url`, `bridge_token`, `bridge_timeout`
- **`settings.primary_symbol`** — new config field (env `PRIMARY_SYMBOL`, default from `symbols.yaml`)
- **CLI flags in `src/app.py`** — `--status` (mode, strategies, session) and `--backtest`
- **Bridge deployment guide** — `docs/bridge_deployment.md`
- **Unit tests for the bridge gateway** — 15 tests via `httpx.MockTransport`

### Changed

- **Bridge server moved to a standalone project** —
  [JiraNot/mt5-bridge](https://github.com/JiraNot/mt5-bridge) (private).
  This repo keeps only the client adapter; server lives with the MT5 host.

### Fixed

- Truncated `src/app.py` (rebuilt `TradingPlatform` pipeline, event handlers, DB wiring, CLI)
- Truncated `src/storage/repository.py#get_equity_curve()`
- Thai text corruption in README project-structure block

### Tests

- 181 tests passing (166 existing + 15 bridge gateway)
- Bridge mode proven end-to-end under Wine: bridge server → `BridgeGateway` →
  account, OHLCV, and live XAUUSD tick

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
