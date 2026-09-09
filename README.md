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

# System status (mode, strategies, session)
python -m src.app --status

# Backtest
python -m src.app --backtest

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
| **MT5 Bridge Mode** | Real MT5 on a separate Windows machine, over HTTP |
| **181 Tests** | Unit + integration tests |
| **Demo Data** | Pre-seeded 100 trades |

### 🔌 MT5 Connection Modes

Set `MT5_MODE` in `.env`:

| Mode | Behavior |
|------|----------|
| `local` (default) | `MetaTrader5` package directly — Windows (or Wine). Without it, MT5 features are mocked (safe paper mode). |
| `bridge` | Connects to a standalone [mt5-bridge](https://github.com/JiraNot/mt5-bridge) server on the Windows machine hosting the real MT5 terminal — real data and order execution from a Linux server. |

```ini
MT5_MODE=bridge
BRIDGE_URL=http://100.x.y.z:8900   # Tailscale/WireGuard IP recommended
BRIDGE_TOKEN=your-shared-secret
```

Full setup guide: [docs/bridge_deployment.md](docs/bridge_deployment.md).

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

# ดูสถานะระบบ (โหมด, กลยุทธ์, session)
python -m src.app --status

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
| **MT5 Bridge Mode** | ต่อ MT5 จริงบนเครื่อง Windows แยก ผ่าน HTTP |
| **181 Tests** | Unit + integration tests |
| **ข้อมูล Demo** | มีข้อมูลเทรด 100 รายการให้ลอง |

### 🏗️ สถาปัตยกรรม

```
ข้อมูล MT5 → โครงสร้างตลาด → Strategy Plugins → AI Scorer → Risk Engine → MT5 Execution
```

### 📁 โครงสร้างโปรเจกต์

```
src/
├── core/           # Types, config, events, logging
├── market/         # เชื่อมต่อ MT5 (local/bridge), ดึงข้อมูล
├── structure/      # โครงสร้างตลาด (BOS, CHoCH, FVG, OB)
├── strategies/     # 3 strategy plugins
├── ai/             # ชั้น AI scoring
├── risk/           # Risk Engine (ผู้มีอำนาจสูงสุด)
├── execution/      # จัดการคำสั่งซื้อขาย
├── storage/        # โมเดลฐานข้อมูล
├── analytics/      # Backtesting
└── dashboard/      # Streamlit UI
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

### 🔌 โหมดการเชื่อมต่อ MT5

ตั้ง `MT5_MODE` ใน `.env`: `local` (MT5 บนเครื่องนี้/Wine, ไม่มีจริง = mock) หรือ `bridge`
(ต่อ MT5 จริงบน Windows ผ่านโปรเจกต์แยก [mt5-bridge](https://github.com/JiraNot/mt5-bridge)) —
ดูคู่มือที่ [docs/bridge_deployment.md](docs/bridge_deployment.md)

---

## License / ลิขสิทธิ์

Proprietary — Freebuff Team
