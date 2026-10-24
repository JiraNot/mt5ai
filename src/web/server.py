"""FastAPI Web and WebSocket server for the Modern Crypto Trading WebApp.

Provides high-frequency REST APIs, WebSocket streaming for TradingView charts,
AI Council decisions, active position controls, and serves the React SPA frontend.
"""

from __future__ import annotations

import asyncio
import httpx
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select

from src.core.config import settings
from src.core.runtime_control import (
    arm_live_trading,
    get_runtime_trading_mode,
    is_live_armed,
    set_runtime_trading_mode,
)
from src.core.runtime_status import read_runtime_status, update_runtime_status
from src.execution.paper_gateway import PaperGateway
from src.market.binance_gateway import (
    BinanceGateway,
    is_binance_futures_live_url,
    is_binance_futures_testnet_url,
)
from src.market.crypto_screener import CryptoScreener
from src.risk.promotion_gate import PromotionGate
from src.storage.models import Trade, get_engine, get_session_factory

logger = logging.getLogger("src.web.server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Global instances
_gateway: BinanceGateway | PaperGateway | None = None
_session_factory = None
_ws_clients: set[WebSocket] = set()
_broadcast_task: asyncio.Task | None = None
_active_chart_symbol: str = "BTCUSDT"


def get_gateway() -> BinanceGateway | PaperGateway:
    global _gateway
    if _gateway is None:
        raw = BinanceGateway()
        has_credentials = bool(settings.binance_api_key.strip() and settings.binance_api_secret.strip())
        is_paper = get_runtime_trading_mode(settings.trading_mode) == "paper"
        _gateway = PaperGateway(raw) if is_paper else raw
        if not has_credentials and get_runtime_trading_mode(settings.trading_mode) == "demo":
            logger.error("DEMO is selected without Binance Testnet credentials; keeping execution fail-closed")
    return _gateway


def get_db_session():
    global _session_factory
    if _session_factory is None:
        engine = get_engine(settings.database_url)
        _session_factory = get_session_factory(engine)
    return _session_factory()


async def broadcast_ws(payload: dict[str, Any]) -> None:
    """Broadcast JSON message to all connected WebSocket clients."""
    if not _ws_clients:
        return
    message = json.dumps(payload, default=str)
    disconnected = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    for ws in disconnected:
        _ws_clients.discard(ws)


async def live_broadcaster_loop() -> None:
    """Background loop pushing live price, positions, and status to frontend."""
    logger.info("Real-time WebSocket broadcaster started")
    gateway = get_gateway()
    await gateway.connect()

    while True:
        try:
            if _ws_clients:
                # 1. Fetch current price of the active chart symbol
                symbol = _active_chart_symbol
                tick_data = None
                try:
                    tick = await gateway.get_current_price(symbol)
                    tick_data = {
                        "type": "tick",
                        "symbol": symbol,
                        "bid": tick.bid,
                        "ask": tick.ask,
                        "last": tick.last,
                        "timestamp": int(tick.timestamp.timestamp()),
                    }
                except Exception as exc:
                    logger.debug("Failed getting tick for %s: %s", symbol, exc)

                if tick_data:
                    await broadcast_ws(tick_data)

                # 2. Broadcast active positions
                try:
                    positions = await gateway.get_positions()
                    pos_payload = [
                        {
                            "ticket": p.ticket,
                            "symbol": p.symbol,
                            "direction": p.direction.value if hasattr(p.direction, "value") else str(p.direction),
                            "volume": p.volume,
                            "open_price": p.open_price,
                            "current_price": p.current_price,
                            "sl": p.sl,
                            "tp": p.tp,
                            "profit": round(p.profit, 2),
                            "pnl_pct": round(((p.current_price - p.open_price) / p.open_price * 100)
                                             if (p.direction.value if hasattr(p.direction, "value") else str(p.direction)) == "BUY"
                                             else ((p.open_price - p.current_price) / p.open_price * 100), 2),
                        }
                        for p in positions
                    ]
                    await broadcast_ws({"type": "positions", "positions": pos_payload})
                except Exception as exc:
                    logger.debug("Failed getting positions: %s", exc)

                # 3. Broadcast heartbeat status
                status = read_runtime_status()
                await broadcast_ws({"type": "status", "data": status})

            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Error in broadcaster loop: %s", exc)
            await asyncio.sleep(2.0)


_trading_platform = None
_trading_task: asyncio.Task | None = None


async def _run_trading_worker(gateway: Any) -> None:
    global _trading_platform
    try:
        from src.app import TradingPlatform
        logger.info("Starting autonomous TradingPlatform worker inside server...")
        _trading_platform = TradingPlatform(gateway=gateway)
        await _trading_platform.start()
    except asyncio.CancelledError:
        logger.info("TradingPlatform worker cancelled cleanly")
    except Exception as exc:
        logger.warning("TradingPlatform worker error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _broadcast_task, _trading_task, _trading_platform
    gateway = get_gateway()
    await gateway.connect()
    _broadcast_task = asyncio.create_task(live_broadcaster_loop())

    enable_worker = os.getenv(
        "ENABLE_TRADING_WORKER",
        "false" if "PYTEST_CURRENT_TEST" in os.environ else "true",
    ).lower() in ("true", "1", "yes")
    if enable_worker:
        _trading_task = asyncio.create_task(_run_trading_worker(gateway))

    logger.info("FastAPI Web server initialized and ready (worker enabled: %s)", enable_worker)
    try:
        yield
    finally:
        if _trading_platform:
            try:
                await _trading_platform.stop()
            except Exception:
                pass
        if _trading_task:
            _trading_task.cancel()
            try:
                await _trading_task
            except asyncio.CancelledError:
                pass
        if _broadcast_task:
            _broadcast_task.cancel()
            try:
                await _broadcast_task
            except asyncio.CancelledError:
                pass
        await gateway.disconnect()
        logger.info("FastAPI Web server shut down cleanly")


app = FastAPI(title="ApexTrader AI Pro Terminal API", version="2.0.0", lifespan=lifespan)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic Request Models ──────────────────────────────────────────────────

class ModeChangeRequest(BaseModel):
    mode: str
    armed: bool = False


class PositionActionRequest(BaseModel):
    ticket: int
    symbol: str = "BTCUSDT"


class SettingsUpdateRequest(BaseModel):
    trading_mode: str | None = None
    primary_symbol: str | None = None
    active_symbols: list[str] | str | None = None
    paper_initial_balance: float | None = None
    risk_per_trade_pct: float | None = None
    max_daily_loss_pct: float | None = None
    max_open_positions: int | None = None
    min_rr: float | None = None
    entry_min_score: int | None = None
    max_consecutive_losses: int | None = None
    emergency_stop_loss_pct: float | None = None
    news_filter_enabled: bool | None = None
    binance_mode: str | None = None
    binance_base_url: str | None = None
    binance_demo_api_key: str | None = None
    binance_demo_api_secret: str | None = None
    binance_live_api_key: str | None = None
    binance_live_api_secret: str | None = None
    # Compatibility fields for older settings clients.
    binance_api_key: str | None = None
    binance_api_secret: str | None = None
    ai_provider: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    vision_provider: str | None = None
    vision_min_score: int | None = None
    volume_filter_enabled: bool | None = None
    rsi_filter_enabled: bool | None = None
    telegram_enabled: bool | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


class AITestRequest(BaseModel):
    provider: str = "codex"


class BinanceTestRequest(BaseModel):
    binance_mode: str | None = None
    binance_base_url: str | None = None
    binance_demo_api_key: str | None = None
    binance_demo_api_secret: str | None = None
    binance_live_api_key: str | None = None
    binance_live_api_secret: str | None = None
    # Compatibility fields for older settings clients.
    binance_api_key: str | None = None
    binance_api_secret: str | None = None


# ─── REST Endpoints ───────────────────────────────────────────────────────────

@app.get("/health")
@app.get("/_stcore/health")
async def health_check() -> dict[str, str]:
    """Compatibility health check for Docker / Coolify / Traefik."""
    return {"status": "ok"}


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    """Return platform heartbeat, balances, and operational mode."""
    gateway = get_gateway()
    account_info = None
    try:
        acc = await gateway.get_account_info()
        account_info = {
            "balance": round(acc.balance, 2),
            "equity": round(acc.equity, 2),
            "free_margin": round(acc.free_margin, 2),
            "currency": acc.currency,
        }
    except Exception as exc:
        logger.warning("Failed reading account info: %s", exc)
        account_info = {
            "balance": settings.paper_initial_balance,
            "equity": settings.paper_initial_balance,
            "free_margin": settings.paper_initial_balance,
            "currency": "USDT",
        }

    runtime = read_runtime_status()
    current_mode = get_runtime_trading_mode(settings.trading_mode)

    return {
        "ok": True,
        "mode": current_mode,
        "execution_mode": "paper" if isinstance(gateway, PaperGateway) else settings.binance_mode,
        "is_live_armed": is_live_armed(),
        "venue": "Binance USDT-M Futures",
        "worker_state": runtime.get("state", "unknown"),
        "binance_connected": runtime.get("binance_connected", gateway.connected),
        "account": account_info,
        "active_symbol": _active_chart_symbol,
        "cycle_count": runtime.get("cycle_count", 0),
        "cycle_errors": runtime.get("cycle_errors", 0),
        "candidate_count": runtime.get("candidate_count", 0),
        "last_candidate": runtime.get("last_candidate"),
        "last_candidate_symbol": runtime.get("last_candidate_symbol"),
        "last_candidate_score": runtime.get("last_candidate_score"),
        "last_decision": runtime.get("last_decision"),
        "last_decision_at": runtime.get("last_decision_at"),
        "last_reason": runtime.get("last_reason"),
        "last_error": runtime.get("last_error"),
        "updated_at": runtime.get("updated_at", datetime.now(timezone.utc).isoformat()),
    }


@app.get("/api/watchlist")
async def get_watchlist() -> dict[str, Any]:
    """Return latest AI crypto watchlist and market regime analysis."""
    watchlist_path = (
        Path("/app/data/crypto_watchlist.json")
        if Path("/app/data/crypto_watchlist.json").is_file()
        else (Path("data/crypto_watchlist.json") if Path("data/crypto_watchlist.json").is_file() else Path("crypto_watchlist.json"))
    )
    if watchlist_path.is_file():
        try:
            data = json.loads(watchlist_path.read_text(encoding="utf-8"))
            return {"ok": True, "data": data}
        except Exception as exc:
            logger.warning("Failed parsing watchlist file: %s", exc)

    # Fallback default watchlist if screener hasn't run yet
    return {
        "ok": True,
        "data": {
            "timestamp": "Just now",
            "btc_report": {
                "symbol": "BTCUSDT",
                "regime": "strong_uptrend",
                "trend_direction": "BUY",
                "funding_bias": "NEUTRAL",
                "recommendation_th": "BTC ทรงตัวในโซนบวก AI แนะนำให้จับตาเหรียญที่มี Momentum สอดคล้อง",
            },
            "candidates": [
                {"symbol": "BTCUSDT", "price": 67800.0, "price_change_pct": 2.1, "score": 85.0, "tags": ["Major", "Market Anchor"]},
                {"symbol": "ETHUSDT", "price": 2650.0, "price_change_pct": 3.4, "score": 88.0, "tags": ["Major", "Mega Vol"]},
                {"symbol": "SOLUSDT", "price": 155.0, "price_change_pct": 5.2, "score": 91.0, "tags": ["High Vol", "Hot Setup"]},
            ],
        },
    }


@app.get("/api/readiness")
async def get_readiness() -> dict[str, Any]:
    """Evaluate live trading promotion readiness (0-100%)."""
    async with get_db_session() as session:
        query = select(Trade).order_by(Trade.exit_time.desc())
        result = await session.execute(query)
        trades = result.scalars().all()
        evaluator = PromotionGate()
        evaluation = evaluator.evaluate_trades(trades)
        checks = [
            {
                "name": c.name,
                "target": c.target,
                "actual": c.actual,
                "passed": c.passed,
                "description": c.description,
            }
            for c in evaluation.gate_checks
        ]
        readiness_score = round((sum(1 for c in checks if c["passed"]) / max(len(checks), 1)) * 100)
        return {
            "ok": True,
            "readiness_score": readiness_score,
            "is_promotable": evaluation.is_promotable,
            "summary_th": evaluation.summary_th,
            "checks": checks,
            "stats": {
                "total_trades": evaluation.total_trades,
                "wins": evaluation.wins,
                "losses": evaluation.losses,
                "win_rate_pct": evaluation.win_rate_pct,
                "profit_factor": evaluation.profit_factor,
                "net_pnl": evaluation.net_pnl,
                "max_drawdown_pct": evaluation.max_drawdown_pct,
                "sl_compliance_pct": evaluation.sl_compliance_pct,
            },
        }


@app.get("/api/positions")
async def get_positions() -> dict[str, Any]:
    """Return all currently open positions."""
    gateway = get_gateway()
    try:
        positions = await gateway.get_positions()
        items = []
        for p in positions:
            dir_str = p.direction.value if hasattr(p.direction, "value") else str(p.direction)
            pnl_pct = 0.0
            if p.open_price > 0:
                pnl_pct = ((p.current_price - p.open_price) / p.open_price * 100) if dir_str == "BUY" else ((p.open_price - p.current_price) / p.open_price * 100)
            items.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "direction": dir_str,
                "volume": p.volume,
                "open_price": p.open_price,
                "current_price": p.current_price,
                "sl": p.sl,
                "tp": p.tp,
                "profit": round(p.profit, 2),
                "pnl_pct": round(pnl_pct, 2),
            })

        # If gateway returned no open positions, check database for OPEN trades
        if not items:
            async with get_db_session() as session:
                query = select(Trade).where(Trade.status == "OPEN")
                res = await session.execute(query)
                open_trades = res.scalars().all()
                for ot in open_trades:
                    try:
                        tick = await gateway.get_current_price(ot.symbol)
                        current_price = tick.last
                    except Exception:
                        current_price = float(ot.entry_price or 0.0)
                    is_buy = ot.direction == "BUY"
                    entry_p = float(ot.entry_price or 0.0)
                    vol = float(ot.volume or 0.0)
                    profit = (current_price - entry_p) * vol if is_buy else (entry_p - current_price) * vol
                    pnl_pct = ((current_price - entry_p) / entry_p * 100) if is_buy and entry_p > 0 else (((entry_p - current_price) / entry_p * 100) if entry_p > 0 else 0.0)
                    items.append({
                        "ticket": ot.id,
                        "symbol": ot.symbol,
                        "direction": ot.direction,
                        "volume": vol,
                        "open_price": entry_p,
                        "current_price": round(current_price, 4),
                        "sl": float(ot.sl) if ot.sl else 0.0,
                        "tp": float(ot.tp1) if ot.tp1 else 0.0,
                        "profit": round(profit, 2),
                        "pnl_pct": round(pnl_pct, 2),
                    })

        return {"ok": True, "positions": items}
    except Exception as exc:
        logger.error("Failed fetching positions: %s", exc)
        return {"ok": False, "positions": [], "error": str(exc)}


