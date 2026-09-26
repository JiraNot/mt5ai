# Dashboard

## Overview

Dashboard แสดงผล real-time ของระบบ trading

## Pages

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
