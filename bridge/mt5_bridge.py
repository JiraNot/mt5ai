"""
Freebuff Windows Bridge Server
==============================

Runs ON the Windows machine (or Wine prefix) that hosts the real MetaTrader 5
terminal, and exposes it to the Linux bot over HTTP.

Setup (on Windows, in cmd/PowerShell):

    pip install fastapi uvicorn MetaTrader5
    set BRIDGE_TOKEN=choose-a-long-random-secret
    set MT5_LOGIN=your_login
    set MT5_PASSWORD=your_password
    set MT5_SERVER=your_server
    python windows_bridge.py

Then on the Linux bot (.env):
    MT5_MODE=bridge
    BRIDGE_URL=http://<windows-ip>:8900
    BRIDGE_TOKEN=choose-a-long-random-secret

SECURITY: bind is 0.0.0.0 but you MUST keep this off the public internet.
Use Tailscale/WireGuard between the two machines, and always set BRIDGE_TOKEN.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

# Optional: load .env from the script's own directory (no dependency needed).
# Real environment variables always win over .env values.
_env_file = Path(__file__).with_name(".env")
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _value = _line.partition("=")
            os.environ.setdefault(_key.strip(), _value.strip())

try:
    import MetaTrader5 as mt5

    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None  # type: ignore[assignment]

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bridge")

BRIDGE_TOKEN = os.getenv("BRIDGE_TOKEN", "")
MT5_LOGIN = os.getenv("MT5_LOGIN", "")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")
PORT = int(os.getenv("BRIDGE_PORT", "8900"))

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
} if MT5_AVAILABLE else {}

app = FastAPI(title="Freebuff MT5 Bridge", version="1.0.0")


# ─── Auth ─────────────────────────────────────────────────────────────────────

def check_token(x_bridge_token: str | None) -> None:
    if BRIDGE_TOKEN and x_bridge_token != BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")


# ─── Models ───────────────────────────────────────────────────────────────────

class OrderIn(BaseModel):
    symbol: str
    direction: str  # BUY / SELL
    volume: float
    price: float | None = None
    sl: float
    tp: float
    magic: int = 20240101
    comment: str = ""
    deviation: int = 10


class ModifyIn(BaseModel):
    sl: float | None = None
    tp: float | None = None


def _iso(epoch_seconds: int | float) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health(x_bridge_token: str | None = Header(default=None)):
    check_token(x_bridge_token)
    if not MT5_AVAILABLE:
        return JSONResponse(
            {"status": "error", "mt5_initialized": False, "error": "MetaTrader5 package not installed"}
        )
    ti = mt5.terminal_info()
    ai = mt5.account_info()
    return {
        "status": "ok",
        "mt5_initialized": ti is not None,
        "terminal": ti.name if ti else None,
        "build": ti.build if ti else None,
        "account": ai.login if ai else None,
        "server": ai.server if ai else None,
        "balance": ai.balance if ai else None,
    }


# ─── Market Data ──────────────────────────────────────────────────────────────

@app.get("/ohlcv/{symbol}")
def ohlcv(
    symbol: str,
    timeframe: str = Query("M5"),
    count: int = Query(500, le=5000),
    x_bridge_token: str | None = Header(default=None),
):
    check_token(x_bridge_token)
    tf = TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        return JSONResponse({"error": f"No data for {symbol} {timeframe}: {mt5.last_error()}"})

    candles = [
        {
            "timestamp": _iso(r["time"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["tick_volume"]),
        }
        for r in rates
    ]
    return {"candles": candles}


@app.get("/tick/{symbol}")
def tick(symbol: str, x_bridge_token: str | None = Header(default=None)):
    check_token(x_bridge_token)
    t = mt5.symbol_info_tick(symbol)
    if t is None:
        return JSONResponse({"error": f"No tick for {symbol}: {mt5.last_error()}"})
    return {
        "tick": {
            "timestamp": _iso(t.time),
            "bid": float(t.bid),
            "ask": float(t.ask),
            "last": float(t.last),
            "volume": float(t.volume),
        }
    }


@app.get("/symbol/{symbol}")
def symbol_info(symbol: str, x_bridge_token: str | None = Header(default=None)):
    check_token(x_bridge_token)
    info = mt5.symbol_info(symbol)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    return {
        "info": {
            "digits": info.digits,
            "point": info.point,
            "spread": info.spread,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_contract_size": info.trade_contract_size,
            "margin_initial": info.margin_initial,
        }
    }


# ─── Account ──────────────────────────────────────────────────────────────────

@app.get("/account")
def account(x_bridge_token: str | None = Header(default=None)):
    check_token(x_bridge_token)
    info = mt5.account_info()
    if info is None:
        raise HTTPException(status_code=503, detail="MT5 account not available (not logged in?)")
    return {
        "account": {
            "login": info.login,
            "name": info.name,
            "server": info.server,
            "balance": float(info.balance),
            "equity": float(info.equity),
            "margin": float(info.margin),
            # MT5 names it margin_free; fall back for package variations
            "free_margin": float(getattr(info, "margin_free", None) or getattr(info, "free_margin", 0.0)),
            "margin_level": float(getattr(info, "margin_level", 0.0)),
            "profit": float(info.profit),
            "currency": info.currency,
            "leverage": int(info.leverage),
        }
    }


# ─── Positions ────────────────────────────────────────────────────────────────

@app.get("/positions")
def positions(
    symbol: str | None = Query(None),
    x_bridge_token: str | None = Header(default=None),
):
    check_token(x_bridge_token)
    raw = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if raw is None:
        return {"positions": []}
    out = [
        {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "direction": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": float(p.volume),
            "open_price": float(p.price_open),
            "current_price": float(p.price_current),
            "sl": float(p.sl),
            "tp": float(p.tp),
            "profit": float(p.profit),
            "swap": float(p.swap),
            "commission": float(getattr(p, "commission", 0.0) or 0.0),
            "magic": int(p.magic),
            "open_time": _iso(p.time),
            "comment": p.comment,
        }
        for p in raw
    ]
    return {"positions": out}


# ─── Orders ───────────────────────────────────────────────────────────────────

@app.post("/order")
def send_order(order: OrderIn, x_bridge_token: str | None = Header(default=None)):
    check_token(x_bridge_token)

    # Resolve market price if not provided
    price = order.price
    if price is None:
        t = mt5.symbol_info_tick(order.symbol)
        if t is None:
            return JSONResponse({"result": {"success": False, "error_message": f"No tick for {order.symbol}"}})
        price = t.ask if order.direction == "BUY" else t.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": order.symbol,
        "volume": order.volume,
        "type": mt5.ORDER_TYPE_BUY if order.direction == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": order.sl,
        "tp": order.tp,
        "magic": order.magic,
        "comment": order.comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
        "deviation": order.deviation,
    }

    result = mt5.order_send(request)
    if result is None:
        err = mt5.last_error()
        return JSONResponse(
            {"result": {"success": False, "error_code": err[0] if err else -1, "error_message": str(err)}}
        )

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return JSONResponse(
            {
                "result": {
                    "success": False,
                    "error_code": int(result.retcode),
                    "error_message": result.comment,
                }
            }
        )

    logger.info(f"ORDER FILLED: {order.direction} {order.volume} {order.symbol} @ {result.price}")
    return {
        "result": {
            "success": True,
            "ticket": int(result.order),
            "price": float(result.price),
            "volume": float(result.volume),
        }
    }


@app.post("/position/{ticket}/modify")
def modify_position(
    ticket: int,
    body: ModifyIn,
    x_bridge_token: str | None = Header(default=None),
):
    check_token(x_bridge_token)
    found = mt5.positions_get(ticket=ticket)
    if not found:
        return JSONResponse({"result": {"success": False, "error_message": f"Position {ticket} not found"}})

    pos = found[0]
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": ticket,
        "sl": body.sl if body.sl is not None else float(pos.sl),
        "tp": body.tp if body.tp is not None else float(pos.tp),
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        msg = result.comment if result else str(mt5.last_error())
        return JSONResponse({"result": {"success": False, "error_message": msg}})
    return {"result": {"success": True, "ticket": ticket}}


@app.post("/position/{ticket}/close")
def close_position(ticket: int, x_bridge_token: str | None = Header(default=None)):
    check_token(x_bridge_token)
    found = mt5.positions_get(ticket=ticket)
    if not found:
        return JSONResponse({"result": {"success": False, "error_message": f"Position {ticket} not found"}})

    pos = found[0]
    close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    t = mt5.symbol_info_tick(pos.symbol)
    price = t.bid if pos.type == mt5.ORDER_TYPE_BUY else t.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": float(pos.volume),
        "type": close_type,
        "position": ticket,
        "price": price,
        "deviation": 10,
        "magic": int(pos.magic),
        "comment": "bridge-close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        msg = result.comment if result else str(mt5.last_error())
        return JSONResponse({"result": {"success": False, "error_message": msg}})

    logger.info(f"POSITION CLOSED: {ticket} @ {result.price}")
    return {"result": {"success": True, "ticket": ticket, "price": float(result.price)}}


# ─── Startup ──────────────────────────────────────────────────────────────────

def initialize_mt5() -> bool:
    """Log in to the MT5 terminal at server startup."""
    if not MT5_AVAILABLE:
        logger.error("MetaTrader5 package not installed on this machine")
        return False

    kwargs: dict = {"timeout": 10000}
    if MT5_LOGIN:
        kwargs.update(
            login=int(MT5_LOGIN),
            password=MT5_PASSWORD,
            server=MT5_SERVER,
        )

    if not mt5.initialize(**kwargs):
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return False

    ai = mt5.account_info()
    if ai:
        logger.info(f"MT5 connected: {ai.login} @ {ai.server} (balance {ai.balance:.2f})")
    return True


if __name__ == "__main__":
    import uvicorn

    if not initialize_mt5():
        logger.error("MT5 failed to initialize — bridge starting anyway, /health will report status")
    logger.info(f"Bridge listening on 0.0.0.0:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
