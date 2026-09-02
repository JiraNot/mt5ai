"""
Auto Trader — the main trading loop that ties everything together.

Architecture:
    MT5 Gateway → Market Data → Structure → Strategy → AI → Risk → Execution

This module:
1. Connects to MT5
2. Reads market data
3. Runs structure analysis
4. Detects trading setups
5. Scores with AI/ML
6. Validates with Risk Engine
7. Executes approved trades
8. Manages open positions
9. Logs everything
10. Learns from results

CRITICAL: Risk Engine has final authority.
          AI can only recommend, never override.
          Default mode is PAPER.
"""

import logging
import time
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TradingState:
    """Current state of the trading system."""
    mode: str = "PAPER"  # PAPER, DEMO, LIVE
    is_running: bool = False
    cycle_count: int = 0
    last_scan: Optional[datetime] = None
    open_positions: int = 0
    daily_trades: int = 0
    daily_pnl: float = 0.0
    consecutive_losses: int = 0
    kill_switch_active: bool = False


class AutoTrader:
    """
    Main auto-trading loop.
    
    Usage:
        trader = AutoTrader(mode="PAPER")
        trader.start()  # Runs indefinitely
    """

    def __init__(
        self,
        mode: str = "PAPER",
        symbol: str = "XAUUSD",
        scan_interval: int = 60,  # seconds
        config_path: str = "config.yaml",
    ):
        self.mode = mode
        self.symbol = symbol
        self.scan_interval = scan_interval
        self.config_path = config_path

        self.state = TradingState(mode=mode)
        self.gateway = None
        self.structure_engine = None
        self.strategies = []
        self.ai_scorer = None
        self.risk_engine = None
        self.ml_trainer = None

        self._candidates_today: List[Dict] = []
        self._trades_today: List[Dict] = []

    def _init_gateway(self):
        """Initialize MT5 gateway."""
        try:
            from src.mt5.gateway import MT5Gateway
            self.gateway = MT5Gateway()
            if self.gateway.connect():
                logger.info("MT5 Gateway connected")
                return True
            else:
                logger.warning("MT5 Gateway failed to connect — running in offline mode")
                return False
        except Exception as e:
            logger.error(f"Gateway init failed: {e}")
            return False

    def _init_structure_engine(self):
        """Initialize market structure analysis."""
        try:
            from src.structure.structure_analyzer import StructureAnalyzer
            from src.structure.fvg_detector import FVGDetector
            from src.structure.order_block_detector import OrderBlockDetector
            from src.structure.liquidity_detector import LiquidityDetector
            from src.structure.regime import MarketRegimeDetector

            self.structure_engine = {
                "analyzer": StructureAnalyzer(lookback=3),
                "fvg": FVGDetector(),
                "ob": OrderBlockDetector(),
                "liquidity": LiquidityDetector(),
                "regime": MarketRegimeDetector(),
            }
            logger.info("Structure engine initialized")
            return True
        except Exception as e:
            logger.error(f"Structure engine init failed: {e}")
            return False

    def _init_strategies(self):
        """Initialize trading strategies."""
        try:
            from src.strategies.choch_orderblock import CHOCHOrderBlockStrategy
            from src.strategies.fvg_final import FVGFinalStrategy
            from src.strategies.breakout_retest import BreakoutRetestStrategy

            self.strategies = [
                CHOCHOrderBlockStrategy(),
                FVGFinalStrategy(),
                BreakoutRetestStrategy(),
            ]
            logger.info(f"Initialized {len(self.strategies)} strategies")
            return True
        except Exception as e:
            logger.error(f"Strategy init failed: {e}")
            return False

    def _init_ai(self):
        """Initialize AI scorer."""
        try:
            from src.ai.scorer import AIScorer
            from src.ai.ml_trainer import MLTrainer

            self.ai_scorer = AIScorer()
            self.ml_trainer = MLTrainer()

            # Try to load trained ML model
            if self.ml_trainer.load_model():
                logger.info("ML model loaded successfully")
            else:
                logger.info("No ML model found — using rule-based scoring only")

            return True
        except Exception as e:
            logger.error(f"AI init failed: {e}")
            return False

    def _init_risk_engine(self):
        """Initialize risk engine."""
        try:
            from src.risk.manager import RiskManager
            self.risk_engine = RiskManager(
                risk_per_trade=0.0025,
                max_daily_loss=0.015,
                max_trades_per_day=5,
                max_consecutive_losses=3,
                min_rr=2.0,
            )
            logger.info("Risk engine initialized")
            return True
        except Exception as e:
            logger.error(f"Risk engine init failed: {e}")
            return False

    def initialize(self) -> bool:
        """Initialize all components."""
        logger.info("=" * 60)
        logger.info(f"Auto Trader initializing — Mode: {self.mode}")
        logger.info("=" * 60)

        results = {
            "gateway": self._init_gateway(),
            "structure": self._init_structure_engine(),
            "strategies": self._init_strategies(),
            "ai": self._init_ai(),
            "risk": self._init_risk_engine(),
        }

        all_ok = all(results.values())
        for name, ok in results.items():
            status = "OK" if ok else "FAILED"
            logger.info(f"  {name:15s}: {status}")

        if not all_ok:
            logger.warning("Some components failed to initialize — running with limited capability")

        return True  # Continue even with partial init

    def _scan_market(self) -> List[Dict]:
        """Scan market for trading opportunities."""
        candidates = []

        if not self.gateway or not self.gateway.is_connected():
            return candidates

        try:
            # Get candles for all timeframes
            tf_map = {
                "H1": 16385,   # mt5.TIMEFRAME_H1
                "M15": 16395,  # mt5.TIMEFRAME_M15
                "M5": 16389,   # mt5.TIMEFRAME_M5
            }

            candles_by_tf = {}
            for tf_name, tf_const in tf_map.items():
                candles = self.gateway.get_candles(self.symbol, tf_const, count=200)
                if candles:
                    candles_by_tf[tf_name] = candles

            if not candles_by_tf:
                logger.warning("No candle data received")
                return candidates

            # Build market context
            current_price = candles_by_tf["M5"][-1]["close"] if "M5" in candles_by_tf else None
            if current_price is None:
                return candidates

            # Run structure analysis on each timeframe
            structures = {}
            for tf_name, candles in candles_by_tf.items():
                if len(candles) < 20:
                    continue

                highs = [c["high"] for c in candles]
                lows = [c["low"] for c in candles]
                closes = [c["close"] for c in candles]

                analyzer = self.structure_engine["analyzer"]
                structure = analyzer.analyze(highs, lows, closes)
                structures[tf_name] = structure

            # Detect FVG, OB, Liquidity on entry timeframe
            entry_candles = candles_by_tf.get("M5", [])
            fvg_list = []
            ob_list = []
            liquidity_list = []

            if len(entry_candles) >= 5:
                fvg_list = self.structure_engine["fvg"].detect(entry_candles)
                ob_list = self.structure_engine["ob"].detect(entry_candles)
                liquidity_list = self.structure_engine["liquidity"].detect(entry_candles)

            # Detect regime
            regime = self.structure_engine["regime"].detect(
                [c["high"] for c in entry_candles],
                [c["low"] for c in entry_candles],
                [c["close"] for c in entry_candles],
            )

            # Build market context
            context = {
                "symbol": self.symbol,
                "timestamp": datetime.now(),
                "current_price": current_price,
                "timeframes": structures,
                "htf_trend": structures.get("H1", {}).get("trend", "none"),
                "structure": structures.get("M15", {}),
                "fvg": fvg_list[-1] if fvg_list else None,
                "ob": ob_list[-1] if ob_list else None,
                "liquidity": liquidity_list[-1] if liquidity_list else None,
                "regime": regime,
                "spread": entry_candles[-1].get("spread", 0) if entry_candles else 0,
                "session": self._get_session(),
            }

            # Run each strategy
            for strategy in self.strategies:
                try:
                    candidate = strategy.detect(context)
                    if candidate:
                        candidate["market_context"] = context
                        candidates.append(candidate)
                        logger.info(
                            f"Candidate: {candidate.get('strategy', 'unknown')} | "
                            f"{candidate.get('direction', '?')} | "
                            f"Score: {candidate.get('rule_score', 0)}"
                        )
                except Exception as e:
                    logger.error(f"Strategy {strategy.id} failed: {e}")

        except Exception as e:
            logger.error(f"Market scan failed: {e}")

        return candidates

    def _score_candidate(self, candidate: Dict) -> Dict:
        """Score candidate with AI/ML."""
        # Rule-based score (already from strategy)
        rule_score = candidate.get("rule_score", 50)

        # ML prediction
        ml_score = 50
        if self.ml_trainer and self.ml_trainer.best_model:
            prediction = self.ml_trainer.predict(candidate)
            if prediction:
                ml_score = int(prediction.win_probability * 100)
                candidate["ml_score"] = ml_score
                candidate["ml_confidence"] = prediction.confidence
                candidate["ml_model"] = prediction.model_name

        # AI score (rule-based context analysis)
        ai_score = rule_score
        if self.ai_scorer:
            try:
                ai_decision = self.ai_scorer.score(candidate, candidate.get("market_context", {}))
                if ai_decision:
                    ai_score = ai_decision.get("score", rule_score)
                    candidate["ai_score"] = ai_score
                    candidate["ai_decision"] = ai_decision.get("decision", "UNCERTAIN")
            except Exception as e:
                logger.warning(f"AI scoring failed: {e}")

        # Combined score (weighted average)
        if ml_score > 0:
            combined = int(rule_score * 0.4 + ai_score * 0.3 + ml_score * 0.3)
        else:
            combined = int(rule_score * 0.6 + ai_score * 0.4)

        candidate["combined_score"] = combined
        return candidate

    def _evaluate_risk(self, candidate: Dict) -> Dict:
        """Evaluate candidate with risk engine."""
        if not self.risk_engine:
            return {"approved": False, "reason": "Risk engine not initialized"}

        try:
            decision = self.risk_engine.evaluate(
                candidate=candidate,
                account_balance=self._get_balance(),
                open_positions=self.state.open_positions,
                daily_trades=self.state.daily_trades,
                daily_pnl=self.state.daily_pnl,
                consecutive_losses=self.state.consecutive_losses,
            )
            return decision
        except Exception as e:
            logger.error(f"Risk evaluation failed: {e}")
            return {"approved": False, "reason": str(e)}

    def _execute_order(self, candidate: Dict, risk_decision: Dict) -> Optional[Dict]:
        """Execute order through MT5 gateway."""
        if self.mode == "PAPER":
            return self._paper_execute(candidate, risk_decision)

        if not self.gateway or not self.gateway.is_connected():
            logger.warning("Cannot execute — MT5 not connected")
            return None

        try:
            result = self.gateway.send_market_order(
                symbol=candidate["symbol"],
                direction=candidate["direction"],
                volume=risk_decision.get("position_size", 0.01),
                stop_loss=risk_decision.get("stop_loss", 0),
                take_profit=risk_decision.get("take_profit", 0),
                magic=123456,
                comment=f"{candidate.get('strategy', 'unknown')}_v{candidate.get('version', '1.0')}",
            )

            if result.success:
                trade = {
                    "ticket": result.ticket,
                    "symbol": candidate["symbol"],
                    "direction": candidate["direction"],
                    "volume": result.volume,
                    "entry_price": result.price,
                    "stop_loss": risk_decision.get("stop_loss"),
                    "take_profit": risk_decision.get("take_profit"),
                    "strategy": candidate.get("strategy"),
                    "rule_score": candidate.get("rule_score"),
                    "ai_score": candidate.get("ai_score"),
                    "ml_score": candidate.get("ml_score"),
                    "combined_score": candidate.get("combined_score"),
                    "opened_at": datetime.now(),
                }
                self._trades_today.append(trade)
                self.state.daily_trades += 1
                logger.info(f"ORDER FILLED: {result.ticket} | {candidate['direction']} {result.volume} {candidate['symbol']}")
                return trade
            else:
                logger.error(f"ORDER FAILED: {result.error_message}")
                return None

        except Exception as e:
            logger.error(f"Execution failed: {e}")
            return None

    def _paper_execute(self, candidate: Dict, risk_decision: Dict) -> Dict:
        """Simulate order execution for paper trading."""
        import random

        entry_price = candidate.get("entry_price", candidate.get("market_context", {}).get("current_price", 0))
        spread = candidate.get("market_context", {}).get("spread", 20) * 0.01

        if candidate["direction"] == "BUY":
            entry_price += spread / 2
        else:
            entry_price -= spread / 2

        trade = {
            "ticket": int(time.time() * 1000) % 1000000,
            "symbol": candidate["symbol"],
            "direction": candidate["direction"],
            "volume": risk_decision.get("position_size", 0.01),
            "entry_price": entry_price,
            "stop_loss": risk_decision.get("stop_loss"),
            "take_profit": risk_decision.get("take_profit"),
            "strategy": candidate.get("strategy"),
            "rule_score": candidate.get("rule_score"),
            "ai_score": candidate.get("ai_score"),
            "ml_score": candidate.get("ml_score"),
            "combined_score": candidate.get("combined_score"),
            "opened_at": datetime.now(),
            "paper": True,
        }

        self._trades_today.append(trade)
        self.state.daily_trades += 1
        logger.info(f"PAPER TRADE: {candidate['direction']} {trade['volume']} {candidate['symbol']} @ {entry_price:.2f}")
        return trade

    def _manage_positions(self):
        """Manage open positions (BE, trailing, time exit)."""
        if not self.gateway or not self.gateway.is_connected():
            return

        try:
            positions = self.gateway.get_positions()
            for pos in positions:
                if pos["symbol"] != self.symbol:
                    continue

                # Check break-even
                if pos["profit"] > 0:
                    entry = pos["price_open"]
                    current = pos["price_current"]

                    if pos["direction"] == "BUY":
                        rr = (current - entry) / max(entry - pos["sl"], 0.01)
                    else:
                        rr = (entry - current) / max(pos["sl"] - entry, 0.01)

                    if rr >= 1.0 and pos["sl"] != entry:
                        result = self.gateway.move_to_breakeven(pos["ticket"], buffer_points=5)
                        if result.success:
                            logger.info(f"BE moved for position {pos['ticket']}")

        except Exception as e:
            logger.error(f"Position management failed: {e}")

    def _get_session(self) -> str:
        """Get current trading session."""
        now = datetime.utcnow()
        hour = now.hour

        if 0 <= hour < 8:
            return "ASIA"
        elif 7 <= hour < 16:
            if 12 <= hour < 16:
                return "LONDON_NY_OVERLAP"
            return "LONDON"
        elif 12 <= hour < 21:
            return "NEW_YORK"
        else:
            return "OFF_HOURS"

    def _get_balance(self) -> float:
        """Get account balance."""
        if self.gateway and self.gateway.is_connected():
            info = self.gateway.get_account_info()
            return info.balance if info else 10000
        return 10000

    def _check_kill_switch(self):
        """Check kill switch conditions."""
        # Daily loss limit
        balance = self._get_balance()
        if balance > 0 and abs(self.state.daily_pnl) / balance > 0.015:
            self.state.kill_switch_active = True
            logger.warning("KILL SWITCH: Daily loss limit exceeded")

        # Consecutive losses
        if self.state.consecutive_losses >= 3:
            self.state.kill_switch_active = True
            logger.warning("KILL SWITCH: Consecutive loss limit reached")

    def _log_cycle(self, candidates: List[Dict], trades: List[Dict]):
        """Log cycle results."""
        self.state.cycle_count += 1
        self.state.last_scan = datetime.now()

        logger.info(
            f"Cycle #{self.state.cycle_count} | "
            f"Candidates: {len(candidates)} | "
            f"Trades today: {self.state.daily_trades} | "
            f"Open: {self.state.open_positions} | "
            f"Session: {self._get_session()}"
        )

    def _trading_loop(self):
        """Main trading loop iteration."""
        try:
            # Check kill switch
            self._check_kill_switch()
            if self.state.kill_switch_active:
                logger.warning("Kill switch active — pausing trading")
                time.sleep(300)  # Wait 5 minutes
                return

            # Scan market
            candidates = self._scan_market()

            # Process each candidate
            for candidate in candidates:
                # Score with AI/ML
                candidate = self._score_candidate(candidate)

                # Evaluate risk
                risk_decision = self._evaluate_risk(candidate)

                if risk_decision.get("approved", False):
                    # Execute
                    trade = self._execute_order(candidate, risk_decision)
                    if trade:
                        logger.info(f"Trade executed: {trade.get('ticket')}")
                else:
                    reason = risk_decision.get("reason", "unknown")
                    logger.info(f"Candidate rejected: {reason}")

                # Log candidate (even if rejected)
                self._candidates_today.append({
                    **candidate,
                    "risk_decision": risk_decision,
                    "timestamp": datetime.now().isoformat(),
                })

            # Manage open positions
            self._manage_positions()

            # Log cycle
            self._log_cycle(candidates, [])

        except Exception as e:
            logger.error(f"Trading loop error: {e}", exc_info=True)

    def start(self):
        """Start the auto-trading loop."""
        self.initialize()
        self.state.is_running = True

        logger.info("=" * 60)
        logger.info(f"AUTO TRADER STARTED — Mode: {self.mode}")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Scan interval: {self.scan_interval}s")
        logger.info("=" * 60)

        try:
            while self.state.is_running:
                self._trading_loop()
                time.sleep(self.scan_interval)
        except KeyboardInterrupt:
            logger.info("Auto trader stopped by user")
        finally:
            self.stop()

    def stop(self):
        """Stop the auto-trading loop."""
        self.state.is_running = False
        if self.gateway:
            self.gateway.disconnect()
        logger.info("Auto trader stopped")

    def run_once(self):
        """Run a single scan cycle (for testing)."""
        self.initialize()
        self._trading_loop()
        self.stop()

    def get_status(self) -> Dict:
        """Get current trading status."""
        return {
            "mode": self.mode,
            "is_running": self.state.is_running,
            "cycle_count": self.state.cycle_count,
            "last_scan": self.state.last_scan.isoformat() if self.state.last_scan else None,
            "daily_trades": self.state.daily_trades,
            "daily_pnl": self.state.daily_pnl,
            "consecutive_losses": self.state.consecutive_losses,
            "kill_switch_active": self.state.kill_switch_active,
            "open_positions": self.state.open_positions,
            "candidates_today": len(self._candidates_today),
            "trades_today": len(self._trades_today),
            "mt5_connected": self.gateway.is_connected() if self.gateway else False,
        }
