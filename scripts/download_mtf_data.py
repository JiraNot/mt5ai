"""Download multi-timeframe gold data for proper structure analysis.

Downloads hourly and 4-hour data to enable proper trend detection
across different timeframes.

Usage:
    python scripts/download_mtf_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))


def download_mtf_data():
    """Download multi-timeframe gold data."""
    print("[DOWNLOAD] Multi-timeframe gold data...")

    # Download different intervals
    intervals = {
        "1h": "60m",   # Hourly data
        "1d": "1d",    # Daily data
    }

    data = {}

    for name, interval in intervals.items():
        print(f"  Downloading {name} data...")
        gold = yf.Ticker("GC=F")

        # For hourly data, we can get up to 730 days
        if interval == "60m":
            df = gold.history(period="2y", interval=interval)
        else:
            df = gold.history(period="2y", interval=interval)

        data[name] = df
        print(f"    {name}: {len(df)} candles")

    # Save to CSV for later use
    for name, df in data.items():
        filename = f"gold_{name}.csv"
        df.to_csv(filename)
        print(f"  Saved: {filename}")

    # Show summary
    print("\n[SUMMARY]")
    print(f"  Hourly candles: {len(data['1h'])}")
    print(f"  Daily candles: {len(data['1d'])}")

    if not data["1h"].empty:
        print(f"  Hourly range: {data['1h'].index[0]} to {data['1h'].index[-1]}")
    if not data["1d"].empty:
        print(f"  Daily range: {data['1d'].index[0]} to {data['1d'].index[-1]}")

    return data


if __name__ == "__main__":
    download_mtf_data()
