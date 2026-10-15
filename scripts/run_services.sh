#!/usr/bin/env bash
set -Eeuo pipefail

mkdir -p /app/data /app/models

python -m src.app &
worker_pid=$!

PORT=8501 python -m src.web.server &
dashboard_pid=$!

python -m src.dashboard.terminal_server &
terminal_pid=$!

cleanup() {
  kill "$worker_pid" "$dashboard_pid" "$terminal_pid" 2>/dev/null || true
  wait "$worker_pid" "$dashboard_pid" "$terminal_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# If either service exits, terminate the container. Docker's restart policy can
# then recreate both services instead of leaving the dashboard without a bot.
wait -n "$worker_pid" "$dashboard_pid" "$terminal_pid"
exit $?
