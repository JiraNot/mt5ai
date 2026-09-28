"""Regression coverage for the dashboard's non-disruptive live refresh."""

from __future__ import annotations

import ast
from pathlib import Path


DASHBOARD_APP = Path(__file__).parents[2] / "src/dashboard/app.py"


def test_live_status_uses_isolated_fragments_not_full_app_autorefresh():
    source = DASHBOARD_APP.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "st_autorefresh" not in source
    assert "streamlit_autorefresh" not in source

    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in ("render_live_sidebar", "render_live_dashboard_header"):
        decorators = functions[name].decorator_list
        assert any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "st"
            and decorator.func.attr == "fragment"
            and any(keyword.arg == "run_every" for keyword in decorator.keywords)
            for decorator in decorators
        )


def test_dashboard_declares_streamlit_fragment_support():
    pyproject = (Path(__file__).parents[2] / "pyproject.toml").read_text(encoding="utf-8")

    assert '"streamlit>=1.37"' in pyproject
    assert "streamlit-autorefresh" not in pyproject
