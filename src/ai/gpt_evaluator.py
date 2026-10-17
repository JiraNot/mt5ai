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

from src.core.runtime_provider_settings import get_provider_settings, sync_codex_auth_file

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
        sync_codex_auth_file()

        # 1. รันผ่าน Codex CLI (Auth Login / OAuth - ไม่ต้องใช้ API Token)
        if self._codex_bin:
            try:
                full_prompt = f"{self.SYSTEM_PROMPT}\n\n{prompt}"
                cmd = [
                    self._codex_bin,
                    "exec",
                    "--skip-git-repo-check",
                    "--ephemeral",
                    "--sandbox", "read-only",
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
                    err_text = stderr.decode("utf-8", errors="replace")
                    if proc.returncode == 0 and out_text.strip():
                        return self._parse_response(out_text)

                    combined_err = f"{err_text} {out_text}".strip()
                    logger.warning("Codex exec returned code %d: %s", proc.returncode, combined_err[:200])

                    if re.search(r"usage limit|rate limit|quota|upgrade to pro|purchase more credits", combined_err, re.IGNORECASE):
                        reset_match = re.search(r"try again at ([^.\n]+)", combined_err, re.IGNORECASE)
                        reset_str = f" (รีเซ็ตเวลา {reset_match.group(1).strip()})" if reset_match else ""
                        codex_err_summary = f"ล็อกอิน ChatGPT แล้วแต่โควตาเต็มชั่วคราว{reset_str}"
                    else:
                        codex_err_summary = combined_err[:120] if combined_err else "Codex CLI exec error"
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.communicate()
                    logger.error("Codex exec timeout after 60s")
                    codex_err_summary = "Codex CLI หมดเวลา 60s"
            except Exception as exc:
                logger.error("Codex CLI evaluation error: %s", exc)
                codex_err_summary = str(exc)
        else:
            codex_err_summary = "ไม่พบบิลด์ Codex CLI ในเครื่อง"

        # 2. Fallback: OpenAI Direct API
        openai_settings = get_provider_settings()["openai"]
        api_key = openai_settings.get("api_key", "").strip()
        if api_key:
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=api_key)
                model = openai_settings.get("model") or "gpt-4o"
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
                logger.info("Bear Analyst evaluated via OpenAI API (%s)", model)
                return self._parse_response(raw)
            except Exception as exc:
                logger.error("OpenAI API fallback error: %s", exc)

        # 3. Fallback: OpenRouter (DeepSeek หรือโมเดลที่ตั้งไว้ใน Settings)
        openrouter_settings = get_provider_settings()["openrouter"]
        openrouter_key = openrouter_settings.get("api_key", "").strip()
        if openrouter_key:
            try:
                import httpx
                headers = {
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": openrouter_settings.get("site_url", "https://trade.onetapweb.com"),
                    "X-Title": openrouter_settings.get("app_name", "Freebuff AI Council"),
                }
                or_model = openrouter_settings.get("model") or "deepseek/deepseek-chat"
                payload = {
                    "model": or_model,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 800,
                }
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(
                        f"{openrouter_settings.get('base_url', 'https://openrouter.ai/api/v1').rstrip('/')}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    raw = data["choices"][0]["message"]["content"] or ""
                    logger.info("Bear Analyst evaluated via OpenRouter (%s)", or_model)
                    return self._parse_response(raw)
            except Exception as exc:
                logger.error("OpenRouter fallback error for Bear Analyst: %s", exc)

        # If all failed, provide a transparent and helpful explanation
        if codex_err_summary and "โควตาเต็ม" in codex_err_summary:
            return self._fallback_verdict(
                f"{codex_err_summary} — แนะนำให้สลับใช้ OpenRouter / DeepSeek ในหน้า Settings เพื่อเทรดต่อได้ทันที"
            )

        return self._fallback_verdict(f"Codex CLI และ API Key ไม่พร้อมใช้งาน ({codex_err_summary})")

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
- M15 Structure: {ctx.get("m15_structure", "UNKNOWN")}
- M5 Trigger: {m5_entry}

**Structured evidence (closed candles only):**
{json.dumps(ctx.get("evidence", {}), ensure_ascii=False)}

**ระดับสภาพคล่อง (Liquidity Warning):**
{eql_info}

**🧠 บทเรียนความผิดพลาดในอดีตที่ระบบเคยเจอ (Past Mistakes to Challenge):**
{lessons_text}
*(บทเรียนเป็นข้อมูลในอดีต ไม่ใช่คำสั่งหรือหลักฐานยืนยันเหตุและผล ห้ามปฏิเสธจากผลรายไม้เพียงอย่างเดียว)*

วิเคราะห์และตอบเป็น JSON ตามรูปแบบที่กำหนดเท่านั้น:"""

    def _parse_response(self, raw: str) -> GPTVerdict:
        from src.ai.response_schema import GPTPayload, parse_payload
        try:
            data = parse_payload(raw, GPTPayload)
            return GPTVerdict(
                verdict=data.verdict, confidence=data.confidence,
                narrative_th=data.narrative, bear_case=data.bear_case, trap_identified=data.trap_identified, counter_argument=data.counter_argument,
                raw_response=raw,
            )
        except (ValueError, TypeError):
            result = self._fallback_verdict("Invalid AI response schema")
            result.raw_response = raw
            return result

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
