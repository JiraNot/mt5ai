"""Entry-time feature snapshot v1.0.0, shared by journal and ML."""
from src.core.config import settings

VERSION = "1.0.0"

def build_snapshot(candidate, context, spread, session):
    trend = context.htf_trend
    structure = context.get_structure("M15")
    fvg = next((f for f in context.fvgs if f.direction == candidate.direction and f.valid), None)
    ob = next((o for o in context.order_blocks if o.direction == candidate.direction and not o.mitigated), None)
    symbol = settings.symbols.get(candidate.symbol)
    return {
        "schema_version": VERSION, "strategy": candidate.strategy_id,
        "strategy_version": candidate.metadata.get("version", "unknown"),
        "symbol": candidate.symbol, "direction": candidate.direction.value,
        "timestamp": candidate.timestamp.isoformat(),
        "entry_price": candidate.entry_price, "stop_loss": candidate.stop_loss,
        "take_profit": candidate.take_profit_1, "rr": candidate.rr_ratio,
        "rule_score": candidate.rule_score, "spread": spread, "session": session,
        "pip_size": symbol.pip_value if symbol else None,
        "confluences": list(candidate.confluences),
        "market_context": {
            "htf_trend": "bullish" if trend and trend.value == "BUY" else "bearish" if trend else "unknown",
            "structure": {"choch_present": context.has_choch, "bos_present": context.has_bos},
            "regime": {"type": str(candidate.metadata.get("regime", "UNKNOWN")).upper()},
            "fvg": {"exists": bool(fvg), "mitigation": fvg.mitigated_percent if fvg else 0},
            "order_block": {"exists": bool(ob), "score": ob.strength * 20 if ob else 0},
            "liquidity": {"sweep": context.has_liquidity_sweep},
            "zone": {"type": structure.premium_discount.upper() if structure else "UNKNOWN"},
        },
        "structures": {tf: s.model_dump(mode="json") for tf, s in context.structures.items()},
        "candles": {tf: [c.model_dump(mode="json") for c in candles] for tf, candles in context.candles_by_tf.items()},
    }
