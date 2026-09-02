# LLM Decision Layer

## Overview

LLM เหมาะกับ:

```
- Context interpretation
- Trade explanation
- Setup scoring
- Complex confluence
- Trade review
- Market narrative
```

LLM ไม่เหมาะเป็น:

```
- Tick execution engine
- Risk engine
- SL emergency handling
```

## Provider Abstraction

```python
class LLMProvider(ABC):
    @abstractmethod
    async def evaluate(self, context: dict) -> AIDecision:
        ...
    
    @abstractmethod
    async def health_check(self) -> bool:
        ...
```

## Supported Providers

| Provider | Model | Use Case |
|----------|-------|----------|
| OpenAI | GPT-4 | General evaluation |
| Anthropic | Claude | Detailed analysis |
| Local | Llama | Cost-effective |

## Decision Output

```python
class AIDecision(BaseModel):
    decision: DecisionType  # APPROVE, REJECT, UNCERTAIN
    score: int  # 0-100
    confidence: float  # 0-1
    reason_codes: List[str]
    risk_flags: List[str]
    explanation: Optional[str] = None
```

## Response Validation

```python
# ทุก response ต้อง validate กับ schema
# ถ้าไม่ valid → ใช้ RULE score แทน
```

## Configuration

```yaml
ai:
  enabled: false
  provider: RULE
  shadow_mode: true
  min_confidence: 0.7
  timeout_seconds: 30
```

## Acceptance Criteria

- [ ] Provider abstraction working
- [ ] Response validation working
- [ ] Fallback to RULE on failure
- [ ] Shadow mode logging
- [ ] Performance comparison logged
