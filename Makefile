# ╔══════════════════════════════════════════════════════════════╗
# ║          🏦 Freebuff Trading Platform — Makefile             ║
# ╚══════════════════════════════════════════════════════════════╝

.PHONY: help setup run dashboard test seed clean install

# Default target
help:
	@echo ""
	@echo "🏦 Freebuff Trading Platform"
	@echo "============================"
	@echo ""
	@echo "📋 Setup & Install:"
	@echo "  make setup       - One-click setup (install + seed + test)"
	@echo "  make install     - Install dependencies only"
	@echo ""
	@echo "🚀 Run:"
	@echo "  make run         - Run trading platform"
	@echo "  make dashboard   - Run Streamlit dashboard"
	@echo "  make dashboard-html - Generate HTML dashboard"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  make test        - Run all tests"
	@echo "  make test-unit   - Run unit tests only"
	@echo "  make test-integration - Run integration tests"
	@echo ""
	@echo "📊 Data:"
	@echo "  make seed        - Seed demo data (100 trades)"
	@echo "  make seed-200    - Seed demo data (200 trades)"
	@echo "  make seed-clear  - Clear and re-seed"
	@echo ""
	@echo "🔧 Development:"
	@echo "  make clean       - Clean generated files"
	@echo "  make format      - Format code with ruff"
	@echo "  make lint        - Lint code with ruff"
	@echo ""

# Setup
setup:
	@echo "🚀 Running full setup..."
	pip install -e "." -q
	pip install pytest pytest-asyncio -q
	python scripts/seed_demo_data.py --trades 100 --clear
	python -m pytest tests/ -q
	@echo ""
	@echo "✅ Setup complete! Run 'make run' or 'make dashboard'"

install:
	pip install -e "." -q
	pip install pytest pytest-asyncio -q
	@echo "✅ Dependencies installed"

# Run
run:
	python -m src.app

dashboard:
	streamlit run src/dashboard/app.py

dashboard-html:
	python scripts/dashboard.py

# Testing
test:
	python -m pytest tests/ -v

test-unit:
	python -m pytest tests/unit/ -v

test-integration:
	python -m pytest tests/integration/ -v

# Data
seed:
	python scripts/seed_demo_data.py --trades 100 --clear

seed-200:
	python scripts/seed_demo_data.py --trades 200 --clear

seed-clear:
	python scripts/seed_demo_data.py --trades 100 --clear

# Development
clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache
	rm -rf src/__pycache__ src/*/__pycache__
	rm -rf tests/__pycache__ tests/*/__pycache__
	rm -rf build dist *.egg-info
	rm -f dashboard.html
	@echo "✅ Cleaned"

format:
	ruff format src/ tests/ scripts/

lint:
	ruff check src/ tests/ scripts/
