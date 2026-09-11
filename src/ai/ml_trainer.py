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
        self.version: str = "2.0.0"
        self.deployment_approved = False
        self.holdout_metrics = {}
        self.sample_times = []
        self.label_end_times = []

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
            ctx = candidate.get("market_context")
            if not isinstance(ctx, dict) or not ctx:
                return None
            structure = ctx.get("structure") or {}
            regime = ctx.get("regime") or {}
            liquidity = ctx.get("liquidity") or {}
            fvg = ctx.get("fvg") or {}
            ob = ctx.get("order_block") or {}
            zone = ctx.get("zone") or {}

            ts = candidate["timestamp"]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if isinstance(ts, datetime):
                hour = ts.hour
                dow = ts.weekday()
            else:
                hour = 12
                dow = 0

            session = candidate.get("session", "UNKNOWN").upper()

            features = [
                # Hour and day
                hour / 24.0,
                dow / 6.0,
                1.0 if session in ("ASIA", "ASIAN") else 0.0,
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

    def load_dataset(self, db_path: str = "freebuff.db") -> Tuple[np.ndarray, np.ndarray]:
        """Load only reconciled outcomes joined to immutable entry snapshots.

        Old unverified trades are deliberately excluded. Empty and malformed
        datasets never become synthetic zero-feature training observations.
        """
        import sqlite3
        from datetime import timezone
        self.sample_times = []
        self.label_end_times = []
        with sqlite3.connect(db_path) as conn:
            try:
                rows = conn.execute("""
                    SELECT snapshot_json, outcome_json FROM learning_evidence
                    WHERE outcome_json IS NOT NULL
                """).fetchall()
            except sqlite3.OperationalError:
                logger.warning("No verified learning evidence table")
                return np.empty((0, len(FEATURE_COLUMNS))), np.array([])
        samples = []
        for snapshot_json, outcome_json in rows:
            try:
                candidate = json.loads(snapshot_json)
                outcome = json.loads(outcome_json)
                if candidate.get("schema_version") != "1.0.0":
                    continue
                start = datetime.fromisoformat(candidate["timestamp"])
                end = datetime.fromisoformat(outcome["close_time"])
                start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start
                end = end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end
                net = float(outcome["net_profit"])
                if end < start or not np.isfinite(net) or net == 0:
                    continue  # Breakeven is neither a win nor a loss.
                features = self._extract_features(candidate)
                if features is None or not np.isfinite(features).all():
                    continue
                samples.append((start, end, features, int(net > 0)))
            except (KeyError, ValueError, TypeError):
                logger.warning("Skipping invalid learning evidence")
        samples.sort(key=lambda row: row[0])
        self.sample_times = [row[0] for row in samples]
        self.label_end_times = [row[1] for row in samples]
        return (np.array([row[2] for row in samples]).reshape(-1, len(FEATURE_COLUMNS)),
                np.array([row[3] for row in samples]))

    def load_from_csv(self, csv_path: str) -> Tuple[np.ndarray, np.ndarray]:
        """Load dataset from CSV file."""
        import csv

        X_list = []
        y_list = []

        self.sample_times = []
        self.label_end_times = []
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = sorted(reader, key=lambda row: row.get("timestamp", ""))
            for row in rows:
                if row.get("outcome", "").upper() not in ("WIN", "LOSS"):
                    continue
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

                label = 1 if row.get("outcome", "").upper() == "WIN" else 0
                X_list.append(features)
                y_list.append(label)

        return np.array(X_list), np.array(y_list)

    def train(self, X: np.ndarray, y: np.ndarray) -> List[TrainingResult]:
        """Walk-forward selection on development data, then untouched final holdout.

        All preprocessing is fitted inside each training fold. Label intervals
        crossing a boundary are purged when verified dataset timestamps exist.
        Research artifacts are never automatically enabled for trading.
        """
        self.models = {}
        self.best_model = None
        self.best_model_name = None
        self.scaler = None
        self.training_results = []
        self.holdout_metrics = {}
        self.deployment_approved = False
        if not SKLEARN_AVAILABLE or len(X) < 50:
            return []
        from sklearn.base import clone
        if X.ndim != 2 or X.shape[1] != len(FEATURE_COLUMNS) or len(y) != len(X):
            raise ValueError("Invalid feature/label shape")
        if not np.isfinite(X).all() or not set(np.unique(y)).issubset({0, 1}):
            raise ValueError("Invalid training data")
        has_times = len(getattr(self, "sample_times", [])) == len(X)
        if has_times and self.sample_times != sorted(self.sample_times):
            raise ValueError("Training samples must be chronological")
        split = int(len(X) * 0.8)
        def purge(indices, boundary):
            if not has_times:
                return indices
            return np.array([i for i in indices
                             if self.label_end_times[i] < self.sample_times[boundary]], dtype=int)
        factories = {
            "LogisticRegression": LogisticRegression(max_iter=1000, random_state=42),
            "RandomForest": RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=1),
        }
        if LIGHTGBM_AVAILABLE:
            factories["LightGBM"] = lgb.LGBMClassifier(n_estimators=100, random_state=42, verbosity=-1)
        results = []
        folds = list(TimeSeriesSplit(n_splits=3).split(X[:split]))
        rule_column = FEATURE_COLUMNS.index("rule_score")
        for name, prototype in factories.items():
            scores, baselines = [], []
            for train_idx, val_idx in folds:
                train_idx = purge(train_idx, val_idx[0])
                if len(train_idx) == 0 or len(np.unique(y[train_idx])) < 2 or len(np.unique(y[val_idx])) < 2:
                    continue
                scaler = StandardScaler().fit(X[train_idx])
                model = clone(prototype).fit(scaler.transform(X[train_idx]), y[train_idx])
                proba = model.predict_proba(scaler.transform(X[val_idx]))[:, 1]
                pred = proba >= 0.5
                scores.append((accuracy_score(y[val_idx], pred), precision_score(y[val_idx], pred, zero_division=0),
                               recall_score(y[val_idx], pred, zero_division=0), f1_score(y[val_idx], pred, zero_division=0),
                               roc_auc_score(y[val_idx], proba), len(train_idx), len(val_idx)))
                baselines.append(roc_auc_score(y[val_idx], X[val_idx, rule_column]))
            if len(scores) != len(folds):
                continue  # Insufficient class coverage for a credible comparison.
            mean = np.mean(scores, axis=0)
            results.append(TrainingResult(
                model_name=name, accuracy=float(mean[0]), precision=float(mean[1]),
                recall=float(mean[2]), f1=float(mean[3]), auc_roc=float(mean[4]),
                feature_importance={}, train_size=int(mean[5]), test_size=int(mean[6]),
                trained_at=datetime.now().isoformat(),
            ))
            self.walk_forward_baseline_auc = float(np.mean(baselines))
        if not results:
            return []
        best = max(results, key=lambda result: result.auc_roc)
        train_idx = purge(np.arange(split), split)
        if not len(train_idx) or len(np.unique(y[train_idx])) < 2:
            return []
        self.scaler = StandardScaler().fit(X[train_idx])
        self.best_model = clone(factories[best.model_name]).fit(self.scaler.transform(X[train_idx]), y[train_idx])
        self.best_model_name = best.model_name
        self.models[best.model_name] = self.best_model
        self.training_results = results
        proba = self.best_model.predict_proba(self.scaler.transform(X[split:]))[:, 1]
        if len(np.unique(y[split:])) == 2:
            self.holdout_metrics = {
                "auc": float(roc_auc_score(y[split:], proba)),
                "rule_baseline_auc": float(roc_auc_score(y[split:], X[split:, rule_column])),
                "size": len(y[split:]), "label_intervals_verified": has_times,
            }
        return results

    def predict(self, candidate: Dict) -> Optional[MLPrediction]:
        """Predict win probability for a trade candidate."""
        if not self.deployment_approved or self.best_model is None or self.scaler is None:
            return None

        features = self._extract_features(candidate)
        if features is None:
            return None

        X = np.array([features])
        X_scaled = self.scaler.transform(X)

        try:
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
            "deployment_approved": False,
            "holdout_metrics": self.holdout_metrics,
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
            if model_data.get("version") != self.version or model_data.get("feature_columns") != FEATURE_COLUMNS:
                return False
            self.deployment_approved = False
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
            "ML Training Report (research only; deployment disabled)",
            "=" * 60,
            f"Best Model: {self.best_model_name}",
            f"Version: {self.version}",
            "",
            "Model Comparison (walk-forward validation):",
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

        lines.append(f"Final untouched holdout: {self.holdout_metrics}")
        lines.append("=" * 60)
        return "\n".join(lines)
