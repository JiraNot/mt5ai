# Backtest Metrics

## Mandatory Metrics

| Metric | Formula | Description |
|--------|---------|-------------|
| Net Profit | Sum(pnl) | Total profit/loss |
| Return % | (final - initial) / initial | Percentage return |
| Win Rate | wins / total | Winning trade % |
| Profit Factor | gross_profit / gross_loss | Risk/reward ratio |
| Expectancy | (win_rate × avg_win) - (loss_rate × avg_loss) | Expected value per trade |
| Average R | Sum(r_multiple) / total | Average R result |
| Max Drawdown | max(equity decline) | Worst peak-to-trough |
| Sharpe Ratio | (return - risk_free) / volatility | Risk-adjusted return |
| Sortino Ratio | (return - risk_free) / downside_vol | Downside risk-adjusted |
| Calmar Ratio | return / max_drawdown | Return per drawdown |
| Average Win | Sum(wins) / win_count | Average winning trade |
| Average Loss | Sum(losses) / loss_count | Average losing trade |
| Longest Losing Streak | max consecutive losses | Worst streak |
| Trades/month | total / months | Trading frequency |

## MFE / MAE

```python
class TradeMetrics(BaseModel):
    mfe: Decimal  # Maximum Favorable Excursion
    mae: Decimal  # Maximum Adverse Excursion
```

### Analysis

```
ถ้า MAE >> SL:
  → SL  wida เกินไป

ถ้า MFE >> TP:
  → TP เร็วเกินไป หรือ trailing ช่วยได้

ถ้า MFE ≈ TP:
  → TP ตั้งได้ดี
```

## Strategy Comparison

```
ต้องสามารถถามได้ว่า:

CHoCH + OB
vs
FVG
vs
Breakout

ตาม:
- symbol
- period
- session
- market regime
- score band
```

## Report Format

```python
class BacktestReport(BaseModel):
    strategy: str
    symbol: str
    period: Tuple[datetime, datetime]
    total_trades: int
    win_rate: Decimal
    net_profit: Decimal
    return_percent: Decimal
    profit_factor: Decimal
    expectancy: Decimal
    max_drawdown: Decimal
    sharpe_ratio: Decimal
    trades: List[TradeDetail]
```

## Acceptance Criteria

- [ ] All mandatory metrics calculated
- [ ] MFE/MAE tracked
- [ ] Strategy comparison working
- [ ] Report format validated
- [ ] Results reproducible
