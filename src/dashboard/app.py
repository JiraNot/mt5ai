"""Freebuff Trading Dashboard — Interactive Streamlit App.

Usage:
    streamlit run src/dashboard/app.py
    streamlit run src/dashboard/app.py -- --db sqlite+aiosqlite:///freebuff.db
"""

from __future__ import annotations
import os

import argparse
import json
import sys
import time
import shutil
import urllib.request
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.storage.models import (
    AccountSnapshot,
    Base,
    DailyRisk,
    SetupLog,
    Trade,
    ensure_database_parent,
)
from src.core.config import settings
from src.ai.candidate_triage import CandidateTriage
from src.core.runtime_status import read_runtime_status
from src.core.runtime_control import (
    arm_live_trading,
    get_candidate_policy,
    get_runtime_trading_mode,
    is_live_armed,
    set_candidate_policy,
    set_runtime_trading_mode,
)
from src.ai.openrouter_model_catalog import (
    fetch_models,
    get_selected_model,
    group_models,
    save_selected_model,
)

# ─── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Freebuff Trading Dashboard",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .stMetric {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px;
    }
    .stMetric label {
        color: #94a3b8 !important;
        font-size: 13px !important;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .stMetric [data-testid="stMetricValue"] {
        font-size: 28px !important;
        font-weight: 700;
    }
    .positive { color: #22c55e !important; }
    .negative { color: #ef4444 !important; }
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
    }
</style>
""", unsafe_allow_html=True)


# ─── Database Connection ──────────────────────────────────────────────────────

@st.cache_resource
def get_engine(db_url: str | None = None):
    """Create synchronous SQLite engine for Streamlit."""
    if not db_url:
        db_url = os.getenv("DATABASE_URL_SYNC", "sqlite:////app/data/freebuff.db")
    ensure_database_parent(db_url)
    engine = create_engine(db_url, echo=False)
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as conn:
            existing_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(setup_log)")).fetchall()]
            new_cols = {
                "gemini_verdict": "VARCHAR(10)",
                "gemini_score": "INTEGER",
                "gemini_narrative": "TEXT",
                "gpt_verdict": "VARCHAR(10)",
                "gpt_score": "INTEGER",
                "gpt_narrative": "TEXT",
                "debate_summary": "TEXT",
                "eql_summary": "TEXT",
            }
            for col_name, col_type in new_cols.items():
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE setup_log ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    except Exception:
                        pass
    except Exception:
        pass
    return engine


def load_trades(engine) -> pd.DataFrame:
    """Load all trades into DataFrame safely."""
    try:
        query = text("""
            SELECT
                t.id, t.symbol, t.direction, t.volume,
                t.entry_price, t.sl, t.tp1, t.tp2,
                t.exit_price, t.exit_time, t.open_time,
                t.profit, t.commission, t.net_profit,
                t.outcome_r, t.outcome_pips, t.status,
                t.comment as strategy_id
            FROM trades t
            ORDER BY t.open_time DESC
        """)
        return pd.read_sql(query, engine)
    except Exception:
        return pd.DataFrame(columns=[
            "id", "symbol", "direction", "volume", "entry_price", "sl", "tp1", "tp2",
            "exit_price", "exit_time", "open_time", "profit", "commission", "net_profit",
            "outcome_r", "outcome_pips", "status", "strategy_id"
        ])


def load_setups(engine) -> pd.DataFrame:
    """Load all setup logs into DataFrame safely."""
    try:
        query = text("""
            SELECT
                s.id, s.symbol, s.timeframe, s.strategy_id,
                s.direction, s.rule_score, s.ai_score, s.combined_score,
                s.decision, s.entry_price, s.stop_loss,
                s.take_profit_1, s.rr_ratio,
                s.confluences, s.risk_flags, s.rejection_reason,
                s.outcome_r, s.outcome_pips, s.created_at,
                s.gemini_verdict, s.gemini_score, s.gemini_narrative,
                s.gpt_verdict, s.gpt_score, s.gpt_narrative,
                s.debate_summary, s.eql_summary
            FROM setup_log s
            ORDER BY s.created_at DESC
        """)
        return pd.read_sql(query, engine)
    except Exception:
        return pd.DataFrame(columns=[
            "id", "symbol", "timeframe", "strategy_id", "direction", "rule_score",
            "ai_score", "combined_score", "decision", "entry_price", "stop_loss",
            "take_profit_1", "rr_ratio", "confluences", "risk_flags",
            "rejection_reason", "outcome_r", "outcome_pips", "created_at",
            "gemini_verdict", "gemini_score", "gemini_narrative",
            "gpt_verdict", "gpt_score", "gpt_narrative",
            "debate_summary", "eql_summary"
        ])


def load_equity_curve(engine) -> pd.DataFrame:
    """Load account snapshots for equity curve safely."""
    try:
        query = text("""
            SELECT ts, equity, balance
            FROM account_snapshots
            ORDER BY ts
        """)
        return pd.read_sql(query, engine)
    except Exception:
        return pd.DataFrame(columns=["ts", "equity", "balance"])



def load_memories(engine) -> pd.DataFrame:
    """Load trade memories / continuous learning lessons safely."""
    try:
        query = text("""
            SELECT
                id, ticket, symbol, strategy_id, direction,
                outcome, profit, pips, rr_achieved, root_cause,
                lesson_learned_th, rule_recommendation, created_at
            FROM trade_memories
            ORDER BY created_at DESC
        """)
        return pd.read_sql(query, engine)
    except Exception:
        return pd.DataFrame(columns=[
            "id", "ticket", "symbol", "strategy_id", "direction",
            "outcome", "profit", "pips", "rr_achieved", "root_cause",
            "lesson_learned_th", "rule_recommendation", "created_at"
        ])


def load_daily_risk(engine) -> pd.DataFrame:
    """Load daily risk data safely."""
    try:
        query = text("""
            SELECT
                trade_date, total_pnl, total_trades,
                winning_trades, losing_trades, circuit_breaker
            FROM daily_risk
            ORDER BY trade_date
        """)
        return pd.read_sql(query, engine)
    except Exception:
        return pd.DataFrame(columns=[
            "trade_date", "total_pnl", "total_trades",
            "winning_trades", "losing_trades", "circuit_breaker"
        ])


@st.cache_data(ttl=300, show_spinner=False)
def load_openrouter_models(base_url: str, api_key_configured: bool):
    """Load the live OpenRouter model catalog for the sidebar selector."""
    if not api_key_configured:
        return []
    try:
        return fetch_models(
            base_url=base_url,
            api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            timeout=10,
        )
    except Exception:
        return []


def render_openrouter_model_selector(container=None) -> str:
    """Render and persist the OpenRouter model choice without exposing secrets."""
    container = container or st.sidebar
    current_model = get_selected_model()
    api_key_configured = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    models = load_openrouter_models(base_url, api_key_configured)
    groups = group_models(models, current_model)

    container.markdown("### 🧠 OpenRouter Model")
    if not api_key_configured:
        container.info("ใส่ OPENROUTER_API_KEY เพื่อโหลดรายการโมเดล")
        return current_model
    if not models:
        container.warning("โหลดรายการโมเดล OpenRouter ไม่สำเร็จ — ใช้โมเดลปัจจุบันต่อไป")
        container.caption(f"Current: `{current_model}`")
        return current_model

    category_labels = {
        "current": "ปัจจุบัน",
        "free": "ฟรี",
        "paid": "เสียเงิน",
    }
    available_categories = [key for key in ("current", "free", "paid") if groups[key]]
    category = container.radio(
        "ประเภทโมเดล",
        available_categories,
        format_func=lambda key: category_labels[key],
        horizontal=True,
        key="openrouter_model_category",
    )
    choices = groups[category]
    labels = {
        model.model_id: f"{model.name} · {model.price_label}"
        for model in choices
    }
    selected = container.selectbox(
        "เลือกโมเดล",
        [model.model_id for model in choices],
        format_func=lambda model_id: labels[model_id],
        index=0,
        key=f"openrouter_model_choice_{category}",
    )
    if selected != current_model:
        try:
            save_selected_model(selected)
            container.success(f"บันทึกโมเดลแล้ว: `{selected}`")
        except (OSError, ValueError) as exc:
            container.error(f"บันทึกโมเดลไม่สำเร็จ: {exc}")
    else:
        container.caption(f"กำลังใช้: `{current_model}`")
    container.caption("การเลือกมีผลกับ Bull Analyst ในการประเมินรอบถัดไป")
    return selected


# ─── Metrics Calculation ──────────────────────────────────────────────────────

def calculate_metrics(trades_df: pd.DataFrame) -> dict:
    """Calculate key trading metrics."""
    if trades_df.empty:
        return {
            "total": 0, "winners": 0, "losers": 0,
            "win_rate": 0, "total_pnl": 0, "avg_win": 0,
            "avg_loss": 0, "profit_factor": 0, "expectancy": 0,
            "max_drawdown": 0, "avg_r": 0, "best_trade": 0,
            "worst_trade": 0, "avg_rr": 0,
        }

    total = len(trades_df)
    winners = len(trades_df[trades_df["net_profit"] > 0])
    losers = len(trades_df[trades_df["net_profit"] <= 0])
    win_rate = (winners / total * 100) if total > 0 else 0

    total_pnl = trades_df["net_profit"].sum()
    avg_win = trades_df[trades_df["net_profit"] > 0]["net_profit"].mean() if winners > 0 else 0
    avg_loss = abs(trades_df[trades_df["net_profit"] <= 0]["net_profit"].mean()) if losers > 0 else 0

    total_wins = trades_df[trades_df["net_profit"] > 0]["net_profit"].sum() if winners > 0 else 0
    total_losses = abs(trades_df[trades_df["net_profit"] <= 0]["net_profit"].sum()) if losers > 0 else 0
    profit_factor = (total_wins / total_losses) if total_losses > 0 else 0

    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)

    # Max drawdown from equity curve
    if not trades_df.empty:
        equity = 10000 + trades_df["net_profit"].cumsum()
        peak = equity.cummax()
        drawdown = (peak - equity) / peak * 100
        max_drawdown = drawdown.max()
    else:
        max_drawdown = 0

    avg_r = trades_df["outcome_r"].mean() if "outcome_r" in trades_df.columns else 0
    best_trade = trades_df["net_profit"].max()
    worst_trade = trades_df["net_profit"].min()
    avg_rr = trades_df["outcome_r"].mean()

    return {
        "total": total,
        "winners": winners,
        "losers": losers,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "max_drawdown": round(max_drawdown, 1),
        "avg_r": round(avg_r, 2),
        "best_trade": round(best_trade, 2),
        "worst_trade": round(worst_trade, 2),
        "avg_rr": round(avg_rr, 2),
    }


# ─── Chart Functions ──────────────────────────────────────────────────────────

def plot_equity_curve(equity_df: pd.DataFrame) -> go.Figure:
    """Plot interactive equity curve."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=equity_df["ts"],
        y=equity_df["equity"],
        mode="lines",
        name="Equity",
        line=dict(color="#3b82f6", width=2),
        fill="tozeroy",
        fillcolor="rgba(59, 130, 246, 0.1)",
    ))

    # Add balance line if different
    if "balance" in equity_df.columns:
        fig.add_trace(go.Scatter(
            x=equity_df["ts"],
            y=equity_df["balance"],
            mode="lines",
            name="Balance",
            line=dict(color="#8b5cf6", width=1, dash="dot"),
            visible="legendonly",
        ))

    fig.update_layout(
        title="📈 Equity Curve",
        xaxis_title="Date",
        yaxis_title="Equity ($)",
        template="plotly_dark",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        yaxis=dict(tickformat="$,.0f"),
        hovermode="x unified",
    )
    return fig


