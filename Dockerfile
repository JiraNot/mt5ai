FROM python:3.12-slim

WORKDIR /app

# Install the AI CLIs used by the restricted dashboard login console. Cline
# requires Node 20+, so install the supported Node 22 runtime before npm tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    libgomp1 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @openai/codex cline \
    && curl -fsSL https://antigravity.google/cli/install.sh | bash \
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
RUN chmod 755 scripts/container-entrypoint.sh
COPY alembic.ini .
COPY alembic/ alembic/
COPY gold_1h.csv .

# Re-install package in editable/local mode without re-downloading dependencies
RUN pip install --no-deps -e .

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PATH=/root/.local/bin:${PATH}
ENV HOME=/app/data/cli-home
ENV MT5_MODE=bridge
ENV BRIDGE_URL=http://mt5-node:8900
ENV DATABASE_URL=sqlite+aiosqlite:////app/data/freebuff.db
ENV DATABASE_URL_SYNC=sqlite:////app/data/freebuff.db

EXPOSE 8501

# Run the trading worker and dashboard under one supervisor so a worker crash
# cannot leave a healthy-looking dashboard behind with a stale heartbeat.
ENTRYPOINT ["/app/scripts/container-entrypoint.sh"]
CMD ["bash", "scripts/run_services.sh"]
