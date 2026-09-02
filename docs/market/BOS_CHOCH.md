# BOS / CHoCH Detection

## Break of Structure (BOS)

### Bullish BOS

```
Current bullish structure (HH + HL sequence)
+
Confirmed close above relevant Swing High
=
Bullish BOS
```

### Bearish BOS

```
Current bearish structure (LH + LL sequence)
+
Confirmed close below relevant Swing Low
=
Bearish BOS
```

## Change of Character (CHoCH)

### Bullish CHoCH

```
ก่อนหน้า: LH → LL (downtrend)
+
ราคา break relevant LH ด้วย close/displacement
=
Bullish CHoCH (trend reversal signal)
```

### Bearish CHoCH

```
ก่อนหน้า: HL → HH (uptrend)
+
ราคา break relevant HL ด้วย close/displacement
=
Bearish CHoCH (trend reversal signal)
```

## Configuration

```yaml
structure:
  break_mode: CLOSE        # CLOSE, WICK, BODY, DISPLACEMENT
  minimum_break_atr: 0.10  # Minimum break distance in ATR
  require_displacement: true
```

## Break Modes

| Mode | Description |
|------|-------------|
| CLOSE | Candle must close beyond level |
| WICK | Wick can break level |
| BODY | Body must break level |
| DISPLACEMENT | Strong momentum candle required |

## Output

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

## Strength Scoring

```
Base: 50

+ Close beyond level by > 0.5 ATR: +15
+ Displacement candle: +15
+ Volume spike: +10
+ Multi-TF alignment: +10

- Wick only (no close): -20
- Weak momentum: -10
```

## Acceptance Criteria

- [ ] Bullish BOS detected correctly
- [ ] Bearish BOS detected correctly
- [ ] Bullish CHoCH detected correctly
- [ ] Bearish CHoCH detected correctly
- [ ] Break mode configuration works
- [ ] Minimum break ATR filter works
- [ ] Golden tests: 20+ scenarios passing
