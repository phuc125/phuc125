"""
Backtest Performance Metrics Wrapper.
Provides regime-level and strategy-level performance breakdowns on top of shared_core/performance_analyzer.py.
"""
from __future__ import annotations

from typing import Any, Dict, List

from database.models import PositionRecord
from shared_core.performance_analyzer import PerformanceAnalyzer, PerformanceReport


def compute_backtest_metrics(
    closed_positions: List[PositionRecord],
    equity_curve: List[float],
) -> Dict[str, Any]:
    report: PerformanceReport = PerformanceAnalyzer.analyze(closed_positions, equity_curve)
    return report.to_dict()
