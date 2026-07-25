# ?? NSE Options Trading Bot ? Project Continuation Prompt (v3.4)
**Status:** Active Development
**Date:** 2024-05-24
**Location:** `C:\Users\Imman\Kiwi_Bot_model\`
**Python Version:** 3.14 (in venv)
## ?? Current Architecture
- **Backend:** FastAPI (`backend/api_server.py`) on `localhost:8000`
- **Frontend:** Streamlit (`dashboard.py`) on `localhost:8501`
- **Launcher:** `start_bot.bat` runs both in background and opens browser.
## ?? Authentication (NEW in v3.4)
- Added JWT-based multi-user authentication.
- `backend/auth_manager.py`: Handles SHA-256 password hashing, JWT creation/verification. Default user: `admin` / `password123`.
- `backend/user_session_manager.py`: `UserSession` class created for each logged-in user to isolate `PaperBroker`, `RiskManager`, etc. (Not fully wired into endpoints yet).
- `api_server.py` has JWT HTTP Middleware. All endpoints require `Authorization: Bearer <token>` header.
- `dashboard.py` has a `render_login_screen()` gate. If unauthenticated, shows login form. Stores JWT in `st.session_state`.
## ??? Known Issues / Next Steps for New Chat
1. **Wire User Sessions:** `api_server.py` currently uses a global `state = TradingServerState()`. It needs to be refactored to use `session_manager.get_session(request.state.user_id)` so each user gets their own isolated trading environment.
2. **Fyers API Integration:** User plans to use Fyers API. Need to create `backend/fyers_broker.py` (mock for now). Add a UI input in the Settings tab to input the Fyers App ID/Secret/Token.
3. **UI Refinement:** The dashboard needs UI cleanup, specifically mobile responsiveness and ensuring all tabs render correctly.
4. **Memory/Bugs:** `state.alerts` and `state.daily_pnl_history` grow unbounded (capped to 500/1000 in v3.3 patch, but needs monitoring).
## ?? File Structure
- `start_bot.bat` (Root launcher)
- `dashboard.py` (Streamlit UI)
- `backend/`
  - `api_server.py` (FastAPI backend, secured with JWT)
  - `auth_manager.py` (Auth logic)
  - `user_session_manager.py` (Per-user state isolation)
  - `paper_broker.py`, `risk_manager.py`, `strategy.py`, etc.
## ?? How to Run
1. Open PowerShell, navigate to `C:\Users\Imman\Kiwi_Bot_model`.
2. Activate venv: `.env\Scriptsctivate`.
3. Run: `.\start_bot.bat`.
4. Go to `http://localhost:8501` and login with `admin` / `password123`.
