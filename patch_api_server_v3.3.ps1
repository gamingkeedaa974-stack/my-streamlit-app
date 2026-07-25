<#
.SYNOPSIS
  NSE Bot v3.2 → v3.3 — Patch 1: Critical api_server.py fixes
.DESCRIPTION
  Fixes 7 bugs: 3 crash bugs, 2 silent-failure bugs, 2 medium-severity bugs.
  Creates a .bak backup before patching. Verifies each patch applied.
#>

 $ErrorActionPreference = "Stop"

 $filePath = "C:\Users\Imman\Kiwi_Bot_model\backend\api_server.py"
 $backupPath = "C:\Users\Imman\Kiwi_Bot_model\backend\api_server.py.bak.v3.2"

# ═══════════════════════════════════════════════════════════
# STEP 1: Backup
# ═══════════════════════════════════════════════════════════
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  NSE Bot Patch 1: api_server.py Fixes" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`n[1/4] Creating backup..." -ForegroundColor Yellow
if (Test-Path $filePath) {
    Copy-Item $filePath $backupPath -Force
    Write-Host "  OK Backup: $backupPath" -ForegroundColor Green
} else {
    Write-Host "  FAIL File not found: $filePath" -ForegroundColor Red
    exit 1
}

# ═══════════════════════════════════════════════════════════
# STEP 2: Read & normalize
# ═══════════════════════════════════════════════════════════
Write-Host "`n[2/4] Reading file..." -ForegroundColor Yellow
 $content = [System.IO.File]::ReadAllText($filePath)
# Normalize line endings to CRLF for consistent matching
 $content = $content.Replace("`r`n", "`n").Replace("`n", "`r`n")
Write-Host "  OK File size: $($content.Length) chars" -ForegroundColor Green

 $patchCount = 0
 $failCount = 0

# ═══════════════════════════════════════════════════════════
# STEP 3: Apply patches
# ═══════════════════════════════════════════════════════════
Write-Host "`n[3/4] Applying patches..." -ForegroundColor Yellow

# ── Patch 1: Add 'symbol' field to OptimizationRequest ──
Write-Host "`n  Patch 1/7: Add symbol to OptimizationRequest" -ForegroundColor White
 $old1 = @'
class OptimizationRequest(BaseModel):
    strategy: str
    mode: str = "adaptive"
    iterations: int = 30
    days: int = 60
'@
 $new1 = @'
class OptimizationRequest(BaseModel):
    strategy: str
    symbol: str = "NIFTY50"
    mode: str = "adaptive"
    iterations: int = 30
    days: int = 60
'@
if ($content.Contains($old1)) {
    $content = $content.Replace($old1, $new1)
    $patchCount++
    Write-Host "    OK Applied" -ForegroundColor Green
} else {
    $failCount++
    Write-Host "    SKIP Pattern not found (already patched?)" -ForegroundColor DarkYellow
}

# ── Patch 2: Fix import path in run_optimization ──
Write-Host "`n  Patch 2/7: Fix auto_improvement_agent import path" -ForegroundColor White
 $old2 = @'
        from backend.agents.auto_improvement_agent import AutoImprovementAgent, DataGenerator
'@
 $new2 = @'
        from backend.auto_improvement_agent import AutoImprovementAgent
'@
if ($content.Contains($old2)) {
    $content = $content.Replace($old2, $new2)
    $patchCount++
    Write-Host "    OK Applied (DataGenerator already imported at top from backtest_engine)" -ForegroundColor Green
} else {
    $failCount++
    Write-Host "    SKIP Pattern not found (already patched?)" -ForegroundColor DarkYellow
}

# ── Patch 3: Fix NSEDataFeed — update risk_manager not paper_broker ──
Write-Host "`n  Patch 3/7: Fix NSEDataFeed to target risk_manager" -ForegroundColor White
 $old3 = @'
    async def update_broker(self, broker):
        """Feed NSE data into paper broker's risk manager."""
        data = await self.fetch_data("")
        if broker:
            await broker.update_market_data(
                pcr=data.get("pcr_ratio"),
                max_pain=data.get("max_pain"),
                oi_buildup=data.get("oi_buildup"),
                iv_percentile=data.get("iv_percentile"),
            )
