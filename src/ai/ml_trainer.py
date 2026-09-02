"""
ML Training Pipeline — learns from trade history to predict setup quality.

Trains multiple models (Logistic Regression, Random Forest, LightGBM)
and selects the best one based on out-of-sample performance.

The model predicts: Will this setup result in a profitable trade?

Usage:
    trainer = MLTrainer()
    trainer.load_dataset("trades.db")
    trainer.train()
    trainer.save_model("models/current_model.pkl")
    
    # Predict
    prediction = trainer.predict(features)
    print(f"Win probability: {prediction.win_probability}")
    print(f"Confidence: {prediction.confidence}")
"""

import logging
import json
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# ML imports
try:
    from sklearn.model_selection import train_test_split, TimeSeriesSplit
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score,
        f1_score, roc_auc_score, classification_report,
    )
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False


# Feature columns for ML model
FEATURE_COLUMNS = [
    # Market features
    "hour",
    "day_of_week",
    "session_asia",
    "session_london",
    "session_new_york",
    
    # HTF features
    "htf_bullish",
    "htf_bearish",
    
    # Regime features
    "regime_trending",
    "regime_ranging",
    "regime_choppy",
    
    # Structure features
    "choch_strength",
    "bos_strength",
    "displacement_score",
    "swing_distance",
    
    # FVG features
    "fvg_present",
    "fvg_size_atr",
    "fvg_mitigation",
    
    # Order Block features
    "ob_present",
    "ob_score",
    
    # Liquidity features
    "liquidity_sweep",
    "sell_side_sweep",
    "buy_side_sweep",
    
    # Zone features
    "premium_zone",
    "discount_zone",
    "equilibrium_zone",
    
    # Trade features
    "rr",
    "rule_score",
    "spread",
]


@dataclass
class MLPrediction:
    """Result of ML model prediction."""
    win_probability: float  # 0.0 - 1.0
    confidence: float  # 0.0 - 1.0
    model_name: str
    features_importance: Dict[str, float] = field(default_factory=dict)
    raw_score: float = 0.0


@dataclass
class TrainingResult:
    """Result of model training."""
    model_name: str
    accuracy: float
    precision: float
    recall: float
    f1: float
    auc_roc: float
    feature_importance: Dict[str, float]
    train_size: int
    test_size: int
    trained_at: str


