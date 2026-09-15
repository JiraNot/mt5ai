from src.ai.ai_council import AICouncil
from src.ai.gemini_evaluator import GeminiVerdict
from src.ai.gpt_evaluator import GPTVerdict


def _gemini(verdict: str, confidence: int) -> GeminiVerdict:
    return GeminiVerdict(
        verdict=verdict,
        confidence=confidence,
        narrative_th="gemini",
        key_confluences=[],
        key_risks=[],
        trap_warning="",
        raw_response="",
    )


def _gpt(verdict: str, confidence: int) -> GPTVerdict:
    return GPTVerdict(
        verdict=verdict,
        confidence=confidence,
        narrative_th="gpt",
        bear_case=[],
        trap_identified="",
        counter_argument="",
        raw_response="",
    )


def test_high_confidence_disagreement_can_reach_risk_engine() -> None:
    council = AICouncil(
        require_consensus=False,
        min_combined_score=70,
        min_single_approval_confidence=75,
    )

    decision = council._make_decision(_gemini("APPROVE", 95), _gpt("REJECT", 55), 90)

    assert decision.final_verdict == "EXECUTE"
    assert decision.consensus is False


def test_consensus_mode_still_skips_disagreement() -> None:
    council = AICouncil(require_consensus=True, min_combined_score=70)

    decision = council._make_decision(_gemini("APPROVE", 100), _gpt("REJECT", 0), 100)

    assert decision.final_verdict == "SKIP"
    assert decision.should_execute is False


def test_low_confidence_disagreement_is_rejected() -> None:
    council = AICouncil(
        require_consensus=False,
        min_combined_score=70,
        min_single_approval_confidence=75,
    )

    decision = council._make_decision(_gemini("APPROVE", 74), _gpt("REJECT", 70), 100)

    assert decision.final_verdict == "SKIP"
