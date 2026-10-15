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
from src.core.runtime_provider_settings import (
    clear_provider_secret,
    get_provider_settings,
    provider_status,
    save_provider_settings,
)
from src.ai.openrouter_model_catalog import (
    fetch_models,
    get_selected_model,
    group_models,
    save_selected_model,
)
from src.dashboard.terminal_auth import dashboard_auth_token

# ─── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Freebuff Trading Dashboard",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _dashboard_refresh_seconds() -> int:
    """Return a safe live-status interval without making the whole app rerun."""
    try:
        return max(0, int(os.getenv("DASHBOARD_REFRESH_SECONDS", "10")))
    except ValueError:
        return 10


DASHBOARD_REFRESH_SECONDS = _dashboard_refresh_seconds()

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
            api_key=get_provider_settings()["openrouter"]["api_key"],
            timeout=10,
        )
    except Exception:
        return []


def render_openrouter_model_selector(container=None) -> str:
    """Render and persist the OpenRouter model choice without exposing secrets."""
    container = container or st.sidebar
    current_model = get_selected_model()
    openrouter_settings = get_provider_settings()["openrouter"]
    api_key_configured = bool(openrouter_settings["api_key"])
    base_url = openrouter_settings["base_url"].rstrip("/")
    models = load_openrouter_models(base_url, api_key_configured)
    groups = group_models(models, current_model)

    container.markdown("### 🧠 OpenRouter Model")
    if not api_key_configured:
        container.info("ใส่ OpenRouter API key ในส่วน AI provider settings เพื่อโหลดรายการโมเดล")
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


@st.cache_data(ttl=15)
def fetch_binance_klines(symbol: str, timeframe: str = "15m", limit: int = 120) -> pd.DataFrame:
    """Fetch recent closed klines directly from Binance public REST API."""
    interval_map = {
        "M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d",
        "1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d",
    }
    tf = interval_map.get(timeframe, "15m")
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol.upper()}&interval={tf}&limit={limit}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "freebuff-dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode())
            rows = []
            for r in data:
                rows.append({
                    "timestamp": pd.to_datetime(r[0], unit="ms", utc=True),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5]),
                })
            return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def plot_candlestick_chart(
    candles_df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    recent_trades: pd.DataFrame | None = None,
) -> go.Figure:
    """Plot interactive Plotly Candlestick chart with trade levels."""
    if candles_df.empty:
        return go.Figure()

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=candles_df["timestamp"],
        open=candles_df["open"],
        high=candles_df["high"],
        low=candles_df["low"],
        close=candles_df["close"],
        name=f"{symbol} ({timeframe})",
        increasing_line_color="#22c55e",
        decreasing_line_color="#ef4444",
    ))

    # Overlay recent trade entry / SL / TP if available
    if recent_trades is not None and not recent_trades.empty and "symbol" in recent_trades.columns:
        sym_trades = recent_trades[recent_trades["symbol"] == symbol].head(3)
        for _, trade in sym_trades.iterrows():
            entry = trade.get("entry_price")
            sl = trade.get("sl")
            tp = trade.get("tp1")
            direction = trade.get("direction", "BUY")

            if entry and float(entry) > 0:
                fig.add_hline(
                    y=float(entry),
                    line_dash="dash",
                    line_color="#3b82f6",
                    annotation_text=f"Entry ({direction}): {float(entry):.2f}",
                    annotation_position="bottom right",
                )
            if sl and float(sl) > 0:
                fig.add_hline(
                    y=float(sl),
                    line_dash="dot",
                    line_color="#ef4444",
                    annotation_text=f"SL: {float(sl):.2f}",
                    annotation_position="top right",
                )
            if tp and float(tp) > 0:
                fig.add_hline(
                    y=float(tp),
                    line_dash="dot",
                    line_color="#22c55e",
                    annotation_text=f"TP: {float(tp):.2f}",
                    annotation_position="bottom right",
                )

    fig.update_layout(
        title=f"🕯️ {symbol} — {timeframe} Binance Futures",
        xaxis_title="Time (UTC)",
        yaxis_title="Price ($)",
        template="plotly_dark",
        height=520,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis_rangeslider_visible=False,
    )
    return fig


