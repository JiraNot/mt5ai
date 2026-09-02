"""Configuration loader — reads YAML + env vars into typed settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class MT5Config(BaseModel):
    login: int = 0
    password: str = ""
    server: str = ""
    timeout: int = 10000
    magic: int = 20240101
    deviation: int = 10


class DataConfig(BaseModel):
    timeframes: dict[str, Any] = Field(default_factory=lambda: {
        "execution": "M5",
        "structure": ["H4", "H1", "M15", "M5"],
        "context": ["D1", "H4", "H1"],
    })
    candle_count: int = 500
    tick_mode: bool = False


class RiskConfig(BaseModel):
    risk_per_trade_pct: float = 0.01
    max_daily_loss_pct: float = 0.03
    max_trades_per_day: int = 5
    max_consecutive_losses: int = 3
    min_rr: float = 2.0
    max_spread_pips: float = 5.0
    max_slippage_pips: float = 3.0
    max_exposure_pct: float = 0.10
    emergency_stop_loss_pct: float = 0.05
    news_filter_enabled: bool = True
    news_minutes_before: int = 30
    news_minutes_after: int = 15


class SessionConfig(BaseModel):
    london_start: str = "07:00"
    london_end: str = "16:00"
    new_york_start: str = "12:00"
    new_york_end: str = "21:00"
    preferred_sessions: list[str] = Field(default_factory=lambda: [
        "london", "new_york", "overlap"
    ])


class AIConfig(BaseModel):
    min_combined_score: int = 70
    scoring_weights: dict[str, int] = Field(default_factory=lambda: {
        "htf_aligned": 15,
        "strong_breakout": 15,
        "retest_quality": 20,
        "fvg_confluence": 15,
        "liquidity_sweep": 15,
        "ob_fvg_overlap": 20,
        "session_london_ny": 10,
        "spread_normal": 5,
        "rr_excellent": 10,
        "htf_conflict": -20,
        "spread_high": -30,
        "low_volume": -10,
        "asian_session": -5,
        "near_news": -25,
    })


class AppConfig(BaseModel):
    name: str = "Freebuff Trading Platform"
    version: str = "0.1.0"
    mode: str = "paper"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"
    file: str = "logs/freebuff.log"


class SymbolConfig(BaseModel):
    name: str = ""
    digits: int = 2
    point: float = 0.01
    pip_value: float = 0.1
    normal_spread: float = 2.5
    max_spread: float = 8.0
    contract_size: int = 100
    min_volume: float = 0.01
    max_volume: float = 100.0
    volume_step: float = 0.01
    margin_requirement: float = 0.01
    swap_long: float = 0.0
    swap_short: float = 0.0
    trading_sessions: list[str] = Field(default_factory=lambda: ["london", "new_york"])


class Settings(BaseSettings):
    """Application settings — loaded from env + YAML files."""

    # Env vars (override YAML)
    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = ""
    database_url: str = "sqlite+aiosqlite:///freebuff.db"
    redis_url: str = "redis://localhost:6379/0"
    trading_mode: str = "paper"
    log_level: str = "INFO"

    # Loaded from YAML
    app: AppConfig = Field(default_factory=AppConfig)
    mt5: MT5Config = Field(default_factory=MT5Config)
    data: DataConfig = Field(default_factory=DataConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    sessions: SessionConfig = Field(default_factory=SessionConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    logging_config: LoggingConfig = Field(default_factory=LoggingConfig)
    symbols: dict[str, SymbolConfig] = Field(default_factory=dict)

    model_config = {"env_prefix": "FREEBUFF_", "extra": "ignore"}


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, return empty dict if not found."""
    if path.exists():
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


def _load_symbols_yaml(path: Path) -> dict[str, SymbolConfig]:
    """Load symbols.yaml into dict of SymbolConfig."""
    raw = _load_yaml(path)
    return {k: SymbolConfig(**v) for k, v in raw.items()}


def load_settings(config_dir: str | Path = "config") -> Settings:
    """
    Load settings from YAML files + environment variables.

    Priority: env vars > YAML files > defaults
    """
    config_path = Path(config_dir)

    # Load main settings
    settings_yaml = _load_yaml(config_path / "settings.yaml")

    # Load symbol configs
    symbols_config = _load_symbols_yaml(config_path / "symbols.yaml")

    # Build MT5 config from env if available
    mt5_config = MT5Config(**settings_yaml.get("mt5", {}))
    if os.getenv("MT5_LOGIN"):
        mt5_config.login = int(os.getenv("MT5_LOGIN", "0"))
    if os.getenv("MT5_PASSWORD"):
        mt5_config.password = os.getenv("MT5_PASSWORD", "")
    if os.getenv("MT5_SERVER"):
        mt5_config.server = os.getenv("MT5_SERVER", "")

    # Build database URL from env
    db_url = os.getenv("DATABASE_URL", settings_yaml.get("database_url", ""))

    # Construct settings
    return Settings(
        mt5_login=mt5_config.login,
        mt5_password=mt5_config.password,
        mt5_server=mt5_config.server,
        database_url=db_url or "sqlite+aiosqlite:///freebuff.db",
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        trading_mode=os.getenv("TRADING_MODE", settings_yaml.get("app", {}).get("mode", "paper")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        app=AppConfig(**settings_yaml.get("app", {})),
        mt5=mt5_config,
        data=DataConfig(**settings_yaml.get("data", {})),
        risk=RiskConfig(**settings_yaml.get("risk", {})),
        sessions=SessionConfig(**settings_yaml.get("sessions", {})),
        ai=AIConfig(**settings_yaml.get("ai", {})),
        logging_config=LoggingConfig(**settings_yaml.get("logging", {})),
        symbols=symbols_config,
    )


# Global settings instance
settings = load_settings()
