# Configuration System

## Overview

ระบบ Configuration ใช้ YAML + Environment Variables + Pydantic Validation

Config ต้อง validate ก่อนเริ่ม Trading Worker — ถ้า config ไม่ valid ระบบต้อง **REFUSE TO START**

## Configuration File

```yaml
# config.yaml

runtime:
  mode: PAPER  # BACKTEST, REPLAY, PAPER, DEMO, LIVE
  log_level: INFO
  correlation_enabled: true

symbols:
  XAUUSD:
    enabled: true
    description: "Gold vs US Dollar"
  EURUSD:
    enabled: false
    description: "Euro vs US Dollar"

timeframes:
  bias: H1
  structure: M15
  entry: M5

market_data:
  candle_history: 500
  tick_enabled: false
  spread_monitor: true
  spread_warn_pips: 3.0
  spread_max_pips: 10.0

structure:
  swing_lookback: 3
  break_mode: CLOSE  # CLOSE, WICK, BODY, DISPLACEMENT
  minimum_break_atr: 0.10
  require_displacement: true

fvg:
  min_size_atr: 0.10
  max_mitigation_percent: 50

order_block:
  min_displacement_score: 60
  require_bos_or_choch: true

liquidity:
  equal_level_tolerance_atr: 0.08
  detect_session_levels: true
  detect_previous_day: true

session:
  primary_timezone: UTC
  sessions:
    ASIA:
      start: "00:00"
      end: "08:00"
    LONDON:
      start: "07:00"
      end: "16:00"
    NEW_YORK:
      start: "12:00"
      end: "21:00"

strategies:
  choch_order_block:
    enabled: true
    version: "1.0.0"
    min_score: 75
    timeframes:
      structure: M15
      entry: M5

  fvg_retracement:
    enabled: true
    version: "1.0.0"
    min_score: 78
    timeframes:
      structure: M15
      entry: M5

  breakout_retest:
    enabled: true
    version: "1.0.0"
    min_score: 80
    timeframes:
      structure: M15
      entry: M5

scoring:
  htf_aligned_bonus: 15
  liquidity_sweep_bonus: 20
  choch_bonus: 20
  displacement_bonus: 15
  ob_bonus: 10
  fvg_bonus: 10
  overlap_bonus: 10
  discount_bonus: 5
  session_bonus: 5
  htf_conflict_penalty: -25
  high_spread_penalty: -20
  news_penalty: -30
  weak_displacement_penalty: -10
  min_score: 70
  max_score: 100

risk:
  risk_per_trade: 0.0025  # 0.25%
  max_daily_loss: 0.015   # 1.5%
  max_weekly_loss: 0.04   # 4%
  max_drawdown: 0.10      # 10%
  max_open_positions: 2
  max_symbol_exposure: 1
  max_correlated_exposure: 2
  max_trades_per_day: 5
  max_consecutive_losses: 3
  min_rr: 2.0
  min_lot: 0.01
  max_lot: 1.0
  position_sizing: VOLATILITY  # FIXED, FIXED_PCT, VOLATILITY, ATR

execution:
  mode: PAPER  # PAPER, DEMO, LIVE
  max_price_deviation_pips: 5
  require_sl: true
  duplicate_protection: true
  execution_timeout_seconds: 30

position_management:
  break_even_enabled: true
  break_even_trigger_rr: 1.0
  trailing_enabled: false
  trailing_type: FIXED  # FIXED, ATR, STRUCTURE
  trailing_distance_atr: 1.0
  partial_close_enabled: false
  time_exit_hours: 24

kill_switch:
  enabled: true
  mt5_disconnect_threshold: 3
  stale_data_seconds: 300
  abnormal_spread_multiplier: 3.0
  daily_dd_action: PAUSE_NEW_ENTRIES
  weekly_dd_action: EMERGENCY_STOP

backtesting:
  spread_model: VARIABLE  # FIXED, VARIABLE, HISTORICAL
  commission_per_lot: 7.0
  slippage_pips: 1.0
  start_balance: 10000
  currency: USD

ai:
  enabled: false
  provider: RULE  # RULE, LLM, ML, ENSEMBLE
  shadow_mode: true
  min_confidence: 0.7

ml:
  model_path: null
  feature_version: "1.0.0"
  prediction_threshold: 0.6

alerts:
  enabled: false
  providers: []
  # telegram, discord, email

dashboard:
  enabled: true
  port: 8501
  host: "0.0.0.0"
```

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/mt5trader
DATABASE_URL_DEV=sqlite:///./dev.db

# MT5
MT5_LOGIN=your_login
MT5_PASSWORD=your_password
MT5_SERVER=your_server
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe

# AI
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Alerts
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DISCORD_WEBHOOK_URL=...

# Security
API_SECRET_KEY=...
JWT_SECRET=...
```

## Configuration Loading

```python
from pydantic import BaseModel, validator

class RuntimeConfig(BaseModel):
    mode: str = "PAPER"
    log_level: str = "INFO"
    
    @validator("mode")
    def validate_mode(cls, v):
        allowed = ["BACKTEST", "REPLAY", "PAPER", "DEMO", "LIVE"]
        if v not in allowed:
            raise ValueError(f"Mode must be one of {allowed}")
        return v

class RiskConfig(BaseModel):
    risk_per_trade: float = 0.0025
    max_daily_loss: float = 0.015
    max_weekly_loss: float = 0.04
    max_drawdown: float = 0.10
    min_rr: float = 2.0
    
    @validator("risk_per_trade")
    def validate_risk(cls, v):
        if v <= 0 or v > 0.05:
            raise ValueError("Risk per trade must be between 0% and 5%")
        return v
```

## Config Validation Rules

| Parameter | Min | Max | Default | Description |
|-----------|-----|-----|---------|-------------|
| risk_per_trade | 0.0001 | 0.05 | 0.0025 | Max risk per trade |
| max_daily_loss | 0.005 | 0.10 | 0.015 | Daily loss limit |
| max_weekly_loss | 0.01 | 0.20 | 0.04 | Weekly loss limit |
| max_drawdown | 0.05 | 0.30 | 0.10 | Max drawdown |
| min_rr | 1.0 | 5.0 | 2.0 | Minimum risk-reward |
| max_trades_per_day | 1 | 20 | 5 | Daily trade limit |
| max_consecutive_losses | 1 | 10 | 3 | Consecutive loss limit |
| max_open_positions | 1 | 10 | 2 | Concurrent positions |

## Config Override Priority

1. Environment Variables (highest)
2. Config File
3. Defaults (lowest)

## Config Reload

```python
# Config can be reloaded at runtime for certain parameters
# Risk limits can be tightened but NOT loosened without restart

# Allowed runtime changes:
# - max_trades_per_day (can decrease only)
# - max_open_positions (can decrease only)
# - kill_switch thresholds (can decrease only)

# Requires restart:
# - risk_per_trade
# - max_daily_loss
# - Strategies enabled/disabled
# - Timeframes
```
