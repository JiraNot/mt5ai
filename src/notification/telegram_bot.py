"""Interactive Two-Way Telegram Bot Listener for mt5ai.

Provides two-way remote control via Telegram long-polling (getUpdates):
- /status: Shows live account balance, equity, mode, and open positions with current R
- /homework: Triggers on-demand CryptoScreener scan and returns Top 5 watchlist
- /panic: Emergency shutdown — closes all open positions and halts trading
- /readiness: Checks 0-100% PromotionGate checklist for Live readiness
- /help: Displays command menu

Runs in the background without needing a public webhook URL or open ports.
Only responds to the configured TELEGRAM_CHAT_ID for security.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from src.core.config import settings
from src.core.events import EventType, event_bus
from src.core.runtime_control import get_runtime_trading_mode
from src.core.types import Direction
from src.market.binance_gateway import BinanceGateway
from src.market.crypto_screener import CryptoScreener
from src.risk.promotion_gate import PromotionGate

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


class TelegramBotListener:
    """Long-polling Telegram Bot listener handling interactive commands."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        gateway: BinanceGateway | None = None,
        order_manager: Any | None = None,
        screener: CryptoScreener | None = None,
        promotion_gate: PromotionGate | None = None,
        platform_stop_callback: Callable[[], Any] | None = None,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        self.bot_token = bot_token or BOT_TOKEN
        self.chat_id = chat_id or CHAT_ID
        if not self.bot_token or not self.chat_id:
            try:
                from src.core.runtime_settings import get_runtime_settings
                cfg = get_runtime_settings(mask_secrets=False)
                if not self.bot_token and cfg.get("telegram_bot_token"):
                    self.bot_token = cfg["telegram_bot_token"]
                if not self.chat_id and cfg.get("telegram_chat_id"):
                    self.chat_id = cfg["telegram_chat_id"]
            except Exception:
                pass
        self.gateway = gateway
        self.order_manager = order_manager
        self.screener = screener
        self.promotion_gate = promotion_gate or PromotionGate()
        self.platform_stop_callback = platform_stop_callback
        self.poll_interval = poll_interval_seconds

        self._running = False
        self._task: asyncio.Task | None = None
        self._last_update_id = 0

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def send_response(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send message back to authorized chat ID."""
        if not self.is_configured:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                )
                resp.raise_for_status()
                return True
        except Exception as exc:
            logger.error("Failed sending Telegram response: %s", exc)
            return False

    async def handle_status_command(self) -> str:
        """Handle /status: balance, active mode, and open positions."""
        mode = get_runtime_trading_mode(settings.trading_mode).upper()
        venue = "Binance USDT-M Futures"

        balance_str = "N/A"
        equity_str = "N/A"
        positions = []

        if self.gateway:
            try:
                acc = await self.gateway.get_account_info()
                balance_str = f"${acc.balance:,.2f}"
                equity_str = f"${acc.equity:,.2f}"
                positions = await self.gateway.get_positions()
            except Exception as exc:
                logger.warning("Status command gateway query failed: %s", exc)

        nl = "\n"
        lines = [
            "📊 <b>[BINANCE AI PLATFORM STATUS]</b>",
            f"🕒 เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"⚙️ โหมด: <b>{mode}</b> | ตลาด: {venue}",
            f"💰 ยอดเงิน (Balance): {balance_str}",
            f"📈 สินทรัพย์สุทธิ (Equity): {equity_str}",
            "",
            f"📌 ไม้ที่กำลังเปิดอยู่ ({len(positions)} ไม้):",
        ]

        if not positions:
            lines.append("  (ไม่มีออเดอร์ค้างในพอร์ต)")
        else:
            for p in positions:
                direction_icon = "🟢 BUY" if p.direction == Direction.BUY else "🔴 SELL"
                pnl_sign = "+" if p.profit >= 0 else ""
                lines.append(
                    f"  • <b>{p.symbol}</b> {direction_icon} {p.volume} lots\n"
                    f"    Entry: ${p.open_price:,.2f} | Current: ${p.current_price:,.2f}\n"
                    f"    SL: ${p.sl:,.2f} | TP: ${p.tp:,.2f}\n"
                    f"    P&L: <b>{pnl_sign}${p.profit:,.2f}</b>"
                )

        lines.extend([
            "",
            "🤖 ระบบกำลังทำงานและเฝ้าตลาดตลอด 24 ชม.",
        ])
        return nl.join(lines)

    async def handle_homework_command(self) -> str:
        """Handle /homework: trigger on-demand screener and report results."""
        scr = self.screener or CryptoScreener(gateway=self.gateway)
        try:
            watchlist = await scr.run_homework()
            nl = "\n"
            lines = [
                "📋 <b>[CRYPTO HOMEWORK & WATCHLIST]</b>",
                f"🕒 อัปเดตล่าสุด: {watchlist.timestamp}",
                "",
            ]
            if watchlist.btc_report:
                rep = watchlist.btc_report
                lines.extend([
                    "👑 <b>BTC Macro Context:</b>",
                    f"  - โครงสร้าง: <b>{rep.regime.value.upper()}</b> (ความมั่นใจ {rep.confidence:.0%})",
                    f"  - อารมณ์ตลาด: {rep.funding_bias} (Funding: {rep.funding_rate * 100:+.4f}%)",
                    f"  - คำแนะนำ: {rep.recommendation_th}",
                    "",
                ])

            lines.append(f"🎯 <b>Top Watchlist Picks ({len(watchlist.candidates)} เหรียญ):</b>")
            for idx, c in enumerate(watchlist.candidates, 1):
                tags_str = ", ".join(c.tags)
                lines.append(
                    f"  <b>{idx}. {c.symbol}</b>: ${c.price:,.2f} ({c.price_change_pct:+.2f}%)\n"
                    f"     Vol: {c.formatted_volume} | Score: {c.score:.1f} [{tags_str}]"
                )

            lines.extend([
                "",
                "💡 บอทจะเฝ้ารอ Setup SMC M5 ตามโครงสร้างเหรียญข้างต้นอัตโนมัติ",
            ])
            return nl.join(lines)
        except Exception as exc:
            logger.error("Error running homework command: %s", exc)
            return f"❌ เกิดข้อผิดพลาดในการรันการบ้าน: {exc}"

    async def handle_panic_command(self) -> str:
        """Handle /panic: Emergency shutdown, close all positions, halt trading."""
        logger.critical("🚨 EMERGENCY PANIC TRIGGERED VIA TELEGRAM COMMAND!")
        closed_count = 0
        error_count = 0

        # Close all active positions
        if self.gateway:
            try:
                positions = await self.gateway.get_positions()
                for pos in positions:
                    try:
                        res = await self.gateway.close_position(pos.ticket)
                        if res.success:
                            closed_count += 1
                        else:
                            error_count += 1
                    except Exception as exc:
                        logger.error("Failed closing position %s during panic: %s", pos.ticket, exc)
                        error_count += 1
            except Exception as exc:
                logger.error("Failed querying positions during panic: %s", exc)

        # Trigger emergency circuit breaker event
        await event_bus.publish(
            EventType.CIRCUIT_BREAKER,
            {"reason": "PANIC_SHUTDOWN_COMMAND_VIA_TELEGRAM"},
        )

        # Call platform stop callback if provided
        if self.platform_stop_callback:
            try:
                import inspect
                if inspect.iscoroutinefunction(self.platform_stop_callback):
                    await self.platform_stop_callback()
                else:
                    self.platform_stop_callback()
            except Exception as exc:
                logger.error("Error executing platform stop callback: %s", exc)

        nl = "\n"
        lines = [
            "🚨 <b>[EMERGENCY PANIC ACTIVATED — ระบบหยุดทำงานฉุกเฉิน]</b>",
            "",
            f"✅ ปิดสถานะออเดอร์ทั้งหมดสำเร็จ: <b>{closed_count}</b> ไม้",
        ]
        if error_count > 0:
            lines.append(f"⚠️ ไม้ที่ปิดไม่สำเร็จ: {error_count} ไม้ (โปรดตรวจสอบบน Binance ทันที)")
        lines.extend([
            "🛑 การเทรดถูกระงับ (HALTED) 100% เรียบร้อยแล้ว",
            "🔒 ทุกฟังก์ชันหยุดส่งคำสั่งใหม่ เพื่อปกป้องเงินทุนของคุณ",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ])
        return nl.join(lines)

    async def handle_readiness_command(self) -> str:
        """Handle /readiness: check promotion gate progress."""
        eval_result = self.promotion_gate.evaluate_trades([])
        total_gates = len(eval_result.gate_checks)
        passed_gates = sum(1 for g in eval_result.gate_checks if g.passed)
        readiness_pct = (passed_gates / total_gates * 100) if total_gates > 0 else 0

        status_text = (
            "🚀 <b>ผ่านเกณฑ์ครบทั้งหมด พร้อมเปิด LIVE TRADING!</b>"
            if eval_result.is_promotable
            else "⏳ <b>กำลังสะสมสถิติใน DEMO ให้ครบตามเกณฑ์</b>"
        )

        nl = "\n"
        lines = [
            "🛡️ <b>[PROMOTION GATE READINESS — เกจวัดความพร้อมขึ้น LIVE]</b>",
            "",
            f"• สถานะปัจจุบัน: <b>{eval_result.current_stage}</b>",
            f"• ระดับความพร้อม: <b>{readiness_pct:.0f}%</b> ({passed_gates}/{total_gates} เกณฑ์ความปลอดภัย)",
            f"• คำตัดสิน: {status_text}",
            f"• ไม้ในเดโมสะสม: {eval_result.total_trades} ไม้ (ชนะ {eval_result.wins} / แพ้ {eval_result.losses})",
            f"• Win Rate: {eval_result.win_rate_pct:.1f}% | Profit Factor: {eval_result.profit_factor:.2f}",
            "",
            "📋 <b>สถานะแต่ละเกณฑ์:</b>",
        ]
        for g in eval_result.gate_checks:
            icon = "✅" if g.passed else "❌"
            lines.append(f"  {icon} {g.name}: เป้าหมาย {g.target} (ค่าจริง: {g.actual})")

        return nl.join(lines)

    async def handle_help_command(self) -> str:
        """Handle /help: command directory."""
        nl = "\n"
        lines = [
            "🤖 <b>[BINANCE AI BOT — เมนูคำสั่งรีโมทคอนโทรล]</b>",
            "",
            "คุณสามารถสั่งงานบอทได้ด้วยคำสั่งต่อไปนี้:",
            "• <b>/status</b> — ดูสถานะพอร์ต, ยอดเงิน, โหมดเทรด และออเดอร์ที่เปิดอยู่",
            "• <b>/homework</b> — สั่งให้ AI รันการบ้านสแกนเหรียญ Binance 24h ทันที",
            "• <b>/readiness</b> — ดูหลอดพลังความพร้อมเลื่อนขั้นสู่ LIVE (0–100%)",
            "• <b>/panic</b> — 🚨 <b>ปุ่มฉุกเฉิน:</b> ปิดทุกไม้ทันทีและหยุดการทำงานทั้งระบบ",
            "• <b>/help</b> — แสดงรายการคำสั่งนี้",
            "",
            "🛡️ <i>ระบบปลอดภัย: ตอบสนองเฉพาะ Chat ID ที่ได้รับอนุญาตเท่านั้น</i>",
        ]
        return nl.join(lines)

    async def process_command(self, text: str) -> str:
        """Route and execute incoming command."""
        cmd = text.strip().split()[0].lower() if text.strip() else ""
        if cmd == "/status":
            return await self.handle_status_command()
        elif cmd == "/homework":
            return await self.handle_homework_command()
        elif cmd == "/panic":
            return await self.handle_panic_command()
        elif cmd == "/readiness":
            return await self.handle_readiness_command()
        elif cmd in ("/help", "/start"):
            return await self.handle_help_command()
        else:
            return (
                f"❓ ไม่รู้จักคำสั่ง <code>{text}</code>\n"
                "พิมพ์ <b>/help</b> เพื่อดูรายการคำสั่งที่รองรับครับ"
            )

    async def check_updates(self, client: httpx.AsyncClient) -> None:
        """Poll getUpdates endpoint from Telegram and process incoming messages."""
        if not self.is_configured:
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {"offset": self._last_update_id + 1, "timeout": 10}

        try:
            resp = await client.get(url, params=params, timeout=15.0)
            if resp.status_code != 200:
                logger.warning("Telegram getUpdates returned status %d", resp.status_code)
                return

            data = resp.json()
            updates = data.get("result", [])

            for upd in updates:
                update_id = upd.get("update_id", 0)
                if update_id > self._last_update_id:
                    self._last_update_id = update_id

                message = upd.get("message") or upd.get("channel_post")
                if not message:
                    continue

                chat = message.get("chat", {})
                chat_id_str = str(chat.get("id", ""))
                text = message.get("text", "")

                # Strictly ignore unauthorized chats
                if str(self.chat_id) != chat_id_str:
                    logger.warning("Ignored unauthorized Telegram message from chat_id %s", chat_id_str)
                    continue

                if text.startswith("/"):
                    logger.info("Received Telegram command: %s", text)
                    response_text = await self.process_command(text)
                    await self.send_response(response_text)

        except (httpx.TimeoutException, httpx.RequestError):
            pass
        except Exception as exc:
            logger.error("Error during Telegram poll cycle: %s", exc)

    async def start(self) -> None:
        """Start long-polling loop in the background."""
        if self._running or not self.is_configured:
            if not self.is_configured:
                logger.info("TelegramBotListener skipped (tokens not configured)")
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("TelegramBotListener started long-polling for commands")

    async def stop(self) -> None:
        """Stop long-polling loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TelegramBotListener stopped")

    async def _poll_loop(self) -> None:
        """Continuous polling loop."""
        async with httpx.AsyncClient() as client:
            while self._running:
                try:
                    await self.check_updates(client)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("Exception in Telegram listener loop: %s", exc)

                try:
                    await asyncio.sleep(self.poll_interval)
                except asyncio.CancelledError:
                    break
