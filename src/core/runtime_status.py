"""Small atomic heartbeat shared by the trading worker and dashboard."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _path() -> Path:
    configured = os.getenv("RUNTIME_STATUS_PATH")
    if configured:
        return Path(configured)
    # `/app/data` is the production Docker volume.  Use a local file when
    # running tests or development commands outside that container.
    production_dir = Path("/app/data")
    if production_dir.is_dir():
        return production_dir / "runtime_status.json"
    return Path("runtime_status.json")


def update_runtime_status(**fields: Any) -> None:
    """Merge fields into the heartbeat file without exposing credentials."""
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        current: dict[str, Any] = {}
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        current.update(fields)
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        fd, temporary_name = tempfile.mkstemp(prefix="runtime_status.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(current, handle, ensure_ascii=False, sort_keys=True)
            os.replace(temporary_name, path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
    except OSError:
        # A diagnostic heartbeat must never stop the trading loop.
        return


def read_runtime_status() -> dict[str, Any]:
    try:
        value = json.loads(_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
