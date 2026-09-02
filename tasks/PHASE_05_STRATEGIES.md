# PHASE 05 — Strategy Framework

## Objective

สร้าง Strategy Plugin System + 3 strategies

## Tasks

### TASK 0501: Strategy Interface

- [ ] Create base TradingStrategy class
- [ ] Define detect/score/invalidate methods
- [ ] Strategy registry

**Acceptance:**
- Interface implemented
- Registry working

---

### TASK 0502: TradeCandidate

- [ ] Create TradeCandidate model
- [ ] Lifecycle states
- [ ] Evidence schema

**Acceptance:**
- Schema validated
- Lifecycle working

---

### TASK 0503: Evidence Schema

- [ ] Evidence code system
- [ ] Score per evidence
- [ ] Reason codes

**Acceptance:**
- Evidence logged correctly

---

### TASK 0504: Scoring Engine

- [ ] Base score = 50
- [ ] Positive/negative evidence
- [ ] Score clamping (0-100)

**Acceptance:**
- Scoring accurate

---

### TASK 0505: Candidate Lifecycle

- [ ] CREATED → AI_EVALUATED → RISK_EVALUATED → APPROVED
- [ ] REJECTED / EXPIRED / CANCELLED

**Acceptance:**
- Lifecycle working

---

### TASK 0510: CHoCH + OB Strategy

- [ ] LONG setup detection
- [ ] SHORT setup detection
- [ ] Entry/SL/TP calculation
- [ ] Score calculation

**Acceptance:**
- Strategy detects correctly
- Score threshold working

---

### TASK 0520: FVG Retracement

- [ ] LONG setup detection
- [ ] SHORT setup detection
- [ ] Entry at FVG level
- [ ] Regime integration

**Acceptance:**
- Strategy detects correctly
- Regime filter working

---

### TASK 0530: Breakout Retest

- [ ] LONG setup detection
- [ ] SHORT setup detection
- [ ] Retest detection
- [ ] Extension filter

**Acceptance:**
- Strategy detects correctly

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 0501 | ✅ Done | |
| 0502 | ✅ Done | |
| 0503 | ✅ Done | |
| 0504 | ✅ Done | |
| 0505 | ✅ Done | |
| 0510 | ✅ Done | |
| 0520 | ✅ Done | |
| 0530 | ⚠️ Needs work | Never triggers on real data |
