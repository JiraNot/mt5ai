from __future__ import annotations

from src.core.config import load_settings, settings


def test_market_data_venues_accepts_multiple_values(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_VENUES", "mt5, binance, mt5")
    monkeypatch.delenv("MARKET_DATA_VENUE", raising=False)

    loaded = load_settings()

    assert loaded.market_data_venues == ["mt5", "binance"]


def test_market_data_venues_preserves_legacy_single_setting(monkeypatch):
    monkeypatch.delenv("MARKET_DATA_VENUES", raising=False)
    monkeypatch.setenv("MARKET_DATA_VENUE", "binance")

    loaded = load_settings()

    assert loaded.market_data_venues == ["binance"]


def test_binance_symbol_has_spread_metadata():
    assert "BTCUSDT" in settings.symbols
    assert settings.symbols["BTCUSDT"].contract_size == 1
    assert settings.symbols["BTCUSDT"].volume_step == 0.001


def test_trading_platform_can_build_a_binance_pipeline(monkeypatch):
    from src.app import TradingPlatform

    monkeypatch.setattr(settings, "binance_mode", "paper")
    platform = TradingPlatform(venue_name="binance")

    assert platform._venue_name == "binance"
    assert platform._trading_symbol == settings.binance_symbol
    assert platform._mt5.venue == "binance"
    assert platform._data_feed._market_data_venue == "binance"
