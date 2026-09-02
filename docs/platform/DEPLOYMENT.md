# Deployment

## Overview

ระบบ部署 2 ส่วน: Trading Node (Windows) และ Server (Linux)

## Trading Node (Windows)

```
Windows Trading Node
├── MetaTrader 5 Terminal
├── Python Trading Worker
└── MT5 Gateway
```

## Server (Linux)

```
Server
├── FastAPI
├── PostgreSQL
├── Redis (optional)
├── Worker
├── Dashboard
└── Analytics
```

## Docker

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://...
    
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
  
  dashboard:
    build: .
    command: streamlit run src/dashboard/app.py
    ports:
      - "8501:8501"
```

## CI/CD

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -e ".[dev]"
      - run: pytest tests/
```

## Environment Separation

```
DEV:     Local development
TEST:    Automated testing
PAPER:   Paper trading
DEMO:    Demo account
LIVE:    Real trading (locked)
```

## Acceptance Criteria

- [ ] Docker compose working
- [ ] CI pipeline running
- [ ] Environment separation clear
- [ ] Deployment documented
