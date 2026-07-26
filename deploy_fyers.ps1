# deploy_fyers.ps1
# Deploys Fyers API integration: broker + API endpoints + dashboard UI
# Run from: C:\Users\Imman\Kiwi_Bot_model\

$base = "C:\Users\Imman\Kiwi_Bot_model"
$backend = "$base\backend"

# ═══════════════════════════════════════════════════════════════
# STEP 1: Copy fyers_broker.py
# ═══════════════════════════════════════════════════════════════
Write-Host "[1/4] Copying fyers_broker.py..." -ForegroundColor Cyan
if (Test-Path "$base\fyers_broker.py") {
    Copy-Item "$base\fyers_broker.py" "$backend\fyers_broker.py" -Force
    Write-Host "  -> Copied" -ForegroundColor Green
} else {
    Write-Host "  -> ERROR: fyers_broker.py not found in $base" -ForegroundColor Red
    Write-Host "  -> Download it from the chat and place it in $base" -ForegroundColor Yellow
}

# ═══════════════════════════════════════════════════════════════
# STEP 2: Install fyers-apiv3 if not present
# ═══════════════════════════════════════════════════════════════
Write-Host "[2/4] Checking fyers-apiv3..." -ForegroundColor Cyan
$pkg = python -c "import importlib.util; print('yes') if importlib.util.find_spec('fyers_apiv3') else print('no')"
if ($pkg.Trim() -eq 'no') {
    Write-Host "  -> Installing fyers-apiv3..." -ForegroundColor Yellow
    pip install fyers-apiv3
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  -> Installed" -ForegroundColor Green
    } else {
        Write-Host "  -> Install failed. Run manually: pip install fyers-apiv3" -ForegroundColor Red
    }
} else {
    Write-Host "  -> Already installed" -ForegroundColor Green
}

# ═══════════════════════════════════════════════════════════════
# STEP 3: Patch api_server.py — add Fyers endpoints
# ═══════════════════════════════════════════════════════════════
Write-Host "[3/4] Patching api_server.py..." -ForegroundColor Cyan

$apiFile = "$backend\api_server.py"
$api = Get-Content $apiFile -Raw

# Add import for FyersBroker
if ($api -notmatch 'from backend.fyers_broker import FyersBroker') {
    $api = $api.Replace(
        'from backend.paper_broker import PaperBroker',
        "from backend.paper_broker import PaperBroker`nfrom backend.fyers_broker import FyersBroker, FyersConfig"
    )
    Write-Host "  -> Added FyersBroker import" -ForegroundColor Green
} else {
    Write-Host "  -> Import already exists" -ForegroundColor Yellow
}

# Add Fyers API endpoints before WebSocket
$fyersEndpoints = @'

# ---------- Fyers API Endpoints ----------
@app.get("/api/fyers/status")
async def fyers_status(request: Request):
    session = await session_manager.get_session(request.state.user_id)
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker, FyersConfig
        session._fyers_broker = FyersBroker()
    return session._fyers_broker.get_connection_status()

@app.post("/api/fyers/save-creds")
async def fyers_save_creds(request: Request):
    body = await request.json()
    from backend.fyers_broker import FyersBroker, FyersConfig
    config = FyersConfig.load()
    config.app_id = body.get("app_id", "")
    config.secret_key = body.get("secret_key", "")
    config.redirect_uri = body.get("redirect_uri", "http://localhost:8501")
    config.save()
    session = await session_manager.get_session(request.state.user_id)
    session._fyers_broker = FyersBroker(fyers_config=config)
    return {"status": "saved", "has_app_id": bool(config.app_id)}

@app.post("/api/fyers/auth-url")
async def fyers_auth_url(request: Request):
    session = await session_manager.get_session(request.state.user_id)
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker, FyersConfig
        session._fyers_broker = FyersBroker()
    url = session._fyers_broker.generate_auth_url()
    if url:
        return {"auth_url": url}
    return JSONResponse(status_code=400, content={"error": session._fyers_broker.last_error})

@app.post("/api/fyers/auth-token")
async def fyers_auth_token(request: Request):
    body = await request.json()
    auth_code = body.get("auth_code", "")
    session = await session_manager.get_session(request.state.user_id)
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker, FyersConfig
        session._fyers_broker = FyersBroker()
    result = await session._fyers_broker.exchange_auth_code(auth_code)
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result

@app.post("/api/fyers/refresh-token")
async def fyers_refresh_token(request: Request):
    session = await session_manager.get_session(request.state.user_id)
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker, FyersConfig
        session._fyers_broker = FyersBroker()
    result = await session._fyers_broker.refresh_access_token()
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result