def plot_strategy_performance(trades_df: pd.DataFrame) -> go.Figure:
    """Plot strategy comparison chart."""
    if trades_df.empty:
        return go.Figure()

    strat_stats = trades_df.groupby("strategy_id").agg(
        total=("id", "count"),
        wins=("net_profit", lambda x: (x > 0).sum()),
        total_pnl=("net_profit", "sum"),
        avg_r=("outcome_r", "mean"),
    ).reset_index()

    strat_stats["win_rate"] = (strat_stats["wins"] / strat_stats["total"] * 100).round(1)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Win Rate %",
        x=strat_stats["strategy_id"],
        y=strat_stats["win_rate"],
        marker_color="#22c55e",
        text=strat_stats["win_rate"].apply(lambda x: f"{x}%"),
        textposition="outside",
    ))

    fig.update_layout(
        title="🎯 Strategy Win Rate Comparison",
        yaxis_title="Win Rate (%)",
        template="plotly_dark",
        height=350,
        margin=dict(l=0, r=0, t=40, b=0),
        yaxis=dict(range=[0, 100]),
    )
    return fig


def plot_strategy_pnl(trades_df: pd.DataFrame) -> go.Figure:
    """Plot strategy P&L comparison."""
    if trades_df.empty:
        return go.Figure()

    strat_pnl = trades_df.groupby("strategy_id")["net_profit"].sum().reset_index()
    strat_pnl = strat_pnl.sort_values("net_profit", ascending=True)

    colors = ["#22c55e" if x >= 0 else "#ef4444" for x in strat_pnl["net_profit"]]

    fig = go.Figure(go.Bar(
        x=strat_pnl["net_profit"],
        y=strat_pnl["strategy_id"],
        orientation="h",
        marker_color=colors,
        text=strat_pnl["net_profit"].apply(lambda x: f"${x:,.2f}"),
        textposition="outside",
    ))

    fig.update_layout(
        title="💰 Strategy P&L",
        xaxis_title="P&L ($)",
        template="plotly_dark",
        height=350,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


def plot_monthly_pnl(trades_df: pd.DataFrame) -> go.Figure:
    """Plot monthly P&L bar chart."""
    if trades_df.empty:
        return go.Figure()

    trades_df = trades_df.copy()
    trades_df["month"] = pd.to_datetime(trades_df["open_time"]).dt.to_period("M").astype(str)
    monthly = trades_df.groupby("month")["net_profit"].sum().reset_index()

    colors = ["#22c55e" if x >= 0 else "#ef4444" for x in monthly["net_profit"]]

    fig = go.Figure(go.Bar(
        x=monthly["month"],
        y=monthly["net_profit"],
        marker_color=colors,
        text=monthly["net_profit"].apply(lambda x: f"${x:,.0f}"),
        textposition="outside",
    ))

    fig.update_layout(
        title="📊 Monthly P&L",
        xaxis_title="Month",
        yaxis_title="P&L ($)",
        template="plotly_dark",
        height=350,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


def plot_session_heatmap(trades_df: pd.DataFrame) -> go.Figure:
    """Plot session performance heatmap."""
    if trades_df.empty:
        return go.Figure()

    trades_df = trades_df.copy()
    trades_df["hour"] = pd.to_datetime(trades_df["open_time"]).dt.hour
    trades_df["day"] = pd.to_datetime(trades_df["open_time"]).dt.day_name()

    # Create pivot table
    pivot = trades_df.pivot_table(
        values="net_profit",
        index="day",
        columns="hour",
        aggfunc="sum",
        fill_value=0,
    )

    # Reorder days
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    pivot = pivot.reindex([d for d in day_order if d in pivot.index])

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[f"{h:02d}:00" for h in pivot.columns],
        y=pivot.index,
        colorscale="RdYlGn",
        text=pivot.values.round(0),
        texttemplate="$%{text}",
        textfont={"size": 10},
    ))

    fig.update_layout(
        title="🕐 Session Performance Heatmap",
        xaxis_title="Hour (UTC)",
        yaxis_title="Day",
        template="plotly_dark",
        height=300,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


def plot_setup_analysis(setups_df: pd.DataFrame) -> go.Figure:
    """Plot setup decision breakdown."""
    if setups_df.empty:
        return go.Figure()

    decision_counts = setups_df["decision"].value_counts()

    colors = {"TRADED": "#22c55e", "SKIPPED": "#f59e0b", "REJECTED": "#ef4444"}

    fig = go.Figure(go.Pie(
        labels=decision_counts.index,
        values=decision_counts.values,
        hole=0.4,
        marker=dict(colors=[colors.get(d, "#3b82f6") for d in decision_counts.index]),
        textinfo="label+percent",
        textfont_size=14,
    ))

    fig.update_layout(
        title="🔍 Setup Analysis",
        template="plotly_dark",
        height=350,
        margin=dict(l=0, r=0, t=40, b=0),
        showlegend=False,
    )
    return fig


def plot_drawdown(trades_df: pd.DataFrame) -> go.Figure:
    """Plot drawdown chart."""
    if trades_df.empty:
        return go.Figure()

    equity = 10000 + trades_df["net_profit"].cumsum()
    peak = equity.cummax()
    drawdown = (peak - equity) / peak * 100

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=trades_df["open_time"],
        y=-drawdown,
        fill="tozeroy",
        fillcolor="rgba(239, 68, 68, 0.3)",
        line=dict(color="#ef4444", width=1),
        name="Drawdown",
    ))

    fig.update_layout(
        title="📉 Drawdown",
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        template="plotly_dark",
        height=250,
        margin=dict(l=0, r=0, t=40, b=0),
        yaxis=dict(ticksuffix="%"),
    )
    return fig


