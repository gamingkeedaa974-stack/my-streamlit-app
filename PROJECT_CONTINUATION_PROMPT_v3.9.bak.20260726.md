@
🚀 NSE Options Trading Bot — Project Continuation Prompt (v3.9 Backup)
Status: Backup created on 2026-07-26
Location: C:\Users\Imman\Kiwi_Bot_model\ | Python 3.14 (in venv)

🤖 CRITICAL INSTRUCTION FOR THE AI
At the end of EVERY response, generate an updated PROJECT_CONTINUATION_PROMPT_vX.X.md file.
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
- Backend: FastAPI (`backend/api_server.py`) on localhost:8000
- Frontend: Streamlit (`dashboard.py`) on localhost:8501
- Launcher: `start_bot.bat`
- Data folders: `data/`, `data/audit_logs/`, `data/backtest_results/`

🔧 Current Work
- `dashboard.py` was recently updated with a form-based settings tab and saved settings summary.
- `backend/api_server.py` exposes JWT-protected endpoints and Fyers stub endpoints.
- Active issue: the local Python environment currently reports `ModuleNotFoundError: No module named 'fastapi'`.
- Need a clean dependency install and a backend startup validation.

✅ What is Working
- `dashboard.py` syntax was validated after the latest UI changes.
- Project includes per-user session manager logic and a structured backend layout.
- Backup of the previous prompt file has been created.

🔥 Next Actions
1. Install or fix missing dependencies: `fastapi`, `uvicorn`, `pydantic`, `requests`.
2. Run `python -m py_compile backend/api_server.py dashboard.py`.
3. Verify login and token auth through the Streamlit dashboard.
4. Add persistent storage for saved settings outside Streamlit session state.
5. Keep prompt updates and backups current at every meaningful change.

🛠️ Run / Recovery Commands
- `python -m py_compile backend/api_server.py dashboard.py`
- `python -m pip install -r requirements.txt`
- `.\start_bot.bat`
