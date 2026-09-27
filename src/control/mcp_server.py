"""Local MCP control server for safe runtime inspection and tuning.

The server uses stdio by default, so it is intended to be registered with a
local MCP client. It can change persisted runtime controls, but it cannot
place orders, edit credentials, or change Risk Engine limits.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.ai.candidate_triage import CandidateTriage
from src.core.runtime_control import (
    arm_live_trading,
    get_candidate_policy,
    normalize_trading_mode,
    read_runtime_control,
    set_candidate_policy,
    set_runtime_trading_mode,
)
from src.core.runtime_status import read_runtime_status as _read_runtime_status

mcp = FastMCP(
    "freebuff-runtime-control",
    instructions=(
        "Inspect and tune Freebuff runtime research controls. "
        "Never place orders or bypass the Risk Engine."
    ),
)


@mcp.tool()
def read_runtime_settings() -> dict[str, Any]:
    """Read current trading mode and candidate triage policy without secrets."""
    return read_runtime_control()


@mcp.tool()
def read_runtime_status() -> dict[str, Any]:
    """Read the worker heartbeat and latest pipeline decision."""
    return _read_runtime_status()


@mcp.tool()
def read_candidate_summary() -> dict[str, Any]:
    """Read the low-cost candidate observation summary."""
    return CandidateTriage().summary()


@mcp.tool()
def update_candidate_policy(
    observe_min_score: int | None = None,
    batch_min_score: int | None = None,
    immediate_min_score: int | None = None,
    max_immediate_per_bar: int | None = None,
    summary_window: int | None = None,
) -> dict[str, Any]:
    """Update candidate triage thresholds while the worker is running.

    The thresholds must satisfy observe <= batch <= immediate. This changes
    AI review priority only; it never changes Risk Engine limits.
    """
    changes = {
        key: value
        for key, value in {
            "observe_min_score": observe_min_score,
            "batch_min_score": batch_min_score,
            "immediate_min_score": immediate_min_score,
            "max_immediate_per_bar": max_immediate_per_bar,
            "summary_window": summary_window,
        }.items()
        if value is not None
    }
    policy = set_candidate_policy(**changes) if changes else get_candidate_policy()
    return {"candidate_policy": policy, "runtime": read_runtime_control()}


@mcp.tool()
def set_trading_mode(mode: str, confirmation: str = "") -> dict[str, Any]:
    """Set PAPER/DEMO, or explicitly arm LIVE with a confirmation phrase.

    LIVE requires the exact phrase ``ENABLE LIVE TRADING``. This tool does not
    change broker credentials or account/server selection.
    """
    normalized = normalize_trading_mode(mode, default="")
    if normalized not in {"paper", "demo", "live"}:
        raise ValueError("mode must be PAPER, DEMO, or LIVE")
    if normalized == "live":
        if confirmation != "ENABLE LIVE TRADING":
            raise ValueError("LIVE requires confirmation='ENABLE LIVE TRADING'")
        arm_live_trading()
    else:
        set_runtime_trading_mode(normalized)
    return read_runtime_control()


def main() -> None:
    """Run the local stdio MCP server."""
    transport = os.getenv("FREEBUFF_MCP_TRANSPORT", "stdio").lower()
    if transport != "stdio":
        raise RuntimeError("Freebuff MCP control is intentionally local stdio-only")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