@app.post("/api/fyers/test")
async def fyers_test(request: Request):
    session = await session_manager.get_session(request.state.user_id)
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker, FyersConfig
        session._fyers_broker = FyersBroker()
    broker = session._fyers_broker
    if not broker.is_connected:
        # Try refresh first
        if broker.config.refresh_token:
            refresh_result = await broker.refresh_access_token()
            if not refresh_result["success"]:
                return JSONResponse(status_code=400, content={"error": broker.last_error, "refresh_result": refresh_result})
        else:
            return JSONResponse(status_code=400, content={"error": broker.last_error})
    profile = broker.get_profile()
    if profile:
        return {"status": "connected", "profile": profile.get("data", {})}
    return JSONResponse(status_code=400, content={"error": "Connected but profile fetch failed"})

'@

if ($api -notmatch 'def fyers_status') {
    $api = $api.Replace('# ---------- WebSocket ----------', $fyersEndpoints + '# ---------- WebSocket ----------')
    Write-Host "  -> Added 6 Fyers endpoints" -ForegroundColor Green
} else {
    Write-Host "  -> Fyers endpoints already exist" -ForegroundColor Yellow
}

Set-Content $apiFile $api -Encoding UTF8

# ═══════════════════════════════════════════════════════════════
# STEP 4: Patch dashboard.py — replace Live Trade tab
# ═══════════════════════════════════════════════════════════════
Write-Host "[4/4] Patching dashboard.py..." -ForegroundColor Cyan

$dashFile = "$base\dashboard.py"
$dash = Get-Content $dashFile -Raw

$newLiveTab = @'
def tab_live_trade():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">Fyers Live Trading</div>', unsafe_allow_html=True)

    # ── Fetch Fyers status ──
    fyers_status = _safe_get("/api/fyers/status") or {}
    connected = fyers_status.get("connected", False)
    has_token = fyers_status.get("token_valid", False)
    token_expiry = fyers_status.get("token_expiry", "")
    error = fyers_status.get("error", "")
    profile_name = fyers_status.get("profile_name", "")
    fyers_id = fyers_status.get("fyers_id", "")

    # ── Connection Status Banner ──
    if connected:
        st.success(f"Connected as {profile_name} ({fyers_id})")
        if token_expiry:
            exp_dt = datetime.fromisoformat(token_expiry) if isinstance(token_expiry, str) else None
            if exp_dt:
                remaining = exp_dt - datetime.now()
                if remaining.total_seconds() < 3600:
                    st.warning(f"Token expires in {int(remaining.total_seconds()/60)} min. Click Refresh Token.")
                else:
                    st.caption(f"Token valid until {exp_dt.strftime('%H:%M %d-%b')}")
    elif has_token:
        st.warning("Token stored but may be expired. Try Refresh Token.")
    else:
        st.info("Not connected. Follow steps below.")

    if error and not connected:
        st.error(f"Error: {error}")

    st.divider()

    # ── STEP 1: API Credentials ──
    st.subheader("Step 1: Fyers API Credentials")
    st.caption("Get these from myfyers.fyers.in > My Account > Apps")
    c1, c2 = st.columns(2)
    with c1:
        f_app_id = st.text_input("App ID (Client ID)", value=st.session_state.get("live_key", ""), key="fyers_app_id")
    with c2:
        f_secret = st.text_input("Secret Key", type="password", value=st.session_state.get("live_secret", ""), key="fyers_secret")
    f_redirect = st.text_input("Redirect URI", value="http://localhost:8501", key="fyers_redirect")

    cols = st.columns([1, 1])
    with cols[0]:
        if st.button("Save Credentials", use_container_width=True, key="fyers_save_creds"):
            payload = {"app_id": f_app_id, "secret_key": f_secret, "redirect_uri": f_redirect}
            result = _safe_post("/api/fyers/save-creds", payload)
            if result and result.get("status") == "saved":
                st.success("Credentials saved!")
                st.rerun()
            else:
                st.error("Failed to save")
    with cols[1]:
        st.caption("Credentials are stored in fyers_config.json")

    st.divider()

    # ── STEP 2: OAuth Authorization ──
    st.subheader("Step 2: Authorize (OAuth)")
    if not f_app_id or not f_secret:
        st.warning("Save API credentials first (Step 1)")
    else:
        cols = st.columns([1, 1])
        with cols[0]:
            if st.button("Generate Auth URL", type="primary", use_container_width=True, key="fyers_gen_url"):
                result = _safe_post("/api/fyers/auth-url", {})
                if result and "auth_url" in result:
                    st.session_state.fyers_auth_url = result["auth_url"]
                    st.rerun()
                else:
                    st.error(result.get("error", "Failed to generate URL") if result else "Backend error")
        with cols[1]:
            auth_url = st.session_state.get("fyers_auth_url", "")
            if auth_url:
                st.text_input("Auth URL", value=auth_url, key="fyers_url_display", label_visibility="collapsed")
                if st.button("Open in Browser", use_container_width=True, key="fyers_open_url"):
                    import webbrowser
                    webbrowser.open(auth_url)
                    st.info("Login to Fyers and authorize. You will be redirected back.")

    # ── STEP 3: Paste Auth Code ──
    if f_app_id and f_secret:
        st.divider()
        st.subheader("Step 3: Get Access Token")
        st.caption("After authorizing in browser, you will be redirected to a URL like:")
        st.code("http://localhost:8501/?auth_code=XXXXX", language="text")
        st.caption("Copy the auth_code value and paste below:")

        auth_code = st.text_input("Auth Code", placeholder="Paste the auth_code from the redirect URL", key="fyers_auth_code")
        cols = st.columns([1, 1])
        with cols[0]:
            if st.button("Get Token", type="primary", use_container_width=True, key="fyers_get_token"):
                if auth_code:
                    result = _safe_post("/api/fyers/auth-token", {"auth_code": auth_code})
                    if result and result.get("success"):
                        st.success(result.get("message", "Token obtained!"))
                        st.session_state.fyers_auth_url = ""
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(result.get("message", "Failed") if result else "Backend error")
                else:
                    st.warning("Paste the auth_code first")
        with cols[1]:
            if st.button("Refresh Token", use_container_width=True, key="fyers_refresh"):
                result = _safe_post("/api/fyers/refresh-token", {})
                if result and result.get("success"):
                    st.success("Token refreshed!")
                    st.rerun()
                else:
                    st.error(result.get("message", "Refresh failed") if result else "Backend error")

    # ── STEP 4: Test Connection ──
    if has_token or connected:
        st.divider()
        st.subheader("Step 4: Test Connection")
        if st.button("Test Connection", use_container_width=True, key="fyers_test_conn"):
            result = _safe_post("/api/fyers/test", {})
            if result and result.get("status") == "connected":
                profile = result.get("profile", {})
                st.success(f"Connected! Name: {profile.get('name', 'N/A')}, ID: {profile.get('fyers_id', 'N/A')}")
            else:
                err = result.get("error", "Unknown error") if result else "No response"
                st.error(f"Connection failed: {err}")

    st.divider()
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Requirements Card ──
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">Requirements</div>', unsafe_allow_html=True)
    st.markdown("""
    1. **Fyers Developer Account** at [myfyers.fyers.in](https://myfyers.fyers.in)
    2. **Create App** to get App ID + Secret Key
    3. **Algo trading enabled** on your Fyers account
    4. **TOTP 2FA** setup
    5. **Minimum Capital**: ~1.5L for 1 NIFTY lot (MIS margin)
    6. **Token refreshes daily** — re-authorize if refresh_token expires (after 30 days)
    """)
    st.markdown('</div>', unsafe_allow_html=True)

