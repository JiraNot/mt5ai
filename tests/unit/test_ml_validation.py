import numpy as np
import pytest
from src.ai.ml_trainer import MLTrainer, FEATURE_COLUMNS


def test_walkforward_scaler_never_fits_holdout_and_artifact_not_auto_enabled(tmp_path):
    pytest.importorskip('sklearn')
    trainer = MLTrainer(str(tmp_path))
    rng = np.random.default_rng(42)
    X = rng.normal(size=(100, len(FEATURE_COLUMNS)))
    y = np.arange(100) % 2
    X[80:] += 1000  # Distinct future distribution must not influence scaler.
    results = trainer.train(X, y)
    assert results
    np.testing.assert_allclose(trainer.scaler.mean_, X[:80].mean(axis=0))
    assert trainer.holdout_metrics['size'] == 20
    assert not trainer.deployment_approved
    trainer.save_model()
    other = MLTrainer(str(tmp_path))
    assert other.load_model()
    assert not other.deployment_approved
    assert other.predict({}) is None


def test_failed_retrain_clears_previous_model(tmp_path):
    trainer = MLTrainer(str(tmp_path))
    trainer.best_model = object()
    assert trainer.train(np.empty((0, len(FEATURE_COLUMNS))), np.array([])) == []
    assert trainer.best_model is None


def test_training_purges_labels_that_close_in_holdout(tmp_path):
    from datetime import datetime, timedelta, timezone
    pytest.importorskip('sklearn')
    trainer = MLTrainer(str(tmp_path))
    X = np.random.default_rng(3).normal(size=(100, len(FEATURE_COLUMNS)))
    y = np.arange(100) % 2
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    trainer.sample_times = [start + timedelta(hours=i) for i in range(100)]
    trainer.label_end_times = [t + timedelta(minutes=5) for t in trainer.sample_times]
    trainer.label_end_times[79] = trainer.sample_times[81]
    assert trainer.train(X, y)
    np.testing.assert_allclose(trainer.scaler.mean_, X[:79].mean(axis=0))
    assert trainer.holdout_metrics['label_intervals_verified']