def plot_r_distribution(trades_df: pd.DataFrame) -> go.Figure:
    """Plot R-multiple distribution."""
    if trades_df.empty or "outcome_r" not in trades_df.columns:
        return go.Figure()

    fig = go.Figure()

    colors = ["#22c55e" if x >= 0 else "#ef4444" for x in trades_df["outcome_r"]]

    fig.add_trace(go.Histogram(
        x=trades_df["outcome_r"],
        nbinsx=30,
        marker_color="#3b82f6",
        opacity=0.7,
    ))

    fig.add_vline(x=0, line_dash="dash", line_color="#ef4444", line_width=2)

    fig.update_layout(
        title="🎲 R-Multiple Distribution",
        xaxis_title="R-Multiple",
        yaxis_title="Count",
        template="plotly_dark",
        height=300,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


# ─── Main App ─────────────────────────────────────────────────────────────────


# ─── Live Health Checks ───────────────────────────────────────────────────────

def check_mt5_bridge_status() -> dict:
    """Check live connectivity to MT5 Bridge server and get account details."""
    bridge_url = os.getenv("BRIDGE_URL", "http://mt5-node:8900").rstrip("/")
    token = os.getenv("BRIDGE_TOKEN", "")
    headers = {"X-Bridge-Token": token} if token else {}
    
    start_time = time.time()
    try:
        req = urllib.request.Request(f"{bridge_url}/health", headers=headers)
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode())
            latency_ms = int((time.time() - start_time) * 1000)
            is_connected = bool(data.get("mt5_connected") or data.get("mt5_initialized") or data.get("account"))
            return {
                "online": True,
                "latency_ms": latency_ms,
                "mt5_connected": is_connected,
                "terminal": data.get("terminal") or "MetaTrader 5",
                "account": data.get("account"),
                "server": data.get("server"),
                "balance": data.get("balance"),
                "bridge_url": bridge_url,
            }
    except Exception as e:
        return {
            "online": False,
            "latency_ms": None,
            "mt5_connected": False,
            "error": str(e),
            "bridge_url": bridge_url,
        }


