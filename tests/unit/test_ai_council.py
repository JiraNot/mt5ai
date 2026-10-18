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


def test_unavailable_provider_does_not_block_strong_available_analyst() -> None:
    council = AICouncil(
        require_consensus=False,
        min_single_approval_confidence=75,
        min_single_provider_rule_score=80,
    )

    unavailable_gemini = _gemini("REJECT", 0)
    available_gpt = _gpt("APPROVE", 85)
    decision = council._make_decision(unavailable_gemini, available_gpt, 85)

    assert decision.final_verdict == "EXECUTE"


def test_real_rejection_still_blocks_single_provider_fallback() -> None:
    council = AICouncil(
        require_consensus=False,
        min_single_approval_confidence=75,
        min_single_provider_rule_score=80,
    )

    rejected_gemini = _gemini("REJECT", 0)
    rejected_gemini.raw_response = '{"verdict":"REJECT"}'
    available_gpt = _gpt("APPROVE", 95)
    decision = council._make_decision(rejected_gemini, available_gpt, 95)

    assert decision.final_verdict == "SKIP"


def test_dynamic_weight_normalization_when_gemini_unavailable() -> None:
    council = AICouncil(require_consensus=False)
    unavailable_gemini = _gemini("REJECT", 0)
    available_gpt = _gpt("APPROVE", 80)
    # Rule score = 80, GPT = 80 -> Normalized: 80 * 0.45 + 80 * 0.55 = 80
    decision = council._make_decision(unavailable_gemini, available_gpt, 80)
    assert decision.combined_score == 80
    assert decision.final_verdict == "EXECUTE"


def test_paper_learning_exploration_mode() -> None:
    council = AICouncil(require_consensus=False, min_combined_score=70)
    # Gemini APPROVE 65, GPT REJECT 50 -> Combined: 75 * 0.4 + 65 * 0.35 + 50 * 0.25 = 30 + 22.75 + 12.5 = 65
    # In live mode (is_paper=False), this would SKIP due to low confidence disagreement
    live_decision = council._make_decision(
        _gemini("APPROVE", 65), _gpt("REJECT", 50), rule_score=75, is_paper=False
    )
    assert live_decision.final_verdict == "SKIP"

    # In paper mode (is_paper=True), exploration is enabled for AI to learn
    paper_decision = council._make_decision(
        _gemini("APPROVE", 65), _gpt("REJECT", 50), rule_score=75, is_paper=True
    )
    assert paper_decision.final_verdict == "EXECUTE"
    assert "Paper Learning" in paper_decision.recommendation


def test_paper_exploration_both_providers_unavailable() -> None:
    council = AICouncil(require_consensus=False)
    unavail_gemini = _gemini("REJECT", 0)
    unavail_gpt = _gpt("REJECT", 0)

    # In paper mode, a solid rule-based setup executes so user can test and TradeLearner learns
    paper_decision = council._make_decision(unavail_gemini, unavail_gpt, rule_score=75, is_paper=True)
    assert paper_decision.final_verdict == "EXECUTE"
    assert paper_decision.combined_score == 75
