# Golden Scenario Tests

## Overview

Golden Tests คือ historical scenarios ที่รู้คำตอบแล้ว ใช้ป้องกัน regression

## Structure

```
tests/golden/
├── bullish_choch/
│   ├── scenario_001/
│   │   ├── candles.csv
│   │   └── expected.json
│   ├── scenario_002/
│   └── ...
├── bearish_choch/
├── false_breakout/
├── bullish_fvg/
├── fvg_fill/
├── bullish_ob/
├── liquidity_sweep/
└── invalid_setup/
```

## Expected Output Format

```json
{
  "scenario_id": "bullish_choch_001",
  "description": "Clear bullish CHoCH after downtrend",
  "expected": {
    "choch_detected": true,
    "choch_direction": "BULLISH",
    "choch_index": 48,
    "bos_detected": false,
    "ob_detected": true,
    "fvg_detected": true,
    "candidate_generated": true,
    "candidate_direction": "BUY",
    "minimum_score": 75
  }
}
```

## Scenario Categories

### Structure Detection

```
- bullish_choch: Trend reversal to upside
- bearish_choch: Trend reversal to downside
- bullish_bos: Continuation upside
- bearish_bos: Continuation downside
```

### Pattern Detection

```
- bullish_fvg: Fair value gap upside
- bearish_fvg: Fair value gap downside
- fvg_fill: FVG fully mitigated
- bullish_ob: Order block upside
- bearish_ob: Order block downside
```

### Liquidity

```
- sell_side_sweep: Liquidity sweep below
- buy_side_sweep: Liquidity sweep above
- equal_highs: Equal high formation
```

### Invalid Setups

```
- false_breakout: Breakout that fails
- weak_choch: CHoCH without displacement
- low_score: Setup below threshold
```

## Test Execution

```python
def test_golden_scenario(scenario_path):
    candles = load_candles(f"{scenario_path}/candles.csv")
    expected = load_expected(f"{scenario_path}/expected.json")
    
    # Run structure engine
    structure = structure_engine.analyze(candles)
    
    # Verify detection
    assert structure.choch_detected == expected["choch_detected"]
    assert structure.choch_direction == expected["choch_direction"]
    
    # Run strategy
    candidates = strategy.detect(context)
    
    # Verify candidate
    assert len(candidates) > 0
    assert candidates[0].direction == expected["candidate_direction"]
```

## Regression Prevention

```
เมื่อแก้ algorithm:
1. Run all golden tests
2. ถ้ามี test fail → ต้อง investigate
3. ห้าม force pass
4. Update golden test only with approval
```

## Acceptance Criteria

- [ ] 30+ golden scenarios created
- [ ] All scenarios passing
- [ ] Regression prevention working
- [ ] New scenarios can be added
