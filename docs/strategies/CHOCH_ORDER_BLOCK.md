# CHoCH + Order Block Strategy

## Overview

**Primary MVP Strategy** — ตรวจจับการเปลี่ยนแปลงโครงสร้างราคา (CHoCH) แล้วเข้าที่ Order Block

## LONG Setup

```
1. HTF bias bullish หรือ neutral
2. Sell-side liquidity sweep (preferred)
3. Bullish CHoCH confirmed
4. Bullish displacement
5. Bullish Order Block identified
6. Price retraces into OB
7. RR >= threshold (2.0)
→ BUY
```

## SHORT Setup

```
1. HTF bias bearish หรือ neutral
2. Buy-side liquidity sweep (preferred)
3. Bearish CHoCH confirmed
4. Bearish displacement
5. Bearish Order Block identified
6. Price retraces into OB
7. RR >= threshold (2.0)
→ SELL
```

## Confluence Bonuses

```
+ FVG overlap: +10
+ Discount zone (long): +5
+ Premium zone (short): +5
+ London/NY session: +5
+ PDL sweep: +10
+ Equal Low sweep: +10
```

## Score Calculation

```
HTF aligned             +15
Sell-side sweep         +20
CHoCH                   +20
Displacement            +15
Fresh OB                +10
FVG overlap             +10
Discount                +5
Preferred session        +5
────────────────────────────
Total: 100
Minimum: 75
```

## Entry Options

```
OB proximal line
OB midpoint
OB 50% mitigation
```

MVP: ENTRY_ZONE (range, not exact price)

## Stop Loss

```
Long: Below OB invalidation + buffer (ATR × 0.10)
Short: Above OB invalidation + buffer (ATR × 0.10)
```

## Take Profit

```
Default: Nearest liquidity target
Must achieve RR >= 2.0
If RR < 2.0 → REJECT
```

## Configuration

```yaml
strategies:
  choch_order_block:
    enabled: true
    version: "1.0.0"
    min_score: 75
    timeframes:
      structure: M15
      entry: M5
    preferred_sessions:
      - LONDON
      - NEW_YORK
```

## Acceptance Criteria

- [ ] LONG setup detected correctly
- [ ] SHORT setup detected correctly
- [ ] Score calculation accurate
- [ ] Entry zone calculated
- [ ] Stop loss calculated
- [ ] Take profit calculated
- [ ] RR validation works
- [ ] Score threshold filtering works
