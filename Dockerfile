FROM python:3.12-slim

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package files
COPY pyproject.toml README.md ./
COPY src/ src/
COPY config/ config/
COPY scripts/ scripts/
COPY alembic.ini .
COPY alembic/ alembic/
COPY gold_1h.csv .

# Install dependencies (core + ML packages)
RUN pip install --no-cache-dir ".[ml]"

# Set environment
ENV PYTHONUNBUFFERED=1
ENV MT5_MODE=bridge
ENV BRIDGE_URL=http://mt5-node:8900
ENV DATABASE_URL=sqlite+aiosqlite:///app/data/freebuff.db

EXPOSE 8501

# Run both Streamlit dashboard on port 8501 and the main trading loop
CMD ["bash", "-c", "mkdir -p /app/data && streamlit run src/dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true & python -m src.app"]
