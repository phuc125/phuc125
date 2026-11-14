"""
Walk-Forward Out-of-Sample Validator.
Evaluates model and scoring stability across rolling chronological windows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from shared_core.prediction_engine import PredictionEngine


@dataclass
class WalkForwardFoldResult:
    fold_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    oos_rmse: float
    oos_directional_accuracy: float


@dataclass
class WalkForwardReport:
    n_folds: int
    mean_oos_rmse: float
    mean_oos_directional_accuracy: float
    folds: List[WalkForwardFoldResult] = field(default_factory=list)


class WalkForwardValidator:
    """Executes expanding-window walk-forward validation with zero look-ahead leakage."""

    @staticmethod
    def run_walk_forward(
        X: np.ndarray,
        y: np.ndarray,
        n_splits: int = 3,
    ) -> WalkForwardReport:
        n = len(X)
        if n < (n_splits + 1) * 5:
            raise ValueError("Insufficient samples for requested walk-forward splits.")

        step = n // (n_splits + 1)
        folds: List[WalkForwardFoldResult] = []

        for k in range(1, n_splits + 1):
            train_end = k * step
            test_end = min(n, (k + 1) * step)
            X_tr, y_tr = X[:train_end], y[:train_end]
            X_te, y_te = X[train_end:test_end], y[train_end:test_end]

            eng = PredictionEngine(model_version=f"wf_fold_{k}")
            eng.fit_chronological(X_tr, y_tr)
            preds = eng.gbdt_return_model.predict(X_te)

            rmse = float(np.sqrt(np.mean((y_te - preds) ** 2)))
            dir_acc = float(np.mean(np.sign(preds) == np.sign(y_te)))
            folds.append(
                WalkForwardFoldResult(
                    fold_index=k,
                    train_start=0,
                    train_end=train_end,
                    test_start=train_end,
                    test_end=test_end,
                    oos_rmse=round(rmse, 4),
                    oos_directional_accuracy=round(dir_acc, 4),
                )
            )

        mean_rmse = float(np.mean([f.oos_rmse for f in folds]))
        mean_dir = float(np.mean([f.oos_directional_accuracy for f in folds]))
        return WalkForwardReport(
            n_folds=len(folds),
            mean_oos_rmse=round(mean_rmse, 4),
            mean_oos_directional_accuracy=round(mean_dir, 4),
            folds=folds,
        )
