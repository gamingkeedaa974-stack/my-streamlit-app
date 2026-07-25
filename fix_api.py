import py_compile, traceback, re
path = r"C:\Users\Imman\Kiwi_Bot_model\backend\api_server.py"
# 1. Check if api_server.py has syntax errors
print("=== Syntax check on api_server.py ===")
try:
    py_compile.compile(path, doraise=True)
    print("  Syntax: OK")
except py_compile.PyCompileError as e:
    print(f"  Syntax ERROR: {e}")
    print("\nAttempting auto-fix...")
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
# 2. Check if the /api/dashboard endpoint exists
if '"/api/dashboard"' in content:
    print("\n=== /api/dashboard endpoint: FOUND ===")
    # Check for the bad walrus operator line
    if "st_session_si :=" in content or "_si_enabled" in content.split("get_dashboard")[1].split("WebSocket")[0] if "get_dashboard" in content else "":
        print("  WARNING: Bad self_improvement expression found, fixing...")
        # Find and show the problematic section
        dash_start = content.find("async def get_dashboard")
        dash_end = content.find("WebSocket", dash_start)
        dash_section = content[dash_start:dash_end]
        print(f"  Section length: {len(dash_section)} chars")
else:
    print("\n=== /api/dashboard endpoint: MISSING (will add) ===")
# 3. Replace the ENTIRE /api/dashboard endpoint with a clean version
# Find the dashboard endpoint block
dash_start = content.find("@app.get(\"/api/dashboard\")")
if dash_start >= 0:
    # Find the end - next @app or # ---- section
    dash_end_search = content[dash_start:]
    next_endpoint = re.search(r'\n(@app\.|# ----)', dash_end_search[10:])
    if next_endpoint:
        dash_end = dash_start + 10 + next_endpoint.start()
        old_block = content[dash_start:dash_end]
        print(f"  Removing old dashboard endpoint ({len(old_block)} chars)")
    else:
        dash_end = dash_start + 1000
        old_block = content[dash_start:dash_end]
    # Clean replacement - no walrus, no complex ternary
    clean_endpoint = '''@app.get("/api/dashboard")
async def get_dashboard(request: Request):
    session = await session_manager.get_session(request.state.user_id)
    si = getattr(session, "self_improvement", None)
    if si is None:
        si = {"enabled": False, "is_ab_testing": False, "current_params": {},
              "candidate_params": None, "optimization_count_today": 0,
              "total_trades": 0, "win_rate": 0.0, "sharpe_ratio": 0.0,
              "max_drawdown": 0.0, "should_optimize": False}
    return {
        "status": {
            "running": session.bot_running,
            "mode": "PAPER",
            "strategy": session.current_strategy or "none",
            "connected_to_broker": False,
            "market_regime": getattr(session.strategy_instance, "_current_regime", None).value if session.strategy_instance else None
        },
        "portfolio": session.paper_broker.get_portfolio_summary(),
        "positions": session.paper_broker.get_positions(),
        "alerts": session.alerts[-50:],
        "backtest_results": session.backtest_results[-50:],
        "optimization_results": session.optimization_results[-50:],
        "self_improvement": si,
    }
'''
    content = content[:dash_start] + clean_endpoint + content[dash_end:]
    print("  Replaced with clean version")
else:
    print("  No dashboard endpoint found to replace")
# 4. Verify syntax again
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("\n=== Final syntax check ===")
try:
    py_compile.compile(path, doraise=True)
    print("  Syntax: OK - backend should start cleanly")
except py_compile.PyCompileError as e:
    print(f"  Syntax STILL BROKEN: {e}")
# 5. Also check dashboard.py syntax
dash_path = r"C:\Users\Imman\Kiwi_Bot_model\dashboard.py"
print("\n=== Syntax check on dashboard.py ===")
try:
    py_compile.compile(dash_path, doraise=True)
    print("  Syntax: OK")
except py_compile.PyCompileError as e:
    print(f"  Syntax ERROR: {e}")
