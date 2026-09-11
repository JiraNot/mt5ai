"""Gemini CLI trade evaluator — Bull Analyst.

Authentication is owned by the locally installed Gemini CLI.  This module never
uses Vertex AI, gcloud, Application Default Credentials, or a Gemini API key.
"""
from __future__ import annotations

import json
import logging
import asyncio
import os
import shutil
from dataclasses import dataclass

logger = logging.getLogger(__name__)

AI_CLI_BIN = os.getenv("AI_CLI_BIN", "agy")

_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["APPROVE", "REJECT"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "narrative": {"type": "string", "minLength": 1},
        "confluences": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "trap_warning": {"type": "string"},
    },
    "required": ["verdict", "confidence", "narrative", "confluences", "risks", "trap_warning"],
    "additionalProperties": False,
}


@dataclass
class GeminiVerdict:
    verdict: str          # "APPROVE" or "REJECT"
    confidence: int       # 0-100
    narrative_th: str     # บทวิเคราะห์ภาษาไทย
    key_confluences: list[str]   # จุดที่เห็นด้วย
    key_risks: list[str]         # ความเสี่ยงที่เจอ
    trap_warning: str            # กับดักที่อาจเจอ
    raw_response: str            # ข้อความดิบจาก Gemini


class GeminiEvaluator:
    """Gemini Bull Analyst — วิเคราะห์ Setup จากมุมมอง SMC ภาษาไทย.

    Auth is provided by an existing Antigravity CLI Google login.
    """

    SYSTEM_PROMPT = """คุณคือ AI Trade Analyst ผู้เชี่ยวชาญด้าน Smart Money Concepts (SMC)
สำหรับตลาด XAU/USD (ทองคำ) คุณรับบท "Bull Analyst" หน้าที่ของคุณคือ:
1. วิเคราะห์ Market Structure จากข้อมูลที่ให้มา (H4, H1, M5)
2. ตรวจสอบว่า Setup นี้สอดคล้องกับ SMC หรือไม่ (Order Block, FVG, BOS/CHoCH)
3. ระบุ Confluence ที่เห็น
4. ระบุกับดัก (Trap) ที่อาจซ่อนอยู่
5. ให้ Verdict: APPROVE หรือ REJECT พร้อมคะแนน 0-100

ห้ามใช้ tool, command, file, workspace inspection, internet search หรือ external action
ให้วิเคราะห์จากข้อมูลใน prompt นี้เท่านั้น

ตอบเป็นภาษาไทยเท่านั้น ใช้ภาษากระชับ ตรงประเด็น
Format การตอบ (JSON):
{
  "verdict": "APPROVE" หรือ "REJECT",
  "confidence": 0-100,
  "narrative": "บทวิเคราะห์ 2-3 ประโยค",
  "confluences": ["จุด 1", "จุด 2"],
  "risks": ["ความเสี่ยง 1"],
  "trap_warning": "กับดักที่อาจเจอ"
}"""

    def __init__(self) -> None:
        self._cli_bin = self._find_cli()

    @staticmethod
    def _find_cli() -> str | None:
        configured = AI_CLI_BIN.strip()
        if os.path.isabs(configured) and os.access(configured, os.X_OK):
            return configured
        return shutil.which(configured)

    async def evaluate(self, setup_context: dict) -> GeminiVerdict:
        """ส่ง Setup context ให้ Gemini วิเคราะห์."""
        if self._cli_bin is None:
            return self._fallback_verdict("Antigravity CLI ไม่พร้อมใช้งาน")

        prompt = self._build_prompt(setup_context)
        try:
            process = await asyncio.create_subprocess_exec(
                self._cli_bin,
                "--print",
                f"{self.SYSTEM_PROMPT}\n\n{prompt}",
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(_VERDICT_SCHEMA),
                "--mode",
                "plan",
                "--sandbox",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
            if process.returncode != 0:
                logger.error("Antigravity CLI failed: %s", stderr.decode("utf-8", errors="replace")[:300])
                return self._fallback_verdict("Antigravity CLI command failed")
            return self._parse_response(self._extract_structured_output(stdout))
        except asyncio.TimeoutError:
            if "process" in locals():
                process.kill()
                await process.communicate()
            return self._fallback_verdict("Antigravity CLI timeout")
        except Exception as exc:
            logger.error("Gemini evaluate error: %s", exc)
            return self._fallback_verdict(f"Error: {exc}")

    @staticmethod
    def _extract_structured_output(stdout: bytes) -> str:
        """Accept the schema result across supported Antigravity CLI envelopes."""
        envelope = json.loads(stdout.decode("utf-8", errors="replace"))
        structured = envelope.get("structured_output")
        if isinstance(structured, dict):
            return json.dumps(structured)

        # Some CLI builds only include the final schema result as the first JSON
        # line in `response`; the strict payload parser still validates it below.
        response = envelope.get("response")
        if isinstance(response, str):
            for line in response.splitlines():
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict):
                    return json.dumps(candidate)
        raise ValueError("Antigravity CLI response has no structured output")

    def _build_prompt(self, ctx: dict) -> str:
        symbol = ctx.get("symbol", "XAUUSD")
        direction = ctx.get("direction", "BUY")
        entry = ctx.get("entry_price", 0)
        sl = ctx.get("stop_loss", 0)
        tp = ctx.get("take_profit", 0)
        rule_score = ctx.get("rule_score", 0)
        confluences = ctx.get("confluences", [])
        h4_bias = ctx.get("h4_bias", "N/A")
        h1_structure = ctx.get("h1_structure", "N/A")
        m5_entry = ctx.get("m5_entry", "N/A")
        eql_info = ctx.get("eql_summary", "ไม่มีข้อมูล EQH/EQL")
        displacement = ctx.get("displacement_detected", False)
        past_lessons = ctx.get("past_lessons", [])
        lessons_text = "\n".join(f"- {l}" for l in past_lessons) if past_lessons else "- ยังไม่มีประวัติความผิดพลาดในระบบ (เปิดรับ Setup ปกติ)"

        return f"""วิเคราะห์ Setup นี้ใน {symbol}:

**Setup Overview:**
- ทิศทาง: {direction}
- Entry: {entry:.2f}
- Stop Loss: {sl:.2f}
- Take Profit: {tp:.2f}
- Rule Score: {rule_score}/100

**Multi-Timeframe Analysis:**
- H4 Bias: {h4_bias}
- H1 Structure: {h1_structure}
- M15 Structure: {ctx.get("m15_structure", "UNKNOWN")}
- M5 Entry: {m5_entry}

**Structured evidence (closed candles only):**
{json.dumps(ctx.get("evidence", {}), ensure_ascii=False)}

**Confluences ที่ตรวจพบ:**
{chr(10).join(f"- {c}" for c in confluences) if confluences else "- ไม่มี"}

**Liquidity (EQH/EQL):**
{eql_info}

**Displacement:** {"ตรวจพบ" if displacement else "ไม่พบ"}

**🧠 บทเรียนจากความทรงจำในอดีต (Continuous Learning Memory):**
{lessons_text}
*(พิจารณาว่า Setup นี้มีความเสี่ยงจะซ้ำรอยบทเรียนความผิดพลาดในอดีตหรือไม่)*

ในฐานะ Bull Analyst กรุณาวิเคราะห์ว่า Setup นี้ควร APPROVE หรือ REJECT
ตรวจหา Liquidity Trap และ Fair Value Gap ที่อาจทำให้ราคากลับตัวก่อนถึง TP"""

    def _parse_response(self, raw: str) -> GeminiVerdict:
        from src.ai.response_schema import GeminiPayload, parse_payload
        try:
            data = parse_payload(raw, GeminiPayload)
            return GeminiVerdict(
                verdict=data.verdict, confidence=data.confidence,
                narrative_th=data.narrative, key_confluences=data.confluences, key_risks=data.risks, trap_warning=data.trap_warning,
                raw_response=raw,
            )
        except (ValueError, TypeError):
            result = self._fallback_verdict("Invalid AI response schema")
            result.raw_response = raw
            return result

    def _fallback_verdict(self, reason: str) -> GeminiVerdict:
        return GeminiVerdict(
            verdict="REJECT",
            confidence=0,
            narrative_th=f"Gemini ไม่สามารถวิเคราะห์ได้: {reason}",
            key_confluences=[],
            key_risks=[reason],
            trap_warning="",
            raw_response="",
        )
