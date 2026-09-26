from __future__ import annotations

import pytest

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
