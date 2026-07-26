"""
patch_dashboard.py — Restore dashboard.py from v3.3 backup and add:
  1. JWT auth (login page, _auth_headers, Bearer tokens)
  2. Fyers Live tab

Usage:  python patch_dashboard.py
        (run from Kiwi_Bot_model directory)
"""
import pathlib, shutil, sys

BACKUP = pathlib.Path("dashboard.py.bak.v3.3")
TARGET = pathlib.Path("dashboard.py")

if not BACKUP.exists():
    print(f"ERROR: Backup not found at {BACKUP}")
    print("Place this script next to dashboard.py.bak.v3.3 and run again.")
    sys.exit(1)

# ── Step 1: Copy clean backup ──────────────────────────────────
shutil.copy2(BACKUP, TARGET)
text = TARGET.read_text(encoding="utf-8")
print("[1/7] Restored dashboard.py from backup (clean UTF-8, no BOM)")

# ── Step 2: Add _auth_headers() before _safe_get ───────────────
auth_func = (
    'def _auth_headers():\n'
    '    token = st.session_state.get("jwt_token", "")\n'
    '    if token:\n'
    '        return {"Authorization": f"Bearer {token}"}\n'
    '    return {}\n\n'
)

old = 'def _safe_get(endpoint: str, timeout: float = 3.0) -> Optional[Any]:'
if old in text:
    text = text.replace(old, auth_func + old)
    print("[2/7] Added _auth_headers() function")
else:
    print("[2/7] WARNING: _safe_get signature not found")

# ── Step 3: Patch _safe_get to include auth headers ─────────────
old_get = 'resp = requests.get(f"{API_URL}{endpoint}", timeout=timeout)'
new_get = 'resp = requests.get(f"{API_URL}{endpoint}", headers=_auth_headers(), timeout=timeout)'
if old_get in text:
    text = text.replace(old_get, new_get)
    print("[3/7] Patched _safe_get with auth headers")
else:
    print("[3/7] WARNING: _safe_get body not found")

# ── Step 4: Patch _safe_post to include auth headers ────────────
old_post = 'resp = requests.post(f"{API_URL}{endpoint}", json=payload, timeout=timeout)'
new_post = 'resp = requests.post(f"{API_URL}{endpoint}", json=payload, headers=_auth_headers(), timeout=timeout)'
if old_post in text:
    text = text.replace(old_post, new_post)
    print("[4/7] Patched _safe_post with auth headers")
else:
    print("[4/7] WARNING: _safe_post body not found")

# ── Step 5: Add render_login() before render_sidebar() ──────────
login_func = '''def render_login():
    st.title("NSE Options Trading Bot")
    st.subheader("Login")
    username = st.text_input("Username", key="login_user")
    password = st.text_input("Password", type="password", key="login_pass")
    if st.button("Login", type="primary", use_container_width=True):
        r = _safe_post("/api/login", {"username": username, "password": password})
        if r and r.get("status") == "ok":
            st.session_state.jwt_token = r.get("token", "")
            st.success("Logged in!")
            st.rerun()
        else:
            st.error("Invalid username or password")
    if st.button("Register", key="login_reg"):
        r = _safe_post("/api/register", {"username": username, "password": password})
        if r and r.get("status") == "ok":
            st.success("Registered! Now login.")
        else:
            st.error("Registration failed")

'''

old_sidebar = 'def render_sidebar():'
if old_sidebar in text:
    text = text.replace(old_sidebar, login_func + old_sidebar)
    print("[5/7] Added render_login() function")
else:
    print("[5/7] WARNING: render_sidebar() not found")

# ── Step 6: Add login gate at start of main() ──────────────────
old_main = 'def main():\n    init_session_state()\n    render_sidebar()'
new_main = (
    'def main():\n'
    '    if not st.session_state.get("jwt_token"):\n'
    '        render_login()\n'
    '        return\n'
    '    init_session_state()\n'
    '    render_sidebar()'
)
if old_main in text:
    text = text.replace(old_main, new_main)
    print("[6/7] Added login gate in main()")
else:
    print("[6/7] WARNING: main() start not found")

# ── Step 7a: Add Fyers Live tab to tabs list ───────────────────
old_tabs = 'st.tabs(["\U0001f4ca Paper Trade", "\U0001f534 Live Trade", "\U0001f52c Intraday Backtest", "\u26a1 Optimize", "\u2699\ufe0f Settings"])'
new_tabs = 'st.tabs(["\U0001f4ca Paper Trade", "\U0001f534 Live Trade", "\U0001f52c Intraday Backtest", "\u26a1 Optimize", "\u2699\ufe0f Settings", "\U0001f310 Fyers Live"])'

