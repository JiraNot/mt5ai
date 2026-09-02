# 🏦 Freebuff Trading Platform

AI-powered Trading Decision Platform for MetaTrader 5.

**[English](#english) | [ภาษาไทย](#ภาษาไทย)**

---

## English

### ⚡ Quick Install (One Command)

**Windows:**
```cmd
setup.bat
```

**Linux/Mac:**
```bash
chmod +x setup.sh && ./setup.sh
```

**Or manually:**
```bash
pip install -e .
```

### 🚀 Run

```bash
# Run trading platform
python -m src.app

# Run dashboard
streamlit run src/dashboard/app.py

# Or use Makefile
make run          # Run platform
make dashboard    # Run dashboard
make test         # Run tests
make help         # See all commands
```

### 📋 What You Get

| Feature | Description |
|---------|-------------|
| **3 Strategies** | CHoCH+OB, FVG Reversal, Breakout Retest |
| **Risk Engine** | Circuit breaker, filters, position sizing |
| **AI Scoring** | Rule-based context analysis |
| **Dashboard** | Interactive Streamlit UI |
| **166 Tests** | Unit + integration tests |
| **Demo Data** | Pre-seeded 100 trades |

### 🏗️ Architecture

```
MT5 Data → Market Structure → Strategy Plugins → AI Scorer → Risk Engine → MT5 Execution
```

### 📁 Project Structure

```
src/
├── core/           # Types, config, events, logging
├── market/         # MT5 connection, data feed
├── structure/      # Market structure (BOS, CHoCH, FVG, OB)
├── strategies/     # 3 strategy plugins
├── ai/             # AI scoring layer
├── risk/           # Risk engine (supreme authority)
├── execution/      # Order management
├── storage/        # Database models
├── analytics/      # Backtesting
└── dashboard/      # Streamlit UI
```

### ⚠️ Risk Engine

The Risk Engine is the **supreme authority** — AI cannot override it.

- Position sizing: 1% risk per trade
- Max daily loss: 3%
- Circuit breaker: 5% drawdown → emergency stop
- Spread filter: max 5 pips
- Session filter: London, New York, Overlap only

### 🧪 Testing

```bash
make test           # All tests
make test-unit      # Unit tests only
make test-integration  # Integration tests
python -m pytest tests/ -q  # Direct
```

### 📊 Dashboard

```bash
make dashboard      # Start Streamlit
# Open http://localhost:8501
```

Features:
- Equity curve
- Strategy performance comparison
- Trade journal with filters
- Setup analysis (traded/skipped/rejected)
- Risk management view

### 🎯 Trading Mode

**Default: Paper Trading**

Real money trading requires explicit configuration.

---

## ภาษาไทย

### ⚡ ติดตั้งง่าย (คำสั่งเดียว)

**Windows:**
```cmd
setup.bat
```

**Linux/Mac:**
```bash
chmod +x setup.sh && ./setup.sh
```

**หรือติดตั้งเอง:**
```bash
pip install -e .
```

### 🚀 วิธีรัน

```bash
# รันระบบเทรด
python -m src.app

# รัน dashboard
streamlit run src/dashboard/app.py

# หรือใช้ Makefile
make run          # รันระบบ
make dashboard    # รัน dashboard
make test         # รัน tests
make help         # ดูคำสั่งทั้งหมด
```

### 📋 สิ่งที่ได้

| ฟีเจอร์ | รายละเอียด |
|---------|------------|
| **3 กลยุทธ์** | CHoCH+OB, FVG Reversal, Breakout Retest |
| **Risk Engine** | Circuit breaker, filters, คำนวณขนาด position |
| **AI Scoring** | วิเคราะห์บริบทแบบ rule-based |
| **Dashboard** | Streamlit UI แบบ interactive |
| **166 Tests** | Unit + integration tests |
| **ข้อมูล Demo** | มีข้อมูลเทรด 100 รายการให้ลอง |

### 🏗️ สถาปัตยกรรม

```
ข้อมูล MT5 → โครงสร้างตลาด → Strategy Plugins → AI Scorer → Risk Engine → MT5 Execution
```

### 📁 โครงสร้างโปรเจกต์

```
src/
├── core/           # _types, config, events, logging_
├── market/         # _เชื่อมต่อ MT5, ดึงข้อมูล_
├── structure/      # _โครงสร้างตลาด (BOS, CHoCH, FVG, OB)_
├── strategies/     # _3 strategy plugins_
├://ai/             # _ชั้น AI scoring_
├── risk/           # _Risk Engine (ผู้มีอำนาจสูงสุด)_
├── execution/      # _จัดการคำสั่งซื้อขาย_
├── storage:        # _โมเดลฐานข้อมูล_
├── analytics/      # _Backtesting_
└── dashboard/      # _Streamlit UI_
```

### ⚠️ ระบบจัดการความเสี่ยง

Risk Engine เป็น **ผู้มีอำนาจสูงสุด** — AI ไม่สามารถ override ได้

- ขนาด Position: ความเสี่ยง 1% ต่อเทรด
- ขาดทุนสูงสุดต่อวัน: 3%
- Circuit Breaker: ขาดทุน 5% → หยุดฉุกเฉิน
- ตัวกรอง Spread: สูงสุด 5 pips
- ตัวกรอง Session: เทรดได้เฉพาะ London, New York, Overlap

### 🧪 การทดสอบ

```bash
make test           # ทดสอบทั้งหมด
make test-unit      # Unit tests เท่านั้น
make test-integration  # Integration tests
python -m pytest tests/ -q  # รันตรงๆ
```

### 📊 Dashboard

```bash
make dashboard      # เริ่ม Streamlit
# เปิดที่ http://localhost:8501
```

ฟีเจอร์:
- Equity curve
- เปรียบเทียบประสิทธิภาพกลยุทธ์
- Trade journal พร้อม filters
- วิเคราะห์ setups (traded/skipped/rejected)
- มุมมอง Risk Management

### 🎯 โหมดการเทรด

**ค่าเริ่มต้น: Paper Trading**

การเทรดด้วยเงินจริงต้องมีการตั้งค่าโดยเฉพาะ

---

## License / ลิขสิทธิ์

Proprietary — Freebuff Team
