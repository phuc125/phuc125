"""
Experiment & Model Version Registry Tracker.
Stores model versions, out-of-sample metrics, and strategy experiments in SQLite.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from database.database import DatabaseManager
from database.models import utc_now_iso
from shared_core.feature_engineering import FEATURE_COLUMNS


class ExperimentTracker:
    """Persists model versions and experiment validation records in SQLite."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def register_model_version(
        self,
        version_id: str,
        model_type: str,
        metrics: Dict[str, Any],
        is_active: bool = False,
    ) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO model_registry (
                    version_id, model_type, metrics_json, feature_names_json, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    model_type,
                    json.dumps(metrics),
                    json.dumps(FEATURE_COLUMNS),
                    int(is_active),
                    utc_now_iso(),
                ),
            )

    def list_models(self) -> List[Dict[str, Any]]:
        with self.db.connection() as conn:
            rows = conn.execute("SELECT * FROM model_registry ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
