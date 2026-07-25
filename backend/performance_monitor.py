"""
performance_monitor.py
Real-time performance tracking for the self-improving trading bot.
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import statistics


@dataclass
class PerformanceSnapshot:
    timestamp: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_pnl_per_trade: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    consecutive_losses: int
    equity: float


@dataclass
class PerformanceThresholds:
    min_win_rate: float = 0.40
    min_sharpe: float = 0.5
    max_drawdown_pct: float = 5.0
    max_consecutive_losses: int = 5
    min_trades_for_assessment: int = 10
    lookback_window_minutes: int = 30


class PerformanceMonitor:
    """Monitors trading performance and triggers optimization when needed."""

    def __init__(self, thresholds: PerformanceThresholds = None):
        self.thresholds = thresholds or PerformanceThresholds()
        self.trades: List[Dict] = []
        self.equity_history: List[tuple[datetime, float]] = []
        self.snapshots: List[PerformanceSnapshot] = []
        self.last_assessment: Optional[datetime] = None
        self.optimization_triggered = False
        self._baseline_sharpe: Optional[float] = None

    def record_trade(self, pnl: float, entry_time: datetime, exit_time: datetime, 
                     symbol: str = "", reason: str = "") -> None:
        """Record a completed trade."""
        self.trades.append({
            "pnl": pnl,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "symbol": symbol,
            "reason": reason,
            "duration_minutes": (exit_time - entry_time).total_seconds() / 60
        })

    def record_equity(self, equity: float, timestamp: datetime = None) -> None:
        """Record equity snapshot."""
        self.equity_history.append((timestamp or datetime.now(), equity))

    def get_recent_trades(self, minutes: int = None) -> List[Dict]:
        """Get trades within lookback window."""
        if minutes is None:
            minutes = self.thresholds.lookback_window_minutes
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [t for t in self.trades if t["exit_time"] >= cutoff]

    def calculate_metrics(self, trade_subset: List[Dict] = None) -> Dict[str, float]:
        """Calculate performance metrics from trades."""
        trades = trade_subset or self.trades

        if len(trades) < self.thresholds.min_trades_for_assessment:
            return {"insufficient_data": True, "total_trades": len(trades)}

        winning = [t for t in trades if t["pnl"] > 0]
        losing = [t for t in trades if t["pnl"] <= 0]

        total_pnl = sum(t["pnl"] for t in trades)
        win_rate = len(winning) / len(trades) if trades else 0

        gross_profit = sum(t["pnl"] for t in winning)
        gross_loss = abs(sum(t["pnl"] for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        avg_pnl = total_pnl / len(trades) if trades else 0

        # Sharpe from equity curve
        sharpe = self._calculate_sharpe()

        # Max drawdown
        max_dd = self._calculate_max_drawdown()

        # Consecutive losses
        max_consec = self._calculate_consecutive_losses(trades)

        return {
            "total_trades": len(trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": win_rate * 100,
            "avg_pnl_per_trade": avg_pnl,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "profit_factor": profit_factor,
            "consecutive_losses": max_consec,
            "equity": self.equity_history[-1][1] if self.equity_history else 1_000_000,
        }

    def _calculate_sharpe(self) -> float:
        """Calculate Sharpe ratio from equity curve."""
        if len(self.equity_history) < 10:
            return 0.0

        equities = [e[1] for e in self.equity_history[-100:]]  # Last 100 points
        if len(equities) < 2:
            return 0.0

        returns = [(equities[i] - equities[i-1]) / equities[i-1] 
                   for i in range(1, len(equities)) if equities[i-1] > 0]

        if not returns or statistics.stdev(returns) == 0:
            return 0.0

        # Annualized (assuming ~375 1-min bars per day)
        return (statistics.mean(returns) / statistics.stdev(returns)) * (375 ** 0.5)

    def _calculate_max_drawdown(self) -> float:
        """Calculate max drawdown from equity curve."""
        if not self.equity_history:
            return 0.0

        peak = self.equity_history[0][1]
        max_dd = 0.0

        for _, equity in self.equity_history:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return max_dd * 100  # As percentage

    def _calculate_consecutive_losses(self, trades: List[Dict]) -> int:
        """Calculate max consecutive losing trades."""
        max_consec = 0
        current = 0
        for t in trades:
            if t["pnl"] <= 0:
                current += 1
                max_consec = max(max_consec, current)
            else:
                current = 0
        return max_consec

    def should_optimize(self) -> tuple[bool, str]:
        """Determine if strategy needs optimization."""
        recent_trades = self.get_recent_trades()

        if len(recent_trades) < self.thresholds.min_trades_for_assessment:
            return False, f"Only {len(recent_trades)} trades, need {self.thresholds.min_trades_for_assessment}"

        metrics = self.calculate_metrics(recent_trades)

        reasons = []

        if metrics["win_rate"] < self.thresholds.min_win_rate * 100:
            reasons.append(f"Win rate {metrics['win_rate']:.1f}% < {self.thresholds.min_win_rate*100:.0f}%")

        if metrics["sharpe_ratio"] < self.thresholds.min_sharpe:
            reasons.append(f"Sharpe {metrics['sharpe_ratio']:.2f} < {self.thresholds.min_sharpe}")

        if metrics["max_drawdown"] > self.thresholds.max_drawdown_pct:
            reasons.append(f"Drawdown {metrics['max_drawdown']:.2f}% > {self.thresholds.max_drawdown_pct}%")

        if metrics["consecutive_losses"] >= self.thresholds.max_consecutive_losses:
            reasons.append(f"{metrics['consecutive_losses']} consecutive losses")

        if reasons:
            return True, "; ".join(reasons)

        return False, "Performance within thresholds"

    def get_snapshot(self) -> PerformanceSnapshot:
        """Get current performance snapshot."""
        metrics = self.calculate_metrics()
        snap = PerformanceSnapshot(
            timestamp=datetime.now(),
            total_trades=metrics.get("total_trades", 0),
            winning_trades=metrics.get("winning_trades", 0),
            losing_trades=metrics.get("losing_trades", 0),
            win_rate=metrics.get("win_rate", 0),
            avg_pnl_per_trade=metrics.get("avg_pnl_per_trade", 0),
            sharpe_ratio=metrics.get("sharpe_ratio", 0),
            max_drawdown=metrics.get("max_drawdown", 0),
            profit_factor=metrics.get("profit_factor", 0),
            consecutive_losses=metrics.get("consecutive_losses", 0),
            equity=metrics.get("equity", 1_000_000)
        )
        self.snapshots.append(snap)
        return snap

    def reset(self) -> None:
        """Reset all tracking data."""
        self.trades = []
        self.equity_history = []
        self.snapshots = []
        self.last_assessment = None
        self.optimization_triggered = False
        self._baseline_sharpe = None