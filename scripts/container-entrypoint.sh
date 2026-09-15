#!/usr/bin/env bash
set -euo pipefail

# Coolify mounts the persistent volumes after the image is built.  Repair the
# mount points at runtime so a newly-created or legacy volume cannot prevent
# SQLite from opening before the trading worker starts.
mkdir -p /app/data /app/models
chmod 0777 /app/data /app/models 2>/dev/null || true

# Antigravity reads its provider selection from this file and the key from its
# environment.  The key itself is never written to disk or an image layer.
if [ -n "${GEMINI_API_KEY:-}" ]; then
  mkdir -p /root/.gemini/antigravity-cli
  printf '%s\n' '{"modelProvider":"gemini"}' \
    > /root/.gemini/antigravity-cli/settings.json
  chmod 600 /root/.gemini/antigravity-cli/settings.json
fi

exec "$@"