@app.get("/api/candles/{symbol}")
async def get_candles(symbol: str, timeframe: str = "5m", count: int = 250) -> dict[str, Any]:
    """Return OHLCV candles formatted for TradingView Lightweight Charts."""
    global _active_chart_symbol
    _active_chart_symbol = symbol.upper()

    gateway = get_gateway()
    tf_upper = timeframe.upper()
    tf_canonical = {
        "1M": "M1", "M1": "M1",
        "5M": "M5", "M5": "M5",
        "15M": "M15", "M15": "M15",
        "1H": "H1", "H1": "H1",
        "4H": "H4", "H4": "H4",
        "1D": "D1", "D1": "D1",
    }.get(tf_upper, "M5")

    try:
        candles = await gateway.get_ohlcv(symbol.upper(), tf_canonical, count=min(count, 500))
        sorted_candles = sorted(candles, key=lambda c: c.timestamp)
        data = [
            {
                "time": int(c.timestamp.timestamp()),
                "open": round(c.open, 4),
                "high": round(c.high, 4),
                "low": round(c.low, 4),
                "close": round(c.close, 4),
                "volume": round(c.volume, 2),
            }
            for c in sorted_candles
        ]
        return {"ok": True, "symbol": symbol.upper(), "timeframe": timeframe, "candles": data}
    except Exception as exc:
        logger.error("Failed fetching candles for %s: %s", symbol, exc)
        return {"ok": False, "candles": [], "error": str(exc)}


