"""Promotion Gate & Readiness Evaluator.

Audits paper/demo trading performance against deterministic statistical
and risk criteria before allowing transition to live trading.

Criteria:
1. Minimum sample size (default >= 30 verified closed trades)
2. Profit Factor >= 1.50
3. Net PnL > 0
4. Win Rate >= 40.0%
5. Maximum Drawdown <= 5.0%
6. 100% Server-side Stop Loss compliance (every order must have a valid SL)

Usage:
    python -m src.risk.promotion_gate
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.core.config import settings
from src.storage.models import Trade

logger = logging.getLogger(__name__)


@dataclass
class PromotionCriteria:
    """Target thresholds required for live trading promotion."""

    min_trades: int = 30
    min_profit_factor: float = 1.50
    min_win_rate_pct: float = 40.0
    max_drawdown_pct: float = 5.0
    min_sl_compliance_pct: float = 100.0


@dataclass
class GateCheck:
    """Result of an individual promotion gate check."""

    name: str
    target: str
    actual: str
    passed: bool
    description: str


@dataclass
class PromotionEvaluation:
    """Complete evaluation report on whether the system is ready for LIVE."""

    is_promotable: bool
    current_stage: str  # "PAPER", "DEMO", "READY_FOR_LIVE"
    total_trades: int
    wins: int
    losses: int
    win_rate_pct: float
    profit_factor: float
    net_pnl: float
    max_drawdown_pct: float
    sl_compliance_pct: float
    gate_checks: list[GateCheck] = field(default_factory=list)
    summary_th: str = ""
    recommendations_th: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 68,
            "🛡️  PROMOTION SAFETY GATE EVALUATION (DEMO -> LIVE READINESS)",
            "=" * 68,
            f"Current Stage:    {self.current_stage}",
            f"Overall Verdict:  {'✅ READY FOR LIVE TRADING' if self.is_promotable else '🛑 NOT READY (CONTINUE DEMO)'}",
            f"Closed Trades:    {self.total_trades} ({self.wins}W / {self.losses}L)",
            f"Net PnL:          ${self.net_pnl:+,.2f}",
            f"Profit Factor:    {self.profit_factor:.2f}",
            f"Win Rate:         {self.win_rate_pct:.1f}%",
            f"Max Drawdown:     {self.max_drawdown_pct:.2f}%",
            f"SL Compliance:    {self.sl_compliance_pct:.1f}%",
            "-" * 68,
            f"{'Gate Name':<28}{'Target':<14}{'Actual':<14}{'Status'}",
            "-" * 68,
        ]
        for g in self.gate_checks:
            status_str = "✅ PASS" if g.passed else "❌ FAIL"
            lines.append(f"{g.name:<28}{g.target:<14}{g.actual:<14}{status_str}")
        lines.append("=" * 68)
        lines.append(f"📌 สรุปผล: {self.summary_th}")
        if self.recommendations_th:
            lines.append("💡 คำแนะนำสำหรับระบบ:")
            for r in self.recommendations_th:
                lines.append(f"   - {r}")
        lines.append("=" * 68)
        return "\n".join(lines)


class PromotionGate:
    """Evaluates whether demo trading data meets criteria to unlock LIVE mode."""

    def __init__(self, criteria: PromotionCriteria | None = None) -> None:
        self.criteria = criteria or PromotionCriteria()

    def evaluate_trades(self, trades: list[dict[str, Any]] | list[Trade]) -> PromotionEvaluation:
        """Run statistical gate checks on closed trade records."""
        parsed_trades: list[dict[str, Any]] = []
        for t in trades:
            if isinstance(t, Trade):
                if t.status != "CLOSED":
                    continue
                parsed_trades.append({
                    "symbol": t.symbol,
                    "net_profit": float(t.net_profit or 0.0),
                    "sl": float(t.sl or 0.0),
                    "outcome": "WIN" if float(t.net_profit or 0.0) > 0 else "LOSS",
                })
            elif isinstance(t, dict):
                if t.get("status") in ("CLOSED", None):
                    parsed_trades.append({
                        "symbol": t.get("symbol", ""),
                        "net_profit": float(t.get("net_profit", t.get("pnl", 0.0))),
                        "sl": float(t.get("sl", 0.0)),
                        "outcome": t.get("outcome", "WIN" if float(t.get("net_profit", t.get("pnl", 0.0))) > 0 else "LOSS"),
                    })

        total = len(parsed_trades)
        if total == 0:
            checks = [
                GateCheck("Sample Size", f">={self.criteria.min_trades}", "0", False, "จำนวนไม้ขั้นต่ำ"),
                GateCheck("Profit Factor", f">={self.criteria.min_profit_factor}", "N/A", False, "อัตราส่วนกำไรต่อขาดทุน"),
                GateCheck("Net PnL", "> $0", "$0.00", False, "กำไรสุทธิต้องเป็นบวก"),
                GateCheck("Win Rate", f">={self.criteria.min_win_rate_pct}%", "0%", False, "อัตราการชนะ"),
                GateCheck("Max Drawdown", f"<={self.criteria.max_drawdown_pct}%", "0%", True, "การย่อตัวสูงสุด"),
                GateCheck("Server SL Compliance", f"{self.criteria.min_sl_compliance_pct}%", "100%", True, "การตั้งจุดตัดขาดทุน"),
            ]
            return PromotionEvaluation(
                is_promotable=False,
                current_stage="PAPER",
                total_trades=0,
                wins=0,
                losses=0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                net_pnl=0.0,
                max_drawdown_pct=0.0,
                sl_compliance_pct=100.0,
                gate_checks=checks,
                summary_th=f"ยังไม่มีข้อมูลออเดอร์ที่ปิดในเดโม ต้องการอีกอย่างน้อย {self.criteria.min_trades} ไม้",
                recommendations_th=["รันการเทรดในโหมด Paper หรือ Testnet Demo เพื่อเก็บตัวอย่างสถิติ"],
            )

        wins = [t for t in parsed_trades if t["net_profit"] > 0]
        losses = [t for t in parsed_trades if t["net_profit"] < 0]
        total_profit = sum(t["net_profit"] for t in wins)
        total_loss = abs(sum(t["net_profit"] for t in losses))
        net_pnl = total_profit - total_loss
        profit_factor = total_profit / total_loss if total_loss > 0 else (99.0 if total_profit > 0 else 0.0)
        win_rate = (len(wins) / total) * 100.0

        # Max drawdown calculation
        equity = 10000.0
        peak = equity
        max_dd = 0.0
        for t in parsed_trades:
            equity += t["net_profit"]
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        # SL compliance
        with_sl = sum(1 for t in parsed_trades if t.get("sl", 0.0) > 0)
        sl_compliance = (with_sl / total) * 100.0

        checks = [
            GateCheck("Sample Size", f">={self.criteria.min_trades}", str(total), total >= self.criteria.min_trades, "จำนวนไม้ขั้นต่ำ"),
            GateCheck("Profit Factor", f">={self.criteria.min_profit_factor}", f"{profit_factor:.2f}", profit_factor >= self.criteria.min_profit_factor, "กำไรต่อขาดทุน"),
            GateCheck("Net PnL", "> $0", f"${net_pnl:+,.2f}", net_pnl > 0, "กำไรสุทธิ"),
            GateCheck("Win Rate", f">={self.criteria.min_win_rate_pct}%", f"{win_rate:.1f}%", win_rate >= self.criteria.min_win_rate_pct, "อัตราการชนะ"),
            GateCheck("Max Drawdown", f"<={self.criteria.max_drawdown_pct}%", f"{max_dd:.2f}%", max_dd <= self.criteria.max_drawdown_pct, "การย่อตัวสูงสุด"),
            GateCheck("Server SL Compliance", f"{self.criteria.min_sl_compliance_pct}%", f"{sl_compliance:.1f}%", sl_compliance >= self.criteria.min_sl_compliance_pct, "การตั้ง SL 100%"),
        ]

        is_promotable = all(c.passed for c in checks)
        stage = "READY_FOR_LIVE" if is_promotable else ("DEMO" if total >= 10 else "PAPER")

        recommendations: list[str] = []
        if total < self.criteria.min_trades:
            recommendations.append(f"สะสมข้อมูลเพิ่มอีก {self.criteria.min_trades - total} ไม้ เพื่อให้ตัวอย่างทางสถิติมีนัยสำคัญ")
        if profit_factor < self.criteria.min_profit_factor:
            recommendations.append(f"Profit Factor ปัจจุบัน {profit_factor:.2f} ต่ำกว่าเป้าหมาย {self.criteria.min_profit_factor} ควรทบทวน Setup ที่ขาดทุน")
        if max_dd > self.criteria.max_drawdown_pct:
            recommendations.append(f"Max Drawdown {max_dd:.2f}% สูงเกินเกณฑ์ {self.criteria.max_drawdown_pct}% ควรลด Risk per trade")
        if sl_compliance < 100.0:
            recommendations.append("ตรวจพบออเดอร์ที่ไม่มี Stop Loss ชัดเจน ห้ามเปิดระบบจริงเด็ดขาด")
        if is_promotable:
            recommendations.append("ผ่านเกณฑ์ทั้งหมด สามารถเปิดระบบจริงแบบ Graduated Live (เริ่มจาก 0.25% risk per trade และ min lot)")

        summary_th = (
            "ระบบผ่านการทดสอบครบทุกเกณฑ์เชิงสถิติ พร้อมสำหรับการเปิดระบบจริง"
            if is_promotable
            else f"ข้อมูลยังไม่ผ่านเกณฑ์การเปิดระบบจริง (ผ่าน {sum(1 for c in checks if c.passed)}/{len(checks)} เกณฑ์)"
        )

        return PromotionEvaluation(
            is_promotable=is_promotable,
            current_stage=stage,
            total_trades=total,
            wins=len(wins),
            losses=len(losses),
            win_rate_pct=round(win_rate, 1),
            profit_factor=round(profit_factor, 2),
            net_pnl=round(net_pnl, 2),
            max_drawdown_pct=round(max_dd, 2),
            sl_compliance_pct=round(sl_compliance, 1),
            gate_checks=checks,
            summary_th=summary_th,
            recommendations_th=recommendations,
        )

    async def evaluate_database(self, session: AsyncSession) -> PromotionEvaluation:
        """Query closed trades from database and evaluate."""
        stmt = select(Trade).where(Trade.status == "CLOSED").order_by(Trade.open_time.asc())
        result = await session.execute(stmt)
        trades = list(result.scalars().all())
        return self.evaluate_trades(trades)


async def _run_evaluation(min_trades: int = 30, min_pf: float = 1.50):
    from src.storage.additive_schema import ensure_additive_schema
    from src.storage.models import Base, get_engine

    engine = get_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_additive_schema(conn)

    async with AsyncSession(engine) as session:
        criteria = PromotionCriteria(min_trades=min_trades, min_profit_factor=min_pf)
        gate = PromotionGate(criteria)
        evaluation = await gate.evaluate_database(session)
        print("\n" + evaluation.summary())
    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Promotion Safety Gate Checker")
    parser.add_argument("--min-trades", type=int, default=30, help="Min required trades")
    parser.add_argument("--min-pf", type=float, default=1.50, help="Min required profit factor")
    args = parser.parse_args()

    asyncio.run(_run_evaluation(min_trades=args.min_trades, min_pf=args.min_pf))


if __name__ == "__main__":
    main()
