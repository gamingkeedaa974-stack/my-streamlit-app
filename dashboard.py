"""
dashboard.py v3.3 — Professional Trading Terminal (Thread-Safe Fix)
Features:
- Thread-safe data fetching (no daemon threads)
- Sidebar Command Center
- Horizontal tabs for navigation
- Candlestick charts with trade markers
- Fixed SI toggle
- Cancel button for backtests
- Equity curve with time labels
- Greeks display in positions
- IV percentile & NSE market data panel
- Trailing stop / partial exit status badges
- Real exit reasons with color coding
"""

import streamlit as st
import requests
import time
from datetime import datetime
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from collections import deque
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------- Page Config ----------
st.set_page_config(
    page_title="NSE Options Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- Custom CSS ----------
st.markdown("""
<style>
    .stApp { background-color: #0a0e1a; }
    .status-pill {
        display: inline-flex; align-items: center; gap: 0.3rem;
        padding: 0.15rem 0.6rem; border-radius: 4px;
        font-size: 0.7rem; font-weight: 600; font-family: 'Courier New', monospace;
    }
    .pill-green { background: #064e3b; color: #34d399; border: 1px solid #065f46; }
    .pill-red { background: #450a0a; color: #f87171; border: 1px solid #7f1d1d; }
    .pill-blue { background: #172554; color: #60a5fa; border: 1px solid #1e3a8a; }
    .pill-purple { background: #3b0764; color: #c084fc; border: 1px solid #581c87; }
    .pill-orange { background: #431407; color: #fb923c; border: 1px solid #7c2d12; }
    .pill-amber { background: #451a03; color: #fbbf24; border: 1px solid #78350f; }
    .pill-cyan { background: #083344; color: #22d3ee; border: 1px solid #164e63; }
    .pill-gray { background: #1e293b; color: #94a3b8; border: 1px solid #334155; }
    .pill-pink { background: #4a044e; color: #f0abfc; border: 1px solid #86198f; }
    .sidebar-header { font-size: 1.1rem; font-weight: 700; color: #e2e8f0; margin-bottom: 0.5rem; letter-spacing: 0.05em; }
    .sidebar-section-title { font-size: 0.65rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.1em; margin: 1rem 0 0.5rem 0; font-weight: 700; }
    .mini-metric { background: #1e293b; border-radius: 6px; padding: 0.6rem; margin-bottom: 0.4rem; }
    .mini-metric-label { font-size: 0.65rem; color: #64748b; text-transform: uppercase; }
    .mini-metric-value { font-size: 1rem; font-weight: 700; font-family: 'Courier New', monospace; }
    .mini-metric-positive { color: #34d399; }
    .mini-metric-negative { color: #f87171; }
    .stTabs [data-baseweb="tab-list"] { gap: 0; background: #0f172a; border-radius: 8px 8px 0 0; padding: 0.2rem 0.2rem 0 0.2rem; }
    .stTabs [data-baseweb="tab"] { padding: 0.6rem 1.2rem; font-size: 0.85rem; font-weight: 600; color: #94a3b8; border-radius: 6px 6px 0 0; border: none; background: transparent; }
    .stTabs [aria-selected="true"] { background: #1e293b !important; color: #e2e8f0 !important; border-bottom: 2px solid #60a5fa !important; }
    .stTabs [data-baseweb="tab-panel"] { background: #0f172a; border-radius: 0 0 8px 8px; border: 1px solid #1e293b; border-top: none; padding: 1rem; }
    .fixed-toolbar-bar {
        position: fixed;
        top: 3.5rem;
        left: 260px;
        right: 2rem;
        z-index: 9999;
        display: flex;
        gap: 0.5rem;
        align-items: center;
        padding: 0.5rem 1rem;
        background: rgba(30, 41, 59, 0.95);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 8px;
        border: 1px solid #334155;
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    }
    .fixed-toolbar-bar > div { flex: 1; min-width: 0; }
    .fixed-toolbar-bar button { width: 100%; padding: 0.3rem !important; font-size: 0.8rem !important; }
    .fixed-toolbar-bar label { display: none !important; }
    .toolbar-spacer { height: 4rem; }
    .stTabs [data-baseweb="tab-panel"] { padding: 0.75rem !important; }
    div[data-testid="stVerticalBlock"] > div { gap: 0.5rem !important; }
    .compact-metric { padding: 0.4rem 0.6rem !important; margin-bottom: 0.3rem !important; }
    .compact-label { font-size: 0.6rem !important; margin-bottom: 0.1rem !important; }
    .compact-value { font-size: 0.9rem !important; }
    .card { background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; }
    .card-header { font-size: 0.85rem; font-weight: 700; color: #e2e8f0; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem; }
    .metric-cell { background: #1e293b; border-radius: 6px; padding: 0.75rem; text-align: center; border: 1px solid #334155; }
    .metric-cell-label { font-size: 0.65rem; color: #64748b; text-transform: uppercase; margin-bottom: 0.3rem; }
    .metric-cell-value { font-size: 1.2rem; font-weight: 700; font-family: 'Courier New', monospace; color: #e2e8f0; }
    .positive { color: #34d399; }
    .negative { color: #f87171; }
    .alert-item { padding: 0.5rem 0.75rem; border-radius: 4px; margin-bottom: 0.3rem; font-size: 0.8rem; border-left: 3px solid; }
    .alert-critical { background: #450a0a30; border-color: #dc2626; color: #fca5a5; }
    .alert-error { background: #43140730; border-color: #ea580c; color: #fdba74; }
    .alert-warning { background: #451a0330; border-color: #d97706; color: #fcd34d; }
    .alert-info { background: #17255430; border-color: #2563eb; color: #93c5fd; }
    .alert-success { background: #064e3b30; border-color: #22c55e; color: #86efac; }
    .pos-card { background: #1e293b; border-radius: 6px; padding: 0.75rem; margin-bottom: 0.4rem; border: 1px solid #334155; }
    .pos-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
    .pos-symbol { font-weight: 700; font-size: 0.9rem; color: #e2e8f0; }
    .pos-details { font-size: 0.75rem; color: #94a3b8; line-height: 1.5; }
    .pos-pnl { font-family: 'Courier New', monospace; font-weight: 700; font-size: 1rem; }
    .pos-greeks { font-size: 0.7rem; color: #64748b; margin-top: 0.3rem; padding-top: 0.3rem; border-top: 1px solid #334155; }
    .pos-greek-item { display: inline-block; margin-right: 0.8rem; }
    .pos-exit-badges { margin-top: 0.3rem; }
    .exit-badge { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 3px; font-size: 0.65rem; font-weight: 600; margin-right: 0.3rem; }
    .badge-breakeven { background: #064e3b; color: #34d399; }
    .badge-partial { background: #172554; color: #60a5fa; }
    .badge-trailing { background: #431407; color: #fb923c; }
    .result-metric { background: #1e293b; border-radius: 6px; padding: 1rem; text-align: center; border: 1px solid #334155; }
    .result-metric-value { font-size: 1.4rem; font-weight: 700; font-family: 'Courier New', monospace; }
    .thin-divider { border: none; border-top: 1px solid #1e293b; margin: 0.5rem 0; }
    .nse-data-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; }
    .nse-data-item { background: #1e293b; border-radius: 6px; padding: 0.5rem; text-align: center; border: 1px solid #334155; }
    .nse-data-label { font-size: 0.6rem; color: #64748b; text-transform: uppercase; }
    .nse-data-value { font-size: 0.9rem; font-weight: 700; font-family: 'Courier New', monospace; color: #e2e8f0; }
    .trade-reason { display: inline-block; padding: 0.15rem 0.4rem; border-radius: 3px; font-size: 0.7rem; font-weight: 600; }
    .reason-or-reversion { background: #3b0764; color: #c084fc; }
    .reason-vwap-cross { background: #172554; color: #60a5fa; }
    .reason-mean-touch { background: #064e3b; color: #34d399; }
    .reason-trailing-stop { background: #431407; color: #fb923c; }
    .reason-breakeven { background: #451a03; color: #fbbf24; }
    .reason-partial-exit { background: #083344; color: #22d3ee; }
    .reason-target { background: #064e3b; color: #86efac; }
    .reason-stop-loss { background: #450a0a; color: #f87171; }
    .reason-square-off { background: #1e293b; color: #94a3b8; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0f172a; }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ---------- API Client ----------
API_URL = "http://localhost:8000"

# ---------- API Helpers ----------
def _auth_headers():
    token = st.session_state.get("jwt_token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}

def _safe_get(endpoint: str, timeout: float = 3.0) -> Optional[Any]:
    try:
        headers = {}
        token = st.session_state.get("jwt_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(f"{API_URL}{endpoint}", headers=headers, timeout=timeout)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None

def _safe_post(endpoint: str, payload: dict, timeout: float = 10.0) -> Optional[Any]:
    try:
        headers = {"Content-Type": "application/json"}
        token = st.session_state.get("jwt_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.post(f"{API_URL}{endpoint}", json=payload, headers=headers, timeout=timeout)
        return resp.json() if resp.status_code in (200, 201) else None
    except Exception:
        return None

# ---------- Auth Screen ----------
def render_login_screen():
    st.markdown("""
    <style>
        section[data-testid="stSidebar"] { display: none !important; }
        div[data-testid="stToolbar"] { display: none !important; }
        footer { display: none !important; }
        .block-container {
            padding-top: 8vh !important;
            max-width: 460px !important;
            width: 100% !important;
            margin: auto !important;
        }
        @media (max-width: 600px) {
            .block-container { width: 95% !important; padding-top: 5vh !important; }
        }
        .login-card {
            background: linear-gradient(145deg, #0f172a, #1e293b);
            border: 1px solid #334155;
            border-radius: 16px;
            padding: 2.5rem 2rem 1.5rem 2rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.6), 0 0 0 1px rgba(96,165,250,0.08);
        }
        .login-logo { text-align: center; margin-bottom: 0.3rem; }
        .login-logo-icon { font-size: 2.8rem; display: block; margin-bottom: 0.5rem; }
        .login-title { font-size: 1.5rem; font-weight: 800; color: #e2e8f0; letter-spacing: 0.02em; }
        .login-subtitle { text-align: center; color: #64748b; font-size: 0.85rem; margin-bottom: 1.8rem; }
        .login-card div[data-testid="stTextInput"] > div > div > input {
            background: #0f172a !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
            padding: 0.75rem 1rem !important;
            color: #e2e8f0 !important;
            font-size: 1rem !important;
            min-height: 46px !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }
        .login-card div[data-testid="stTextInput"] > div > div > input:focus {
            border-color: #60a5fa !important;
            box-shadow: 0 0 0 2px rgba(96,165,250,0.2) !important;
        }
        .login-card [data-testid="stFormSubmitButton"] button {
            background: linear-gradient(135deg, #3b82f6, #2563eb) !important;
            border: none !important; border-radius: 8px !important;
            padding: 0.75rem !important; font-size: 1rem !important;
            font-weight: 700 !important; color: white !important;
            width: 100% !important; margin-top: 0.5rem !important;
        }
        .login-card div[data-testid="stException"] {
            background: #450a0a30 !important; border: 1px solid #7f1d1d !important;
            border-radius: 8px !important;
        }
        .login-footer { text-align: center; color: #475569; font-size: 0.72rem; margin-top: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)
    st.markdown('<div class="login-card">'
                '<div class="login-logo">'
                '<span class="login-logo-icon">&#x1F4C8;</span>'
                '<div class="login-title">NSE Trading Bot</div>'
                '</div>'
                '<div class="login-subtitle">Sign in to your trading terminal</div>', unsafe_allow_html=True)
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", value="admin", key="login_user",
                                  label_visibility="collapsed", placeholder="Username")
        password = st.text_input("Password", type="password", key="login_pass",
                                  label_visibility="collapsed", placeholder="Password")
        submit = st.form_submit_button("Sign In", type="primary", use_container_width=True)
    st.markdown('</div>'
                '<div class="login-footer">v3.7 | Secure JWT Auth | Paper &amp; Live Trading</div>',
                unsafe_allow_html=True)
    if submit:
        if not username or not password:
            st.error("Please enter both username and password")
            return
        with st.spinner("Authenticating..."):
            payload = {"username": username, "password": password}
            try:
                resp = requests.post(f"{API_URL}/api/login", json=payload, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.authenticated = True
                    st.session_state.jwt_token = data.get("access_token")
                    st.session_state.user_id = data.get("user_id")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to backend. Is the bot running?")
            except requests.exceptions.Timeout:
                st.error("Login timed out. Backend may be slow to start.")
            except Exception as e:
                st.error(f"Login error: {e}")

# ═══════════════════════════════════════════════════════════
# SIDEBAR — COMMAND CENTER
# ═══════════════════════════════════════════════════════════
def render_sidebar(data):
    with st.sidebar:
        st.markdown('<div class="sidebar-header">⚡ NSE BOT v3.2</div>', unsafe_allow_html=True)

        data = get_data()
        status = data["status"] or {}
        portfolio = data["portfolio"] or {}
        si = data["self_improvement"] or {}
        is_running = status.get("running", False)
        is_kill = portfolio.get("kill_switch", False)

        if st.session_state.get("si_toggled", False):
            fresh_si = _safe_get("/api/self-improvement-status")
            if fresh_si:
                si = fresh_si
            st.session_state.si_toggled = False

        st.markdown('<div class="sidebar-section-title">System</div>', unsafe_allow_html=True)
        cols = st.columns(2)
        with cols[0]:
            if data["ws_connected"]:
                st.markdown('<span class="status-pill pill-green">● ONLINE</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="status-pill pill-red">● OFFLINE</span>', unsafe_allow_html=True)
        with cols[1]:
            if is_running:
                st.markdown('<span class="status-pill pill-green">● RUNNING</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="status-pill pill-gray">● IDLE</span>', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-section-title">Account</div>', unsafe_allow_html=True)
        if portfolio:
            daily_pnl = portfolio.get("daily_pnl", 0)
            pnl_class = "mini-metric-positive" if daily_pnl >= 0 else "mini-metric-negative"
            st.markdown(f'<div class="mini-metric"><div class="mini-metric-label">Daily P&L</div><div class="mini-metric-value {pnl_class}">₹{daily_pnl:,.0f}</div></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="mini-metric"><div class="mini-metric-label">Capital</div><div class="mini-metric-value">₹{portfolio.get("capital", 1_000_000):,.0f}</div></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="mini-metric"><div class="mini-metric-label">Positions</div><div class="mini-metric-value">{portfolio.get("open_positions", 0)}</div></div>', unsafe_allow_html=True)
            net_delta = portfolio.get("net_delta", 0)
            net_gamma = portfolio.get("net_gamma", 0)
            net_theta = portfolio.get("net_theta", 0)
            st.markdown(f'<div class="mini-metric"><div class="mini-metric-label">Δ {net_delta:+.2f} | Γ {net_gamma:+.4f} | Θ {net_theta:+.2f}</div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="mini-metric"><div class="mini-metric-label">Daily P&L</div><div class="mini-metric-value">₹0</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-section-title">Quick Actions</div>', unsafe_allow_html=True)

        if st.button("▶ START", key="sidebar_start", disabled=is_running or is_kill, use_container_width=True):
            result = _safe_post("/api/control", {
                "action": "START", "mode": st.session_state.mode,
                "symbols": st.session_state.selected_symbols,
                "strategy_name": st.session_state.selected_strategy
            })
            if result:
                st.toast("🚀 Bot started!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Failed")

        if st.button("⏹ STOP", key="sidebar_stop", disabled=not is_running, use_container_width=True):
            result = _safe_post("/api/control", {"action": "STOP"})
            if result:
                st.toast("⏹ Stopped")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Failed")

        if st.button("📉 SQUARE OFF", key="sidebar_sq", disabled=not is_running or len(data["positions"]) == 0, use_container_width=True):
            result = _safe_post("/api/control", {"action": "SQUARE_OFF"})
            if result:
                st.toast("📉 Squared off")

        with st.expander("☠ Kill Switch"):
            confirm = st.checkbox("Confirm", key="kill_confirm")
            if confirm and st.button("ACTIVATE", key="sidebar_kill", disabled=is_kill, use_container_width=True):
                result = _safe_post("/api/control", {"action": "KILL_SWITCH"})
                if result:
                    st.toast("🚨 KILL SWITCH")
                    st.rerun()

        st.markdown('<div class="sidebar-section-title">Auto-Improve</div>', unsafe_allow_html=True)

        si_enabled = st.session_state.si_enabled

        toggle_label = "🤖 ENABLE SI" if not si_enabled else "🤖 DISABLE SI"
        if st.button(toggle_label, key="sidebar_si", use_container_width=True):
            result = _safe_post("/api/control", {"action": "TOGGLE_SELF_IMPROVE"})
            if result:
                new_state = result.get("enabled", not si_enabled)
                st.session_state.si_enabled = new_state
                st.session_state.si_toggled = True
                status_text = "ENABLED" if new_state else "DISABLED"
                st.toast(f"🤖 SI {status_text}!")
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("Failed to toggle SI")

        if st.session_state.si_enabled:
            st.markdown('<span class="status-pill pill-green">● ACTIVE</span>', unsafe_allow_html=True)
            if si and si.get("is_ab_testing"):
                st.markdown('<span class="status-pill pill-cyan">🧪 A/B TEST</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-pill pill-gray">● OFF</span>', unsafe_allow_html=True)

        st.markdown('<hr class="thin-divider">', unsafe_allow_html=True)
        if st.button("LOGOUT", key="sidebar_logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.jwt_token = None
            st.rerun()
        st.caption("v3.7 | NSE Bot | JWT Auth")

# ═══════════════════════════════════════════════════════════
# STATUS BAR
# ═══════════════════════════════════════════════════════════
def render_status_bar(data):
    status = data["status"] or {}
    portfolio = data["portfolio"] or {}
    si = data["self_improvement"] or {}

    pills = []
    if data["ws_connected"]:
        pills.append('<span class="status-pill pill-green">● API</span>')
    else:
        pills.append('<span class="status-pill pill-red">● API</span>')

    if status.get("mode") == "PAPER":
        pills.append('<span class="status-pill pill-purple">PAPER</span>')
    elif status.get("mode") == "LIVE":
        pills.append('<span class="status-pill pill-orange">LIVE</span>')

    strat = status.get("strategy", "None")
    if strat and strat != "None":
        pills.append(f'<span class="status-pill pill-blue">{strat.upper()}</span>')

    regime = status.get("market_regime", "")
    if regime and regime != "unknown":
        regime_color = "pill-cyan" if "trending" in regime else "pill-amber" if "ranging" in regime else "pill-pink"
        pills.append(f'<span class="status-pill {regime_color}">📊 {regime.upper()}</span>')

    if st.session_state.si_enabled:
        pills.append('<span class="status-pill pill-cyan">🤖 SI</span>')

    if portfolio.get("kill_switch"):
        pills.append('<span class="status-pill pill-red">🚨 KILL</span>')
    if portfolio.get("circuit_breaker"):
        pills.append('<span class="status-pill pill-amber">⚡ CB</span>')

    iv_pct = portfolio.get("iv_percentile")
    if iv_pct is not None:
        iv_color = "pill-red" if iv_pct > 0.9 else "pill-amber" if iv_pct > 0.75 else "pill-green"
        pills.append(f'<span class="status-pill {iv_color}">IV {iv_pct*100:.0f}%</span>')

    uptime = status.get("uptime_seconds", 0)
    h, m, s = int(uptime // 3600), int((uptime % 3600) // 60), int(uptime % 60)
    last_up = data["last_update"].strftime('%H:%M:%S') if data["last_update"] else '--'

    cols = st.columns([4, 2])
    with cols[0]:
        st.markdown(" ".join(pills), unsafe_allow_html=True)
    with cols[1]:
        if st.button("Refresh", key="statusbar_refresh", use_container_width=True):
            st.rerun()
        st.markdown(f'<div style="text-align:right; font-size:0.75rem; color:#64748b; font-family:monospace;">{h:02d}:{m:02d}:{s:02d} | {last_up}</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# CANDLESTICK CHART HELPER
# ═══════════════════════════════════════════════════════════
def render_candlestick_chart(df: pd.DataFrame, trades: List[Dict] = None, title: str = "Price Chart"):
    """Render a professional candlestick chart with trade markers."""
    if df is None or df.empty:
        st.info("No price data available")
        return

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, row_heights=[0.75, 0.25])

    for col in ['open', 'high', 'low', 'close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['open'], high=df['high'],
        low=df['low'], close=df['close'],
        name='Price',
        increasing_line_color='#22c55e', 
        increasing_fillcolor='rgba(34, 197, 94, 0.5)',
        decreasing_line_color='#ef4444', 
        decreasing_fillcolor='rgba(239, 68, 68, 0.5)',
        increasing_line_width=3, 
        decreasing_line_width=3,
        whiskerwidth=0.6,
    ), row=1, col=1)

    if 'volume' in df.columns:
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
        vol_colors = []
        for i in range(len(df)):
            if df['close'].iloc[i] >= df['open'].iloc[i]:
                vol_colors.append('rgba(34, 197, 94, 0.4)')
            else:
                vol_colors.append('rgba(239, 68, 68, 0.4)')

        fig.add_trace(go.Bar(
            x=df.index, y=df['volume'],
            marker_color=vol_colors, name='Volume',
            showlegend=False
        ), row=2, col=1)

    if trades:
        entry_traces = []
        exit_traces = []
        connect_lines = []

        for trade in trades:
            entry_time = trade.get('entry_time')
            exit_time = trade.get('exit_time')
            entry_price = float(trade.get('entry_price', 0))
            exit_price = float(trade.get('exit_price', 0))
            pnl = float(trade.get('pnl', 0))
            option_type = trade.get('option_type', 'CE')
            exit_reason = trade.get('exit_reason', '')

            entry_idx = None
            exit_idx = None
            entry_y = None
            exit_y = None

            if entry_time and entry_price > 0:
                try:
                    et = pd.to_datetime(entry_time)
                    nearest_idx = df.index.get_indexer([et], method='nearest')[0]
                    if nearest_idx >= 0 and nearest_idx < len(df):
                        candle = df.iloc[nearest_idx]
                        entry_idx = nearest_idx
                        entry_y = candle['high'] * 1.012

                        opt_label = "CALL" if option_type == "CE" else "PUT"
                        marker_color = '#22c55e' if option_type == 'CE' else '#ef4444'
                        symbol = 'triangle-up' if option_type == 'CE' else 'triangle-down'
                        label = f"📥 BUY {opt_label}"

                        entry_traces.append(go.Scatter(
                            x=[df.index[nearest_idx]],
                            y=[entry_y],
                            mode='markers+text',
                            marker=dict(
                                symbol=symbol, size=20, color=marker_color,
                                line=dict(width=3, color='white'),
                                opacity=1.0
                            ),
                            text=[label],
                            textposition="top center",
                            textfont=dict(size=11, color=marker_color, family='Arial Black'),
                            showlegend=False,
                            cliponaxis=False,
                            hovertemplate=f"<b>ENTRY</b><br>Price: ₹{entry_price:.2f}<br>Type: {opt_label}<br>Strike: {trade.get('strike', 'N/A')}<extra></extra>"
                        ))
                except Exception:
                    pass

            if exit_time and exit_price > 0:
                try:
                    ext = pd.to_datetime(exit_time)
                    nearest_idx = df.index.get_indexer([ext], method='nearest')[0]
                    if nearest_idx >= 0 and nearest_idx < len(df):
                        candle = df.iloc[nearest_idx]
                        exit_idx = nearest_idx
                        exit_y = candle['low'] * 0.988

                        exit_color = '#22c55e' if pnl > 0 else '#ef4444'
                        pnl_text = f"+₹{pnl:,.0f}" if pnl > 0 else f"₹{pnl:,.0f}"
                        opt_label = "CALL" if option_type == "CE" else "PUT"
                        label = f"📤 SELL {opt_label} {pnl_text}"

                        exit_traces.append(go.Scatter(
                            x=[df.index[nearest_idx]],
                            y=[exit_y],
                            mode='markers+text',
                            marker=dict(
                                symbol='x', size=18, color=exit_color,
                                line=dict(width=3, color='white'),
                                opacity=1.0
                            ),
                            text=[label],
                            textposition="bottom center",
                            textfont=dict(size=10, color=exit_color, family='Arial Black'),
                            showlegend=False,
                            cliponaxis=False,
                            hovertemplate=f"<b>EXIT</b><br>Price: ₹{exit_price:.2f}<br>P&L: {pnl_text}<br>Reason: {exit_reason}<extra></extra>"
                        ))
                except Exception:
                    pass

            if entry_idx is not None and exit_idx is not None and entry_y is not None and exit_y is not None:
                line_color = 'rgba(34, 197, 94, 0.35)' if pnl > 0 else 'rgba(239, 68, 68, 0.35)'
                connect_lines.append(go.Scatter(
                    x=[df.index[entry_idx], df.index[exit_idx]],
                    y=[entry_y, exit_y],
                    mode='lines',
                    line=dict(color=line_color, width=2, dash='dot'),
                    showlegend=False,
                    hoverinfo='skip',
                    cliponaxis=False,
                ))

        for line in connect_lines:
            fig.add_trace(line, row=1, col=1)
        for trace in entry_traces:
            fig.add_trace(trace, row=1, col=1)
        for trace in exit_traces:
            fig.add_trace(trace, row=1, col=1)

    fig.update_layout(
        title=dict(text=title, font=dict(color='#e2e8f0', size=16, family='Arial')),
        paper_bgcolor='#0a0e1a', plot_bgcolor='#0a0e1a',
        font=dict(color='#94a3b8', family='Arial'),
        xaxis_rangeslider_visible=False,
        showlegend=False,
        margin=dict(l=60, r=80, t=70, b=40),
        height=650,
        hovermode='x unified',
        dragmode='pan',
    )

    fig.update_xaxes(
        gridcolor='#1e293b', tickfont=dict(size=10, color='#64748b'),
        showgrid=True, gridwidth=0.5,
        tickformat='%H:%M',
        nticks=12,
        row=1, col=1
    )
    fig.update_xaxes(
        gridcolor='#1e293b', tickfont=dict(size=10, color='#64748b'),
        showgrid=True, gridwidth=0.5,
        tickformat='%H:%M',
        nticks=12,
        row=2, col=1
    )

    fig.update_yaxes(
        title="Price (₹)", title_font=dict(size=11, color='#64748b'),
        gridcolor='#1e293b', tickfont=dict(size=10, color='#64748b'),
        side='right',
        nticks=10,
        tickformat=',.0f',
        row=1, col=1
    )
    fig.update_yaxes(
        title="Vol", title_font=dict(size=11, color='#64748b'),
        gridcolor='#1e293b', tickfont=dict(size=10, color='#64748b'),
        side='right',
        nticks=5,
        tickformat='s',
        row=2, col=1
    )

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})


def _get_exit_reason_badge(reason: str) -> str:
    """Return a color-coded badge HTML for exit reason."""
    reason_lower = reason.lower()
    if "reversion" in reason_lower or "or " in reason_lower:
        return '<span class="trade-reason reason-or-reversion">OR REV</span>'
    elif "vwap" in reason_lower:
        return '<span class="trade-reason reason-vwap-cross">VWAP</span>'
    elif "mean" in reason_lower:
        return '<span class="trade-reason reason-mean-touch">MEAN</span>'
    elif "trailing" in reason_lower:
        return '<span class="trade-reason reason-trailing-stop">TRAIL</span>'
    elif "breakeven" in reason_lower:
        return '<span class="trade-reason reason-breakeven">BE</span>'
    elif "partial" in reason_lower:
        return '<span class="trade-reason reason-partial-exit">PART</span>'
    elif "target" in reason_lower:
        return '<span class="trade-reason reason-target">TGT</span>'
    elif "stop_loss" in reason_lower or "sl" in reason_lower:
        return '<span class="trade-reason reason-stop-loss">SL</span>'
    elif "square" in reason_lower:
        return '<span class="trade-reason reason-square-off">SQ</span>'
    return '<span class="trade-reason reason-square-off">EXIT</span>'


# ═══════════════════════════════════════════════════════════
# EQUITY CURVE WITH TIME LABELS
# ═══════════════════════════════════════════════════════════
def render_equity_curve(equity_data: List[Dict], title: str = "Equity Curve"):
    """Render equity curve with proper time labels."""
    if not equity_data or len(equity_data) < 2:
        st.info("No equity data available")
        return

    df = pd.DataFrame(equity_data)
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
    elif 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
    else:
        df['step'] = range(len(df))
        df.set_index('step', inplace=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['equity'],
        mode='lines',
        line=dict(color='#34d399', width=2),
        fill='tozeroy',
        fillcolor='rgba(52, 211, 153, 0.1)',
        name='Equity'
    ))

    fig.update_layout(
        title=dict(text=title, font=dict(color='#e2e8f0', size=14)),
        paper_bgcolor='#0f172a',
        plot_bgcolor='#0f172a',
        font=dict(color='#94a3b8'),
        xaxis=dict(
            gridcolor='#1e293b',
            tickformat='%H:%M' if isinstance(df.index, pd.DatetimeIndex) else None,
            title='Time' if isinstance(df.index, pd.DatetimeIndex) else 'Trade #'
        ),
        yaxis=dict(gridcolor='#1e293b', title='Capital (₹)'),
        margin=dict(l=60, r=40, t=50, b=40),
        height=240,
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════
# NSE MARKET DATA PANEL
# ═══════════════════════════════════════════════════════════
def render_nse_data_panel():
    """Render NSE-specific market data: PCR, Max Pain, OI Buildup, IV Percentile."""
    data = get_data()
    portfolio = data["portfolio"] or {}
    nse_data = data.get("nse_data") or {}

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">📊 NSE Market Data</div>', unsafe_allow_html=True)

    cols = st.columns(4)
    metrics = [
        ("PCR Ratio", nse_data.get("pcr_ratio", portfolio.get("pcr_ratio", "N/A")), 
         "pill-blue" if (nse_data.get("pcr_ratio") or 0) > 1 else "pill-gray"),
        ("Max Pain", f"₹{nse_data.get('max_pain', portfolio.get('max_pain', 'N/A'))}", "pill-purple"),
        ("IV %ile", f"{(nse_data.get('iv_percentile') or portfolio.get('iv_percentile') or 0)*100:.0f}%",
         "pill-green" if (nse_data.get("iv_percentile") or 0) < 0.75 else "pill-red"),
        ("OI Buildup", nse_data.get("oi_buildup_str", "—"), "pill-cyan"),
    ]

    for i, (label, value, color) in enumerate(metrics):
        with cols[i]:
            if isinstance(value, (int, float)):
                display_val = f"{value:,.2f}" if isinstance(value, float) else str(value)
            else:
                display_val = str(value)
            st.markdown(f"""
                <div class="nse-data-item">
                    <div class="nse-data-label">{label}</div>
                    <div class="nse-data-value">{display_val}</div>
                </div>
            """, unsafe_allow_html=True)

    oi_buildup = nse_data.get("oi_buildup") or portfolio.get("oi_buildup")
    if oi_buildup and isinstance(oi_buildup, dict):
        st.divider()
        oi_df = pd.DataFrame([
            {"strike": k, "change_pct": v} for k, v in oi_buildup.items()
        ])
        if not oi_df.empty:
            fig = go.Figure()
            colors = ['#22c55e' if x > 0 else '#ef4444' for x in oi_df['change_pct']]
            fig.add_trace(go.Bar(
                x=oi_df['strike'],
                y=oi_df['change_pct'],
                marker_color=colors,
                name='OI Change %'
            ))
            fig.update_layout(
                title=dict(text='OI Buildup by Strike', font=dict(color='#e2e8f0', size=12)),
                paper_bgcolor='#0f172a',
                plot_bgcolor='#0f172a',
                font=dict(color='#94a3b8'),
                xaxis=dict(gridcolor='#1e293b', title='Strike'),
                yaxis=dict(gridcolor='#1e293b', title='OI Change %'),
                height=180,
                margin=dict(l=40, r=20, t=40, b=40),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# TAB 1: PAPER TRADE
# ═══════════════════════════════════════════════════════════
def tab_paper_trade():
    data = get_data()
    status = data["status"] or {}
    portfolio = data["portfolio"] or {}
    si = data["self_improvement"] or {}

    st.markdown('<div class="fixed-toolbar-bar">', unsafe_allow_html=True)
    tcols = st.columns([1, 1, 1.5, 1, 1])
    with tcols[0]:
        st.session_state.mode = st.selectbox("Mode", ["PAPER", "LIVE"], 
            index=0 if st.session_state.mode == "PAPER" else 1, label_visibility="collapsed", key="paper_mode")
    with tcols[1]:
        st.session_state.auto_strategy = st.toggle("Auto", st.session_state.auto_strategy, label_visibility="collapsed", key="paper_auto")
    with tcols[2]:
        if not st.session_state.auto_strategy:
            st.session_state.selected_strategy = st.selectbox("Strategy", 
                ["orb", "vwap_momentum", "mean_reversion"],
                index=["orb", "vwap_momentum", "mean_reversion"].index(st.session_state.selected_strategy),
                label_visibility="collapsed", key="paper_strat")
        else:
            auto_name = si.get("current_params", {}).get("name", "orb") if si else "orb"
            st.markdown(f'<div style="padding-top:0.5rem;"><span class="status-pill pill-cyan">🤖 {auto_name.upper()}</span></div>', unsafe_allow_html=True)
            st.session_state.selected_strategy = auto_name
    with tcols[3]:
        st.session_state.selected_symbols = st.multiselect("Symbols",
            ["NSE:NIFTY50-INDEX", "NSE:BANKNIFTY-INDEX", "NSE:FINNIFTY-INDEX", 
             "NSE:MIDCPNIFTY-INDEX", "BSE:SENSEX-INDEX"],
            default=st.session_state.selected_symbols, label_visibility="collapsed", key="paper_symbols")
    with tcols[4]:
        regime = si.get("market_regime", "detecting...") if si else "detecting..."
        st.markdown(f'<div style="padding-top:0.5rem; text-align:right;"><span class="status-pill pill-gray">📊 {regime}</span></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="toolbar-spacer"></div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">💼 Portfolio</div>', unsafe_allow_html=True)
    mcols = st.columns(6)
    metrics = [
        ("Daily P&L", f"₹{portfolio.get('daily_pnl', 0):,.2f}", portfolio.get('daily_pnl_pct', 0), True),
        ("Capital", f"₹{portfolio.get('capital', 1_000_000):,.0f}", None, False),
        ("Positions", str(portfolio.get('open_positions', 0)), None, False),
        ("Margin", f"{portfolio.get('margin_used_pct', 0):.1f}%", None, False),
        ("Delta", f"{portfolio.get('net_delta', 0):.2f}", None, False),
        ("VIX", f"{portfolio.get('vix', 'N/A')}", None, False),
    ]
    for i, (label, value, delta, is_pnl) in enumerate(metrics):
        with mcols[i]:
            st.markdown(f'<div class="metric-cell">', unsafe_allow_html=True)
            st.markdown(f'<div class="metric-cell-label">{label}</div>', unsafe_allow_html=True)
            if is_pnl and delta is not None:
                color = "positive" if delta >= 0 else "negative"
                st.markdown(f'<div class="metric-cell-value {color}">{value}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="metric-cell-delta {color}">{delta:+.2f}%</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="metric-cell-value">{value}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.get("show_nse_data", True):
        render_nse_data_panel()

    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-header">📊 P&L Curve</div>', unsafe_allow_html=True)
        pnl_hist = data["pnl_history"]
        if len(pnl_hist) > 1:
            render_equity_curve([
                {"time": item["time"], "equity": item["equity"]} 
                for item in pnl_hist
            ], title="Live P&L")
        else:
            st.info("Start bot to see P&L chart")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-header">🔔 Alerts</div>', unsafe_allow_html=True)
        alerts = data["alerts"]
        if alerts:
            for alert in alerts[:8]:
                level = alert.get("level", "INFO")
                msg = alert.get("message", "")
                ts = alert.get("timestamp", "")
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
                    except:
                        ts = str(ts)[:8]
                alert_class = {"CRITICAL": "alert-critical", "ERROR": "alert-error",
                    "WARNING": "alert-warning", "SUCCESS": "alert-success"}.get(level, "alert-info")
                st.markdown(f'<div class="alert-item {alert_class}"><b>{level}</b> <span style="opacity:0.5">{ts}</span> — {msg}</div>', unsafe_allow_html=True)
        else:
            st.info("No alerts")
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-header">📋 Positions</div>', unsafe_allow_html=True)
        positions = data["positions"]
        if positions:
            for pos in positions:
                pnl = pos.get("unrealized_pnl", 0)
                pnl_pct = pos.get("unrealized_pnl_pct", 0)
                color = "positive" if pnl >= 0 else "negative"

                badges = []
                if pos.get("breakeven_triggered"):
                    badges.append('<span class="exit-badge badge-breakeven">BE</span>')
                if pos.get("partial_exit_done"):
                    badges.append('<span class="exit-badge badge-partial">PART</span>')
                if pos.get("trailing_sl_price"):
                    badges.append(f'<span class="exit-badge badge-trailing">TRAIL ₹{pos["trailing_sl_price"]:.1f}</span>')

                greeks_html = ""
                if any(k in pos for k in ["delta", "gamma", "theta", "vega"]):
                    greeks_items = []
                    if pos.get("delta") is not None:
                        greeks_items.append(f"Δ {pos['delta']:+.3f}")
                    if pos.get("gamma") is not None:
                        greeks_items.append(f"Γ {pos['gamma']:.4f}")
                    if pos.get("theta") is not None:
                        greeks_items.append(f"Θ {pos['theta']:+.2f}")
                    if pos.get("vega") is not None:
                        greeks_items.append(f"V {pos['vega']:.2f}")
                    if greeks_items:
                        greeks_html = '<div class="pos-greeks">' + ' | '.join(
                            f'<span class="pos-greek-item">{g}</span>' for g in greeks_items
                        ) + '</div>'

                st.markdown(f"""
                    <div class="pos-card">
                        <div class="pos-header">
                            <div>
                                <div class="pos-symbol">{pos.get('symbol', '')} {pos.get('option_type', '')}</div>
                                <div class="pos-details">Qty: {pos.get('quantity', 0)}/{pos.get('original_quantity', pos.get('quantity', 0))} | Strike: {pos.get('strike', 0)}</div>
                                <div class="pos-details">Entry: ₹{pos.get('entry_price', 0):.2f} | Cur: ₹{pos.get('current_price', 0):.2f}</div>
                                {greeks_html}
                            </div>
                            <div style="text-align:right;">
                                <div class="pos-pnl {color}">₹{pnl:,.0f}</div>
                                <div class="pos-details {color}">{pnl_pct:+.2f}%</div>
                                <div class="pos-details">SL: ₹{pos.get('stop_loss', 0):.2f}</div>
                                <div class="pos-exit-badges">{''.join(badges)}</div>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No positions")
        st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.si_enabled:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-header">🤖 SI Metrics</div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.metric("Win Rate", f"{si.get('win_rate', 0):.1f}%", delta=None)
            c2.metric("Sharpe", f"{si.get('sharpe_ratio', 0):.2f}", delta=None)
            c1.metric("Drawdown", f"{si.get('max_drawdown', 0):.2f}%", delta=None)
            c2.metric("Changes", si.get('optimization_count_today', 0), delta=None)
            if si and si.get("current_params"):
                with st.expander("Params"):
                    st.json(si.get("current_params", {}))
            st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# TAB 2: LIVE TRADE
# ═══════════════════════════════════════════════════════════
def tab_live_trade():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">🔴 Live Trading</div>', unsafe_allow_html=True)
    st.warning("⚠️ Requires broker API key. Currently in development.")
    st.divider()
    st.subheader("Supported Brokers")
    brokers = [("Fyers", "✅ Recommended", "Good API"), ("Angel One", "✅ Available", "SmartAPI"),
        ("Zerodha", "✅ Available", "Kite Connect"), ("Upstox", "⏳ Coming Soon", "API in beta")]
    for name, status, desc in brokers:
        c1, c2, c3 = st.columns([2, 2, 4])
        with c1: st.write(f"**{name}**")
        with c2: st.write(status)
        with c3: st.caption(desc)
    st.divider()
    st.subheader("Connection Setup")
    c1, c2 = st.columns(2)
    with c1: st.selectbox("Broker", ["Fyers", "Angel One", "Zerodha"], key="live_broker")
    with c2: st.text_input("API Key", type="password", placeholder="Enter key", key="live_key")
    st.text_input("API Secret", type="password", placeholder="Enter secret", key="live_secret")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔗 Connect", type="primary", use_container_width=True, key="live_connect"):
            st.info("Coming in next update")
    with c2:
        if st.button("🧪 Test", use_container_width=True, key="live_test"):
            st.info("Will verify credentials")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">📋 Requirements</div>', unsafe_allow_html=True)
    st.markdown("""
    1. **Broker Account** with algo trading enabled
    2. **API Key + Secret** from broker developer portal
    3. **Access Token** (OAuth2, expires daily)
    4. **TOTP 2FA** setup
    5. **Minimum Capital**: ~₹1.5L for 1 NIFTY lot
    6. **SEBI Compliance**: Audit logs maintained automatically
    """)
    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# TAB 3: BACKTEST LAB (with Candlestick Charts + Cancel)
# ═══════════════════════════════════════════════════════════
def tab_backtest():
    data = get_data()

    # ── TOOLBAR ──
    st.markdown('<div class="fixed-toolbar-bar">', unsafe_allow_html=True)
    bcols = st.columns([1, 1, 1, 1, 1, 1])
    with bcols[0]:
        st.selectbox("Strategy", ["auto", "orb", "vwap_momentum", "mean_reversion"], key="bt_strat")
    with bcols[1]:
        st.selectbox("Symbol", ["NIFTY50", "BANKNIFTY", "FINNIFTY", "SENSEX"], key="bt_sym")
    with bcols[2]:
        st.number_input("Days", 1, 120, 5, key="bt_days")
    with bcols[3]:
        st.selectbox("Data", ["synthetic", "real", "csv_file"], key="bt_mode")
    with bcols[4]:
        mode = st.session_state.get("bt_mode", "synthetic")
        if mode == "csv_file":
            st.text_input("CSV", placeholder="path/to/file.csv", key="bt_csv", label_visibility="collapsed")
        elif mode == "real":
            st.selectbox("Source", ["auto", "nsepython", "fyers", "zerodha"], key="bt_source", label_visibility="collapsed")
        else:
            st.markdown('<div style="padding-top:0.5rem;"><span class="status-pill pill-gray">auto-generated</span></div>', unsafe_allow_html=True)
    with bcols[5]:
        is_auto = st.session_state.get("bt_strat", "orb") == "auto"
        btn_label = "🚀 COMPARE ALL" if is_auto else "🚀 RUN"

        # ── NEW: Cancel button during backtest ──
        if st.session_state.get("bt_running", False):
            if st.button("⛔ CANCEL", type="secondary", use_container_width=True, key="bt_cancel"):
                st.session_state.bt_cancelled = True
                st.session_state.bt_running = False
                st.toast("⛔ Backtest cancelled")
                time.sleep(0.3)
                st.rerun()
        else:
            if st.button(btn_label, type="primary", use_container_width=True, key="bt_run"):
                st.session_state.bt_running = True
                st.session_state.bt_cancelled = False
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="toolbar-spacer"></div>', unsafe_allow_html=True)

    # ── Handle backtest execution ──
    if st.session_state.get("bt_running", False) and not st.session_state.get("bt_cancelled", False):
        with st.spinner("Comparing all strategies..." if is_auto else "Running backtest..."):
            payload = {
                "symbol": st.session_state.get("bt_sym", "NIFTY50"),
                "days": st.session_state.get("bt_days", 30),
                "mode": st.session_state.get("bt_mode", "synthetic"),
                "interval": "5minute"
            }
            if st.session_state.get("bt_mode") == "csv_file":
                payload["data_path"] = st.session_state.get("bt_csv", "")
            elif st.session_state.get("bt_mode") == "real":
                payload["data_source"] = st.session_state.get("bt_source", "auto")
                from datetime import datetime, timedelta
                end_dt = datetime.now()
                start_dt = end_dt - timedelta(days=st.session_state.get("bt_days", 30))
                payload["start_date"] = start_dt.strftime("%Y-%m-%d")
                payload["end_date"] = end_dt.strftime("%Y-%m-%d")

            if is_auto:
                result = _safe_post("/api/backtest/compare", payload, timeout=120.0)
                st.session_state.bt_running = False
                if result and isinstance(result, dict) and "comparisons" in result:
                    st.session_state.last_compare_result = result
                    st.success(f"✅ Winner: {result.get('winner', 'Unknown').upper()}")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Comparison failed. Is backend running?")
            else:
                payload["strategy"] = st.session_state.get("bt_strat", "orb")
                result = _safe_post("/api/backtest", payload, timeout=60.0)
                st.session_state.bt_running = False
                if result and isinstance(result, dict) and "total_trades" in result:
                    st.session_state.last_backtest_result = result
                    st.success(f"✅ Backtest complete! {result.get('total_trades', 0)} trades")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Backtest failed. Is backend running?")

    # ── COMPARISON VIEW (AUTO MODE) ──
    compare_result = st.session_state.get("last_compare_result")
    if compare_result and st.session_state.get("bt_strat") == "auto":
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-header">🏆 Strategy Comparison Results</div>', unsafe_allow_html=True)

        winner = compare_result.get("winner", "")
        comparisons = compare_result.get("comparisons", [])

        if comparisons:
            st.markdown(f"""
                <div style="background: linear-gradient(90deg, #064e3b, #065f46);
                    border: 1px solid #22c55e; border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                    <div style="font-size: 1.2rem; font-weight: 700; color: #34d399;">
                        🏆 WINNER: {winner.upper()}
                    </div>
                    <div style="font-size: 0.85rem; color: #86efac; margin-top: 0.3rem;">
                        Best composite score across P&L, Sharpe, Win Rate, and Drawdown on identical data
                    </div>
                </div>
            """, unsafe_allow_html=True)

            st.subheader("📊 Side-by-Side Comparison")
            rows = []
            for c in comparisons:
                rows.append({
                    "Strategy": c.get("strategy", "").upper(),
                    "Score": c.get("score", 0),
                    "P&L %": f"{c.get('total_pnl_pct', 0):.2f}%",
                    "Trades": c.get("total_trades", 0),
                    "Win Rate": f"{c.get('win_rate', 0):.1f}%",
                    "Sharpe": f"{c.get('sharpe_ratio', 0):.2f}",
                    "Max DD": f"{c.get('max_drawdown', 0):.2f}%",
                    "Profit Factor": f"{c.get('profit_factor', 0):.2f}",
                    "Avg Trade": f"₹{c.get('avg_trade_pnl', 0):,.0f}",
                })
            df_compare = pd.DataFrame(rows)

            def highlight_winner(row):
                if row['Strategy'].lower() == winner.lower():
                    return ['background-color: #064e3b; color: #34d399; font-weight: 700'] * len(row)
                return [''] * len(row)

            st.dataframe(df_compare.style.apply(highlight_winner, axis=1),
                        use_container_width=True, hide_index=True, height=200)

            winner_data = next((c for c in comparisons if c.get("strategy") == winner), None)
            if winner_data:
                st.divider()
                st.subheader(f"📈 {winner.upper()} — Winner Chart & Trades")
                ohlc_data = winner_data.get("ohlc_data", [])
                trades = winner_data.get("trades", [])
                if ohlc_data and len(ohlc_data) > 0:
                    chart_df = pd.DataFrame(ohlc_data)
                    chart_df['timestamp'] = pd.to_datetime(chart_df['timestamp'])
                    chart_df.set_index('timestamp', inplace=True)
                    chart_df = chart_df[['open', 'high', 'low', 'close', 'volume']]
                    render_candlestick_chart(chart_df, trades,
                        title=f"{winner.upper()} on {compare_result.get('symbol', '')}")
                else:
                    st.info("No OHLC data available for winner")

                if trades:
                    with st.expander(f"📋 {winner.upper()} Trade Log ({len(trades)} trades)"):
                        trade_df = pd.DataFrame(trades)
                        if 'exit_reason' in trade_df.columns:
                            trade_df['exit_badge'] = trade_df['exit_reason'].apply(
                                lambda r: _get_exit_reason_badge(r)
                            )
                        st.dataframe(trade_df, use_container_width=True, hide_index=True, height=250)

                st.divider()
                c1, c2 = st.columns([1, 3])
                with c1:
                    if st.button("✅ Use Winner for Paper Trading", type="primary", use_container_width=True, key="use_winner"):
                        st.session_state.selected_strategy = winner
                        st.session_state.bt_strat = winner
                        st.session_state.last_compare_result = None
                        st.success(f"Strategy set to {winner.upper()}! Go to Paper Trade tab to start.")
                        time.sleep(1)
                        st.rerun()
                with c2:
                    st.info("Sets active strategy. Self-Improvement will then auto-tune its parameters.")
        else:
            st.error("No comparison data returned")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # ── REGULAR SINGLE-STRATEGY BACKTEST VIEW ──
    last_result = st.session_state.get("last_backtest_result")
    bt_results = data.get("backtest_results", [])

    all_results = []
    if last_result and isinstance(last_result, dict):
        all_results.append(last_result)
    if bt_results and isinstance(bt_results, list):
        all_results.extend([r for r in bt_results if isinstance(r, dict)])

    seen = set()
    unique_results = []
    for r in all_results:
        ts = r.get("timestamp", r.get("id", str(r)))
        if ts not in seen:
            seen.add(ts)
            unique_results.append(r)

    if unique_results:
        latest = unique_results[-1]

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-header">📊 Results</div>', unsafe_allow_html=True)
        mcols = st.columns(6)
        metrics = [
            ("Total P&L", f"₹{latest.get('total_pnl', 0):,.2f}", latest.get('total_pnl_pct', 0), True),
            ("Win Rate", f"{latest.get('win_rate', 0):.1f}%", None, False),
            ("Trades", str(latest.get('total_trades', 0)), None, False),
            ("Sharpe", f"{latest.get('sharpe_ratio', 0):.2f}", None, False),
            ("Max DD", f"{latest.get('max_drawdown', 0):.2f}%", None, False),
            ("Profit Factor", f"{latest.get('profit_factor', 0):.2f}", None, False),
        ]
        for i, (label, value, delta, is_pnl) in enumerate(metrics):
            with mcols[i]:
                st.markdown(f'<div class="metric-cell">', unsafe_allow_html=True)
                st.markdown(f'<div class="metric-cell-label">{label}</div>', unsafe_allow_html=True)
                if is_pnl and delta is not None:
                    color = "positive" if delta >= 0 else "negative"
                    st.markdown(f'<div class="metric-cell-value {color}">{value}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="metric-cell-delta {color}">{delta:+.2f}%</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="metric-cell-value">{value}</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-header">📈 Price Chart with Trades</div>', unsafe_allow_html=True)
            ohlc_data = latest.get("ohlc_data", [])
            trades = latest.get("trades", [])
            if ohlc_data and len(ohlc_data) > 0:
                chart_df = pd.DataFrame(ohlc_data)
                chart_df['timestamp'] = pd.to_datetime(chart_df['timestamp'])
                chart_df.set_index('timestamp', inplace=True)
                chart_df = chart_df[['open', 'high', 'low', 'close', 'volume']]
                render_candlestick_chart(chart_df, trades,
                    title=f"{latest.get('strategy', '').upper()} on {latest.get('symbol', '')}")
            else:
                st.info("No chart data available")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-header">⚙️ Parameters</div>', unsafe_allow_html=True)
            params = latest.get("params", {})
            if params:
                pcols = st.columns(min(4, len(params)))
                for i, (k, v) in enumerate(params.items()):
                    with pcols[i % len(pcols)]:
                        st.markdown(f'<div class="result-metric"><div class="metric-cell-label">{k}</div><div class="result-metric-value">{v}</div></div>', unsafe_allow_html=True)
            else:
                st.info("No parameters recorded")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-header">📋 Extra Metrics</div>', unsafe_allow_html=True)
            em_cols = st.columns(4)
            with em_cols[0]: st.metric("Avg Trade", f"₹{latest.get('avg_trade_pnl', 0):,.0f}")
            with em_cols[1]: st.metric("Max Consec Losses", latest.get('max_consecutive_losses', 0))
            with em_cols[2]: st.metric("Winning Trades", latest.get('winning_trades', 0))
            with em_cols[3]: st.metric("Losing Trades", latest.get('losing_trades', 0))
            st.markdown('</div>', unsafe_allow_html=True)

        with c2:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-header">📋 Trade Log</div>', unsafe_allow_html=True)
            trades = latest.get("trades", [])
            if trades:
                trade_df = pd.DataFrame(trades)
                if 'exit_reason' in trade_df.columns:
                    trade_df['exit_badge'] = trade_df['exit_reason'].apply(
                        lambda r: _get_exit_reason_badge(r)
                    )
                st.dataframe(trade_df, use_container_width=True, hide_index=True, height=400)
            else:
                st.info("No trades executed")
            st.markdown('</div>', unsafe_allow_html=True)

            equity_curve = latest.get("equity_curve", [])
            if equity_curve and len(equity_curve) > 1:
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown('<div class="card-header">📈 Equity Curve</div>', unsafe_allow_html=True)

                if isinstance(equity_curve[0], dict) and 'timestamp' in equity_curve[0]:
                    eq_data = [
                        {"timestamp": e.get('timestamp'), "equity": e.get('equity', 0)}
                        for e in equity_curve
                    ]
                    render_equity_curve(eq_data, title="Equity Curve")
                else:
                    eq_df = pd.DataFrame({"step": range(len(equity_curve)), "equity": equity_curve})
                    st.line_chart(eq_df, x="step", y="equity", color="#34d399", height=200)
                st.markdown('</div>', unsafe_allow_html=True)

        if len(unique_results) > 1:
            st.divider()
            st.subheader("📚 Backtest History")
            for result in reversed(unique_results[-5:-1]):
                with st.expander(f"{result.get('strategy', 'Unknown').upper()} — {result.get('symbol', '')} — {result.get('total_trades', 0)} trades"):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("P&L", f"{result.get('total_pnl_pct', 0):.2f}%")
                    c2.metric("Win Rate", f"{result.get('win_rate', 0):.1f}%")
                    c3.metric("Sharpe", f"{result.get('sharpe_ratio', 0):.2f}")
                    c4.metric("Trades", result.get('total_trades', 0))
    else:
        st.info("No backtest results yet. Configure parameters above and click RUN.")
        with st.expander("💡 How Backtesting Works"):
            st.markdown("""
            1. **Select Strategy**: ORB, VWAP Momentum, or Mean Reversion
            2. **Select Symbol**: NIFTY50, BANKNIFTY, FINNIFTY, SENSEX
            3. **Select Data**: Synthetic (fast), Real (NSEPython/Fyers/Zerodha), or CSV
            4. **Click RUN**: Engine simulates trades on historical data
            5. **Analyze**: Review P&L, win rate, Sharpe, drawdown, and trade-by-trade log
            """)

# ═══════════════════════════════════════════════════════════
# TAB 4: OPTIMIZE
# ═══════════════════════════════════════════════════════════
def tab_optimize():
    data = get_data()

    st.markdown('<div class="fixed-toolbar-bar">', unsafe_allow_html=True)
    ocols = st.columns([1, 1, 1, 1, 1, 1])
    with ocols[0]:
        st.selectbox("Strategy", ["orb", "vwap_momentum", "mean_reversion"], key="opt_strat")
    with ocols[1]:
        st.selectbox("Search", ["adaptive", "grid"], key="opt_mode")
    with ocols[2]:
        st.number_input("Iterations", 10, 200, 30, key="opt_iters")
    with ocols[3]:
        st.number_input("Train Days", 10, 120, 60, key="opt_days")
    with ocols[4]:
        st.markdown('<div style="padding-top:0.5rem;"><span class="status-pill pill-gray">60% broad + 40% focused</span></div>', unsafe_allow_html=True)
    with ocols[5]:
        if st.button("🚀 RUN", type="primary", use_container_width=True, key="opt_run"):
            with st.spinner("Optimizing..."):
                result = _safe_post("/api/optimize", {
                    "strategy": st.session_state.get("opt_strat", "orb"),
                    "mode": st.session_state.get("opt_mode", "adaptive"),
                    "iterations": st.session_state.get("opt_iters", 30),
                    "days": st.session_state.get("opt_days", 60)
                }, timeout=120.0)
                if result and isinstance(result, dict) and "best_params" in result:
                    st.session_state.last_opt_result = result
                    st.success(f"✅ Optimization complete! Score: {result.get('best_score', 0):.2f}")
                    time.sleep(0.5)
                    st.rerun()
                elif result and isinstance(result, dict):
                    st.error(f"❌ Optimization error: {result.get('detail', 'Unknown error')}")
                else:
                    st.error("❌ Failed. Is backend running on localhost:8000?")
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="toolbar-spacer"></div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">📊 Optimization Results</div>', unsafe_allow_html=True)

    last_result = st.session_state.get("last_opt_result")
    opt_results = data["optimization_results"]

    all_results = []
    if last_result and isinstance(last_result, dict):
        all_results.append(last_result)
    if opt_results and isinstance(opt_results, list):
        all_results.extend([r for r in opt_results if isinstance(r, dict)])

    seen = set()
    unique_results = []
    for r in all_results:
        ts = r.get("timestamp", r.get("id", str(r)))
        if ts not in seen:
            seen.add(ts)
            unique_results.append(r)

    if unique_results:
        latest = unique_results[-1]

        cols = st.columns([3, 1, 1])
        with cols[0]:
            st.markdown(f'<div style="font-size:1.1rem; font-weight:700; color:#e2e8f0;">⚡ {latest.get("strategy_name", "Unknown").upper()}</div>', unsafe_allow_html=True)
        with cols[1]:
            improvement = latest.get("improvement_pct", 0)
            color = "pill-green" if improvement > 0 else "pill-red"
            st.markdown(f'<span class="status-pill {color}">+{improvement:.1f}%</span>', unsafe_allow_html=True)
        with cols[2]:
            st.markdown(f'<span class="status-pill pill-blue">Score: {latest.get("best_score", 0):.2f}</span>', unsafe_allow_html=True)

        st.divider()

        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("🏆 Best Parameters")
            best_params = latest.get("best_params", {})
            if best_params:
                pcols = st.columns(min(3, len(best_params)))
                for i, (k, v) in enumerate(best_params.items()):
                    with pcols[i % len(pcols)]:
                        st.markdown(f'<div class="result-metric"><div class="metric-cell-label">{k}</div><div class="result-metric-value">{v}</div></div>', unsafe_allow_html=True)
            else:
                st.info("No parameters")

        with col2:
            st.subheader("📈 Performance")
            train_pnl = latest.get("train_pnl", latest.get("train_results", {}).get("total_pnl_pct", 0))
            test_pnl = latest.get("test_pnl", latest.get("test_results", {}).get("total_pnl_pct", 0))
            baseline = latest.get("baseline_score", 0)

            st.metric("Train P&L", f"{train_pnl:.2f}%")
            st.metric("Test P&L", f"{test_pnl:.2f}%")
            st.metric("Baseline", f"{baseline:.2f}")
            st.metric("Best Score", f"{latest.get('best_score', 0):.2f}")

        if len(unique_results) > 1:
            st.divider()
            st.subheader("📚 History")
            for result in reversed(unique_results[-6:-1]):
                with st.expander(f"{result.get('strategy_name', 'Unknown')} — Score: {result.get('best_score', 0):.2f}"):
                    params = result.get('best_params', {})
                    if params:
                        st.json(params)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Improvement", f"{result.get('improvement_pct', 0):.1f}%")
                    c2.metric("Train P&L", f"{result.get('train_pnl', 0):.2f}%")
                    c3.metric("Test P&L", f"{result.get('test_pnl', 0):.2f}%")
    else:
        st.info("No results yet. Configure and run above.")
        with st.expander("💡 How Auto-Optimization Works"):
            st.markdown("""
            1. **Adaptive Search**: 60% broad random + 40% focused mutation
            2. **Validation**: Best params tested on unseen data
            3. **A/B Test**: Live comparison for 15 min
            4. **Auto-Apply**: If candidate beats current by >5%, auto-switch
            5. **Safety**: Max 3 changes/day, auto-revert if A/B fails
            """)

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# TAB 5: SETTINGS
# ═══════════════════════════════════════════════════════════
def tab_settings():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">⚙️ Trading Settings</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1: st.number_input("Capital (₹)", 100000, 5000000, 1000000, step=50000, key="set_capital")
    with c2: st.number_input("Lot Size", 1, 100, 25, key="set_lot")

    st.divider()
    st.subheader("Risk Limits")
    c1, c2, c3 = st.columns(3)
    with c1: st.slider("Max Daily Loss %", 1, 10, 3, key="set_maxloss")
    with c2: st.slider("Max Risk/Trade %", 0.5, 5.0, 1.0, step=0.5, key="set_risk")
    with c3: st.slider("Max Positions", 1, 5, 2, key="set_maxpos")

    st.divider()
    st.subheader("Self-Improvement")
    c1, c2 = st.columns(2)
    with c1: st.slider("Check Interval (min)", 1, 30, 5, key="set_si_interval")
    with c2: st.slider("Max Changes/Day", 1, 10, 3, key="set_si_changes")

    st.divider()
    st.subheader("Notifications")
    telegram_enabled = st.toggle("Telegram Alerts", key="set_telegram")
    if telegram_enabled:
        st.text_input("Bot Token", type="password", key="set_telegram_token")
        st.text_input("Chat ID", key="set_telegram_chat")

    st.divider()
    st.subheader("Display")
    st.toggle("Show NSE Market Data Panel", value=st.session_state.get("show_nse_data", True), key="show_nse_data")

    if st.button("💾 Save", type="primary", use_container_width=True, key="set_save"):
        st.success("Settings saved!")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">📋 Symbol Universe</div>', unsafe_allow_html=True)
    symbols_data = {
        "Indices": ["NIFTY 50", "BANK NIFTY", "FIN NIFTY", "MIDCAP NIFTY", "SENSEX", "BANKEX"],
        "Stocks (Sample)": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC"],
        "Coming Soon": ["All NSE F&O (~180)", "Currency pairs", "Commodities"]
    }
    for category, syms in symbols_data.items():
        with st.expander(category):
            st.write(", ".join(syms))
    st.info("💡 Connect to Fyers/Zerodha/Angel One for 180+ F&O symbols.")
    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

# ---------- Session State Initialization ----------
def init_session_state():
    defaults = {
        "authenticated": False,
        "jwt_token": None,
        "user_id": None,
        "si_enabled": False,
        "si_toggled": False,
        "mode": "PAPER",
        "auto_strategy": False,
        "selected_strategy": "orb",
        "selected_symbols": ["NSE:NIFTY50-INDEX"],
        "show_nse_data": True,
        "bt_running": False,
        "bt_cancelled": False,
        "bt_strat": "orb",
        "bt_sym": "NIFTY50",
        "bt_days": 30,
        "bt_mode": "synthetic",
        "bt_source": "auto",
        "bt_csv": "",
        "opt_strat": "orb",
        "opt_mode": "adaptive",
        "opt_iters": 30,
        "opt_days": 60,
        "last_backtest_result": None,
        "last_compare_result": None,
        "last_opt_result": None,
        "kill_confirm": False,
        "live_broker": "Fyers",
        "live_key": "",
        "live_secret": "",
        "set_capital": 1000000,
        "set_lot": 25,
        "set_maxloss": 3,
        "set_risk": 1.0,
        "set_maxpos": 2,
        "set_si_interval": 5,
        "set_si_changes": 3,
        "set_telegram": False,
        "set_telegram_token": "",
        "set_telegram_chat": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

# === AUTO-REPAIRED MISSING FUNCTIONS ===

# ---------- API Helpers ----------
def _auth_headers():
    h = {"Content-Type": "application/json"}
    token = st.session_state.get("jwt_token")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h
def _safe_get(endpoint: str, timeout: float = 5.0) -> Optional[Any]:
    try:
        resp = requests.get(f"{API_URL}{endpoint}", headers=_auth_headers(), timeout=timeout)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None
def _safe_post(endpoint: str, payload: dict, timeout: float = 10.0) -> Optional[Any]:
    try:
        resp = requests.post(f"{API_URL}{endpoint}", json=payload, headers=_auth_headers(), timeout=timeout)
        return resp.json() if resp.status_code in (200, 201) else None
    except Exception:
        return None

# --- Fast single-call data fetch ---
def _fetch_dashboard():
    try:
        resp = requests.get(f"{API_URL}/api/dashboard", headers=_auth_headers(), timeout=5.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}
def get_data():
    raw = _fetch_dashboard()
    portfolio = raw.get("portfolio") or {}
    return {
        "status": raw.get("status"),
        "portfolio": portfolio,
        "positions": list(raw.get("positions") or []),
        "alerts": list(raw.get("alerts") or []),
        "backtest_results": list(raw.get("backtest_results") or []),
        "optimization_results": list(raw.get("optimization_results") or []),
        "self_improvement": raw.get("self_improvement"),
        "pnl_history": [],
        "last_update": datetime.now(),
        "ws_connected": raw.get("status") is not None,
        "nse_data": None,
    }
# === END AUTO-REPAIR ===

def main():
    init_session_state()
    # ---------- AUTH GATE ----------
    if not st.session_state.authenticated:
        render_login_screen()
        st.stop()
    # ----------------------------
    # Fetch data ONCE ? pass to all render functions
    data = get_data()
    # Show connectivity warning if backend is offline
    if not data.get("ws_connected"):
        st.warning("Backend API is offline. Start the bot or check if FastAPI is running on port 8000.")
    render_sidebar(data)
    render_status_bar(data)

    tabs = st.tabs(["📊 Paper Trade", "🔴 Live Trade", "🔬 Intraday Backtest", "⚡ Optimize", "⚙️ Settings"])

    with tabs[0]:
        tab_paper_trade()
    with tabs[1]:
        tab_live_trade()
    with tabs[2]:
        tab_backtest()
    with tabs[3]:
        tab_optimize()
    with tabs[4]:
        tab_settings()

    st.divider()
    st.caption("NSE Options Trading Bot v3.3 | Thread-Safe Fix | Built for Indian Markets")

if __name__ == "__main__":
    main()