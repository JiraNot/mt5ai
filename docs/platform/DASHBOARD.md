# Dashboard

## Overview

Dashboard แสดงผล real-time ของระบบ trading

## Current Streamlit Layout

The dashboard is organized around five jobs instead of exposing every chart at
the same level:

### Command Center

The first screen answers: is the worker running, is market data connected, are
Candidates arriving, and what did the engine decide most recently?

### Candidates & AI

Shows the candidate funnel, observe/batch/immediate counts, filters by strategy
and direction, recent setup rows, AI Council debates, and the compact digest
sent alongside immediate AI reviews.

### Learning

Shows broker-verified memories and makes the boundary explicit: memories are
evidence for future AI context, not automatic strategy mutation.

### Performance

Combines trade metrics, equity/drawdown, strategy comparison, daily P&L, and an
expandable trade journal.

### Controls & Safety

The canonical place for PAPER/DEMO/LIVE, candidate triage thresholds, AI review
budget, model selection, connection status, and read-only Risk Engine limits.
LIVE requires explicit confirmation. Risk limits and broker credentials remain
outside this runtime control surface.

## Legacy Product Map

### /dashboard (Main)
```
- Mode (PAPER/DEMO/LIVE)
- Runtime execution setting (persisted in `/app/data`, no redeploy required)
- MT5 status
- Account Equity
- Daily P/L
- Daily Risk Used
- Open Positions
- Candidates Today
- Trades Today
- Bot status
```

The runtime mode selector supports PAPER and DEMO immediately. LIVE is locked
behind a separate explicit arm confirmation and remains subject to each venue's
execution safeguards. The deployment `TRADING_MODE` value is only the fallback
when no dashboard setting has been saved.

### /markets
```
- Symbol list
- Current price
- Spread
- Session
- Market regime
- Active structure
```

### /candidates
```
- Live candidate feed
- Strategy
- Rule Score
- AI Score
- Status
- Click for detail
```

### /candidates/{id} (Detail)
```
- Strategy
- Rule Score
- Evidence list
- Market Context
- AI Score
- Risk Decision
- Outcome
```

### /trades
```
- Trade journal
- Entry/Exit prices
- P&L
- R-multiple
- Strategy
- Filters
```

### /strategies
```
- Strategy comparison
- Win rate
- Profit factor
- P&L
- By session
- By regime
```

### /backtests
```
- Backtest results
- Equity curve
- Metrics
- Comparison
```

### /risk
```
- Risk engine status
- Daily limits
- Drawdown
- Circuit breaker
- Kill switch
```

### /system
```
- MT5 connection
- Database health
- Worker status
- Logs
- Errors
```

## Tech Stack (Planned)

```
Frontend: Next.js + TypeScript
Charts: TradingView Lightweight Charts
UI: Tailwind CSS + shadcn/ui
Real-time: WebSocket
```

## Current Implementation

```
Streamlit (Python) — working prototype
Self-contained HTML — static reports
```

## Acceptance Criteria

- [ ] All pages implemented
- [ ] Real-time updates
- [ ] Mobile responsive
- [ ] Dark theme
- [ ] Authentication
