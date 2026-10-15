"""Automated Background Scheduler for Binance AI Platform.

Handles routine automated tasks:
1. 08:00 (UTC+7) Morning Briefing:
   - Scans 24h Binance Futures tickers via CryptoScreener
   - Saves updated Watchlist to data/crypto_watchlist.json
   - Dispatches alert_morning_brief to Telegram
2. 20:00 (UTC+7) Evening Reflection:
   - Audits closed trades from database
   - Evaluates PromotionGate readiness (0-100% gauge)
   - Dispatches alert_evening_reflection to Telegram
3. Every 4 Hours (H4 candle close):
   - Refreshes BTC Macro Regime & Funding Rate crowd bias
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from src.market.binance_gateway import BinanceGateway
from src.market.btc_regime import BTCRegimeAnalyzer
from src.market.crypto_screener import CryptoScreener, CryptoWatchlist
from src.risk.promotion_gate import PromotionGate, PromotionEvaluation
from src.notification.telegram_alert import (
    alert_morning_brief,
    alert_evening_reflection,
)

logger = logging.getLogger(__name__)

# Bangkok Timezone (UTC+7)
TZ_BANGKOK = timezone(timedelta(hours=7), name="UTC+7")


class BackgroundScheduler:
    """Manages scheduled daily briefings, evening reflections, and macro refreshes."""

    def __init__(
        self,
        gateway: BinanceGateway | None = None,
        db_session_factory: Any | None = None,
        screener: CryptoScreener | None = None,
        promotion_gate: PromotionGate | None = None,
        btc_analyzer: BTCRegimeAnalyzer | None = None,
        check_interval_seconds: float = 30.0,
    ) -> None:
        self.gateway = gateway or BinanceGateway()
        self.db_session_factory = db_session_factory
        self.screener = screener or CryptoScreener(gateway=self.gateway)
        self.promotion_gate = promotion_gate or PromotionGate()
        self.btc_analyzer = btc_analyzer or BTCRegimeAnalyzer()
        self.check_interval_seconds = check_interval_seconds

        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._last_morning_brief_date: str | None = None
        self._last_evening_reflection_date: str | None = None
        self._last_macro_refresh_hour: int | None = None

        self._latest_watchlist: CryptoWatchlist | None = None
        self._latest_reflection: dict[str, Any] | None = None
        self._latest_btc_macro: dict[str, Any] | None = None

    async def run_morning_brief(self) -> dict[str, Any]:
        """Execute morning homework screener and send Telegram morning brief."""
        logger.info("Executing 08:00 AM Morning Briefing...")
        try:
            watchlist = await self.screener.run_homework()
            self._latest_watchlist = watchlist

            btc_dict = asdict(watchlist.btc_report) if watchlist.btc_report else None
            bias_val = "UNKNOWN"
            if btc_dict:
                reg = btc_dict.get("regime")
                bias_raw = getattr(reg, "value", str(reg)) if reg else btc_dict.get("macro_bias", "UNKNOWN")
                bias_val = str(bias_raw).upper()
                btc_dict["macro_bias"] = bias_val
                btc_dict["crowd_bias"] = str(btc_dict.get("crowd_bias") or btc_dict.get("funding_bias", "NEUTRAL")).upper()
                btc_dict["funding_rate_pct"] = btc_dict.get("funding_rate_pct", btc_dict.get("funding_rate", 0.0) * 100)

            candidates_dict = [asdict(c) for c in watchlist.candidates]

            await alert_morning_brief(btc_dict, candidates_dict)
            logger.info("Morning Briefing delivered with %d candidates", len(candidates_dict))
            return {
                "success": True,
                "timestamp": watchlist.timestamp,
                "candidates_count": len(candidates_dict),
                "btc_bias": bias_val,
            }
        except Exception as exc:
            logger.error("Failed executing Morning Briefing: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    async def run_evening_reflection(self) -> dict[str, Any]:
        """Execute evening performance audit and send Telegram evening reflection."""
        logger.info("Executing 20:00 PM Evening Reflection...")
        try:
            evaluation: PromotionEvaluation
            if self.db_session_factory:
                async with self.db_session_factory() as session:
                    evaluation = await self.promotion_gate.evaluate_database(session)
            else:
                evaluation = self.promotion_gate.evaluate_trades([])

            daily_stats = {
                "total_trades": evaluation.total_trades,
                "win_rate_pct": evaluation.win_rate_pct,
                "net_pnl": evaluation.net_pnl,
                "lesson_of_the_day": (
                    evaluation.recommendations_th[0]
                    if evaluation.recommendations_th
                    else "Maintain discipline, respect Stop Loss, and observe HTF liquidity pools."
                ),
            }

            eval_dict = asdict(evaluation)
            self._latest_reflection = {
                "daily_stats": daily_stats,
                "gate_evaluation": eval_dict,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            await alert_evening_reflection(daily_stats, eval_dict)
            logger.info("Evening Reflection delivered. Stage: %s, Trades: %d", evaluation.current_stage, evaluation.total_trades)
            return {
                "success": True,
                "total_trades": evaluation.total_trades,
                "win_rate_pct": evaluation.win_rate_pct,
                "net_pnl": evaluation.net_pnl,
                "is_promotable": evaluation.is_promotable,
            }
        except Exception as exc:
            logger.error("Failed executing Evening Reflection: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    async def run_macro_refresh(self) -> dict[str, Any]:
        """Execute 4-Hour BTC Macro Context refresh."""
        logger.info("Executing 4-Hour BTC Macro Refresh...")
        try:
            if not self.gateway.connected:
                await self.gateway.connect()

            btc_candles = await self.gateway.get_ohlcv("BTCUSDT", "H4", count=60)
            funding_rate = await self.gateway.get_funding_rate("BTCUSDT")
            report = self.btc_analyzer.analyze(btc_candles, funding_rate=funding_rate)
            context = report.to_context_dict()
            self._latest_btc_macro = context
            logger.info("BTC Macro refreshed: Bias=%s, Crowd=%s, Funding=%.4f%%", report.macro_bias.value, report.crowd_bias.value, funding_rate * 100)
            return {"success": True, "context": context}
        except Exception as exc:
            logger.warning("Failed refreshing BTC macro context: %s", exc)
            return {"success": False, "error": str(exc)}

    async def check_and_execute_schedules(self, now_dt: datetime | None = None) -> list[str]:
        """Check current time against schedule rules and run pending jobs."""
        now_bkk = (now_dt or datetime.now(timezone.utc)).astimezone(TZ_BANGKOK)
        today_bkk_str = now_bkk.strftime("%Y-%m-%d")
        now_utc = now_bkk.astimezone(timezone.utc)

        executed: list[str] = []

        # 1. 08:00 AM (08:00 - 08:59) Bangkok Time -> Morning Brief
        if now_bkk.hour == 8 and self._last_morning_brief_date != today_bkk_str:
            self._last_morning_brief_date = today_bkk_str
            res = await self.run_morning_brief()
            if res.get("success"):
                executed.append("morning_brief")

        # 2. 20:00 PM (20:00 - 20:59) Bangkok Time -> Evening Reflection
        if now_bkk.hour == 20 and self._last_evening_reflection_date != today_bkk_str:
            self._last_evening_reflection_date = today_bkk_str
            res = await self.run_evening_reflection()
            if res.get("success"):
                executed.append("evening_reflection")

        # 3. Every 4 hours UTC (0, 4, 8, 12, 16, 20) -> Macro Refresh
        utc_hour = now_utc.hour
        if utc_hour % 4 == 0 and self._last_macro_refresh_hour != utc_hour:
            self._last_macro_refresh_hour = utc_hour
            res = await self.run_macro_refresh()
            if res.get("success"):
                executed.append("macro_refresh")

        return executed

    async def start(self) -> None:
        """Start the background scheduler loop."""
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("BackgroundScheduler started (interval=%.1fs)", self.check_interval_seconds)

    async def stop(self) -> None:
        """Stop the background scheduler loop."""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("BackgroundScheduler stopped")

    async def _run_loop(self) -> None:
        """Periodic background evaluation loop."""
        while self._running:
            try:
                await self.check_and_execute_schedules()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in scheduler cycle: %s", exc, exc_info=True)

            try:
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                break
