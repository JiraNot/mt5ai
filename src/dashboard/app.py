"""Freebuff Trading Dashboard — Interactive Streamlit App.

Usage:
    streamlit run src/dashboard/app.py
    streamlit run src/dashboard/app.py -- --db sqlite+aiosqlite:///freebuff.db
"""

from __future__ import annotations

import argparse
import json
import sys
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
def get_engine(db_url: str = "sqlite:///freebuff.db"):
    """Create synchronous SQLite engine for Streamlit."""
    return create_engine(db_url, echo=False)


def load_trades(engine) -> pd.DataFrame:
    """Load all trades into DataFrame."""
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


def load_setups(engine) -> pd.DataFrame:
    """Load all setup logs into DataFrame."""
    query = text("""
        SELECT
            s.id, s.symbol, s.timeframe, s.strategy_id,
            s.direction, s.rule_score, s.ai_score, s.combined_score,
            s.decision, s.entry_price, s.stop_loss,
            s.take_profit_1, s.rr_ratio,
            s.confluences, s.risk_flags, s.rejection_reason,
            s.outcome_r, s.outcome_pips, s.created_at
        FROM setup_log s
        ORDER BY s.created_at DESC
    """)
    return pd.read_sql(query, engine)


def load_equity_curve(engine) -> pd.DataFrame:
    """Load account snapshots for equity curve."""
    query = text("""
        SELECT ts, equity, balance
        FROM account_snapshots
        ORDER BY ts
    """)
    return pd.read_sql(query, engine)


def load_daily_risk(engine) -> pd.DataFrame:
    """Load daily risk data."""
    query = text("""
        SELECT
            trade_date, total_pnl, total_trades,
            winning_trades, losing_trades, circuit_breaker
        FROM daily_risk
        ORDER BY trade_date
    """)
    return pd.read_sql(query, engine)


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

def main():
    # Sidebar
    st.sidebar.title("🏦 Freebuff Trading")
    st.sidebar.markdown("---")

    # Database connection
    db_url = "sqlite:///freebuff.db"
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

    # Tabs
    tab_overview, tab_journal, tab_strategy, tab_analysis, tab_risk = st.tabs([
        "📊 Overview",
        "📋 Trade Journal",
        "🎯 Strategy Performance",
        "🔍 Setup Analysis",
        "⚠️ Risk Management",
    ])

    # ─── Overview Tab ─────────────────────────────────────────────────────────
    with tab_overview:
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
