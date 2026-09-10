FROM gmag11/metatrader5_vnc:latest

USER root

# Copy our bridge application into container
COPY bridge/ /app/bridge/

# Add custom container init script to auto-start mt5-bridge
RUN mkdir -p /custom-cont-init.d && \
    printf '#!/bin/bash\n(sleep 15 && wine python -m pip install --no-cache-dir fastapi uvicorn && wine python /app/bridge/mt5_bridge.py) > /tmp/mt5_bridge.log 2>&1 &\n' > /custom-cont-init.d/99-mt5-bridge.sh && \
    chmod +x /custom-cont-init.d/99-mt5-bridge.sh

EXPOSE 3000 8900
