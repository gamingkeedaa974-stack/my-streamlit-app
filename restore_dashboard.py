import shutil
import pathlib

# Step 1: Restore backup
src = pathlib.Path("dashboard.py.bak.v3.3")
dst = pathlib.Path("dashboard.py")
shutil.copy2(src, dst)
print("[1/4] Restored dashboard.py from backup")

# Step 2: Read and patch
text = dst.read_text(encoding="utf-8")

# Patch 2a: Add _auth_headers and fix _safe_get/_safe_post
old_helpers = '''# ---------- API Helpers ----------
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
        return None'''

new_helpers = '''# ---------- API Helpers ----------
def _auth_headers():
    token = st.session_state.get("jwt_token", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}

def _safe_get(endpoint: str, timeout: float = 3.0) -> Optional[Any]:
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
        return None'''

if old_helpers in text:
    text = text.replace(old_helpers, new_helpers)
    print("[2/4] Added _auth_headers, patched _safe_get/_safe_post")
else:
    print("[2/4] WARNING: Could not find API helpers block")

# Patch 2b: Add Fyers tab to tabs list
old_tabs = 'tabs = st.tabs(["\U0001f4ca Paper Trade", "\U0001f534 Live Trade", "\U0001f52c Intraday Backtest", "\u26a1 Optimize", "\u2699\ufe0f Settings"])'
new_tabs = 'tabs = st.tabs(["\U0001f4ca Paper Trade", "\U0001f534 Live Trade", "\U0001f52c Intraday Backtest", "\u26a1 Optimize", "\u2699\ufe0f Settings", "\U0001f310 Fyers Live"])'

if old_tabs in text:
    text = text.replace(old_tabs, new_tabs)
    print("[3/4] Added Fyers Live tab to tabs list")
else:
    # Fallback: try the literal string
    old_tabs2 = 'tabs = st.tabs(["📊 Paper Trade", "🔴 Live Trade", "🔬 Intraday Backtest", "⚡ Optimize", "⚙️ Settings"])'
    if old_tabs2 in text:
        new_tabs2 = 'tabs = st.tabs(["📊 Paper Trade", "🔴 Live Trade", "🔬 Intraday Backtest", "⚡ Optimize", "⚙️ Settings", "🌐 Fyers Live"])'
        text = text.replace(old_tabs2, new_tabs2)
        print("[3/4] Added Fyers Live tab (fallback match)")
    else:
        print("[3/4] WARNING: Could not find tabs definition")

# Patch 2c: Add tab_fyers_live() call after tabs[4]
old_tab4 = '''    with tabs[4]:
        tab_settings()

    st.divider()'''

new_tab4 = '''    with tabs[4]:
        tab_settings()
    with tabs[5]:
        tab_fyers_live()

    st.divider()'''

if old_tab4 in text:
    text = text.replace(old_tab4, new_tab4)
    print("[3/4] Added tab_fyers_live() call")
else:
    print("[3/4] WARNING: Could not find tabs[4] block")

# Patch 2d: Add tab_fyers_live function before main()
fyers_func = '''
# ═══════════════════════════════════════════════════════════
# FYERS LIVE TRADE TAB
# ═══════════════════════════════════════════════════════════
def tab_fyers_live():
    st.subheader("Fyers API - Live Trading")

    if "fyers_connected" not in st.session_state:
        st.session_state.fyers_connected = False
    if "fyers_app_id" not in st.session_state:
        st.session_state.fyers_app_id = ""

    # Step 1: Credentials
    with st.expander("Step 1: Fyers App Credentials", expanded=not st.session_state.fyers_connected):
        c1, c2 = st.columns(2)
        with c1:
            aid = st.text_input("App ID", value=st.session_state.fyers_app_id, key="fi_aid")
        with c2:
            sec = st.text_input("Secret Key", value=st.session_state.get("fyers_secret", ""), type="password", key="fi_sec")
        if st.button("Save Credentials", key="fi_save"):
            if aid and sec:
                r = _safe_post("/api/fyers/configure", {"app_id": aid, "secret_key": sec})
                if r and r.get("status") == "ok":
                    st.session_state.fyers_app_id = aid
                    st.session_state.fyers_secret = sec
                    st.success("Credentials saved!")
                else:
                    st.error("Failed to save")
            else:
                st.warning("Enter both fields")

    # Step 2: OAuth
    if st.session_state.fyers_app_id:
        with st.expander("Step 2: Authorize & Get Token"):
            if st.button("Generate Auth URL", key="fi_url"):
                r = _safe_get("/api/fyers/auth-url")
                if r and r.get("status") == "ok":
                    st.markdown(f"**[Click to Authorize]({r['auth_url']})**")
                    st.code(r["auth_url"])
                else:
                    st.error("Could not generate auth URL")
            acode = st.text_input("Paste auth_code from redirect URL", key="fi_ac")
            if st.button("Get Access Token", key="fi_tok"):
                if acode:
                    with st.spinner("Getting token..."):
                        r = _safe_post("/api/fyers/token", {"auth_code": acode})
                        if r and r.get("status") == "ok":
                            st.session_state.fyers_connected = True
                            st.success("Connected to Fyers!")
                            st.rerun()
                        else:
                            st.error(f"Token failed: {r}")
                else:
                    st.warning("Paste auth_code first")

    # Connected state
    if st.session_state.fyers_connected:
        st.success("Connected to Fyers (LIVE)")
        c1, c2, c3 = st.columns(3)
        with c1:
            pr = _safe_get("/api/fyers/profile")
            if pr and pr.get("status") == "ok":
                pd = pr.get("data", {}).get("data", {})
                st.metric("Account", pd.get("name", "N/A"))
        with c2:
            fu = _safe_get("/api/fyers/funds")
            if fu and fu.get("status") == "ok":
                eq = fu.get("data", {}).get("equity", {})
                st.metric("Margin", f"Rs {eq.get('intraday_payin', 0):,.0f}")
        with c3:
            su = _safe_get("/api/fyers/summary")
            if su and su.get("status") == "ok":
                st.metric("Positions", su.get("data", {}).get("open_positions", 0))

        st.subheader("Fyers Positions")
        po = _safe_get("/api/fyers/positions")
        if po and po.get("status") == "ok":
            nps = po.get("data", {}).get("data", {}).get("netPositions", [])
            if nps:
                st.dataframe(pd.DataFrame(nps), use_container_width=True)
            else:
                st.info("No open positions")
        with st.expander("Recent Orders"):
            orr = _safe_get("/api/fyers/orders")
            if orr and orr.get("status") == "ok":
                ob = orr.get("data", {}).get("data", {}).get("orderBook", [])
                if ob:
                    st.dataframe(pd.DataFrame(ob), use_container_width=True)
                else:
                    st.info("No orders yet")
    else:
        st.info("Complete Steps 1-2 to connect to Fyers for live trading.")

'''

# Insert before the MAIN section
main_marker = "# ═══════════════════════════════════════════════════════════\n# MAIN"
if main_marker in text:
    text = text.replace(main_marker, fyers_func + "# ═══════════════════════════════════════════════════════════\n# MAIN")
    print("[4/4] Added tab_fyers_live() function")
else:
    print("[4/4] WARNING: Could not find MAIN marker")

# Write as UTF-8 without BOM
dst.write_text(text, encoding="utf-8")
print("\nDone! dashboard.py restored + patched.")
