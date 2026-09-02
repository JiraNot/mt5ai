"""Generate a self-contained HTML dashboard from trade database.

Usage:
    python scripts/dashboard.py                          # Generate and open
    python scripts/dashboard.py --output report.html     # Custom output
    python scripts/dashboard.py --no-open                # Don't auto-open
    python scripts/dashboard.py --db sqlite+aiosqlite:///freebuff.db

The generated HTML uses Chart.js from CDN — no local dependencies needed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import webbrowser
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.storage.models import AccountSnapshot, DailyRisk, SetupLog, Trade


# ─── Data Queries ─────────────────────────────────────────────────────────────

async def query_summary(session: AsyncSession) -> dict:
    """Query overall trading summary."""
    # Total trades
    result = await session.execute(select(func.count(Trade.id)))
    total = result.scalar() or 0

    # Win/loss counts
    result = await session.execute(
        select(
            func.count(Trade.id).filter(Trade.net_profit > 0),
            func.count(Trade.id).filter(Trade.net_profit <= 0),
        )
    )
    row = result.one()
    winners = row[0] or 0
    losers = row[1] or 0

    # P&L
    result = await session.execute(
        select(
            func.sum(Trade.net_profit),
            func.sum(Trade.net_profit).filter(Trade.net_profit > 0),
            func.sum(Trade.net_profit).filter(Trade.net_profit <= 0),
            func.avg(Trade.outcome_r),
        )
    )
    row = result.one()
    total_pnl = float(row[0] or 0)
    total_wins_pnl = float(row[1] or 0)
    total_losses_pnl = float(row[2] or 0)
    avg_r = float(row[3] or 0)

    win_rate = winners / total if total > 0 else 0
    avg_win = total_wins_pnl / winners if winners else 0
    avg_loss = abs(total_losses_pnl / losers) if losers else 0
    profit_factor = total_wins_pnl / abs(total_losses_pnl) if total_losses_pnl else 0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    return {
        "total_trades": total,
        "winners": winners,
        "losers": losers,
        "win_rate": round(win_rate * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "avg_r": round(avg_r, 2),
    }


async def query_equity_curve(session: AsyncSession) -> list[dict]:
    """Query account snapshots for equity curve."""
    result = await session.execute(
        select(AccountSnapshot.ts, AccountSnapshot.equity)
        .order_by(AccountSnapshot.ts)
    )
    return [{"ts": str(row[0]), "equity": float(row[1])} for row in result.all()]


async def query_strategy_performance(session: AsyncSession) -> list[dict]:
    """Query performance breakdown by strategy."""
    result = await session.execute(
        select(
            Trade.comment.label("strategy_id"),
            func.count(Trade.id).label("total"),
            func.count(Trade.id).filter(Trade.net_profit > 0).label("wins"),
            func.sum(Trade.net_profit).label("total_pnl"),
            func.avg(Trade.outcome_r).label("avg_r"),
        )
        .group_by(Trade.comment)
        .order_by(func.sum(Trade.net_profit).desc())
    )

    strategies = []
    for row in result.all():
        sid = row[0] or "unknown"
        total = row[1]
        wins = row[2]
        pnl = float(row[3] or 0)
        avg_r = float(row[4] or 0)
        strategies.append({
            "strategy_id": sid,
            "total": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": round(wins / total * 100, 1) if total else 0,
            "total_pnl": round(pnl, 2),
            "avg_r": round(avg_r, 2),
        })
    return strategies


async def query_session_performance(session: AsyncSession) -> list[dict]:
    """Query performance by session (inferred from strategy comment or time)."""
    result = await session.execute(
        select(
            func.strftime("%H", Trade.open_time).label("hour"),
            func.count(Trade.id).label("total"),
            func.count(Trade.id).filter(Trade.net_profit > 0).label("wins"),
            func.sum(Trade.net_profit).label("total_pnl"),
        )
        .group_by(func.strftime("%H", Trade.open_time))
        .order_by(func.strftime("%H", Trade.open_time))
    )

    sessions = []
    for row in result.all():
        hour = int(row[0] or 0)
        if 7 <= hour < 12:
            session_name = "London AM"
        elif 12 <= hour < 16:
            session_name = "London/NY Overlap"
        elif 16 <= hour < 21:
            session_name = "New York"
        elif hour < 7 or hour >= 21:
            session_name = "Asian"
        else:
            session_name = "Off-hours"

        sessions.append({
            "session": session_name,
            "hour": hour,
            "total": row[1],
            "wins": row[2],
            "total_pnl": round(float(row[3] or 0), 2),
        })
    return sessions


async def query_monthly_pnl(session: AsyncSession) -> list[dict]:
    """Query monthly P&L for heatmap."""
    result = await session.execute(
        select(
            func.strftime("%Y-%m", Trade.open_time).label("month"),
            func.sum(Trade.net_profit).label("pnl"),
            func.count(Trade.id).label("trades"),
        )
        .group_by(func.strftime("%Y-%m", Trade.open_time))
        .order_by(func.strftime("%Y-%m", Trade.open_time))
    )
    return [{"month": row[0], "pnl": round(float(row[1] or 0), 2), "trades": row[2]} for row in result.all()]


async def query_trade_journal(session: AsyncSession, limit: int = 50) -> list[dict]:
    """Query recent trades for journal table."""
    result = await session.execute(
        select(Trade)
        .order_by(Trade.open_time.desc())
        .limit(limit)
    )
    trades = []
    for t in result.scalars().all():
        trades.append({
            "id": t.id,
            "direction": t.direction,
            "symbol": t.symbol,
            "volume": float(t.volume),
            "entry": float(t.entry_price),
            "sl": float(t.sl),
            "tp1": float(t.tp1),
            "exit_price": float(t.exit_price) if t.exit_price else 0,
            "pnl": float(t.net_profit),
            "r_multiple": float(t.outcome_r) if t.outcome_r else 0,
            "pips": float(t.outcome_pips) if t.outcome_pips else 0,
            "strategy": t.comment or "unknown",
            "open_time": str(t.open_time)[:16],
            "exit_time": str(t.exit_time)[:16] if t.exit_time else "",
        })
    return trades


async def query_setup_analysis(session: AsyncSession) -> dict:
    """Query setup decision breakdown."""
    result = await session.execute(
        select(
            SetupLog.decision,
            func.count(SetupLog.id).label("count"),
        )
        .group_by(SetupLog.decision)
    )
    breakdown = {row[0]: row[1] for row in result.all()}

    # Win rate of traded setups
    result = await session.execute(
        select(
            SetupLog.strategy_id,
            func.count(SetupLog.id).label("total"),
            func.count(SetupLog.id).filter(SetupLog.decision == "TRADED").label("traded"),
            func.avg(SetupLog.ai_score).label("avg_ai_score"),
        )
        .group_by(SetupLog.strategy_id)
    )
    strategy_setups = []
    for row in result.all():
        strategy_setups.append({
            "strategy": row[0],
            "total": row[1],
            "traded": row[2],
            "trade_rate": round(row[2] / row[1] * 100, 1) if row[1] else 0,
            "avg_ai_score": round(float(row[3] or 0), 1),
        })

    return {"breakdown": breakdown, "by_strategy": strategy_setups}


# ─── HTML Template ────────────────────────────────────────────────────────────

def generate_html(
    summary: dict,
    equity_curve: list[dict],
    strategies: list[dict],
    sessions: list[dict],
    monthly: list[dict],
    trades: list[dict],
    setup_analysis: dict,
) -> str:
    """Generate self-contained HTML dashboard."""

    # Prepare chart data
    eq_labels = json.dumps([e["ts"][:10] for e in equity_curve])
    eq_data = json.dumps([e["equity"] for e in equity_curve])

    strat_names = json.dumps([s["strategy_id"] for s in strategies])
    strat_winrates = json.dumps([s["win_rate"] for s in strategies])
    strat_pnl = json.dumps([s["total_pnl"] for s in strategies])
    strat_trades = json.dumps([s["total"] for s in strategies])

    sess_names = json.dumps(list(set(s["session"] for s in sessions)))
    sess_pnl_data = {}
    for s in sessions:
        sess_pnl_data.setdefault(s["session"], 0)
        sess_pnl_data[s["session"]] += s["total_pnl"]
    sess_pnl = json.dumps([round(sess_pnl_data.get(n, 0), 2) for n in json.loads(sess_names)])

    month_labels = json.dumps([m["month"] for m in monthly])
    month_pnl = json.dumps([m["pnl"] for m in monthly])
    month_colors = json.dumps(["#22c55e" if m["pnl"] >= 0 else "#ef4444" for m in monthly])

    setup_labels = json.dumps(list(setup_analysis["breakdown"].keys()))
    setup_counts = json.dumps(list(setup_analysis["breakdown"].values()))

    # Trade journal rows
    trade_rows = ""
    for t in trades:
        pnl_class = "positive" if t["pnl"] >= 0 else "negative"
        dir_class = "buy" if t["direction"] == "BUY" else "sell"
        trade_rows += f"""
        <tr>
            <td>{t['open_time']}</td>
            <td><span class="badge {dir_class}">{t['direction']}</span></td>
            <td>{t['symbol']}</td>
            <td>{t['volume']}</td>
            <td>{t['entry']:.2f}</td>
            <td>{t['sl']:.2f}</td>
            <td>{t['tp1']:.2f}</td>
            <td>{t['exit_price']:.2f}</td>
            <td class="{pnl_class}">${t['pnl']:.2f}</td>
            <td class="{pnl_class}">{t['r_multiple']:.1f}R</td>
            <td>{t['pips']:.1f}</td>
            <td>{t['strategy']}</td>
            <td>{t['exit_time']}</td>
        </tr>"""

    # Max drawdown calculation
    max_dd = 0
    peak = equity_curve[0]["equity"] if equity_curve else 10000
    for e in equity_curve:
        if e["equity"] > peak:
            peak = e["equity"]
        dd = (peak - e["equity"]) / peak * 100
        if dd > max_dd:
            max_dd = dd

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Freebuff Trading Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 20px;
        }}
        .header {{
            text-align: center;
            padding: 20px 0 30px;
        }}
        .header h1 {{
            font-size: 28px;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .header .subtitle {{ color: #64748b; margin-top: 5px; }}

        /* Summary Cards */
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }}
        .card {{
            background: #1e293b;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #334155;
        }}
        .card .label {{ color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }}
        .card .value {{ font-size: 28px; font-weight: 700; margin-top: 8px; }}
        .card .sub {{ color: #64748b; font-size: 13px; margin-top: 4px; }}
        .positive {{ color: #22c55e; }}
        .negative {{ color: #ef4444; }}

        /* Charts Grid */
        .charts {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        .chart-box {{
            background: #1e293b;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #334155;
        }}
        .chart-box.full {{ grid-column: 1 / -1; }}
        .chart-box h3 {{
            color: #94a3b8;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
        }}
        .chart-box canvas {{ max-height: 300px; }}

        /* Table */
        .table-box {{
            background: #1e293b;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #334155;
            overflow-x: auto;
            margin-bottom: 30px;
        }}
        .table-box h3 {{
            color: #94a3b8;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th {{
            text-align: left;
            padding: 10px 12px;
            border-bottom: 2px solid #334155;
            color: #94a3b8;
            font-weight: 600;
            white-space: nowrap;
        }}
        td {{
            padding: 8px 12px;
            border-bottom: 1px solid #1e293b;
            white-space: nowrap;
        }}
        tr:hover {{ background: #334155; }}
        .badge {{
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}
        .badge.buy {{ background: #166534; color: #bbf7d0; }}
        .badge.sell {{ background: #991b1b; color: #fecaca; }}

        /* Strategy Table */
        .strat-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }}
        .strat-card {{
            background: #1e293b;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #334155;
        }}
        .strat-card h4 {{ color: #e2e8f0; margin-bottom: 12px; }}
        .strat-card .metric {{
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            border-bottom: 1px solid #334155;
        }}
        .strat-card .metric:last-child {{ border: none; }}
        .strat-card .metric .label {{ color: #94a3b8; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏦 Freebuff Trading Dashboard</h1>
        <div class="subtitle">XAUUSD &bull; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
    </div>

    <!-- Summary Cards -->
    <div class="cards">
        <div class="card">
            <div class="label">Total Trades</div>
            <div class="value">{summary['total_trades']}</div>
            <div class="sub">{summary['winners']}W / {summary['losers']}L</div>
        </div>
        <div class="card">
            <div class="label">Win Rate</div>
            <div class="value {'positive' if summary['win_rate'] >= 50 else 'negative'}">{summary['win_rate']}%</div>
            <div class="sub">Target: &gt;50%</div>
        </div>
        <div class="card">
            <div class="label">Total P&amp;L</div>
            <div class="value {'positive' if summary['total_pnl'] >= 0 else 'negative'}">${summary['total_pnl']:,.2f}</div>
            <div class="sub">Avg R: {summary['avg_r']:.2f}</div>
        </div>
        <div class="card">
            <div class="label">Max Drawdown</div>
            <div class="value negative">{max_dd:.1f}%</div>
            <div class="sub">Emergency: 5%</div>
        </div>
        <div class="card">
            <div class="label">Profit Factor</div>
            <div class="value {'positive' if summary['profit_factor'] >= 1.5 else 'negative'}">{summary['profit_factor']}</div>
            <div class="sub">Target: &gt;1.5</div>
        </div>
        <div class="card">
            <div class="label">Expectancy</div>
            <div class="value {'positive' if summary['expectancy'] >= 0 else 'negative'}">${summary['expectancy']:,.2f}</div>
            <div class="sub">Per trade avg</div>
        </div>
        <div class="card">
            <div class="label">Avg Win</div>
            <div class="value positive">${summary['avg_win']:,.2f}</div>
        </div>
        <div class="card">
            <div class="label">Avg Loss</div>
            <div class="value negative">${summary['avg_loss']:,.2f}</div>
        </div>
    </div>

    <!-- Charts -->
    <div class="charts">
        <div class="chart-box full">
            <h3>📈 Equity Curve</h3>
            <canvas id="equityChart"></canvas>
        </div>
        <div class="chart-box">
            <h3>🎯 Strategy Performance (Win Rate)</h3>
            <canvas id="strategyChart"></canvas>
        </div>
        <div class="chart-box">
            <h3>💰 Strategy P&amp;L</h3>
            <canvas id="strategyPnlChart"></canvas>
        </div>
        <div class="chart-box">
            <h3>🕐 Session Performance</h3>
            <canvas id="sessionChart"></canvas>
        </div>
        <div class="chart-box">
            <h3>📊 Monthly P&amp;L</h3>
            <canvas id="monthlyChart"></canvas>
        </div>
        <div class="chart-box">
            <h3>🔍 Setup Analysis</h3>
            <canvas id="setupChart"></canvas>
        </div>
    </div>

    <!-- Strategy Detail Cards -->
    <div class="strat-grid">
        {"".join(f'''
        <div class="strat-card">
            <h4>{s["strategy_id"]}</h4>
            <div class="metric"><span class="label">Trades</span><span>{s["total"]}</span></div>
            <div class="metric"><span class="label">Win Rate</span><span class="{"positive" if s["win_rate"] >= 50 else "negative"}">{s["win_rate"]}%</span></div>
            <div class="metric"><span class="label">P&amp;L</span><span class="{"positive" if s["total_pnl"] >= 0 else "negative"}">${s["total_pnl"]:,.2f}</span></div>
            <div class="metric"><span class="label">Avg R</span><span>{s["avg_r"]:.2f}</span></div>
        </div>''' for s in strategies)}
    </div>

    <!-- Trade Journal -->
    <div class="table-box">
        <h3>📋 Trade Journal (Last 50)</h3>
        <table>
            <thead>
                <tr>
                    <th>Open Time</th>
                    <th>Dir</th>
                    <th>Symbol</th>
                    <th>Vol</th>
                    <th>Entry</th>
                    <th>SL</th>
                    <th>TP1</th>
                    <th>Exit</th>
                    <th>P&amp;L</th>
                    <th>R-Multiple</th>
                    <th>Pips</th>
                    <th>Strategy</th>
                    <th>Exit Time</th>
                </tr>
            </thead>
            <tbody>
                {trade_rows}
            </tbody>
        </table>
    </div>

    <script>
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.borderColor = '#334155';

        // Equity Curve
        new Chart(document.getElementById('equityChart'), {{
            type: 'line',
            data: {{
                labels: {eq_labels},
                datasets: [{{
                    label: 'Equity',
                    data: {eq_data},
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 2,
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ display: true, ticks: {{ maxTicksLimit: 10 }} }},
                    y: {{ ticks: {{ callback: v => '$' + v.toLocaleString() }} }}
                }}
            }}
        }});

        // Strategy Win Rate
        new Chart(document.getElementById('strategyChart'), {{
            type: 'bar',
            data: {{
                labels: {strat_names},
                datasets: [{{
                    label: 'Win Rate %',
                    data: {strat_winrates},
                    backgroundColor: {strat_winrates}.map(v => v >= 50 ? '#22c55e' : '#ef4444'),
                    borderRadius: 6,
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ y: {{ beginAtZero: true, max: 100, ticks: {{ callback: v => v + '%' }} }} }}
            }}
        }});

        // Strategy P&L
        new Chart(document.getElementById('strategyPnlChart'), {{
            type: 'bar',
            data: {{
                labels: {strat_names},
                datasets: [{{
                    label: 'P&L ($)',
                    data: {strat_pnl},
                    backgroundColor: {strat_pnl}.map(v => v >= 0 ? '#22c55e' : '#ef4444'),
                    borderRadius: 6,
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ y: {{ ticks: {{ callback: v => '$' + v.toLocaleString() }} }} }}
            }}
        }});

        // Session Performance
        new Chart(document.getElementById('sessionChart'), {{
            type: 'bar',
            data: {{
                labels: {sess_names},
                datasets: [{{
                    label: 'P&L ($)',
                    data: {sess_pnl},
                    backgroundColor: {sess_pnl}.map(v => v >= 0 ? '#22c55e' : '#ef4444'),
                    borderRadius: 6,
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ y: {{ ticks: {{ callback: v => '$' + v.toLocaleString() }} }} }}
            }}
        }});

        // Monthly P&L
        new Chart(document.getElementById('monthlyChart'), {{
            type: 'bar',
            data: {{
                labels: {month_labels},
                datasets: [{{
                    label: 'Monthly P&L',
                    data: {month_pnl},
                    backgroundColor: {month_colors},
                    borderRadius: 6,
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ y: {{ ticks: {{ callback: v => '$' + v.toLocaleString() }} }} }}
            }}
        }});

        // Setup Analysis Doughnut
        new Chart(document.getElementById('setupChart'), {{
            type: 'doughnut',
            data: {{
                labels: {setup_labels},
                datasets: [{{
                    data: {setup_counts},
                    backgroundColor: ['#22c55e', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6'],
                    borderWidth: 0,
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ position: 'bottom' }}
                }}
            }}
        }});
    </script>
</body>
</html>"""


