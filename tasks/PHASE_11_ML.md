# PHASE 11 — Machine Learning

## Objective

สร้าง ML pipeline จาก trade history

## Tasks

### TASK 1101: Candidate Dataset Builder

- [ ] Collect trade candidates
- [ ] Extract features
- [ ] Label outcomes

**Acceptance:**
- Dataset built correctly

---

### TASK 1102: Feature Pipeline

- [ ] Feature extraction
- [ ] Normalization
- [ ] Missing value handling

**Acceptance:**
- Feature pipeline working

---

### TASK 1103: Train/Validation Split

- [ ] Time-based split
- [ ] No data leakage

**Acceptance:**
- Split correct

---

### TASK 1104: Baseline

- [ ] Rule Score only baseline
- [ ] Accuracy metrics

**Acceptance:**
- Baseline established

---

### TASK 1105: Logistic Regression

- [ ] Train model
- [ ] Evaluate

**Acceptance:**
- Model working

---

### TASK 1106: Random Forest

- [ ] Train model
- [ ] Evaluate
- [ ] Feature importance

**Acceptance:**
- Model working

---

### TASK 1107: Gradient Boosting

- [ ] LightGBM / XGBoost
- [ ] Train model
- [ ] Evaluate

**Acceptance:**
- Model working

---

### TASK 1108: Model Comparison

- [ ] Compare all models
- [ ] vs baseline
- [ ] Select best

**Acceptance:**
- Comparison complete
- ML beats baseline (or don't deploy)

---

### TASK 1109: Model Registry

- [ ] Version control
- [ ] Metric tracking
- [ ] Deployment status

**Acceptance:**
- Registry working

---

## Rules

```
1. ML model MUST beat Rule Score baseline
   If not → DO NOT DEPLOY

2. Walk-forward validation required

3. Feature importance must be interpretable

4. No black-box deployment
```

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 1101 | ❌ Not done | |
| 1102 | ✅ Done | Feature engine ready |
| 1103 | ❌ Not done | |
| 1104 | ❌ Not done | |
| 1105 | ❌ Not done | |
| 1106 | ❌ Not done | |
| 1107 | ❌ Not done | |
| 1108 | ❌ Not done | |
| 1109 | ❌ Not done | |
