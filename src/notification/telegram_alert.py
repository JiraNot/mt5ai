"""Telegram Alert System for mt5ai.

ส่ง notification เมื่อ:
- AI Council APPROVE -> เปิดไม้
- Disagreement -> AI เถียงกัน
- Trade ปิด -> ผลลัพธ์
- Daily Review -> สรุปรายวัน
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


@dataclass
class TradeAlert:
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    rule_score: int
    gemini_score: int
    gpt_score: int
    gemini_verdict: str
    gpt_verdict: str
    combined_verdict: str
    narrative_th: str


async def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """ส่งข้อความไปยัง Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN หรือ TELEGRAM_CHAT_ID ยังไม่ได้ตั้งค่า")
        return False
    try:
        api_url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                api_url,
                json={"chat_id": CHAT_ID, "text": text, "parse_mode": parse_mode},
            )
            resp.raise_for_status()
            logger.info("Telegram: ส่งสำเร็จ")
            return True
    except Exception as exc:
        logger.error("Telegram error: %s", exc)
        return False


async def alert_trade_opened(alert: TradeAlert) -> None:
    """แจ้งเตือนเมื่อเปิดไม้."""
    direction_th = "BUY (Long)" if alert.direction == "BUY" else "SELL (Short)"
    nl = "\n"
    lines = [
        "TRADE OPEN — " + alert.symbol,
        "",
        "ทิศทาง: " + direction_th,
        "Entry: " + str(round(alert.entry_price, 2)),
        "Stop Loss: " + str(round(alert.stop_loss, 2)),
        "Take Profit: " + str(round(alert.take_profit, 2)),
        "",
        "AI Council:",
        "  Gemini (Bull): " + alert.gemini_verdict + " (" + str(alert.gemini_score) + "%)",
        "  GPT (Bear): " + alert.gpt_verdict + " (" + str(alert.gpt_score) + "%)",
        "  Rule Score: " + str(alert.rule_score) + "/100",
        "",
        alert.narrative_th[:200],
        "",
        datetime.now().strftime("%H:%M:%S"),
    ]
    await send_message(nl.join(lines))


async def alert_trade_skipped(
    symbol: str,
    reason: str,
    gemini_say: str,
    gpt_say: str,
) -> None:
    """แจ้งเตือนเมื่อ Skip ไม้ (AI ไม่เห็นด้วยกัน)."""
    nl = "\n"
    lines = [
        "SKIP — AI เถียงกัน (" + symbol + ")",
        "",
        "เหตุผล: " + reason,
        "",
        "Gemini: " + gemini_say[:150],
        "GPT: " + gpt_say[:150],
        "",
        datetime.now().strftime("%H:%M:%S"),
    ]
    await send_message(nl.join(lines))


async def alert_trade_closed(
    symbol: str,
    direction: str,
    result_r: float,
    result_pips: float,
    was_ai_correct: bool,
) -> None:
    """แจ้งเตือนเมื่อปิดไม้."""
    sign = "+" if result_r >= 0 else ""
    ai_result = "AI ทำนายถูก" if was_ai_correct else "AI ทำนายผิด"
    nl = "\n"
    lines = [
        "TRADE CLOSED — " + symbol + " " + direction,
        "",
        "ผลลัพธ์: " + sign + str(round(result_r, 2)) + "R (" + str(round(result_pips, 1)) + " pips)",
        ai_result,
        "",
        datetime.now().strftime("%H:%M:%S"),
    ]
    await send_message(nl.join(lines))


async def alert_daily_review(
    total_trades: int,
    win_rate: float,
    total_r: float,
    gemini_accuracy: float,
    gpt_accuracy: float,
    summary_th: str,
) -> None:
    """ส่งสรุปรายวัน."""
    sign = "+" if total_r >= 0 else ""
    nl = "\n"
    lines = [
        "สรุปรายวัน — " + datetime.now().strftime("%d/%m/%Y"),
        "",
        "จำนวนไม้: " + str(total_trades),
        "Win Rate: " + str(round(win_rate, 1)) + "%",
        "Total: " + sign + str(round(total_r, 2)) + "R",
        "",
        "AI Accuracy:",
        "  Gemini: " + str(round(gemini_accuracy, 1)) + "%",
        "  GPT: " + str(round(gpt_accuracy, 1)) + "%",
        "",
        summary_th[:300],
    ]
    await send_message(nl.join(lines))


async def alert_trade_lesson(
    symbol: str,
    direction: str,
    outcome: str,
    profit: float,
    root_cause: str,
    lesson_th: str,
) -> None:
    """แจ้งเตือนเมื่อ AI Council สรุปบทเรียนจากไม้ที่ปิด (Continuous Learning)."""
    icon = "💡 [AI COUNCIL BIBLE — LESSON LEARNED]" if outcome == "LOSS" else "🎯 [AI COUNCIL REINFORCEMENT]"
    sign = "+" if profit >= 0 else ""
    nl = "\n"
    lines = [
        icon,
        "",
        "ไม้: " + symbol + " " + direction + " | ผลลัพธ์: " + outcome + " (" + sign + "$" + str(round(profit, 2)) + ")",
        "🔍 สาเหตุ: " + root_cause,
        "",
        "📝 บทเรียนที่ได้:",
        "\"" + lesson_th + "\"",
        "",
        "🧠 บันทึกลง AI Memory Bank เรียบร้อยแล้ว เพื่อใช้เตือนสติในการเทรดไม้ถัดไป",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]
    await send_message(nl.join(lines))