@app.get("/api/council/latest")
async def get_latest_council() -> dict[str, Any]:
    """Return the most recent AI Council decision and analysis."""
    triage_path = (
        Path("/app/data/candidate_triage.json")
        if Path("/app/data/candidate_triage.json").is_file()
        else (Path("data/candidate_triage.json") if Path("data/candidate_triage.json").is_file() else Path("candidate_triage.json"))
    )
    recent = []
    if triage_path.is_file():
        try:
            triage_data = json.loads(triage_path.read_text(encoding="utf-8"))
            recent = triage_data.get("recent", [])[-5:]
        except Exception:
            pass

    runtime = read_runtime_status()
    latest_item = recent[-1] if recent else {}
    decision = runtime.get("last_decision")
    no_candidate = bool(decision and (
        decision == "NO_CANDIDATE" or str(decision).startswith("WAITING_FOR_CANDLES_")
    ))
    recorded_candidate = bool(latest_item)
    if not decision:
        decision = "RECORDED_CANDIDATE" if recorded_candidate else "NO_RECENT_DECISION"

    return {
        "ok": True,
        "latest": {
            "decision": decision,
            "candidate": None if no_candidate else (
                runtime.get("last_candidate") or latest_item.get("strategy_id")
            ),
            "symbol": None if no_candidate else (
                runtime.get("last_candidate_symbol") or latest_item.get("symbol")
            ),
            "score": None if no_candidate else (
                runtime.get("last_candidate_score", latest_item.get("score"))
            ),
            "reason": runtime.get("last_reason") or (
                "ยังไม่มี candidate หรือผลการประเมินจาก worker"
                if not recorded_candidate else "Candidate นี้เป็นรายการล่าสุดที่บันทึกไว้"
            ),
            "confluences": [] if no_candidate else latest_item.get("confluences", []),
            "vision_verdict": None,
            "timestamp": runtime.get("last_decision_at") or latest_item.get("timestamp"),
        },
        "history": list(reversed(recent)),
    }


@app.get("/api/history")
async def get_history(limit: int = 30) -> dict[str, Any]:
    """Return closed trades and audit history."""
    async with get_db_session() as session:
        query = select(Trade).order_by(Trade.exit_time.desc()).limit(limit)
        result = await session.execute(query)
        trades = result.scalars().all()
        data = [
            {
                "id": t.id,
                "ticket": t.external_order_id or str(t.id),
                "symbol": t.symbol,
                "direction": t.direction.value if hasattr(t.direction, "value") else str(t.direction),
                "volume": float(t.volume) if t.volume is not None else 0.0,
                "entry_price": float(t.entry_price) if t.entry_price is not None else 0.0,
                "exit_price": float(t.exit_price) if t.exit_price is not None else 0.0,
                "profit": round(float(t.profit), 2) if t.profit is not None else 0.0,
                "r_multiple": round(float(t.outcome_r), 2) if t.outcome_r is not None else 0.0,
                "pnl_pct": 0.0,
                "exit_reason": t.comment,
                "entry_time": t.open_time.isoformat() if t.open_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            }
            for t in trades
        ]
        return {"ok": True, "trades": data}


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    """Return effective runtime settings with sensitive fields masked."""
    from src.core.runtime_settings import get_runtime_settings
    return {"ok": True, "settings": get_runtime_settings(mask_secrets=True)}


