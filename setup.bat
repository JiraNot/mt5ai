@echo off
REM ╔══════════════════════════════════════════════════════════════╗
REM ║          🏦 Freebuff Trading Platform — Quick Setup         ║
REM ╚══════════════════════════════════════════════════════════════╝

echo.
echo 🏦 Freebuff Trading Platform Setup
echo ==================================
echo.

REM Check Python
echo 📋 Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Please install Python 3.11+
    pause
    exit /b 1
)
echo ✅ Python found

REM Create virtual environment
echo.
echo 📦 Creating virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo ✅ Virtual environment created
) else (
    echo ⚠️  Virtual environment already exists
)

REM Activate
call .venv\Scripts\activate.bat

REM Upgrade pip
echo.
echo 📦 Upgrading pip...
python -m pip install --upgrade pip -q

REM Install dependencies
echo.
echo 📦 Installing dependencies...
pip install -e "." -q

REM Install dev dependencies
echo.
echo 📦 Installing dev dependencies...
pip install pytest pytest-asyncio -q

REM Setup .env
echo.
echo ⚙️  Setting up configuration...
if not exist ".env" (
    copy .env.example .env >nul
    echo ✅ .env created from .env.example
    echo 📝 Edit .env with your MT5 credentials
) else (
    echo ⚠️  .env already exists
)

REM Seed demo data
echo.
echo 🌱 Seeding demo data...
python scripts/seed_demo_data.py --trades 100 --clear

REM Run tests
echo.
echo 🧪 Running tests...
python -m pytest tests/ -q

REM Done
echo.
echo ==================================
echo ✅ Setup complete!
echo.
echo 🚀 Quick Start:
echo    .venv\Scripts\activate
echo    python -m src.app
echo    streamlit run src/dashboard\app.py
echo    python -m pytest tests/ -q
echo.
echo 📖 Read README.md for more details
echo.
pause
