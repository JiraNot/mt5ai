#!/usr/bin/env bash
set -Eeuo pipefail

mkdir -p /app/data /app/models

python -m src.app &
worker_pid=$!

streamlit run src/dashboard/app.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true &
dashboard_pid=$!

cleanup() {
  kill "$worker_pid" "$dashboard_pid" 2>/dev/null || true
  wait "$worker_pid" "$dashboard_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# If either service exits, terminate the container. Docker's restart policy can
# then recreate both services instead of leaving the dashboard without a bot.
wait -n "$worker_pid" "$dashboard_pid"
exit $?
