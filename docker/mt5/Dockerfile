FROM gmag11/metatrader5_vnc:latest

USER root

# The base image starts the legacy mt5linux RPyC server on port 8001.  Its
# rolling dependency install currently pulls mt5linux 1.1.x, whose f-string
# syntax requires Python 3.12 while this image ships Debian's Python 3.11.
# This deployment uses the HTTP bridge below instead, so remove that optional
# startup path and keep the image independent of the mutable mt5linux package.
RUN python3 - <<'PY'
from pathlib import Path

path = Path("/Metatrader/start.sh")
text = path.read_text(encoding="utf-8")

install_start = "# Install mt5linux library in Windows if not installed"
install_end = "# Install pyxdg library in Linux if not installed"
server_start = "# Start the MT5 server on Linux"

if install_start not in text or install_end not in text or server_start not in text:
    raise SystemExit("Unexpected gmag11 start.sh layout; refusing an unsafe patch")

before_install, remainder = text.split(install_start, 1)
_, after_install = remainder.split(install_end, 1)

replacement = (
    before_install
    + "# mt5linux RPyC is intentionally disabled; the HTTP bridge on port 8900\n"
    + "# is the only MT5 connectivity path used by this deployment.\n"
    + "show_message \"[6/7] Skipping legacy mt5linux RPyC server.\"\n"
    + after_install.split(server_start, 1)[0]
    + "# Start the project HTTP bridge instead of the legacy mt5linux server.\n"
    + "show_message \"[7/7] MT5 HTTP bridge is managed by custom init.\"\n"
)
replacement = replacement.replace('mt5server_port="8001"\n', "")

path.write_text(replacement, encoding="utf-8")
PY

# Copy our bridge application into container
COPY bridge/ /app/bridge/

# Add custom container init script to auto-start mt5-bridge with proper WINEPREFIX & retry loop
RUN mkdir -p /custom-cont-init.d && \
    printf '#!/bin/bash\n(\n  export WINEPREFIX="/config/.wine"\n  export WINEDEBUG=-all\n  echo "Waiting for Wine python and MetaTrader 5..."\n  while ! wine python --version >/dev/null 2>&1; do sleep 5; done\n  while ! wine python -c "import MetaTrader5" >/dev/null 2>&1; do sleep 5; done\n  echo "Installing fastapi & uvicorn..."\n  wine python -m pip install --no-cache-dir fastapi uvicorn\n  echo "Starting MT5 Bridge on port 8900..."\n  while true; do\n    wine python /app/bridge/mt5_bridge.py\n    sleep 5\n  done\n) > /tmp/mt5_bridge.log 2>&1 &\n' > /custom-cont-init.d/99-mt5-bridge.sh && \
    chmod +x /custom-cont-init.d/99-mt5-bridge.sh

# Replace the generated script with the user-aware version.
COPY docker/mt5/99-mt5-bridge.sh /custom-cont-init.d/99-mt5-bridge.sh
RUN chmod +x /custom-cont-init.d/99-mt5-bridge.sh

# Repair a malformed command left in some persisted volumes by older image
# startup scripts before Openbox launches MetaTrader.
RUN printf '#!/bin/bash\nif [ -f /config/.config/openbox/autostart ]; then\n  sed -i "s#/Metatrader/start\\.shsleep#/Metatrader/start.sh\\nsleep#g" /config/.config/openbox/autostart\nfi\n' \
    > /custom-cont-init.d/98-repair-mt5-autostart.sh && \
    chmod +x /custom-cont-init.d/98-repair-mt5-autostart.sh

EXPOSE 3000 8900
