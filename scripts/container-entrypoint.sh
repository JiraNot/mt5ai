#!/usr/bin/env bash
set -euo pipefail

# Coolify mounts the persistent volumes after the image is built.  Repair the
# mount points at runtime so a newly-created or legacy volume cannot prevent
# SQLite from opening before the trading worker starts.
mkdir -p /app/data /app/models /app/data/cli-home 2>/dev/null || true
chmod 0777 /app/data /app/models /app/data/cli-home 2>/dev/null || true

# Provide agy CLI symlink if antigravity exists
if [ -x /usr/bin/antigravity ] && [ ! -e /usr/local/bin/agy ]; then
  ln -sf /usr/bin/antigravity /usr/local/bin/agy 2>/dev/null || true
fi

# Synchronize Gemini / Antigravity OAuth tokens across roots (root terminal vs worker)
for src in /config/.gemini /root/.gemini /app/data/cli-home/.gemini /app/data/.gemini; do
  if [ -d "$src" ] && { [ -f "$src/jetski-standalone-oauth-token" ] || [ -f "$src/oauth_creds.json" ]; }; then
    for dest in /root/.gemini /app/data/cli-home/.gemini /config/.gemini; do
      if [ "$src" != "$dest" ]; then
        mkdir -p "$dest" 2>/dev/null || true
        cp -rn "$src"/* "$dest"/ 2>/dev/null || true
      fi
    done
    break
  fi
done

# Synchronize Antigravity user storage (containing login email username)
for src in /config/antigravity-data /root/.config/antigravity /app/data/cli-home/.config/antigravity /app/data/antigravity-data; do
  if [ -f "$src/app_storage.json" ]; then
    for dest in /config/antigravity-data /root/.config/antigravity /app/data/cli-home/.config/antigravity /app/data/antigravity-data; do
      if [ "$src" != "$dest" ]; then
        mkdir -p "$dest" 2>/dev/null || true
        cp -rn "$src/app_storage.json" "$dest/app_storage.json" 2>/dev/null || true
      fi
    done
    break
  fi
done

# Synchronize Codex session tokens across roots
for src in /root/.codex /config/.codex /app/data/cli-home/.codex; do
  if [ -f "$src/auth.json" ]; then
    for dest in /root/.codex /config/.codex /app/data/cli-home/.codex; do
      if [ "$src" != "$dest" ]; then
        mkdir -p "$dest" 2>/dev/null || true
        cp -rn "$src/auth.json" "$dest/auth.json" 2>/dev/null || true
      fi
    done
    break
  fi
done

# Antigravity reads its provider selection from this file and the key from its
# environment.  The key itself is never written to disk or an image layer.
if [ -n "${GEMINI_API_KEY:-}" ]; then
  mkdir -p "$HOME/.gemini/antigravity-cli"
  printf '%s\n' '{"modelProvider":"gemini"}' \
    > "$HOME/.gemini/antigravity-cli/settings.json"
  chmod 600 "$HOME/.gemini/antigravity-cli/settings.json"
fi

exec "$@"
