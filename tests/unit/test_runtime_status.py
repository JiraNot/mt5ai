import json

from src.core.runtime_status import read_runtime_status, update_runtime_status


def test_runtime_status_is_atomic_and_merges_fields(tmp_path, monkeypatch):
    path = tmp_path / "runtime_status.json"
    monkeypatch.setenv("RUNTIME_STATUS_PATH", str(path))

    update_runtime_status(state="running", cycle_count=3)
    update_runtime_status(last_decision="NO_CANDIDATE")

    status = read_runtime_status()
    assert status["state"] == "running"
    assert status["cycle_count"] == 3
    assert status["last_decision"] == "NO_CANDIDATE"
    assert "updated_at" in status
    assert status["last_decision_at"] == status["updated_at"]
    assert json.loads(path.read_text())["state"] == "running"

    decision_at = status["last_decision_at"]
    update_runtime_status(cycle_count=4)
    status = read_runtime_status()
    assert status["cycle_count"] == 4
    assert status["last_decision_at"] == decision_at
