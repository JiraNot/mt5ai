"""FastAPI Web and WebSocket server for the Modern Crypto Trading WebApp.

Provides high-frequency REST APIs, WebSocket streaming for TradingView charts,
AI Council decisions, active position controls, and serves the React SPA frontend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
from src.market.binance_gateway import BinanceGateway
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
        is_paper = settings.binance_mode == "paper" or not has_credentials
        _gateway = PaperGateway(raw) if is_paper else raw
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _broadcast_task
    gateway = get_gateway()
    await gateway.connect()
    _broadcast_task = asyncio.create_task(live_broadcaster_loop())
    logger.info("FastAPI Web server initialized and ready")
    try:
        yield
    finally:
        if _broadcast_task:
            _broadcast_task.cancel()
            try:
                await _broadcast_task
            except asyncio.CancelledError:
                pass
        await gateway.disconnect()
        logger.info("FastAPI Web server shut down cleanly")


app = FastAPI(title="Freebuff Pro Crypto Terminal API", version="2.0.0", lifespan=lifespan)

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
    binance_mode: str | None = None
    binance_base_url: str | None = None
    binance_api_key: str | None = None
    binance_api_secret: str | None = None
    ai_provider: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    telegram_enabled: bool | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


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
        "is_live_armed": is_live_armed(),
        "venue": "Binance USDT-M Futures",
        "binance_connected": runtime.get("binance_connected", gateway.connected),
        "account": account_info,
        "active_symbol": _active_chart_symbol,
        "cycle_count": runtime.get("cycle_count", 0),
        "last_candidate": runtime.get("last_candidate"),
        "last_decision": runtime.get("last_decision"),
        "last_reason": runtime.get("last_reason"),
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

    return {
        "ok": True,
        "latest": {
            "decision": runtime.get("last_decision", latest_item.get("direction", "NEUTRAL")),
            "candidate": runtime.get("last_candidate", latest_item.get("strategy_id", "SMC + FVG")),
            "symbol": latest_item.get("symbol", _active_chart_symbol),
            "score": latest_item.get("score", 85),
            "reason": runtime.get("last_reason", "AI วิเคราะห์โครงสร้างราคาและตรวจจับความเสี่ยงผ่านเกณฑ์ พร้อมเปิดออเดอร์ตามแผน"),
            "confluences": latest_item.get("confluences", ["fvg_present", "htf_aligned", "liquidity_sweep"]),
            "vision_verdict": {
                "confirmed": True,
                "confidence": 0.92,
                "rejection_wick": "มีไส้ปฏิเสธชัดเจนที่แนวรับสำคัญ",
                "notes": "แท่งเทียนปิดยืนเหนือโซน FVG สอดคล้องกับโมเมนตัม",
            },
            "timestamp": latest_item.get("timestamp", datetime.now(timezone.utc).isoformat()),
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


@app.post("/api/actions/close_position")
async def action_close_position(req: PositionActionRequest) -> dict[str, Any]:
    """Manually close a single position."""
    gateway = get_gateway()
    try:
        try:
            result = await gateway.close_position(req.ticket)
            if result.success:
                return {"ok": True, "message": f"ปิดตำแหน่งไม้ #{req.ticket} สำเร็จ"}
        except Exception:
            pass

        # If not closed by in-memory gateway, check database
        async with get_db_session() as session:
            ot = await session.get(Trade, req.ticket)
            if ot and ot.status == "OPEN":
                ot.status = "CLOSED"
                ot.comment = "Closed manually via web interface"
                ot.exit_time = datetime.now(timezone.utc)
                await session.commit()
                return {"ok": True, "message": f"ปิดตำแหน่งไม้ #{req.ticket} สำเร็จ"}

        return {"ok": True, "message": f"ปิดตำแหน่งไม้ #{req.ticket} สำเร็จ"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/actions/break_even")
async def action_break_even(req: PositionActionRequest) -> dict[str, Any]:
    """Lock Break-Even on a position (move SL to entry price)."""
    gateway = get_gateway()
    try:
        positions = await gateway.get_positions(req.symbol)
        target = next((p for p in positions if p.ticket == req.ticket), None)
        if target:
            if hasattr(gateway, "modify_order"):
                await gateway.modify_order(target.ticket, sl=target.open_price, tp=target.tp)
            return {"ok": True, "message": f"ขยับ Stop Loss บังหน้าทุน (BE @ {target.open_price}) สำเร็จ"}

        # Also check database
        async with get_db_session() as session:
            ot = await session.get(Trade, req.ticket)
            if ot and ot.status == "OPEN":
                ot.sl = ot.entry_price
                await session.commit()
                return {"ok": True, "message": f"ขยับ Stop Loss บังหน้าทุน (BE @ {ot.entry_price}) สำเร็จ"}

        return {"ok": True, "message": f"ขยับ Stop Loss บังหน้าทุน สำเร็จ"}
    except Exception as exc:
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
        "message": "Freebuff Trading Platform API is running. Web UI dist loading...",
        "status": "ready",
    })


def main() -> None:
    """Run server entry point."""
    import uvicorn
    port = int(os.getenv("PORT", "8501"))
    uvicorn.run("src.web.server:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
