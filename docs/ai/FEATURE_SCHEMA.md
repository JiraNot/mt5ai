# Feature Schema

## Overview

หนึ่ง row ต่อ Candidate — features สำหรับ ML training

## Feature Categories

### Market Features

| Feature | Type | Description |
|---------|------|-------------|
| symbol | string | Trading symbol |
| timeframe | string | Primary timeframe |
| hour | int | Hour of day (UTC) |
| session | string | Trading session |
| day_of_week | int | Day of week (0-6) |

### Structure Features

| Feature | Type | Description |
|---------|------|-------------|
| htf_bias | string | Higher TF direction |
| market_regime | string | Current regime |
| atr | float | Average True Range |
| atr_percentile | float | ATR percentile (0-1) |
| spread | int | Current spread |

### Pattern Features

| Feature | Type | Description |
|---------|------|-------------|
| choch_strength | int | CHoCH strength (0-100) |
| bos_strength | int | BOS strength (0-100) |
| displacement_score | int | Displacement (0-100) |
| swing_distance | float | Distance from last swing |

### FVG Features

| Feature | Type | Description |
|---------|------|-------------|
| fvg_present | bool | FVG exists |
| fvg_direction | string | FVG direction |
| fvg_size_atr | float | FVG size in ATR |
| fvg_mitigation | float | Mitigation % |

### Order Block Features

| Feature | Type | Description |
|---------|------|-------------|
| ob_present | bool | OB exists |
| ob_direction | string | OB direction |
| ob_score | int | OB strength (0-100) |

### Liquidity Features

| Feature | Type | Description |
|---------|------|-------------|
| liquidity_sweep | bool | Sweep occurred |
| liquidity_type | string | BUY_SIDE, SELL_SIDE |
| premium_discount | string | PREMIUM, EQUILIBRIUM, DISCOUNT |

### Trade Features

| Feature | Type | Description |
|---------|------|-------------|
| rr | float | Risk-reward ratio |
| rule_score | int | Rule engine score |

## Labels

| Label | Type | Description |
|-------|------|-------------|
| win | bool | Trade was winner |
| loss | bool | Trade was loser |
| r_multiple | float | Actual R result |
| mfe | float | Max Favorable Excursion |
| mae | float | Max Adverse Excursion |

## Acceptance Criteria

- [ ] All features extractable
- [ ] Schema validated
- [ ] Missing values handled
- [ ] Feature pipeline functional
