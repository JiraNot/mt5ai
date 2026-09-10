# Bridge Deployment Guide

Connect the Linux bot to a real MT5 terminal running on a separate Windows
machine. The bot decides; the bridge executes. Strategies/AI/Risk code never
changes.

The **server** side is its own standalone project — [`mt5-bridge`](file:///home/dulla/projects/mt5-bridge) — kept
out of this repo on purpose:

```
[This repo — Linux server]                    [mt5-bridge — Windows machine]
src/app.py (bot)                              mt5_bridge.py (FastAPI)
  └─ BridgeGateway ──── HTTP + token ───────▶    └─ MetaTrader5 pkg ──▶ terminal64.exe
```

## 1. Windows machine setup

Follow `mt5-bridge/README.md`. Summary:

1. Install the MT5 terminal and log in once manually.
2. Install Python 3.12+ (Add to PATH), then `pip install -r requirements.txt`.
3. Copy the `mt5-bridge` folder to the machine (e.g. `C:\mt5-bridge\`), create `.env` from its `.env.example`.
4. Verify, then run: `python selftest.py` → `python mt5_bridge.py`.
5. For boot autostart, use the included `bridge_start.bat.example`.

## 2. Network: Tailscale (recommended)

Keep the bridge off the public internet. With [Tailscale](https://tailscale.com) (free, 10 min):

1. Install Tailscale on both machines, log in with the same account.
2. Each machine gets a stable `100.x.y.z` IP (`tailscale ip -4` to see it).
3. Use `http://100.x.y.z:8900` as the bridge URL on the Linux side.

Alternatives: WireGuard, or a plain LAN/VPN you control. Only expose the port
publicly if you accept the risk (not recommended; token alone is not hardening
enough).

## 3. Linux bot configuration

Add to `.env`:

```ini
MT5_MODE=bridge
BRIDGE_URL=http://100.x.y.z:8900
BRIDGE_TOKEN=paste-a-long-random-secret
```

Run as usual:

```bash
source .venv/bin/activate
python -m src.app            # platform (paper/loop)
python -m src.app --status   # shows MT5 mode: bridge
```

## 4. Verify end to end

```bash
# From the Linux machine — health check (should show your account):
curl -H "X-Bridge-Token: $BRIDGE_TOKEN" http://100.x.y.z:8900/health

# Start the bot and watch for:
#   "Bridge connected: http://100.x.y.z:8900 (account=..., server=...)"
```

## 5. Endpoints reference

All endpoints require the `X-Bridge-Token` header when `BRIDGE_TOKEN` is set.
Full reference lives in `mt5-bridge/README.md`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Terminal + account status |
| GET | `/ohlcv/{symbol}?timeframe=M5&count=500` | Candle history |
| GET | `/tick/{symbol}` | Latest bid/ask |
| GET | `/symbol/{symbol}` | Trading conditions |
| GET | `/account` | Balance, equity, margin |
| GET | `/positions?symbol=XAUUSD` | Open positions |
| POST | `/order` | Market order (OrderRequest JSON) |
| POST | `/position/{ticket}/modify` | Change SL/TP |
| POST | `/position/{ticket}/close` | Close position |

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `Bridge reachable but MT5 not initialized` | Terminal closed or logged out on Windows — open it and log in |
| `Invalid bridge token` (401) | Token mismatch between Windows `.env` and Linux `.env` |
| Tick returns 0.00 | Market closed (weekend) — historical data still works |
| `connect timeout` | Firewall on Windows (allow inbound 8900) or wrong/missing Tailscale IP |
| Data differs from charts | Bars are broker time (UTC+2/+3 typical), not local time |
