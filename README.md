# 🏦 Freebuff Trading Platform

AI-powered Trading Decision Platform for MetaTrader 5.

**[English](#english) | [ภาษาไทย](#ภาษาไทย)**

---

## English

### Architecture

```
MT5 Data → Market Structure → Strategy Plugins → AI Scorer → Risk Engine → MT5 Execution
                                    ↑                                ↓
                              Multi-strategy                   Trade Journal
                              voting                          & Analytics
```

### Quick Start

```bash
# 1. Clone and setup
cp .env.example .env
# Edit .env with your MT5 credentials

# 2. Install dependencies
pip install -e .

# 3. Start infrastructure (optional — SQLite works without Docker)
docker-compose up -d

# 4. Run the platform
python -m src.app

# 5. Check status
python -m src.app --status
```

### Project Structure

```
src/
├── core/           # Types, config, events, logging
├── market/         # MT5 connection, data feed, sessions
├── structure/      # Market structure analysis (BOS, CHoCH, FVG, OB)
├── strategies/     # Strategy plugin system (3 strategies)
├── ai/             # AI decision layer (rule-based scoring)
├── risk/           # Risk engine (filters, limits, circuit breaker)
├── execution/      # Order management
├── storage/        # Database models + repository
├── analytics/      # Backtesting engine
└── dashboard/      # Streamlit interactive dashboard
```

### Strategies

| Strategy | Description | Status |
|----------|-------------|--------|
| **CHoCH + Order Block** | Highest-probability setup: CHoCH reversal + OB/FVG overlap | ✅ |
| **FVG Reversal** | Fair Value Gap with HTF alignment + liquidity sweep | ✅ |
| **Breakout Retest** | Breakout + retest of key level with confirmation | ✅ |

### Risk Engine

The Risk Engine is the **supreme authority** — AI cannot override it.

- **Position Sizing**: Fixed risk % per trade (default 1%)
- **Max Daily Loss**: 3% of account balance
- **Circuit Breaker**: Emergency stop at 5% drawdown
- **Spread Filter**: Max 5 pips
- **Session Filter**: London, New York, Overlap only
- **Consecutive Loss Limit**: Max 3 in a row

### Testing

```bash
# Run all tests (166 tests)
python -m pytest tests/ -q

# Run unit tests only
python -m pytest tests/unit/ -q

# Run integration tests
python -m pytest tests/integration/ -q

# Generate demo data
python scripts/seed_demo_data.py --trades 100

# Generate HTML dashboard
python scripts/dashboard.py
```

### Dashboard

```bash
# Start Streamlit interactive dashboard
streamlit run src/dashboard/app.py
# Open http://localhost:8501
```

### Trading Mode

**Default: Paper Trading**

The platform starts in paper mode. Real money trading requires explicit configuration.

---

## ภาษาไทย

### สถาปัตยกรรม (Architecture)

```
ข้อมูล MT5 → โครงสร้างตลาด → Strategy Plugins → AI Scorer → Risk Engine → MT5 Execution
                                    ↑                                ↓
                              Multi-strategy                   Trade Journal
                              voting                          & Analytics
```

### เริ่มต้นใช้งาน (Quick Start)

```bash
# 1. คัดลอกและตั้งค่า
cp .env.example .env
# แก้ไข .env ด้วยข้อมูล MT5 ของคุณ

# 2. ติดตั้ง dependencies
pip install -e .

# 3. เริ่ม infrastructure (ไม่จำเป็น — SQLite ทำงานได้โดยไม่ต้อง Docker)
docker-compose up -d

# 4. รันระบบ
python -m src.app

# 5. ตรวจสอบสถานะ
python -m src.app --status
```

### โครงสร้างโปรเจกต์ (Project Structure)

```
src/
├── core/           # _types, config, events, logging_
├── market/         # _เชื่อมต่อ MT5, ดึงข้อมูล, sessions_
├── structure/      # _วิเคราะห์โครงสร้างตลาด (BOS, CHoCH, FVG, OB)_
├── strategies/     # _ระบบ Strategy Plugin (3 strategies)_
├://ai/             # _ชั้น AI ตัดสินใจ (rule-based scoring)_
├── risk/           # _Risk Engine (filters, limits, circuit breaker)_
├── execution/      # _จัดการคำสั่งซื้อขาย_
├── storage:        # _โมเดลฐานข้อมูล + repository_
├── analytics/      # _Backtesting engine_
└── dashboard/      # _Streamlit dashboard แบบ interactive_
```

### กลยุทธ์การเทรด (Strategies)

| กลยุทธ์ | รายละเอียด | สถานะ |
|---------|------------|-------|
| **CHoCH + Order Block** | Setup ที่มีโอกาสสำเร็จสูงสุด: CHoCH reversal + OB/FVG overlap | ✅ |
| **FVG Reversal** | Fair Value Gap กับ HTF alignment + liquidity sweep | ✅ |
| **Breakout Retest** | Breakout + retest ของระดับสำคัญพร้อม confirmation | ✅ |

### ระบบจัดการความเสี่ยง (Risk Engine)

Risk Engine เป็น **ผู้มีอำนาจสูงสุด** — AI ไม่สามารถ override ได้

- **การคำนวณขนาด Position**: Fixed risk % ต่อเทรด (ค่าเริ่มต้น 1%)
- **ขาดทุนสูงสุดต่อวัน**: 3% ของยอดเงินในบัญชี
- **Circuit Breaker**: หยุดฉุกเฉินเมื่อขาดทุน 5%
- **ตัวกรอง Spread**: สูงสุด 5 pips
- **ตัวกรอง Session**: เทรดได้เฉพาะ London, New York, Overlap
- **จำกัดการขาดทุนติดต่อกัน**: สูงสุด 3 ครั้ง

### การทดสอบ (Testing)

```bash
# รัน tests ทั้งหมด (166 tests)
python -m pytest tests/ -q

# รัน unit tests เท่านั้น
python -m pytest tests/unit/ -q

# รัน integration tests
python -m pytest tests/integration/ -q

# สร้างข้อมูล demo
python scripts/seed_demo_data.py --trades 100

# สร้าง HTML dashboard
python scripts/dashboard.py
```

### Dashboard

```bash
# เริ่ม Streamlit dashboard แบบ interactive
streamlit run src/dashboard/app.py
# เปิดที่ http://localhost:8501
```

### โหมดการเทรด (Trading Mode)

**ค่าเริ่มต้น: Paper Trading**

ระบบเริ่มต้นในโหมด Paper Trading การเทรดด้วยเงินจริงต้องมีการตั้งค่าโดยเฉพาะ

### ค่าผลลัพธ์ (Demo Data)

```
จำนวนเทรด: 100 (Win Rate 53%, P&L $2,452)
จำนวน Setups: 133 (traded + skipped + rejected)
กลยุทธ์: choch_orderblock, fvg_reversal, breakout_retest
ช่วงวันที่: 2024-06-01 ถึง 2024-07-15
```

---

## License / ลิขสิทธิ์

Proprietary — Freebuff Team
