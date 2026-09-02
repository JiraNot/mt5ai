# Project Vision

## Mission

สร้างระบบ Automated Trading Platform สำหรับ MetaTrader 5 ที่สามารถ:

- อ่านตลาด (Market Data)
- วิเคราะห์ Market Structure (Swing, BOS, CHoCH, FVG, OB, Liquidity)
- ตรวจจับ Trading Setup จากหลายกลยุทธ์
- ใช้ AI ช่วยประเมินคุณภาพของ Setup
- ควบคุม Risk อย่างเข้มงวด
- Execute ผ่าน MT5
- เก็บผล Trade ทุกรายการ
- Backtest และวิเคราะห์ Strategy
- เรียนรู้จากข้อมูลจริง (ML)

เป้าหมายไม่ใช่สร้างเพียง EA ตัวเดียว แต่สร้าง Trading Platform ที่สามารถเพิ่ม Strategy, Symbol, Model และ Broker ได้ในอนาคต

## Core Principles

### Deterministic First
ทุก Decision ต้องอธิบายได้ด้วยข้อมูล ไม่ใช่ feeling

### Data Second
ทุก Trade ต้องเก็บเป็นข้อมูล ทั้งที่เปิดจริงและที่ปฏิเสธ

### AI Third
AI เป็นผู้ช่วยประเมิน ไม่ใช่ผู้ตัดสินใจหลัก

### Risk Always First
Risk Engine มี Authority สูงสุด ไม่มีใคร override ได้

## System Capabilities

| Capability | Status |
|------------|--------|
| Backtest | ✅ Working |
| Replay | ❌ Planned |
| Paper Trading | ✅ Working |
| Demo Trading | ⚠️ Needs MT5 |
| Live Trading | ❌ Locked |
| AI Scoring | ⚠️ Rule-based only |
| ML Model | ⚠️ Feature engine ready |
| Trade Journal | ✅ Working |
| Analytics | ✅ Basic |
| Strategy Comparison | ✅ Working |
| Risk Management | ✅ Working |
| Portfolio Management | ❌ Planned |
| Multi-symbol | ❌ Planned |
| Multi-timeframe | ✅ Working |

## Non-Goals of MVP

ระบบ MVP ไม่ทำ:

- HFT (High-Frequency Trading)
- Scalping ระดับ millisecond
- Reinforcement Learning
- AI vision เป็น engine หลัก
- Martingale
- Grid recovery
- Copy Trading
- Multi-broker
- Multi-user SaaS

## Target Instruments (MVP)

```yaml
symbol: XAUUSD
timeframes:
  bias: H1
  structure: M15
  entry: M5
```

## Target Strategies (MVP)

1. CHoCH + Order Block (Primary)
2. FVG Retracement
3. Breakout Retest

## Success Metrics

### Milestone A — Trading Research Core
- [ ] Historical XAUUSD data loaded
- [ ] Market Structure detection working
- [ ] CHoCH + OB Strategy backtested
- [ ] Positive expectancy demonstrated

### Milestone B — Safe Automation
- [ ] Rule Strategy working
- [ ] Risk Engine validated
- [ ] MT5 Demo trading functional
- [ ] Trade Journal complete

### Milestone C — Intelligence Layer
- [ ] Paper trading history collected
- [ ] Candidate Dataset built
- [ ] AI Shadow Mode running
- [ ] ML Model trained and validated
- [ ] Ensemble scoring deployed

## Long-term Vision

เมื่อระบบโตเต็มที่ ระบบจะสามารถตอบได้ว่า:

```
ตลาดตอนนี้เป็น Regime อะไร
Strategy ไหนเหมาะ
Setup ไหนมีคุณภาพ
ควรเสี่ยงหรือไม่
ผลย้อนหลังของ setup แบบนี้เป็นอย่างไร
AI ช่วยหรือทำลาย performance
Symbol / Session ใดมี Edge จริง
```

ทุก Decision สามารถย้อนดูเหตุผลและข้อมูลต้นทางได้
