# ADR-002: PostgreSQL Database

## Status

Accepted

## Context

ต้องเลือก database สำหรับเก็บ trade history, market data, และ configuration

## Decision

ใช้ **PostgreSQL** เป็น database หลัก, **SQLite** สำหรับ development/testing

## Rationale

### ข้อดี

1. **ACID Compliance**: สำคัญมากสำหรับ financial data
2. **JSONB Support**: เก็บ market context, evidence ได้
3. **Full-text Search**: ค้นหา trade logs ได้
4. **Scalability**: ขยายได้เมื่อมีข้อมูลมาก
5. **Docker Support**: ตั้งง่าย

### ข้อเสีย

1. **Setup**: ต้องตั้ง server (แก้ด้วย Docker)
2. **Complexity**: มากกว่า SQLite (trade-off ที่ยอมรับได้)

## Consequences

- Production ใช้ PostgreSQL 16
- Development ใช้ SQLite (ง่ายกว่า)
- Alembic สำหรับ migrations
- SQLAlchemy ORM สำหรับ data access
- ต้องมี backup strategy

## Alternatives Considered

- **SQLite**: ง่ายแต่ไม่เหมาะกับ production (no concurrent writes)
- **MySQL**: ใช้ได้แต่ PostgreSQL มี JSONB support ดีกว่า
- **MongoDB**: Flexible แต่ไม่เหมาะกับ financial data (ACID สำคัญ)
