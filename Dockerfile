FROM python:3.12-slim

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition first for optimal Docker layer caching
COPY pyproject.toml README.md ./
RUN mkdir src && touch src/__init__.py && \
    pip install --no-cache-dir ".[ml]" && \
    rm -rf src

# Copy application source code
COPY src/ src/
COPY config/ config/
COPY scripts/ scripts/
COPY alembic.ini .
COPY alembic/ alembic/
COPY gold_1h.csv .

# Re-install package in editable/local mode without re-downloading dependencies
RUN pip install --no-deps -e .

# Set environment
ENV PYTHONUNBUFFERED=1
ENV MT5_MODE=bridge
ENV BRIDGE_URL=http://mt5-node:8900
ENV DATABASE_URL=sqlite+aiosqlite:///app/data/freebuff.db
ENV DATABASE_URL_SYNC=sqlite:////app/data/freebuff.db

EXPOSE 8501

# Run background trading loop and foreground Streamlit dashboard
CMD ["bash", "-c", "mkdir -p /app/data && python -m src.app & exec streamlit run src/dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true"]
