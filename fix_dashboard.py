# fix_dashboard.py
import pathlib, re
f = pathlib.Path("dashboard.py")
raw = f.read_bytes()
# Strip UTF-8 BOM if present
if raw[:3] == b"\xef\xbb\xbf":
    raw = raw[3:]
txt = raw.decode("utf-8", errors="replace")
# --- Fix mojibake (double-encoding) ---
try:
    fixed = txt.encode("cp1252").decode("utf-8")
except Exception:
    fixed = txt
# Fallback: explicit emoji replacements
emoji_map = {
    "\u00e2\u0080\u0094": "\u2014",
    "\u00e2\u0082\u00b9": "\u20b9",
    "\u00e2\u0097\u008f": "\u25cf",
    "\u00e2\u009a\u00a1": "\u26a1",
    "\u00e2\u009a\u0099": "\u2699",
}
for bad, good in emoji_map.items():
    fixed = fixed.replace(bad, good)
# Fix 4-byte emoji mojibake patterns
import re as _re
def fix_moji(m):
    try:
        return bytes(m.group(0), "cp1252").decode("utf-8")
    except Exception:
        return m.group(0)
fixed = _re.sub(r"[\x80-\xff]{3,}", fix_moji, fixed)
# --- Remove broken Fyers tab appended at end ---
marker = "# \u2550" * 10
idx = fixed.find(marker)
# Find the SECOND occurrence (the appended block)
first = fixed.find(marker)
if first >= 0:
    second = fixed.find(marker, first + 10)
    if second >= 0:
        fixed = fixed[:second]
    else:
        fixed = fixed[:first]
# Also remove the with tab("Live Trade (Fyers)"): block if present
fixed = _re.sub(
    r'\n*with tab\("Live Trade \(Fyers\)"\):.*',
    "", fixed, flags=_re.DOTALL
)
# --- Insert Fyers tab inside the tabs list ---
# Find the tabs definition line
tab_match = _re.search(
    r'tabs\s*=\s*st\.tabs\(\s*\[(.*?)\]\s*\)', fixed, _re.DOTALL
)
if tab_match:
    tab_list = tab_match.group(1).strip()
    if "Live Trade (Fyers)" not in tab_list:
        # Add Fyers tab to the list
        new_list = tab_list.rstrip().rstrip(",").rstrip() + ',\n    "Live Trade (Fyers)",'
        old_def = tab_match.group(0)
        new_def = old_def.replace(tab_list, new_list, 1)
        fixed = fixed.replace(old_def, new_def, 1)
        print("[OK] Added Fyers tab to tabs list")
else:
    print("[WARN] Could not find tabs definition")
# --- Add Fyers tab content before the last meaningful section ---
fyers_tab = r'''
with tabs[-1]:
    st.subheader("Fyers API - Live Trading")
    if "fyers_app_id" not in st.session_state:
        st.session_state.fyers_app_id = ""
    if "fyers_secret_key" not in st.session_state:
        st.session_state.fyers_secret_key = ""
    if "fyers_connected" not in st.session_state:
        st.session_state.fyers_connected = False
    with st.expander("Step 1: App Credentials", expanded=not st.session_state.fyers_connected):
        c1, c2 = st.columns(2)
        with c1:
            aid = st.text_input("App ID", value=st.session_state.fyers_app_id, key="fi_aid")
        with c2:
            sec = st.text_input("Secret Key", value=st.session_state.fyers_secret_key, type="password", key="fi_sec")
        if st.button("Save Credentials", key="fi_save"):
            if aid and sec:
                r = _safe_post("/api/fyers/configure", {"app_id": aid, "secret_key": sec})
                if r and r.get("status") == "ok":
                    st.session_state.fyers_app_id = aid
                    st.session_state.fyers_secret_key = sec
                    st.success("Credentials saved!")
                else:
                    st.error("Failed to save credentials")
            else:
                st.warning("Enter both App ID and Secret Key")
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
                    st.warning("Paste the auth_code first")
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
                import pandas as _pd
                st.dataframe(_pd.DataFrame(nps), use_container_width=True)
            else:
                st.info("No open positions")
        with st.expander("Recent Orders"):
            orr = _safe_get("/api/fyers/orders")
            if orr and orr.get("status") == "ok":
                ob = orr.get("data", {}).get("data", {}).get("orderBook", [])
                if ob:
                    import pandas as _pd
                    st.dataframe(_pd.DataFrame(ob), use_container_width=True)
                else:
                    st.info("No orders yet")
    else:
        st.info("Complete Steps 1-2 above to connect to Fyers.")
'''
# Insert before the last tab block (find the last 'with tabs[' and insert before it)
last_tab = None
for m in _re.finditer(r'with tabs\[(\d+)\]', fixed):
    last_tab = m
if last_tab:
    pos = last_tab.start()
    fixed = fixed[:pos] + fyers_tab + "\n" + fixed[pos:]
    print("[OK] Fyers tab inserted inside tabs block")
else:
    # Fallback: append at end
    fixed += fyers_tab
    print("[WARN] Could not find tab blocks, appended at end")
# Write back as UTF-8 without BOM
f.write_bytes(fixed.encode("utf-8"))
print("[OK] dashboard.py saved (UTF-8 no BOM)")
