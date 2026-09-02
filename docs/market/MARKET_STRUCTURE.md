# Market Structure Engine

## Overview

Market Structure Engine วิเคราะห์โครงสร้างราคาเพื่อเข้าใจแนวโน้มและการเปลี่ยนแปลง

## Components

```
Market Structure Engine
├── Swing Detector
├── BOS/CHoCH Analyzer
├── Displacement Detector
├── Structure Context Builder
└── Market Regime Detector
```

## Data Flow

```
Candles (Multi-TF)
    ↓
Swing Detection
    ↓
BOS/CHoCH Detection
    ↓
Displacement Scoring
    ↓
Structure Context
    ↓
Strategy Input
```

## Structure Events

```python
class StructureEvent(BaseModel):
    symbol: str
    timeframe: str
    timestamp: datetime
    type: StructureType  # BOS, CHOCH
    direction: Direction  # BULLISH, BEARISH
    price: Decimal
    strength: int  # 0-100
    version: str = "1.0.0"
```

## Trend Identification

### Uptrend (Bullish Structure)

```
HH (Higher High)
    ↓
HL (Higher Low)
    ↓
HH
    ↓
HL
```

### Downtrend (Bearish Structure)

```
LH (Lower High)
    ↓
LL (Lower Low)
    ↓
LH
    ↓
LL
```

## Acceptance Criteria

- [ ] Swing detection accurate
- [ ] BOS detection working
- [ ] CHoCH detection working
- [ ] Displacement scoring functional
- [ ] 30+ golden test scenarios passing
