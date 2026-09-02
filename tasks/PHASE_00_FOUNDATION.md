# PHASE 00 — Foundation

## Objective

สร้าง project structure, config system, logging, และ database

## Tasks

### TASK 0001: Project Structure

- [ ] Create repository structure
- [ ] Create pyproject.toml
- [ ] Create .gitignore
- [ ] Create .env.example
- [ ] Create docker-compose.yml
- [ ] Create Makefile

**Acceptance:**
- Repository structure exists
- Python project runs
- pytest runs

---

### TASK 0002: Config System

- [ ] Create config YAML schema
- [ ] Implement Pydantic validation
- [ ] Environment variable override
- [ ] Config reload capability

**Acceptance:**
- YAML loaded correctly
- Pydantic validates
- Invalid config prevents startup

---

### TASK 0003: Logging

- [ ] Configure structlog
- [ ] Add correlation IDs
- [ ] JSON structured output
- [ ] Log rotation

**Acceptance:**
- Structured logs working
- Correlation IDs propagated

---

### TASK 0004: Database

- [ ] Create PostgreSQL setup
- [ ] Create Alembic migrations
- [ ] Create base models
- [ ] Health check endpoint

**Acceptance:**
- Migration works
- DB health check passes

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 0001 | ✅ Done | |
| 0002 | ✅ Done | |
| 0003 | ✅ Done | |
| 0004 | ✅ Done | SQLite for dev |

## Completed

Phase 00 is complete.
