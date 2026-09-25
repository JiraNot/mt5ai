#!/bin/bash

(
  export WINEPREFIX="/config/.wine"
  export WINEDEBUG=-all

  # The persisted Wine prefix is owned by LinuxServer's abc user (UID 911).
  # Run every Wine process as that user or Wine refuses the prefix.
  run_wine() {
    runuser -u abc --preserve-environment -- wine "$@"
  }

  echo "Waiting for Wine python and MetaTrader 5..."
  while ! run_wine python --version >/dev/null 2>&1; do sleep 5; done
  while ! run_wine python -c "import MetaTrader5" >/dev/null 2>&1; do sleep 5; done
  echo "Installing fastapi & uvicorn..."
  run_wine python -m pip install --no-cache-dir fastapi uvicorn
  echo "Starting MT5 Bridge on port 8900..."
  while true; do
    run_wine python /app/bridge/mt5_bridge.py
    sleep 5
  done
) > /tmp/mt5_bridge.log 2>&1 &
