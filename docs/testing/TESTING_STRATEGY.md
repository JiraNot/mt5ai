# Testing Strategy

## Overview

Testing Pyramid สำหรับ MT5 AI Trading Platform

## Testing Levels

```
                    ┌─────────────┐
                    │ E2E Tests   │  Slow, few
                    ├─────────────┤
                    │ Integration │  Medium
                    ├─────────────┤
                    │ Domain      │  Core logic
                    ├─────────────┤
                    │ Unit Tests  │  Fast, many
                    └─────────────┘
```

## Unit Tests

```
- Swing detection
- BOS/CHoCH detection
- FVG detection
- Order Block detection
- Liquidity detection
- Position sizing
- Risk calculations
- Score calculations
```

## Domain Tests

```
- Strategy detection end-to-end
- Market context building
- Candidate generation
- Risk evaluation flow
- Order state machine
```

## Golden Scenario Tests

```
- Known patterns with expected outcomes
- Regression prevention
- Algorithm stability
```

## Integration Tests

```
- Strategy → AI → Risk pipeline
- Backtest engine
- Database operations
- API endpoints
```

## E2E Tests (Paper Trading)

```
- Full pipeline with simulated data
- Position management
- Trade journal logging
```

## Test Commands

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Golden tests
pytest tests/golden/

# All tests
pytest tests/

# With coverage
pytest tests/ --cov=src
```

## Coverage Target

```
Core modules: > 90%
Strategies: > 80%
Risk engine: > 90%
Total: > 80%
```

## Acceptance Criteria

- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] Golden tests passing
- [ ] Coverage > 80%
- [ ] No critical bugs