def render_tradingview_widget(symbol: str = "BTCUSDT", interval: str = "15", height: int = 560) -> None:
    """Embed TradingView real-time widget for Binance USDT-M Futures."""
    import streamlit.components.v1 as components

    clean_symbol = symbol.replace("USDT", "USDT").upper()
    interval_map = {
        "M1": "1", "M5": "5", "M15": "15", "H1": "60", "H4": "240", "D1": "D",
        "1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D",
    }
    tv_interval = interval_map.get(interval, "15")
    tv_symbol = f"BINANCE:{clean_symbol}.P"

    html_code = f"""
    <div class="tradingview-widget-container" style="height:{height}px;width:100%">
      <div id="tradingview_chart_{clean_symbol}" style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "autosize": true,
        "symbol": "{tv_symbol}",
        "interval": "{tv_interval}",
        "timezone": "Asia/Bangkok",
        "theme": "dark",
        "style": "1",
        "locale": "th",
        "toolbar_bg": "#1e293b",
        "enable_publishing": false,
        "allow_symbol_change": true,
        "save_image": false,
        "container_id": "tradingview_chart_{clean_symbol}"
      }}
      );
      </script>
    </div>
    """
    components.html(html_code, height=height)


def render_market_chart_section(
    default_symbol: str = "BTCUSDT",
    trades_df: pd.DataFrame | None = None,
    setups_df: pd.DataFrame | None = None,
) -> None:
    """Render market chart section with TradingView live feed and Plotly AI setup levels."""
    from pathlib import Path

    available_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    watchlist_path = Path("data/crypto_watchlist.json")
    if watchlist_path.exists():
        try:
            with open(watchlist_path, "r", encoding="utf-8") as f:
                w_data = json.load(f)
                for cand in w_data.get("candidates", []):
                    s = cand.get("symbol")
                    if s and s not in available_symbols:
                        available_symbols.append(s)
        except Exception:
            pass

    col_sym, col_tf, col_type = st.columns([2, 1.5, 2.5])
    with col_sym:
        def_idx = available_symbols.index(default_symbol) if default_symbol in available_symbols else 0
        selected_symbol = st.selectbox("🪙 เลือกเหรียญ", available_symbols, index=def_idx, key=f"chart_sym_{default_symbol}")
    with col_tf:
        timeframe_options = ["M5", "M15", "H1", "H4", "D1"]
        selected_tf = st.selectbox("⏱️ Timeframe", timeframe_options, index=1, key=f"chart_tf_{default_symbol}")
    with col_type:
        chart_type = st.radio("📊 รูปแบบกราฟ", ["TradingView (Live Pro)", "Plotly (AI Setup & SL/TP)"], horizontal=True, key=f"chart_mode_{default_symbol}")

    if chart_type == "TradingView (Live Pro)":
        render_tradingview_widget(symbol=selected_symbol, interval=selected_tf, height=560)
    else:
        with st.spinner(f"กำลังดึงแท่งเทียน {selected_symbol} ({selected_tf})..."):
            kline_df = fetch_binance_klines(selected_symbol, selected_tf, limit=120)
            if not kline_df.empty:
                st.plotly_chart(
                    plot_candlestick_chart(kline_df, selected_symbol, selected_tf, recent_trades=trades_df),
                    use_container_width=True,
                )
            else:
                st.warning(f"ไม่สามารถดึงข้อมูลแท่งเทียนของ {selected_symbol} จาก Binance ได้ในขณะนี้ กรุณาใช้มุมมอง TradingView ด้านบน")

    # Show recent trade executions on this symbol
    if trades_df is not None and not trades_df.empty and "symbol" in trades_df.columns:
        sym_trades = trades_df[trades_df["symbol"] == selected_symbol].head(5)
        if not sym_trades.empty:
            with st.expander(f"📜 ออเดอร์ล่าสุดของ {selected_symbol} (มี Entry/SL/TP ในกราฟ)", expanded=False):
                st.dataframe(
                    sym_trades[["open_time", "direction", "entry_price", "sl", "tp1", "net_profit", "status"]],
                    use_container_width=True,
                    hide_index=True,
                )


