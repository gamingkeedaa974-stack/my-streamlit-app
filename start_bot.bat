@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title NSE Options Trading Bot
echo Starting NSE Trading Bot...
cd /d C:\Users\Imman\Kiwi_Bot_model
echo [1/3] Activating Virtual Environment...
call venv\Scripts\activate.bat
echo [1.5/3] Clearing any existing backend on port 8000...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000"') do (
    taskkill /PID %%p /F >nul 2>&1
)
echo [2/3] Starting FastAPI Backend...
start /b cmd /c "call venv\Scripts\activate.bat && set PYTHONIOENCODING=utf-8 && python -m backend.api_server --host 0.0.0.0 --port 8000 --no-reload > backend.log 2>&1"
echo [3/3] Starting Streamlit Dashboard...
timeout /t 3 /nobreak >nul
start /b cmd /c "call venv\Scripts\activate.bat && set PYTHONIOENCODING=utf-8 && streamlit run dashboard.py --server.port 8501 --server.headless true > dashboard.log 2>&1"
echo Opening dashboard in browser...
timeout /t 5 /nobreak >nul
start http://localhost:8501
echo.
echo ========================================
echo Bot is running in background. Close this window to keep it running.
echo To stop the bot, close the python/streamlit processes in Task Manager.
echo.
echo MOBILE ACCESS:
echo   1. Make sure your phone is on the same WiFi as this PC.
echo   2. Open Chrome on your phone and go to the URL below:
echo.
REM Extract IP and print full URL
for /f "delims=: tokens=2" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    echo   http://%%a:8501
)
echo ========================================
pause