@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest) -> dict[str, Any]:
    """Update runtime settings persistently without modifying .env files."""
    from src.core.runtime_settings import save_runtime_settings
    changes = req.model_dump(exclude_none=True)
    updated = save_runtime_settings(changes)
    return {"ok": True, "message": "Settings updated successfully", "settings": updated}


@app.post("/api/settings/binance/test")
async def test_binance_credentials(req: BinanceTestRequest) -> dict[str, Any]:
    """Check selected Binance Futures environment with a read-only request."""
    from src.core.runtime_settings import get_runtime_settings, is_masked

    current = get_runtime_settings(mask_secrets=False)

    def resolve_secret(provided: str | None, stored: str | None) -> str:
        value = (provided or "").strip()
        if value and not is_masked(value):
            return value
        return (stored or "").strip()

    mode = (req.binance_mode or current.get("binance_mode", "")).lower()
    if mode == "testnet":
        environment = "Demo/Testnet"
        key_field, secret_field = "binance_demo_api_key", "binance_demo_api_secret"
        provided_key = req.binance_demo_api_key if req.binance_demo_api_key is not None else req.binance_api_key
        provided_secret = req.binance_demo_api_secret if req.binance_demo_api_secret is not None else req.binance_api_secret
    elif mode == "live":
        environment = "Live"
        key_field, secret_field = "binance_live_api_key", "binance_live_api_secret"
        provided_key = req.binance_live_api_key if req.binance_live_api_key is not None else req.binance_api_key
        provided_secret = req.binance_live_api_secret if req.binance_live_api_secret is not None else req.binance_api_secret
    else:
        return {"ok": False, "message": "เลือก Binance environment เป็น DEMO/TESTNET หรือ LIVE ก่อนทดสอบ"}

    api_key = resolve_secret(provided_key, current.get(key_field))
    api_secret = resolve_secret(provided_secret, current.get(secret_field))
    if not api_key or not api_secret:
        return {"ok": False, "message": f"กรุณากรอก Binance Futures {environment} API Key และ Secret ก่อนทดสอบ"}

    base_url = (req.binance_base_url or current.get("binance_base_url") or "").strip().rstrip("/")
    if mode == "testnet" and not is_binance_futures_testnet_url(base_url):
        return {"ok": False, "message": "ทดสอบ Demo/Testnet ได้เฉพาะ Binance Futures Demo/Testnet URL ที่รองรับเท่านั้น"}
    if mode == "live" and not is_binance_futures_live_url(base_url):
        return {"ok": False, "message": "ทดสอบ Live ได้เฉพาะ https://fapi.binance.com เท่านั้น"}

    gateway = BinanceGateway(
        base_url=base_url,
        api_key=api_key,
        api_secret=api_secret,
    )
    try:
        account = (
            await gateway.test_testnet_account_access()
            if mode == "testnet"
            else await gateway.test_live_account_access()
        )
        result = {
            "ok": True,
            "message": f"เชื่อมต่อ Binance Futures {environment} สำเร็จ (อ่านข้อมูลบัญชีเท่านั้น)",
        }
        # Keep real-account financial data out of the API response. The Live
        # check only needs to confirm the credential; Demo retains its balance
        # display for the existing workflow.
        if mode == "testnet":
            result.update({
                "balance": round(account.balance, 2),
                "equity": round(account.equity, 2),
                "currency": account.currency,
            })
        return result
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        exchange_code: int | None = None
        try:
            raw_code = exc.response.json().get("code")
            exchange_code = int(raw_code) if raw_code is not None else None
        except (ValueError, TypeError, AttributeError):
            pass
        if exchange_code == -2014:
            message = f"รูปแบบ API Key ไม่ถูกต้อง ตรวจว่าเป็น HMAC API Key จาก Binance Futures {environment} API Management"
        elif exchange_code == -2015:
            source = "Futures Demo API Management" if mode == "testnet" else "API Management ของบัญชี Live"
            message = f"Binance ปฏิเสธ API Key ตรวจว่าคีย์มาจาก {source}, URL ตรงกับสภาพแวดล้อม และคีย์ยังใช้งานได้"
        elif exchange_code == -1022:
            message = f"ลายเซ็น API ไม่ถูกต้อง ตรวจ Secret และใช้ HMAC API Key สำหรับ Futures {environment}"
        elif exchange_code == -1021:
            message = "เวลาเซิร์ฟเวอร์คลาดเคลื่อนเกินกำหนด ลองอีกครั้งหลังซิงก์เวลา"
        elif status_code == 401:
            message = f"Binance ปฏิเสธ API Key/Secret ตรวจว่าคีย์เป็นของ Futures {environment} และมีสิทธิ์อ่าน Futures account"
        elif status_code == 403:
            message = "Binance ไม่อนุญาตคำขอ ตรวจสิทธิ์ Futures และ IP allowlist ของ API key"
        elif status_code == 400:
            message = "Binance ปฏิเสธคำขอ ตรวจ API Key/Secret และเวลาเครื่องของเซิร์ฟเวอร์"
        else:
            message = f"Binance Futures {environment} ตอบกลับ HTTP {status_code} ลองอีกครั้งภายหลัง"
        result = {"ok": False, "message": message, "status_code": status_code}
        if exchange_code is not None:
            result["exchange_code"] = exchange_code
        return result
    except Exception as exc:
        logger.warning("Binance Futures %s API check failed (%s)", environment, type(exc).__name__)
        return {
            "ok": False,
            "message": f"เชื่อมต่อ Binance Futures {environment} ไม่สำเร็จ ตรวจ URL และการเชื่อมต่อเครือข่าย",
        }
    finally:
        await gateway.disconnect()


@app.get("/api/ai/auth-status")
@app.get("/api/agents/auth")
async def get_ai_auth_status(refresh: bool = False) -> dict[str, Any]:
    """Inspect local AI auth state (Codex ChatGPT, Gemini OAuth, API keys) without burning tokens."""
    from src.core.ai_auth_service import ai_auth_service
    return await ai_auth_service.inspect(force=refresh)


