# AGENTS.md

## Project

Binance AI Trading Platform

## Primary Objective

Build a deterministic, testable automated trading platform for Binance USDT-M Futures.

AI may evaluate trading candidates but must never bypass Risk Engine.

## Architecture Rule

```
Market Data
→ Market Structure
→ Strategy
→ Candidate
→ Decision
→ Risk
→ Execution
→ Position Management
→ Journal
```

Do not bypass layers.

## Binance Connectivity

- `BINANCE_MODE=paper` is the safe default; live exchange calls are disabled unless an explicitly supported mode is configured.
- Market data and execution use the Binance gateway in `src/market/binance_gateway.py`.
- Credentials must stay out of source control. Tests use mocked HTTP transports and must not require exchange credentials or a real account.
- Keep execution fail-closed and preserve broker-side protective stops for every supported non-paper order.

## Safety Rules

1. LIVE trading must be disabled by default.
2. Default execution mode is PAPER.
3. Every opened position must have server/broker-side SL.
4. AI cannot modify risk limits.
5. No martingale.
6. No grid recovery.
7. No averaging-down unless explicitly implemented as a future strategy.
8. No hidden auto-enable LIVE mode.
9. Every order must have an audit trail.
10. Risk Engine has final authority.

## Development Rules

- Prefer deterministic logic.
- Avoid duplicated trading logic.
- Backtest and live execution should reuse domain logic.
- No trading parameter hardcoding.
- Every algorithm must expose a version.
- New strategy must implement Strategy interface.
- Add tests before marking tasks complete.

## Current MVP

**Symbol:** XAUUSD

**Timeframes:**
- H1 = Bias
- M15 = Structure
- M5 = Entry

**Strategies:**
1. CHoCH + Order Block
2. FVG Retracement
3. Breakout Retest

**Execution:** PAPER → DEMO → LIVE

## Before Coding

Read:
1. PROJECT_STATUS.md
2. docs/01_ARCHITECTURE.md
3. docs/02_ROADMAP.md
4. Current task file
5. Relevant module specification
6. When touching Binance connectivity: the relevant gateway specification and current Binance configuration docs

## After Coding

Update:
- PROJECT_STATUS.md
- task checklist
- tests
- CHANGELOG.md when architecture or behavior changes
