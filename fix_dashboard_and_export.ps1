<#
.SYNOPSIS
  Force-fixes dashboard.py missing patches and generates context file for new chat.
#>
 $ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Dashboard Force-Fix & Context Export" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

 $pyScript = @'
import sys
import os

dash_path = r"C:\Users\Imman\Kiwi_Bot_model\dashboard.py"
ctx_path = r"C:\Users\Imman\Kiwi_Bot_model\PROJECT_CONTINUATION_PROMPT_v3.4.md"

# ==========================================
# 1. FIX DASHBOARD.PY
# ==========================================
print("Reading dashboard.py...")
with open(dash_path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix 1: API Helpers (JWT injection)
old_helpers = """# ---------- API Helpers ----------
def _safe_get(endpoint: str, timeout: float = 3.0) -> Optional[Any]:
    try:
        resp = requests.get(f"{API_URL}{endpoint}", timeout=timeout)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None

def _safe_post(endpoint: str, payload: dict, timeout: float = 10.0) -> Optional[Any]:
    try:
        resp = requests.post(f"{API_URL}{endpoint}", json=payload, timeout=timeout)
        return resp.json() if resp.status_code in (200, 201) else None
    except Exception:
        return None"""

new_helpers = """# ---------- API Helpers ----------
def _get_headers():
    \"\"\"Returns auth headers if logged in.\"\"\"
    token = st.session_state.get("jwt_token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}

def _safe_get(endpoint: str, timeout: float = 3.0) -> Optional[Any]:
    try:
        resp = requests.get(f"{API_URL}{endpoint}", timeout=timeout, headers=_get_headers())
        if resp.status_code == 401:
            st.session_state.authenticated = False
            st.session_state.jwt_token = None
            st.rerun()
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None

def _safe_post(endpoint: str, payload: dict, timeout: float = 10.0) -> Optional[Any]:
    try:
        resp = requests.post(f"{API_URL}{endpoint}", json=payload, timeout=timeout, headers=_get_headers())
        if resp.status_code == 401:
            st.session_state.authenticated = False
            st.session_state.jwt_token = None
            st.rerun()
        return resp.json() if resp.status_code in (200, 201) else None
    except Exception:
        return None"""

if old_helpers in content:
    content = content.replace(old_helpers, new_helpers)
    print("OK: API Helpers updated with JWT.")
else:
    print("SKIP: API Helpers pattern not found (might already be patched).")

# Fix 2: Main Execution Gate
# We look for the sidebar definition and inject the auth gate right before it
old_main = """# ═══════════════════════════════════════════════════════════
# SIDEBAR — COMMAND CENTER
# ═══════════════════════════════════════════════════════════
def render_sidebar():"""

new_main = """# ---------- Main Execution ----------
init_session_state()

if not st.session_state.authenticated:
    render_login_screen()
    st.stop()

# ═══════════════════════════════════════════════════════════
# SIDEBAR — COMMAND CENTER
# ═══════════════════════════════════════════════════════════
def render_sidebar():"""

if old_main in content:
    content = content.replace(old_main, new_main)
    print("OK: Login gate injected.")
else:
    print("SKIP: Main execution pattern not found.")

# Fix 3: Ensure init_session_state is called at the bottom of the file
# Streamlit runs top to bottom. We need to ensure the main execution block is hit.
# Find the very bottom of the file and append if missing
if "if not st.session_state.authenticated:" not in content:
    content += "\n# ---------- Main Execution ----------\ninit_session_state()\nif not st.session_state.authenticated:\n    render_login_screen()\n    st.stop()\nelse:\n    render_sidebar()\n    # Render tabs\n"
    print("OK: Appended execution block to end of file.")
else:
    print("OK: Execution block already exists.")

with open(dash_path, "w", encoding="utf-8") as f:
    f.write(content)
print("dashboard.py saved successfully.\n")

# ==========================================
# 2. GENERATE CONTEXT FILE
# ==========================================
print("Generating PROJECT_CONTINUATION_PROMPT_v3.4.md...")
context = """# 🚀 NSE Options Trading Bot — Project Continuation Prompt (v3.4)

**Status:** Active Development
**Date:** 2024-05-24
**Location:** `C:\\Users\\Imman\\Kiwi_Bot_model\\`
**Python Version:** 3.14 (in venv)

## 📋 Current Architecture
- **Backend:** FastAPI (`backend/api_server.py`) on `localhost:8000`
- **Frontend:** Streamlit (`dashboard.py`) on `localhost:8501`
- **Launcher:** `start_bot.bat` runs both in background and opens browser.

## 🔐 Authentication (NEW in v3.4)
- Added JWT-based multi-user authentication.
- `backend/auth_manager.py`: Handles SHA-256 password hashing, JWT creation/verification. Default user: `admin` / `password123`.
- `backend/user_session_manager.py`: `UserSession` class created for each logged-in user to isolate `PaperBroker`, `RiskManager`, etc. (Not fully wired into endpoints yet).
- `api_server.py` has JWT HTTP Middleware. All endpoints require `Authorization: Bearer <token>` header.
- `dashboard.py` has a `render_login_screen()` gate. If unauthenticated, shows login form. Stores JWT in `st.session_state`.

## 🛠️ Known Issues / Next Steps for New Chat
1. **Wire User Sessions:** `api_server.py` currently uses a global `state = TradingServerState()`. It needs to be refactored to use `session_manager.get_session(request.state.user_id)` so each user gets their own isolated trading environment.
2. **Fyers API Integration:** User plans to use Fyers API. Need to create `backend/fyers_broker.py` (mock for now). Add a UI input in the Settings tab to input the Fyers App ID/Secret/Token.
3. **UI Refinement:** The dashboard needs UI cleanup, specifically mobile responsiveness and ensuring all tabs render correctly.
4. **Memory/Bugs:** `state.alerts` and `state.daily_pnl_history` grow unbounded (capped to 500/1000 in v3.3 patch, but needs monitoring).

## 📁 File Structure
- `start_bot.bat` (Root launcher)
- `dashboard.py` (Streamlit UI)
- `backend/`
  - `api_server.py` (FastAPI backend, secured with JWT)
  - `auth_manager.py` (Auth logic)
  - `user_session_manager.py` (Per-user state isolation)
  - `paper_broker.py`, `risk_manager.py`, `strategy.py`, etc.

## 🚀 How to Run
1. Open PowerShell, navigate to `C:\\Users\\Imman\\Kiwi_Bot_model`.
2. Activate venv: `.\venv\Scripts\activate`.
3. Run: `.\start_bot.bat`.
4. Go to `http://localhost:8501` and login with `admin` / `password123`.
"""

with open(ctx_path, "w", encoding="utf-8") as f:
    f.write(context)
print(f"OK: Context file saved to {ctx_path}")
'@

# Execute the python script
 $pyScript | python

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  Fix & Export Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "`nNext Steps:" -ForegroundColor Yellow
Write-Host "  1. Double-click 'start_bot.bat' to launch the app." -ForegroundColor White
Write-Host "  2. If you hit context limits, start a new chat and paste the contents of:" -ForegroundColor White
Write-Host "     C:\Users\Imman\Kiwi_Bot_model\PROJECT_CONTINUATION_PROMPT_v3.4.md" -ForegroundColor Cyan
Write-Host ""