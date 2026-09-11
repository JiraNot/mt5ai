#!/usr/bin/env bash
set -euo pipefail

# Antigravity reads its provider selection from this file and the key from its
# environment.  The key itself is never written to disk or an image layer.
if [ -n "${GEMINI_API_KEY:-}" ]; then
  mkdir -p /root/.gemini/antigravity-cli
  printf '%s\n' '{"modelProvider":"gemini"}' \
    > /root/.gemini/antigravity-cli/settings.json
  chmod 600 /root/.gemini/antigravity-cli/settings.json
fi

exec "$@"
