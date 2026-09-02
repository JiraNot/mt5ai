# PHASE 10 — AI Shadow Mode

## Objective

เพิ่ม AI layer ใน shadow mode — วิเคราะห์แต่ไม่มี execution authority

## Tasks

### TASK 1001: Structured Feature Payload

- [ ] Market context → JSON
- [ ] Candidate context
- [ ] Feature extraction

**Acceptance:**
- Feature payload valid

---

### TASK 1002: LLM Provider Abstraction

- [ ] Provider interface
- [ ] OpenAI provider
- [ ] Anthropic provider
- [ ] Local provider

**Acceptance:**
- Provider abstraction working

---

### TASK 1003: Response Schema Validation

- [ ] Validate AI response
- [ ] Fallback to RULE on failure

**Acceptance:**
- Response validated

---

### TASK 1004: AI Journal

- [ ] Log AI decisions
- [ ] Log confidence
- [ ] Log reason codes

**Acceptance:**
- AI decisions logged

---

### TASK 1005: Shadow Evaluation

- [ ] AI evaluates in shadow
- [ ] No execution authority
- [ ] Compare with rule engine

**Acceptance:**
- Shadow mode working

---

### TASK 1006: Rule vs AI Comparison

- [ ] Track agreement/disagreement
- [ ] Measure AI accuracy
- [ ] Generate comparison report

**Acceptance:**
- Comparison working

---

## Important Rules

```
AI ห้ามมี execution authority ใน Phase นี้

AI ทำหน้าที่:
- Evaluate candidates
- Log decisions
- Compare with rule engine

AI ไม่ทำหน้าที่:
- Execute orders
- Modify risk limits
- Override risk engine
```

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 1001 | ✅ Done | Feature engine ready |
| 1002 | ❌ Not done | |
| 1003 | ❌ Not done | |
| 1004 | ⚠️ Partial | |
| 1005 | ❌ Not done | |
| 1006 | ❌ Not done | |
