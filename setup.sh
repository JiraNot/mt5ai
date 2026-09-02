#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║          🏦 Freebuff Trading Platform — Quick Setup         ║
# ╚══════════════════════════════════════════════════════════════╝

set -e

echo ""
echo "🏦 Freebuff Trading Platform Setup"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check Python
echo "📋 Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 not found. Please install Python 3.11+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}✅ Python ${PYTHON_VERSION}${NC}"

# Check if version is >= 3.11
if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo -e "${GREEN}✅ Python version OK${NC}"
else
    echo -e "${RED}❌ Python 3.11+ required (found ${PYTHON_VERSION})${NC}"
    exit 1
fi

# Create virtual environment
echo ""
echo "📦 Creating virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
else
    echo -e "${YELLOW}⚠️  Virtual environment already exists${NC}"
fi

# Activate
source .venv/bin/activate

# Upgrade pip
echo ""
echo "📦 Upgrading pip..."
pip install --upgrade pip -q

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip install -e "." -q

# Install dev dependencies
echo ""
echo "📦 Installing dev dependencies..."
pip install pytest pytest-asyncio pytest-asyncio -q

# Setup .env
echo ""
echo "⚙️  Setting up configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✅ .env created from .env.example${NC}"
    echo -e "${YELLOW}📝 Edit .env with your MT5 credentials${NC}"
else
    echo -e "${YELLOW}⚠️  .env already exists${NC}"
fi

# Seed demo data
echo ""
echo "🌱 Seeding demo data..."
python scripts/seed_demo_data.py --trades 100 --clear 2>/dev/null || echo -e "${YELLOW}⚠️  Demo data seeding skipped${NC}"

# Run tests
echo ""
echo "🧪 Running tests..."
python -m pytest tests/ -q 2>/dev/null && echo -e "${GREEN}✅ All tests passed${NC}" || echo -e "${YELLOW}⚠️  Some tests failed${NC}"

# Done
echo ""
echo "=================================="
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "🚀 Quick Start:"
echo "   source .venv/bin/activate"
echo "   python -m src.app          # Run platform"
echo "   streamlit run src/dashboard/app.py  # Dashboard"
echo "   python -m pytest tests/ -q  # Run tests"
echo ""
echo "📖 Read README.md for more details"
echo ""