# ─── Main App ─────────────────────────────────────────────────────────────────


# ─── Live Health Checks ───────────────────────────────────────────────────────

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
    """Check CLI installation and dashboard-managed provider availability."""
    configured_providers = provider_status()
    codex_auth_files = [
        os.path.expanduser("~/.codex/auth.json"),
        "/root/.codex/auth.json",
        "/mnt/c/Users/Dulla/.codex/auth.json",
        r"C:\Users\Dulla\.codex\auth.json",
    ]
    codex_auth_ok = any(os.path.exists(p) for p in codex_auth_files) or bool(configured_providers["codex"]["configured"])
    codex_cli_ok = bool(shutil.which("codex")) or any(
        os.path.exists(p) for p in [
            "/usr/local/bin/codex",
            "/usr/bin/codex",
            os.path.expanduser("~/.local/bin/codex"),
            "/mnt/c/Users/Dulla/.codex/plugins/.plugin-appserver/codex.exe",
            r"C:\Users\Dulla\.codex\plugins\.plugin-appserver\codex.exe",
        ]
    )

    ai_cli = get_provider_settings()["gemini"]["cli_bin"]
    antigravity_cli_ok = bool(shutil.which(ai_cli) or (os.path.isabs(ai_cli) and os.access(ai_cli, os.X_OK)))
    antigravity_auth_ok = bool(configured_providers["gemini"]["configured"])
    openrouter_auth_ok = bool(configured_providers["openrouter"]["configured"])

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
    return dashboard_auth_token(password)

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


def _live_dashboard_state() -> dict:
    """Read only the small, volatile dashboard state needed for live indicators."""
    return {
        "binance_status": check_binance_status(),
        "ai_status": check_ai_status(),
        "runtime_status": read_runtime_status(),
        "trading_mode": get_runtime_trading_mode(os.getenv("TRADING_MODE", "PAPER")).upper(),
        "live_armed": is_live_armed(),
        "candidate_policy": get_candidate_policy(),
        "candidate_summary": CandidateTriage().summary(),
    }


@st.fragment(run_every=DASHBOARD_REFRESH_SECONDS or None)
def render_live_sidebar() -> None:
    """Refresh only live connection indicators, preserving dashboard controls."""
    state = _live_dashboard_state()
    binance_status = state["binance_status"]
    ai_status = state["ai_status"]
    runtime_status = state["runtime_status"]
    trading_mode = state["trading_mode"]
    candidate_policy = state["candidate_policy"]

    st.markdown("### 🔌 Live Connection Status")
    if DASHBOARD_REFRESH_SECONDS:
        st.caption(f"อัปเดตเฉพาะสถานะสดทุก {DASHBOARD_REFRESH_SECONDS} วินาที")
    mode_icon = {"DEMO": "🟢", "LIVE": "🔴"}.get(trading_mode, "🟡")
    st.caption(f"{mode_icon} Trading mode: `{trading_mode}`")
    st.caption(
        "AI triage: "
        f"batch ≥ {candidate_policy['batch_min_score']} · "
        f"immediate ≥ {candidate_policy['immediate_min_score']}"
    )
    st.caption("รายละเอียดและการเปลี่ยนค่าทั้งหมดอยู่ที่แท็บ `Controls & Safety`")
    if runtime_status:
        st.caption(
            f"Loop: `{runtime_status.get('state', 'unknown')}` · "
            f"cycles: `{runtime_status.get('cycle_count', 0)}`"
        )
    st.caption("Venue: `Binance USDT-M Futures`")
    if binance_status["online"]:
        st.success(f"🟢 **Binance Market Data Online** ({binance_status['latency_ms']}ms)")
        st.caption(f"Public API: `{binance_status['base_url']}`")
    else:
        st.error("🔴 **Binance Market Data Disconnected**")
        st.caption(f"API `{binance_status['base_url']}` not reachable")

    st.markdown("**AI Council (Debate):**")
    if ai_status["chatgpt_auth"] or ai_status["chatgpt_cli"]:
        st.markdown("🟢 `ChatGPT (Codex)`: Auth Ready (Bear)")
    else:
        st.markdown("🟡 `ChatGPT (Codex)`: Waiting Session")
    if ai_status["gemini_auth"]:
        st.markdown("🟢 `Gemini (Google)`: API Key Ready (Bull)")
    else:
        st.markdown("🟡 `Gemini (Google)`: API Key Not Ready")
    if ai_status["deepseek_auth"]:
        st.markdown("🟢 `DeepSeek (OpenRouter)`: API Key Ready (Bull)")
    else:
        st.markdown("⚪ `DeepSeek (OpenRouter)`: Not Configured")
    st.markdown("🟢 `Strategy Engine`: 15 SMC Models")


