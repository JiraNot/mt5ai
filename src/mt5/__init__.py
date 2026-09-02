"""MT5 Gateway — real MetaTrader 5 connection and execution."""

from src.mt5.gateway import MT5Gateway, AccountInfo, SymbolSpec, MT5OrderResult

__all__ = ["MT5Gateway", "AccountInfo", "SymbolSpec", "MT5OrderResult"]
