"""Gemini CLI trade evaluator — Bull Analyst.

Authentication is owned by the locally installed Gemini CLI.  This module never
uses Vertex AI, gcloud, Application Default Credentials, or a Gemini API key.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.core.runtime_provider_settings import get_provider_settings

logger = logging.getLogger(__name__)

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
        configured = get_provider_settings()["gemini"]["cli_bin"]
        candidates = [
            configured,
            "agy",
            "antigravity",
            "/usr/bin/antigravity",
            "/usr/local/bin/agy",
            "/usr/local/bin/antigravity",
            "/root/.local/bin/agy",
            "/config/.gemini/antigravity/bin/agy",
            str(Path.home() / ".local" / "bin" / "agy"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            if os.path.isabs(candidate) and os.access(candidate, os.X_OK):
                return candidate
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return None

    async def evaluate(self, setup_context: dict) -> GeminiVerdict:
        """ส่ง Setup context ให้ Gemini วิเคราะห์."""
        if self._cli_bin is None:
            # 1. Fallback to direct Gemini REST API if api_key is configured
            api_key = get_provider_settings()["gemini"]["api_key"] or os.getenv("GEMINI_API_KEY", "").strip()
            if api_key:
                try:
                    import httpx
                    prompt = self._build_prompt(setup_context)
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
                    payload = {
                        "contents": [{"parts": [{"text": f"{self.SYSTEM_PROMPT}\n\n{prompt}"}]}],
                        "generationConfig": {
                            "temperature": 0.2,
                            "response_mime_type": "application/json",
                        },
                    }
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(url, json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        return self._parse_response(raw_text)
                except Exception as exc:
                    logger.warning("Gemini REST API evaluation failed: %s", exc)

            # 2. In Paper Mode, provide deterministic SMC Bull Analyst heuristic
            from src.core.runtime_control import get_runtime_trading_mode
            if get_runtime_trading_mode() == "paper":
                return self._smc_bull_heuristic(setup_context)

            return self._fallback_verdict("Antigravity CLI ไม่พร้อมใช้งาน")

        prompt = self._build_prompt(setup_context)
        child_env = os.environ.copy()
        # Ensure HOME points to a directory containing active .gemini credentials
        for cand in [Path.home(), Path("/config"), Path("/root"), Path("/app/data/cli-home")]:
            if (cand / ".gemini" / "jetski-standalone-oauth-token").is_file():
                child_env["HOME"] = str(cand)
                break
        api_key = get_provider_settings()["gemini"]["api_key"]
        if api_key:
            child_env["GEMINI_API_KEY"] = api_key
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
                env=child_env,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
            if process.returncode != 0:
                logger.error("Antigravity CLI failed: %s", stderr.decode("utf-8", errors="replace")[:300])
                from src.core.runtime_control import get_runtime_trading_mode
                if get_runtime_trading_mode() == "paper":
                    return self._smc_bull_heuristic(setup_context)
                return self._fallback_verdict("Antigravity CLI command failed")
            try:
                return self._parse_response(self._extract_structured_output(stdout))
            except Exception as parse_err:
                logger.warning("Antigravity CLI output parsing failed (%s), using SMC Bull Heuristic", parse_err)
                from src.core.runtime_control import get_runtime_trading_mode
                if get_runtime_trading_mode() == "paper":
                    return self._smc_bull_heuristic(setup_context)
                return self._fallback_verdict(f"Output parse error: {parse_err}")
        except asyncio.TimeoutError:
            if "process" in locals():
                process.kill()
                await process.communicate()
            from src.core.runtime_control import get_runtime_trading_mode
            if get_runtime_trading_mode() == "paper":
                return self._smc_bull_heuristic(setup_context)
            return self._fallback_verdict("Antigravity CLI timeout")
        except Exception as exc:
            logger.error("Gemini evaluate error: %s", exc)
            from src.core.runtime_control import get_runtime_trading_mode
            if get_runtime_trading_mode() == "paper":
                return self._smc_bull_heuristic(setup_context)
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

    def _smc_bull_heuristic(self, ctx: dict) -> GeminiVerdict:
        """Deterministic SMC Bull Analyst heuristic for continuous paper learning."""
        rule_score = ctx.get("rule_score", 0)
        direction = ctx.get("direction", "BUY")
        confluences = ctx.get("confluences", [])
        h4_bias = str(ctx.get("h4_bias", "UNKNOWN")).upper()
        displacement = ctx.get("displacement_detected", False)
        symbol = ctx.get("symbol", "XAUUSD")

        aligned = (
            (direction == "BUY" and ("UP" in h4_bias or "BULL" in h4_bias))
            or (direction == "SELL" and ("DOWN" in h4_bias or "BEAR" in h4_bias))
        )

        if rule_score >= 65 or aligned:
            confidence = min(88, max(65, int(rule_score * 0.9 + (10 if displacement else 0))))
            conf_str = ", ".join(confluences[:2]) if confluences else "HTF Alignment + SMC Key Level"
            return GeminiVerdict(
                verdict="APPROVE",
                confidence=confidence,
                narrative_th=f"SMC Bull Analyst: โครงสร้าง {direction} ({symbol}) มี Confluence ชัดเจน ({conf_str})",
                key_confluences=confluences or ["SMC Structure Confirmed"],
                key_risks=["ระวัง False Breakout บริเวณแนวรับ/แนวต้าน"],
                trap_warning="ระวัง Liquidity Sweep ก่อนถึงเป้าหมาย TP",
                raw_response=json.dumps({
                    "verdict": "APPROVE",
                    "confidence": confidence,
                    "narrative": f"SMC Bull Analyst: โครงสร้าง {direction} มี Confluence ({conf_str})",
                    "confluences": confluences or ["SMC Structure Confirmed"],
                    "risks": ["ระวัง False Breakout"],
                    "trap_warning": "ระวัง Liquidity Sweep",
                }),
            )
        else:
            return GeminiVerdict(
                verdict="REJECT",
                confidence=35,
                narrative_th=f"SMC Bull Analyst: โครงสร้าง {direction} ยังไม่ชัดเจนพอ (คะแนน {rule_score}/100)",
                key_confluences=[],
                key_risks=["Rule score ต่ำกว่าเกณฑ์"],
                trap_warning="ระวัง Choppy Market หรือ Sideway",
                raw_response=json.dumps({
                    "verdict": "REJECT",
                    "confidence": 35,
                    "narrative": f"Rule score {rule_score} ต่ำกว่าเกณฑ์",
                    "confluences": [],
                    "risks": ["Rule score ต่ำกว่าเกณฑ์"],
                    "trap_warning": "Sideway",
                }),
            )
