"""GPT/Codex Trade Evaluator — Bear Analyst.

ใช้ OpenAI Codex CLI OAuth ที่ login ไว้แล้วใน ~/.codex/
ไม่ต้องใส่ API Key ในโค้ด — อ่าน session token จาก Codex CLI state

Role: GPT = Bear Analyst — หาเหตุผลว่า "ทำไมไม่ควรเข้าไม้"
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False
    logger.warning("openai ยังไม่ได้ติดตั้ง: pip install openai")

# อ่าน API Key จาก env (Codex OAuth จะถูก inject เป็น OPENAI_API_KEY โดย codex CLI)
# หรือ mount ผ่าน Docker secret
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # fallback จาก gpt-5.6-sol


@dataclass
class GPTVerdict:
    verdict: str           # "APPROVE" or "REJECT"
    confidence: int        # 0-100
    narrative_th: str      # บทวิเคราะห์ภาษาไทย
    bear_case: list[str]   # เหตุผลที่ไม่ควรเข้า
    trap_identified: str   # กับดักที่เจอ
    counter_argument: str  # ถ้า APPROVE: ทำไมถึงยอมรับ risk
    raw_response: str


class GPTEvaluator:
    """GPT Bear Analyst — หากับดักและเหตุผล NOT to trade.

    Auth: ใช้ OPENAI_API_KEY จาก env
    (Codex CLI inject ให้อัตโนมัติเมื่อรันผ่าน codex subprocess)
    """

    SYSTEM_PROMPT = """คุณคือ AI Trade Risk Analyst ผู้เชี่ยวชาญด้าน Smart Money Concepts (SMC)
คุณรับบท "Bear Analyst" หน้าที่ของคุณคือ:
1. มองหาเหตุผลว่าทำไม Setup นี้ถึงอาจ FAIL
2. ตรวจหา Liquidity Trap, Bear Trap, Bull Trap
3. ตรวจสอบว่ามีสัญญาณที่ขัดแย้งกับ Setup ไหม
4. ให้ Verdict: APPROVE (ยอมรับ risk) หรือ REJECT (risk สูงเกินไป)

คุณเป็น devil's advocate — สงสัยทุกอย่างก่อน
ตอบเป็นภาษาไทยเท่านั้น ใช้ภาษากระชับ

Format (JSON):
{
  "verdict": "APPROVE" หรือ "REJECT",
  "confidence": 0-100,
  "narrative": "บทวิเคราะห์ 2-3 ประโยค",
  "bear_case": ["เหตุผล 1", "เหตุผล 2"],
  "trap_identified": "ชื่อกับดัก ถ้าพบ",
  "counter_argument": "ทำไมถึง APPROVE ถ้าเลือก APPROVE"
}"""

    def __init__(self) -> None:
        self._client: Any = None
        self._init_client()

    def _init_client(self) -> None:
        if not _OPENAI_AVAILABLE:
            return
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY ไม่ได้ตั้งค่า — GPT Evaluator ไม่พร้อม")
            return
        try:
            self._client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            logger.info("GPT Evaluator: เชื่อมต่อ OpenAI สำเร็จ (model: %s)", OPENAI_MODEL)
        except Exception as exc:
            logger.error("GPT init failed: %s", exc)

    async def evaluate(self, setup_context: dict) -> GPTVerdict:
        """ส่ง Setup context ให้ GPT วิเคราะห์."""
        if not _OPENAI_AVAILABLE or self._client is None:
            return self._fallback_verdict("GPT ไม่พร้อมใช้งาน")

        prompt = self._build_prompt(setup_context)
        try:
            response = await self._client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=800,
                temperature=0.3,
            )
            raw = response.choices[0].message.content or ""
            return self._parse_response(raw)
        except Exception as exc:
            logger.error("GPT evaluate error: %s", exc)
            return self._fallback_verdict(f"Error: {exc}")

    def _build_prompt(self, ctx: dict) -> str:
        symbol = ctx.get("symbol", "XAUUSD")
        direction = ctx.get("direction", "BUY")
        entry = ctx.get("entry_price", 0)
        sl = ctx.get("stop_loss", 0)
        tp = ctx.get("take_profit", 0)
        rule_score = ctx.get("rule_score", 0)
        h4_bias = ctx.get("h4_bias", "N/A")
        h1_structure = ctx.get("h1_structure", "N/A")
        m5_entry = ctx.get("m5_entry", "N/A")
        eql_info = ctx.get("eql_summary", "ไม่มีข้อมูล")
        rr = ctx.get("rr_ratio", 0)

        return f"""ตรวจสอบ Setup นี้ใน {symbol} จากมุม Bear (ความเสี่ยง):

**Setup:**
- ทิศทาง: {direction} | Entry: {entry:.2f} | SL: {sl:.2f} | TP: {tp:.2f}
- R:R Ratio: {rr:.1f} | Rule Score: {rule_score}/100

**Timeframe:**
- H4: {h4_bias}
- H1: {h1_structure}
- M5: {m5_entry}

**Liquidity Warning:**
{eql_info}

คุณคือ Bear Analyst — หาทุกเหตุผลที่ทำให้ไม้นี้อาจ FAIL
ระบุกับดักที่ซ่อนอยู่ ถ้าไม่พบจริงๆ ค่อย APPROVE"""

    def _parse_response(self, raw: str) -> GPTVerdict:
        import json
        import re
        try:
            match = re.search(r"\{.*?\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return GPTVerdict(
                    verdict=data.get("verdict", "REJECT").upper(),
                    confidence=int(data.get("confidence", 50)),
                    narrative_th=data.get("narrative", raw[:200]),
                    bear_case=data.get("bear_case", []),
                    trap_identified=data.get("trap_identified", ""),
                    counter_argument=data.get("counter_argument", ""),
                    raw_response=raw,
                )
        except (json.JSONDecodeError, AttributeError):
            pass

        verdict = "APPROVE" if "APPROVE" in raw.upper() else "REJECT"
        return GPTVerdict(
            verdict=verdict,
            confidence=50,
            narrative_th=raw[:300] if raw else "ไม่สามารถวิเคราะห์ได้",
            bear_case=[],
            trap_identified="",
            counter_argument="",
            raw_response=raw,
        )

    def _fallback_verdict(self, reason: str) -> GPTVerdict:
        return GPTVerdict(
            verdict="REJECT",
            confidence=0,
            narrative_th=f"GPT ไม่สามารถวิเคราะห์ได้: {reason}",
            bear_case=[reason],
            trap_identified="",
            counter_argument="",
            raw_response="",
        )
