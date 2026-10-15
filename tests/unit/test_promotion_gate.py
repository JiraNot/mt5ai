"""Unit tests for PromotionGate."""

import pytest

from src.risk.promotion_gate import GateCheck, PromotionCriteria, PromotionEvaluation, PromotionGate


def test_promotion_gate_empty():
    gate = PromotionGate(PromotionCriteria(min_trades=30))
    eval_res = gate.evaluate_trades([])
    assert eval_res.is_promotable is False
    assert eval_res.current_stage == "PAPER"
    assert eval_res.total_trades == 0
    assert any(g.name == "Sample Size" and not g.passed for g in eval_res.gate_checks)


def test_promotion_gate_insufficient_sample():
    gate = PromotionGate(PromotionCriteria(min_trades=30, min_profit_factor=1.5))
    # 10 winning trades, but only 10 trades total (target is 30)
    mock_trades = [
        {"net_profit": 50.0, "sl": 60000.0, "status": "CLOSED"} for _ in range(10)
    ]
    eval_res = gate.evaluate_trades(mock_trades)
    assert eval_res.is_promotable is False
    assert eval_res.current_stage == "DEMO"
    assert eval_res.total_trades == 10
    sample_check = next(g for g in eval_res.gate_checks if g.name == "Sample Size")
    assert sample_check.passed is False


def test_promotion_gate_failing_profit_factor():
    gate = PromotionGate(PromotionCriteria(min_trades=20, min_profit_factor=1.5))
    # 20 trades: 10 wins of $10, 10 losses of $10 -> PF = 1.0 < 1.5
    mock_trades = []
    for i in range(20):
        profit = 10.0 if i % 2 == 0 else -10.0
        mock_trades.append({"net_profit": profit, "sl": 60000.0, "status": "CLOSED"})

    eval_res = gate.evaluate_trades(mock_trades)
    assert eval_res.is_promotable is False
    pf_check = next(g for g in eval_res.gate_checks if g.name == "Profit Factor")
    assert pf_check.passed is False


def test_promotion_gate_missing_stop_loss():
    gate = PromotionGate(PromotionCriteria(min_trades=10, min_sl_compliance_pct=100.0))
    mock_trades = [
        {"net_profit": 50.0, "sl": 60000.0, "status": "CLOSED"} for _ in range(9)
    ]
    # 1 trade without SL
    mock_trades.append({"net_profit": 50.0, "sl": 0.0, "status": "CLOSED"})

    eval_res = gate.evaluate_trades(mock_trades)
    assert eval_res.is_promotable is False
    sl_check = next(g for g in eval_res.gate_checks if g.name == "Server SL Compliance")
    assert sl_check.passed is False
    assert eval_res.sl_compliance_pct == 90.0


def test_promotion_gate_success_ready_for_live():
    gate = PromotionGate(
        PromotionCriteria(
            min_trades=30,
            min_profit_factor=1.5,
            min_win_rate_pct=40.0,
            max_drawdown_pct=5.0,
            min_sl_compliance_pct=100.0,
        )
    )
    # 20 wins of $100 = $2000, 10 losses of $50 = $500 -> PF = 4.0, WR = 66.7%
    mock_trades = [{"net_profit": 100.0, "sl": 60000.0, "status": "CLOSED"} for _ in range(20)]
    mock_trades += [{"net_profit": -50.0, "sl": 60000.0, "status": "CLOSED"} for _ in range(10)]

    eval_res = gate.evaluate_trades(mock_trades)
    assert eval_res.is_promotable is True
    assert eval_res.current_stage == "READY_FOR_LIVE"
    assert eval_res.total_trades == 30
    assert eval_res.profit_factor == 4.0
    assert eval_res.win_rate_pct == pytest.approx(66.7, abs=0.1)
    assert all(g.passed for g in eval_res.gate_checks)
    summary_text = eval_res.summary()
    assert "READY FOR LIVE TRADING" in summary_text
