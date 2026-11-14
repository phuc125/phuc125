"""
Shared Performance & Risk-Adjusted Metrics Analyzer.
Computes win rate, profit factor, expected value per trade, net profit, maximum drawdown,
Sharpe ratio, Sortino ratio, fee ratio, and breakdown by strategy family and market regime.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

import numpy as np

from database.models import PositionRecord


@dataclass
class PerformanceReport:
    """Comprehensive trading performance report."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    expected_value_usdt: float
    net_profit_usdt: float
    gross_profit_usdt: float
    gross_loss_usdt: float
    total_fees_usdt: float
    fees_pct_of_gross_profit: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    avg_win_usdt: float
    avg_loss_usdt: float
    performance_by_strategy: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PerformanceAnalyzer:
    """Computes realistic institutional performance statistics from closed positions and equity curves."""

    @staticmethod
    def analyze(
        closed_positions: List[PositionRecord],
        equity_curve: List[float],
    ) -> PerformanceReport:
        n = len(closed_positions)
        if n == 0:
            return PerformanceReport(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                expected_value_usdt=0.0,
                net_profit_usdt=0.0,
                gross_profit_usdt=0.0,
                gross_loss_usdt=0.0,
                total_fees_usdt=0.0,
                fees_pct_of_gross_profit=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                avg_win_usdt=0.0,
                avg_loss_usdt=0.0,
            )

        pnls = [p.realized_pnl_usdt for p in closed_positions]
        wins = [x for x in pnls if x > 0]
        losses = [x for x in pnls if x <= 0]

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        net_profit = sum(pnls)
        total_fees = sum(p.fees_paid_usdt for p in closed_positions)

        win_rate = (len(wins) / n) * 100.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 1e-9 else (gross_profit if gross_profit > 0 else 0.0)
        ev = net_profit / n
        avg_win = (gross_profit / len(wins)) if wins else 0.0
        avg_loss = (-gross_loss / len(losses)) if losses else 0.0
        fees_pct = (total_fees / gross_profit * 100.0) if gross_profit > 1e-9 else 100.0

        # Maximum drawdown from equity curve
        max_dd_pct = 0.0
        if equity_curve:
            peak = equity_curve[0]
            for eq in equity_curve:
                if eq > peak:
                    peak = eq
                if peak > 0:
                    dd = ((peak - eq) / peak) * 100.0
                    if dd > max_dd_pct:
                        max_dd_pct = dd

        # Trade-by-trade Sharpe and Sortino ratios
        ret_arr = np.array(pnls, dtype=float)
        mean_ret = float(np.mean(ret_arr))
        std_ret = float(np.std(ret_arr))
        sharpe = (mean_ret / std_ret * math.sqrt(n)) if std_ret > 1e-9 else 0.0

        downside = ret_arr[ret_arr < 0]
        downside_std = float(np.std(downside)) if len(downside) > 1 else (abs(float(downside[0])) if len(downside) == 1 else 0.0)
        sortino = (mean_ret / downside_std * math.sqrt(n)) if downside_std > 1e-9 else 0.0

        by_strat: Dict[str, Dict[str, float]] = {}
        for pos in closed_positions:
            st = pos.strategy_family
            entry = by_strat.setdefault(st, {"trades": 0.0, "wins": 0.0, "net_pnl_usdt": 0.0})
            entry["trades"] += 1.0
            if pos.realized_pnl_usdt > 0:
                entry["wins"] += 1.0
            entry["net_pnl_usdt"] = round(entry["net_pnl_usdt"] + pos.realized_pnl_usdt, 4)

        for st, stats in by_strat.items():
            stats["win_rate_pct"] = round((stats["wins"] / max(1.0, stats["trades"])) * 100.0, 2)

        return PerformanceReport(
            total_trades=n,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 3),
            expected_value_usdt=round(ev, 5),
            net_profit_usdt=round(net_profit, 4),
            gross_profit_usdt=round(gross_profit, 4),
            gross_loss_usdt=round(gross_loss, 4),
            total_fees_usdt=round(total_fees, 5),
            fees_pct_of_gross_profit=round(fees_pct, 2),
            max_drawdown_pct=round(max_dd_pct, 3),
            sharpe_ratio=round(sharpe, 3),
            sortino_ratio=round(sortino, 3),
            avg_win_usdt=round(avg_win, 5),
            avg_loss_usdt=round(avg_loss, 5),
            performance_by_strategy=by_strat,
        )
