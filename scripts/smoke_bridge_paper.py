"""Bounded real-feed smoke test; PAPER only, no broker orders or notifications.

Run with MT5_MODE=bridge and BRIDGE_URL/BRIDGE_TOKEN configured. Output is a JSON
summary. Database is temporary; no account credentials or balances are printed.
"""
import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

os.environ['TRADING_MODE'] = 'paper'
os.environ['TELEGRAM_BOT_TOKEN'] = ''
os.environ['TELEGRAM_CHAT_ID'] = ''
os.environ.pop('CODEX_AUTH_JSON', None)
os.environ.pop('GOOGLE_ADC_JSON', None)

from src.app import TradingPlatform
from src.core.config import settings
from src.notification import telegram_alert


async def main():
    if settings.mt5_mode != 'bridge':
        raise RuntimeError('Set MT5_MODE=bridge')
    # Explicitly suppress outbound messaging, including any module-level settings.
    async def no_notification(*args, **kwargs):
        return None
    telegram_alert.send_message = no_notification
    with tempfile.TemporaryDirectory(prefix='mt5-paper-smoke-') as directory:
        settings.database_url = f'sqlite+aiosqlite:///{directory}/smoke.db'
        platform = TradingPlatform(max_cycles=2)
        summary = {'mode': settings.trading_mode, 'cycles': 0, 'cycle_errors': 0}
        original_connect = platform._mt5.connect
        async def connect():
            if not await original_connect():
                raise RuntimeError('Bridge or terminal unavailable')
            symbol = settings.primary_symbol
            candles = await platform._mt5.get_ohlcv(symbol, 'M5', 10)
            tick = await platform._mt5.get_current_price(symbol)
            summary.update(symbol=symbol, candles=len(candles), bid=tick.bid, ask=tick.ask,
                           last_bar=candles[-1].timestamp.isoformat() if candles else None,
                           open_positions=len(await platform._mt5.get_positions(symbol)))
            summary['history_endpoint'] = isinstance(await platform._mt5.get_position_deals(0), list)
            return True
        platform._mt5.connect = connect
        # Defence in depth: a smoke run must never reach gateway mutation methods.
        async def forbid_order(*args, **kwargs):
            raise AssertionError('Smoke test attempted a broker mutation')
        platform._mt5.send_order = forbid_order
        platform._mt5.modify_position = forbid_order
        platform._mt5.close_position = forbid_order
        try:
            await asyncio.wait_for(platform.start(), timeout=180)
            summary.update(cycles=platform._cycle_count, cycle_errors=platform._cycle_errors)
            if summary['cycle_errors'] or summary['cycles'] != 2:
                raise RuntimeError(f'Incomplete smoke run: {summary}')
            print(json.dumps(summary, indent=2))
        finally:
            if platform._running:
                await platform.stop()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
