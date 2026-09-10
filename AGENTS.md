# AGENTS.md

## Project

MT5 AI Trading Platform

## Primary Objective

Build a deterministic, testable automated trading platform for MetaTrader 5.

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

## MT5 Connectivity (Bridge Mode)

The bot talks to MetaTrader 5 through a gateway selected by `MT5_MODE` in `.env`:

- `local` (default) — `MetaTrader5` package on this machine (Windows/Wine). If the package is absent, MT5 features are mocked — this is the normal state on Linux and tests must keep passing without it.
- `bridge` — real MT5 terminal on a separate Windows machine, reached over HTTP via `src/market/bridge_gateway.py`.

**The bridge server is a separate project:** `~/projects/mt5-bridge`
(GitHub: `JiraNot/mt5-bridge`, private). It is intentionally NOT in this repo —
do not re-create or duplicate it here; edit it in its own repo.

Rules:

1. `BridgeGateway` must implement the same interface as `MT5Connection` — strategies, AI, and Risk Engine must stay gateway-agnostic.
2. New MT5-related behavior on the server side goes in `mt5-bridge/mt5_bridge.py`; both sides of the HTTP contract must change together.
3. Bridge behavior is tested with `httpx.MockTransport` in `tests/unit/test_bridge_gateway.py` — no real server needed.
4. Bridge settings: `MT5_MODE`, `BRIDGE_URL`, `BRIDGE_TOKEN`, `BRIDGE_TIMEOUT` (see `.env.example` and `docs/bridge_deployment.md`).
5. A Wine-hosted MT5 terminal (`~/.mt5` prefix) exists on this machine and can run the bridge for E2E testing — Wine is dev/fallback only, never the production path.

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
6. When touching MT5 connectivity: docs/bridge_deployment.md and the mt5-bridge repo's README.md

## After Coding

Update:
- PROJECT_STATUS.md
- task checklist
- tests
- CHANGELOG.md when architecture or behavior changes
