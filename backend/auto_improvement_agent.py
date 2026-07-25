"""
auto_improvement_agent.py
Autonomous agent that continuously backtests, evaluates, and improves strategies.
Runs locally with zero API cost. Uses grid search + adaptive optimization.

USAGE:
    python -m backend.auto_improvement_agent --strategy orb --mode adaptive --iterations 30
"""

from __future__ import annotations
import asyncio
import json
import argparse
import itertools
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
import pandas as pd
import numpy as np

from backend.strategies.strategy import (
    BaseStrategy, StrategyConfig, StrategyRegistry, 
    ORBConfig, VWAPMomentumConfig, MeanReversionConfig,
    BacktestResult
)
from backend.risk_manager import RiskConfig
from backend.backtest_engine import BacktestEngine, DataGenerator
from backend.audit_logger import AuditLogger

@dataclass
class OptimizationResult:
    strategy_name: str
    best_params: Dict[str, Any]
    best_score: float
    baseline_score: float
    improvement_pct: float
    train_results: BacktestResult
    test_results: BacktestResult
    all_results: List[Tuple[Dict, float]]
    generated_at: datetime = None
    
    def __post_init__(self):
        if self.generated_at is None:
            self.generated_at = datetime.now()


class AutoImprovementAgent:
    def __init__(self, 
                 strategy_name: str,
                 data: pd.DataFrame,
                 risk_config: RiskConfig = None,
                 output_dir: str = "data/backtest_results",
                 audit_dir: str = "data/audit_logs",
                 symbol: str = "NIFTY50"):
        self.strategy_name = strategy_name
        self.data = data
        self.symbol = symbol
        self.risk_config = risk_config or RiskConfig()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLogger(Path(audit_dir))
        self.audit.start_session()
        
        self.strategy_cls = StrategyRegistry.get(strategy_name)
        self.config_cls = StrategyRegistry.get_config_class(strategy_name)
        
    async def run_grid_search(self, 
                             param_grid: Optional[Dict[str, List]] = None,
                             max_combinations: int = 50,
                             train_size: float = 0.7) -> OptimizationResult:
        if param_grid is None:
            default_config = self.config_cls(name=self.strategy_name)
            param_grid = default_config.get_param_space()
        
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        all_combinations = list(itertools.product(*values))
        
        if len(all_combinations) > max_combinations:
            print(f"Warning: {len(all_combinations)} combinations, sampling {max_combinations}")
            np.random.shuffle(all_combinations)
            all_combinations = all_combinations[:max_combinations]
        
        print(f"Testing {len(all_combinations)} parameter combinations...")
        
        split_idx = int(len(self.data) * train_size)
        train_data = self.data.iloc[:split_idx]
        test_data = self.data.iloc[split_idx:]
        
        baseline_config = self.config_cls(name=self.strategy_name)
        baseline_strategy = self.strategy_cls(baseline_config)
        # ── NEW: Reset strategy before backtest ──
        baseline_strategy.reset()
        baseline_engine = BacktestEngine(baseline_strategy, self.risk_config, train_data, symbol=self.symbol)
        baseline_result = await baseline_engine.run()
        baseline_score = baseline_result.score()
        print(f"Baseline score: {baseline_score:.4f} (PnL: {baseline_result.total_pnl_pct:.2f}%)")
        
        results = []
        best_score = -float('inf')
        best_params = None
        best_train_result = None
        
        for i, combo in enumerate(all_combinations):
            params = dict(zip(keys, combo))
            
            try:
                config = self.config_cls(name=self.strategy_name, **params)
                strategy = self.strategy_cls(config)
                # ── NEW: Reset strategy before each backtest ──
                strategy.reset()
                engine = BacktestEngine(strategy, self.risk_config, train_data, symbol=self.symbol)
                result = await engine.run()
                score = result.score()
                
                results.append((params, score))
                
                if score > best_score:
                    best_score = score
                    best_params = params
                    best_train_result = result
                    
                if (i + 1) % 10 == 0:
                    print(f"  Tested {i+1}/{len(all_combinations)}... Best score so far: {best_score:.4f}")
                    
            except Exception as e:
                print(f"  Error with params {params}: {e}")
                results.append((params, -999))
        
        if best_params:
            test_config = self.config_cls(name=self.strategy_name, **best_params)
            test_strategy = self.strategy_cls(test_config)
            # ── NEW: Reset strategy before test backtest ──
            test_strategy.reset()
            test_engine = BacktestEngine(test_strategy, self.risk_config, test_data, symbol=self.symbol)
            test_result = await test_engine.run()
            
            improvement = ((best_score - baseline_score) / abs(baseline_score) * 100) if baseline_score != 0 else 0
            
            opt_result = OptimizationResult(
                strategy_name=self.strategy_name,
                best_params=best_params,
                best_score=best_score,
                baseline_score=baseline_score,
                improvement_pct=improvement,
                train_results=best_train_result,
                test_results=test_result,
                all_results=results,
            )
            
            self.audit.log_optimization(
                strategy=self.strategy_name,
                old_params=baseline_config.model_dump(),
                new_params=best_params,
                improvement=improvement
            )
            
            self._save_results(opt_result)
            return opt_result
        
        return None
    
    async def run_adaptive_search(self,
                                  iterations: int = 30,
                                  top_k: int = 5) -> OptimizationResult:
        default_config = self.config_cls(name=self.strategy_name)
        param_space = default_config.get_param_space()
        
        phase1_iters = int(iterations * 0.6)
        print(f"Phase 1: Broad search ({phase1_iters} iterations)")
        
        phase1_results = []
        for i in range(phase1_iters):
            params = {k: np.random.choice(v) for k, v in param_space.items()}
            score = await self._test_params(params)
            phase1_results.append((params, score))
            print(f"  Iter {i+1}/{phase1_iters}: Score={score:.4f}")
        
        phase2_iters = iterations - phase1_iters
        print(f"\nPhase 2: Focused search ({phase2_iters} iterations)")
        
        phase1_results.sort(key=lambda x: x[1], reverse=True)
        top_performers = phase1_results[:top_k]
        
        phase2_results = []
        for i in range(phase2_iters):
            base_params = dict(top_performers[i % top_k][0])
            param_to_mutate = np.random.choice(list(base_params.keys()))
            possible_values = param_space[param_to_mutate]
            base_params[param_to_mutate] = np.random.choice(possible_values)
            
            score = await self._test_params(base_params)
            phase2_results.append((base_params, score))
            print(f"  Iter {phase1_iters + i + 1}/{iterations}: Score={score:.4f}")
        
        all_results = phase1_results + phase2_results
        all_results.sort(key=lambda x: x[1], reverse=True)
        
        best_params = all_results[0][0]
        best_score = all_results[0][1]
        
        split_idx = int(len(self.data) * 0.7)
        train_data = self.data.iloc[:split_idx]
        test_data = self.data.iloc[split_idx:]
        
        baseline_config = self.config_cls(name=self.strategy_name)
        baseline_strategy = self.strategy_cls(baseline_config)
        # ── NEW: Reset strategy before baseline backtest ──
        baseline_strategy.reset()
        baseline_engine = BacktestEngine(baseline_strategy, self.risk_config, train_data, symbol=self.symbol)
        baseline_result = await baseline_engine.run()
        
        test_config = self.config_cls(name=self.strategy_name, **best_params)
        test_strategy = self.strategy_cls(test_config)
        # ── NEW: Reset strategy before test backtest ──
        test_strategy.reset()
        test_engine = BacktestEngine(test_strategy, self.risk_config, test_data, symbol=self.symbol)
        test_result = await test_engine.run()
        
        improvement = ((best_score - baseline_result.score()) / abs(baseline_result.score()) * 100) if baseline_result.score() != 0 else 0
        
        opt_result = OptimizationResult(
            strategy_name=self.strategy_name,
            best_params=best_params,
            best_score=best_score,
            baseline_score=baseline_result.score(),
            improvement_pct=improvement,
            train_results=baseline_result,
            test_results=test_result,
            all_results=all_results,
        )
        
        self._save_results(opt_result)
        return opt_result
    
    async def _test_params(self, params: Dict) -> float:
        try:
            config = self.config_cls(name=self.strategy_name, **params)
            strategy = self.strategy_cls(config)
            # ── NEW: Reset strategy before test ──
            strategy.reset()
            
            split_idx = int(len(self.data) * 0.7)
            train_data = self.data.iloc[:split_idx]
            
            engine = BacktestEngine(strategy, self.risk_config, train_data, symbol=self.symbol)
            result = await engine.run()
            return result.score()
        except Exception as e:
            print(f"Error testing params {params}: {e}")
            return -999
    
    def _save_results(self, result: OptimizationResult) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.output_dir / f"optimization_{self.strategy_name}_{timestamp}.json"
        
        output = {
            "strategy": result.strategy_name,
            "generated_at": result.generated_at.isoformat(),
            "best_params": result.best_params,
            "best_score": result.best_score,
            "baseline_score": result.baseline_score,
            "improvement_pct": result.improvement_pct,
            "train_results": {
                "total_pnl_pct": result.train_results.total_pnl_pct,
                "win_rate": result.train_results.win_rate,
                "max_drawdown": result.train_results.max_drawdown,
                "sharpe_ratio": result.train_results.sharpe_ratio,
                "profit_factor": result.train_results.profit_factor,
                "total_trades": result.train_results.total_trades,
            },
            "test_results": {
                "total_pnl_pct": result.test_results.total_pnl_pct,
                "win_rate": result.test_results.win_rate,
                "max_drawdown": result.test_results.max_drawdown,
                "sharpe_ratio": result.test_results.sharpe_ratio,
                "profit_factor": result.test_results.profit_factor,
                "total_trades": result.test_results.total_trades,
            },
            "all_combinations_tested": len(result.all_results),
        }
        
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        
        print(f"\nResults saved to: {filename}")
    
    def generate_report(self, result: OptimizationResult) -> str:
        report = f"""
{'='*60}
STRATEGY OPTIMIZATION REPORT
{'='*60}
Strategy: {result.strategy_name}
Generated: {result.generated_at.strftime('%Y-%m-%d %H:%M:%S')}

BASELINE (Default Parameters)
  Score:        {result.baseline_score:.4f}
  P&L:          {result.train_results.total_pnl_pct:.2f}%
  Win Rate:     {result.train_results.win_rate:.1f}%
  Max Drawdown: {result.train_results.max_drawdown:.2f}%
  Sharpe:       {result.train_results.sharpe_ratio:.3f}
  Trades:       {result.train_results.total_trades}

OPTIMIZED PARAMETERS
"""
        for param, value in result.best_params.items():
            report += f"  {param:20s}: {value}\n"
        
        report += f"""
OPTIMIZED RESULTS (Training)
  Score:        {result.best_score:.4f} ({result.improvement_pct:+.1f}% vs baseline)
  P&L:          {result.train_results.total_pnl_pct:.2f}%
  Win Rate:     {result.train_results.win_rate:.1f}%
  Max Drawdown: {result.train_results.max_drawdown:.2f}%
  Sharpe:       {result.train_results.sharpe_ratio:.3f}
  Trades:       {result.train_results.total_trades}

VALIDATION RESULTS (Test Set - Unseen Data)
  P&L:          {result.test_results.total_pnl_pct:.2f}%
  Win Rate:     {result.test_results.win_rate:.1f}%
  Max Drawdown: {result.test_results.max_drawdown:.2f}%
  Sharpe:       {result.test_results.sharpe_ratio:.3f}
  Trades:       {result.test_results.total_trades}

RECOMMENDATION: {"APPLY" if result.improvement_pct > 10 and result.test_results.total_pnl_pct > 0 else "REJECT"}
{'='*60}
"""
        return report


