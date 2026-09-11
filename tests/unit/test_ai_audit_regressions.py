"""Regression cases found by the AI learning audit. No network or broker calls."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.gpt_evaluator import GPTEvaluator
from src.ai.gemini_evaluator import GeminiEvaluator
from src.core.types import Deal, Direction, Position, OrderRequest
from src.execution.outcomes import reconcile_deals
from src.execution.position_tracker import PositionTracker
from src.core.events import event_bus, EventType


@pytest.mark.parametrize('provider', [GPTEvaluator, GeminiEvaluator])
@pytest.mark.parametrize('raw', [
    'Do not APPROVE this setup.', 'APPROVE', '{}', '{"verdict":"APPROVE"}',
    '{"verdict":"APPROVE","confidence":999,"narrative":"x"}',
    'null', '["APPROVE"]', '{"verdict":"REJECT","verdict":"APPROVE"}',
])
def test_invalid_provider_response_never_approves(provider, raw):
    result = provider.__new__(provider)._parse_response(raw)
    assert result.verdict == 'REJECT'
    assert result.confidence == 0


@pytest.mark.parametrize('provider,extra', [
    (GPTEvaluator, {'bear_case': [], 'trap_identified': '', 'counter_argument': 'valid'}),
    (GeminiEvaluator, {'confluences': ['FVG'], 'risks': [], 'trap_warning': ''}),
])
def test_strict_provider_payload(provider, extra):
    data = dict(verdict='APPROVE', confidence=80, narrative='Evidence reviewed', **extra)
    evaluator = provider.__new__(provider)
    assert evaluator._parse_response(json.dumps(data)).verdict == 'APPROVE'
    for bad in [True, '80', -1, 101, float('nan')]:
        data['confidence'] = bad
        assert evaluator._parse_response(json.dumps(data)).verdict == 'REJECT'


def deals():
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    return [Deal(ticket=1, order=100, position_id=100, time=now, entry=0, type=0,
                 volume=1, price=2000, profit=0, commission=-2, symbol='XAUUSD'),
            Deal(ticket=2, order=101, position_id=100, time=now + timedelta(minutes=5), entry=1, type=1,
                 volume=.4, price=1995, profit=-200, commission=-1, symbol='XAUUSD'),
            Deal(ticket=3, order=102, position_id=100, time=now + timedelta(minutes=10), entry=1, type=1,
                 volume=.6, price=1990, profit=-600, commission=-1, swap=-3, fee=-1, symbol='XAUUSD')]


def test_reconciles_partial_exits_and_all_costs():
    outcome = reconcile_deals(100, deals())
    assert outcome.net_profit == -808
    assert outcome.close_price == 1992
    assert outcome.opening_order == 100


@pytest.mark.parametrize('case', ['partial', 'duplicate', 'reversal', 'multiple_entry', 'wrong_position'])
def test_incomplete_or_ambiguous_history_is_not_a_label(case):
    history = deals()
    if case == 'partial': history.pop()
    if case == 'duplicate': history.append(history[-1])
    if case == 'reversal': history[-1] = history[-1].model_copy(update={'entry': 2})
    if case == 'multiple_entry': history.append(history[0].model_copy(update={'ticket': 10}))
    if case == 'wrong_position': history[-1] = history[-1].model_copy(update={'position_id': 999})
    assert reconcile_deals(100, history) is None


@pytest.mark.asyncio
async def test_tracker_retries_history_and_never_uses_last_floating_profit(monkeypatch):
    gateway = MagicMock()
    pos = Position(ticket=100, symbol='XAUUSD', direction=Direction.BUY,
                   volume=1, open_price=2000, profit=999)
    gateway.get_positions = AsyncMock(side_effect=[[pos], [], [], []])
    gateway.get_position_deals = AsyncMock(side_effect=[[], deals()])
    publish = AsyncMock()
    monkeypatch.setattr(event_bus, 'publish', publish)
    tracker = PositionTracker(gateway)
    await tracker.sync_positions()
    await tracker.sync_positions()
    assert tracker.get_position(100) is not None
    await tracker.sync_positions()
    await tracker.sync_positions()
    closed = [c.args[1] for c in publish.call_args_list if c.args[0] == EventType.POSITION_CLOSED]
    assert len(closed) == 1
    assert closed[0]['position'].profit == -808


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['paper', 'live', 'unknown'])
async def test_order_manager_never_sends_broker_order_in_paper_or_live(monkeypatch, mode):
    from src.execution.order_manager import OrderManager
    from src.core.config import settings
    monkeypatch.setattr(settings, 'trading_mode', mode)
    gateway = MagicMock(send_order=AsyncMock())
    result = await OrderManager(gateway).send_market_order(OrderRequest(
        symbol='XAUUSD', direction=Direction.BUY, volume=.01, sl=1900, tp=2100))
    assert not result.success
    gateway.send_order.assert_not_called()


def test_adaptation_does_not_change_scores():
    from src.strategies.meta_engine import MetaDecisionEngine
    engine = MetaDecisionEngine()
    for outcome in ['WIN', 'LOSS', 'BREAKEVEN'] * 20:
        engine.adjust_strategy('fvg', outcome)
    assert engine.get_strategy_health()['fvg']['score_delta'] == 0


def test_startup_components_and_no_auth_side_effects(monkeypatch):
    from src.app import TradingPlatform, setup_auth_credentials
    monkeypatch.delenv('CODEX_AUTH_JSON', raising=False)
    monkeypatch.delenv('GOOGLE_ADC_JSON', raising=False)
    setup_auth_credentials()
    platform = TradingPlatform()
    assert platform._ai_council is not None
    assert platform._eql_detector is not None


@pytest.mark.asyncio
async def test_candidate_context_reaches_council_then_risk_can_reject(monkeypatch):
    from src.app import TradingPlatform
    from src.core.types import StrategyCandidate, AIDecision, RiskDecision, MarketStructure
    from src.structure.context import MultiTimeframeContext
    platform = TradingPlatform()
    candidate = StrategyCandidate(strategy_id='fvg', strategy_name='FVG', symbol='XAUUSD',
        timeframe='M5', direction=Direction.BUY, entry_price=2000, stop_loss=1990,
        take_profit_1=2020, rule_score=80)
    context = MultiTimeframeContext(symbol='XAUUSD', structures={
        'H1': MarketStructure(timeframe='H1', trend=Direction.BUY),
        'M15': MarketStructure(timeframe='M15', trend=Direction.BUY)})
    platform._ai_scorer.score = MagicMock(return_value=AIDecision(candidate=candidate, decision='BUY'))
    council = MagicMock(should_execute=True)
    platform._ai_council.evaluate = AsyncMock(return_value=council)
    platform._mt5.get_account_info = AsyncMock(return_value=MagicMock(balance=10000, equity=10000))
    platform._position_tracker.sync_positions = AsyncMock(return_value=[])
    platform._risk_engine = MagicMock(evaluate=AsyncMock(return_value=RiskDecision(approved=False)))
    platform._order_manager.send_market_order = AsyncMock()
    await platform._process_candidate(candidate, context, 2000, 1, 'london')
    payload = platform._ai_council.evaluate.call_args.args[0]
    assert 'BUY' in payload['h1_structure']
    assert 'BUY' in payload['m15_structure']
    assert payload['rule_score'] == 80
    platform._risk_engine.evaluate.assert_awaited_once()
    platform._order_manager.send_market_order.assert_not_called()


@pytest.mark.asyncio
async def test_forming_candle_is_not_used_by_main_loop(monkeypatch):
    from src.app import TradingPlatform
    from src.core.types import Candle, Tick
    platform = TradingPlatform(max_cycles=1)
    stamp = datetime(2026, 9, 10, tzinfo=timezone.utc)
    closed = Candle(timestamp=stamp, open=2000, high=2001, low=1999, close=2000)
    forming = Candle(timestamp=stamp + timedelta(minutes=5), open=2000, high=2100, low=1900, close=2050)
    platform._data_feed.get_cached_candles = MagicMock(return_value=[closed, forming])
    platform._mt5.get_current_price = AsyncMock(return_value=Tick(timestamp=stamp, bid=2000, ask=2000.1))
    platform._position_tracker.sync_positions = AsyncMock(return_value=[])
    platform._process_strategies = AsyncMock()
    monkeypatch.setattr('src.app.asyncio.sleep', AsyncMock())
    platform._running = True
    await platform._main_loop('XAUUSD')
    assert platform._cycle_errors == 0
    context = platform._process_strategies.call_args.args[0]
    assert context.primary_candle.timestamp == closed.timestamp
    assert context.candles_by_tf['H1'] == [closed]


@pytest.mark.parametrize('reward,risk,expected', [(20, 10, 2), (30, 10, 3), (20, 0, 0), (-20, 10, 0)])
def test_reward_risk_is_distance_ratio(reward, risk, expected):
    from src.core.ratios import reward_risk
    assert reward_risk(reward, risk) == expected


@pytest.mark.parametrize('side', ['buy', 'sell'])
def test_fvg_range_reward_risk_is_two_for_both_directions(side):
    from src.strategies.fvg_final import FVGFinalStrategy
    from src.structure.context import MultiTimeframeContext
    from src.core.types import Candle
    context = MultiTimeframeContext(symbol='XAUUSD')
    candle = Candle(timestamp=datetime(2026, 9, 10), open=2000, high=2030, low=1990, close=2000)
    strategy = FVGFinalStrategy()
    method = strategy._check_range_buy if side == 'buy' else strategy._check_range_sell
    result = method(context, candle, 2000, 1, 'london', MagicMock(confidence=.8), 1990, 2030)
    assert result.rr_ratio == 2


def test_gemini_without_cli_is_unavailable(monkeypatch):
    import src.ai.gemini_evaluator as module
    monkeypatch.setattr(module.GeminiEvaluator, '_find_cli', staticmethod(lambda: None))
    evaluator = module.GeminiEvaluator()
    assert evaluator._cli_bin is None


@pytest.mark.asyncio
async def test_gemini_cli_response_is_validated(monkeypatch):
    import src.ai.gemini_evaluator as module
    evaluator = module.GeminiEvaluator.__new__(module.GeminiEvaluator)
    evaluator._cli_bin = '/usr/bin/agy'
    process = MagicMock(returncode=0)
    output = json.dumps({'structured_output': {'verdict': 'REJECT', 'confidence': 80,
        'narrative': 'Insufficient evidence', 'confluences': [], 'risks': ['missing'], 'trap_warning': ''}})
    process.communicate = AsyncMock(return_value=(output.encode(), b''))
    monkeypatch.setattr(module.asyncio, 'create_subprocess_exec', AsyncMock(return_value=process))
    result = await evaluator.evaluate({'symbol': 'XAUUSD'})
    assert result.verdict == 'REJECT' and result.confidence == 80
    command = module.asyncio.create_subprocess_exec.await_args.args
    assert command[:3] == ('/usr/bin/agy', '--print', command[2])
    assert '--json-schema' in command and '--sandbox' in command
    assert ('--mode', 'plan') == (command[command.index('--mode')], command[command.index('--mode') + 1])


def test_antigravity_response_fallback_is_strict():
    from src.ai.gemini_evaluator import GeminiEvaluator
    output = {
        'response': '{"verdict":"APPROVE","confidence":70,"narrative":"ok",'
                    '"confluences":[],"risks":[],"trap_warning":""}\n'
                    '{"toolAction":"Finishing task"}',
    }
    parsed = GeminiEvaluator._extract_structured_output(json.dumps(output).encode())
    assert json.loads(parsed)['verdict'] == 'APPROVE'
