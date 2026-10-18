"""AI Council — Debate Engine.

รวม Gemini (Bull) + GPT (Bear) มาเถียงกัน
แล้วตัดสิน Combined Verdict

Verdict Logic:
  APPROVE + APPROVE -> Execute
  APPROVE + REJECT  -> Skip (disagreement)
  REJECT  + APPROVE -> Skip (disagreement)
  REJECT  + REJECT  -> Hard Skip
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from src.ai.gemini_evaluator import GeminiEvaluator, GeminiVerdict
from src.ai.gpt_evaluator import GPTEvaluator, GPTVerdict
from src.ai.openrouter_evaluator import OpenRouterEvaluator
from src.core.runtime_control import get_runtime_trading_mode
from src.core.runtime_provider_settings import get_provider_settings

logger = logging.getLogger(__name__)


@dataclass
class CouncilDecision:
    """ผลการตัดสินจาก AI Council."""

    final_verdict: str        # "EXECUTE" / "SKIP" / "HARD_SKIP"
    combined_score: int       # คะแนนรวม 0-100
    gemini_verdict: GeminiVerdict
    gpt_verdict: GPTVerdict
    consensus: bool           # True = เห็นด้วยกัน
    debate_summary_th: str    # สรุปการเถียงกัน
    recommendation: str       # คำแนะนำสุดท้าย

    @property
    def should_execute(self) -> bool:
        return self.final_verdict == "EXECUTE"


class AICouncil:
    """ประสานงาน Gemini + GPT ให้ debate ก่อนตัดสินใจเทรด."""

    VERSION = "2.0.0"

    def __init__(
        self,
        min_rule_score: int = 60,
        require_consensus: bool = False,
        min_combined_score: int = 65,
        min_single_approval_confidence: int = 75,
        min_single_provider_rule_score: int = 80,
    ) -> None:
        self.min_rule_score = min_rule_score
        self.require_consensus = require_consensus
        self.min_combined_score = min_combined_score
        self.min_single_approval_confidence = min_single_approval_confidence
        self.min_single_provider_rule_score = min_single_provider_rule_score
        self.bull_provider = ""
        self.gemini: GeminiEvaluator
        self._refresh_bull_provider()
        self.gpt = GPTEvaluator()

    def _refresh_bull_provider(self) -> None:
        """Apply dashboard provider changes without restarting the worker."""
        provider = "deepseek" if get_provider_settings()["openrouter"]["api_key"] else "gemini"
        if provider == self.bull_provider:
            return
        self.bull_provider = provider
        self.gemini = OpenRouterEvaluator() if provider == "deepseek" else GeminiEvaluator()

    async def evaluate(self, setup_context: dict) -> CouncilDecision:
        """รับ Setup context แล้วให้ AI Council ตัดสิน."""
        self._refresh_bull_provider()
        rule_score = setup_context.get("rule_score", 0)

        if rule_score < self.min_rule_score:
            logger.info("Rule score %d < %d — Skip AI Council", rule_score, self.min_rule_score)
            return self._skip_decision("Rule score ต่ำเกินไป", rule_score)

        logger.info("AI Council: กำลังประเมิน Setup (Rule score: %d)", rule_score)

        gemini_result, gpt_result = await asyncio.gather(
            self.gemini.evaluate(setup_context),
            self.gpt.evaluate(setup_context),
            return_exceptions=True,
        )

        if isinstance(gemini_result, Exception):
            logger.error("%s error: %s", self.bull_provider.title(), gemini_result)
            gemini_result = GeminiVerdict(
                verdict="REJECT", confidence=0,
                narrative_th="Gemini Error: " + str(gemini_result),
                key_confluences=[], key_risks=[], trap_warning="", raw_response="",
            )

        if isinstance(gpt_result, Exception):
            logger.error("GPT error: %s", gpt_result)
            gpt_result = GPTVerdict(
                verdict="REJECT", confidence=0,
                narrative_th="GPT Error: " + str(gpt_result),
                bear_case=[], trap_identified="", counter_argument="", raw_response="",
            )

        is_paper = (
            setup_context.get("is_paper")
            or (setup_context.get("trading_mode") == "paper")
            or (get_runtime_trading_mode() == "paper")
        )
        return self._make_decision(gemini_result, gpt_result, rule_score, is_paper=is_paper)

    def _make_decision(
        self,
        gemini: GeminiVerdict,
        gpt: GPTVerdict,
        rule_score: int,
        is_paper: bool = False,
    ) -> CouncilDecision:
        gemini_approve = gemini.verdict == "APPROVE"
        gpt_approve = gpt.verdict == "APPROVE"
        consensus = gemini_approve == gpt_approve

        gemini_unavailable = (
            not gemini_approve and gemini.confidence == 0 and not gemini.raw_response
        )
        gpt_unavailable = (
            not gpt_approve and gpt.confidence == 0 and not gpt.raw_response
        )

        # Dynamic weight normalization:
        # If an analyst is unavailable, re-normalize weights across active components
        # rather than penalizing the setup with a 0-confidence deficit.
        if gemini_unavailable and gpt_unavailable:
            combined = int(rule_score)
        elif gemini_unavailable:
            combined = int(rule_score * 0.45 + gpt.confidence * 0.55)
        elif gpt_unavailable:
            combined = int(rule_score * 0.45 + gemini.confidence * 0.55)
        else:
            combined = int(
                rule_score * 0.40
                + gemini.confidence * 0.35
                + gpt.confidence * 0.25
            )

        both_approve = gemini_approve and gpt_approve
        one_approves = gemini_approve != gpt_approve
        approving_confidence = max(
            gemini.confidence if gemini_approve else 0,
            gpt.confidence if gpt_approve else 0,
        )

        single_provider_fallback = (
            one_approves
            and not self.require_consensus
            and (gemini_unavailable or gpt_unavailable)
            and rule_score >= self.min_single_provider_rule_score
            and approving_confidence >= self.min_single_approval_confidence
        )

        # A disagreement is allowed to proceed to the Risk Engine only when
        # the approving analyst is highly confident and the combined score is
        # still strong. Risk Engine remains the final authority.
        high_confidence_disagreement = (
            one_approves
            and not self.require_consensus
            and approving_confidence >= self.min_single_approval_confidence
            and combined >= self.min_combined_score
        )

        # Paper Learning Mode:
        # In PAPER mode, allow exploration trades for SMC candidates so TradeLearner
        # can observe trades, evaluate R-multiples, and generate lessons.
        # Fail-closed consensus is preserved for LIVE mode.
        paper_learning_eligible = (
            is_paper
            and not self.require_consensus
            and rule_score >= self.min_rule_score
        )
        paper_exploration = (
            paper_learning_eligible
            and (
                (gemini_unavailable and gpt_unavailable and rule_score >= 65)
                or (one_approves and combined >= 58 and rule_score >= 65)
            )
        )

        if (
            (both_approve and combined >= self.min_combined_score)
            or high_confidence_disagreement
            or single_provider_fallback
            or paper_exploration
        ):
            verdict = "EXECUTE"
        elif not gemini_approve and not gpt_approve:
            verdict = "HARD_SKIP"
        else:
            verdict = "SKIP"

        debate = self._build_debate_summary(gemini, gpt, verdict, combined, is_paper=is_paper)
        recommendation = self._build_recommendation(gemini, gpt, verdict, paper_exploration=paper_exploration)

        logger.info(
            "AI Council: %s (Gemini=%s/GPT=%s, Combined=%d, Paper=%s)",
            verdict, gemini.verdict, gpt.verdict, combined, is_paper,
        )

        return CouncilDecision(
            final_verdict=verdict,
            combined_score=combined,
            gemini_verdict=gemini,
            gpt_verdict=gpt,
            consensus=consensus,
            debate_summary_th=debate,
            recommendation=recommendation,
        )

    def _build_debate_summary(
        self, gemini: GeminiVerdict, gpt: GPTVerdict, verdict: str, score: int, is_paper: bool = False
    ) -> str:
        nl = "\n"
        if verdict == "EXECUTE":
            tag = " [Paper Learning]" if is_paper and (gemini.verdict != gpt.verdict or not gemini.confidence or not gpt.confidence) else ""
            return (
                f"AI Council{tag} — EXECUTE (คะแนนรวม " + str(score) + ")" + nl
                + "Gemini (Bull): " + gemini.narrative_th + nl
                + "GPT (Bear): " + gpt.narrative_th
            )
        elif verdict == "HARD_SKIP":
            return (
                "AI Council เห็นตรงกัน — SKIP" + nl
                + "Gemini: " + gemini.narrative_th + nl
                + "GPT: " + gpt.narrative_th
            )
        else:
            trap = gpt.trap_identified or "ไม่ระบุ"
            return (
                "AI Council เถียงกัน — SKIP (รอ consensus)" + nl
                + "Gemini (" + gemini.verdict + "): " + gemini.narrative_th + nl
                + "GPT (" + gpt.verdict + "): " + gpt.narrative_th + nl
                + "กับดักที่ GPT เตือน: " + trap
            )

    def _build_recommendation(
        self, gemini: GeminiVerdict, gpt: GPTVerdict, verdict: str, paper_exploration: bool = False
    ) -> str:
        if verdict == "EXECUTE":
            if paper_exploration:
                return "เข้าไม้โหมด Paper Learning — ทดสอบสมมติฐาน SMC เพื่อสะสมบทเรียน AI"
            conf = gemini.key_confluences[0] if gemini.key_confluences else (gpt.counter_argument or "Setup คุณภาพดี")
            return "เข้าไม้ได้ — " + conf
        elif verdict == "HARD_SKIP":
            reason = gpt.bear_case[0] if gpt.bear_case else "ไม่มี Confluence"
            return "ข้ามไม้นี้ — " + reason
        else:
            trap = gpt.trap_identified or "Risk สูงเกินไป"
            return "รอ Setup ใหม่ — GPT เตือน: " + trap

    def _skip_decision(self, reason: str, rule_score: int) -> CouncilDecision:
        return CouncilDecision(
            final_verdict="HARD_SKIP",
            combined_score=rule_score,
            gemini_verdict=GeminiVerdict(
                verdict="REJECT", confidence=0,
                narrative_th="ไม่ได้รับการประเมิน (Rule score ต่ำ)",
                key_confluences=[], key_risks=[], trap_warning="", raw_response="",
            ),
            gpt_verdict=GPTVerdict(
                verdict="REJECT", confidence=0,
                narrative_th="ไม่ได้รับการประเมิน (Rule score ต่ำ)",
                bear_case=[], trap_identified="", counter_argument="", raw_response="",
            ),
            consensus=True,
            debate_summary_th="Skip: " + reason,
            recommendation=reason,
        )
