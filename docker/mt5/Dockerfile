FROM gmag11/metatrader5_vnc:latest

USER root

# Copy our bridge application into container
COPY bridge/ /app/bridge/

# Add custom container init script to auto-start mt5-bridge with proper WINEPREFIX & retry loop
RUN mkdir -p /custom-cont-init.d && \
    printf '#!/bin/bash\n(\n  export WINEPREFIX="/config/.wine"\n  export WINEDEBUG=-all\n  echo "Waiting for Wine python and MetaTrader 5..."\n  while ! wine python --version >/dev/null 2>&1; do sleep 5; done\n  while ! wine python -c "import MetaTrader5" >/dev/null 2>&1; do sleep 5; done\n  echo "Installing fastapi & uvicorn..."\n  wine python -m pip install --no-cache-dir fastapi uvicorn\n  echo "Starting MT5 Bridge on port 8900..."\n  while true; do\n    wine python /app/bridge/mt5_bridge.py\n    sleep 5\n  done\n) > /tmp/mt5_bridge.log 2>&1 &\n' > /custom-cont-init.d/99-mt5-bridge.sh && \
    chmod +x /custom-cont-init.d/99-mt5-bridge.sh

EXPOSE 3000 8900
