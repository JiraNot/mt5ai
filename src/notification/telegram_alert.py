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


def _get_telegram_credentials() -> tuple[str, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "") or BOT_TOKEN
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "") or CHAT_ID
    if not token or not chat_id:
        try:
            from src.core.runtime_settings import get_runtime_settings
            cfg = get_runtime_settings(mask_secrets=False)
            if not token and cfg.get("telegram_bot_token"):
                token = cfg["telegram_bot_token"]
            if not chat_id and cfg.get("telegram_chat_id"):
                chat_id = cfg["telegram_chat_id"]
        except Exception:
            pass
    return token, chat_id


async def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """ส่งข้อความไปยัง Telegram."""
    token, chat_id = _get_telegram_credentials()
    if not token or not chat_id:
        logger.debug("Telegram credentials not configured; skipping alert")
        return False
    try:
        api_url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                api_url,
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
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


async def alert_morning_brief(
    btc_report: dict[str, Any] | None,
    watchlist_candidates: list[dict[str, Any]],
) -> bool:
    """ส่งสรุปการบ้านเช้า (Morning Briefing) รายงาน BTC Macro และ Top Watchlist."""
    nl = "\n"
    lines = [
        "☀️ [MORNING BRIEFING — สรุปตลาดและการบ้านประจำวัน]",
        f"📅 วันที่: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    if btc_report:
        bias = btc_report.get("macro_bias", "NEUTRAL")
        crowd = btc_report.get("crowd_bias", "NEUTRAL")
        rate = btc_report.get("funding_rate_pct", 0.0)
        lines.extend([
            "👑 BTC Macro Context:",
            f"  - โครงสร้างแนวโน้ม: {bias}",
            f"  - อารมณ์ตลาด (Crowd Bias): {crowd} (Funding: {rate:+.4f}%)",
            "",
        ])

    lines.append(f"🎯 Watchlist แนะนำจับตาวันนี้ ({len(watchlist_candidates)} เหรียญ):")
    if not watchlist_candidates:
        lines.append("  (ไม่มีเหรียญที่ผ่านเกณฑ์ Volume & Momentum วันนี้)")
    else:
        for idx, cand in enumerate(watchlist_candidates, 1):
            sym = cand.get("symbol", "")
            chg = cand.get("price_change_pct", 0.0)
            score = cand.get("score", 0.0)
            tags = ", ".join(cand.get("tags", [])) or "Active"
            vol = cand.get("formatted_volume") or f"${cand.get('quote_volume_24h', 0) / 1e6:.1f}M"
            lines.append(f"  {idx}. {sym}: 24h {chg:+.2f}% | Vol {vol} | Score {score} [{tags}]")

    lines.extend([
        "",
        "🛡️ แผนการเทรด: เฝ้ารอ Setup SMC M5 ตามทิศทาง HTF และปฏิบัติตามคำสั่ง Risk Engine 100%",
    ])
    return await send_message(nl.join(lines))


async def alert_evening_reflection(
    daily_stats: dict[str, Any],
    gate_evaluation: dict[str, Any] | None = None,
) -> bool:
    """ส่งสรุปค่ำ (Daily Reflection) สรุปผลการเทรดและเกจวัดความพร้อมขึ้น Live."""
    nl = "\n"
    total_trades = daily_stats.get("total_trades", 0)
    win_rate = daily_stats.get("win_rate_pct", 0.0)
    net_pnl = daily_stats.get("net_pnl", 0.0)
    sign = "+" if net_pnl >= 0 else ""

    lines = [
        "🌙 [DAILY REFLECTION — สรุปผลเทรดและประเมินความพร้อม LIVE]",
        f"📅 วันที่: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "📊 ผลการเทรดรอบ 24 ชม.:",
        f"  - จำนวนไม้: {total_trades} ไม้",
        f"  - Win Rate: {win_rate:.1f}%",
        f"  - Net P&L: {sign}${net_pnl:,.2f}",
        "",
    ]

    if gate_evaluation:
        current_stage = gate_evaluation.get("current_stage", "DEMO")
        is_ready = gate_evaluation.get("is_promotable", False)
        gates = gate_evaluation.get("gate_checks", [])
        passed_gates = sum(1 for g in gates if g.get("passed", False))
        total_gates = len(gates) or 6
        readiness_pct = (passed_gates / total_gates) * 100

        status_text = "🚀 ผ่านเกณฑ์ครบทั้งหมด พร้อมเปิด LIVE TRADING!" if is_ready else "⏳ กำลังสะสมสถิติใน DEMO ให้ครบตามเกณฑ์"
        lines.extend([
            "🛡️ เกจวัดความพร้อมเลื่อนขั้น (Promotion Gate):",
            f"  - สถานะปัจจุบัน: {current_stage}",
            f"  - ความพร้อม: {readiness_pct:.0f}% ({passed_gates}/{total_gates} เกณฑ์ความปลอดภัย)",
            f"  - ผลการประเมิน: {status_text}",
            "",
        ])

    lesson = daily_stats.get("lesson_of_the_day")
    if lesson:
        lines.extend([
            "💡 บทเรียนสำคัญวันนี้:",
            f"  \"{lesson}\"",
            "",
        ])

    lines.append("🤖 AI Council & Risk Engine กำลังเฝ้าติดตามตลาดอย่างมีวินัย")
    return await send_message(nl.join(lines))


async def alert_break_even(
    symbol: str,
    direction: str,
    entry_price: float,
    new_sl: float,
    current_r: float,
) -> bool:
    """แจ้งเตือนเมื่อเลื่อน Stop Loss มาที่ทุน (Break-Even Lock)."""
    nl = "\n"
    lines = [
        "🛡️ [RISK-FREE ACTIVATED — ล็อกทุน BREAK-EVEN]",
        "",
        f"เหรียญ: {symbol} ({direction})",
        f"กำไรปัจจุบัน: +{current_r:.2f}R",
        f"ราคาเปิด (Entry): ${entry_price:,.2f}",
        f"Stop Loss ใหม่: ${new_sl:,.2f} (ล็อกทุนเรียบร้อย)",
        "",
        "🔒 ไม้นี้ปลอดภัย 100% (ไม่มีวันขาดทุนแล้ว)",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]
    return await send_message(nl.join(lines))


async def alert_partial_tp(
    symbol: str,
    direction: str,
    closed_volume: float,
    remaining_volume: float,
    realized_profit: float,
    current_r: float,
) -> bool:
    """แจ้งเตือนเมื่อแบ่งปิดทำกำไร (Partial Take Profit)."""
    sign = "+" if realized_profit >= 0 else ""
    nl = "\n"
    lines = [
        "💰 [PARTIAL TP EXECUTED — แบ่งปิดทำกำไรเข้ากระเป๋า]",
        "",
        f"เหรียญ: {symbol} ({direction})",
        f"จุดทำกำไร: +{current_r:.2f}R (TP1 Reached)",
        f"จำนวนที่ปิด: {closed_volume} lots ({sign}${realized_profit:,.2f})",
        f"จำนวนที่คงเหลือ: {remaining_volume} lots (ปล่อย Run Trend)",
        "",
        "🎯 ล็อกกำไรเข้าพอร์ตเรียบร้อย และปล่อยให้ไม้ที่เหลือทำกำไรต่อ",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]
    return await send_message(nl.join(lines))
