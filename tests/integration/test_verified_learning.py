"""Persist entry evidence, reconcile, recover after restart, and build labels."""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.storage.models import Base, TradeMemory, LearningEvidence
from src.ai.trade_learner import TradeLearner
from src.ai.ml_trainer import MLTrainer
from src.execution.outcomes import reconcile_deals
from tests.unit.test_ai_audit_regressions import deals


@pytest.mark.asyncio
async def test_memory_exactly_once_costs_r_multiple_dataset_and_restart(tmp_path):
    path = tmp_path / 'test.db'
    engine = create_async_engine(f'sqlite+aiosqlite:///{path}')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    learner = TradeLearner(factory)
    learner.account_key = 'demo/123'
    snapshot = {'schema_version': '1.0.0', 'strategy': 'fvg', 'symbol': 'XAUUSD',
        'direction': 'BUY', 'timestamp': datetime(2026, 9, 10, tzinfo=timezone.utc).isoformat(),
        'entry_price': 2000, 'rule_score': 80, 'rr': 2, 'spread': 1, 'session': 'london',
        'pip_size': .1, 'market_context': {'htf_trend': 'bullish'}}
    await learner.record_entry(account_key=learner.account_key, opening_order=100,
                               snapshot=snapshot, initial_risk=400)
    learner.close()
    # New instance recovers an order closed while the process was offline.
    learner = TradeLearner(factory)
    learner.account_key = 'demo/123'
    gateway = MagicMock(get_positions=AsyncMock(return_value=[]), get_position_deals=AsyncMock(return_value=deals()))
    await learner.reconcile_pending(gateway)
    await learner.process_outcome(reconcile_deals(100, deals()))
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(TradeMemory)) == 1
        memory = await session.scalar(select(TradeMemory))
        assert float(memory.profit) == -808
        assert float(memory.rr_achieved) == -2.02
        assert memory.root_cause == 'UNDETERMINED'
    assert len(await learner.get_lessons_for_prompt('XAUUSD', 'fvg')) == 1
    learner.account_key = 'other/123'
    assert await learner.get_lessons_for_prompt('XAUUSD', 'fvg') == []
    trainer = MLTrainer(str(tmp_path / 'models'))
    X, y = trainer.load_dataset(str(path))
    assert len(X) == 1 and y.tolist() == [0]
    learner.close()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('net,label', [(10, 'WIN'), (0, 'BREAKEVEN'), (-10, 'LOSS')])
async def test_labels_use_verified_net_profit_without_causal_claims(tmp_path, net, label):
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    learner = TradeLearner(factory)
    learner.account_key = 'test/1'
    await learner.record_entry(account_key='test/1', opening_order=100,
        snapshot={'symbol': 'XAUUSD', 'direction': 'BUY', 'strategy': 'fvg', 'entry_price': 2000}, initial_risk=None)
    result = reconcile_deals(100, deals()).model_copy(update={'net_profit': net})
    await learner.process_outcome(result)
    async with factory() as session:
        memory = await session.scalar(select(TradeMemory))
        assert memory.outcome == label
        assert memory.rr_achieved is None
        assert memory.root_cause == 'UNDETERMINED'
    learner.close()
    await engine.dispose()
