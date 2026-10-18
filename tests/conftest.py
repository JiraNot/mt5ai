"""Test configuration and fixtures ensuring tests run in isolation."""

import os
from pathlib import Path

# Ensure tests do not mutate or depend on production runtime_settings.json
os.environ.setdefault("RUNTIME_SETTINGS_PATH", "/tmp/mt5ai_test_runtime_settings.json")
