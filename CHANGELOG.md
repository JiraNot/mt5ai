# Changelog

## 2026-10-18 (Institutional Enhancements: In-App Backtesting, Volume/RSI Filters & Multimodal Vision)

- **One-Click In-App Strategy Backtester (`BacktestModal.tsx` + `POST /api/backtest/run`)**:
  - Implemented on-demand historical simulation accessible via the new `BACKTEST` button in the header.
  - Multi-parameter simulation supporting Strategy selection, Symbol (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`), Timeframe (`1m`, `5m`, `15m`, `1h`), Capital, and Candle length.
  - Real-time simulation metrics: Win Rate %, Profit Factor, Max Drawdown %, Net PnL, Expectancy, and Sharpe Ratio.
  - Interactive SVG Equity Curve displaying portfolio trajectory over time with gradient fill.
  - Simulated trade log detailing side, entry, exit, PnL ($), and R-multiples with realistic Binance taker fees (0.05%) and slippage modeling.
- **Institutional Volume Spike & RSI Momentum Filters (`src/strategies/indicators.py`)**:
  - Implemented Wilder's smoothed Relative Strength Index (RSI) and 20-period Volume Moving Average ratio.
  - Added institutional volume expansion filter preventing low-liquidity false breaks (bull/bear traps).
  - Integrated momentum filters directly into `CHOCHOrderBlockStrategy` (v1.1.0) and `BreakoutRetestStrategy` (v1.1.0).
  - Completed `_check_short_choch_ob` candidate generation and enabled strategy auto-registration.
- **Multimodal AI Vision Provider Selector & Configurable Threshold**:
  - Added `vision_provider` selector in `SettingsModal.tsx` (Deterministic High-Res Engine, OpenAI GPT-4o Vision, Claude 3.5 Sonnet, DeepSeek Vision).
  - Added customizable Minimum Vision Approval Score slider (50% to 90%).
  - Added Volume Spike and RSI Momentum filter toggle switches directly into the Trading & Risk settings tab.
- **Test Suite**:
  - Added `tests/unit/test_indicators.py` (6 tests) and `tests/unit/test_api_backtest.py` (1 test).
  - Test suite expanded to **343 passing tests (0 failures)**.

## 2026-10-18 (System Recheck & Production Hardening)

- **Docker Persistent Volume (`/app/data`) Synchronization**:
  - Resolved path discrepancy where Docker production containers mounted persistent data to `/app/data/` while local runs used `data/`.
  - Added dual-path saving in `CryptoScreener._save_watchlist()` to persist to both `/app/data/crypto_watchlist.json` and `data/crypto_watchlist.json`.
  - Updated API endpoints in `src/web/server.py` (`/api/watchlist`, `/api/council/latest`) and `src/app.py` to check `/app/data` first.
- **Dynamic Binance Gateway & Telegram Re-initialization**:
  - Updated `BinanceGateway.connect()` and `websocket_base_url` to automatically tear down and re-establish `httpx.AsyncClient` if `binance_base_url` or venue mode is updated in runtime settings.
  - Added fallback in `TelegramAlert.send_message()` and `TelegramBotListener` to load `telegram_bot_token` and `telegram_chat_id` dynamically from encrypted `runtime_settings.json` when environment variables are omitted.
- **Automated Recheck & Test Suite Stability**:
  - Full end-to-end regression audit: 336 tests passing (0 failures).

## 2026-10-17 (Technical Indicators, Trade Markers & Retrospective, Dynamic Settings UI)

- **Technical Indicators & Institutional Overlays (`TradingChart.tsx`)**:
  - Implemented mathematical Exponential Moving Averages (EMA 20 in Cyan `#00d4ff`, EMA 50 in Amber `#f59e0b`, EMA 200 in Purple `#a855f7`) with O(N) calculation from closed candles.
  - Added Dynamic Support & Resistance levels (24h High resistance, 24h Low support, Midpoint pivot) based on SMC swing context.
  - Added chart toolbar toggle buttons for `EMA 20/50/200`, `S/R Levels`, and `Trade Markers` with real-time numeric value legend readout.
- **Trade Candlestick Markers & Retrospective Drawer (`TradingChart.tsx` + `/api/trades/markers`)**:
  - Rendered entry markers (`arrowUp` for BUY, `arrowDown` for SELL) and exit markers (`circle` with WIN/LOSS PnL).
  - Added collapsible "Trade Inspector" drawer below the chart showing trade tickets, entry/exit prices, profit, and R-multiple.
  - Added clear Thai contextual explanations for each trade:
    - **🎯 เข้าเพราะ (Why entered)**: Identifies whether setup was FVG Reversal, Breakout Retest, or CHoCH Order Block.
    - **📊 ผลลัพธ์ (Why won/lost)**: Detailed retrospective explaining if TP was reached according to SMC plan or if SL was hit due to spread volatility.
- **Dynamic Settings UI & Manager (`SettingsModal.tsx` + `src/core/runtime_settings.py`)**:
  - Created persistent runtime settings manager storing configuration in `/app/data/runtime_settings.json` (survives container redeployments).
  - Encrypts sensitive secrets (Binance API Key/Secret, AI Provider keys, Telegram Bot Token) using Fernet cryptography derived from dashboard password.
  - Allows full configuration of Trading Mode (Paper/Demo/Live), Primary & Watchlist Symbols, Risk % per trade, Daily loss limit, Binance API credentials, AI Models, and Telegram alerts directly from the Web UI without touching `.env`.
  - Added `SETTINGS` button in `Header.tsx` to open the modal from any screen.
- **Test Suite**:
  - Added `tests/unit/test_runtime_settings.py` (4 tests) and `tests/unit/test_api_settings_and_markers.py` (2 tests).
  - Platform test suite expanded to **336 passing tests (0 failures)**.

## 2026-10-16 (Phase 09: Paper Trading Full Loop & Comprehensive Analytics Reporting)

- **Paper Trading Full Loop Runner (`src/live/paper_loop.py`)**:
  - Implemented `PaperTradingRunner` executing the full deterministic pipeline:
    - Market Data Ingestion & Multi-timeframe SMC Context Building (`M5`, `M15`, `H1`, `H4`).
    - Multi-strategy Candidate Evaluation via `MetaDecisionEngine` (`fvg_reversal`, `fvg_final`, `fvg_optimized`, etc.).
    - Comprehensive Candidate & Signal Logging in `TradeJournal` (TASK 0902).
    - Rule-Based AI Scorer Evaluation with candidate triage.
    - Risk Engine Evaluation checking daily drawdown limits, max exposure, and position sizing (TASK 0901).
    - Simulated Execution via `PaperGateway` with mandatory server/broker-side Stop Loss (Rule 3).
- **Real-Time Outcome & Hypothetical Tracking (TASK 0903)**:
  - Real-time open position tracking evaluating SL/TP hits on incoming candles.
  - Binance Futures taker fee model accounting (0.05% entry and exit fee deduction).
  - Maximum Favorable Excursion (MFE), Maximum Adverse Excursion (MAE), and R-multiple tracking.
  - Hypothetical outcome tracking for rejected candidates to monitor filter quality and false rejection rates.
  - Real-time equity curve, peak equity, and maximum drawdown percentage calculation.
- **Report Generation Suite (`src/analytics/report_generator.py` - TASK 0904)**:
  - `DailyReport`: Daily candidate summary, approved/rejected/executed ratios, win rate, net PnL, profit factor, fees, false reject rate, and per-strategy breakdown.
  - `WeeklyReport`: 7-day multi-day aggregation, day-by-day table, strategy contribution, and risk adherence audits.
  - `StrategyComparisonReport`: Side-by-side comparative matrix, composite score ranking, underperforming strategy detection, and automated recommendations.
  - Markdown and structured dictionary export (`to_markdown()`, `to_dict()`, `save_report_to_file()`).
- **Comprehensive Test Suite**:
  - Added `tests/unit/test_report_generator.py` (4 tests) and `tests/integration/test_paper_trading_loop.py` (4 tests).
  - Platform test suite expanded to **330 passing tests (0 failures)**.

## 2026-10-15 (Binance AI Platform Full-Suite Enhancement & Modern WebApp Overhaul)

- **Modern Pro Crypto WebApp (React 19 + TypeScript + Vite + Tailwind CSS + TradingView Charts)**:
  - Replaced legacy, slow Streamlit UI with a blazing-fast, responsive single-page application (SPA).
  - **All-in-One Pro Terminal Grid**:
    - **Header**: Live balance, equity, spread ticker, Promotion Gate readiness gauge (0–100%), Paper/Live mode toggle, and Panic Kill-Switch modal.
    - **TradingView Lightweight Charts**: 60 FPS canvas candlestick chart with timeframe switcher (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`), volume histogram, and dynamic Entry/SL/TP horizontal line overlays.
    - **AI Watchlist & Homework Panel**: BTC Macro regime cards, top ranked coins, 24h change %, and "Scan Now" button with immediate chart symbol switching.
    - **AI Council Verdict Card**: Real-time evaluation breakdown, consensus score, Thai narrative analysis, confluences, and multimodal AI Vision confirmation verdict.
    - **Active Positions & History Table**: Live positions with manual "Close" and "Lock BE" buttons, plus historical closed trade audit log.
    - **Tablet & Touch UI/UX Optimization**:
      - Responsive collapsible sidebar drawer with backdrop overlay for tablet portrait and smaller screens (`< 1024px`), maximizing chart canvas.
      - Tabbed navigation in sidebar (`Watchlist` vs `AI Council`) so each view gets full vertical space on tablet without micro-scrolling.
      - Enabled native touchscreen pinch-to-zoom (`pinch: true`) and horizontal drag pan (`horzTouchDrag: true`) on TradingView chart.
      - Collapsible bottom positions table with chevron toggle to maximize TradingView height on tablet screens.
      - Enlarged all interactive touch controls to >= 44px (Timeframe, Mode, AI Login, PANIC, Drawer tabs, Table collapse, Lock BE, Close, Scan Now).
      - Fixed Header layout across tablet portrait (768px, 820px) to prevent PANIC clipping, moving account stats to `lg:flex` and ensuring zero horizontal overflow.
      - Full automated Tablet UX verification passed (65/65 checks across 5 viewport sizes, docs/testing/TABLET_UX_VERIFICATION.md).
      - Table horizontal scroll container (`overflow-x-auto min-w-[800px]`) prevents column squeezing on touchscreens.
      - Dynamic Viewport Height (`h-[100dvh]`) preventing tablet browser address bar from shifting/obscuring bottom controls.
      - Haptic touch vibration (`navigator.vibrate`) on PANIC, Lock BE, and Close actions for physical confirmation.
  - **Unified FastAPI & WebSocket Server (`src/web/server.py`)**:
    - High-frequency REST APIs (`/api/status`, `/api/watchlist`, `/api/readiness`, `/api/positions`, `/api/candles/{symbol}`, `/api/council/latest`, `/api/actions/*`).
    - Real-time WebSocket broadcaster (`/ws`) streaming price ticks, candle updates, and active position changes.
    - Serves pre-built Vite assets with single-port deployment on port 8501 (fully compatible with Coolify / Traefik reverse proxies).
  - **Automated Test Suite**: Added `tests/unit/test_web_api.py` with 10 unit tests. Platform test suite expanded to **321 passing tests (0 failures)**.

- **Web Dashboard "Agent Homework & Readiness" Tab**:
  - Live Promotion Readiness Gauge (0–100%) with 6-gate safety audit checklist (Sample size >= 30, Profit Factor >= 1.5, Net PnL > 0, Win Rate >= 40%, Max DD <= 5%, 100% Server SL compliance).
  - Agent Homework & Watchlist section showing BTC Macro Framework (Bias, Trend, Crowd Sentiment, Funding Rate) and Top 5 curated Binance Futures picks.
  - Interactive on-demand "Run Screener Now" button to execute homework live from the browser.
- **Automated Background Scheduler (`src/live/scheduler.py`)**:
  - Automatically runs at **08:00 (UTC+7)** Bangkok time: executes `CryptoScreener.run_homework()`, updates `data/crypto_watchlist.json`, and dispatches `alert_morning_brief` to Telegram.
  - Automatically runs at **20:00 (UTC+7)** Bangkok time: audits closed trades against `PromotionGate`, calculates readiness percentage, and dispatches `alert_evening_reflection` to Telegram.
  - Periodic **4-Hour BTC Macro Refresh** on H4 candle closes to maintain fresh BTC structural and funding crowd sentiment.
  - Full lifecycle support with graceful start/stop in `TradingPlatform`.
- **Two-Way Interactive Telegram Bot (`src/notification/telegram_bot.py`)**:
  - Implemented long-polling command listener with chat ID authentication.
  - Commands supported:
    - `/status`: Displays live balance, equity, mode (PAPER/DEMO/LIVE), and open positions with current PnL and R-multiples.
    - `/homework`: Runs on-demand `CryptoScreener` and delivers Top 5 watchlist picks with 24h volume and BTC Macro bias.
    - `/panic`: Emergency shutdown button — closes all open positions across all symbols, halts platform execution, and triggers circuit breaker.
    - `/readiness`: Displays 0–100% Promotion Gate progress and checklist status.
    - `/help`: Displays available command directory.
- **Multimodal AI Vision Confirmation (`src/ai/vision_analyst.py`)**:
  - High-definition dark-mode candlestick chart renderer (Pillow-based, pure Python, fast and headless).
  - Overlays Entry, Stop Loss, and Take Profit reference lines.
  - Candlestick pattern heuristic engine: detects lower/upper rejection wicks (liquidity sweeps), institutional displacement candle bodies, and false breakout exhaustion traps.
  - Emits `VisionVerdict` (score 0–100, verdict `APPROVE`/`CAUTION`/`REJECT`) feeding directly into candidate risk flags and AI Council debate.
- **Walk-Forward Backtesting Suite (`src/analytics/walk_forward.py`)**:
  - Rolling multi-window In-Sample (Train) and Out-of-Sample (Test) validation for Binance USDT-M Futures.
  - Computes Walk-Forward Efficiency (WFE), Out-of-Sample Profit Factor, Expectancy, Win Rate, and Max Drawdown.
  - Exports comprehensive markdown report evaluating model robustness against overfitting.
- **Test Coverage**: 311 total automated tests passing (0 failures).

## 2026-10-14

- Complete Binance-Only Refactoring: purged legacy `src/mt5` folder, replaced `yfinance` gold proxy with native Binance Futures gateway in `src/live/monitor_mtf.py` and `src/live/paper_trader.py`.
- Added `BTCRegimeAnalyzer` (`src/market/btc_regime.py`) to analyze Bitcoin macro bias (H4/D1 trend, market regime, and funding rate crowd status) and feed into trade context.
- Added `CryptoScreener` (`src/market/crypto_screener.py`) for agent "homework" scanning 24h Binance USDT-M Futures tickers to generate curated watchlists (Top Volume, Volatility, Momentum).
- Enhanced `TradeLearner` (`src/ai/trade_learner.py`) with structured post-trade retrospectives and contextual lesson generation fed into AI Council decision prompts.
- Added `PromotionGate` (`src/risk/promotion_gate.py`) implementing the 6-point statistical readiness checklist (sample size >= 30, Profit Factor >= 1.5, Max DD <= 5%, 100% SL compliance) before permitting LIVE mode.
- Added CLI entrypoints `freebuff-homework` and `freebuff-gate` in `pyproject.toml`.

- Added MT5 path/portable/account environment wiring to the Docker bridge and
  automatic initialization retries after the terminal becomes ready or is
  logged in manually.
- Added concurrent MT5 and Binance pipelines. Configure
  `MARKET_DATA_VENUES=mt5,binance`; each venue keeps its own gateway, symbol,
  candle cache, position tracker, and paper execution path.

## Unreleased

- Removed MetaTrader 5 and bridge connectivity; Binance USDT-M Futures is now the only supported exchange. Paper remains the safe default, Testnet requires explicit configuration, and LIVE remains disabled by default.
- Replaced the line-based CLI Login Console with a real WebSocket PTY browser
  terminal for Codex, agy, and ClinePass. It transports raw keystrokes, paste,
  terminal resize, and OAuth/TUI output while still launching only allow-listed
  login commands; input/output are never persisted and audit records contain
  metadata only.
- Moved Codex/ChatGPT, Gemini/Antigravity, and OpenRouter/DeepSeek provider
  login/API settings into Controls & Safety. Secrets are write-only in the UI,
  encrypted in the runtime volume, and applied by the worker on its next AI
  evaluation; Compose no longer injects provider secrets as environment values.
- Dashboard live status now refreshes as isolated Streamlit fragments instead
  of rerunning the entire page; filters, active tabs, charts, and safety forms
  stay in place. This requires Streamlit 1.37 or newer.
- Added candidate triage with persistent observe/batch/immediate summaries and a local stdio MCP for safe runtime policy control.
- Reorganized the Streamlit dashboard into Command Center, Candidates & AI,
  Learning, Performance, and Controls & Safety views with explicit runtime and
  candidate-policy controls.

- Added a persistent dashboard runtime execution setting. PAPER/DEMO changes
  are picked up by the worker without an ENV redeploy; LIVE requires a separate
  explicit arm confirmation and keeps venue safeguards in force.
- Binance account/position startup now falls back to public-data-only PAPER
  behavior after the dashboard explicitly selects PAPER, avoiding a signed
  account request from blocking BTCUSDT analysis.

- The optional Docker/Wine MT5 image now disables the base image's legacy
  `mt5linux` RPyC startup and uses the project HTTP bridge on port 8900,
  avoiding the Python 3.11-incompatible rolling `mt5linux` package.
- Fixed MT5 bridge startup by running Wine commands as the owner of the
  persisted Wine prefix (`abc`, UID 911).
- Pinned Wine NumPy below 2 so the bundled MetaTrader5 extension can import.
- Started the multi-venue Binance slice with a venue gateway contract and a
  read-only Binance USDT-M Futures REST adapter for klines, book ticker, and
  exchange symbol filters. Binance order execution is intentionally fail-closed
  until paper, testnet signing, and reconciliation are implemented.
- Consensus mode now blocks unavailable-provider fallback as well as real
  analyst disagreement; the relaxed fallback remains opt-in only.
- Binance can now be selected as the market-data venue, with paper fills,
  venue-aware trade journal identity, reconnectable kline streaming, server
  clock synchronization, and testnet-only signed orders with protective SL/TP.
- Verified position outcomes now close the corresponding venue-aware trade
  journal row by external order ID, including net PnL and close price.
- Binance reconciliation now filters `userTrades` by the journaled opening order,
  handles partial exits deterministically, selects the official testnet/mainnet
  WebSocket host through a tested property, and never treats liquidation price as
  a protective stop.
- Binance WebSocket streams now invoke the gateway's server-time synchronization
  callback before each connection/reconnect, with a regression test for the
  `sync → connect` ordering.
- Binance REST polling now excludes forming klines and includes `venue` on its
  `NEW_CANDLE` events, matching the WebSocket data-feed contract.
- The dashboard now exposes an OpenRouter model selector grouped into current,
  free, and paid models; the selected model is persisted for the next Bull
  Analyst evaluation without storing the API key or requiring a redeploy.
- Coolify's `docker-compose.yml` and `docker-compose.yaml` now have matching
  runtime settings, and the dashboard service exposes a Streamlit health check
  for reliable proxy readiness detection.
- Outcome reconciliation now accepts multiple fills from one opening order,
  while still rejecting separate opening order IDs as unsafe attribution.
- Testnet execution coverage now verifies HMAC signature fields, server-time
  parameters, partial primary-fill status, filled quantity, and close-position
  protective orders.
- Testnet retries now query Binance by `origClientOrderId` before creating a
  primary order, and recover existing protective orders after a process restart
  instead of sending a duplicate order.

- AI Council gating is less restrictive for high-quality setups: a disagreement may
  proceed to the Risk Engine only when the approving analyst has at least 75/100
  confidence and the combined score is at least 70. Consensus mode remains
  available, and all hard risk controls remain unchanged.
- When one AI provider is unavailable (for example, Gemini credentials are not
  configured), a strong available analyst plus rule score >=80 may proceed to
  the Risk Engine; a real provider rejection still blocks the setup.
- Added OpenRouter DeepSeek as a Bull analyst provider, selected automatically
  when `OPENROUTER_API_KEY` is configured. It uses the existing structured
  verdict contract and cannot bypass the Risk Engine.
- Docker services now run under a small supervisor so a crashed trading worker
  terminates the container instead of leaving the dashboard with a stale
  `starting` heartbeat; `BRIDGE_TOKEN` is also passed explicitly to the worker.
- Graceful worker shutdown now publishes a `stopped` runtime state.
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
- Coolify Compose now runs the database-sharing app and trainer as UID/GID 0 so
  the startup permission repair can access restrictive persistent-volume mounts.
- Configuration now normalizes the legacy three-slash absolute SQLite URL so
  older Coolify environment values cannot redirect the worker to `/app/app/data`.
- Coolify/Traefik router labels now explicitly select their named backend service,
  avoiding automatic-linking conflicts with Coolify's generated HTTP/HTTPS services.
- Custom router names use the `freebuff-` prefix so they cannot collide with
  Coolify's routers named after the Compose services.

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
