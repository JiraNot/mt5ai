"""GPT/Codex Trade Evaluator — Bear Analyst.

ใช้ OpenAI Codex CLI Auth Login (ChatGPT OAuth ที่ล็อกอินไว้แล้ว)
ไม่ต้องใช้ API Key / API Token ใดๆ!
อ่านเซสชันโดยตรงจาก ~/.codex/auth.json ผ่าน Codex CLI

Role: GPT = Bear Analyst — หาเหตุผลว่า "ทำไมไม่ควรเข้าไม้ / มีกับดักอะไรซ่อนอยู่"
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# รายการ path ที่อาจพบ codex executable
CODEX_CANDIDATE_PATHS = [
    shutil.which("codex") or "",
    "/usr/local/bin/codex",
    "/usr/bin/codex",
    os.path.expanduser("~/.local/bin/codex"),
    "/mnt/c/Users/Dulla/.codex/plugins/.plugin-appserver/codex.exe",
    r"C:\Users\Dulla\.codex\plugins\.plugin-appserver\codex.exe",
]


def find_codex_bin() -> str | None:
    """ค้นหา Codex CLI executable สำหรับรัน auth login session."""
    for p in CODEX_CANDIDATE_PATHS:
        if p and os.path.exists(p):
            return p
    return None


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
    """GPT Bear Analyst — ใช้ ChatGPT Auth Login ผ่าน Codex CLI (Zero Token)."""

    SYSTEM_PROMPT = """คุณคือ AI Trade Risk Analyst ผู้เชี่ยวชาญด้าน Smart Money Concepts (SMC)
คุณรับบท "Bear Analyst" หน้าที่ของคุณคือ:
1. มองหาเหตุผลว่าทำไม Setup นี้ถึงอาจ FAIL
2. ตรวจหา Liquidity Trap, Bear Trap, Bull Trap
3. ตรวจสอบว่ามีสัญญาณที่ขัดแย้งกับ Setup ไหม
4. ให้ Verdict: APPROVE (ยอมรับ risk) หรือ REJECT (risk สูงเกินไป)

คุณเป็น devil's advocate — สงสัยทุกอย่างก่อน
ตอบเป็น JSON เท่านั้น (ห้ามมีคำอธิบายอื่นนอกเหนือจาก JSON):
{
  "verdict": "APPROVE" หรือ "REJECT",
  "confidence": 0-100,
  "narrative": "บทวิเคราะห์ 2-3 ประโยค",
  "bear_case": ["เหตุผล 1", "เหตุผล 2"],
  "trap_identified": "ชื่อกับดัก ถ้าพบ",
  "counter_argument": "ทำไมถึง APPROVE ถ้าเลือก APPROVE"
}"""

    def __init__(self) -> None:
        self._codex_bin = find_codex_bin()
        if self._codex_bin:
            logger.info("GPT Evaluator: ใช้ Codex CLI Auth Login (Path: %s)", self._codex_bin)
        else:
            logger.warning("Codex CLI executable ไม่พบใน path ที่ระบุ")

    async def evaluate(self, setup_context: dict) -> GPTVerdict:
        """ส่ง Setup context ให้ GPT/Codex วิเคราะห์ผ่าน Auth Login."""
        prompt = self._build_prompt(setup_context)

        # 1. รันผ่าน Codex CLI (Auth Login / OAuth - ไม่ต้องใช้ API Token)
        if self._codex_bin:
            try:
                full_prompt = f"{self.SYSTEM_PROMPT}\n\n{prompt}"
                cmd = [
                    self._codex_bin,
                    "exec",
                    "--skip-git-repo-check",
                    "--ephemeral",
                    full_prompt,
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
                    out_text = stdout.decode("utf-8", errors="replace")
                    if proc.returncode == 0 and out_text.strip():
                        return self._parse_response(out_text)
                    logger.warning("Codex exec returned code %d: %s", proc.returncode, stderr.decode()[:200])
                except asyncio.TimeoutError:
                    proc.kill()
                    logger.error("Codex exec timeout after 60s")
            except Exception as exc:
                logger.error("Codex CLI evaluation error: %s", exc)

        # 2. Fallback เฉพาะกรณีมี OPENAI_API_KEY ใน env
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key:
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=api_key)
                model = os.getenv("OPENAI_MODEL", "gpt-4o")
                response = await client.chat.completions.create(
                    model=model,
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
                logger.error("OpenAI API fallback error: %s", exc)

        return self._fallback_verdict("Codex CLI Auth Login และ API Key ไม่พร้อมใช้งาน")

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
        past_lessons = ctx.get("past_lessons", [])
        lessons_text = "\n".join(f"- {l}" for l in past_lessons) if past_lessons else "- ยังไม่มีประวัติความผิดพลาดในระบบ"

        return f"""ตรวจสอบความเสี่ยง Setup นี้ใน {symbol} จากมุมมอง Bear Analyst:

**Setup Details:**
- คู่เงิน/สินทรัพย์: {symbol}
- ทิศทาง: {direction}
- Entry Price: {entry:.2f}
- Stop Loss: {sl:.2f}
- Take Profit: {tp:.2f}
- Risk:Reward Ratio: {rr:.1f}
- Rule Score: {rule_score}/100

**โครงสร้างตลาด (Multi-Timeframe):**
- H4 Bias: {h4_bias}
- H1 Structure: {h1_structure}
- M5 Trigger: {m5_entry}

**ระดับสภาพคล่อง (Liquidity Warning):**
{eql_info}

**🧠 บทเรียนความผิดพลาดในอดีตที่ระบบเคยเจอ (Past Mistakes to Challenge):**
{lessons_text}
*(ในฐานะ Bear Analyst ให้จับตาดูว่า Setup นี้กำลังทำผิดซ้ำรอยบทเรียนในอดีตหรือไม่ ถ้าใช่ให้ REJECT ทันที)*

วิเคราะห์และตอบเป็น JSON ตามรูปแบบที่กำหนดเท่านั้น:"""

    def _parse_response(self, raw: str) -> GPTVerdict:
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
