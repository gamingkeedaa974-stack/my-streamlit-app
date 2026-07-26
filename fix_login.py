import pathlib

t = pathlib.Path("dashboard.py").read_text(encoding="utf-8")

# Fix 1: Login response check — API returns {"access_token": ...} not {"status": "ok"}
old_login = '''            r = _safe_post("/api/login", {"username": username, "password": password})
        if r and r.get("status") == "ok":
            st.session_state.jwt_token = r.get("token", "")
            st.success("Logged in!")'''
new_login = '''            r = _safe_post("/api/login", {"username": username, "password": password})
        if r and "access_token" in r:
            st.session_state.jwt_token = r["access_token"]
            st.success("Logged in!")'''

if old_login in t:
    t = t.replace(old_login, new_login)
    print("[1/2] Fixed login response check")
else:
    print("[1/2] WARNING: login block not found")

# Fix 2: Remove Register button — /api/register endpoint does not exist
old_reg = '''    if st.button("Register", key="login_reg"):
        r = _safe_post("/api/register", {"username": username, "password": password})
        if r and r.get("status") == "ok":
            st.success("Registered! Now login.")
        else:
            st.error("Registration failed")'''
new_reg = ''

if old_reg in t:
    t = t.replace(old_reg, new_reg)
    print("[2/2] Removed register button (endpoint does not exist)")
else:
    print("[2/2] WARNING: register block not found")

pathlib.Path("dashboard.py").write_text(t, encoding="utf-8")
print("Done!")