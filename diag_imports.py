import sys, traceback
sys.path.insert(0, r"C:\Users\Imman\Kiwi_Bot_model")
print("=== Attempting to import api_server ===")
try:
    from backend.api_server import app
    print("  Import: OK")
except Exception as e:
    print(f"  Import FAILED:\n{traceback.format_exc()}")
    exit(1)
print("\n=== Checking all backend imports ===")
modules = [
    "backend.auth_manager",
    "backend.user_session_manager",
    "backend.paper_broker",
    "backend.risk_manager",
    "backend.audit_logger",
    "backend.backtest_engine",
    "backend.performance_monitor",
    "backend.self_improvement_loop",
    "backend.strategies.strategy",
]
for mod in modules:
    try:
        __import__(mod)
        print(f"  {mod}: OK")
    except Exception as e:
        print(f"  {mod}: FAILED - {type(e).__name__}: {e}")
print("\n=== Testing backend startup directly ===")
try:
    import uvicorn
    import asyncio
    async def test():
        config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
        server = uvicorn.Server(config)
        # Just test if it can start, then stop
        async def run_and_stop():
            await asyncio.wait_for(server.serve(), timeout=3.0)
        try:
            await run_and_stop()
        except asyncio.TimeoutError:
            print("  Server started OK (stopped after 3s test)")
    asyncio.run(test())
except KeyboardInterrupt:
    pass
except Exception as e:
    print(f"  Startup FAILED:\n{traceback.format_exc()}")
