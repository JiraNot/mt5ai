# Model Versioning

## Overview

ทุก model ต้องมี version เพื่อ traceability

## Versioning Schema

```
model_name-v{major}.{minor}.{patch}

Examples:
ai-score-v1.0.0
feature-set-v1.0.0
prompt-v1.0.0
```

## Version Types

| Type | When | Example |
|------|------|---------|
| Major | Architecture change | v2.0.0 |
| Minor | New features/params | v1.1.0 |
| Patch | Bug fix | v1.0.1 |

## Model Registry

```python
class ModelVersion(BaseModel):
    model_name: str
    version: str
    model_type: str  # RULE, LLM, ML, ENSEMBLE
    metrics: dict
    artifact_path: Optional[str]
    status: str  # STAGING, ACTIVE, ARCHIVED
    created_at: datetime
```

## Deployment States

```
STAGING → Testing
ACTIVE → Production
ARCHIVED → Deprecated
```

## Rules

```
1. ทุก Trade ต้องบันทึก strategy_version
2. ทุก AI Decision ต้องบันทึก model_version
3. ห้ามเปลี่ยน ACTIVE model โดยไม่มี approval
4. ARCHIVED model ไม่สามารถกลับมาใช้ได้
5. Rollback ต้องมี audit trail
```

## Acceptance Criteria

- [ ] Version format validated
- [ ] Model registry working
- [ ] Status transitions working
- [ ] Audit trail complete
- [ ] Rollback capability
