# ADR-001: Python Trading Core

## Status

Accepted

## Context

ต้องเลือกภาษาสำหรับ Trading Engine ที่เชื่อมต่อกับ MetaTrader 5

## Decision

ใช้ **Python 3.12+** เป็นภาษาหลักของ Trading Engine

## Rationale

### ข้อดี

1. **MT5 Integration**: MetaQuotes มี Python package อย่างเป็นทางการ (`MetaTrader5`)
2. **Data Science Ecosystem**: pandas, NumPy, scikit-learn, LightGBM, XGBoost, PyTorch
3. **Rapid Development**: เขียนเร็ว, debug ง่าย
4. **Library Support**: FastAPI, SQLAlchemy, Pydantic
5. **ML/AI Ready**: ต่อยอดไป ML pipeline ได้ง่าย

### ข้อเสีย

1. **Performance**: ช้ากว่า C++/Rust สำหรับ HFT (ไม่ใช่เป้าหมาย)
2. **GIL**: Thread limitation (ใช้ async แก้)
3. **Type Safety**: ต้องใช้ type hints + mypy

## Consequences

- Trading Engine ทั้งหมดเขียนด้วย Python
- MT5 Gateway ใช้ `MetaTrader5` Python package
- Backtester ใช้ pandas สำหรับ data processing
- ML pipeline ใช้ scikit-learn / LightGBM
- API ใช้ FastAPI
- Dashboard ใช้ Streamlit (ปัจจุบัน) → Next.js (อนาคต)

## Alternatives Considered

- **C++**: Performance ดีแต่ development ช้า, MT5 binding ยุ่งยาก
- **Rust**: Performance ดีแต่ ecosystem ยังไม่ mature สำหรับ trading
- **MQL5**: ต้องรันบน MT5 terminal, ไม่สามารถใช้ Python ML libraries
