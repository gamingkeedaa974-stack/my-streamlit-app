"""
Quick test to verify all modules import correctly.
Run this after fixing the files.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def test_imports():
    print("Testing imports...")
    
    try:
        from strategies.strategy import StrategyRegistry, ORBConfig, VWAPMomentumConfig, MeanReversionConfig
        print("  strategies.strategy: OK")
    except Exception as e:
        print(f"  strategies.strategy: FAILED - {e}")
        return False
    
    try:
        from risk_manager import RiskManager, RiskConfig
        print("  risk_manager: OK")
    except Exception as e:
        print(f"  risk_manager: FAILED - {e}")
        return False
    
    try:
        from audit_logger import AuditLogger, AuditEventType
        print("  audit_logger: OK")
    except Exception as e:
        print(f"  audit_logger: FAILED - {e}")
        return False
    
    try:
        from backtest_engine import BacktestEngine, DataGenerator, SyntheticOptionsChainProvider
        print("  backtest_engine: OK")
    except Exception as e:
        print(f"  backtest_engine: FAILED - {e}")
        return False
    
    try:
        from agents.auto_improvement_agent import AutoImprovementAgent
        print("  auto_improvement_agent: OK")
    except Exception as e:
        print(f"  auto_improvement_agent: FAILED - {e}")
        return False
    
    print("\nAll imports successful!")
    return True


def test_strategy_registry():
    print("\nTesting StrategyRegistry...")
    from strategies.strategy import StrategyRegistry
    
    strategies = StrategyRegistry.list_strategies()
    print(f"  Available strategies: {strategies}")
    
    for name in strategies:
        cls = StrategyRegistry.get(name)
        config_cls = StrategyRegistry.get_config_class(name)
        config = config_cls(name=name)
        strategy = cls(config)
        params = strategy.get_current_params()
        param_space = config.get_param_space()
        print(f"  {name}: params={len(params)}, param_space={len(param_space)} combinations")
    
    print("StrategyRegistry OK!")
    return True


def test_data_generator():
    print("\nTesting DataGenerator...")
    from backtest_engine import DataGenerator
    
    df = DataGenerator.generate_synthetic_data(days=5)
    print(f"  Generated {len(df)} bars over {df.index[-1].date() - df.index[0].date()} days")
    print(f"  Columns: {list(df.columns)}")
    print("DataGenerator OK!")
    return True


async def test_backtest():
    print("\nTesting BacktestEngine...")
    from strategies.strategy import StrategyRegistry, ORBConfig
    from risk_manager import RiskConfig
    from backtest_engine import BacktestEngine, DataGenerator
    
    df = DataGenerator.generate_synthetic_data(days=10)
    config = ORBConfig(name="orb")
    strategy = StrategyRegistry.get("orb")(config)
    risk_config = RiskConfig()
    
    engine = BacktestEngine(strategy, risk_config, df)
    result = await engine.run()
    
    print(f"  Total trades: {result.total_trades}")
    print(f"  Win rate: {result.win_rate:.1f}%")
    print(f"  Total P&L: {result.total_pnl_pct:.2f}%")
    print(f"  Sharpe: {result.sharpe_ratio:.3f}")
    print("BacktestEngine OK!")
    return True


async def test_optimization():
    print("\nTesting AutoImprovementAgent (quick run)...")
    from agents.auto_improvement_agent import AutoImprovementAgent
    from backtest_engine import DataGenerator
    from risk_manager import RiskConfig
    
    df = DataGenerator.generate_synthetic_data(days=15)
    risk_config = RiskConfig()
    agent = AutoImprovementAgent(
        strategy_name="orb",
        data=df,
        risk_config=risk_config,
        output_dir="data/backtest_results"
    )
    
    result = await agent.run_adaptive_search(iterations=5)
    
    if result:
        print(f"  Best score: {result.best_score:.4f}")
        print(f"  Baseline score: {result.baseline_score:.4f}")
        print(f"  Improvement: {result.improvement_pct:+.1f}%")
        print(f"  Best params: {result.best_params}")
        print("AutoImprovementAgent OK!")
    else:
        print("  No result (possibly no trades generated)")
    
    return True


async def main():
    print("="*60)
    print("NSE TRADING BOT - INTEGRATION TEST")
    print("="*60)
    
    if not test_imports():
        print("\nImport tests failed. Fix errors above.")
        return
    
    test_strategy_registry()
    test_data_generator()
    await test_backtest()
    await test_optimization()
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED!")
    print("="*60)
    print("\nYou can now run the full optimization:")
    print("  python -m backend.agents.auto_improvement_agent --strategy orb --mode adaptive --iterations 30")


if __name__ == "__main__":
    asyncio.run(main())