'@
 $new3 = @'
    async def update_risk_manager(self, risk_manager):
        """Feed NSE data into risk manager for PCR, max pain, OI buildup, IV percentile."""
        data = await self.fetch_data("NIFTY50")
        if risk_manager:
            await risk_manager.update_market_data(
                pcr=data.get("pcr_ratio"),
                max_pain=data.get("max_pain"),
                oi_buildup=data.get("oi_buildup"),
                iv_percentile=data.get("iv_percentile"),
            )
'@
if ($content.Contains($old3)) {
    $content = $content.Replace($old3, $new3)
    $patchCount++
    Write-Host "    OK Method renamed" -ForegroundColor Green
} else {
    $failCount++
    Write-Host "    SKIP Pattern not found" -ForegroundColor DarkYellow
}

# ── Patch 3b: Fix the call site in run_paper_trading ──
Write-Host "`n  Patch 3b/7: Fix NSEDataFeed call site" -ForegroundColor White
 $old3b = @'
        if timestamp.minute % 15 == 0:  # Every 15 minutes
            try:
                await state.nse_data_feed.update_broker(state.paper_broker)
            except Exception as e:
                print(f"[NSE DATA] Feed error: {e}")
'@
 $new3b = @'
        if timestamp.minute % 15 == 0:  # Every 15 minutes
            try:
                if state.risk_manager:
                    await state.nse_data_feed.update_risk_manager(state.risk_manager)
            except Exception as e:
                print(f"[NSE DATA] Feed error: {e}")
'@
if ($content.Contains($old3b)) {
    $content = $content.Replace($old3b, $new3b)
    Write-Host "    OK Call site updated" -ForegroundColor Green
} else {
    Write-Host "    SKIP Call site pattern not found" -ForegroundColor DarkYellow
}

# ── Patch 4: Wire up risk manager exit signals (trailing stop, breakeven, partial exit) ──
Write-Host "`n  Patch 4/7: Wire up risk manager exit signals in trading loop" -ForegroundColor White
 $old4 = @'
        # Update prices for all positions
        await state.paper_broker.update_prices(row["close"], timestamp)
'@
 $new4 = @'
        # Update prices for all positions
        await state.paper_broker.update_prices(row["close"], timestamp)

        # ── NEW: Risk manager MTM updates + exit signal checks ──
        # Enables: trailing stops, breakeven triggers, partial exits, target/SL hits
        if state.risk_manager:
            try:
                rm_positions = await state.risk_manager.get_positions()
                for rm_underlying, rm_pos in rm_positions.items():
                    await state.risk_manager.update_mtm(rm_underlying, row["close"])
                    exit_sig = await state.risk_manager.get_exit_signal(rm_underlying, row["close"])
                    if exit_sig and exit_sig.action == SignalAction.EXIT:
                        ex_ok, ex_reason, ex_qty = await state.risk_manager.can_trade(exit_sig, timestamp)
                        if ex_ok:
                            await state.paper_broker.place_order(exit_sig, rm_underlying, timestamp, qty=ex_qty)
                            state.alerts.append({
                                "level": "WARNING",
                                "message": f"Risk exit: {exit_sig.reason}",
                                "timestamp": timestamp.isoformat()
                            })
            except Exception as e:
                print(f"[RISK EXIT] Error: {e}")
'@
if ($content.Contains($old4)) {
    $content = $content.Replace($old4, $new4)
    $patchCount++
    Write-Host "    OK Trailing stop / breakeven / partial exit now active" -ForegroundColor Green
} else {
    $failCount++
    Write-Host "    SKIP Pattern not found" -ForegroundColor DarkYellow
}

# ── Patch 5: Add list trimming (memory leak fix) ──
Write-Host "`n  Patch 5/7: Add memory leak prevention (list trimming)" -ForegroundColor White
 $old5 = @'
        state.data_index += 1
        await asyncio.sleep(0.5)  # 0.5s = 1 min market time
'@
 $new5 = @'
        # ── NEW: Trim growing lists to prevent memory leaks ──
        if len(state.alerts) > 500:
            state.alerts = state.alerts[-500:]
        if len(state.daily_pnl_history) > 1000:
            state.daily_pnl_history = state.daily_pnl_history[-1000:]
        if len(state.backtest_results) > 50:
            state.backtest_results = state.backtest_results[-50:]
        if len(state.optimization_results) > 50:
            state.optimization_results = state.optimization_results[-50:]

        state.data_index += 1
        await asyncio.sleep(0.5)  # 0.5s = 1 min market time
