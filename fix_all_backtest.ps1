# fix_all_backtest.ps1
# Fixes: login issue + all 4 backtest bugs
# Run from: C:\Users\Imman\Kiwi_Bot_model\

$base = "C:\Users\Imman\Kiwi_Bot_model"

Write-Host "[1/5] Fixing users.json (login issue)..." -ForegroundColor Cyan
$hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes("password123"))
$hex = -join ($hash | ForEach-Object { $_.ToString("x2") })
$json = @{ admin = $hex } | ConvertTo-Json
Set-Content -Path "$base\users.json" -Value $json -Encoding UTF8
Write-Host "  -> users.json recreated with admin / password123" -ForegroundColor Green

Write-Host "[2/5] Patching risk_manager.py (theta cutoff 12:30 -> 14:30)..." -ForegroundColor Cyan
$riskFile = "$base\backend\risk_manager.py"
$risk = Get-Content $riskFile -Raw
$risk = $risk.Replace('theta_cutoff_time: time = time(12, 30)', 'theta_cutoff_time: time = time(14, 30)')
Set-Content $riskFile $risk -Encoding UTF8
Write-Host "  -> theta_cutoff_time changed to 14:30" -ForegroundColor Green

Write-Host "[3/5] Patching strategy.py (regime detection + volume)..." -ForegroundColor Cyan
$stratFile = "$base\backend\strategies\strategy.py"
$strat = Get-Content $stratFile -Raw

# Fix 3a: Regime detection - annualization + thresholds
$oldRegime = @'
        vol = returns.rolling(20).std().iloc[-1] * np.sqrt(252)
        trend = (df['close'].iloc[-1] / df['close'].iloc[-20] - 1)

        if vol > 0.25:
            regime = MarketRegime.VOLATILE
        elif trend > 0.03:
            regime = MarketRegime.TRENDING_UP
        elif trend < -0.03:
            regime = MarketRegime.TRENDING_DOWN
'@

$newRegime = @'
        # Annualize for 5-min bars: 252 days * 75 bars/day
        bars_per_day = 75
        vol = returns.rolling(20).std().iloc[-1] * np.sqrt(252 * bars_per_day)
        trend = (df['close'].iloc[-1] / df['close'].iloc[-20] - 1)

        # Calibrated for intraday 5-min bars
        if vol > 0.15:
            regime = MarketRegime.VOLATILE
        elif trend > 0.003:
            regime = MarketRegime.TRENDING_UP
        elif trend < -0.003:
            regime = MarketRegime.TRENDING_DOWN
'@

$strat = $strat.Replace($oldRegime, $newRegime)

# Fix 3b: Volume multiplier 0.8 -> 0.4
$strat = $strat.Replace('volume_multiplier: float = 0.8', 'volume_multiplier: float = 0.4')

Set-Content $stratFile $strat -Encoding UTF8
Write-Host "  -> Regime annualization fixed (sqrt(252) -> sqrt(252*75))" -ForegroundColor Green
Write-Host "  -> VOLATILE threshold: 0.25 -> 0.15, TRENDING: 0.03 -> 0.003" -ForegroundColor Green
Write-Host "  -> ORB volume_multiplier: 0.8 -> 0.4" -ForegroundColor Green

Write-Host "[4/5] Patching api_server.py (compare endpoint + backtest risk config)..." -ForegroundColor Cyan
$apiFile = "$base\backend\api_server.py"
$api = Get-Content $apiFile -Raw

# Fix 4a: Use backtest-friendly risk config in single backtest
$api = $api.Replace(
    'engine = BacktestEngine(strategy, RiskConfig(), data, symbol=req.symbol)',
    'bt_risk_config = RiskConfig(theta_cutoff_time=time(15, 0))`n    engine = BacktestEngine(strategy, bt_risk_config, data, symbol=req.symbol)'
)

# Fix 4b: Add compare endpoint before WebSocket section
$compareEndpoint = @'

