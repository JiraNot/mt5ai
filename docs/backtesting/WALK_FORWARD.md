# Walk-Forward Testing

## Overview

ห้าม Optimize แล้ว test บนข้อมูลเดียวกัน

## Data Split

```
Training / Optimization: 60%
Validation: 20%
Out-of-sample Test: 20%
```

## Example

```
2023 Jan-Jun: Train/Optimize
2023 Jul-Aug: Validate
2023 Sep-Oct: Test
```

## Rolling Walk-Forward

```
Window 1: Train Jan-Mar, Test Apr
Window 2: Train Feb-Apr, Test May
Window 3: Train Mar-May, Test Jun
...
```

## Rules

```
1. ห้ามเลือก parameter จาก Test set
2. ใช้ Validation set เพื่อ tune
3. Test set ใช้ครั้งเดียว
4. ถ้า ML model → ต้องมี out-of-sample test
5. Walk-forward results ต้อง reproducible
```

## Metrics Comparison

```
Train metrics vs Test metrics:
- ถ้า Train >> Test: Overfitting
- ถ้า Train ≈ Test: Good generalization
- ถ้า Train < Test: Luck (check data)
```

## Acceptance Criteria

- [ ] Data split working
- [ ] Rolling window working
- [ ] No data leakage
- [ ] Overfitting detection
- [ ] Results reproducible