'@

# Replace the old live trade tab
$oldLiveTabStart = 'def tab_live_trade():'
$oldLiveTabEnd = 'def tab_backtest():'

$startIdx = $dash.IndexOf($oldLiveTabStart)
$endIdx = $dash.IndexOf($oldLiveTabEnd)

if ($startIdx -ge 0 -and $endIdx -gt $startIdx) {
    $dash = $dash.Substring(0, $startIdx) + $newLiveTab + $dash.Substring($endIdx)
    Write-Host "  -> Replaced Live Trade tab with Fyers OAuth flow" -ForegroundColor Green
} else {
    Write-Host "  -> Could not find Live Trade tab boundaries" -ForegroundColor Red
}

Set-Content $dashFile $dash -Encoding UTF8

# ═══════════════════════════════════════════════════════════════
# VERIFY
# ═══════════════════════════════════════════════════════════════
Write-Host "" -ForegroundColor White
Write-Host "Verifying syntax..." -ForegroundColor Cyan
python -c "import py_compile; py_compile.compile(r'$backend\api_server.py', doraise=True); py_compile.compile(r'$base\dashboard.py', doraise=True); py_compile.compile(r'$backend\fyers_broker.py', doraise=True); print('All 3 files: OK')"

Write-Host "" -ForegroundColor White
Write-Host "=== FYERS INTEGRATION DEPLOYED ===" -ForegroundColor Green
Write-Host "" -ForegroundColor White
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. pip install fyers-apiv3  (if not auto-installed)" -ForegroundColor White
Write-Host "  2. Go to myfyers.fyers.in > My Account > Apps > Create App" -ForegroundColor White
Write-Host "  3. Enter App ID + Secret in Live Trade tab" -ForegroundColor White
Write-Host "  4. Generate Auth URL, open in browser, authorize" -ForegroundColor White
Write-Host "  5. Paste auth_code, get token, test connection" -ForegroundColor White
Write-Host "  6. Restart: .\start_bot.bat" -ForegroundColor White
Write-Host "" -ForegroundColor White
