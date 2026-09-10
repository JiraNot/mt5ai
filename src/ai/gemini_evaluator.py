"""Gemini AI Trade Evaluator — Bull Analyst.

ใช้ Google Application Default Credentials (ADC)
รัน: gcloud auth application-default login  ครั้งเดียวบน server
Python จะหา credentials อัตโนมัติ ไม่ต้องใส่ API Key ในโค้ด

Role: Gemini = Bull Analyst — หาเหตุผลว่า "ทำไมควรเข้าไม้"
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ใช้ google-genai SDK (ไม่ใช่ google-generativeai เดิม)
try:
    from google import genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    logger.warning("google-genai ยังไม่ได้ติดตั้ง: pip install google-genai")


GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # Optional fallback


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

    Auth: ใช้ ADC (Application Default Credentials)
    ถ้าตั้ง GEMINI_API_KEY ใน env จะใช้ API Key แทน
    """

    SYSTEM_PROMPT = """คุณคือ AI Trade Analyst ผู้เชี่ยวชาญด้าน Smart Money Concepts (SMC)
สำหรับตลาด XAU/USD (ทองคำ) คุณรับบท "Bull Analyst" หน้าที่ของคุณคือ:
1. วิเคราะห์ Market Structure จากข้อมูลที่ให้มา (H4, H1, M5)
2. ตรวจสอบว่า Setup นี้สอดคล้องกับ SMC หรือไม่ (Order Block, FVG, BOS/CHoCH)
3. ระบุ Confluence ที่เห็น
4. ระบุกับดัก (Trap) ที่อาจซ่อนอยู่
5. ให้ Verdict: APPROVE หรือ REJECT พร้อมคะแนน 0-100

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
        self._client: Any = None
        self._init_client()

    def _init_client(self) -> None:
        if not _GENAI_AVAILABLE:
            return
        try:
            if GEMINI_API_KEY:
                # ใช้ API Key (fallback)
                self._client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info("Gemini: ใช้ API Key auth")
            else:
                # ใช้ ADC (Application Default Credentials)
                self._client = genai.Client()
                logger.info("Gemini: ใช้ ADC auth (gcloud)")
        except Exception as exc:
            logger.error("Gemini init failed: %s", exc)

    async def evaluate(self, setup_context: dict) -> GeminiVerdict:
        """ส่ง Setup context ให้ Gemini วิเคราะห์."""
        if not _GENAI_AVAILABLE or self._client is None:
            return self._fallback_verdict("Gemini ไม่พร้อมใช้งาน")

        prompt = self._build_prompt(setup_context)
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.interactions.create(
                    model=GEMINI_MODEL,
                    system_instruction=self.SYSTEM_PROMPT,
                    input=prompt,
                    store=False,  # ไม่เก็บ interaction (privacy)
                ),
            )
            return self._parse_response(response.output_text or "")
        except Exception as exc:
            logger.error("Gemini evaluate error: %s", exc)
            return self._fallback_verdict(f"Error: {exc}")

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
- M5 Entry: {m5_entry}

**Confluences ที่ตรวจพบ:**
{chr(10).join(f"- {c}" for c in confluences) if confluences else "- ไม่มี"}

**Liquidity (EQH/EQL):**
{eql_info}

**Displacement:** {"ตรวจพบ" if displacement else "ไม่พบ"}

ในฐานะ Bull Analyst กรุณาวิเคราะห์ว่า Setup นี้ควร APPROVE หรือ REJECT
ตรวจหา Liquidity Trap และ Fair Value Gap ที่อาจทำให้ราคากลับตัวก่อนถึง TP"""

    def _parse_response(self, raw: str) -> GeminiVerdict:
        import json
        import re
        try:
            # หา JSON block ในข้อความ
            match = re.search(r"\{.*?\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return GeminiVerdict(
                    verdict=data.get("verdict", "REJECT").upper(),
                    confidence=int(data.get("confidence", 50)),
                    narrative_th=data.get("narrative", raw[:200]),
                    key_confluences=data.get("confluences", []),
                    key_risks=data.get("risks", []),
                    trap_warning=data.get("trap_warning", ""),
                    raw_response=raw,
                )
        except (json.JSONDecodeError, AttributeError):
            pass

        # Fallback: parse text
        verdict = "APPROVE" if "APPROVE" in raw.upper() else "REJECT"
        return GeminiVerdict(
            verdict=verdict,
            confidence=60 if verdict == "APPROVE" else 40,
            narrative_th=raw[:300] if raw else "ไม่สามารถวิเคราะห์ได้",
            key_confluences=[],
            key_risks=[],
            trap_warning="",
            raw_response=raw,
        )

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
