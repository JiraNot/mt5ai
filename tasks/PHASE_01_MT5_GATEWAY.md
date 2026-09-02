# PHASE 01 — MT5 Gateway

## Objective

เชื่อมต่อ Python กับ MetaTrader 5 Terminal

## Tasks

### TASK 0101: Connect MT5 Terminal

- [ ] Initialize MT5 connection
- [ ] Handle connection errors
- [ ] Reconnection logic

**Acceptance:**
- Connect to demo MT5
- Handle disconnect gracefully

---

### TASK 0102: Read Account State

- [ ] Get account info
- [ ] Get balance, equity, margin
- [ ] Track changes

**Acceptance:**
- Read account correctly
- Update on change

---

### TASK 0103: Read Symbol Specification

- [ ] Get symbol info
- [ ] Digits, point, tick size
- [ ] Contract size, lot limits

**Acceptance:**
- Read XAUUSD spec correctly

---

### TASK 0104: Read Candles

- [ ] Get historical candles
- [ ] Get latest candles
- [ ] Multi-timeframe support

**Acceptance:**
- Read H1/M15/M5 candles

---

### TASK 0105: Read Ticks

- [ ] Get tick data
- [ ] Real-time tick subscription

**Acceptance:**
- Read ticks correctly

---

### TASK 0106: Read Positions

- [ ] Get open positions
- [ ] Get pending orders
- [ ] Track changes

**Acceptance:**
- Read positions correctly

---

### TASK 0107: Demo Order Abstraction

- [ ] Create order intent
- [ ] Validate before send
- [ ] Handle response

**Acceptance:**
- Open controlled demo trade

---

### TASK 0108: Close/Modify Order

- [ ] Close position
- [ ] Modify SL/TP
- [ ] Handle partial close

**Acceptance:**
- SL/TP works
- Close trade works

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 0101 | ⚠️ Mock | MT5 not installed |
| 0102 | ⚠️ Mock | |
| 0103 | ⚠️ Mock | |
| 0104 | ⚠️ Mock | |
| 0105 | ⚠️ Mock | |
| 0106 | ⚠️ Mock | |
| 0107 | ⚠️ Mock | |
| 0108 | ⚠️ Mock | |

## Blockers

- MT5 Terminal not installed on dev machine
- Need Windows machine for real testing
