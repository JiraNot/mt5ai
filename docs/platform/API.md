# API Specification

## Overview

FastAPI backend สำหรับ Dashboard และ external integrations

## Endpoints

### System

```
GET  /api/health          - Health check
GET  /api/status          - System status
GET  /api/config          - Current config (safe fields only)
```

### Settings

```
GET  /api/settings              - Current runtime settings with secrets masked
POST /api/settings              - Persist runtime settings
POST /api/settings/binance/test - Read-only Binance Futures Demo/Testnet or Live account check
```

The Binance credential check selects the Demo/Testnet or Live credential pair
independently. Demo accepts the current `https://demo-fapi.binance.com` endpoint
and classic `https://testnet.binancefuture.com`; Live accepts only the exact
`https://fapi.binance.com` origin. Both checks read `/fapi/v2/account`, do not
persist submitted credentials, and never place orders. The Live check is
read-only; LIVE order execution remains disabled. Responses never include API
keys, secrets, signatures, or raw exchange error bodies. Safe Binance error
codes are returned separately to distinguish invalid keys, signatures, or clocks.

### Account

```
GET  /api/account         - Account info
GET  /api/account/equity  - Equity curve
GET  /api/account/daily   - Daily P&L
```

### Trades

```
GET  /api/trades          - List trades (with filters)
GET  /api/trades/{id}     - Trade detail
GET  /api/trades/stats    - Trade statistics
```

### Candidates

```
GET  /api/candidates      - List candidates
GET  /api/candidates/{id} - Candidate detail
GET  /api/candidates/feed - Live candidate feed
```

### Strategies

```
GET  /api/strategies              - List strategies
GET  /api/strategies/{id}/stats   - Strategy statistics
GET  /api/strategies/compare      - Compare strategies
```

### Risk

```
GET  /api/risk/status     - Risk engine status
GET  /api/risk/limits     - Current limits
GET  /api/risk/daily      - Daily risk usage
```

### Control

```
POST /api/control/stop    - Emergency stop
POST /api/control/pause   - Pause trading
POST /api/control/resume  - Resume trading
POST /api/control/close-all - Close all positions
```

## Authentication

```python
# JWT token required for all endpoints
# API key for programmatic access

headers = {
    "Authorization": "Bearer {jwt_token}"
}
```

## Rate Limiting

```
100 requests per minute (default)
50 requests per minute (control endpoints)
```

## Acceptance Criteria

- [ ] All endpoints implemented
- [ ] Authentication working
- [ ] Rate limiting working
- [ ] Error handling complete
- [ ] OpenAPI docs generated
