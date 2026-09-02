# PHASE 02 — Market Data

## Objective

สร้าง Market Data Engine ที่จัดการ candles, spread, session

## Tasks

### TASK 0201: Candle Models

- [ ] Create Candle Pydantic model
- [ ] Create SymbolInfo model
- [ ] Create Tick model

**Acceptance:**
- Models validated correctly

---

### TASK 0202: Multi-Timeframe Cache

- [ ] Create candle cache
- [ ] Thread-safe access
- [ ] Cache invalidation

**Acceptance:**
- H1/M15/M5 synchronized

---

### TASK 0203: New Candle Detection

- [ ] Detect new candle close
- [ ] Event emission
- [ ] Deduplication

**Acceptance:**
- Closed candles processed once only

---

### TASK 0204: Historical Loader

- [ ] Load historical candles
- [ ] Bulk insert
- [ ] Gap detection

**Acceptance:**
- Historical data loaded correctly

---

### TASK 0205: Spread Tracking

- [ ] Current spread
- [ ] Spread percentile
- [ ] Abnormal spread detection

**Acceptance:**
- Spread tracking working

---

### TASK 0206: Session Clock

- [ ] Session detection (Asia/London/NY)
- [ ] Session high/low
- [ ] DST handling

**Acceptance:**
- Session detection working

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 0201 | ✅ Done | |
| 0202 | ✅ Done | |
| 0203 | ⚠️ Partial | |
| 0204 | ✅ Done | Yahoo Finance |
| 0205 | ✅ Done | |
| 0206 | ✅ Done | |
