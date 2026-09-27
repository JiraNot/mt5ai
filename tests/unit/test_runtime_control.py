from __future__ import annotations

import pytest
from datetime import datetime, timezone
from types import SimpleNamespace

from src.core.runtime_control import (
    arm_live_trading,
    get_runtime_trading_mode,
    is_live_armed,
    set_runtime_trading_mode,
)


def test_runtime_mode_persists_without_redeploy(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_PATH", str(tmp_path / "runtime_control.json"))

    assert get_runtime_trading_mode("demo") == "demo"
    set_runtime_trading_mode("paper")
    assert get_runtime_trading_mode("demo") == "paper"
    assert not is_live_armed()


def test_live_requires_explicit_arm_and_disarms_on_mode_change(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_PATH", str(tmp_path / "runtime_control.json"))

    set_runtime_trading_mode("live")
    assert get_runtime_trading_mode("paper") == "live"
    assert not is_live_armed()

    arm_live_trading()
    assert is_live_armed()

    set_runtime_trading_mode("demo")
    assert get_runtime_trading_mode("paper") == "demo"
    assert not is_live_armed()


@pytest.mark.asyncio
async def test_binance_paper_setting_skips_signed_account_request(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_PATH", str(tmp_path / "runtime_control.json"))
    set_runtime_trading_mode("paper")

    from src.core.config import settings
    from src.market.binance_gateway import BinanceGateway

    monkeypatch.setattr(settings, "binance_mode", "testnet")
    account = await BinanceGateway().get_account_info()

    assert account.server == "paper"
    assert account.currency == "USDT"


@pytest.mark.asyncio
async def test_binance_live_execution_is_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_PATH", str(tmp_path / "runtime_control.json"))
    set_runtime_trading_mode("live")
    arm_live_trading()

    from src.core.config import settings
    from src.core.types import Direction, OrderRequest
    from src.market.binance_gateway import BinanceGateway

    monkeypatch.setattr(settings, "binance_mode", "testnet")
    result = await BinanceGateway().send_order(OrderRequest(
        symbol="BTCUSDT", direction=Direction.BUY, volume=0.001, sl=90000, tp=100000,
    ))

    assert not result.success
    assert "LIVE execution is disabled" in (result.error_message or "")


def test_candidate_policy_persists_and_preserves_trading_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_PATH", str(tmp_path / "runtime_control.json"))

    from src.core.runtime_control import get_candidate_policy, set_candidate_policy

    set_runtime_trading_mode("demo")
    policy = set_candidate_policy(batch_min_score=45, immediate_min_score=68, summary_window=40)

    assert policy["batch_min_score"] == 45
    assert policy["immediate_min_score"] == 68
    assert get_runtime_trading_mode("paper") == "demo"
    with pytest.raises(ValueError):
        set_candidate_policy(batch_min_score=80, immediate_min_score=70)


def test_candidate_triage_records_all_priorities(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_PATH", str(tmp_path / "runtime_control.json"))
    monkeypatch.setenv("CANDIDATE_TRIAGE_PATH", str(tmp_path / "candidate_triage.json"))

    from src.ai.candidate_triage import CandidateTriage
    from src.core.types import Direction

    triage = CandidateTriage()
    for score in (30, 60, 80):
        priority = triage.observe(SimpleNamespace(
            timestamp=datetime.now(timezone.utc), symbol="XAUUSD",
            strategy_id="fvg", direction=Direction.BUY, rr_ratio=2.0,
            confluences=["fvg_present"],
        ), score, "london")
        assert priority in {"observe", "batch", "immediate"}

    summary = triage.summary()
    assert summary["total"] == 3
    assert summary["by_priority"] == {"observe": 1, "batch": 1, "immediate": 1}


def test_mcp_can_read_and_change_safe_runtime_controls(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_PATH", str(tmp_path / "runtime_control.json"))
    monkeypatch.setenv("CANDIDATE_TRIAGE_PATH", str(tmp_path / "candidate_triage.json"))

    from src.control.mcp_server import read_runtime_settings, set_trading_mode, update_candidate_policy

    update_candidate_policy(batch_min_score=50, immediate_min_score=72)
    set_trading_mode("demo")
    result = read_runtime_settings()

    assert result["trading_mode"] == "demo"
    assert result["candidate_policy"]["immediate_min_score"] == 72
