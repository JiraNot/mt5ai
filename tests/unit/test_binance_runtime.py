from src.core.config import load_settings, settings


def test_configuration_is_binance_only_with_safe_defaults(monkeypatch):
    for name in ("MT5_MODE", "BRIDGE_URL", "MARKET_DATA_VENUES", "MARKET_DATA_VENUE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("PRIMARY_SYMBOL", raising=False)
    monkeypatch.delenv("BINANCE_SYMBOL", raising=False)

    loaded = load_settings()

    assert loaded.binance_mode == "paper"
    assert loaded.binance_symbol == "BTCUSDT"
    assert loaded.primary_symbol == "BTCUSDT"
    assert not hasattr(loaded, "mt5_mode")
    assert not hasattr(loaded, "market_data_venues")


def test_platform_builds_only_a_binance_pipeline(monkeypatch):
    from src.app import TradingPlatform

    monkeypatch.setattr(settings, "binance_mode", "paper")
    platform = TradingPlatform()

    assert platform._venue_name == "binance"
    assert platform._trading_symbol == settings.binance_symbol
    assert platform._gateway.venue == "binance"
    assert platform._data_feed._gateway is platform._gateway
