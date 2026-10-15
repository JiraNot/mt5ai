"""Unit tests for Dashboard Homework & Readiness tab integration."""

import ast
from pathlib import Path
import pytest


DASHBOARD_APP = Path(__file__).parents[2] / "src/dashboard/app.py"


def test_dashboard_declares_homework_and_readiness_tab():
    source = DASHBOARD_APP.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 1. Verify tab declaration
    assert "📋 Agent Homework & Readiness" in source

    # 2. Verify function definition exists
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "render_homework_and_readiness_tab" in functions

    # 3. Verify key components wired into the function
    func_source = ast.get_source_segment(source, functions["render_homework_and_readiness_tab"])
    assert func_source is not None
    assert "PromotionGate" in func_source
    assert "evaluate_trades" in func_source
    assert "readiness_pct" in func_source
    assert "CryptoScreener" in func_source
    assert "run_homework" in func_source
    assert "crypto_watchlist.json" in func_source
    assert "st.progress" in func_source
    assert "Sample Size" in func_source


def test_promotion_gate_evaluates_readiness_gauge():
    from src.risk.promotion_gate import PromotionGate

    gate = PromotionGate()
    # Test with empty trades (initial state)
    empty_eval = gate.evaluate_trades([])
    assert empty_eval.is_promotable is False
    assert empty_eval.total_trades == 0
    assert len(empty_eval.gate_checks) == 6

    # Test with passing demo trades
    sample_trades = [
        {"symbol": "BTCUSDT", "net_profit": 100.0, "sl": 64000.0, "status": "CLOSED"}
        for _ in range(30)
    ]
    pass_eval = gate.evaluate_trades(sample_trades)
    assert pass_eval.is_promotable is True
    assert pass_eval.total_trades == 30
    assert pass_eval.win_rate_pct == 100.0
    passed_count = sum(1 for g in pass_eval.gate_checks if g.passed)
    assert passed_count == 6


def test_dashboard_declares_live_market_chart():
    source = DASHBOARD_APP.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 1. Verify tab declaration
    assert "📊 Live Chart" in source

    # 2. Verify functions exist
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "fetch_binance_klines" in functions
    assert "plot_candlestick_chart" in functions
    assert "render_tradingview_widget" in functions
    assert "render_market_chart_section" in functions

    # 3. Verify TradingView integration features
    tv_source = ast.get_source_segment(source, functions["render_tradingview_widget"])
    assert tv_source is not None
    assert "TradingView.widget" in tv_source
    assert "BINANCE:" in tv_source

