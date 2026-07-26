@
🚀 NSE Options Trading Bot — Project Continuation Prompt (v3.9)
Status: Active Development | Date: 2025-07-26
Location: C:\Users\Imman\Kiwi_Bot_model\ | Python 3.14 (in venv)

🤖 CRITICAL INSTRUCTION FOR THE AI
At the end of EVERY response, generate an updated PROJECT_CONTINUATION_PROMPT_vX.X.md.
Bump version on major updates.

⚠️ STRICT PATCHING RULE (MUST FOLLOW)
NEVER use content.replace() or regex replacements that match large blocks of code.
These aggressively eat adjacent functions and cause cascading NameErrors.
ONLY use the SAFE REPAIR approach:
1. First RUN a diagnostic that checks which functions exist (regex: ^def funcname\()
2. Only INSERT missing functions — NEVER delete/replace existing code
3. Write fix scripts to .py files using PowerShell @'...'@ heredoc, then execute
4. Always run py_compile.check() on both api_server.py and dashboard.py after any edit
5. NEVER use Python triple-quotes (""") inside PowerShell $pyScript = @'...'@ blocks
   — Use @'...'@ | Out-File to write a .py file, then python execute it

📋 Current Architecture
Backend: FastAPI (backend/api_server.py) on localhost:8000
Frontend: Streamlit (dashboard.py) on localhost:8501 with streamlit-autorefresh (5s)
Launcher: start_bot.bat (double-click)

🔐 Authentication (Working v3.9)
- backend/auth_manager.py: AuthManager class, SHA-256 + PyJWT (HS256)
- users.json: MUST contain hashed passwords (NOT plaintext!)
  Fix: python -c "import json,hashlib;f=open(r'C:\Users\Imman\Kiwi_Bot_model\users.json','w');json.dump({'admin':hashlib.sha256(b'password123').hexdigest()},f,indent=4);f.close()"
- Default: admin / password123
- auth_manager = AuthManager() instantiated at module level in api_server.py
- JWT middleware on all endpoints except /api/login, /, /docs, /openapi.json
- dashboard.py: _auth_headers() adds Bearer token to ALL _safe_get/_safe_post calls

⚡ Performance (Working v3.7)
- Single /api/dashboard batched endpoint (1 HTTP call instead of 7)
- get_data() called ONCE in main(), passed to render_sidebar(data) and render_status_bar(data)
- streamlit-autorefresh at 5s interval
- render_sidebar(data) and render_status_bar(data) accept data parameter

📁 File Structure
start_bot.bat | dashboard.py | users.json | backend/
  api_server.py (FastAPI, multi-user, /api/dashboard batched endpoint, /api/backtest/compare)
  auth_manager.py (SHA-256 + PyJWT)
  user_session_manager.py (per-user session isolation)
  paper_broker.py | risk_manager.py | strategy.py
  backtest_engine.py (synthetic data, NO API key needed)
  performance_monitor.py | self_improvement_loop.py | audit_logger.py
  strategies/
    strategy.py (ORB, VWAP Momentum, Mean Reversion, StrategyRegistry)

🔧 v3.9 Changelog (Intraday Backtest Fix)
- [FIXED] Added missing POST /api/backtest/compare endpoint (was 404)
- [FIXED] Regime detection: annualization sqrt(252) -> sqrt(252*75) for 5-min bars
- [FIXED] Regime thresholds: VOLATILE 0.25->0.15, TRENDING 0.03->0.003 (calibrated for intraday)
- [FIXED] RiskConfig theta_cutoff_time: 12:30 -> 14:30 (was blocking entries after noon)
- [FIXED] ORBConfig volume_multiplier: 0.8 -> 0.4 (was blocking mid-day entries)
- [FIXED] auth_manager = AuthManager() instance restored in api_server.py
- [FIXED] _auth_headers() added to dashboard.py _safe_get/_safe_post (was missing JWT)
- [NOTE] Backtest endpoints use theta_cutoff_time=15:00 override for full-day coverage

🛠️ Known Issues / Next Steps
- Fyers API Integration: backend/fyers_broker.py (mock), UI in Settings tab
- WebSocket Auth: /ws endpoint needs JWT via query param
- Mobile Responsiveness: Login works, tabs need testing
- Settings Save: Save button only shows toast, doesn't persist
- Optimize tab: /api/optimize endpoint may need similar regime/risk fixes

🚀 How to Run
1. cd C:\Users\Imman\Kiwi_Bot_model
2. Double-click start_bot.bat
3. Login: admin / password123 at localhost:8501

🛡️ Quick Recovery Commands
- Fix users.json: python -c "import json,hashlib;f=open(r'...\users.json','w');json.dump({'admin':hashlib.sha256(b'password123').hexdigest()},f,indent=4);f.close()"
- Syntax check: python -c "import py_compile; py_compile.compile(r'...\api_server.py', doraise=True); py_compile.compile(r'...\dashboard.py', doraise=True); print('OK')"
- Function check: Run fix_all.py pattern (checks ^def funcname\() before inserting)
- Restore auth_manager: python -c "f=open(r'...\backend\api_server.py','r',enc='utf-8');c=f.read();f.close();c=c.replace('from backend.auth_manager import AuthManager','from backend.auth_manager import AuthManager\nauth_manager = AuthManager()') if 'auth_manager = AuthManager()' not in c else c;f=open(r'...\backend\api_server.py','w',enc='utf-8');f.write(c);f.close()"
- Restore auth headers: Check dashboard.py has _auth_headers() function and it's used in _safe_get/_safe_post
