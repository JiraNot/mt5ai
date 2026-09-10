FROM gmag11/metatrader5:latest

USER root

# Copy our bridge application into container
COPY bridge/ /app/bridge/

# Append startup command to autostart: install fastapi/uvicorn in wine python, then start bridge
RUN echo 'sleep 20 && wine python -m pip install --no-cache-dir fastapi uvicorn && wine python /app/bridge/mt5_bridge.py &' >> /defaults/autostart

EXPOSE 3000 8900