# ─── Main ─────────────────────────────────────────────────────────────────────

async def generate_dashboard(db_url: str, output_path: str):
    """Query database and generate HTML dashboard."""
    engine = create_async_engine(db_url, echo=False)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        summary = await query_summary(session)
        equity_curve = await query_equity_curve(session)
        strategies = await query_strategy_performance(session)
        sessions = await query_session_performance(session)
        monthly = await query_monthly_pnl(session)
        trades = await query_trade_journal(session, limit=50)
        setup_analysis = await query_setup_analysis(session)

    html = generate_html(
        summary=summary,
        equity_curve=equity_curve,
        strategies=strategies,
        sessions=sessions,
        monthly=monthly,
        trades=trades,
        setup_analysis=setup_analysis,
    )

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Dashboard generated: {output_path}")
    print(f"Summary: {summary['total_trades']} trades, {summary['win_rate']}% win rate, ${summary['total_pnl']:,.2f} P&L")

    await engine.dispose()
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate trading dashboard")
    parser.add_argument("--output", default="dashboard.html", help="Output HTML file")
    parser.add_argument("--db", default="sqlite+aiosqlite:///freebuff.db", help="Database URL")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open in browser")
    args = parser.parse_args()

    output_path = asyncio.run(generate_dashboard(args.db, args.output))

    if not args.no_open:
        webbrowser.open(f"file://{os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