@st.fragment(run_every=DASHBOARD_REFRESH_SECONDS or None)
def render_live_dashboard_header() -> None:
    """Keep the decision-critical header current without rerunning tabs or filters."""
    state = _live_dashboard_state()
    runtime_status = state["runtime_status"]
    trading_mode = state["trading_mode"]
    live_armed = state["live_armed"]
    candidate_summary = state["candidate_summary"]
    engine_state = str(runtime_status.get("state", "unknown")).lower()
    engine_tone = "good" if engine_state == "running" else "warn" if engine_state in {"starting", "degraded"} else "bad"
    engine_label = {
        "running": "Running",
        "starting": "Starting",
        "error": "Error",
        "stopped": "Stopped",
    }.get(engine_state, engine_state.title())
    priorities = candidate_summary.get("by_priority", {}) or {}

    head = st.columns([1.3, 1.1, 1.1, 1.1, 1.5])
    with head[0]:
        _render_status_chip("Engine", engine_label, engine_tone)
    with head[1]:
        _render_status_chip("Mode", trading_mode, "bad" if trading_mode == "LIVE" and live_armed else "good" if trading_mode == "DEMO" else "neutral")
    with head[2]:
        _render_status_chip("Candidates", str(int(candidate_summary.get("total", 0) or 0)), "good" if candidate_summary.get("total") else "warn")
    with head[3]:
        _render_status_chip("AI review now", str(int(priorities.get("immediate", 0) or 0)), "good" if priorities.get("immediate") else "neutral")
    with head[4]:
        last_decision = runtime_status.get("last_decision", "Waiting")
        raw_reason = runtime_status.get("last_reason") or runtime_status.get("last_error")
        last_reason = raw_reason if raw_reason not in {None, "", "unknown", "None"} else "รอผลการประเมินรอบถัดไป"
        st.info(f"**Latest:** `{last_decision}`\n\n{last_reason}")


def _save_provider_from_form(provider: str, **changes: str | None) -> None:
    """Save one provider form and keep validation errors inside its panel."""
    try:
        save_provider_settings(provider, **changes)
        st.success("บันทึกแล้ว — worker จะใช้ค่าใหม่นี้ในการประเมินรอบถัดไป")
    except ValueError as exc:
        st.error(str(exc))


