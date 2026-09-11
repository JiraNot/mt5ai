"""Shared reward/risk arithmetic v1.0.0."""
from math import isfinite

VERSION = '1.0.0'


def reward_risk(reward: float, risk: float) -> float:
    """Distances must be positive and use the same units."""
    if not isfinite(reward) or not isfinite(risk) or reward <= 0 or risk <= 0:
        return 0.0
    return reward / risk
