# Project Status

## Current Phase

PHASE 09 — Paper Trading (Completed)

## Current Milestone

Milestone A — Trading Research Core (complete)

## Current Trading Mode

PAPER

## Live Trading

DISABLED

## Implemented

- [x] Core types, config, events, logging (Phase 00)
- [x] Binance USDT-M gateway for market data and supported execution modes
- [x] Paper Trading Full Loop & Runner (Phase 09: TASK 0901, 0902, 0903)
- [x] Report Generator: Daily, Weekly, Strategy Comparison (Phase 09: TASK 0904)
- [x] Market Data Engine (Phase 02)
- [x] Swing Detection (Phase 03)
- [x] BOS/CHoCH Detection (Phase 03)
- [x] Displacement Detection (Phase 03)
- [x] Structure Context Builder (Phase 03)
- [x] FVG Detection (Phase 04)
- [x] Order Block Detection (Phase 04)
- [x] Liquidity Detection (Phase 04)
- [x] Market Regime Detector (Phase 04)
- [x] Session Engine (Phase 04)
- [x] Strategy Plugin System (Phase 05)
- [x] 4 Strategies: CHoCH+OB, FVG, Breakout, Optimized FVG (Phase 05)
- [x] AI Scoring (rule-based) (Phase 05)
- [x] Risk Engine: filters, limits, circuit breaker (Phase 06)
- [x] Order State Machine (Phase 06)
- [x] Position Manager (Phase 06)
- [x] Kill Switch (Phase 06)
- [x] Trade Journal v2 (Phase 06)
- [x] Feature Engine for ML (Phase 10)
- [x] Database Models (SQLite) (Phase 00)
- [x] Backtester (basic) (Phase 07)
- [x] Live Monitor MTF (Phase 09)
- [x] Paper Trader (Phase 09)
- [x] Dashboard (Streamlit, partial live-status refresh) (Phase 08)
- [x] OpenRouter DeepSeek Bull Analyst integration (uses Risk Engine final gate)
- [x] OpenRouter model catalog selector in dashboard (Current / Free / Paid)
- [x] Dashboard-managed encrypted AI provider login/API settings (Codex, Gemini, OpenRouter)
- [x] Real PTY dashboard CLI login terminal (Codex, agy, ClinePass)
- [x] Binance USDT-M public market-data gateway (read-only, fail-closed execution)
- [x] Binance market data feed and cache
- [x] Persistent dashboard runtime mode setting (PAPER/DEMO without ENV redeploy)
- [x] Candidate triage and local digest (observe/batch/immediate AI review)
- [x] Local stdio MCP for runtime settings and candidate summaries
- [x] Binance paper execution with journal venue/order identity fields
- [x] Binance WebSocket kline streaming with reconnect and server-time sync
- [x] Binance Futures Testnet signed market orders with server-side SL/TP
- [x] Autonomous background trading worker embedded in FastAPI server lifespan (`ENABLE_TRADING_WORKER=true`)
- [x] Adaptive Paper Learning & Exploration Engine in AI Council (feeds live outcomes to `TradeLearner`)
- [x] Dynamic weight normalization for AI Council (prevents score penalty from unavailable providers)
- [x] Built-in SMC Bull & Bear Heuristics for offline/paper trading resilience
- [x] 24/7 Crypto spread and session filter allowance in Risk Engine for Binance USDT-M pairs
- [x] Multi-root Google/Antigravity and Codex OAuth credential discovery & account email badge
- [x] 100% Real Trade Telemetry on Pro Desk (Eliminated mock template numbers, linked to user capital & SQLite trades)
- [x] Aggressive Risk Presets (1%, 3%, 5%) with auto-synchronized Daily Loss limits and Crypto Futures exposure scaling
- [x] On-demand Paper Simulator API (`POST /api/actions/simulate_trade`) and UI buttons in Header & Pro Desk
- [x] Initial position/deal reconciliation and duplicate-order protection
- [x] Verified outcomes close venue-aware journal trades
- [x] Bitcoin Macro Regime Analyzer (H4/D1 SMC trend + funding rate crowd detection)
- [x] Crypto Screener & Homework engine for 24h Binance USDT-M Futures watchlists
- [x] Post-trade retrospective and contextual lesson generation in TradeLearner
- [x] Promotion Gate statistical readiness auditor for safe Demo -> Live transition
- [x] Macro News Filter with high-impact economic blackout windows (TradeFilter)
- [x] Safe Leverage (5-10x) and Isolated Margin enforcement with liquidation distance safety
- [x] Multi-Symbol Watchlist execution loop in TradingPlatform with portfolio-wide concurrency limits
- [x] Telegram Morning Briefing and Evening Reflection alerts
- [x] Streamlit Dashboard "Agent Homework & Readiness" tab with 0-100% Readiness Gauge
- [x] Streamlit Dashboard Live Charts: TradingView Pro real-time widget + Plotly AI Candlestick with SL/TP overlays
- [x] Automated Background Scheduler (08:00 UTC+7 Morning Brief, 20:00 UTC+7 Daily Reflection, 4H BTC Macro refresh)
- [x] Smart Position Management (Break-Even auto-lock at >= 1.0R, Partial Take-Profit 50% volume at >= 1.5R, Telegram alerts)
- [x] Two-Way Interactive Telegram Bot (/status, /homework, /panic emergency shutdown, /readiness, /help)
- [x] Multimodal AI Vision Confirmation (TradingView-style dark candlestick renderer + Rejection/Displacement/Trap analysis)
- [x] Walk-Forward Backtesting Suite (Rolling in-sample/out-of-sample windows, Walk-Forward Efficiency WFE calculation)
- [x] Modern Pro Crypto WebApp (React 19 + TypeScript + Vite + Tailwind CSS + TradingView Lightweight Charts + FastAPI WebSocket backend)
- [x] Responsive Tablet & Touch UX for WebApp (Verified 65/65 checks passed: Header layout, PANIC visibility, >= 44px touch targets, 100dvh, haptic vibration across 5 screen sizes). See docs/testing/TABLET_UX_VERIFICATION.md.
- [x] Binance Testnet 401 Unauthorized auto-fallback to safe Paper execution & robust SPA routing
- [x] Technical Indicators & Dynamic S/R Overlays (EMA 20, EMA 50, EMA 200, Resistance, Support, Pivot) with real-time value strip and toggle controls
- [x] Candlestick Trade Markers & Trade Retrospective Drawer (Why entered, Why won/lost in Thai, with interactive chart focus)
- [x] Dynamic Settings Management & Modal (`SettingsModal.tsx` + `src/core/runtime_settings.py`) allowing seamless configuration of Risk, Binance API, AI, and Telegram without .env redeployments
- [x] Docker Persistent Volume (`/app/data`) Synchronization across Screener, Watchlist, and Council triage
- [x] Dynamic Binance Gateway & Telegram Re-initialization upon runtime configuration updates
- [x] Institutional Volume Spike & RSI Momentum Filters (`src/strategies/indicators.py`, `choch_orderblock` v1.1.0, `breakout_retest` v1.1.0)
- [x] One-Click In-App Strategy Backtester (`BacktestModal.tsx` + `POST /api/backtest/run`) with SVG Equity Curve and simulated trade log
- [x] Multimodal AI Vision Provider selector & customizable approval threshold
- [x] Docker & Coolify Auto-Deploy Hardening (docker-compose sync, resilient healthchecks, GitHub Actions webhook trigger)
- [x] MobileIDE-inspired AI Login & Local Session Probing (`src/core/ai_auth_service.py`, `GET /api/ai/auth-status`, `POST /api/ai/test`): Quota-safe CLI status checking (Codex ChatGPT, Gemini Antigravity, OpenAI, OpenRouter) with real-time latency ping and 1-click Web Terminal login
- [x] Institutional Pro Prop Desk & Telemetry Dashboard (`ProAnalyticsDashboard.tsx`, `src/analytics/pro_metrics_service.py`, `GET /api/analytics/pro-metrics`): SwingFrontRun-inspired high-density desk featuring Top Telemetry Ribbon (Regime, S/R Range, Spread, Latency, Macro News, Global Clocks), Executive 6 Financial Cards, Multi-Strategy LEGS Breakdown with Win/Loss 20-trade sparkline ticks, Daily P/L Calendar Heatmap (day-by-day tiles, weekly subtotals, Green Days count), Execution Quality & Slippage Analytics (Broker Grade A+, latency, slip vs edge ratio, hourly slip distribution), Dual-Line Equity & Gross Edge Curve SVG, and Live Circuit Breakers Safety Matrix. Seamless 1-click Header toggle between `📈 CHART` and `📊 PRO DESK`.
- [x] 347 Tests passing (0 failures)
- [x] Documentation structure complete
- [x] ADR documents (5)
- [x] Task files (13 phases)

