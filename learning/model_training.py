"""
Chronological ML Model Trainer.
Enforces strict time-ordered train/validation/test splits to prevent look-ahead bias
and data leakage. Refuses to train on corrupted or NaN-contaminated datasets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from shared_core.prediction_engine import PredictionEngine


@dataclass
class ChronologicalSplitResult:
    """Metrics from a strictly chronological train/val/test split."""
    train_size: int
    val_size: int
    test_size: int
    train_metrics: Dict[str, float]
    val_rmse: float
    test_rmse: float
    test_directional_accuracy: float


class ModelTrainer:
    """Trains the hybrid PredictionEngine using leak-free chronological splits."""

    @staticmethod
    def chronological_split(
        X: np.ndarray,
        y: np.ndarray,
        train_frac: float = 0.60,
        val_frac: float = 0.20,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Split time-ordered feature matrix X and target vector y chronologically."""
        if len(X) != len(y) or len(X) < 10:
            raise ValueError("Dataset must have matching X, y lengths and at least 10 chronological samples.")
        if np.isnan(X).any() or np.isnan(y).any() or np.isinf(X).any() or np.isinf(y).any():
            raise ValueError("Corrupted data detected (NaN or Inf present); aborting model training.")

        n = len(X)
        i_train = max(2, int(n * train_frac))
        i_val = max(i_train + 1, int(n * (train_frac + val_frac)))

        return (
            X[:i_train],
            y[:i_train],
            X[i_train:i_val],
            y[i_train:i_val],
            X[i_val:],
            y[i_val:],
        )

    @classmethod
    def train_and_evaluate(
        cls,
        engine: PredictionEngine,
        X: np.ndarray,
        y: np.ndarray,
    ) -> ChronologicalSplitResult:
        X_tr, y_tr, X_val, y_val, X_te, y_te = cls.chronological_split(X, y)
        train_metrics = engine.fit_chronological(X_tr, y_tr)

        val_preds = engine.gbdt_return_model.predict(X_val)
        test_preds = engine.gbdt_return_model.predict(X_te)

        val_rmse = float(np.sqrt(np.mean((y_val - val_preds) ** 2)))
        test_rmse = float(np.sqrt(np.mean((y_te - test_preds) ** 2)))
        test_dir = float(np.mean(np.sign(test_preds) == np.sign(y_te)))

        return ChronologicalSplitResult(
            train_size=len(X_tr),
            val_size=len(X_val),
            test_size=len(X_te),
            train_metrics=train_metrics,
            val_rmse=round(val_rmse, 4),
            test_rmse=round(test_rmse, 4),
            test_directional_accuracy=round(test_dir, 4),
        )
