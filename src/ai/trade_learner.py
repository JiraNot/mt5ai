"""Evidence-only trade learning v2.0.0.

No causal diagnosis from PnL alone, no score or risk mutation. Legacy memories
are retained for audit but never fed back into decisions or model training.
"""
from __future__ import annotations
import asyncio
import json
import logging
from sqlalchemy import select, update
from src.core.events import EventType, event_bus
from src.core.types import ClosedOutcome
from src.storage.models import LearningEvidence, TradeMemory
from src.execution.outcomes import reconcile_deals

logger = logging.getLogger(__name__)

class TradeLearner:
    VERSION = "2.0.0"

    def __init__(self, repository_factory, gemini_evaluator=None, gpt_evaluator=None):
        self._repo_factory = repository_factory
        self.account_key = ""
        self._lock = asyncio.Lock()
        event_bus.subscribe(EventType.POSITION_CLOSED, self._on_position_closed_event)

    def close(self):
        event_bus.unsubscribe(EventType.POSITION_CLOSED, self._on_position_closed_event)

    async def record_entry(self, *, account_key, opening_order, snapshot, initial_risk, setup_id=None):
        """Record only our filled orders, using the approved initial monetary risk."""
        key = f"{account_key}/{opening_order}"
        async with self._repo_factory() as session:
            if await session.get(LearningEvidence, key):
                return
            session.add(LearningEvidence(
                key=key, account_key=account_key, opening_order=opening_order,
                position_id=opening_order, setup_id=setup_id,
                snapshot_json=json.dumps(snapshot),
                initial_risk=initial_risk if initial_risk and initial_risk > 0 else None,
            ))
            await session.commit()

    async def link_setup(self, account_key, opening_order, setup_id):
        async with self._repo_factory() as session:
            await session.execute(update(LearningEvidence).where(
                LearningEvidence.key == f"{account_key}/{opening_order}"
            ).values(setup_id=setup_id))
            await session.commit()

    async def _on_position_closed_event(self, data):
        outcome = data.get("outcome")
        if isinstance(outcome, ClosedOutcome):
            await self.process_outcome(outcome)

    async def process_outcome(self, outcome: ClosedOutcome):
        if not self.account_key:
            return
        async with self._lock:
            async with self._repo_factory() as session:
                evidence = await session.get(LearningEvidence, f"{self.account_key}/{outcome.opening_order}")
                if evidence is None or evidence.outcome_json is not None:
                    return
                claimed = await session.execute(update(LearningEvidence).where(
                    LearningEvidence.key == evidence.key,
                    LearningEvidence.outcome_json.is_(None),
                ).values(outcome_json=outcome.model_dump_json()))
                if claimed.rowcount != 1:
                    return
                snapshot = json.loads(evidence.snapshot_json)
                if snapshot["symbol"] != outcome.symbol:
                    raise ValueError("Outcome symbol does not match entry evidence")
                profit = outcome.net_profit
                label = "WIN" if profit > 0 else "LOSS" if profit < 0 else "BREAKEVEN"
                risk = float(evidence.initial_risk or 0)
                r_multiple = profit / risk if risk > 0 else None
                # Facts only: a winner does not prove confluence; a loss does not prove a trap.
                lesson = (f"ผลปิดยืนยันจาก broker: {label}, กำไรสุทธิ {profit:.2f}; "
                          "ผลรายไม้ยังไม่ยืนยันสาเหตุหรือความได้เปรียบของกลยุทธ์")
                pip_size = snapshot.get("pip_size")
                movement = outcome.close_price - (snapshot.get("fill_price") or snapshot["entry_price"])
                if snapshot["direction"] == "SELL":
                    movement = -movement
                memory = TradeMemory(
                    ticket=outcome.position_id, symbol=outcome.symbol,
                    strategy_id=snapshot["strategy"], direction=snapshot["direction"],
                    outcome=label, profit=profit,
                    pips=movement / pip_size if pip_size and pip_size > 0 else None,
                    rr_achieved=r_multiple, root_cause="UNDETERMINED",
                    lesson_learned_th=lesson,
                    rule_recommendation="ตรวจสอบหลายตัวอย่างและ walk-forward ก่อนปรับกลยุทธ์",
                    setup_snapshot=json.dumps({"version": self.VERSION, "entry": snapshot,
                                               "outcome": outcome.model_dump(mode="json")}),
                )
                session.add(memory)
                await session.flush()
                evidence.memory_id = memory.id
                evidence.position_id = outcome.position_id
                evidence.outcome_json = outcome.model_dump_json()
                await session.commit()  # Outcome and memory are one transaction.

    async def reconcile_pending(self, gateway):
        """Recover missed closes after restart; never label an open/incomplete position."""
        if not self.account_key:
            return
        positions = await gateway.get_positions()
        open_ids = {p.identifier or p.ticket for p in positions}
        async with self._repo_factory() as session:
            rows = list((await session.execute(select(LearningEvidence).where(
                LearningEvidence.account_key == self.account_key,
                LearningEvidence.outcome_json.is_(None),
            ))).scalars())
            pending = [(row.position_id, row.opening_order) for row in rows]
        for position_id, opening_order in pending:
            if position_id in open_ids:
                continue
            try:
                outcome = reconcile_deals(position_id, await gateway.get_position_deals(position_id))
                if outcome and outcome.opening_order == opening_order:
                    await self.process_outcome(outcome)
            except Exception:
                logger.exception("History pending for %s", position_id)

    async def get_lessons_for_prompt(self, symbol, strategy_id=None, limit=3):
        if not self.account_key:
            return []
        async with self._repo_factory() as session:
            query = select(TradeMemory).join(
                LearningEvidence, LearningEvidence.memory_id == TradeMemory.id
            ).where(LearningEvidence.account_key == self.account_key, TradeMemory.symbol == symbol)
            if strategy_id:
                query = query.where(TradeMemory.strategy_id == strategy_id)
            rows = (await session.execute(query.order_by(TradeMemory.created_at.desc()).limit(limit))).scalars()
            return [f"[{m.outcome}] {m.strategy_id} {m.direction}: {m.lesson_learned_th}" for m in rows]
