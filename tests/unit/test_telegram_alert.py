"""Unit tests for Telegram notification module."""

from unittest.mock import AsyncMock, patch
import pytest

from src.notification.telegram_alert import (
    TradeAlert,
    alert_daily_review,
    alert_evening_reflection,
    alert_morning_brief,
    alert_trade_closed,
    alert_trade_lesson,
    alert_trade_opened,
    alert_trade_skipped,
    send_message,
)


@pytest.mark.asyncio
async def test_send_message_disabled_without_tokens(monkeypatch):
    monkeypatch.setattr("src.notification.telegram_alert.BOT_TOKEN", "")
    monkeypatch.setattr("src.notification.telegram_alert.CHAT_ID", "")
    result = await send_message("test")
    assert result is False


@pytest.mark.asyncio
async def test_send_message_success(monkeypatch):
    monkeypatch.setattr("src.notification.telegram_alert.BOT_TOKEN", "mock_bot_token")
    monkeypatch.setattr("src.notification.telegram_alert.CHAT_ID", "mock_chat_id")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = await send_message("Hello from mt5ai!")
        assert result is True
        mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_alert_morning_brief():
    btc_report = {
        "macro_bias": "BULLISH",
        "crowd_bias": "LONG_CROWDED",
        "funding_rate_pct": 0.0150,
    }
    candidates = [
        {
            "symbol": "SOLUSDT",
            "price": 145.20,
            "price_change_pct": 8.5,
            "quote_volume_24h": 150_000_000,
            "score": 78.5,
            "tags": ["High Momentum", "High Volatility"],
            "formatted_volume": "$150.0M",
        },
        {
            "symbol": "ETHUSDT",
            "price": 2650.0,
            "price_change_pct": 3.2,
            "quote_volume_24h": 600_000_000,
            "score": 65.0,
            "tags": ["Major"],
            "formatted_volume": "$600.0M",
        },
    ]

    with patch("src.notification.telegram_alert.send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        res = await alert_morning_brief(btc_report, candidates)
        assert res is True
        mock_send.assert_awaited_once()
        text = mock_send.call_args[0][0]
        assert "MORNING BRIEFING" in text
        assert "SOLUSDT" in text
        assert "ETHUSDT" in text
        assert "BULLISH" in text
        assert "LONG_CROWDED" in text


@pytest.mark.asyncio
async def test_alert_evening_reflection():
    daily_stats = {
        "total_trades": 4,
        "win_rate_pct": 75.0,
        "net_pnl": 350.50,
        "lesson_of_the_day": "Follow trend alignment and respect Asian range sweeps.",
    }
    gate_eval = {
        "current_stage": "DEMO",
        "is_promotable": False,
        "gate_checks": [
            {"name": "Sample Size", "passed": False},
            {"name": "Profit Factor", "passed": True},
            {"name": "Net PnL", "passed": True},
            {"name": "Win Rate", "passed": True},
            {"name": "Max Drawdown", "passed": True},
            {"name": "SL Compliance", "passed": True},
        ],
    }

    with patch("src.notification.telegram_alert.send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        res = await alert_evening_reflection(daily_stats, gate_eval)
        assert res is True
        mock_send.assert_awaited_once()
        text = mock_send.call_args[0][0]
        assert "DAILY REFLECTION" in text
        assert "75.0%" in text
        assert "$350.50" in text
        assert "Promotion Gate" in text
        assert "83%" in text  # 5/6 gates passed = 83%


@pytest.mark.asyncio
async def test_alert_trade_opened():
    alert = TradeAlert(
        symbol="BTCUSDT",
        direction="BUY",
        entry_price=65000.0,
        stop_loss=64500.0,
        take_profit=66500.0,
        rule_score=85,
        gemini_score=90,
        gpt_score=80,
        gemini_verdict="APPROVE",
        gpt_verdict="APPROVE",
        combined_verdict="APPROVE",
        narrative_th="ทดสอบเปิดสถานะ Long",
    )
    with patch("src.notification.telegram_alert.send_message", new_callable=AsyncMock) as mock_send:
        await alert_trade_opened(alert)
        mock_send.assert_awaited_once()
        assert "TRADE OPEN" in mock_send.call_args[0][0]
