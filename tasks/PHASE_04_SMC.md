# PHASE 04 — SMC Engine

## Objective

สร้าง Smart Money Concept components: FVG, Order Block, Liquidity, Regime

## Tasks

### TASK 0401: FVG Detection

- [ ] Bullish FVG
- [ ] Bearish FVG
- [ ] Size filter (ATR)

**Acceptance:**
- FVG detected correctly

---

### TASK 0402: FVG Lifecycle

- [ ] ACTIVE state
- [ ] Mitigation tracking
- [ ] FILLED state
- [ ] INVALIDATED state

**Acceptance:**
- State transitions working

---

### TASK 0403: Order Block

- [ ] Bullish OB detection
- [ ] Bearish OB detection
- [ ] Strength scoring

**Acceptance:**
- OB detected correctly

---

### TASK 0404: OB Lifecycle

- [ ] Mitigation tracking
- [ ] Invalidation detection
- [ ] Caused BOS/CHoCH tracking

**Acceptance:**
- OB lifecycle working

---

### TASK 0405: Liquidity Zones

- [ ] Swing liquidity
- [ ] Equal High/Low
- [ ] Previous Day levels
- [ ] Session levels

**Acceptance:**
- Liquidity zones detected

---

### TASK 0406: Equal High/Low

- [ ] Tolerance-based detection
- [ ] ATR-based tolerance

**Acceptance:**
- Equal levels detected

---

### TASK 0407: Sweep

- [ ] Sell-side sweep
- [ ] Buy-side sweep
- [ ] Sweep strength scoring

**Acceptance:**
- Sweep detection working

---

### TASK 0408: Premium/Discount

- [ ] Dealing range calculation
- [ ] Zone classification
- [ ] Score bonus

**Acceptance:**
- Premium/Discount working

---

### TASK 0409: Market Regime

- [ ] ADX calculation
- [ ] ATR percentile
- [ ] Choppiness index
- [ ] Regime classification

**Acceptance:**
- Regime detection working

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 0401 | ✅ Done | |
| 0402 | ✅ Done | |
| 0403 | ✅ Done | |
| 0404 | ✅ Done | |
| 0405 | ✅ Done | |
| 0406 | ✅ Done | |
| 0407 | ✅ Done | |
| 0408 | ✅ Done | |
| 0409 | ✅ Done | |
