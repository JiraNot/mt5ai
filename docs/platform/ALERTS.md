# Alert System

## Overview

Alert System แจ้งเตือนเมื่อเกิดเหตุการณ์สำคัญ

## Alert Types

### Trade Alerts

```
- Trade Opened
- Trade Closed (Win)
- Trade Closed (Loss)
- Trade Closed (BE)
```

### Risk Alerts

```
- Daily Loss Limit Hit
- Weekly Loss Limit Hit
- Max Drawdown Warning
- Consecutive Loss Warning
- Kill Switch Triggered
```

### System Alerts

```
- MT5 Disconnected
- MT5 Reconnected
- Database Error
- Data Stale
- Worker Error
```

### Opportunity Alerts

```
- High Score Candidate (score > 90)
- Strategy Signal
- Regime Change
```

## Providers

```yaml
alerts:
  enabled: true
  providers:
    - type: TELEGRAM
      bot_token: ${TELEGRAM_BOT_TOKEN}
      chat_id: ${TELEGRAM_CHAT_ID}
    - type: DISCORD
      webhook_url: ${DISCORD_WEBHOOK_URL}
    - type: EMAIL
      smtp_host: smtp.gmail.com
      to: admin@example.com
```

## Message Format

```python
class AlertMessage(BaseModel):
    level: str  # INFO, WARNING, CRITICAL
    category: str  # TRADE, RISK, SYSTEM, OPPORTUNITY
    title: str
    message: str
    data: Optional[dict] = None
    timestamp: datetime
```

## Acceptance Criteria

- [ ] Telegram alerts working
- [ ] Discord alerts working
- [ ] Email alerts working
- [ ] Alert throttling (no spam)
- [ ] Alert history logged