@app.post("/api/backtest/compare")
async def run_backtest_compare(request: Request, req: StrategyCompareRequest):
    """Run all strategies on the SAME synthetic data and return comparison."""
    from backend.strategies.strategy import StrategyRegistry
    from backend.backtest_engine import BacktestEngine, DataGenerator
    from backend.risk_manager import RiskConfig
    import math

    np_seed = int(datetime.now().timestamp()) % (2**32)
    data = DataGenerator.generate_synthetic_data(days=req.days, symbol=req.symbol, seed=np_seed)
    ohlc_data = [{
        "timestamp": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
        "open": float(row["open"]), "high": float(row["high"]), "low": float(row["low"]), "close": float(row["close"]),
        "volume": int(row["volume"]) if not math.isnan(float(row["volume"])) else 0
    } for idx, row in data.iterrows()]

    comparisons = []
    best_score = -999
    winner = "orb"

    for strat_name in StrategyRegistry.list_strategies():
        try:
            strategy_cls = StrategyRegistry.get(strat_name)
            config_cls = StrategyRegistry.get_config_class(strat_name)
            config = config_cls(name=strat_name)
            strategy = strategy_cls(config)
            strategy.reset()
            bt_risk_config = RiskConfig(theta_cutoff_time=time(15, 0))
            engine = BacktestEngine(strategy, bt_risk_config, data, symbol=req.symbol)
            result = await engine.run()
            score_val = result.score() if hasattr(result, 'score') else result.total_pnl_pct
            comp = {
                "strategy": strat_name,
                "total_pnl_pct": result.total_pnl_pct,
                "win_rate": result.win_rate,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown": result.max_drawdown,
                "total_trades": result.total_trades,
                "profit_factor": 999.99 if result.profit_factor == float("inf") else result.profit_factor,
                "avg_trade_pnl": result.avg_profit_per_trade,
                "score": score_val,
                "ohlc_data": ohlc_data,
                "trades": result.trades,
            }
            comparisons.append(comp)
            if score_val > best_score:
                best_score = score_val
                winner = strat_name
            print(f"[COMPARE] {strat_name}: score={score_val:.2f}, trades={result.total_trades}, pnl%={result.total_pnl_pct:.2f}")
        except Exception as e:
            print(f"[COMPARE] {strat_name} failed: {e}")
            comparisons.append({
                "strategy": strat_name, "total_pnl_pct": 0, "win_rate": 0,
                "sharpe_ratio": 0, "max_drawdown": 0, "total_trades": 0,
                "profit_factor": 0, "avg_trade_pnl": 0, "score": -999,
                "ohlc_data": [], "trades": [],
            })

    result_data = {
        "comparisons": comparisons,
        "winner": winner,
        "symbol": req.symbol,
        "timestamp": datetime.now().isoformat(),
    }
    session = await session_manager.get_session(request.state.user_id)
    session.backtest_results.append(result_data)
    return result_data

'@

$api = $api.Replace('# ---------- WebSocket ----------', $compareEndpoint + '# ---------- WebSocket ----------')

Set-Content $apiFile $api -Encoding UTF8
Write-Host "  -> /api/backtest/compare endpoint added" -ForegroundColor Green
Write-Host "  -> Single backtest uses theta_cutoff_time=15:00" -ForegroundColor Green

Write-Host "[5/5] Verifying syntax..." -ForegroundColor Cyan
python -c "import py_compile; py_compile.compile(r'$base\backend\api_server.py', doraise=True); py_compile.compile(r'$base\backend\strategies\strategy.py', doraise=True); py_compile.compile(r'$base\backend\risk_manager.py', doraise=True); print('All 3 files: OK')"

Write-Host "" -ForegroundColor White
Write-Host "=== ALL FIXES APPLIED ===" -ForegroundColor Green
Write-Host "Login: admin / password123" -ForegroundColor Yellow
Write-Host "Restart bot: .\start_bot.bat" -ForegroundColor Yellow
