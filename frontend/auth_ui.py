# frontend/auth_ui.py
import streamlit as st
import requests
from urllib.parse import unquote

st.set_page_config(page_title="OAuth callback", layout="centered")

st.header("OAuth callback")

# Debugging output. Remove or hide in production.
params = st.experimental_get_query_params()
st.write("Query params:", params)

# Accept common parameter names
auth_code = params.get("auth_code", [None])[0] or params.get("code", [None])[0]
returned_state = params.get("state", [None])[0]

# Retrieve expected state from session state if you saved it earlier
expected_state = st.session_state.get("oauth_state")

if auth_code:
    auth_code = unquote(auth_code)
    st.success("Received auth code. Exchanging for token...")

    backend_url = st.secrets.get("BACKEND_EXCHANGE_URL", "http://localhost:5000/exchange")
    redirect_uri = st.secrets.get("REDIRECT_URI", "http://localhost:8501/callback")

    # Optional state validation
    if expected_state and returned_state != expected_state:
        st.error("State mismatch. Aborting exchange.")
    else:
        try:
            resp = requests.post(
                backend_url,
                json={"code": auth_code, "redirect_uri": redirect_uri},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            st.success("Exchange succeeded")
            # In production do not show tokens; show minimal status
            st.json({"status": "ok", "exchange_response": data})
        except Exception as e:
            st.error(f"Exchange failed: {e}")
else:
    st.info("No auth code found. Click Generate Auth URL in your app to start.")
    if st.button("Generate Auth URL"):
        st.info("Use the generate_auth script to open the provider consent page.")