def render_ai_provider_settings() -> None:
    """Render write-only AI provider credentials for Controls & Safety."""
    states = provider_status()
    values = get_provider_settings()
    st.markdown("### AI provider settings")
    st.caption(
        "API key และ Codex login จะถูกเข้ารหัสก่อนบันทึกใน runtime volume; "
        "หน้าจอนี้แสดงเพียงสถานะ ไม่แสดง secret เดิม"
    )

    with st.expander("ChatGPT / Codex (Bear Analyst)", expanded=not states["codex"]["configured"]):
        st.caption(f"Codex login: {'ตั้งค่าแล้ว' if states['codex']['configured'] else 'ยังไม่ตั้งค่า'} · source: {states['codex']['source']}")
        st.caption(f"OpenAI API fallback: {'ตั้งค่าแล้ว' if states['openai']['configured'] else 'ยังไม่ตั้งค่า'} · source: {states['openai']['source']}")
        with st.form("codex_provider_settings"):
            codex_auth_json = st.text_input(
                "วางเนื้อหา Codex auth.json เพื่อ login", type="password",
                help="วางเฉพาะเมื่อเปลี่ยน session; ปล่อยว่างไว้เพื่อเก็บค่าเดิม",
            )
            openai_api_key = st.text_input(
                "OpenAI API key (fallback)", type="password",
                help="ใช้เมื่อ Codex CLI login ใช้งานไม่ได้; ปล่อยว่างไว้เพื่อเก็บค่าเดิม",
            )
            openai_model = st.text_input("OpenAI model", value=values["openai"]["model"])
            if st.form_submit_button("บันทึก ChatGPT / Codex", type="primary"):
                _save_provider_from_form(
                    "codex", auth_json=codex_auth_json or None,
                )
                _save_provider_from_form(
                    "openai", api_key=openai_api_key or None, model=openai_model,
                )
        if st.checkbox("ยืนยันลบ Codex login ที่บันทึกไว้", key="clear_codex_auth"):
            if st.button("ลบ Codex login", key="clear_codex_auth_button"):
                clear_provider_secret("codex", "auth_json")
                st.success("ลบ Codex login แล้ว")
                st.rerun()

    with st.expander("Gemini / Antigravity (Bull Analyst)", expanded=not states["gemini"]["configured"]):
        st.caption(f"Gemini API: {'ตั้งค่าแล้ว' if states['gemini']['configured'] else 'ยังไม่ตั้งค่า'} · source: {states['gemini']['source']}")
        with st.form("gemini_provider_settings"):
            gemini_api_key = st.text_input(
                "Gemini API key", type="password",
                help="ส่งให้ Antigravity CLI เฉพาะตอนเรียกประเมิน; ปล่อยว่างไว้เพื่อเก็บค่าเดิม",
            )
            gemini_cli_bin = st.text_input("Antigravity CLI command", value=values["gemini"]["cli_bin"])
            if st.form_submit_button("บันทึก Gemini", type="primary"):
                _save_provider_from_form(
                    "gemini", api_key=gemini_api_key or None, cli_bin=gemini_cli_bin,
                )
        if st.checkbox("ยืนยันลบ Gemini API key ที่บันทึกไว้", key="clear_gemini_key"):
            if st.button("ลบ Gemini API key", key="clear_gemini_key_button"):
                clear_provider_secret("gemini", "api_key")
                st.success("ลบ Gemini API key แล้ว")
                st.rerun()

    with st.expander("OpenRouter / DeepSeek (Bull Analyst)", expanded=not states["openrouter"]["configured"]):
        st.caption(f"OpenRouter API: {'ตั้งค่าแล้ว' if states['openrouter']['configured'] else 'ยังไม่ตั้งค่า'} · source: {states['openrouter']['source']}")
        with st.form("openrouter_provider_settings"):
            openrouter_api_key = st.text_input(
                "OpenRouter API key", type="password",
                help="ปล่อยว่างไว้เพื่อเก็บค่าเดิม",
            )
            openrouter_base_url = st.text_input("Base URL", value=values["openrouter"]["base_url"])
            openrouter_site_url = st.text_input("Site URL", value=values["openrouter"]["site_url"])
            openrouter_app_name = st.text_input("App name", value=values["openrouter"]["app_name"])
            if st.form_submit_button("บันทึก OpenRouter", type="primary"):
                _save_provider_from_form(
                    "openrouter", api_key=openrouter_api_key or None,
                    base_url=openrouter_base_url, site_url=openrouter_site_url,
                    app_name=openrouter_app_name,
                )
        render_openrouter_model_selector(st)
        if st.checkbox("ยืนยันลบ OpenRouter API key ที่บันทึกไว้", key="clear_openrouter_key"):
            if st.button("ลบ OpenRouter API key", key="clear_openrouter_key_button"):
                clear_provider_secret("openrouter", "api_key")
                st.success("ลบ OpenRouter API key แล้ว")
                st.rerun()


