# Strategy Interface

## Base Strategy

All strategies must implement this interface:

```python
class TradingStrategy:
    """Base class for all trading strategies."""

    @property
    def id(self) -> str:
        """Unique strategy identifier."""
        pass

    @property
    def version(self) -> str:
        """Strategy version (semver)."""
        pass

    def is_enabled(self, context: MarketContext) -> bool:
        """Check if strategy should run in current market conditions."""
        pass

    def detect(self, context: MarketContext) -> list[TradeCandidate]:
        """Detect potential trade setups."""
        pass

    def score(self, candidate: TradeCandidate, context: MarketContext) -> int:
        """Score a candidate (0-100)."""
        pass

    def invalidate(self, candidate: TradeCandidate, context: MarketContext) -> bool:
        """Check if a candidate should be invalidated."""
        pass
```

## Rules

1. **Strategy must NOT:**
   - Send orders directly
   - Calculate account risk
   - Query database directly
   - Call MT5 directly

2. **Strategy must:**
   - Use MarketContext for all data
   - Return TradeCandidate objects
   - Implement versioning
   - Have dedicated test suite

## TradeCandidate Schema

```json
{
  "id": "string",
  "strategy_id": "string",
  "strategy_version": "string",
  "symbol": "string",
  "direction": "BUY|SELL",
  "entry_zone": [min, max],
  "stop_loss": "number",
  "take_profit": "number",
  "rr_ratio": "number",
  "rule_score": "number (0-100)",
  "evidence": [{"code": "string", "score": "number"}],
  "warnings": ["string"],
  "invalidation": ["string"],
  "created_at": "datetime"
}
```

## Evidence Schema

Each piece of evidence must have:

```json
{
  "code": "BULLISH_CHOCH",
  "score": 20,
  "timeframe": "M15"
}
```

### Evidence Codes

```
HTF_BULLISH
HTF_BEARISH
SELL_SIDE_SWEEP
BUY_SIDE_SWEEP
BULLISH_CHOCH
BEARISH_CHOCH
BULLISH_BOS
BEARISH_BOS
BULLISH_OB
BEARISH_OB
BULLISH_FVG
BEARISH_FVG
OB_FVG_OVERLAP
DISCOUNT_ZONE
PREMIUM_ZONE
LONDON_SESSION
NEW_YORK_SESSION
STRONG_DISPLACEMENT
WEAK_DISPLACEMENT
```

## Scoring Rules

- Base score: 50
- Positive evidence: +score
- Negative evidence: -score
- Final score: clamp(0, 100)
- Minimum for trade: configurable (default 75)

## Versioning

Every strategy must have a version:

```
v1.0.0
```

Format: MAJOR.MINOR.PATCH

- MAJOR: Breaking change
- MINOR: New feature
- PATCH: Bug fix