def check_binance_status() -> dict:
    """Check Binance public market-data connectivity without requiring credentials."""
    base_url = os.getenv("BINANCE_BASE_URL", "https://testnet.binancefuture.com").rstrip("/")
    start_time = time.time()
    try:
        req = urllib.request.Request(
            f"{base_url}/fapi/v1/ping",
            headers={"User-Agent": "freebuff-dashboard/0.1"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            resp.read()
            return {
                "online": True,
                "latency_ms": int((time.time() - start_time) * 1000),
                "base_url": base_url,
            }
    except Exception as e:
        return {
            "online": False,
            "latency_ms": None,
            "base_url": base_url,
            "error": str(e),
        }


def check_ai_status() -> dict:
    """Check CLI installation and Codex credential availability.

    Antigravity's account tokens are held in an OS keyring. In a container we
    report only the supported API-key deployment configuration.
    """
    codex_auth_files = [
        os.path.expanduser("~/.codex/auth.json"),
        "/root/.codex/auth.json",
        "/mnt/c/Users/Dulla/.codex/auth.json",
        r"C:\Users\Dulla\.codex\auth.json",
    ]
    codex_auth_ok = any(os.path.exists(p) for p in codex_auth_files) or bool(os.getenv("CODEX_AUTH_JSON"))
    codex_cli_ok = bool(shutil.which("codex")) or any(
        os.path.exists(p) for p in [
            "/usr/local/bin/codex",
            "/usr/bin/codex",
            os.path.expanduser("~/.local/bin/codex"),
            "/mnt/c/Users/Dulla/.codex/plugins/.plugin-appserver/codex.exe",
            r"C:\Users\Dulla\.codex\plugins\.plugin-appserver\codex.exe",
        ]
    )

    ai_cli = os.getenv("AI_CLI_BIN", "agy")
    antigravity_cli_ok = bool(shutil.which(ai_cli) or (os.path.isabs(ai_cli) and os.access(ai_cli, os.X_OK)))
    antigravity_auth_ok = bool(os.getenv("GEMINI_API_KEY"))
    openrouter_auth_ok = bool(os.getenv("OPENROUTER_API_KEY"))

    return {
        "chatgpt_auth": codex_auth_ok,
        "chatgpt_cli": codex_cli_ok,
        "gemini_auth": antigravity_cli_ok and antigravity_auth_ok,
        "deepseek_auth": openrouter_auth_ok,
        "council_ready": codex_auth_ok and codex_cli_ok and (
            (antigravity_cli_ok and antigravity_auth_ok) or openrouter_auth_ok
        ),
    }



# ─── Security & Authentication Gate ──────────────────────────────────────────

def _auth_token(password: str) -> str:
    import hashlib
    return hashlib.sha256(f"freebuff_auth:{password}".encode()).hexdigest()[:20]

def check_dashboard_auth() -> bool:
    """Password protection gate with session persistence across page refreshes."""
    st.markdown('<meta name="robots" content="noindex, nofollow">', unsafe_allow_html=True)

    expected_password = os.getenv("DASHBOARD_PASSWORD", "freebuff2026").strip()
    if not expected_password:
        return True  # If empty, no password required

    expected_token = _auth_token(expected_password)

    # 1. Check if token already in URL query parameters (survives refresh!)
    current_token = st.query_params.get("auth")
    if current_token == expected_token:
        st.session_state["authenticated"] = True
        return True

    # 2. Check in-memory session
    if st.session_state.get("authenticated", False):
        st.query_params["auth"] = expected_token
        return True

    # Render clean, premium dark login card
    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style="background-color: #1e293b; padding: 2.5rem; border-radius: 12px; border: 1px solid #334155; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                <h2 style="color: #f8fafc; margin-bottom: 0.5rem;">🔒 Freebuff Trading Portal</h2>
                <p style="color: #94a3b8; font-size: 0.95rem; margin-bottom: 1.5rem;">Private Algorithmic Execution System · Authorized Only</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("login_form", clear_on_submit=False):
            input_pass = st.text_input("Enter Access Password", type="password", placeholder="••••••••••••")
            submit = st.form_submit_button("🔓 Access System", use_container_width=True)
            if submit:
                if input_pass == expected_password:
                    st.session_state["authenticated"] = True
                    st.query_params["auth"] = expected_token
                    st.rerun()
                else:
                    st.error("❌ Access Denied: Invalid Password")
        st.caption("🔒 Protected with persistent auth token & robots no-index policy.")
    return False


def _render_status_chip(label: str, value: str, tone: str = "neutral") -> None:
    colors = {
        "good": ("#22c55e", "rgba(34,197,94,.12)"),
        "warn": ("#f59e0b", "rgba(245,158,11,.12)"),
        "bad": ("#ef4444", "rgba(239,68,68,.12)"),
        "neutral": ("#94a3b8", "rgba(148,163,184,.10)"),
    }
    foreground, background = colors.get(tone, colors["neutral"])
    st.markdown(
        f"<div style='background:{background};border:1px solid {foreground}55;"
        f"border-radius:10px;padding:10px 12px;margin-bottom:8px'>"
        f"<div style='font-size:.72rem;color:#94a3b8;text-transform:uppercase;"
        f"letter-spacing:.08em'>{label}</div>"
        f"<div style='font-size:1.05rem;font-weight:700;color:{foreground}'>{value}</div></div>",
        unsafe_allow_html=True,
    )


def render_redesigned_dashboard(
    *,
    mt5_status: dict,
    binance_status: dict | None,
    ai_status: dict,
    runtime_status: dict,
    trading_mode: str,
    live_armed: bool,
    configured_venues: list[str],
    candidate_policy: dict[str, int],
    candidate_summary: dict,
    trades_df: pd.DataFrame,
    setups_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    filtered_trades: pd.DataFrame,
    filtered_metrics: dict,
) -> None:
    """Render the task-oriented control center.

    The previous dashboard exposed every chart at the same level. This layout
    puts the current decision and required action first, then keeps research
    detail one click deeper.
    """
    engine_state = str(runtime_status.get("state", "unknown")).lower()
    engine_tone = "good" if engine_state == "running" else "warn" if engine_state in {"starting", "degraded"} else "bad"
    engine_label = {
        "running": "Running",
        "starting": "Starting",
        "error": "Error",
        "stopped": "Stopped",
    }.get(engine_state, engine_state.title())
    observed = int(candidate_summary.get("total", 0) or 0)
    priorities = candidate_summary.get("by_priority", {}) or {}
    immediate = int(priorities.get("immediate", 0) or 0)
    batch = int(priorities.get("batch", 0) or 0)
    observe = int(priorities.get("observe", 0) or 0)

    st.markdown("# Freebuff Control Center")
    st.caption("ดูสิ่งที่ระบบกำลังทำอยู่ก่อน แล้วค่อยลงลึกถึง Candidate, AI, Learning และ Risk")

    head = st.columns([1.3, 1.1, 1.1, 1.1, 1.5])
    with head[0]:
        _render_status_chip("Engine", engine_label, engine_tone)
    with head[1]:
        _render_status_chip("Mode", trading_mode, "bad" if trading_mode == "LIVE" and live_armed else "good" if trading_mode == "DEMO" else "neutral")
    with head[2]:
        _render_status_chip("Candidates", str(observed), "good" if observed else "warn")
    with head[3]:
        _render_status_chip("AI review now", str(immediate), "good" if immediate else "neutral")
    with head[4]:
        last_decision = runtime_status.get("last_decision", "Waiting")
        raw_reason = runtime_status.get("last_reason") or runtime_status.get("last_error")
        last_reason = raw_reason if raw_reason not in {None, "", "unknown", "None"} else "รอผลการประเมินรอบถัดไป"
        st.info(f"**Latest:** `{last_decision}`\n\n{last_reason}")

    if engine_state != "running":
        st.warning(f"Worker state is `{engine_label}`. ตรวจสอบ health และ logs ก่อนประเมินว่าไม่มี setup")

    tabs = st.tabs([
        "🎛️ Command Center",
        "🔎 Candidates & AI",
        "🧠 Learning",
        "📈 Performance",
        "⚙️ Controls & Safety",
    ])

    with tabs[0]:
        st.markdown("## ตอนนี้ระบบกำลังทำอะไร")
        status_cols = st.columns(3)
        with status_cols[0]:
            if mt5_status["online"] and mt5_status["mt5_connected"]:
                st.success(f"**MT5 connected** · {mt5_status.get('server', 'server unknown')}\n\nAccount `{mt5_status.get('account', 'N/A')}`")
            elif mt5_status["online"]:
                st.warning("**MT5 bridge online**\n\nกำลังรอ terminal/account")
            else:
                st.error("**MT5 disconnected**\n\nตรวจสอบ bridge และ MT5 credentials")
        with status_cols[1]:
            if binance_status is None:
                st.info("**Binance disabled**\n\nVenue นี้ไม่ได้อยู่ใน MARKET_DATA_VENUES")
            elif binance_status["online"]:
                st.success(f"**Binance market data online**\n\n{binance_status['latency_ms']}ms · public API")
            else:
                st.error("**Binance market data offline**\n\nตรวจสอบ endpoint/network")
        with status_cols[2]:
            if ai_status["council_ready"]:
                st.success("**AI Council ready**\n\nBull + Bear provider พร้อมใช้งาน")
            else:
                st.warning("**Rule scorer active**\n\nAI Council ยังไม่ครบ provider")

        st.markdown("## Candidate funnel")
        funnel = st.columns(4)
        funnel[0].metric("Observed", observed, "บันทึกทุก setup ที่ผ่าน observation floor")
        funnel[1].metric("Observe", observe, "เก็บไว้เรียนรู้ ไม่เรียก AI")
        funnel[2].metric("Batch", batch, "รวมเป็น digest ก่อน")
        funnel[3].metric("Immediate", immediate, "มีสิทธิ์เข้า AI Council")

        attention: list[str] = []
        if not runtime_status:
            attention.append("ยังไม่มี heartbeat จาก worker")
        if not ai_status["council_ready"]:
            attention.append("AI Council ยังไม่พร้อมครบทุก provider — ระบบยังใช้ rule scorer ได้")
        if observed == 0:
            attention.append("ยังไม่มี Candidate ที่ถูกบันทึก ให้ตรวจ market data และ strategy output")
        if attention:
            st.markdown("## สิ่งที่ควรตรวจตอนนี้")
            for item in attention:
                st.warning(item)
        else:
            st.success("ระบบมี heartbeat, data feed และ candidate triage ทำงานอยู่")

        st.markdown("## กิจกรรมล่าสุด")
        if setups_df.empty:
            st.info("ยังไม่มี setup log")
        else:
            latest = setups_df.head(12).copy()
            latest = latest[["created_at", "symbol", "strategy_id", "direction", "rule_score", "ai_score", "decision", "rejection_reason"]]
            latest.columns = ["Time", "Symbol", "Strategy", "Dir", "Rule", "AI", "Status", "Reason"]
            st.dataframe(latest, use_container_width=True, hide_index=True)

        st.markdown("## ผลการเทรด")
        metrics_cols = st.columns(4)
        metrics_cols[0].metric("Trades", filtered_metrics["total"])
        metrics_cols[1].metric("Win rate", f"{filtered_metrics['win_rate']}%")
        metrics_cols[2].metric("Net P&L", f"${filtered_metrics['total_pnl']:,.2f}")
        metrics_cols[3].metric("Max drawdown", f"{filtered_metrics['max_drawdown']}%")
        if not equity_df.empty:
            st.plotly_chart(plot_equity_curve(equity_df), use_container_width=True)

    with tabs[1]:
        st.markdown("## Candidate inbox")
        st.caption("Candidate ทุกระดับถูกเก็บไว้ แต่ AI จะถูกเรียกตาม priority เพื่อควบคุมค่าใช้จ่ายและลด noise")
        policy_cols = st.columns(5)
        policy_cols[0].metric("Observe floor", candidate_policy["observe_min_score"])
        policy_cols[1].metric("Batch from", candidate_policy["batch_min_score"])
        policy_cols[2].metric("Immediate from", candidate_policy["immediate_min_score"])
        policy_cols[3].metric("AI/bar", candidate_policy["max_immediate_per_bar"])
        policy_cols[4].metric("Digest window", candidate_policy["summary_window"])

        if setups_df.empty:
            st.info("ยังไม่มี Candidate")
        else:
            c1, c2, c3 = st.columns(3)
            strategy_options = ["All"] + sorted(setups_df["strategy_id"].dropna().astype(str).unique().tolist())
            selected_setup_strategy = c1.selectbox("Strategy", strategy_options, key="candidate_strategy_filter")
            selected_decisions = c2.multiselect(
                "Status", ["TRADED", "SKIPPED", "REJECTED"], default=["TRADED", "SKIPPED", "REJECTED"],
                key="candidate_decision_filter",
            )
            selected_direction = c3.selectbox("Direction", ["All", "BUY", "SELL"], key="candidate_direction_filter")
            candidate_df = setups_df.copy()
            if selected_setup_strategy != "All":
                candidate_df = candidate_df[candidate_df["strategy_id"] == selected_setup_strategy]
            if selected_decisions:
                candidate_df = candidate_df[candidate_df["decision"].isin(selected_decisions)]
            if selected_direction != "All":
                candidate_df = candidate_df[candidate_df["direction"] == selected_direction]
            st.dataframe(
                candidate_df[["created_at", "symbol", "strategy_id", "direction", "rule_score", "ai_score", "combined_score", "decision", "outcome_r", "rejection_reason"]].head(100),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("### AI Council feed")
            debates = candidate_df[candidate_df["gemini_verdict"].notna()].head(10)
            if debates.empty:
                st.info("ยังไม่มี AI Council debate สำหรับ Candidate ที่เลือก")
            for _, row in debates.iterrows():
                status = "✅" if row.get("decision") == "TRADED" else "⏸️"
                with st.expander(f"{status} {row.get('created_at')} · {row.get('symbol')} {row.get('direction')} · {row.get('strategy_id')}"):
                    left, right = st.columns(2)
                    with left:
                        st.markdown(f"**Bull:** `{row.get('gemini_verdict')}` · {row.get('gemini_score')}/100")
                        st.info(row.get("gemini_narrative") or "ไม่มี narrative")
                    with right:
                        st.markdown(f"**Bear:** `{row.get('gpt_verdict')}` · {row.get('gpt_score')}/100")
                        st.warning(row.get("gpt_narrative") or "ไม่มี narrative")
                    if row.get("debate_summary"):
                        st.markdown(f"**Council summary:** {row.get('debate_summary')}")

        st.markdown("### Candidate digest ที่ส่งประกอบ AI")
        digest = {
            key: value for key, value in candidate_summary.items()
            if key in {"total", "by_priority", "by_strategy", "by_session", "updated_at", "policy"}
        }
        st.json(digest)

    with tabs[2]:
        st.markdown("## Learning Lab")
        st.caption("ระบบเก็บ evidence และบทเรียนจากผลที่ broker ยืนยันแล้ว ก่อนนำไปใช้ประกอบการตัดสินใจครั้งถัดไป")
        memories_df = load_memories(get_engine(os.getenv("DATABASE_URL_SYNC", "sqlite:////app/data/freebuff.db")))
        if memories_df.empty:
            st.info("ยังไม่มี memory จากไม้ที่ปิดแล้ว")
        else:
            lm = st.columns(4)
            lm[0].metric("Memories", len(memories_df))
            lm[1].metric("Wins", int((memories_df["outcome"] == "WIN").sum()))
            lm[2].metric("Losses", int((memories_df["outcome"] == "LOSS").sum()))
            lm[3].metric("Root cause known", int((memories_df["root_cause"] != "UNDETERMINED").sum()))
            st.warning("การบันทึกผลยังเป็น evidence-only: ระบบยังไม่สรุปสาเหตุเชิงเหตุผลจากไม้เดียว และยังไม่แก้กฎเทรดเอง")
            st.dataframe(
                memories_df[["created_at", "symbol", "strategy_id", "direction", "outcome", "profit", "rr_achieved", "root_cause", "lesson_learned_th", "rule_recommendation"]].head(50),
                use_container_width=True,
                hide_index=True,
            )
            st.markdown("### วิธีที่บทเรียนถูกใช้")
            st.markdown("1. บันทึก snapshot ตอนเข้าไม้  \n2. รอผลปิดที่ยืนยันจาก broker  \n3. ส่งบทเรียนล่าสุดของ symbol/strategy เดียวกันให้ AI Council  \n4. การปรับ strategy ต้องผ่าน dataset และ walk-forward ก่อน")

    with tabs[3]:
        st.markdown("## Performance & Journal")
        m = st.columns(6)
        m[0].metric("Trades", filtered_metrics["total"])
        m[1].metric("Win rate", f"{filtered_metrics['win_rate']}%")
        m[2].metric("Profit factor", filtered_metrics["profit_factor"])
        m[3].metric("Expectancy", f"${filtered_metrics['expectancy']:,.2f}")
        m[4].metric("Avg R", filtered_metrics["avg_r"])
        m[5].metric("Net P&L", f"${filtered_metrics['total_pnl']:,.2f}")
        p1, p2 = st.columns(2)
        with p1:
            if not filtered_trades.empty:
                st.plotly_chart(plot_strategy_performance(filtered_trades), use_container_width=True)
            else:
                st.info("ยังไม่มี trade performance")
        with p2:
            if not filtered_trades.empty:
                st.plotly_chart(plot_strategy_pnl(filtered_trades), use_container_width=True)
            else:
                st.info("ยังไม่มี P&L data")
        if not filtered_trades.empty:
            st.plotly_chart(plot_drawdown(filtered_trades), use_container_width=True)
            with st.expander("เปิด Trade Journal รายละเอียด"):
                st.dataframe(filtered_trades, use_container_width=True, hide_index=True)
        if not daily_df.empty:
            st.plotly_chart(px.bar(daily_df, x="trade_date", y="total_pnl", color=daily_df["total_pnl"].apply(lambda x: "Win" if x >= 0 else "Loss"), color_discrete_map={"Win": "#22c55e", "Loss": "#ef4444"}, title="Daily P&L").update_layout(template="plotly_dark"), use_container_width=True)

    with tabs[4]:
        st.markdown("## Controls & Safety")
        st.caption("ค่าที่เปลี่ยนตรงนี้มีผลกับ runtime หลังบันทึก ไม่ต้อง deploy ENV ใหม่ แต่ Risk Engine และ broker safeguards ยังแก้จากหน้านี้ไม่ได้")
        control_left, control_right = st.columns(2)
        with control_left:
            st.markdown("### Execution mode")
            selected_mode = st.selectbox("Runtime mode", ["PAPER", "DEMO", "LIVE"], index=["PAPER", "DEMO", "LIVE"].index(trading_mode), key="controls_runtime_mode")
            if selected_mode == "LIVE":
                st.error("LIVE ต้องยืนยันแยกต่างหาก และ MT5 ต้องเชื่อมบัญชีจริงที่ถูกต้อง")
                confirmation = st.text_input("พิมพ์ ENABLE LIVE TRADING", type="password", key="controls_live_confirmation")
                if st.button("Arm LIVE", type="secondary", disabled=confirmation != "ENABLE LIVE TRADING", key="controls_arm_live"):
                    arm_live_trading()
                    st.rerun()
                if live_armed:
                    st.error("LIVE ARMED — ใช้ PAPER เพื่อหยุด broker execution")
            elif selected_mode != trading_mode:
                if st.button(f"Apply {selected_mode}", type="primary", key="controls_apply_mode"):
                    set_runtime_trading_mode(selected_mode.lower())
                    st.rerun()
            else:
                st.success(f"Active mode: {trading_mode}")

            st.markdown("### AI candidate triage")
            st.caption("ต่ำกว่านี้ยังเก็บข้อมูลได้ แต่ไม่เรียก AI ทันที")
            observe_value = st.number_input("Observe floor", 0, 100, candidate_policy["observe_min_score"], key="policy_observe")
            batch_value = st.number_input("Batch review from", 0, 100, candidate_policy["batch_min_score"], key="policy_batch")
            immediate_value = st.number_input("Immediate AI from", 0, 100, candidate_policy["immediate_min_score"], key="policy_immediate")
            max_ai_value = st.number_input("Max immediate AI reviews / candle", 0, 10, candidate_policy["max_immediate_per_bar"], key="policy_max_ai")
            window_value = st.number_input("Digest window", 5, 500, candidate_policy["summary_window"], key="policy_window")
            if st.button("Save candidate policy", type="primary", key="save_candidate_policy"):
                try:
                    set_candidate_policy(
                        observe_min_score=int(observe_value), batch_min_score=int(batch_value),
                        immediate_min_score=int(immediate_value), max_immediate_per_bar=int(max_ai_value),
                        summary_window=int(window_value),
                    )
                    st.success("บันทึก candidate policy แล้ว")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

        with control_right:
            st.markdown("### Connections")
            connection_rows = [
                {"Component": "MT5 bridge", "Status": "Online" if mt5_status["online"] else "Offline", "Detail": mt5_status.get("server") or mt5_status.get("bridge_url", "")},
                {"Component": "Binance market data", "Status": "Online" if binance_status and binance_status["online"] else "Disabled/Offline", "Detail": binance_status.get("base_url", "not configured") if binance_status else "not configured"},
                {"Component": "AI Council", "Status": "Ready" if ai_status["council_ready"] else "Rule scorer only", "Detail": "provider credentials are deployment settings"},
            ]
            st.dataframe(pd.DataFrame(connection_rows), use_container_width=True, hide_index=True)
            render_openrouter_model_selector(st)

            st.markdown("### Risk policy (read-only)")
            risk_rows = [
                {"Setting": "Risk / trade", "Value": f"{settings.risk.risk_per_trade_pct * 100:.2f}%"},
                {"Setting": "Max daily loss", "Value": f"{settings.risk.max_daily_loss_pct * 100:.2f}%"},
                {"Setting": "Max trades / day", "Value": str(settings.risk.max_trades_per_day)},
                {"Setting": "Max consecutive losses", "Value": str(settings.risk.max_consecutive_losses)},
                {"Setting": "Minimum RR", "Value": str(settings.risk.min_rr)},
                {"Setting": "Max spread", "Value": f"{settings.risk.max_spread_pips} pips"},
            ]
            st.dataframe(pd.DataFrame(risk_rows), use_container_width=True, hide_index=True)
            st.info("Risk Engine เป็น authority สุดท้าย และไม่มีปุ่มใดใน dashboard ที่ bypass ได้")


def main():
    if not check_dashboard_auth():
        return
    refresh_seconds = max(0, int(os.getenv("DASHBOARD_REFRESH_SECONDS", "10")))
    if refresh_seconds:
        st_autorefresh(
            interval=refresh_seconds * 1000,
            key="dashboard_auto_refresh",
        )
    # Sidebar
    st.sidebar.title("🏦 Freebuff Trading")
    st.sidebar.markdown("---")

    # Check live connections
    mt5_status = check_mt5_bridge_status()
    configured_venues = [
        venue.strip().lower()
        for venue in os.getenv("MARKET_DATA_VENUES", os.getenv("MARKET_DATA_VENUE", "mt5")).split(",")
        if venue.strip()
    ]
    binance_status = check_binance_status() if "binance" in configured_venues else None
    ai_status = check_ai_status()
    runtime_status = read_runtime_status()
    trading_mode = get_runtime_trading_mode(os.getenv("TRADING_MODE", "PAPER")).upper()
    live_armed = is_live_armed()

    # Sidebar: Live Connection Status
    st.sidebar.markdown("### 🔌 Live Connection Status")
    if refresh_seconds:
        st.sidebar.caption(f"Auto refresh: every {refresh_seconds}s")
    mode_icon = {"DEMO": "🟢", "LIVE": "🔴"}.get(trading_mode, "🟡")
    st.sidebar.caption(f"{mode_icon} Trading mode: `{trading_mode}`")
    candidate_policy = get_candidate_policy()
    st.sidebar.caption(
        "AI triage: "
        f"batch ≥ {candidate_policy['batch_min_score']} · "
        f"immediate ≥ {candidate_policy['immediate_min_score']}"
    )
    st.sidebar.caption("รายละเอียดและการเปลี่ยนค่าทั้งหมดอยู่ที่แท็บ `Controls & Safety`")
    if runtime_status:
        st.sidebar.caption(
            f"Loop: `{runtime_status.get('state', 'unknown')}` · "
            f"cycles: `{runtime_status.get('cycle_count', 0)}`"
        )
    st.sidebar.caption(f"Enabled venues: `{', '.join(venue.upper() for venue in configured_venues)}`")
    if mt5_status["online"] and mt5_status["mt5_connected"]:
        st.sidebar.success(f"🟢 **MT5 Trader Online** ({mt5_status['latency_ms']}ms)")
        if mt5_status.get("account"):
            st.sidebar.caption(f"📌 Account: `{mt5_status['account']}` | `{mt5_status.get('server', '')}`")
        if mt5_status.get("balance") is not None:
            st.sidebar.caption(f"💰 Balance: `${mt5_status['balance']:,.2f}`")
    elif mt5_status["online"]:
        st.sidebar.warning("🟡 **Bridge UP / Waiting MT5**")
        st.sidebar.caption(f"Bridge responsive at `{mt5_status['bridge_url']}`")
    else:
        st.sidebar.error("🔴 **MT5 Disconnected**")
        st.sidebar.caption(f"Bridge `{mt5_status['bridge_url']}` not reachable")
    if binance_status is not None:
        if binance_status["online"]:
            st.sidebar.success(f"🟢 **Binance Market Data Online** ({binance_status['latency_ms']}ms)")
            st.sidebar.caption(f"Public API: `{binance_status['base_url']}`")
        else:
            st.sidebar.error("🔴 **Binance Market Data Disconnected**")
            st.sidebar.caption(f"API `{binance_status['base_url']}` not reachable")

    # AI Council in Sidebar
    st.sidebar.markdown("**AI Council (Debate):**")
    if ai_status["chatgpt_auth"] or ai_status["chatgpt_cli"]:
        st.sidebar.markdown("🟢 `ChatGPT (Codex)`: Auth Ready (Bear)")
    else:
        st.sidebar.markdown("🟡 `ChatGPT (Codex)`: Waiting Session")

    if ai_status["gemini_auth"]:
        st.sidebar.markdown("🟢 `Gemini (Google)`: API Key Ready (Bull)")
    else:
        st.sidebar.markdown("🟡 `Gemini (Google)`: API Key Not Ready")

    if ai_status["deepseek_auth"]:
        st.sidebar.markdown("🟢 `DeepSeek (OpenRouter)`: API Key Ready (Bull)")
    else:
        st.sidebar.markdown("⚪ `DeepSeek (OpenRouter)`: Not Configured")

    st.sidebar.markdown("🟢 `Strategy Engine`: 15 SMC Models")
    st.sidebar.markdown("---")
    if st.sidebar.button("🔒 Logout", use_container_width=True):
        st.session_state["authenticated"] = False
        st.query_params.clear()
        st.rerun()

    # Database connection
    db_url = os.getenv("DATABASE_URL_SYNC", "sqlite:////app/data/freebuff.db")
    engine = get_engine(db_url)

    # Load data
    trades_df = load_trades(engine)
    setups_df = load_setups(engine)
    equity_df = load_equity_curve(engine)
    daily_df = load_daily_risk(engine)

    # Calculate metrics
    metrics = calculate_metrics(trades_df)

    # Sidebar filters
    st.sidebar.markdown("### 🔍 Filters")

    # Strategy filter
    if not trades_df.empty:
        all_strategies = ["All"] + trades_df["strategy_id"].unique().tolist()
        selected_strategy = st.sidebar.selectbox("Strategy", all_strategies)
    else:
        selected_strategy = "All"

    # Direction filter
    direction_filter = st.sidebar.radio("Direction", ["All", "BUY", "SELL"])

    # Date range
    if not trades_df.empty:
        min_date = pd.to_datetime(trades_df["open_time"]).min()
        max_date = pd.to_datetime(trades_df["open_time"]).max()
        date_range = st.sidebar.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
    else:
        date_range = None

    # Apply filters
    filtered_trades = trades_df.copy()
    if selected_strategy != "All":
        filtered_trades = filtered_trades[filtered_trades["strategy_id"] == selected_strategy]
    if direction_filter != "All":
        filtered_trades = filtered_trades[filtered_trades["direction"] == direction_filter]
    if date_range and len(date_range) == 2:
        filtered_trades["open_time"] = pd.to_datetime(filtered_trades["open_time"])
        filtered_trades = filtered_trades[
            (filtered_trades["open_time"].dt.date >= date_range[0]) &
            (filtered_trades["open_time"].dt.date <= date_range[1])
        ]

    # Recalculate metrics for filtered data
    filtered_metrics = calculate_metrics(filtered_trades)

    # New task-oriented dashboard. The legacy tab layout below is retained in
    # source for reference during migration but is intentionally unreachable.
    candidate_summary = CandidateTriage().summary()
    render_redesigned_dashboard(
        mt5_status=mt5_status,
        binance_status=binance_status,
        ai_status=ai_status,
        runtime_status=runtime_status,
        trading_mode=trading_mode,
        live_armed=live_armed,
        configured_venues=configured_venues,
        candidate_policy=candidate_policy,
        candidate_summary=candidate_summary,
        trades_df=trades_df,
        setups_df=setups_df,
        equity_df=equity_df,
        daily_df=daily_df,
        filtered_trades=filtered_trades,
        filtered_metrics=filtered_metrics,
    )
    return

    # Tabs
    tab_overview, tab_journal, tab_learning, tab_strategy, tab_analysis, tab_risk = st.tabs([
        "📊 Overview",
        "📋 Trade Journal",
        "🧠 AI Learning & Memory",
        "🎯 Strategy Performance",
        "🔍 Setup Analysis",
        "⚠️ Risk Management",
    ])

    # ─── Overview Tab ─────────────────────────────────────────────────────────
    with tab_overview:
        # System Live Status Banner
        s_col1, s_col2, s_col3 = st.columns([1.2, 1.4, 1.0])
        with s_col1:
            if mt5_status["online"] and mt5_status["mt5_connected"]:
                st.success(
                    f"🟢 **MT5 Trader Online**\n\n"
                    f"Server: `{mt5_status.get('server', 'MT5')}` · Login: `{mt5_status.get('account', 'N/A')}` · Latency: `{mt5_status['latency_ms']}ms`"
                )
            elif mt5_status["online"]:
                st.warning(
                    f"🟡 **Bridge Waiting MT5**\n\n"
                    f"Bridge `{mt5_status['bridge_url']}` is UP, waiting for MT5 terminal connection."
                )
            else:
                st.error(
                    f"🔴 **MT5 Trader Offline**\n\n"
                    f"Cannot reach Bridge at `{mt5_status['bridge_url']}`"
                )
            if binance_status is not None:
                if binance_status["online"]:
                    st.success(
                        f"🟢 **Binance Market Data Online**\n\n"
                        f"Testnet/public API · Latency: `{binance_status['latency_ms']}ms`"
                    )
                else:
                    st.error(
                        f"🔴 **Binance Market Data Offline**\n\n"
                        f"Cannot reach `{binance_status['base_url']}`"
                    )

        with s_col2:
            cg_tag = "🟢 ChatGPT" if (ai_status["chatgpt_auth"] or ai_status["chatgpt_cli"]) else "🟡 ChatGPT"
            gm_tag = "🟢 Gemini" if ai_status["gemini_auth"] else "🟡 Gemini"
            ds_tag = "🟢 DeepSeek" if ai_status["deepseek_auth"] else "⚪ DeepSeek"
            if ai_status["council_ready"]:
                st.success(
                    f"🧠 **AI Council Debate: Online**\n\n"
                    f"{cg_tag} (Bear Trap) · {gm_tag if ai_status['gemini_auth'] else ds_tag} (Bull Confluence) · Auth Ready"
                )
            else:
                st.info(
                    f"🧠 **AI Council Status**\n\n"
                    f"{cg_tag} · {gm_tag if ai_status['gemini_auth'] else ds_tag} · Rule Scorer Active"
                )

        with s_col3:
            symbols = "XAUUSD · BTCUSDT" if "binance" in configured_venues else os.getenv("TRADING_SYMBOL", "XAUUSD")
            st.info(
                f"⚡ **Active Market & Engine**\n\n"
                f"Symbols: `{symbols}` · Mode: `{trading_mode}` · "
                f"Cycles: `{runtime_status.get('cycle_count', 0)}`"
            )

        if runtime_status.get("last_decision"):
            reason = runtime_status.get("last_reason") or runtime_status.get("last_error") or ""
            st.caption(
                f"Last engine decision: `{runtime_status['last_decision']}` "
                f"{('— ' + reason) if reason else ''}"
            )

        st.markdown("## 📊 Trading Overview")

        # Summary cards
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric(
                "Total Trades",
                filtered_metrics["total"],
                f"{filtered_metrics['winners']}W / {filtered_metrics['losers']}L",
            )
        with col2:
            st.metric(
                "Win Rate",
                f"{filtered_metrics['win_rate']}%",
                delta="Target: >50%",
                delta_color="normal" if filtered_metrics["win_rate"] >= 50 else "inverse",
            )
        with col3:
            st.metric(
                "Total P&L",
                f"${filtered_metrics['total_pnl']:,.2f}",
                delta_color="normal" if filtered_metrics["total_pnl"] >= 0 else "inverse",
            )
        with col4:
            st.metric(
                "Profit Factor",
                filtered_metrics["profit_factor"],
                delta="Target: >1.5",
                delta_color="normal" if filtered_metrics["profit_factor"] >= 1.5 else "inverse",
            )
        with col5:
            st.metric(
                "Max Drawdown",
                f"{filtered_metrics['max_drawdown']}%",
                delta_color="inverse",
            )

        # Second row of metrics
        col6, col7, col8, col9, col10 = st.columns(5)

        with col6:
            st.metric("Avg Win", f"${filtered_metrics['avg_win']:,.2f}")
        with col7:
            st.metric("Avg Loss", f"${filtered_metrics['avg_loss']:,.2f}")
        with col8:
            st.metric("Expectancy", f"${filtered_metrics['expectancy']:,.2f}")
        with col9:
            st.metric("Avg R", filtered_metrics["avg_r"])
        with col10:
            st.metric("Avg RR", filtered_metrics["avg_rr"])

        st.markdown("---")

        # Charts
        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            if not equity_df.empty:
                st.plotly_chart(plot_equity_curve(equity_df), use_container_width=True)
            else:
                st.info("No equity data available")

        with col_chart2:
            if not filtered_trades.empty:
                st.plotly_chart(plot_r_distribution(filtered_trades), use_container_width=True)
            else:
                st.info("No trade data for R-distribution")

        # Drawdown chart
        if not filtered_trades.empty:
            st.plotly_chart(plot_drawdown(filtered_trades), use_container_width=True)

    # ─── Trade Journal Tab ────────────────────────────────────────────────────
    with tab_journal:
        st.markdown("## 📋 Trade Journal")

        if filtered_trades.empty:
            st.info("No trades to display")
        else:
            # Format the dataframe for display
            display_df = filtered_trades[[
                "open_time", "exit_time", "direction", "symbol", "volume",
                "entry_price", "sl", "tp1", "exit_price",
                "net_profit", "outcome_r", "outcome_pips", "strategy_id"
            ]].copy()

            display_df.columns = [
                "Open Time", "Exit Time", "Dir", "Symbol", "Vol",
                "Entry", "SL", "TP1", "Exit",
                "P&L", "R-Multiple", "Pips", "Strategy"
            ]

            # Style P&L column
            def color_pnl(val):
                if isinstance(val, (int, float)):
                    color = "#22c55e" if val >= 0 else "#ef4444"
                    return f"color: {color}; font-weight: bold"
                return ""

            def color_dir(val):
                if val == "BUY":
                    return "color: #22c55e; font-weight: bold"
                elif val == "SELL":
                    return "color: #ef4444; font-weight: bold"
                return ""

            styled_df = display_df.style.applymap(color_pnl, subset=["P&L", "R-Multiple", "Pips"])
            styled_df = styled_df.applymap(color_dir, subset=["Dir"])

            st.dataframe(
                styled_df,
                height=500,
                use_container_width=True,
                column_config={
                    "Open Time": st.column_config.DatetimeColumn("Open Time", format="YYYY-MM-DD HH:mm"),
                    "Exit Time": st.column_config.DatetimeColumn("Exit Time", format="YYYY-MM-DD HH:mm"),
                    "Entry": st.column_config.NumberColumn("Entry", format="%.2f"),
                    "SL": st.column_config.NumberColumn("SL", format="%.2f"),
                    "TP1": st.column_config.NumberColumn("TP1", format="%.2f"),
                    "Exit": st.column_config.NumberColumn("Exit", format="%.2f"),
                    "P&L": st.column_config.NumberColumn("P&L", format="$%.2f"),
                    "R-Multiple": st.column_config.NumberColumn("R-Multiple", format="%.1fR"),
                    "Pips": st.column_config.NumberColumn("Pips", format="%.1f"),
                    "Vol": st.column_config.NumberColumn("Vol", format="%.2f"),
                },
            )

            # Summary stats
            st.markdown("---")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Best Trade", f"${filtered_metrics['best_trade']:,.2f}")
            with col2:
                st.metric("Worst Trade", f"${filtered_metrics['worst_trade']:,.2f}")
            with col3:
                st.metric("Avg P&L", f"${filtered_metrics['total_pnl'] / filtered_metrics['total']:,.2f}" if filtered_metrics['total'] > 0 else "$0")
            with col4:
                st.metric("Total Volume", f"{filtered_trades['volume'].sum():.2f} lots")


    # ─── AI Learning & Memory Bank Tab ───────────────────────────────────────
    with tab_learning:
        st.markdown("## 🧠 AI Brain & Continuous Learning Memory Bank")
        st.caption("ระบบเรียนรู้และปรับกลยุทธ์อัตโนมัติจากประสบการณ์จริง: ทุกไม้ที่ปิด (โดยเฉพาะไม้ที่ชน SL) จะถูก AI Post-Mortem ชันสูตรหาสาเหตุ สกัดเป็นบทเรียน และ Feed กลับเข้า AI Council เพื่อไม่ให้พลาดท่าเดิมซ้ำสอง")

        memories_df = load_memories(engine)

        if memories_df.empty:
            st.info("🧠 ยังไม่มีบทเรียนในคลังความจำ ระบบจะทำการวิเคราะห์และบันทึกอัตโนมัติทันทีที่มีออเดอร์ปิด (SL หรือ TP)")
        else:
            # Summary Metrics
            total_lessons = len(memories_df)
            losses_analyzed = len(memories_df[memories_df["outcome"] == "LOSS"])
            wins_recorded = len(memories_df[memories_df["outcome"] == "WIN"])
            
            top_causes = memories_df["root_cause"].value_counts()
            top_cause_str = top_causes.index[0] if not top_causes.empty else "N/A"

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Total Memories", total_lessons)
            with m2:
                st.metric("Losses Reflected (ชน SL)", losses_analyzed, delta="-Learning" if losses_analyzed > 0 else None, delta_color="inverse")
            with m3:
                st.metric("Wins Reinforced", wins_recorded, delta="+Good Pattern" if wins_recorded > 0 else None)
            with m4:
                st.metric("Top Failure Cause", top_cause_str)

            st.markdown("---")

            # Two columns: Chart & Recent Lessons Feed
            col_chart, col_feed = st.columns([1, 1.4])

            with col_chart:
                st.markdown("### 📊 Failure Root Cause Distribution")
                if losses_analyzed > 0:
                    loss_df = memories_df[memories_df["outcome"] == "LOSS"]
                    cause_counts = loss_df["root_cause"].value_counts().reset_index()
                    cause_counts.columns = ["Root Cause", "Count"]
                    fig = px.pie(
                        cause_counts,
                        names="Root Cause",
                        values="Count",
                        hole=0.4,
                        color_discrete_sequence=["#ef4444", "#f97316", "#eab308", "#8b5cf6", "#06b6d4"],
                    )
                    fig.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=10, r=10, t=20, b=10),
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.success("🎉 ยังไม่มีประวัติการขาดทุนในระบบ!")

                st.markdown("### ⚙️ How It Feeds the Council")
                st.info(
                    "📌 **Experience Injection:** ก่อนที่ Gemini Bull และ GPT Bear จะตัดสินใจ Setup ใดๆ "
                    "ระบบจะค้นหาบทเรียนที่ตรงกับกลยุทธ์นั้นๆ 3 ข้อล่าสุด และแนบเข้าไปใน Prompt โดยตรง "
                    "ทำให้ GPT Bear สามารถยกเคสอดีตมาคัดค้าน และ Gemini ต้องตรวจสอบว่าแก้จุดบกพร่องเดิมหรือยัง"
                )

            with col_feed:
                st.markdown("### 💡 Latest Lessons Learned (คลังบทเรียนล่าสุด)")
                for _, row in memories_df.head(15).iterrows():
                    is_loss = row["outcome"] == "LOSS"
                    box_color = "#ef4444" if is_loss else "#22c55e"
                    badge_bg = "rgba(239, 68, 68, 0.15)" if is_loss else "rgba(34, 197, 94, 0.15)"
                    icon = "⚠️" if is_loss else "✅"

                    pnl_val = float(row["profit"] or 0)
                    pnl_str = f"+${pnl_val:.2f}" if pnl_val >= 0 else f"-${abs(pnl_val):.2f}"

                    st.markdown(
                        f"""
                        <div style="background: rgba(255,255,255,0.03); border-left: 4px solid {box_color}; padding: 12px 16px; border-radius: 6px; margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <span style="font-weight: bold; font-size: 0.95rem; color: #f1f5f9;">
                                    {icon} {row['symbol']} {row['direction']} — {row['strategy_id']}
                                </span>
                                <span style="background: {badge_bg}; color: {box_color}; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem;">
                                    {row['outcome']} ({pnl_str})
                                </span>
                            </div>
                            <div style="font-size: 0.82rem; color: #94a3b8; margin-bottom: 6px;">
                                <b>Root Cause:</b> <code>{row['root_cause']}</code> | <b>Time:</b> {str(row['created_at'])[:19]}
                            </div>
                            <div style="font-size: 0.9rem; color: #e2e8f0; line-height: 1.4; background: rgba(0,0,0,0.25); padding: 8px 10px; border-radius: 4px;">
                                💬 <b>บทเรียน:</b> {row['lesson_learned_th']}
                            </div>
                            {f'<div style="font-size: 0.82rem; color: #38bdf8; margin-top: 6px;">🔧 <b>คำแนะนำปรับปรุง:</b> {row["rule_recommendation"]}</div>' if row.get("rule_recommendation") else ""}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    # ─── Strategy Performance Tab ─────────────────────────────────────────────
    with tab_strategy:
        st.markdown("## 🎯 Strategy Performance")

        if filtered_trades.empty:
            st.info("No trade data for strategy analysis")
        else:
            col1, col2 = st.columns(2)

            with col1:
                st.plotly_chart(plot_strategy_performance(filtered_trades), use_container_width=True)

            with col2:
                st.plotly_chart(plot_strategy_pnl(filtered_trades), use_container_width=True)

            # Monthly P&L
            st.plotly_chart(plot_monthly_pnl(filtered_trades), use_container_width=True)

            # Strategy detail table
            st.markdown("### 📊 Strategy Breakdown")

            strat_detail = filtered_trades.groupby("strategy_id").agg(
                Trades=("id", "count"),
                Winners=("net_profit", lambda x: (x > 0).sum()),
                Total_PnL=("net_profit", "sum"),
                Avg_R=("outcome_r", "mean"),
                Avg_Pips=("outcome_pips", "mean"),
                Best=("net_profit", "max"),
                Worst=("net_profit", "min"),
            ).reset_index()

            strat_detail["Win Rate"] = (strat_detail["Winners"] / strat_detail["Trades"] * 100).round(1)
            strat_detail["Avg P&L"] = (strat_detail["Total_PnL"] / strat_detail["Trades"]).round(2)

            st.dataframe(
                strat_detail.style.applymap(
                    lambda x: "color: #22c55e" if isinstance(x, (int, float)) and x > 0 else "color: #ef4444" if isinstance(x, (int, float)) and x < 0 else "",
                    subset=["Total_PnL", "Avg P&L", "Best", "Worst"]
                ),
                use_container_width=True,
                column_config={
                    "Total_PnL": st.column_config.NumberColumn("Total P&L", format="$%.2f"),
                    "Avg P&L": st.column_config.NumberColumn("Avg P&L", format="$%.2f"),
                    "Best": st.column_config.NumberColumn("Best", format="$%.2f"),
                    "Worst": st.column_config.NumberColumn("Worst", format="$%.2f"),
                    "Avg_R": st.column_config.NumberColumn("Avg R", format="%.2f"),
                    "Avg_Pips": st.column_config.NumberColumn("Avg Pips", format="%.1f"),
                },
            )

    # ─── Setup Analysis Tab ───────────────────────────────────────────────────
    with tab_analysis:
        st.markdown("## 🔍 Setup Analysis")

        if setups_df.empty:
            st.info("No setup data available")
        else:
            col1, col2 = st.columns(2)

            with col1:
                st.plotly_chart(plot_setup_analysis(setups_df), use_container_width=True)

            with col2:
                # AI Score vs Outcome
                traded_setups = setups_df[setups_df["decision"] == "TRADED"].copy()
                if not traded_setups.empty:
                    fig = go.Figure()

                    fig.add_trace(go.Box(
                        y=traded_setups["ai_score"],
                        name="AI Score",
                        marker_color="#3b82f6",
                    ))

                    fig.update_layout(
                        title="🤖 AI Score Distribution (Traded Setups)",
                        template="plotly_dark",
                        height=350,
                        margin=dict(l=0, r=0, t=40, b=0),
                        yaxis_title="AI Score",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No traded setups for AI score analysis")

            # Setup decision breakdown by strategy
            st.markdown("### 📊 Setup Decisions by Strategy")

            setup_by_strategy = setups_df.groupby(["strategy_id", "decision"]).size().unstack(fill_value=0)
            if not setup_by_strategy.empty:
                fig = go.Figure()

                for decision in setup_by_strategy.columns:
                    color = {"TRADED": "#22c55e", "SKIPPED": "#f59e0b", "REJECTED": "#ef4444"}.get(decision, "#3b82f6")
                    fig.add_trace(go.Bar(
                        name=decision,
                        x=setup_by_strategy.index,
                        y=setup_by_strategy[decision],
                        marker_color=color,
                    ))

                fig.update_layout(
                    barmode="stack",
                    title="📋 Setup Decisions by Strategy",
                    template="plotly_dark",
                    height=400,
                    margin=dict(l=0, r=0, t=40, b=0),
                    yaxis_title="Count",
                )
                st.plotly_chart(fig, use_container_width=True)

            # Rejection reasons
            rejected = setups_df[setups_df["decision"] == "REJECTED"]
            if not rejected.empty:
                st.markdown("### ❌ Rejection Reasons")
                reasons = rejected["rejection_reason"].value_counts()
                fig = go.Figure(go.Bar(
                    x=reasons.values,
                    y=reasons.index,
                    orientation="h",
                    marker_color="#ef4444",
                ))
                fig.update_layout(
                    template="plotly_dark",
                    height=300,
                    margin=dict(l=0, r=0, t=0, b=0),
                )
                st.plotly_chart(fig, use_container_width=True)

            # AI Council Debate Feed (Gemini vs GPT)
            has_debates = "gemini_verdict" in setups_df.columns and setups_df["gemini_verdict"].notna().any()
            if has_debates:
                st.markdown("### 🤖 AI Council Debate Feed (Gemini 🟢 vs GPT 🔴)")
                recent_debates = setups_df[setups_df["gemini_verdict"].notna()].head(10)
                for _, row in recent_debates.iterrows():
                    d_icon = "🟢" if row.get("decision") == "TRADED" else ("🟡" if row.get("decision") == "SKIPPED" else "🔴")
                    with st.expander(f"{d_icon} {row.get('created_at')} — {row.get('symbol')} {row.get('direction')} | Verdict: {row.get('decision')} (Rule: {row.get('rule_score')}, Combined: {row.get('combined_score')})"):
                        d_c1, d_c2 = st.columns(2)
                        with d_c1:
                            st.markdown(f"**Gemini (Bull Analyst):** `{row.get('gemini_verdict')}` ({row.get('gemini_score')}/100)")
                            st.info(row.get("gemini_narrative") or "No narrative")
                        with d_c2:
                            st.markdown(f"**GPT/Codex (Bear Analyst):** `{row.get('gpt_verdict')}` ({row.get('gpt_score')}/100)")
                            st.warning(row.get("gpt_narrative") or "No narrative")
                        if row.get("debate_summary"):
                            st.markdown(f"**⚖️ Council Summary:** {row.get('debate_summary')}")
                        if row.get("eql_summary"):
                            st.caption(f"**💧 Liquidity Pools:** {row.get('eql_summary')}")

    # ─── Risk Management Tab ──────────────────────────────────────────────────
    with tab_risk:
        st.markdown("## ⚠️ Risk Management")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Max Drawdown", f"{filtered_metrics['max_drawdown']}%")
            st.caption("Emergency threshold: 5%")

        with col2:
            st.metric("Circuit Breaker", "OFF" if daily_df["circuit_breaker"].sum() == 0 else "ON")

        with col3:
            st.metric("Consecutive Losses", "0")

        st.markdown("---")

        # Daily P&L
        if not daily_df.empty:
            st.plotly_chart(
                px.bar(
                    daily_df,
                    x="trade_date",
                    y="total_pnl",
                    color=daily_df["total_pnl"].apply(lambda x: "Win" if x >= 0 else "Loss"),
                    color_discrete_map={"Win": "#22c55e", "Loss": "#ef4444"},
                    title="📅 Daily P&L",
                ).update_layout(
                    template="plotly_dark",
                    height=350,
                    margin=dict(l=0, r=0, t=40, b=0),
                    yaxis_title="P&L ($)",
                ),
                use_container_width=True,
            )

            # Daily trade count
            st.plotly_chart(
                px.bar(
                    daily_df,
                    x="trade_date",
                    y="total_trades",
                    title="📊 Daily Trade Count",
                ).update_layout(
                    template="plotly_dark",
                    height=250,
                    margin=dict(l=0, r=0, t=40, b=0),
                    yaxis_title="Trades",
                ),
                use_container_width=True,
            )

        # Risk limits
        st.markdown("### 🛡️ Risk Limits Status")

        risk_limits = {
            "Max Daily Loss": {"value": "3%", "status": "OK", "threshold": "5%"},
            "Max Trades/Day": {"value": "5", "status": "OK", "threshold": "10"},
            "Max Consecutive Losses": {"value": "3", "status": "OK", "threshold": "3"},
            "Min RR Ratio": {"value": "2.0", "status": "OK", "threshold": "1.5"},
            "Max Spread": {"value": "5.0 pips", "status": "OK", "threshold": "8.0"},
        }

        risk_df = pd.DataFrame(risk_limits).T
        st.dataframe(risk_df, use_container_width=True)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
