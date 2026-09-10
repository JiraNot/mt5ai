"""Trade Learner — Continuous Learning & Post-Mortem Reflection Engine.

หน้าที่:
1. ดักฟัง Event: POSITION_CLOSED จาก MT5
2. วิเคราะห์ผลลัพธ์: WIN / LOSS (ชน SL)
3. หากเป็น LOSS: ให้ AI ทำการ Post-Mortem Reflection ชันสูตรหาสาเหตุ
   สกัดเป็น `root_cause` และ `lesson_learned_th`
4. บันทึกบทเรียนลงฐานข้อมูล (TradeMemory)
5. ส่งบทเรียนที่เคยได้ ย้อนกลับไปให้ AI Council ในไม้ถัดๆ ไป (Prompt Injection)
6. แจ้งเตือน Telegram เมื่อ AI ได้บทเรียนใหม่
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from src.core.events import EventType, event_bus
from src.core.types import Position
from src.storage.repository import Repository

logger = logging.getLogger(__name__)


class TradeLearner:
    """ระบบ Continuous Self-Learning และความจำระยะยาวของ AI Trading Bot."""

    def __init__(
        self,
        repository_factory,
        gemini_evaluator=None,
        gpt_evaluator=None,
    ) -> None:
        """
        repository_factory: callable ที่คืน AsyncSession หรือ Repository
        gemini_evaluator: GeminiEvaluator instance
        gpt_evaluator: GPTEvaluator instance
        """
        self._repo_factory = repository_factory
        self._gemini = gemini_evaluator
        self._gpt = gpt_evaluator
        self._active = True

        # ติดตาม Event POSITION_CLOSED
        event_bus.subscribe(EventType.POSITION_CLOSED, self._on_position_closed_event)
        logger.info("🧠 TradeLearner (Continuous Self-Learning Engine) initialized and subscribed to POSITION_CLOSED.")

    async def _on_position_closed_event(self, data: dict[str, Any]) -> None:
        """Handler เมื่อ MT5 ส่ง event position_closed."""
        pos: Optional[Position] = data.get("position")
        if not pos:
            return

        # รันใน background task เพื่อไม่ให้บล็อก trading loop
        asyncio.create_task(self.process_closed_position(pos))

    async def process_closed_position(self, pos: Position) -> None:
        """วิเคราะห์ไม้ที่ปิด สกัดบทเรียน และบันทึกลง Memory Bank."""
        try:
            profit = float(pos.profit or 0.0)
            symbol = pos.symbol
            direction = pos.direction.value if hasattr(pos.direction, "value") else str(pos.direction)
            entry_price = float(pos.open_price or 0.0)
            sl = float(pos.sl or 0.0)
            tp = float(pos.tp or 0.0)
            strategy_id = pos.comment or "smc_strategy"

            # คำนวณ Pips
            pips = 0.0
            if pos.current_price and entry_price:
                if direction == "BUY":
                    diff = pos.current_price - entry_price
                else:
                    diff = entry_price - pos.current_price
                pips = round(diff * 10, 1) if "XAU" in symbol else round(diff * 10000, 1)

            if profit > 0:
                outcome = "WIN"
            elif profit < 0:
                outcome = "LOSS"
            else:
                outcome = "BREAKEVEN"

            logger.info(
                f"🧠 TradeLearner: วิเคราะห์ไม้ปิด #{pos.ticket} {symbol} {direction} "
                f"| Outcome: {outcome} | PnL: ${profit:.2f} ({pips} pips)"
            )

            # Post-Mortem Reflection
            root_cause, lesson_th, rule_rec = await self._reflect_on_trade(
                pos=pos,
                outcome=outcome,
                profit=profit,
                pips=pips,
            )

            # บันทึกลง Database
            async with self._repo_factory() as session:
                repo = Repository(session)
                mem_id = await repo.add_trade_memory(
                    ticket=pos.ticket,
                    symbol=symbol,
                    strategy_id=strategy_id,
                    direction=direction,
                    outcome=outcome,
                    profit=profit,
                    pips=pips,
                    rr_achieved=round(profit / abs(sl - entry_price), 2) if abs(sl - entry_price) > 0 else 0,
                    root_cause=root_cause,
                    lesson_learned_th=lesson_th,
                    rule_recommendation=rule_rec,
                    setup_snapshot=json.dumps({
                        "entry": entry_price,
                        "sl": sl,
                        "tp": tp,
                        "comment": pos.comment,
                        "closed_at": datetime.utcnow().isoformat(),
                    }),
                )
                logger.info(f"🧠 Saved Trade Memory #{mem_id} for ticket #{pos.ticket}")

            # ส่งการแจ้งเตือน Telegram
            try:
                from src.notification.telegram_alert import alert_trade_lesson
                await alert_trade_lesson(
                    symbol=symbol,
                    direction=direction,
                    outcome=outcome,
                    profit=profit,
                    root_cause=root_cause,
                    lesson_th=lesson_th,
                )
            except Exception as e:
                logger.warning(f"Telegram alert_trade_lesson error: {e}")

        except Exception as e:
            logger.error(f"TradeLearner process_closed_position error: {e}", exc_info=True)

    async def _reflect_on_trade(
        self,
        pos: Position,
        outcome: str,
        profit: float,
        pips: float,
    ) -> tuple[str, str, str]:
        """ให้ AI ชันสูตรไม้ หรือใช้ Heuristic ที่แม่นยำ."""
        direction = pos.direction.value if hasattr(pos.direction, "value") else str(pos.direction)

        if outcome == "WIN":
            return (
                "CONFLUENCE_CONFIRMED",
                f"โครงสร้าง {pos.symbol} {direction} ชัดเจน ทำกำไรได้ +${profit:.2f} ควรยึดเกณฑ์ Confluence ชุดนี้ไว้เป็นตัวอย่างที่ดี",
                "เพิ่มน้ำหนักความเชื่อมั่นในสัญญาณลักษณะนี้ +5 คะแนน",
            )

        # กรณี LOSS (ชน SL หรือขาดทุน): ให้ AI ชันสูตร
        reflection_prompt = f"""คุณคือ AI Trade Post-Mortem Auditor ผู้เชี่ยวชาญ SMC สำหรับ {pos.symbol}
