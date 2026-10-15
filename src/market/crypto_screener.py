"""Crypto Market Screener & Homework Engine.

Scans Binance USDT-M Futures for top volume, high volatility, and trending
pairs to generate a curated daily/session Watchlist for the trading agent.

Usage:
    python -m src.market.crypto_screener
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.market.binance_gateway import BinanceGateway
from src.market.btc_regime import BTCRegimeAnalyzer, BTCRegimeReport

logger = logging.getLogger(__name__)


@dataclass
class CryptoCandidate:
    """A scored cryptocurrency candidate from 24h market screening."""

    symbol: str
    price: float
    price_change_pct: float
    quote_volume_24h: float
    high_low_spread_pct: float
    score: float
    tags: list[str] = field(default_factory=list)

    @property
    def formatted_volume(self) -> str:
        if self.quote_volume_24h >= 1_000_000_000:
            return f"${self.quote_volume_24h / 1_000_000_000:.2f}B"
        return f"${self.quote_volume_24h / 1_000_000:.1f}M"


@dataclass
class CryptoWatchlist:
    """Daily/Session homework result containing BTC macro analysis and top picks."""

    timestamp: str
    btc_report: BTCRegimeReport | None
    candidates: list[CryptoCandidate]

    def summary(self) -> str:
        lines = [
            "=" * 65,
            f"📋 CRYPTO WATCHLIST & HOMEWORK — {self.timestamp}",
            "=" * 65,
        ]
        if self.btc_report:
            lines.append(f"👑 Macro Driver: {self.btc_report.summary()}")
            lines.append("-" * 65)

        lines.append(f"{'Rank':<5}{'Symbol':<12}{'Price':<12}{'24h Chg':<10}{'24h Vol':<12}{'Score':<8}{'Tags'}")
        lines.append("-" * 65)
        for i, c in enumerate(self.candidates, 1):
            chg_str = f"{c.price_change_pct:+.2f}%"
            tags_str = ", ".join(c.tags)
            lines.append(
                f"#{i:<4}{c.symbol:<12}${c.price:<11.2f}{chg_str:<10}{c.formatted_volume:<12}{c.score:<8.1f}{tags_str}"
            )
        lines.append("=" * 65)
        return "\n".join(lines)


class CryptoScreener:
    """Performs daily/session market homework by screening Binance Futures tickers."""

    def __init__(
        self,
        gateway: BinanceGateway | None = None,
        min_24h_volume_usdt: float = 30_000_000.0,
        top_n: int = 5,
    ) -> None:
        self.gateway = gateway or BinanceGateway()
        self.btc_analyzer = BTCRegimeAnalyzer()
        self.min_volume = min_24h_volume_usdt
        self.top_n = top_n

    def screen_tickers(self, tickers: list[dict[str, Any]]) -> list[CryptoCandidate]:
        """Filter and rank 24hr tickers based on volume and opportunity score."""
        candidates: list[CryptoCandidate] = []

        for item in tickers:
            symbol = item.get("symbol", "")
            if not symbol.endswith("USDT"):
                continue

            # Exclude delivery quarterly tokens (e.g. BTCUSDT_241227)
            if "_" in symbol:
                continue

            try:
                price = float(item.get("lastPrice", 0.0))
                price_change_pct = float(item.get("priceChangePercent", 0.0))
                quote_volume = float(item.get("quoteVolume", 0.0))
                high_price = float(item.get("highPrice", 0.0))
                low_price = float(item.get("lowPrice", 0.0))
            except (ValueError, TypeError):
                continue

            if quote_volume < self.min_volume:
                continue

            high_low_spread_pct = ((high_price - low_price) / low_price * 100.0) if low_price > 0 else 0.0

            # Composite Opportunity Score:
            # - Volume Factor (log scale proxy: volume / 50M, max 40 pts)
            # - Volatility Factor (daily range % + absolute change %, max 40 pts)
            # - Momentum Factor (clean directional move, max 20 pts)
            vol_factor = min(40.0, (quote_volume / 50_000_000.0) * 10.0)
            volatility_factor = min(40.0, high_low_spread_pct * 3.0)
            momentum_factor = min(20.0, abs(price_change_pct) * 2.0)
            composite_score = round(vol_factor + volatility_factor + momentum_factor, 1)

            tags: list[str] = []
            if symbol == "BTCUSDT":
                tags.append("Market Anchor")
            elif symbol == "ETHUSDT":
                tags.append("Major")
            if quote_volume >= 500_000_000:
                tags.append("Mega Vol")
            if abs(price_change_pct) >= 7.0:
                tags.append("High Momentum")
            if high_low_spread_pct >= 10.0:
                tags.append("High Volatility")

            candidates.append(
                CryptoCandidate(
                    symbol=symbol,
                    price=price,
                    price_change_pct=price_change_pct,
                    quote_volume_24h=quote_volume,
                    high_low_spread_pct=round(high_low_spread_pct, 2),
                    score=composite_score,
                    tags=tags,
                )
            )

        # Sort descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[: self.top_n]

    async def run_homework(self) -> CryptoWatchlist:
        """Run complete market preparation: BTC Macro + Altcoin Screener."""
        if not self.gateway.connected:
            await self.gateway.connect()

        # 1. BTC Macro Analysis
        btc_report: BTCRegimeReport | None = None
        try:
            btc_candles = await self.gateway.get_ohlcv("BTCUSDT", "H4", count=60)
            funding_rate = await self.gateway.get_funding_rate("BTCUSDT")
            btc_report = self.btc_analyzer.analyze(btc_candles, funding_rate=funding_rate)
        except Exception as exc:
            logger.warning("Failed to analyze BTC macro regime: %s", exc)

        # 2. 24h Ticker Screener
        raw_tickers = await self.gateway.get_24hr_tickers()
        candidates = self.screen_tickers(raw_tickers)

        # Ensure BTCUSDT is included in the watchlist if not already
        if btc_report and not any(c.symbol == "BTCUSDT" for c in candidates):
            btc_cand = next((c for c in self.screen_tickers(raw_tickers) if c.symbol == "BTCUSDT"), None)
            if btc_cand:
                candidates.insert(0, btc_cand)

        watchlist = CryptoWatchlist(
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            btc_report=btc_report,
            candidates=candidates[: self.top_n],
        )

        # Save to local audit cache
        self._save_watchlist(watchlist)
        return watchlist

    def _save_watchlist(self, watchlist: CryptoWatchlist) -> None:
        """Persist watchlist for other modules to consume."""
        try:
            out_file = Path("data/crypto_watchlist.json")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "timestamp": watchlist.timestamp,
                "btc_report": asdict(watchlist.btc_report) if watchlist.btc_report else None,
                "candidates": [asdict(c) for c in watchlist.candidates],
            }
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Failed to persist crypto watchlist: %s", exc)


def main():
    parser = argparse.ArgumentParser(description="Binance Crypto Market Screener")
    parser.add_argument("--top", type=int, default=5, help="Number of top coins to select")
    parser.add_argument("--min-vol", type=float, default=30_000_000.0, help="Min 24h volume in USDT")
    args = parser.parse_args()

    screener = CryptoScreener(min_24h_volume_usdt=args.min_vol, top_n=args.top)
    watchlist = asyncio.run(screener.run_homework())
    print("\n" + watchlist.summary())


if __name__ == "__main__":
    main()
