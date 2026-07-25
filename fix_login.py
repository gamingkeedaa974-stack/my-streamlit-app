import re
path = r"C:\Users\Imman\Kiwi_Bot_model\dashboard.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
new_login = """def render_login_screen():
    st.markdown(\"\"\"
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
    \"\"\", unsafe_allow_html=True)
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
"""
# Find the function and replace it
idx = content.find("def render_login_screen():")
if idx < 0:
    print("ERROR: render_login_screen not found!")
    exit(1)
# Find the next top-level function/section after render_login_screen
rest = content[idx:]
next_match = re.search(r'\n(def [A-Z]\w+|class \w+|# \u2550{3,})', rest[10:])
if next_match:
    end = idx + 10 + next_match.start()
    content = content[:idx] + new_login + content[end:]
    print(f"Replaced render_login_screen ({end - idx} chars)")
else:
    print("WARNING: Could not find end marker, replacing to end of file")
    content = content[:idx] + new_login
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("OK: Login page rewritten with full-width inputs + spinner")
