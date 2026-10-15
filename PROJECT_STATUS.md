# Project Status

## Current Phase

PHASE 09 — Paper Trading (partial)

## Current Milestone

Milestone A — Trading Research Core (mostly complete)

## Current Trading Mode

PAPER

## Live Trading

DISABLED

## Implemented

- [x] Core types, config, events, logging (Phase 00)
- [x] Binance USDT-M gateway for market data and supported execution modes
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
- [x] 311 Tests passing
- [x] Documentation structure complete
- [x] ADR documents (5)
- [x] Task files (13 phases)

## In Progress

- [ ] Paper trading full loop (Phase 09)

## Pending

- [ ] FastAPI backend (Phase 08)
- [ ] AI Shadow Mode (Phase 10)
- [ ] LLM integration (Phase 10)
- [ ] ML training pipeline (Phase 11)
- [ ] Next.js dashboard (Phase 08)
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
Source files: 50+
Test files: 11
Total tests: 282 (all passing)
Documentation files: 40+
Task files: 13
```

## Next Task

PHASE_07 / TASK_0709 — Walk Forward Testing

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