def main():
    parser = argparse.ArgumentParser(description='Auto-Improvement Agent for NSE Options Strategies')
    parser.add_argument('--strategy', type=str, default='orb', 
                        choices=StrategyRegistry.list_strategies(),
                        help='Strategy to optimize')
    parser.add_argument('--symbol', type=str, default='NIFTY50',
                        choices=['NIFTY50', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'],
                        help='Symbol for synthetic data generation')
    parser.add_argument('--data', type=str, default=None,
                        help='Path to historical CSV data (if None, uses synthetic data)')
    parser.add_argument('--mode', type=str, default='adaptive',
                        choices=['grid', 'adaptive'],
                        help='Optimization mode')
    parser.add_argument('--iterations', type=int, default=30,
                        help='Number of iterations (for adaptive mode)')
    parser.add_argument('--max-combinations', type=int, default=50,
                        help='Max combinations for grid search')
    parser.add_argument('--capital', type=float, default=1_000_000,
                        help='Starting capital')
    parser.add_argument('--output-dir', type=str, default='data/backtest_results',
                        help='Directory to save results')
    parser.add_argument('--synthetic-days', type=int, default=60,
                        help='Days of synthetic data to generate if no CSV provided')
    
    args = parser.parse_args()
    
    if args.data and Path(args.data).exists():
        print(f"Loading data from: {args.data}")
        data = DataGenerator.load_csv_data(args.data)
    else:
        # ── FIXED: Symbol-specific synthetic data ──
        print(f"Generating {args.synthetic_days} days of synthetic data for {args.symbol}...")
        data = DataGenerator.generate_synthetic_data(
            days=args.synthetic_days,
            symbol=args.symbol,
            seed=None
        )
    
    print(f"Data shape: {data.shape}")
    print(f"Date range: {data.index[0]} to {data.index[-1]}")
    
    risk_config = RiskConfig(capital=args.capital)
    agent = AutoImprovementAgent(
        strategy_name=args.strategy,
        data=data,
        risk_config=risk_config,
        output_dir=args.output_dir,
        symbol=args.symbol
    )
    
    print(f"\n{'='*60}")
    print(f"Starting {args.mode} optimization for '{args.strategy}' on {args.symbol}")
    print(f"{'='*60}\n")
    
    if args.mode == 'grid':
        result = asyncio.run(agent.run_grid_search(max_combinations=args.max_combinations))
    else:
        result = asyncio.run(agent.run_adaptive_search(iterations=args.iterations))
    
    if result:
        print(agent.generate_report(result))
        
        print("\n" + "="*60)
        print("BEST PARAMETERS (Copy into your strategy config):")
        print("="*60)
        for param, value in result.best_params.items():
            print(f"  {param} = {value}")
        print("="*60)
    else:
        print("Optimization failed. Check logs for details.")


if __name__ == "__main__":
    main()