"""Versioned, fail-closed provider response contracts."""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

VERSION = "2.0.0"

class VerdictPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    verdict: Literal["APPROVE", "REJECT"]
    confidence: int = Field(ge=0, le=100)
    narrative: str = Field(min_length=1)

class GPTPayload(VerdictPayload):
    bear_case: list[str]
    trap_identified: str
    counter_argument: str

class GeminiPayload(VerdictPayload):
    confluences: list[str]
    risks: list[str]
    trap_warning: str

def parse_payload(raw: str, schema):
    text = raw.strip()
    if text.startswith("```json\n") and text.endswith("```"):
        text = text[8:-3].strip()
    elif text.startswith("```\n") and text.endswith("```"):
        text = text[4:-3].strip()
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return schema.model_validate(json.loads(text, object_pairs_hook=unique_pairs))
