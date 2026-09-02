# Session Engine

## Overview

Session Engine ติดตามช่วงเวลาการเทรด (Asia, London, New York)

## Sessions

```python
class TradingSession(Enum):
    ASIA = "ASIA"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    LONDON_NY_OVERLAP = "LONDON_NY_OVERLAP"
    OFF_HOURS = "OFF_HOURS"
```

## Default Schedule (UTC)

| Session | Start | End | Characteristics |
|---------|-------|-----|-----------------|
| ASIA | 00:00 | 08:00 | Low volatility, range-bound |
| LONDON | 07:00 | 16:00 | High volatility, trend start |
| NEW_YORK | 12:00 | 21:00 | High volatility, continuation |
| OVERLAP | 12:00 | 16:00 | Highest volatility |
| OFF_HOURS | 21:00 | 00:00 | Very low activity |

## Session Data

```python
class SessionData(BaseModel):
    session: TradingSession
    high: Decimal
    low: Decimal
    range: Decimal
    volume: int
    is_active: bool
```

## Strategy Usage

```yaml
# Strategy สามารถระบุ preferred sessions
strategies:
  choch_order_block:
    preferred_sessions:
      - LONDON
      - NEW_YORK
```

## Configuration

```yaml
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
```

## DST Handling

- ใช้ timezone ที่กำหนดเป็น UTC ภายในระบบ
- UI แปลง timezone ตาม user preference
- ห้าม hardcode timezone offset แบบถาวร

## Acceptance Criteria

- [ ] Session detection working
- [ ] Session high/low tracking
- [ ] Overlap detection working
- [ ] Off-hours detection working
- [ ] DST handled correctly
