# Acceptance Tests

## Overview

Acceptance Tests ตรวจสอบว่าระบบทำงานตาม requirements

## Phase 0: Foundation

```
- [ ] Repository structure exists
- [ ] Python project runs
- [ ] pytest runs
- [ ] lint runs
- [ ] Config loaded and validated
- [ ] Logging working
- [ ] Database migration works
```

## Phase 1: MT5 Gateway

```
- [ ] Connect demo MT5
- [ ] Read XAUUSD data
- [ ] Open controlled demo trade
- [ ] SL works
- [ ] TP works
- [ ] Close trade
- [ ] Journal execution
```

## Phase 2: Market Data

```
- [ ] H1/M15/M5 synchronized
- [ ] Closed candles processed once only
- [ ] Spread tracking working
- [ ] Session detection working
```

## Phase 3: Structure Engine

```
- [ ] Swing detection accurate
- [ ] BOS detection working
- [ ] CHoCH detection working
- [ ] Displacement scoring working
- [ ] 30+ golden scenarios passing
```

## Phase 4: SMC Engine

```
- [ ] FVG detection working
- [ ] FVG lifecycle working
- [ ] Order Block detection working
- [ ] OB lifecycle working
- [ ] Liquidity zones detected
- [ ] Liquidity sweep working
- [ ] Premium/Discount working
- [ ] Market Regime working
```

## Phase 5: Strategies

```
- [ ] Strategy interface implemented
- [ ] TradeCandidate schema validated
- [ ] Evidence schema working
- [ ] Scoring engine working
- [ ] CHoCH+OB strategy working
- [ ] FVG strategy working
- [ ] Breakout strategy working
```

## Phase 6: Risk & Execution

```
- [ ] Risk state tracking
- [ ] Daily limit enforced
- [ ] Position size calculated
- [ ] Minimum RR enforced
- [ ] Trade limit enforced
- [ ] Consecutive losses tracked
- [ ] Execution state machine working
- [ ] Duplicate protection working
- [ ] Kill switch working
```

## Phase 7: Backtest

```
- [ ] Historical event loop working
- [ ] Simulated broker working
- [ ] Spread model working
- [ ] Commission model working
- [ ] Slippage model working
- [ ] Metrics calculated correctly
- [ ] Report generated
```

## Acceptance Criteria

- [ ] All phase tests passing
- [ ] No critical bugs
- [ ] Documentation updated
- [ ] Performance acceptable