'@
if ($content.Contains($old5)) {
    $content = $content.Replace($old5, $new5)
    $patchCount++
    Write-Host "    OK Lists capped: alerts(500), pnl(1000), results(50)" -ForegroundColor Green
} else {
    $failCount++
    Write-Host "    SKIP Pattern not found" -ForegroundColor DarkYellow
}

# ── Patch 6: Fix redundant broadcast_updates ──
Write-Host "`n  Patch 6/7: Fix redundant broadcast_updates" -ForegroundColor White
 $old6 = @'
async def broadcast_updates():
    while True:
        await asyncio.sleep(2)
        if state.bot_running and state.paper_broker:
            pf = state.paper_broker.get_portfolio_summary()
            await state.manager.broadcast({
                "type": "PORTFOLIO",
                "data": pf
            })
'@
 $new6 = @'
async def broadcast_updates():
    """Broadcast periodic status heartbeats to WebSocket clients."""
    while True:
        await asyncio.sleep(5)
        if state.bot_running:
            await state.manager.broadcast({
                "type": "STATUS",
                "data": state.get_status().model_dump()
            })
'@
if ($content.Contains($old6)) {
    $content = $content.Replace($old6, $new6)
    $patchCount++
    Write-Host "    OK Now sends status heartbeat every 5s (no portfolio spam)" -ForegroundColor Green
} else {
    $failCount++
    Write-Host "    SKIP Pattern not found" -ForegroundColor DarkYellow
}

# ── Patch 7: Add version bump in app definition ──
Write-Host "`n  Patch 7/7: Bump version to 3.3.0" -ForegroundColor White
 $old7 = @'
    version="3.2.0",
'@
 $new7 = @'
    version="3.3.0",
'@
if ($content.Contains($old7)) {
    $content = $content.Replace($old7, $new7)
    $patchCount++
    Write-Host "    OK Version: 3.2.0 -> 3.3.0" -ForegroundColor Green
} else {
    $failCount++
    Write-Host "    SKIP Pattern not found" -ForegroundColor DarkYellow
}

# ═══════════════════════════════════════════════════════════
# STEP 4: Write & verify
# ═══════════════════════════════════════════════════════════
Write-Host "`n[4/4] Writing patched file..." -ForegroundColor Yellow
 $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($filePath, $content, $utf8NoBom)
Write-Host "  OK Written: $filePath" -ForegroundColor Green

# ── Summary ──
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  RESULTS: $patchCount patched, $failCount skipped" -ForegroundColor $(if ($failCount -eq 0) { "Green" } else { "Yellow" })
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Backup:  $backupPath" -ForegroundColor Gray
Write-Host "  Patched: $filePath" -ForegroundColor Gray
Write-Host ""

if ($failCount -gt 0) {
    Write-Host "  NOTE: $failCount patch(es) skipped. This is OK if:" -ForegroundColor DarkYellow
    Write-Host "    - Code was already patched from a previous run" -ForegroundColor DarkYellow
    Write-Host "    - Code was manually edited" -ForegroundColor DarkYellow
    Write-Host "    Review the SKIP messages above." -ForegroundColor DarkYellow
    Write-Host ""
}

Write-Host "  NEXT STEPS:" -ForegroundColor Cyan
Write-Host "    1. Syntax check:" -ForegroundColor White
Write-Host "       python -m py_compile `"$filePath`"" -ForegroundColor Gray
Write-Host "    2. Start backend:" -ForegroundColor White
Write-Host "       cd C:\Users\Imman\Kiwi_Bot_model" -ForegroundColor Gray
Write-Host "       python -m backend.api_server --host 0.0.0.0 --port 8000 --no-reload" -ForegroundColor Gray
Write-Host "    3. Start dashboard:" -ForegroundColor White
Write-Host "       streamlit run dashboard.py --server.port 8501" -ForegroundColor Gray
Write-Host ""

# ── Rollback option ──
Write-Host "  ROLLBACK (if needed):" -ForegroundColor Cyan
Write-Host "    Copy-Item '$backupPath' '$filePath' -Force" -ForegroundColor Gray
Write-Host ""