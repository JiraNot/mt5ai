"""Deterministic broker history reconciliation v1.0.0."""
from math import isclose
from src.core.types import Deal, ClosedOutcome

VERSION = "1.0.0"

def reconcile_deals(position_id: int, deals: list[Deal]) -> ClosedOutcome | None:
    if not deals or any(d.position_id != position_id for d in deals):
        return None
    if len({d.ticket for d in deals}) != len(deals):
        return None
    # Reversals / multiple entries cannot be attributed to one candidate safely.
    entries = [d for d in deals if d.entry == 0]
    exits = [d for d in deals if d.entry in (1, 3)]
    if len(entries) != 1 or not exits or len(entries) + len(exits) != len(deals):
        return None
    opening = entries[0]
    if opening.type not in (0, 1):
        return None
    if any(d.type == opening.type or d.type not in (0, 1) or d.time < opening.time
           or d.symbol != opening.symbol for d in exits):
        return None
    if not isclose(opening.volume, sum(d.volume for d in exits), abs_tol=1e-8):
        return None
    return ClosedOutcome(
        position_id=position_id, opening_order=opening.order, symbol=opening.symbol,
        close_time=max(d.time for d in exits),
        close_price=sum(d.price * d.volume for d in exits) / opening.volume,
        net_profit=sum(d.profit + d.commission + d.swap + d.fee for d in deals),
        deal_tickets=sorted(d.ticket for d in deals),
        reason_codes=sorted({d.reason for d in exits}),
    )
