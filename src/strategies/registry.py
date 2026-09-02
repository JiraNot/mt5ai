"""Strategy plugin registry — auto-discovery and registration."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Dict

from src.strategies.base import StrategyPlugin

logger = logging.getLogger(__name__)

_registry: Dict[str, StrategyPlugin] = {}


def register(strategy: StrategyPlugin) -> None:
    """Register a strategy plugin."""
    _registry[strategy.strategy_id] = strategy
    logger.info(f"Registered strategy: {strategy.strategy_id} ({strategy.name})")


def get_strategy(strategy_id: str) -> StrategyPlugin | None:
    """Get a strategy by ID."""
    return _registry.get(strategy_id)


def get_all_strategies() -> Dict[str, StrategyPlugin]:
    """Get all registered strategies."""
    return dict(_registry)


def get_strategy_ids() -> list[str]:
    """Get list of all strategy IDs."""
    return list(_registry.keys())


def auto_discover() -> None:
    """Auto-import all modules in strategies/ to trigger registration."""
    import src.strategies as strategies_pkg

    for importer, modname, ispkg in pkgutil.iter_modules(strategies_pkg.__path__):
        if modname not in ("base", "registry", "meta_engine"):
            try:
                importlib.import_module(f"src.strategies.{modname}")
                logger.debug(f"Discovered strategy module: {modname}")
            except Exception as e:
                logger.error(f"Failed to load strategy module {modname}: {e}")
