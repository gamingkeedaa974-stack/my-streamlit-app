import re
path = r"C:\Users\Imman\Kiwi_Bot_model\dashboard.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
# --- Check which functions exist ---
required = ["init_session_state", "_auth_headers", "_safe_get", "_safe_post", "_fetch_dashboard", "get_data",
            "render_login_screen", "render_sidebar", "render_status_bar", "main"]
found = {}
for func in required:
    found[func] = bool(re.search(rf'^def {func}\(', content, re.MULTILINE))
print("=== Function check ===")
for func, exists in found.items():
    status = "OK" if exists else "MISSING"
    print(f"  {func}: {status}")
missing = [f for f in required if not found[f]]
if not missing:
    print("\nAll functions present!")
    exit(0)
# --- Build the missing functions block ---
blocks = {}
blocks["_auth_headers"] = '''
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
'''
blocks["_fetch_dashboard"] = '''
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
'''
blocks["init_session_state"] = '''
# ---------- Session State Initialization ----------
def init_session_state():
    defaults = {
        "authenticated": False, "jwt_token": None, "user_id": None,
        "si_enabled": False, "si_toggled": False, "mode": "PAPER",
        "auto_strategy": False, "selected_strategy": "orb",
        "selected_symbols": ["NSE:NIFTY50-INDEX"], "show_nse_data": True,
        "bt_running": False, "bt_cancelled": False, "bt_strat": "orb",
        "bt_sym": "NIFTY50", "bt_days": 30, "bt_mode": "synthetic",
        "bt_source": "auto", "bt_csv": "", "opt_strat": "orb",
        "opt_mode": "adaptive", "opt_iters": 30, "opt_days": 60,
        "last_backtest_result": None, "last_compare_result": None,
        "last_opt_result": None, "kill_confirm": False,
        "live_broker": "Fyers", "live_key": "", "live_secret": "",
        "set_capital": 1000000, "set_lot": 25, "set_maxloss": 3,
        "set_risk": 1.0, "set_maxpos": 2, "set_si_interval": 5,
        "set_si_changes": 3, "set_telegram": False,
        "set_telegram_token": "", "set_telegram_chat": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
'''
# --- Insert missing functions BEFORE main() ---
main_idx = content.find("def main():")
if main_idx < 0:
    print("ERROR: def main() not found!")
    exit(1)
# Build insertion block - order matters
insert_order = ["_auth_headers", "_fetch_dashboard", "init_session_state"]
insert_text = "\n# === AUTO-REPAIRED MISSING FUNCTIONS ===\n"
for func_key in insert_order:
    if not found.get(func_key, False):
        insert_text += blocks[func_key]
        print(f"  Inserting: {func_key}")
insert_text += "# === END AUTO-REPAIR ===\n\n"
content = content[:main_idx] + insert_text + content[main_idx:]
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print(f"\nRepaired {len(insert_order)} missing function blocks before main()")