def render_cli_login_console() -> None:
    """Link to the raw-keystroke PTY terminal for supported CLI auth flows."""
    st.markdown("### CLI Login Terminal")
    st.caption(
        "Terminal จริงสำหรับ Codex, agy และ ClinePass: รองรับปุ่มลูกศร, เมนู TUI, "
        "OAuth และการวางข้อความ ระบบเปิดได้เฉพาะคำสั่ง login ที่อนุญาต ไม่ใช่ shell ทั่วไป"
    )
    password = os.getenv("DASHBOARD_PASSWORD", "freebuff2026").strip()
    if not password:
        st.warning("ต้องตั้ง DASHBOARD_PASSWORD ก่อนใช้ terminal")
        return
    st.link_button("เปิด CLI Login Terminal", f"/terminal?auth={dashboard_auth_token(password)}", type="primary")


def render_homework_and_readiness_tab(trades_df: pd.DataFrame) -> None:
    """Render Agent Homework & Watchlist along with Live Promotion Readiness Gauge."""
    from pathlib import Path
    from src.risk.promotion_gate import PromotionGate
    from src.market.crypto_screener import CryptoScreener

    st.markdown("## 🛡️ Live Promotion Readiness Gauge (เกจวัดความพร้อม Live)")
    st.caption("ระบบตรวจสอบและรับรองความพร้อมทางสถิติและวินัยความเสี่ยงก่อนอนุญาตให้เลื่อนขั้นสู่โหมด LIVE")

    trades_records = trades_df.to_dict(orient="records") if not trades_df.empty else []
    eval_result = PromotionGate().evaluate_trades(trades_records)

    passed_count = sum(1 for g in eval_result.gate_checks if g.passed)
    total_gates = len(eval_result.gate_checks)
    readiness_pct = (passed_count / total_gates) * 100 if total_gates else 0

    # Readiness Progress Bar
    bar_color = "🟢" if eval_result.is_promotable else "🟡" if readiness_pct >= 50 else "🔴"
    st.progress(
        readiness_pct / 100.0,
        text=f"{bar_color} ความพร้อมเลื่อนขั้น: {readiness_pct:.0f}% (ผ่าน {passed_count}/{total_gates} เกณฑ์ความปลอดภัย)",
    )

    # Metric Cards
    g_cols = st.columns(5)
    remaining_trades = max(0, 30 - eval_result.total_trades)
    sample_delta = f"ขาดอีก {remaining_trades} ไม้" if remaining_trades > 0 else "ครบเกณฑ์แล้ว"
    g_cols[0].metric("Sample Size", f"{eval_result.total_trades} / 30", sample_delta)
    g_cols[1].metric("Win Rate", f"{eval_result.win_rate_pct:.1f}%", "เกณฑ์ >= 40%")
    g_cols[2].metric("Profit Factor", f"{eval_result.profit_factor:.2f}", "เกณฑ์ >= 1.50")
    g_cols[3].metric("Net P&L", f"${eval_result.net_pnl:+,.2f}", "เกณฑ์ > $0")
    g_cols[4].metric("Max Drawdown", f"{eval_result.max_drawdown_pct:.2f}%", "เกณฑ์ <= 5%")

    # Gate Details Expander
    with st.expander("📋 รายละเอียดเกณฑ์ความปลอดภัยทั้ง 6 ข้อ (Promotion Gate Audit)", expanded=True):
        gate_rows = []
        for g in eval_result.gate_checks:
            gate_rows.append({
                "Gate Name": g.name,
                "Target": g.target,
                "Actual": g.actual,
                "Status": "✅ PASS" if g.passed else "❌ FAIL",
                "Description": g.description,
            })
        st.dataframe(pd.DataFrame(gate_rows), use_container_width=True, hide_index=True)

    if eval_result.is_promotable:
        st.success("🎉 **ยินดีด้วย! ระบบผ่านเกณฑ์ความปลอดภัยครบทั้งหมด 100% พร้อมเปิด Live Trading ได้อย่างมั่นใจ**")
    else:
        st.info(f"⏳ **คำแนะนำปัจจุบัน:** {eval_result.summary_th}")

    st.markdown("---")
    st.markdown("## 📋 Agent Homework & Watchlist (การบ้านประจำวัน & เหรียญคัดสรร)")
    st.caption("AI ทำการบ้านวิเคราะห์แนวโน้ม Macro ของ Bitcoin และสแกนเหรียญ Futures ที่มี Volume และ Momentum สูง")

    col_btn, col_info = st.columns([1.5, 3.5])
    with col_btn:
        if st.button("🔄 Run Screener Now (สั่ง AI ทำการบ้านทันที)", use_container_width=True, type="primary"):
            with st.spinner("AI กำลังดึงข้อมูล Binance 24h Tickers และวิเคราะห์ BTC Macro..."):
                try:
                    import asyncio
                    asyncio.run(CryptoScreener().run_homework())
                    st.success("ทำการบ้านและอัปเดต Watchlist เรียบร้อยแล้ว!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"เกิดข้อผิดพลาดในการรัน Screener: {exc}")

    watchlist_path = Path("data/crypto_watchlist.json")
    watchlist_data = None
    if watchlist_path.exists():
        try:
            with open(watchlist_path, "r", encoding="utf-8") as f:
                watchlist_data = json.load(f)
        except Exception:
            pass

    if not watchlist_data:
        st.info("ยังไม่มีข้อมูล Watchlist ล่าสุด คลิกปุ่ม 'Run Screener Now' ด้านบนเพื่อให้ AI ทำการบ้านรอบแรก")
        return

    with col_info:
        st.caption(f"🕒 ข้อมูลล่าสุดเมื่อ: `{watchlist_data.get('timestamp', 'Unknown')}`")

    # BTC Macro View
    btc_report = watchlist_data.get("btc_report")
    if btc_report:
        st.markdown("### 👑 Bitcoin Macro Framework")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Macro Bias", btc_report.get("macro_bias", "UNKNOWN"))
        b2.metric("H4 Trend", btc_report.get("h4_trend", "UNKNOWN"))
        b3.metric("Crowd Bias", btc_report.get("crowd_bias", "UNKNOWN"))
        b4.metric("Funding Rate", f"{btc_report.get('funding_rate_pct', 0.0):+.4f}%")

        if btc_report.get("ai_context_snippet"):
            st.caption(f"🧠 **AI Perspective:** {btc_report['ai_context_snippet']}")

    # Candidates Table
    candidates = watchlist_data.get("candidates", [])
    if candidates:
        st.markdown(f"### 🎯 Top {len(candidates)} Watchlist Candidates")
        cand_rows = []
        for idx, c in enumerate(candidates, 1):
            cand_rows.append({
                "Rank": f"#{idx}",
                "Symbol": c.get("symbol"),
                "Price": f"${c.get('price', 0):,.2f}",
                "24h Change": f"{c.get('price_change_pct', 0):+.2f}%",
                "24h Volume": c.get("formatted_volume") or f"${c.get('quote_volume_24h', 0) / 1e6:.1f}M",
                "Opportunity Score": c.get("score"),
                "24h Range Spread": f"{c.get('high_low_spread_pct', 0):.2f}%",
                "Tags": ", ".join(c.get("tags", [])),
            })
        st.dataframe(pd.DataFrame(cand_rows), use_container_width=True, hide_index=True)
        top_symbol = candidates[0].get("symbol", "BTCUSDT")
        with st.expander(f"📊 ดูกราฟราคาเหรียญใน Watchlist ({top_symbol})", expanded=False):
            render_market_chart_section(default_symbol=top_symbol, trades_df=trades_df)
    else:
        st.info("ไม่มีเหรียญที่ผ่านเกณฑ์ Volume & Opportunity ในรอบนี้")


def render_redesigned_dashboard(
    *,
    binance_status: dict,
    ai_status: dict,
    runtime_status: dict,
    trading_mode: str,
    live_armed: bool,
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
    render_live_dashboard_header()

    if engine_state != "running":
        st.warning(f"Worker state is `{engine_label}`. ตรวจสอบ health และ logs ก่อนประเมินว่าไม่มี setup")

    tabs = st.tabs([
        "🎛️ Command Center",
        "📊 Live Chart",
        "📋 Agent Homework & Readiness",
        "🔎 Candidates & AI",
        "🧠 Learning",
        "📈 Performance",
        "⚙️ Controls & Safety",
    ])

    with tabs[0]:
        st.markdown("## ตอนนี้ระบบกำลังทำอะไร")
        status_cols = st.columns(3)
        with status_cols[0]:
            if binance_status["online"]:
                st.success(f"**Binance market data online**\n\n{binance_status['latency_ms']}ms · public API")
            else:
                st.error("**Binance market data offline**\n\nตรวจสอบ endpoint/network")
        with status_cols[1]:
            st.info("**Binance USDT-M Futures**\n\nExchange ที่เปิดใช้งาน")
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

        st.markdown("## 📊 Live Market Chart (กราฟราคา Real-Time)")
        with st.expander("เปิด/ปิด ดูกราฟราคา Real-Time ทันที", expanded=True):
            render_market_chart_section(default_symbol=settings.binance_symbol, trades_df=trades_df, setups_df=setups_df)

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
        render_market_chart_section(default_symbol=settings.binance_symbol, trades_df=trades_df, setups_df=setups_df)

    with tabs[2]:
        render_homework_and_readiness_tab(trades_df)

    with tabs[3]:
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

    with tabs[4]:
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

    with tabs[5]:
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

    with tabs[6]:
        st.markdown("## Controls & Safety")
        st.caption("ค่าที่เปลี่ยนตรงนี้มีผลกับ runtime หลังบันทึก ไม่ต้อง deploy ENV ใหม่ แต่ Risk Engine และ broker safeguards ยังแก้จากหน้านี้ไม่ได้")
        control_left, control_right = st.columns(2)
        with control_left:
            st.markdown("### Execution mode")
            selected_mode = st.selectbox("Runtime mode", ["PAPER", "DEMO", "LIVE"], index=["PAPER", "DEMO", "LIVE"].index(trading_mode), key="controls_runtime_mode")
            if selected_mode == "LIVE":
                st.error("LIVE ต้องยืนยันแยกต่างหาก และ Binance safeguards จะยังบังคับใช้")
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
                {"Component": "Binance market data", "Status": "Online" if binance_status["online"] else "Offline", "Detail": binance_status["base_url"]},
                {"Component": "AI Council", "Status": "Ready" if ai_status["council_ready"] else "Rule scorer only", "Detail": "ตั้งค่า provider ได้ใน Controls & Safety"},
            ]
            st.dataframe(pd.DataFrame(connection_rows), use_container_width=True, hide_index=True)
            render_ai_provider_settings()
            render_cli_login_console()

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
    # Sidebar
    st.sidebar.title("🏦 Freebuff Trading")
    st.sidebar.markdown("---")

    # Check live connections
    binance_status = check_binance_status()
    ai_status = check_ai_status()
    runtime_status = read_runtime_status()
    trading_mode = get_runtime_trading_mode(os.getenv("TRADING_MODE", "PAPER")).upper()
    live_armed = is_live_armed()

    candidate_policy = get_candidate_policy()
    with st.sidebar:
        render_live_sidebar()
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

    # Task-oriented Binance dashboard.
    candidate_summary = CandidateTriage().summary()
    render_redesigned_dashboard(
        binance_status=binance_status,
        ai_status=ai_status,
        runtime_status=runtime_status,
        trading_mode=trading_mode,
        live_armed=live_armed,
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

# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