## In Progress

- [ ] AI Shadow Mode & Evaluation (Phase 10)

## Pending

- [ ] FastAPI backend & Next.js dashboard refinement (Phase 08)
- [ ] AI Shadow Mode (Phase 10)
- [ ] LLM integration & Deep Research (Phase 10)
- [ ] ML training pipeline (Phase 11)
- [ ] Alert system (Phase 08)
- [ ] News filter (Phase 10)
- [ ] Security/auth (Phase 08)
- [ ] Docker production (Phase 00)
- [ ] CI/CD (Phase 00)
- [ ] Demo trading (Phase 12)
- [ ] Live trading (Phase 12)

## Known Issues

- Production dashboard previously showed `Loop: starting · cycles: 0` when the background worker exited; Docker supervision, explicit bridge-token wiring, root startup permissions for Coolify persistent volumes, and defensive normalization of legacy SQLite URLs are fixed and verified in production on 2026-09-15. The AI Council now permits only high-confidence disagreements to proceed to the Risk Engine; Risk Engine remains final authority.
- Coolify Compose manifests are now kept in sync, including OpenRouter runtime settings and an explicit Streamlit health check, so `trade.onetapweb.com` can be routed only after the dashboard is ready (2026-09-22).
- OpenRouter DeepSeek is available as the Bull analyst when `OPENROUTER_API_KEY` is configured; without it, the existing Gemini path remains available.
- Binance is the only supported exchange. Paper mode is the safe default; Testnet signing requires `BINANCE_MODE=testnet` and explicit credentials. LIVE remains disabled by default.
- Execution mode can be changed from the dashboard and is persisted under `/app/data`; LIVE remains locked behind explicit arming and Binance safeguards.
- Candidate triage records all strategy outputs above the observation floor, sends only immediate candidates to the AI Council, and exposes its policy/status through the local MCP server.
- Binance restart reconciliation now uses the journaled symbol and opening order to isolate relevant `userTrades`; liquidation price is never exposed as a strategy stop.
- Partial fills from one Binance opening order are aggregated before outcome verification; separate opening orders remain rejected.
- No real-time data feed
- Breakout Retest strategy never triggers on real data
- CHoCH+OB strategy has low win rate (16.7%)

