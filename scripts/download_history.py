#!/usr/bin/env python3
"""
Download historical OHLCV data from MT5 and store in database.

Usage:
    python scripts/download_history.py                          # XAUUSD, all TFs, last 6 months
    python scripts/download_history.py --symbol XAUUSD --months 12
    python scripts/download_history.py --timeframes M5 H1 --start 2024-01-01
    python scripts/download_history.py --symbol XAUUSD --start 2024-06-01 --end 2024-12-31
    python scripts/download_history.py --mock                   # Generate mock data (no MT5 needed)

The script:
    1. Connects to MT5 (or generates mock data)
    2. Downloads OHLCV candles in batches
    3. Stores in the ohlcv table (SQLite or PostgreSQL)
    4. Skips duplicates (same symbol + timeframe + timestamp)
    5. Shows progress with candle counts per timeframe
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.types import Candle
from src.storage.models import Base, get_engine, get_session_factory

# Use print for user-facing output (structlog may not be configured)
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_SYMBOLS = ["XAUUSD"]
DEFAULT_TIMEFRAMES = ["M5", "M15", "H1", "H4"]
BATCH_SIZE = 5000  # Max candles per MT5 request
INSERT_BATCH_SIZE = 1000  # Rows per INSERT


# ─── Database Setup ───────────────────────────────────────────────────────────

async def ensure_tables(engine) -> None:
    """Create tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")


async def get_existing_range(
    session: AsyncSession, symbol: str, timeframe: str
) -> tuple[datetime | None, datetime | None]:
    """Get the earliest and latest timestamps already in the database."""
    result = await session.execute(
        text(
            "SELECT MIN(ts), MAX(ts) FROM ohlcv "
            "WHERE symbol = :symbol AND timeframe = :tf"
        ),
        {"symbol": symbol, "tf": timeframe},
    )
    row = result.fetchone()
    return row[0], row[1]


async def count_candles(
    session: AsyncSession, symbol: str, timeframe: str
) -> int:
    """Count existing candles for a symbol/timeframe."""
    result = await session.execute(
        text(
            "SELECT COUNT(*) FROM ohlcv "
            "WHERE symbol = :symbol AND timeframe = :tf"
        ),
        {"symbol": symbol, "tf": timeframe},
    )
    return result.scalar() or 0


async def insert_candles(
    session: AsyncSession, candles: list[Candle], symbol: str, timeframe: str
) -> int:
    """
    Insert candles into the database, skipping duplicates.
    Returns the number of new rows inserted.
    """
    if not candles:
        return 0

    # Check for existing timestamps to avoid duplicates
    timestamps = [c.timestamp for c in candles]
    existing_ts = set()
    # Query in small batches to avoid SQLite IN limit
    batch_size = 100
    for i in range(0, len(timestamps), batch_size):
        batch = timestamps[i:i + batch_size]
        placeholders = ",".join([f":ts{j}" for j in range(len(batch))])
        params = {f"ts{j}": t for j, t in enumerate(batch)}
        params["symbol"] = symbol
        params["tf"] = timeframe
        result = await session.execute(
            text(
                f"SELECT ts FROM ohlcv "
                f"WHERE symbol = :symbol AND timeframe = :tf AND ts IN ({placeholders})"
            ),
            params,
        )
        existing_ts.update(row[0] for row in result.fetchall())

    # Filter out duplicates
    new_candles = [c for c in candles if c.timestamp not in existing_ts]

    if not new_candles:
        return 0

    # Batch insert
    inserted = 0
    for i in range(0, len(new_candles), INSERT_BATCH_SIZE):
        batch = new_candles[i : i + INSERT_BATCH_SIZE]
        rows = [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "ts": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in batch
        ]
        await session.execute(
            text(
                "INSERT INTO ohlcv (symbol, timeframe, ts, open, high, low, close, volume) "
                "VALUES (:symbol, :timeframe, :ts, :open, :high, :low, :close, :volume)"
            ),
            rows,
        )
        inserted += len(batch)

    await session.commit()
    return inserted


# ─── MT5 Download ─────────────────────────────────────────────────────────────

async def download_from_mt5(
    mt5: MT5Connection,
    session: AsyncSession,
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
) -> int:
    """
    Download OHLCV data from MT5 and store in database.

    Uses copy_rates_from for date-range based fetching.
    Downloads in batches to handle large date ranges.
    """
    logger.info(f"Downloading {symbol} {timeframe} from {start_date} to {end_date}")

    # MT5 timeframe mapping
    import MetaTrader5 as m5

    tf_map = {
        "M1": m5.TIMEFRAME_M1,
        "M5": m5.TIMEFRAME_M5,
        "M15": m5.TIMEFRAME_M15,
        "H1": m5.TIMEFRAME_H1,
        "H4": m5.TIMEFRAME_H4,
        "D1": m5.TIMEFRAME_D1,
    }

    if timeframe not in tf_map:
        logger.error(f"Unsupported timeframe: {timeframe}")
        return 0

    mt5_tf = tf_map[timeframe]
    total_inserted = 0
    current_start = start_date

    while current_start < end_date:
        # Fetch batch from MT5
        rates = m5.copy_rates_from(symbol, mt5_tf, current_start, BATCH_SIZE)

        if rates is None or len(rates) == 0:
            logger.debug(f"No more data from {current_start}")
            break

        # Convert to Candle objects
        candles = []
        for rate in rates:
            ts = datetime.fromtimestamp(rate["time"])
            if ts > end_date:
                break
            if ts >= current_start:
                candles.append(
                    Candle(
                        timestamp=ts,
                        open=rate["open"],
                        high=rate["high"],
                        low=rate["low"],
                        close=rate["close"],
                        volume=rate["tick_volume"],
                    )
                )

        if not candles:
            break

        # Insert into database
        inserted = await insert_candles(session, candles, symbol, timeframe)
        total_inserted += inserted

        # Move start forward
        last_ts = candles[-1].timestamp
        if last_ts <= current_start:
            # No progress — break to avoid infinite loop
            break
        current_start = last_ts + timedelta(seconds=1)

        # Progress
        pct = min(100, (current_start - start_date).total_seconds() /
                  max(1, (end_date - start_date).total_seconds()) * 100)
        logger.info(
            f"  {symbol} {timeframe}: {total_inserted} new candles "
            f"({pct:.0f}%) — last: {current_start.strftime('%Y-%m-%d %H:%M')}"
        )

    return total_inserted


