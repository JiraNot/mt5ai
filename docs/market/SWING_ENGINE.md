# Swing Engine

## Overview

Swing Engine ตรวจจับจุดกลับตัว (Swing High/Low) ในราคา

## Algorithm

### Pivot Detection

```python
class SwingDetector:
    def __init__(self, left_bars: int = 3, right_bars: int = 3):
        self.left_bars = left_bars
        self.right_bars = right_bars
```

### Swing High

```
high[i] > highs ของ left N bars
AND
high[i] >= highs ของ right N bars
```

### Swing Low

```
low[i] < lows ของ left N bars
AND
low[i] <= lows ของ right N bars
```

## Output

```python
class SwingPoint(BaseModel):
    symbol: str
    timeframe: str
    timestamp: datetime
    type: SwingType  # HIGH, LOW
    price: Decimal
    strength: int  # 0-100
    confirmed: bool = False
    confirmed_at: Optional[datetime] = None
```

## Confirmation Rule

**Swing จะถือว่า confirmed เมื่อ right bars ครบแล้วเท่านั้น**

```
Index 0-2: Cannot confirm (need right bars)
Index 3+: Can confirm if pivot condition met
```

## Strength Calculation

```python
def calculate_strength(self, candles: List[Candle], index: int) -> int:
    """
    Score based on:
    - Body/range ratio
    - Volume relative to average
    - Number of consecutive candles in direction
    - Distance from recent structure
    """
    ...
```

## Configuration

```yaml
structure:
  swing_lookback: 3  # left_bars and right_bars
```

## Acceptance Criteria

- [ ] Swing High detected correctly
- [ ] Swing Low detected correctly
- [ ] Confirmation works properly
- [ ] Strength scoring functional
- [ ] Golden tests passing
