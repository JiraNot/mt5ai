# PHASE 07 — Backtest

## Objective

สร้าง Backtest Engine ที่ใช้ domain logic เดียวกับ live

## Tasks

### TASK 0701: Historical Event Loop

- [ ] Candle-by-candle processing
- [ ] Event emission
- [ ] State management

**Acceptance:**
- Event loop working

---

### TASK 0702: Simulated Broker

- [ ] Order execution simulation
- [ ] Position tracking
- [ ] P&L calculation

**Acceptance:**
- Simulated broker working

---

### TASK 0703: Spread Model

- [ ] Fixed spread
- [ ] Variable spread (ATR-based)
- [ ] Historical spread

**Acceptance:**
- Spread model working

---

### TASK 0704: Commission Model

- [ ] Per lot commission
- [ ] Per trade commission

**Acceptance:**
- Commission deducted correctly

---

### TASK 0705: Slippage Model

- [ ] Fixed slippage
- [ ] Random slippage

**Acceptance:**
- Slippage applied correctly

---

### TASK 0706: Position Simulation

- [ ] SL hit detection
- [ ] TP hit detection
- [ ] Pessimistic fill

**Acceptance:**
- Position simulation working

---

### TASK 0707: Metrics

- [ ] All mandatory metrics
- [ ] MFE/MAE tracking
- [ ] Strategy comparison

**Acceptance:**
- Metrics calculated correctly

---

### TASK 0708: Report

- [ ] Backtest report generation
- [ ] Trade list
- [ ] Equity curve

**Acceptance:**
- Report generated

---

### TASK 0709: Walk Forward

- [ ] Data split
- [ ] Rolling window
- [ ] Overfitting detection

**Acceptance:**
- Walk-forward working

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 0701 | ✅ Done | Basic version |
| 0702 | ⚠️ Basic | |
| 0703 | ✅ Done | |
| 0704 | ✅ Done | |
| 0705 | ✅ Done | |
| 0706 | ⚠️ Basic | |
| 0707 | ✅ Done | |
| 0708 | ✅ Done | |
| 0709 | ❌ Not done | |