# ─── Mock Data Generation ────────────────────────────────────────────────────

async def generate_mock_data(
    session: AsyncSession,
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
) -> int:
    """Generate realistic mock OHLCV data for testing without MT5."""
    import random

    logger.info(f"Generating mock data for {symbol} {timeframe}")

    # Timeframe delta
    tf_delta = {
        "M1": timedelta(minutes=1),
        "M5": timedelta(minutes=5),
        "M15": timedelta(minutes=15),
        "H1": timedelta(hours=1),
        "H4": timedelta(hours=4),
        "D1": timedelta(days=1),
    }
    delta = tf_delta.get(timeframe, timedelta(hours=1))

    # Generate candles with random walk
    candles = []
    current_time = start_date
    price = 2000.0 if "XAU" in symbol else 1.1000
    random.seed(42)  # Reproducible

    while current_time < end_date:
        # Skip weekends for daily TFs
        if timeframe in ("D1", "H4") and current_time.weekday() >= 5:
            current_time += delta
            continue

        # Random walk
        change = random.gauss(0, 0.001) * price
        open_ = price
        close = price + change
        high = max(open_, close) + abs(random.gauss(0, 0.0005)) * price
        low = min(open_, close) - abs(random.gauss(0, 0.0005)) * price
        volume = random.randint(100, 5000)

        candles.append(
            Candle(
                timestamp=current_time,
                open=round(open_, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                volume=volume,
            )
        )

        price = close
        current_time += delta

    # Insert in batches
    inserted = await insert_candles(session, candles, symbol, timeframe)
    logger.info(f"  {symbol} {timeframe}: {inserted} mock candles generated")
    return inserted


# ─── Main ─────────────────────────────────────────────────────────────────────

async def run_download(args) -> None:
    """Main download orchestrator."""
    # Determine date range
    if args.start:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start_date = datetime.now() - timedelta(days=args.months * 30)

    if args.end:
        end_date = datetime.strptime(args.end, "%Y-%m-%d")
    else:
        end_date = datetime.now()

    symbols = args.symbols or DEFAULT_SYMBOLS
    timeframes = args.timeframes or DEFAULT_TIMEFRAMES

    print("=" * 60)
    print("Freebuff Historical Data Downloader")
    print("=" * 60)
    print(f"Symbols:    {symbols}")
    print(f"Timeframes: {timeframes}")
    print(f"Start:      {start_date.strftime('%Y-%m-%d')}")
    print(f"End:        {end_date.strftime('%Y-%m-%d')}")
    print(f"Mode:       {'MOCK' if args.mock else 'MT5'}")
    print("=" * 60)

    # Database setup
    db_url = settings.database_url
    if "sqlite" in db_url:
        Path("data").mkdir(exist_ok=True)

    engine = get_engine(db_url)
    await ensure_tables(engine)
    session_factory = get_session_factory(engine)

    # MT5 connection (if not mock)
    mt5 = None
    if not args.mock:
        from src.market.mt5_connection import MT5Connection
        mt5 = MT5Connection()
        connected = await mt5.connect()
        if not connected:
            print("ERROR: Failed to connect to MT5. Use --mock for mock data.")
            return

    total_candles = 0
    start_time = time.time()

    try:
        async with session_factory() as session:
            for symbol in symbols:
                for tf in timeframes:
                    print(f"\n--- {symbol} {tf} ---")

                    existing = await count_candles(session, symbol, tf)
                    if existing > 0:
                        min_ts, max_ts = await get_existing_range(session, symbol, tf)
                        print(f"  Existing: {existing} candles ({min_ts} to {max_ts})")

                    if args.mock:
                        inserted = await generate_mock_data(
                            session, symbol, tf, start_date, end_date
                        )
                    else:
                        inserted = await download_from_mt5(
                            mt5, session, symbol, tf, start_date, end_date
                        )

                    total_candles += inserted
                    final_count = await count_candles(session, symbol, tf)
                    print(f"  Total in DB: {final_count} candles")

    finally:
        if mt5:
            await mt5.disconnect()
        await engine.dispose()

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"Download complete!")
    print(f"New candles:  {total_candles:,}")
    print(f"Time elapsed: {elapsed:.1f}s")
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download historical OHLCV data from MT5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/download_history.py                              # Default: XAUUSD, all TFs, 6 months
  python scripts/download_history.py --symbols XAUUSD --months 12 # 12 months of XAUUSD
  python scripts/download_history.py --timeframes M5 H1           # Only M5 and H1
  python scripts/download_history.py --start 2024-01-01 --end 2024-06-30
  python scripts/download_history.py --mock                       # Mock data (no MT5)
        """,
    )
    parser.add_argument("--symbols", nargs="+", default=None, help="Symbols to download")
    parser.add_argument("--timeframes", nargs="+", default=None, help="Timeframes to download")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--months", type=int, default=6, help="Months of history (default: 6)")
    parser.add_argument("--mock", action="store_true", help="Generate mock data (no MT5)")
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    asyncio.run(run_download(args))


if __name__ == "__main__":
    main()
