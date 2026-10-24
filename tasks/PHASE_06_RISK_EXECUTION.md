# PHASE 06 — Risk & Execution

## Objective

สร้าง Risk Engine และ Execution Engine

## Tasks

### TASK 0601: Risk State

- [ ] Daily P&L tracking
- [ ] Weekly P&L tracking
- [ ] Drawdown calculation

**Acceptance:**
- Risk state accurate

---

### TASK 0602: Daily Limit

- [ ] Max daily loss enforcement
- [ ] Daily lock trigger

**Acceptance:**
- Daily limit enforced

---

### TASK 0603: Weekly Limit

- [ ] Max weekly loss enforcement

**Acceptance:**
- Weekly limit enforced

---

### TASK 0604: Position Size

- [ ] Risk-based position sizing
- [ ] Symbol specification
- [x] Lot step validation against Binance market filters; floor quantity without exceeding risk budget

**Acceptance:**
- Position size correct

---

### TASK 0605: Minimum RR

- [ ] RR calculation
- [ ] Minimum threshold

**Acceptance:**
- RR enforcement working

---

### TASK 0606: Trade Limit

- [ ] Max trades per day
- [ ] Max concurrent positions

**Acceptance:**
- Trade limits enforced

---

### TASK 0607: Consecutive Losses

- [ ] Loss streak tracking
- [ ] Pause trigger

**Acceptance:**
- Consecutive loss protection working

---

### TASK 0610: Execution State Machine

- [ ] CREATED → VALIDATED → SUBMITTED → FILLED → ACTIVE → CLOSED
- [ ] Error states

**Acceptance:**
- State machine working

---

### TASK 0611: Duplicate Protection

- [ ] Execution key generation
- [ ] Duplicate detection

**Acceptance:**
- Duplicate protection working

---

### TASK 0612: Broker Validation

- [ ] Pre-flight checks
- [ ] Market open check
- [ ] Symbol tradable check

**Acceptance:**
- Pre-flight checks working

---

### TASK 0613: Kill Switch

- [ ] Trigger conditions
- [ ] Level escalation
- [ ] Manual reset

**Acceptance:**
- Kill switch working

---

### TASK 0620: Position Manager

- [ ] Fixed SL/TP
- [ ] Break-even move
- [ ] Time exit

**Acceptance:**
- Position management working

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 0601 | ✅ Done | |
| 0602 | ✅ Done | |
| 0603 | ✅ Done | |
| 0604 | ✅ Done | |
| 0605 | ✅ Done | |
| 0606 | ✅ Done | |
| 0607 | ✅ Done | |
| 0610 | ✅ Done | |
| 0611 | ✅ Done | |
| 0612 | ⚠️ Partial | Testnet safeguards implemented; end-to-end fill still needs confirmation |
| 0613 | ✅ Done | |
| 0620 | ✅ Done | |

## Binance Testnet Hardening (2026-10-24)

- [x] Route conditional SL/TP through Binance `/fapi/v1/algoOrder`.
- [x] Validate supported symbol, One-way mode, Testnet host, exchange tick/lot rules, and available margin.
- [x] Install Isolated margin and configured leverage before a new entry.
- [x] Flatten immediately if server-side SL placement fails; keep DEMO execution fail-closed.
- [x] Implement reduce-only position close and replace-first server-side stop modification.
- [ ] Confirm one automated Testnet fill and broker-side SL through the deployed worker.

Task 0612 remains partial until the Testnet fill and protection are observed in the deployment.
