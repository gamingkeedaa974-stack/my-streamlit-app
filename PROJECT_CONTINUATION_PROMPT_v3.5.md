# 🚀 NSE Options Trading Bot — Project Continuation Prompt (v3.5)
**Status:** Active Development
**Date:** 2024-05-24
**Location:** C:\Users\Imman\Kiwi_Bot_model\
**Python Version:** 3.14 (in venv)
## 🤖 CRITICAL INSTRUCTION FOR THE AI
**At the end of EVERY response you give me, you MUST generate and provide an updated PROJECT_CONTINUATION_PROMPT_vX.X.md file.** 
This is mandatory to ensure I can easily start a new chat without losing context. If we are making major updates, bump the version number (e.g., v3.6). If minor, keep the same version but update the content.
## 📋 Current Architecture
- **Backend:** FastAPI (ackend/api_server.py) on localhost:8000
- **Frontend:** Streamlit (dashboard.py) on localhost:8501
- **Launcher:** start_bot.bat (Double-click to start backend + headless frontend automatically and open browser). Uses UTF-8 encoding to prevent emoji crashes.
## 🔐 Authentication (Completed in v3.4/v3.5)
- JWT-based multi-user authentication is fully active.
- ackend/auth_manager.py: Handles SHA-256 password hashing, JWT creation/verification. Default user: dmin / password123.
- ackend/user_session_manager.py: UserSession class created for each logged-in user to isolate PaperBroker, RiskManager, etc.
- pi_server.py has JWT HTTP Middleware. All endpoints require Authorization: Bearer <token> header.
- dashboard.py has a polished Login Screen (ender_login_screen()) that hides the sidebar, uses a spinner, and is neatly centered with CSS. Logout button added to sidebar.
## 🛠️ Known Issues / Next Steps for New Chat
1. **Wire User Sessions to Endpoints:** pi_server.py currently uses a global state = TradingServerState(). It needs to be refactored to use session_manager.get_session(request.state.user_id) so each user gets their own isolated trading environment.
2. **Fyers API Integration:** User plans to use Fyers API. Need to create ackend/fyers_broker.py (mock for now). Add a UI input in the Settings tab to input the Fyers App ID/Secret/Token.
3. **UI Refinement:** The dashboard needs UI cleanup, specifically mobile responsiveness and ensuring all tabs render correctly.
4. **Memory/Bugs:** state.alerts and state.daily_pnl_history grow unbounded (capped to 500/1000 in v3.3 patch, but needs monitoring).
## 📁 File Structure
- start_bot.bat (Root launcher - runs both backend and frontend)
- dashboard.py (Streamlit UI with Login Gate & polished CSS)
- ackend/
  - pi_server.py (FastAPI backend, secured with JWT)
  - uth_manager.py (Auth logic)
  - user_session_manager.py (Per-user state isolation)
  - paper_broker.py, isk_manager.py, strategy.py, etc.
## 🚀 How to Run
1. Open Windows File Explorer to C:\Users\Imman\Kiwi_Bot_model.
2. Double-click start_bot.bat.
3. Browser opens automatically to http://localhost:8501.
4. Login with dmin / password123.