ไม้ล่าสุดของเราเพิ่งปิดแบบขาดทุน (ชน SL):
- ทิศทาง: {direction}
- Entry Price: {pos.open_price}
- Stop Loss: {pos.sl}
- Take Profit: {pos.tp}
- Close Price: {pos.current_price}
- ขาดทุน: ${profit:.2f} ({pips} pips)
- กลยุทธ์/Comment: {pos.comment}

จงวิเคราะห์อย่างตรงไปตรงมาว่าทำไมถึงแพ้ เช่น:
- โดน Liquidity Hunt / Fakeout ก่อนไปตามทางหรือไม่?
- เข้าเร็วเกินไปโดยไม่มี Confirmation หรือไม่?
- สวนทาง High Timeframe Momentum หรือไม่?
- สรุปบทเรียน 1-2 ประโยคกระชับสำหรับเตือน AI Council ไม่ให้พลาดซ้ำสองในไม้หน้า

ตอบกลับเป็น JSON เท่านั้นในรูปแบบ:
{{
  "root_cause": "LIQUIDITY_HUNT" หรือ "COUNTER_HTF" หรือ "EARLY_ENTRY" หรือ "CHOPPY_MARKET" หรือ "PRE_NEWS",
  "lesson_learned_th": "บทเรียนภาษาไทยกระชับ 1-2 ประโยค",
  "rule_recommendation": "คำแนะนำปรับปรุงเกณฑ์เทคนิคสั้นๆ"
}}"""

        # 1. พยายามเรียก GPT / Codex CLI ทำการชันสูตร
        if self._gpt:
            try:
                verdict = await self._gpt.evaluate({
                    "symbol": pos.symbol,
                    "direction": direction,
                    "entry_price": pos.open_price,
                    "stop_loss": pos.sl,
                    "take_profit": pos.tp,
                    "rule_score": 0,
                    "custom_prompt": reflection_prompt,
                })
                # ถ้า GPT ให้บทวิเคราะห์กลับมา
                if verdict and verdict.narrative_th and "Error" not in verdict.narrative_th:
                    lesson = verdict.narrative_th
                    trap = getattr(verdict, "trap_identified", "FAKE_OUT")
                    return (
                        trap or "SMC_TRAP_TRIGGERED",
                        lesson,
                        "ระวังกับดักสภาพคล่องและรอ Confirmation Bar ก่อนเข้าออเดอร์",
                    )
            except Exception as e:
                logger.warning(f"GPT reflection failed: {e}")

        # 2. Fallback Heuristic ชันสูตรอัตโนมัติอย่างชาญฉลาด
        if abs(pips) < 20:
            return (
                "NOISE_OR_TIGHT_SL",
                f"ไม้ {pos.symbol} {direction} โดน SL ในระยะกระชั้นชิด ({pips} pips) เป็นไปได้ว่าตั้ง SL ชิดเกินไป หรือเจอ Market Noise ช่วงพักตัว",
                "เผื่อระยะ Stop Loss ให้พ้น Swing High/Low อย่างน้อย 1.5 เท่าของ ATR",
            )
        elif "fvg" in (pos.comment or "").lower():
            return (
                "FVG_FAILED_MITIGATION",
                f"ราคาไม่เคารพ Fair Value Gap (FVG) ในทิศทาง {direction} และทะลุผ่านโซน แสดงว่าแรงโมเมนตัมฝั่งตรงข้ามแข็งแกร่งกว่า",
                "อย่าเพิ่ง Limit Order ทันทีที่แตะ FVG ควรรอให้เกิด M5 CHoCH กลับตัวก่อน",
            )
        else:
            return (
                "COUNTER_HTF_LIQUIDITY_RUN",
                f"ไม้ {pos.symbol} {direction} ขาดทุน ${abs(profit):.2f} ราคาถูกดึงดูดไปกวาด Liquidity ฝั่งตรงข้ามก่อน",
                "ตรวจสอบแนว Equal Highs/Lows ฝั่งตรงข้ามทุกครั้งก่อนเปิดออเดอร์",
            )

    async def get_lessons_for_prompt(
        self,
        symbol: str,
        strategy_id: Optional[str] = None,
        limit: int = 3,
    ) -> list[str]:
        """ดึงบทเรียนล่าสุดจาก Database มาเป็น List ของข้อความสำหรับใส่ใน Prompt."""
        try:
            async with self._repo_factory() as session:
                repo = Repository(session)
                memories = await repo.get_recent_lessons(symbol=symbol, strategy_id=strategy_id, limit=limit)
                if not memories:
                    # ดึงของ symbol เดียวกันโดยไม่ฟิก strategy
                    memories = await repo.get_recent_lessons(symbol=symbol, limit=limit)

                lessons = []
                for m in memories:
                    prefix = "⚠️ [เตือนความผิดพลาดในอดีต]" if m.outcome == "LOSS" else "✅ [ตัวอย่างความสำเร็จ]"
                    lessons.append(f"{prefix} ({m.strategy_id} {m.direction}): {m.lesson_learned_th}")
                return lessons
        except Exception as e:
            logger.warning(f"Failed to fetch memories for prompt: {e}")
            return []
