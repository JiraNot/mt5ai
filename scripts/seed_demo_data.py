"""Seed realistic demo trade data into the database for dashboard visualization.

Usage:
    python scripts/seed_demo_data.py              # Seed with defaults
    python scripts/seed_demo_data.py --trades 200 # Seed 200 trades
    python scripts/seed_demo_data.py --clear       # Clear existing data first
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.storage.models import (
    AccountSnapshot,
    Base,
    DailyRisk,
    SetupLog,
    Trade,
)


STRATEGIES = [
    {"id": "choch_orderblock", "name": "CHoCH + Order Block", "weight": 40},
    {"id": "fvg_reversal", "name": "FVG Reversal", "weight": 35},
    {"id": "breakout_retest", "name": "Breakout Retest", "weight": 25},
]

SYMBOLS = ["XAUUSD"]
TIMEFRAMES = ["M5", "M15", "H1"]
SESSIONS = ["london", "new_york", "overlap", "london", "new_york"]  # Weighted toward active sessions


def pick_strategy() -> dict:
    total = sum(s["weight"] for s in STRATEGIES)
    r = random.uniform(0, total)
    cumulative = 0
    for s in STRATEGIES:
        cumulative += s["weight"]
        if r <= cumulative:
            return s
    return STRATEGIES[-1]


def generate_trade_series(
    num_trades: int,
    start_date: datetime,
    win_rate: float = 0.55,
    avg_win_r: float = 2.2,
    avg_loss_r: float = 1.0,
) -> list[dict]:
    """Generate a realistic series of trades with equity curve."""
    trades = []
    equity = 10000.0
    equity_curve = [{"ts": start_date, "equity": equity}]
    current_date = start_date

    for i in range(num_trades):
        # Advance time by 2-8 hours (skip weekends)
        current_date += timedelta(hours=random.randint(2, 8))
        while current_date.weekday() >= 5:  # Skip weekends
            current_date += timedelta(days=1)
        current_date += timedelta(hours=random.randint(0, 4))

        strategy = pick_strategy()
        direction = random.choice(["BUY", "SELL"])

        # Entry price
        base_price = 2030.0 + random.uniform(-50, 50)
        sl_distance = random.uniform(3.0, 8.0)
        rr_ratio = random.uniform(1.5, 4.0)

        if direction == "BUY":
            entry = round(base_price, 2)
            sl = round(entry - sl_distance, 2)
            tp1 = round(entry + sl_distance * rr_ratio, 2)
            tp2 = round(entry + sl_distance * (rr_ratio + 1), 2)
        else:
            entry = round(base_price, 2)
            sl = round(entry + sl_distance, 2)
            tp1 = round(entry - sl_distance * rr_ratio, 2)
            tp2 = round(entry - sl_distance * (rr_ratio + 1), 2)

        # Determine outcome
        is_win = random.random() < win_rate
        if is_win:
            r_multiple = random.uniform(1.0, avg_win_r * 1.5)
            exit_price = tp1 if random.random() > 0.3 else entry + (tp1 - entry) * random.uniform(0.5, 1.0)
            if direction == "SELL":
                exit_price = tp1 if random.random() > 0.3 else entry - (entry - tp1) * random.uniform(0.5, 1.0)
            profit = round(random.uniform(50, 300), 2)
        else:
            r_multiple = -random.uniform(0.3, 1.2)
            exit_price = sl if random.random() > 0.4 else entry - (entry - sl) * random.uniform(0.3, 1.0)
            if direction == "SELL":
                exit_price = sl if random.random() > 0.4 else entry + (sl - entry) * random.uniform(0.3, 1.0)
            profit = round(random.uniform(-200, -30), 2)

        commission = round(random.uniform(3.5, 7.0), 2)
        net_profit = round(profit - commission, 2)
        equity += net_profit

        session = random.choice(SESSIONS)
        rr_ratio_calc = abs(tp1 - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0

        # AI score correlates with outcome (better setups tend to win more)
        rule_score = random.randint(50, 95)
        ai_score = rule_score + random.randint(-10, 15)
        ai_score = max(0, min(100, ai_score))

        confluences = []
        if random.random() > 0.3:
            confluences.append("choch_confirmed")
        if random.random() > 0.4:
            confluences.append("liquidity_sweep")
        if random.random() > 0.5:
            confluences.append("fvg_present")
        if random.random() > 0.6:
            confluences.append("htf_aligned")
        if random.random() > 0.7:
            confluences.append("ob_fvg_overlap")

        outcome_pips = round((exit_price - entry) * (1 if direction == "BUY" else -1) * 10, 1)

        trades.append({
            "symbol": "XAUUSD",
            "direction": direction,
            "volume": round(random.uniform(0.05, 0.30), 2),
            "entry_price": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "exit_price": round(exit_price, 2),
            "exit_time": current_date + timedelta(minutes=random.randint(15, 480)),
            "open_time": current_date,
            "profit": profit,
            "commission": commission,
            "net_profit": net_profit,
            "outcome_r": round(r_multiple, 2),
            "outcome_pips": outcome_pips,
            "status": "CLOSED",
            "strategy_id": strategy["id"],
            "strategy_name": strategy["name"],
            "timeframe": random.choice(TIMEFRAMES),
            "session": session,
            "rule_score": rule_score,
            "ai_score": ai_score,
            "combined_score": max(rule_score, ai_score),
            "rr_ratio": round(rr_ratio_calc, 2),
            "confluences": confluences,
        })

        equity_curve.append({"ts": current_date, "equity": round(equity, 2)})

    return trades, equity_curve


async def seed_database(db_url: str, num_trades: int = 100, clear: bool = False):
    """Seed the database with demo trade data."""
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        if clear:
            await session.execute(delete(Trade))
            await session.execute(delete(SetupLog))
            await session.execute(delete(DailyRisk))
            await session.execute(delete(AccountSnapshot))
            await session.commit()
            print(f"Cleared existing data")

        # Generate trades
        start_date = datetime(2024, 6, 1)
        trades, equity_curve = generate_trade_series(num_trades, start_date)

        # Insert trades + setups
        daily_pnl: dict[str, float] = {}
        daily_trades: dict[str, int] = {}
        daily_wins: dict[str, int] = {}
        daily_losses: dict[str, int] = {}

        for t in trades:
            # Insert setup
            setup = SetupLog(
                symbol=t["symbol"],
                timeframe=t["timeframe"],
                strategy_id=t["strategy_id"],
                direction=t["direction"],
                rule_score=t["rule_score"],
                ai_score=t["ai_score"],
                combined_score=t["combined_score"],
                decision="TRADED",
                entry_price=t["entry_price"],
                stop_loss=t["sl"],
                take_profit_1=t["tp1"],
                take_profit_2=t["tp2"],
                rr_ratio=t["rr_ratio"],
                confluences=json.dumps(t["confluences"]),
                outcome_r=t["outcome_r"],
                outcome_pips=t["outcome_pips"],
                created_at=t["open_time"],
            )
            session.add(setup)
            await session.flush()  # Get setup.id

            # Insert trade
            trade = Trade(
                setup_id=setup.id,
                symbol=t["symbol"],
                direction=t["direction"],
                volume=t["volume"],
                entry_price=t["entry_price"],
                sl=t["sl"],
                tp1=t["tp1"],
                tp2=t["tp2"],
                exit_price=t["exit_price"],
                exit_time=t["exit_time"],
                profit=t["profit"],
                commission=t["commission"],
                net_profit=t["net_profit"],
                outcome_r=t["outcome_r"],
                outcome_pips=t["outcome_pips"],
                status="CLOSED",
                open_time=t["open_time"],
                magic=20240101,
                comment=t["strategy_id"],
            )
            session.add(trade)

            # Track daily stats
            day_key = t["open_time"].strftime("%Y-%m-%d")
            daily_pnl[day_key] = daily_pnl.get(day_key, 0) + t["net_profit"]
            daily_trades[day_key] = daily_trades.get(day_key, 0) + 1
            if t["net_profit"] > 0:
                daily_wins[day_key] = daily_wins.get(day_key, 0) + 1
            else:
                daily_losses[day_key] = daily_losses.get(day_key, 0) + 1

        # Insert daily risk records
        for day_key in sorted(daily_pnl.keys()):
            dr = DailyRisk(
                trade_date=datetime.strptime(day_key, "%Y-%m-%d"),
                total_pnl=round(daily_pnl[day_key], 2),
                total_trades=daily_trades[day_key],
                winning_trades=daily_wins.get(day_key, 0),
                losing_trades=daily_losses.get(day_key, 0),
                max_drawdown=0,
                circuit_breaker=False,
            )
            session.add(dr)

        # Insert account snapshots
        equity = 10000.0
        for ec in equity_curve:
            snap = AccountSnapshot(
                ts=ec["ts"],
                balance=ec["equity"],
                equity=ec["equity"],
                open_positions=0,
                daily_pnl=0,
            )
            session.add(snap)

        # Also add some SKIPPED and REJECTED setups for setup analysis
        for i in range(num_trades // 3):
            strategy = pick_strategy()
            skip_date = start_date + timedelta(days=random.randint(0, 120), hours=random.randint(0, 23))
            setup = SetupLog(
                symbol="XAUUSD",
                timeframe=random.choice(TIMEFRAMES),
                strategy_id=strategy["id"],
                direction=random.choice(["BUY", "SELL"]),
                rule_score=random.randint(20, 65),
                ai_score=random.randint(15, 55),
                combined_score=random.randint(15, 55),
                decision=random.choice(["SKIPPED", "REJECTED"]),
                entry_price=round(2030 + random.uniform(-50, 50), 2),
                stop_loss=round(2025 + random.uniform(-5, 5), 2),
                take_profit_1=round(2040 + random.uniform(-10, 10), 2),
                rr_ratio=round(random.uniform(0.5, 2.5), 2),
                confluences=json.dumps([]),
                rejection_reason=random.choice([
                    "AI score below threshold",
                    "HTF conflict",
                    "RR too low",
                    "Spread too wide",
                    "Asian session",
                ]),
                created_at=skip_date,
            )
            session.add(setup)

        await session.commit()
        print(f"Seeded {num_trades} trades + {num_trades // 3} skipped/rejected setups")
        print(f"Equity: $10,000 -> ${equity_curve[-1]['equity']:.2f}")
        print(f"Date range: {start_date.date()} -> {trades[-1]['open_time'].date()}")

    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Seed demo trade data")
    parser.add_argument("--trades", type=int, default=100, help="Number of trades to generate")
    parser.add_argument("--clear", action="store_true", help="Clear existing data first")
    parser.add_argument("--db", type=str, default="sqlite+aiosqlite:///freebuff.db", help="Database URL")
    args = parser.parse_args()

    asyncio.run(seed_database(args.db, args.trades, args.clear))


if __name__ == "__main__":
    main()