class MLTrainer:
    """
    ML Training Pipeline for trade setup prediction.
    
    Features are extracted from trade candidates.
    Labels are win/loss outcomes.
    """

    def __init__(self, model_dir: str = "models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        self.scaler: Optional[StandardScaler] = None
        self.models: Dict[str, Any] = {}
        self.best_model_name: Optional[str] = None
        self.best_model = None
        self.training_results: List[TrainingResult] = []
        self.version: str = "1.0.0"

    def _extract_features(self, candidate: Dict) -> Optional[List[float]]:
        """
        Extract ML features from a trade candidate.
        
        Candidate should contain:
        - market_context: dict with structure, regime, etc.
        - strategy: str
        - direction: str
        - rule_score: int
        - rr: float
        - spread: int
        """
        try:
            ctx = candidate.get("market_context", {})
            structure = ctx.get("structure", {})
            regime = ctx.get("regime", {})
            liquidity = ctx.get("liquidity", {})
            fvg = ctx.get("fvg", {})
            ob = ctx.get("order_block", {})
            zone = ctx.get("zone", {})

            ts = candidate.get("timestamp", datetime.now())
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if isinstance(ts, datetime):
                hour = ts.hour
                dow = ts.weekday()
            else:
                hour = 12
                dow = 0

            session = candidate.get("session", "UNKNOWN")

            features = [
                # Hour and day
                hour / 24.0,
                dow / 6.0,
                1.0 if session == "ASIA" else 0.0,
                1.0 if session == "LONDON" else 0.0,
                1.0 if session == "NEW_YORK" else 0.0,
                
                # HTF
                1.0 if ctx.get("htf_trend") == "bullish" else 0.0,
                1.0 if ctx.get("htf_trend") == "bearish" else 0.0,
                
                # Regime
                1.0 if regime.get("type") in ("STRONG_UPTREND", "MODERATE_UPTREND", "STRONG_DOWNTREND", "MODERATE_DOWNTREND") else 0.0,
                1.0 if regime.get("type") == "RANGING" else 0.0,
                1.0 if regime.get("type") == "CHOPPY" else 0.0,
                
                # Structure
                structure.get("choch_strength", 0) / 100.0,
                structure.get("bos_strength", 0) / 100.0,
                structure.get("displacement_score", 0) / 100.0,
                min(structure.get("swing_distance", 0) / 100.0, 1.0),
                
                # FVG
                1.0 if fvg.get("exists") else 0.0,
                min(fvg.get("size_atr", 0) / 2.0, 1.0),
                fvg.get("mitigation", 0) / 100.0,
                
                # Order Block
                1.0 if ob.get("exists") else 0.0,
                ob.get("score", 0) / 100.0,
                
                # Liquidity
                1.0 if liquidity.get("sweep") else 0.0,
                1.0 if liquidity.get("type") == "SELL_SIDE" else 0.0,
                1.0 if liquidity.get("type") == "BUY_SIDE" else 0.0,
                
                # Zone
                1.0 if zone.get("type") == "PREMIUM" else 0.0,
                1.0 if zone.get("type") == "DISCOUNT" else 0.0,
                1.0 if zone.get("type") == "EQUILIBRIUM" else 0.0,
                
                # Trade
                min(candidate.get("rr", 2.0) / 5.0, 1.0),
                candidate.get("rule_score", 50) / 100.0,
                min(candidate.get("spread", 20) / 100.0, 1.0),
            ]

            return features

        except Exception as e:
            logger.warning(f"Failed to extract features: {e}")
            return None

    def load_dataset(self, db_path: str = "trading.db") -> Tuple[np.ndarray, np.ndarray]:
        """
        Load dataset from trade candidates database.
        
        Returns:
            (X, y) where X is feature matrix and y is labels (1=win, 0=loss)
        """
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Try to get candidates with outcomes
        try:
            cursor.execute("""
                SELECT 
                    strategy, symbol, direction, setup_time, rule_score, rr,
                    market_context_json, evidence_json, status,
                    profit, r_multiple
                FROM trade_candidates
                WHERE status IN ('APPROVED', 'REJECTED')
                AND profit IS NOT NULL
                ORDER BY created_at
            """)
            rows = cursor.fetchall()
        except Exception:
            # Fallback: try trades table
            try:
                cursor.execute("""
                    SELECT 
                        strategy, symbol, direction, opened_at, 50, 2.0,
                        NULL, NULL, 'APPROVED',
                        profit, r_multiple
                    FROM trades
                    WHERE profit IS NOT NULL
                    ORDER BY opened_at
                """)
                rows = cursor.fetchall()
            except Exception:
                logger.warning("No trade data found in database")
                conn.close()
                return np.array([]), np.array([])

        conn.close()

        if not rows:
            logger.warning("No training data found")
            return np.array([]), np.array([])

        X_list = []
        y_list = []

        for row in rows:
            strategy, symbol, direction, setup_time, rule_score, rr, ctx_json, evidence_json, status, profit, r_multiple = row

            # Build candidate dict
            candidate = {
                "strategy": strategy,
                "symbol": symbol,
                "direction": direction,
                "timestamp": setup_time,
                "rule_score": rule_score or 50,
                "rr": rr or 2.0,
                "spread": 20,
                "market_context": {},
                "session": "UNKNOWN",
            }

            if ctx_json:
                try:
                    candidate["market_context"] = json.loads(ctx_json)
                except Exception:
                    pass

            features = self._extract_features(candidate)
            if features is None:
                continue

            # Label: win = 1, loss = 0
            label = 1 if (profit and profit > 0) or (r_multiple and r_multiple > 0) else 0

            X_list.append(features)
            y_list.append(label)

        X = np.array(X_list)
        y = np.array(y_list)

        logger.info(f"Loaded {len(X)} samples: {sum(y)} wins, {len(y) - sum(y)} losses")
        return X, y

    def load_from_csv(self, csv_path: str) -> Tuple[np.ndarray, np.ndarray]:
        """Load dataset from CSV file."""
        import csv

        X_list = []
        y_list = []

        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                candidate = {
                    "strategy": row.get("strategy", ""),
                    "symbol": row.get("symbol", "XAUUSD"),
                    "direction": row.get("direction", "BUY"),
                    "timestamp": row.get("timestamp", ""),
                    "rule_score": int(row.get("rule_score", 50)),
                    "rr": float(row.get("rr", 2.0)),
                    "spread": int(row.get("spread", 20)),
                    "market_context": json.loads(row.get("market_context", "{}")),
                    "session": row.get("session", "UNKNOWN"),
                }

                features = self._extract_features(candidate)
                if features is None:
                    continue

                label = 1 if row.get("outcome") == "win" else 0
                X_list.append(features)
                y_list.append(label)

        return np.array(X_list), np.array(y_list)

    def train(self, X: np.ndarray, y: np.ndarray) -> List[TrainingResult]:
        """
        Train multiple models and compare performance.
        
        Uses time-series split to avoid data leakage.
        """
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not installed")
            return []

        if len(X) < 50:
            logger.warning(f"Insufficient data: {len(X)} samples (need 50+)")
            return []

        logger.info(f"Training on {len(X)} samples with {X.shape[1]} features")

        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Time-series split (80/20)
        split_idx = int(len(X_scaled) * 0.8)
        X_train, X_test = X_scaled[:split_idx], X_scaled[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        results = []

        # 1. Logistic Regression
        try:
            lr = LogisticRegression(max_iter=1000, random_state=42)
            lr.fit(X_train, y_train)
            y_pred = lr.predict(X_test)
            y_proba = lr.predict_proba(X_test)[:, 1]

            result = TrainingResult(
                model_name="LogisticRegression",
                accuracy=accuracy_score(y_test, y_pred),
                precision=precision_score(y_test, y_pred, zero_division=0),
                recall=recall_score(y_test, y_pred, zero_division=0),
                f1=f1_score(y_test, y_pred, zero_division=0),
                auc_roc=roc_auc_score(y_test, y_proba) if len(set(y_test)) > 1 else 0.5,
                feature_importance=dict(zip(FEATURE_COLUMNS, lr.coef_[0])),
                train_size=len(X_train),
                test_size=len(X_test),
                trained_at=datetime.now().isoformat(),
            )
            self.models["LogisticRegression"] = lr
            results.append(result)
            logger.info(f"LogisticRegression: Acc={result.accuracy:.3f} AUC={result.auc_roc:.3f}")
        except Exception as e:
            logger.error(f"LogisticRegression failed: {e}")

        # 2. Random Forest
        try:
            rf = RandomForestClassifier(
                n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
            )
            rf.fit(X_train, y_train)
            y_pred = rf.predict(X_test)
            y_proba = rf.predict_proba(X_test)[:, 1]

            importance = dict(zip(FEATURE_COLUMNS, rf.feature_importances_))
            result = TrainingResult(
                model_name="RandomForest",
                accuracy=accuracy_score(y_test, y_pred),
                precision=precision_score(y_test, y_pred, zero_division=0),
                recall=recall_score(y_test, y_pred, zero_division=0),
                f1=f1_score(y_test, y_pred, zero_division=0),
                auc_roc=roc_auc_score(y_test, y_proba) if len(set(y_test)) > 1 else 0.5,
                feature_importance=importance,
                train_size=len(X_train),
                test_size=len(X_test),
                trained_at=datetime.now().isoformat(),
            )
            self.models["RandomForest"] = rf
            results.append(result)
            logger.info(f"RandomForest: Acc={result.accuracy:.3f} AUC={result.auc_roc:.3f}")
        except Exception as e:
            logger.error(f"RandomForest failed: {e}")

        # 3. LightGBM
        if LIGHTGBM_AVAILABLE:
            try:
                train_data = lgb.Dataset(X_train, label=y_train)
                valid_data = lgb.Dataset(X_test, label=y_test, reference=train_data)

                params = {
                    "objective": "binary",
                    "metric": "auc",
                    "boosting_type": "gbdt",
                    "num_leaves": 31,
                    "learning_rate": 0.05,
                    "feature_fraction": 0.9,
                    "bagging_fraction": 0.8,
                    "bagging_freq": 5,
                    "verbose": -1,
                    "random_state": 42,
                }

                gbm = lgb.train(
                    params,
                    train_data,
                    num_boost_round=100,
                    valid_sets=[valid_data],
                    callbacks=[lgb.log_evaluation(0)],
                )

                y_proba = gbm.predict(X_test)
                y_pred = (y_proba > 0.5).astype(int)

                importance = dict(zip(FEATURE_COLUMNS, gbm.feature_importance(importance_type="gain")))
                result = TrainingResult(
                    model_name="LightGBM",
                    accuracy=accuracy_score(y_test, y_pred),
                    precision=precision_score(y_test, y_pred, zero_division=0),
                    recall=recall_score(y_test, y_pred, zero_division=0),
                    f1=f1_score(y_test, y_pred, zero_division=0),
                    auc_roc=roc_auc_score(y_test, y_proba) if len(set(y_test)) > 1 else 0.5,
                    feature_importance=importance,
                    train_size=len(X_train),
                    test_size=len(X_test),
                    trained_at=datetime.now().isoformat(),
                )
                self.models["LightGBM"] = gbm
                results.append(result)
                logger.info(f"LightGBM: Acc={result.accuracy:.3f} AUC={result.auc_roc:.3f}")
            except Exception as e:
                logger.error(f"LightGBM failed: {e}")

        # Select best model by AUC-ROC
        if results:
            best = max(results, key=lambda r: r.auc_roc)
            self.best_model_name = best.model_name
            self.best_model = self.models[best.model_name]
            self.training_results = results
            logger.info(f"Best model: {best.model_name} (AUC={best.auc_roc:.3f})")

        return results

    def predict(self, candidate: Dict) -> Optional[MLPrediction]:
        """Predict win probability for a trade candidate."""
        if self.best_model is None or self.scaler is None:
            return None

        features = self._extract_features(candidate)
        if features is None:
            return None

        X = np.array([features])
        X_scaled = self.scaler.transform(X)

        try:
            if self.best_model_name == "LightGBM":
                proba = self.best_model.predict(X_scaled)[0]
            else:
                proba = self.best_model.predict_proba(X_scaled)[0][1]

            # Calculate confidence based on distance from 0.5
            confidence = abs(proba - 0.5) * 2  # 0 at 0.5, 1 at 0 or 1

            # Get feature importance
            importance = {}
            if hasattr(self.best_model, "feature_importances_"):
                importance = dict(zip(FEATURE_COLUMNS, self.best_model.feature_importances_))
            elif self.best_model_name == "LightGBM":
                importance = dict(zip(FEATURE_COLUMNS, self.best_model.feature_importance(importance_type="gain")))

            return MLPrediction(
                win_probability=float(proba),
                confidence=float(confidence),
                model_name=self.best_model_name,
                features_importance=importance,
                raw_score=float(proba),
            )
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return None

    def save_model(self, filename: str = "model.pkl"):
        """Save trained model to disk."""
        if not JOBLIB_AVAILABLE:
            logger.error("joblib not installed")
            return

        filepath = self.model_dir / filename
        model_data = {
            "model": self.best_model,
            "scaler": self.scaler,
            "model_name": self.best_model_name,
            "version": self.version,
            "trained_at": datetime.now().isoformat(),
            "feature_columns": FEATURE_COLUMNS,
            "training_results": [
                {
                    "model_name": r.model_name,
                    "accuracy": r.accuracy,
                    "auc_roc": r.auc_roc,
                    "f1": r.f1,
                }
                for r in self.training_results
            ],
        }

        joblib.dump(model_data, filepath)
        logger.info(f"Model saved to {filepath}")

    def load_model(self, filename: str = "model.pkl") -> bool:
        """Load trained model from disk."""
        if not JOBLIB_AVAILABLE:
            return False

        filepath = self.model_dir / filename
        if not filepath.exists():
            logger.warning(f"Model file not found: {filepath}")
            return False

        try:
            model_data = joblib.load(filepath)
            self.best_model = model_data["model"]
            self.scaler = model_data["scaler"]
            self.best_model_name = model_data["model_name"]
            self.version = model_data.get("version", "1.0.0")
            logger.info(f"Model loaded: {self.best_model_name} v{self.version}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    def generate_report(self) -> str:
        """Generate training report."""
        if not self.training_results:
            return "No training results available"

        lines = [
            "=" * 60,
            "ML Training Report",
            "=" * 60,
            f"Best Model: {self.best_model_name}",
            f"Version: {self.version}",
            "",
            "Model Comparison:",
            "-" * 60,
        ]

        for r in self.training_results:
            lines.append(
                f"  {r.model_name:20s} | "
                f"Acc={r.accuracy:.3f} | "
                f"AUC={r.auc_roc:.3f} | "
                f"F1={r.f1:.3f} | "
                f"P={r.precision:.3f} | "
                f"R={r.recall:.3f}"
            )

        lines.append("")
        lines.append(f"Train size: {self.training_results[0].train_size}")
        lines.append(f"Test size: {self.training_results[0].test_size}")

        # Top features
        if self.best_model_name and self.training_results:
            best_result = next(r for r in self.training_results if r.model_name == self.best_model_name)
            if best_result.feature_importance:
                sorted_features = sorted(
                    best_result.feature_importance.items(),
                    key=lambda x: abs(x[1]),
                    reverse=True,
                )[:10]
                lines.append("")
                lines.append("Top 10 Features:")
                for name, score in sorted_features:
                    lines.append(f"  {name:25s} {score:.4f}")

        lines.append("=" * 60)
        return "\n".join(lines)