## Architecture Decisions

- ADR-001: Python Trading Core
- ADR-002: PostgreSQL Database
- ADR-003: Closed Candle Strategy Evaluation
- ADR-004: Risk Engine Final Authority
- ADR-005: Shared Live/Backtest Domain Logic

## Performance Results

Historical figures below predate the 2026-09-10 R:R correction and must be revalidated.

| Strategy | Trades | Win Rate | Profit Factor | Return | Verdict |
|----------|--------|----------|---------------|--------|---------|
| FVG Optimized | 23 | 82.6% | 8.64 | +30.8% | Profitable |
| FVG Reversal | 13 | 61.5% | 2.87 | +10.8% | Profitable |
| CHoCH+OB | 6 | 16.7% | 0.41 | -3.0% | Losing |
| Breakout Retest | 0 | N/A | N/A | 0% | Never triggers |

## Code Statistics

```
Source files: 52+
Test files: 13
Total tests: 330 (all passing)
Documentation files: 40+
Task files: 13
```

## Next Task

PHASE_10 / TASK_1001 — Shadow Mode & ML Feature Store

## Documentation

```
AGENTS.md              - Coding agent guidance
PROJECT_STATUS.md      - This file
CHANGELOG.md           - Version history
docs/00_PROJECT_VISION.md
docs/01_ARCHITECTURE.md
docs/02_ROADMAP.md
docs/03_DOMAIN_MODEL.md
docs/04_DATABASE.md
docs/05_CONFIGURATION.md
docs/market/           - 9 specification files
docs/strategies/       - 6 specification files
docs/trading/          - 5 specification files
docs/ai/              - 5 specification files
docs/backtesting/     - 4 specification files
docs/platform/        - 6 specification files
docs/testing/         - 3 specification files
docs/adr/             - 5 ADR documents
tasks/                - 13 phase task files
```

## Last Updated

2026-09-28


## AI audit remediation — 2026-09-10

- [x] Strict provider response validation and repaired main app/context wiring
- [x] Verified broker outcomes, durable entry evidence and restart-safe memories
- [x] Removed unsupported causal diagnoses and per-trade score mutation
- [x] Repaired ML dataset and leakage; walk-forward plus final holdout implemented
- [x] PAPER broker-order guard and bounded smoke-run support
- [ ] Real-data evidence that AI/ML beats the rule baseline (no model promoted)
- [ ] Full PAPER simulation/rejected-candidate outcome comparison

See `docs/ai/AUDIT_FIXES_2026_09_10.md` for verified scope and limitations.