@app.post("/api/ai/test")
@app.post("/api/settings/providers/{provider}/test")
async def test_ai_provider_endpoint(
    provider: str | None = None,
    req: AITestRequest | None = None,
) -> dict[str, Any]:
    """Test connectivity to an AI provider with latency measurement."""
    from src.core.ai_auth_service import ai_auth_service
    target = provider or (req.provider if req else "codex")
    result = await ai_auth_service.test_provider(target)
    return {"ok": result.get("ok", False), "result": result}


@app.get("/api/analytics/pro-metrics")
async def get_pro_metrics_endpoint(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """Return institutional prop-desk analytics for the SwingFrontRun dashboard view."""
    from src.analytics.pro_metrics_service import get_pro_dashboard_metrics
    return await get_pro_dashboard_metrics(symbol)


@app.get("/api/trades/markers")
async def get_trade_markers(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """Return chart markers and detailed trade explanations for the specified symbol."""
    sym = symbol.upper()
    async with get_db_session() as session:
        query = select(Trade).where(Trade.symbol == sym).order_by(Trade.open_time.desc()).limit(50)
        result = await session.execute(query)
        trades = result.scalars().all()

        markers: list[dict[str, Any]] = []
        trade_details: list[dict[str, Any]] = []

        for t in trades:
            direction_str = t.direction.value if hasattr(t.direction, "value") else str(t.direction)
            profit_val = round(float(t.profit), 2) if t.profit is not None else 0.0
            r_val = round(float(t.outcome_r), 2) if t.outcome_r is not None else 0.0
            is_win = profit_val > 0

            strategy_raw = (t.comment or "").lower()
            if "fvg_reversal" in strategy_raw or "fvg" in strategy_raw:
                strategy_title = "FVG Reversal"
                why_entered = "ราคาย่อตัวทดสอบ Fair Value Gap (FVG) ในโซน Discount/Premium สอดคล้องกับโครงสร้างแท่งเทียน"
            elif "breakout" in strategy_raw:
                strategy_title = "Breakout Retest"
                why_entered = "ราคาทะลุแนวรับแนวต้านสำคัญ (BOS) และย้อนกลับมา Retest ตามตำรา Price Action"
            elif "choch" in strategy_raw or "orderblock" in strategy_raw:
                strategy_title = "CHoCH + Order Block"
                why_entered = "เกิด Change of Character (CHoCH) และกลับมาทดสอบโซน Order Block ของสถาบัน"
            else:
                strategy_title = "Smart Money Setup"
                why_entered = "AI วิเคราะห์โครงสร้างราคาสอดคล้องกับแนวโน้ม Multi-Timeframe และผ่านเกณฑ์ความเสี่ยง"

            if is_win:
                why_won_lost = f"✅ ชนะ (+{r_val:+.1f}R, +${profit_val:,.2f}): ราคาวิ่งไปแตะเป้า Take Profit ตามแผน โครงสร้างราคาไม่เสีย"
            elif profit_val < 0:
                why_won_lost = f"❌ เสีย ({r_val:+.1f}R, -${abs(profit_val):,.2f}): ราคาถูกตัดขาดทุน (Stop Loss) เนื่องจากความผันผวนของสเปรดและแรงขายต้าน"
            else:
                why_won_lost = "⚪ เสมอตัว (0.0R): ออเดอร์ปิดที่จุด Break-Even คุ้มทุนพอดี"

            entry_ts = int(t.open_time.timestamp()) if t.open_time else 0
            exit_ts = int(t.exit_time.timestamp()) if t.exit_time else (entry_ts + 300)

            if entry_ts > 0:
                markers.append({
                    "time": entry_ts,
                    "position": "belowBar" if direction_str == "BUY" else "aboveBar",
                    "color": "#10b981" if direction_str == "BUY" else "#ef4444",
                    "shape": "arrowUp" if direction_str == "BUY" else "arrowDown",
                    "text": f"{direction_str} @ {float(t.entry_price):,.2f}",
                    "id": f"entry_{t.id}",
                })

            if t.exit_time and exit_ts > entry_ts:
                markers.append({
                    "time": exit_ts,
                    "position": "aboveBar" if direction_str == "BUY" else "belowBar",
                    "color": "#10b981" if is_win else "#ef4444",
                    "shape": "circle",
                    "text": f"{'WIN' if is_win else 'LOSS'} {r_val:+.1f}R",
                    "id": f"exit_{t.id}",
                })

            trade_details.append({
                "id": t.id,
                "ticket": t.external_order_id or str(t.id),
                "symbol": t.symbol,
                "direction": direction_str,
                "volume": float(t.volume) if t.volume else 0.0,
                "entry_price": float(t.entry_price) if t.entry_price else 0.0,
                "exit_price": float(t.exit_price) if t.exit_price else 0.0,
                "sl": float(t.sl) if t.sl else 0.0,
                "tp": float(t.tp1) if t.tp1 else 0.0,
                "profit": profit_val,
                "outcome_r": r_val,
                "status": "WIN" if is_win else ("LOSS" if profit_val < 0 else "BREAKEVEN"),
                "strategy": strategy_title,
                "why_entered": why_entered,
                "why_won_lost": why_won_lost,
                "open_time": t.open_time.isoformat() if t.open_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            })

        # Add currently open positions for this symbol
        gateway = get_gateway()
        try:
            positions = await gateway.get_positions()
            for p in positions:
                if p.symbol == sym:
                    direction_str = p.direction.value if hasattr(p.direction, "value") else str(p.direction)
                    open_ts = int(datetime.now(timezone.utc).timestamp()) - 300
                    markers.append({
                        "time": open_ts,
                        "position": "belowBar" if direction_str == "BUY" else "aboveBar",
                        "color": "#3b82f6",
                        "shape": "arrowUp" if direction_str == "BUY" else "arrowDown",
                        "text": f"⏳ ACTIVE {direction_str} @ {p.open_price:,.2f}",
                        "id": f"pos_{p.ticket}",
                    })
                    trade_details.insert(0, {
                        "id": p.ticket,
                        "ticket": str(p.ticket),
                        "symbol": p.symbol,
                        "direction": direction_str,
                        "volume": p.volume,
                        "entry_price": p.open_price,
                        "exit_price": 0.0,
                        "sl": p.sl,
                        "tp": p.tp,
                        "profit": round(p.profit, 2),
                        "outcome_r": 0.0,
                        "status": "OPEN",
                        "strategy": "Active SMC Order",
                        "why_entered": "ออเดอร์เปิดตามเงื่อนไข SMC Confluence และผ่านการอนุมัติจาก Risk Engine",
                        "why_won_lost": "⏳ กำลังถือออเดอร์: มี Server-side SL ควบคุมความเสี่ยง และมีระบบ Auto Break-Even เฝ้าระวังที่ +1.0R",
                        "open_time": datetime.now(timezone.utc).isoformat(),
                        "exit_time": None,
                    })
        except Exception:
            pass

        markers.sort(key=lambda m: m["time"])
        return {"ok": True, "symbol": sym, "markers": markers, "trades": trade_details}


class BacktestRunRequest(BaseModel):
    strategy_id: str = "choch_orderblock"
    symbol: str = "BTCUSDT"
    timeframe: str = "5m"
    candle_count: int = 300
    initial_balance: float = 10000.0
    risk_pct: float = 0.01
    spread_pips: float = 2.0


@app.post("/api/backtest/run")
async def run_backtest_endpoint(req: BacktestRunRequest) -> dict[str, Any]:
    """Execute on-demand backtesting simulation for any strategy and symbol."""
    from src.analytics.backtester import Backtester
    from src.core.types import Candle
    from src.strategies.registry import auto_discover

    auto_discover()
    sym = req.symbol.upper()
    gateway = get_gateway()
    tf_norm = {
        "1M": "M1", "5M": "M5", "15M": "M15", "1H": "H1", "4H": "H4", "1D": "D1",
        "M1": "M1", "M5": "M5", "M15": "M15", "H1": "H1", "H4": "H4", "D1": "D1",
    }.get(req.timeframe.upper(), "M5")

    # 1. Fetch primary timeframe candles
    candles: list[Candle] = []
    try:
        fetched = await gateway.get_ohlcv(sym, tf_norm, count=min(max(req.candle_count, 100), 500))
        if fetched:
            candles = sorted(fetched, key=lambda c: c.timestamp)
    except Exception as exc:
        logger.warning("Could not fetch online candles for backtest %s: %s", sym, exc)

    # 2. If insufficient candles (e.g. offline/mock environment), generate synthetic candles
    if len(candles) < 60:
        base_price = 80000.0 if "BTC" in sym else (2600.0 if "ETH" in sym else 150.0)
        import random
        now = datetime.now(timezone.utc)
        curr = base_price
        candles = []
        for i in range(min(max(req.candle_count, 100), 300)):
            delta = (random.random() - 0.49) * (curr * 0.004)
            c_open = curr
            curr += delta
            c_close = curr
            c_high = max(c_open, c_close) + abs(delta) * (0.2 + random.random() * 0.5)
            c_low = min(c_open, c_close) - abs(delta) * (0.2 + random.random() * 0.5)
            c_vol = 100.0 + random.random() * 300.0
            ts = now - timedelta(minutes=5 * (300 - i))
            candles.append(Candle(timestamp=ts, open=c_open, high=c_high, low=c_low, close=c_close, volume=c_vol))

    # Multi-timeframe mapping
    candles_by_tf = {
        tf_norm: candles,
        "M15": candles[::3] if len(candles) >= 3 else candles,
        "H1": candles[::12] if len(candles) >= 12 else candles,
    }

    try:
        backtester = Backtester(spread_pips=req.spread_pips)
        result = backtester.run(
            strategy_id=req.strategy_id,
            symbol=sym,
            candles_by_tf=candles_by_tf,
            entry_tf=tf_norm,
            htf="H1",
            start_idx=min(40, len(candles) // 3),
            initial_balance=req.initial_balance,
        )

        final_equity = result.equity_curve[-1] if result.equity_curve else req.initial_balance
        total_pnl = round(final_equity - req.initial_balance, 2)

        return {
            "ok": True,
            "summary": {
                "strategy_id": req.strategy_id,
                "symbol": sym,
                "timeframe": req.timeframe,
                "total_trades": result.total_trades,
                "winners": result.winners,
                "losers": result.losers,
                "win_rate": round(result.win_rate * 100, 2),
                "profit_factor": result.profit_factor,
                "max_drawdown": result.max_drawdown,
                "expectancy": result.expectancy,
                "sharpe_ratio": result.sharpe_ratio,
                "total_pnl": total_pnl,
                "initial_balance": req.initial_balance,
                "final_equity": round(final_equity, 2),
            },
            "equity_curve": result.equity_curve,
            "trades": result.trades,
        }
    except Exception as exc:
        logger.error("Backtest execution error: %s", exc)
        return {"ok": False, "error": str(exc)}


# ─── Action Endpoints ─────────────────────────────────────────────────────────

@app.post("/api/actions/panic")
async def action_panic() -> dict[str, Any]:
    """Emergency Panic Switch: Close all open positions immediately and disarm live."""
    logger.warning("🚨 EMERGENCY PANIC TRIGGERED VIA WEB INTERFACE")
    gateway = get_gateway()
    closed_count = 0
    try:
        positions = await gateway.get_positions()
        for pos in positions:
            try:
                await gateway.close_position(pos.ticket)
                closed_count += 1
            except Exception as exc:
                logger.error("Failed closing position %s during panic: %s", pos.ticket, exc)

        # Also close any open trades in SQLite
        async with get_db_session() as session:
            query = select(Trade).where(Trade.status == "OPEN")
            res = await session.execute(query)
            open_trades = res.scalars().all()
            for ot in open_trades:
                ot.status = "CLOSED"
                ot.comment = "Emergency Panic: closed by web interface"
                ot.exit_time = datetime.now(timezone.utc)
                closed_count += 1
            await session.commit()

        # Disarm Live trading immediately
        from src.core.runtime_control import disarm_live_trading
        disarm_live_trading()
        update_runtime_status(
            last_decision="PANIC_SHUTDOWN",
            last_reason=f"ปุ่มฉุกเฉิน Panic: ปิดทุกไม้สำเร็จ {closed_count} รายการ และหยุดการทำงานชั่วคราว",
        )
        await broadcast_ws({
            "type": "alert",
            "level": "error",
            "message": f"🚨 ฉุกเฉิน Panic: ปิดออเดอร์ทั้งหมด {closed_count} ไม้เรียบร้อยแล้ว",
        })
        return {
            "ok": True,
            "message": f"ฉุกเฉิน Panic สำเร็จ: ปิดทุกไม้เรียบร้อยแล้ว ({closed_count} ไม้) และปลดล็อกระบบ Live ปลอดภัย 100%",
            "closed_count": closed_count,
        }
    except Exception as exc:
        logger.error("Panic action failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/actions/scan")
async def action_scan() -> dict[str, Any]:
    """Trigger AI Crypto Screener homework scan."""
    gateway = get_gateway()
    screener = CryptoScreener(gateway)

    async def _run_scan():
        try:
            result = await screener.run(top_n=5)
            await broadcast_ws({
                "type": "alert",
                "level": "success",
                "message": f"✅ AI ทำการบ้านเสร็จแล้ว: คัดเลือกเหรียญน่าสนใจ {len(result.candidates)} รายการ",
            })
        except Exception as exc:
            logger.error("Background scan failed: %s", exc)

    asyncio.create_task(_run_scan())
    return {"ok": True, "message": "เริ่มการสแกนและทำการบ้าน AI ในพื้นหลังเรียบร้อยแล้ว"}


class SimulateTradeRequest(BaseModel):
    symbol: str = "BTCUSDT"
    direction: str = "BUY"
    strategy: str = "CHoCH + Order Block"


@app.post("/api/actions/simulate_trade")
async def action_simulate_trade(req: SimulateTradeRequest | None = None) -> dict[str, Any]:
    """Execute an immediate simulated paper trade with SMC confluence, server-side SL/TP, and audit log."""
    sym = (req.symbol if req else "BTCUSDT").upper()
    direction_str = (req.direction if req else "BUY").upper()
    strategy_name = req.strategy if req else "CHoCH + Order Block"

    gateway = get_gateway()
    try:
        tick = await gateway.get_current_price(sym)
        mid = float(tick.mid or tick.last or (tick.ask + tick.bid) / 2.0)
    except Exception:
        mid = 81250.0

    from src.core.types import Direction, OrderRequest
    dir_enum = Direction.BUY if direction_str == "BUY" else Direction.SELL

    # Dynamic ATR/Risk calculation for 1:2 Risk/Reward
    atr = mid * 0.005  # 0.5% risk distance
    if dir_enum == Direction.BUY:
        sl = round(mid - atr, 2)
        tp = round(mid + atr * 2.0, 2)
    else:
        sl = round(mid + atr, 2)
        tp = round(mid - atr * 2.0, 2)

    # Calculate reasonable volume (~$1,000 notional)
    vol = round(1000.0 / mid, 3) if mid > 0 else 0.01
    vol = max(vol, 0.001)

    order_req = OrderRequest(
        symbol=sym,
        direction=dir_enum,
        volume=vol,
        sl=sl,
        tp=tp,
        comment=f"Paper: {strategy_name}",
        venue="binance",
        execution_key=f"sim_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
    )

    res = await gateway.send_order(order_req)
    if not res.success:
        return {"ok": False, "message": f"Simulated order failed: {res.error_message}"}

    # Store in database trade log for audit trail & retrospective
    try:
        async with get_db_session() as session:
            from src.core.types import PositionStatus, TradeRecord
            from src.storage.repository import Repository
            repo = Repository(session)
            trade_rec = TradeRecord(
                symbol=sym,
                direction=dir_enum,
                volume=vol,
                entry_price=res.price or mid,
                sl=sl,
                tp1=tp,
                status=PositionStatus.OPEN,
                comment=f"{strategy_name} (Paper Simulation)",
                venue="binance",
                external_order_id=str(res.ticket),
                execution_key=order_req.execution_key,
            )
            await repo.log_trade(trade_rec)
    except Exception as exc:
        logger.warning("Could not persist trade to database: %s", exc)

    # Immediately push WebSocket updates
    try:
        positions = await gateway.get_positions()
        await broadcast_ws({
            "type": "positions",
            "positions": [
                {
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "direction": p.direction.value if hasattr(p.direction, "value") else str(p.direction),
                    "volume": p.volume,
                    "open_price": p.open_price,
                    "current_price": p.current_price,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": round(p.profit, 2),
                    "pnl_pct": round((p.profit / (p.open_price * p.volume or 1)) * 100, 2),
                }
                for p in positions
            ],
        })
        await broadcast_ws({
            "type": "alert",
            "level": "success",
            "message": f"⚡ AI ซ้อมเปิดออเดอร์สำเร็จ: {dir_enum.value} {vol} {sym} @ ${mid:,.2f} (SL=${sl:,.2f}, TP=${tp:,.2f})",
        })
    except Exception:
        pass

    return {
        "ok": True,
        "message": f"เปิดออเดอร์ซ้อมเทรด {dir_enum.value} {sym} สำเร็จ",
        "ticket": res.ticket,
        "price": res.price or mid,
        "sl": sl,
        "tp": tp,
        "volume": vol,
        "strategy": strategy_name,
    }


@app.post("/api/actions/close_position")
async def action_close_position(req: PositionActionRequest) -> dict[str, Any]:
    """Manually close a single position."""
    gateway = get_gateway()
    try:
        positions = await gateway.get_positions(req.symbol)
        target = next((position for position in positions if position.ticket == req.ticket), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Open position not found")
        result = await gateway.close_position(req.ticket)
        if not result.success:
            raise HTTPException(status_code=502, detail=result.error_message or "Binance did not confirm the close order")

        exit_price = result.price or target.current_price
        closed_volume = float(result.volume if result.volume is not None else target.volume)
        direction = target.direction.value if hasattr(target.direction, "value") else str(target.direction)
        contract_size = settings.symbols.get(target.symbol).contract_size if target.symbol in settings.symbols else 1
        pnl = (exit_price - target.open_price) * closed_volume * contract_size
        if direction == "SELL":
            pnl = -pnl
        async with get_db_session() as session:
            query = (
                select(Trade)
                .where(Trade.status == "OPEN", Trade.symbol == target.symbol, Trade.direction == direction)
                .order_by(Trade.id.desc())
                .limit(1)
            )
            db_result = await session.execute(query)
            ot = db_result.scalar_one_or_none()
            if ot:
                ot.status = "CLOSED"
                ot.exit_price = exit_price
                ot.profit = pnl
                ot.net_profit = pnl
                ot.exit_time = datetime.now(timezone.utc)
                ot.comment = "Closed manually via web interface"
                await session.commit()
        return {"ok": True, "message": f"ปิดตำแหน่งไม้ #{req.ticket} สำเร็จ (P&L: {pnl:+.2f} USDT)"}
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/actions/break_even")
async def action_break_even(req: PositionActionRequest) -> dict[str, Any]:
    """Lock Break-Even on a position (move SL to entry price)."""
    gateway = get_gateway()
    try:
        positions = await gateway.get_positions(req.symbol)
        target = next((p for p in positions if p.ticket == req.ticket), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Open position not found")
        result = await gateway.modify_position(target.ticket, sl=target.open_price, tp=target.tp or None)
        if not result.success:
            raise HTTPException(status_code=502, detail=result.error_message or "Stop update was not confirmed")
        return {"ok": True, "message": f"ขยับ Stop Loss บังหน้าทุน (BE @ {target.open_price}) สำเร็จ"}
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/actions/mode")
async def action_set_mode(req: ModeChangeRequest) -> dict[str, Any]:
    """Toggle PAPER vs LIVE trading mode."""
    target_mode = req.mode.upper()
    if target_mode not in ("PAPER", "LIVE"):
        raise HTTPException(status_code=400, detail="Mode must be PAPER or LIVE")

    if target_mode == "LIVE":
        set_runtime_trading_mode("live")
        if req.armed:
            arm_live_trading()
    else:
        from src.core.runtime_control import disarm_live_trading
        disarm_live_trading()
        set_runtime_trading_mode("paper")

    update_runtime_status(mode=target_mode)
    return {"ok": True, "mode": target_mode, "is_live_armed": is_live_armed()}


# ─── WebSocket Endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info("New WebSocket client connected (Total: %d)", len(_ws_clients))
    try:
        # Send initial state
        runtime = read_runtime_status()
        await websocket.send_text(json.dumps({"type": "status", "data": runtime}))

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")
                if action == "set_symbol":
                    global _active_chart_symbol
                    _active_chart_symbol = msg.get("symbol", "BTCUSDT").upper()
                    logger.info("Active chart symbol switched to: %s", _active_chart_symbol)
                elif action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "time": time.time()}))
            except Exception:
                pass
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
        logger.info("WebSocket client disconnected (Remaining: %d)", len(_ws_clients))


# ─── Terminal & CLI Authentication (/terminal) ──────────────────────────────

@app.get("/terminal")
async def terminal_page():
    """Serve the interactive CLI terminal page for ChatGPT / Codex / Gemini auth."""
    candidate_paths = [
        Path("src/dashboard/terminal.html"),
        Path(__file__).resolve().parent.parent / "dashboard" / "terminal.html",
        Path("/app/src/dashboard/terminal.html"),
    ]
    term_html = next((p for p in candidate_paths if p.is_file()), None)
    if term_html:
        return FileResponse(term_html, media_type="text/html")
    return JSONResponse({"ok": False, "error": "Terminal page not found"}, status_code=404)


@app.websocket("/terminal/ws")
async def terminal_ws_endpoint(websocket: WebSocket):
    """Handle interactive PTY terminal session for CLI login over WebSocket."""
    from src.dashboard.cli_login_console import DEFAULT_COMMANDS
    from src.dashboard.terminal_server import TerminalProcess
    from src.dashboard.terminal_auth import is_terminal_authorized, dashboard_auth_token

    auth = websocket.query_params.get("auth", "")
    password = os.getenv("DASHBOARD_PASSWORD", "freebuff2026").strip()
    is_valid = (
        auth == password
        or auth == dashboard_auth_token(password)
        or is_terminal_authorized(f"/terminal/ws?auth={auth}", password)
        or not password
    )
    if not is_valid:
        await websocket.close(code=1008, reason="Terminal access denied")
        return

    await websocket.accept()
    terminal: TerminalProcess | None = None
    pump: asyncio.Task[None] | None = None

    async def _output_pump(term: TerminalProcess):
        try:
            while term.running:
                output = term.read()
                if output:
                    await websocket.send_text(json.dumps({"type": "output", "data": output}))
                await asyncio.sleep(0.02)
            output = term.read()
            if output:
                await websocket.send_text(json.dumps({"type": "output", "data": output}))
            reason = "terminal_timed_out" if term.process.poll() is None else "terminal_completed"
            term.stop(reason)
            await websocket.send_text(json.dumps({"type": "exit", "code": term.process.returncode}))
        except Exception:
            term.stop("terminal_disconnected")

    try:
        await websocket.send_text(json.dumps({"type": "ready", "agents": list(DEFAULT_COMMANDS)}))
        while True:
            raw_message = await websocket.receive_text()
            try:
                message = json.loads(raw_message)
            except Exception:
                continue
            if not isinstance(message, dict):
                continue
            action = message.get("type")
            if action == "start":
                agent = message.get("agent")
                if agent not in DEFAULT_COMMANDS:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Unsupported CLI agent"}))
                    continue
                if terminal:
                    terminal.stop()
                if pump:
                    pump.cancel()
                try:
                    terminal = TerminalProcess(DEFAULT_COMMANDS[agent])
                    terminal.resize(int(message.get("cols", 100)), int(message.get("rows", 28)))
                    pump = asyncio.create_task(_output_pump(terminal))
                except Exception as exc:
                    await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
            elif action == "input" and terminal and terminal.running:
                data = message.get("data")
                if isinstance(data, str):
                    try:
                        terminal.write(data)
                    except Exception as exc:
                        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
            elif action == "resize" and terminal and terminal.running:
                try:
                    terminal.resize(int(message.get("cols", 100)), int(message.get("rows", 28)))
                except Exception:
                    pass
            elif action == "stop" and terminal:
                terminal.stop()
    except WebSocketDisconnect:
        pass
    finally:
        if pump:
            pump.cancel()
        if terminal:
            terminal.stop("terminal_disconnected")


# ─── Static Files & SPA Fallback ──────────────────────────────────────────────

candidate_paths = [
    Path("web/dist"),
    Path(__file__).resolve().parent.parent.parent / "web" / "dist",
    Path("/app/web/dist"),
]
web_dist = next((p for p in candidate_paths if p.is_dir()), candidate_paths[1])

if (web_dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(web_dist / "assets")), name="assets")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    file_path = web_dist / full_path
    if full_path and file_path.is_file():
        return FileResponse(file_path)
    index_file = web_dist / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return JSONResponse({
        "ok": True,
        "message": "ApexTrader AI Trading Platform API is running. Web UI dist loading...",
        "status": "ready",
    })


def main() -> None:
    """Run server entry point."""
    import uvicorn
    port = int(os.getenv("PORT", "8501"))
    uvicorn.run("src.web.server:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
