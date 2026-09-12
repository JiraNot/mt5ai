"""Periodic research-only retraining from verified demo outcomes."""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

from src.ai.ml_trainer import MLTrainer

logger = logging.getLogger("retrain_loop")


def verified_outcome_count(db_path: str) -> int:
    """Return the number of evidence rows with a confirmed broker outcome."""
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM learning_evidence WHERE outcome_json IS NOT NULL"
            ).fetchone()
        return int(row[0] if row else 0)
    except (sqlite3.Error, TypeError):
        return 0


def _read_state(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return 0


def _write_state(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(str(count), encoding="utf-8")
    os.replace(temporary, path)


def train_if_ready(
    db_path: str,
    model_dir: str,
    minimum_samples: int = 50,
    state_path: str | None = None,
) -> bool:
    """Train once when new verified data reaches the configured threshold."""
    count = verified_outcome_count(db_path)
    state = Path(state_path or Path(model_dir) / ".retrain-state")
    if count < minimum_samples:
        logger.info("Waiting for verified outcomes: %d/%d", count, minimum_samples)
        return False
    if count <= _read_state(state):
        logger.info("No new verified outcomes since last training (%d)", count)
        return False

    trainer = MLTrainer(model_dir)
    features, labels = trainer.load_dataset(db_path)
    if len(labels) < minimum_samples:
        logger.info("Usable labelled outcomes: %d/%d", len(labels), minimum_samples)
        return False
    results = trainer.train(features, labels)
    if not results:
        logger.warning("Training produced no valid research model")
        return False
    trainer.save_model("research_model.pkl")
    _write_state(state, count)
    logger.info("Research model retrained from %d verified outcomes", len(labels))
    return True


def main() -> None:
    logging.basicConfig(
        level=os.getenv("TRAINING_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    db_path = os.getenv("TRAINING_DB_PATH", "/app/data/freebuff.db")
    model_dir = os.getenv("TRAINING_MODEL_DIR", "/app/models")
    minimum_samples = int(os.getenv("TRAINING_MIN_SAMPLES", "50"))
    interval = max(300, int(os.getenv("TRAINING_INTERVAL_SECONDS", "86400")))
    while True:
        try:
            train_if_ready(db_path, model_dir, minimum_samples)
        except Exception:
            logger.exception("Scheduled training failed; will retry")
        time.sleep(interval)


if __name__ == "__main__":
    main()
