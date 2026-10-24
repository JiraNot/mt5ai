# PHASE 09 — Paper Trading

## Objective

รัน full pipeline แบบ paper trading เพื่อ validate ระบบ

## Tasks

### TASK 0901: Paper Trading Loop

- [x] Market data ingestion
- [x] Strategy evaluation
- [x] Latest closed candle reaches strategies without being dropped twice (2026-10-23)
- [x] Risk evaluation
- [x] Simulated execution

**Acceptance:**
- Paper trading running (`src/live/paper_loop.py` PaperTradingRunner + `PaperGateway`)

---

### TASK 0902: Signal Logging

- [x] Log all signals
- [x] Log all candidates
- [x] Log all decisions

**Acceptance:**
- Signals logged (`src/storage/trade_journal.py` TradeJournal + `src/storage/setup_logger.py`)

---

### TASK 0903: Outcome Tracking

- [x] Track open positions
- [x] Track P&L
- [x] Track metrics

**Acceptance:**
- Outcomes tracked (Real-time PnL, taker fee accounting 0.05%, MFE/MAE, R-multiple, hypothetical outcome tracking for rejected setups)

---

### TASK 0904: Report Generation

- [x] Daily report
- [x] Weekly report
- [x] Strategy comparison

**Acceptance:**
- Reports generated (`src/analytics/report_generator.py`: DailyReport, WeeklyReport, StrategyComparisonReport with Markdown & Dict export)

---

## Goals

```
เป้าหมายไม่ใช่กำไรทันที

เป้าหมาย:
- Validate system behavior
- Collect candidate data
- Test risk engine
- Verify strategy logic
```

## Acceptance Criteria

- [x] Paper trading runs 24/7 / continuous step-wise loop
- [x] No crashes (Fail-closed & exception resilience)
- [x] All candidates logged
- [x] Risk limits enforced (Broker-side SL, max drawdown, position sizing)
- [x] Metrics tracked
- [x] Runtime status records the timestamp and reason for the latest pipeline decision (2026-10-23)

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 0901 | ✅ Done | `PaperTradingRunner` in `src/live/paper_loop.py` |
| 0902 | ✅ Done | Comprehensive candidate & decision logging in `TradeJournal` |
| 0903 | ✅ Done | Position tracking, taker fees (0.05%), MFE/MAE, hypothetical evaluation |
| 0904 | ✅ Done | `ReportGenerator` with daily, weekly, and strategy comparison |
