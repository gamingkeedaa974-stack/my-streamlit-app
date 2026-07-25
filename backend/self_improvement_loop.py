"""
self_improvement_loop.py
Autonomous self-improving trading agent.
Monitors performance, triggers optimization, validates and applies new parameters.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass

from backend.performance_monitor import PerformanceMonitor, PerformanceThresholds
from backend.auto_improvement_agent import AutoImprovementAgent, DataGenerator
from backend.strategies.strategy import StrategyRegistry
from backend.backtest_engine import BacktestEngine
from backend.risk_manager import RiskConfig


@dataclass
class SelfImprovementConfig:
    check_interval_minutes: int = 10
    min_trades_before_optimize: int = 10
    optimization_iterations: int = 30
    synthetic_days_for_opt: int = 60
    validation_minutes: int = 15  # A/B test new params for 15 min before full commit
    max_param_changes_per_day: int = 3
    improvement_threshold_pct: float = 10.0  # Min % improvement to apply


class SelfImprovementLoop:
    """
    Autonomous agent that:
    1. Monitors live trading performance
    2. Triggers optimization when metrics degrade
    3. Validates new params via backtest
    4. A/B tests new params briefly
    5. Auto-applies if validated, reverts if not
    """

    def __init__(self, strategy_name: str, config: SelfImprovementConfig = None, symbol: str = "NIFTY50"):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.config = config or SelfImprovementConfig()
        self.monitor = PerformanceMonitor(PerformanceThresholds())
        self.current_params: Dict[str, Any] = {}
        self.candidate_params: Optional[Dict[str, Any]] = None
        self.is_ab_testing = False
        self.ab_test_start: Optional[datetime] = None
        self.ab_test_monitor: Optional[PerformanceMonitor] = None
        self.optimization_count_today = 0
        self.last_opt_date: Optional[datetime.date] = None
        self._running = False
        self._task = None

    async def start(self, initial_params: Dict[str, Any] = None):
        """Start the self-improvement monitoring loop."""
        self.current_params = initial_params or self._get_default_params()
        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())

    async def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _monitoring_loop(self):
        """Main loop: check performance periodically."""
        while self._running:
            await asyncio.sleep(self.config.check_interval_minutes * 60)

            if not self._running:
                break

            await self._assess_and_act()

    async def _assess_and_act(self):
        """Assess performance and take action if needed."""
        # Reset daily optimization count
        today = datetime.now().date()
        if self.last_opt_date != today:
            self.optimization_count_today = 0
            self.last_opt_date = today

        # Skip if already A/B testing
        if self.is_ab_testing:
            await self._check_ab_test_results()
            return

        # Check if performance degraded
        should_opt, reason = self.monitor.should_optimize()

        if should_opt:
            if self.optimization_count_today >= self.config.max_param_changes_per_day:
                print(f"[SELF-IMPROVE] Performance degraded ({reason}) but max daily changes reached")
                return

            print(f"[SELF-IMPROVE] Triggering optimization: {reason}")
            await self._run_optimization()

    async def _run_optimization(self):
        """Run optimization and validate results."""
        try:
            # Generate data with symbol-specific volatility
            data = DataGenerator.generate_synthetic_data(
                days=self.config.synthetic_days_for_opt,
                symbol=self.symbol,
                seed=None
            )

            agent = AutoImprovementAgent(
                strategy_name=self.strategy_name,
                data=data,
                output_dir="data/self_improvement",
                symbol=self.symbol
            )

            result = await agent.run_adaptive_search(iterations=self.config.optimization_iterations)

            if not result:
                print("[SELF-IMPROVE] Optimization failed")
                return

            # Check improvement threshold
            if result.improvement_pct < self.config.improvement_threshold_pct:
                print(f"[SELF-IMPROVE] Improvement {result.improvement_pct:.1f}% below threshold {self.config.improvement_threshold_pct}%")
                return

            # Validate: backtest new params on unseen data
            is_valid = await self._validate_params(result.best_params, data)

            if not is_valid:
                print("[SELF-IMPROVE] New params failed validation")
                return

            # Start A/B test
            self.candidate_params = result.best_params
            await self._start_ab_test()

            self.optimization_count_today += 1

        except Exception as e:
            print(f"[SELF-IMPROVE] Optimization error: {e}")

    async def _validate_params(self, params: Dict[str, Any], data) -> bool:
        """Validate new params via walk-forward backtest."""
        try:
            # Split data: 70% train, 30% test
            split_idx = int(len(data) * 0.7)
            test_data = data.iloc[split_idx:]

            strategy_cls = StrategyRegistry.get(self.strategy_name)
            config_cls = StrategyRegistry.get_config_class(self.strategy_name)

            config = config_cls(name=self.strategy_name, **params)
            strategy = strategy_cls(config)
            # ── NEW: Reset strategy before validation ──
            strategy.reset()

            engine = BacktestEngine(strategy, RiskConfig(), test_data, symbol=self.symbol)
            result = await engine.run()

            # Validation criteria
            if result.total_trades < 3:
                print(f"[VALIDATE] Only {result.total_trades} trades on test set")
                return False

            if result.total_pnl_pct <= 0:
                print(f"[VALIDATE] Test P&L {result.total_pnl_pct:.2f}% not positive")
                return False

            if result.win_rate < 40:
                print(f"[VALIDATE] Test win rate {result.win_rate:.1f}% too low")
                return False

            print(f"[VALIDATE] Passed: P&L {result.total_pnl_pct:.2f}%, Win Rate {result.win_rate:.1f}%")
            return True

        except Exception as e:
            print(f"[VALIDATE] Error: {e}")
            return False

    async def _start_ab_test(self):
        """Start A/B testing candidate params against current."""
        print(f"[SELF-IMPROVE] Starting A/B test for {self.config.validation_minutes} minutes")
        self.is_ab_testing = True
        self.ab_test_start = datetime.now()
        self.ab_test_monitor = PerformanceMonitor()

    async def _check_ab_test_results(self):
        """Check if A/B test period is complete and decide winner."""
        if not self.ab_test_start:
            return

        elapsed = (datetime.now() - self.ab_test_start).total_seconds() / 60

        if elapsed < self.config.validation_minutes:
            return  # Still testing

        # Compare current vs candidate
        current_metrics = self.monitor.calculate_metrics()
        candidate_metrics = self.ab_test_monitor.calculate_metrics()

        print(f"[SELF-IMPROVE] A/B test complete:")
        print(f"  Current:  Sharpe={current_metrics.get('sharpe_ratio', 0):.2f}, WinRate={current_metrics.get('win_rate', 0):.1f}%")
        print(f"  Candidate: Sharpe={candidate_metrics.get('sharpe_ratio', 0):.2f}, WinRate={candidate_metrics.get('win_rate', 0):.1f}%")

        # Apply if candidate is better
        candidate_sharpe = candidate_metrics.get('sharpe_ratio', 0)
        current_sharpe = current_metrics.get('sharpe_ratio', 0)

        if candidate_sharpe > current_sharpe * 1.05:  # 5% better
            print(f"[SELF-IMPROVE] ✅ Applying new params: {self.candidate_params}")
            self.current_params = self.candidate_params
            # Reset monitor with new baseline
            self.monitor.reset()
        else:
            print(f"[SELF-IMPROVE] ❌ Rejecting new params, keeping current")

        self.is_ab_testing = False
        self.ab_test_start = None
        self.ab_test_monitor = None
        self.candidate_params = None

    def get_params_for_trading(self) -> Dict[str, Any]:
        """Get the params that should be used for current trading."""
        if self.is_ab_testing and self.candidate_params:
            return self.candidate_params
        return self.current_params

    def _get_default_params(self) -> Dict[str, Any]:
        """Get default params for strategy."""
        config_cls = StrategyRegistry.get_config_class(self.strategy_name)
        config = config_cls(name=self.strategy_name)
        return config.model_dump()

    def get_status(self) -> Dict[str, Any]:
        """Get current self-improvement status for dashboard."""
        metrics = self.monitor.calculate_metrics()
        return {
            "enabled": True,  # If this object exists, SI is enabled
            "is_ab_testing": self.is_ab_testing,
            "current_params": self.current_params,
            "candidate_params": self.candidate_params,
            "optimization_count_today": self.optimization_count_today,
            "total_trades": metrics.get("total_trades", 0),
            "win_rate": metrics.get("win_rate", 0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
            "max_drawdown": metrics.get("max_drawdown", 0),
            "consecutive_losses": metrics.get("consecutive_losses", 0),
            "should_optimize": self.monitor.should_optimize()[0],
            "last_assessment": self.monitor.last_assessment.isoformat() if self.monitor.last_assessment else None,
        }