if old_tabs in text:
    text = text.replace(old_tabs, new_tabs)
    print("[7a/7] Added Fyers Live tab label (unicode escape)")
else:
    # Try literal emoji match
    old_tabs2 = 'st.tabs(["\U0001f4ca Paper Trade", "\U0001f534 Live Trade", "\U0001f52c Intraday Backtest", "\u26a1 Optimize", "\u2699\ufe0f Settings"])'
    if old_tabs2 in text:
        new_tabs2 = 'st.tabs(["\U0001f4ca Paper Trade", "\U0001f534 Live Trade", "\U0001f52c Intraday Backtest", "\u26a1 Optimize", "\u2699\ufe0f Settings", "\U0001f310 Fyers Live"])'
        text = text.replace(old_tabs2, new_tabs2)
        print("[7a/7] Added Fyers Live tab label (literal)")
    else:
        print("[7a/7] WARNING: tabs definition not found")

# ── Step 7b: Add with tabs[5] after tabs[4] ───────────────────
old_tab4 = '    with tabs[4]:\n        tab_settings()\n\n    st.divider()'
new_tab4 = '    with tabs[4]:\n        tab_settings()\n    with tabs[5]:\n        tab_fyers_live()\n\n    st.divider()'
if old_tab4 in text:
    text = text.replace(old_tab4, new_tab4)
    print("[7b/7] Added tab_fyers_live() call")
else:
    print("[7b/7] WARNING: tabs[4] block not found")

# ── Step 7c: Add tab_fyers_live() function before MAIN ────────
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
    with st.expander("Step 1: App Credentials", expanded=not st.session_state.fyers_connected):
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
    if st.session_state.fyers_app_id:
        with st.expander("Step 2: Authorize & Get Token"):
            if st.button("Generate Auth URL", key="fi_url"):
                r = _safe_get("/api/fyers/auth-url")
                if r and r.get("status") == "ok":
                    url = r.get("auth_url", "")
                    st.markdown(f"**[Click to Authorize]({url})**")
                    st.code(url)
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
    if st.session_state.fyers_connected:
        st.success("Connected to Fyers (LIVE)")
        c1, c2, c3 = st.columns(3)
        with c1:
            pr = _safe_get("/api/fyers/profile")
            if pr and pr.get("status") == "ok":
                st.metric("Account", pr.get("data",{}).get("data",{}).get("name","N/A"))
        with c2:
            fu = _safe_get("/api/fyers/funds")
            if fu and fu.get("status") == "ok":
                eq = fu.get("data",{}).get("equity",{})
                margin = eq.get("intraday_payin", 0)
                st.metric("Margin", f"Rs {margin:,.0f}")
        with c3:
            su = _safe_get("/api/fyers/summary")
            if su and su.get("status") == "ok":
                st.metric("Positions", su.get("data",{}).get("open_positions",0))
        st.subheader("Fyers Positions")
        po = _safe_get("/api/fyers/positions")
        if po and po.get("status") == "ok":
            nps = po.get("data",{}).get("data",{}).get("netPositions",[])
            if nps:
                st.dataframe(pd.DataFrame(nps), use_container_width=True)
            else:
                st.info("No open positions")
        with st.expander("Recent Orders"):
            orr = _safe_get("/api/fyers/orders")
            if orr and orr.get("status") == "ok":
                ob = orr.get("data",{}).get("data",{}).get("orderBook",[])
                if ob:
                    st.dataframe(pd.DataFrame(ob), use_container_width=True)
                else:
                    st.info("No orders yet")
    else:
        st.info("Complete Steps 1-2 to connect to Fyers for live trading.")

'''

main_marker = '# ═══════════════════════════════════════════════════════════\n# MAIN\n# ═══════════════════════════════════════════════════════════'
if main_marker in text:
    text = text.replace(main_marker, fyers_func + main_marker)
    print("[7c/7] Added tab_fyers_live() function")
else:
    print("[7c/7] WARNING: MAIN marker not found")

# ── Final: Write as UTF-8 without BOM ─────────────────────────
TARGET.write_text(text, encoding="utf-8")
print(f"\nDone! {TARGET} restored + patched successfully.")
print(f"File size: {TARGET.stat().st_size:,} bytes")