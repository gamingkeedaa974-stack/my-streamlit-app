path = r"C:\Users\Imman\Kiwi_Bot_model\dashboard.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
init_func = '''
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
'''
# Insert init_session_state right before "def main()"
content = content.replace("def main():", init_func + "def main():", 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("OK: init_session_state() restored before main()")
