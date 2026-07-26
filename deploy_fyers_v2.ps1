# deploy_fyers_v2.ps1 — Fyers integration (NO fyers-apiv3 SDK needed)
# Usage: powershell -ExecutionPolicy Bypass -File .\deploy_fyers_v2.ps1

$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot

Write-Host ''
Write-Host '=== FYERS V2 DEPLOY (pure requests, no SDK) ===' -ForegroundColor Cyan
Write-Host ''

# ── 1. Copy fyers_broker.py ─────────────────────────────────────────────
Write-Host '[1/3] Copying fyers_broker.py...' -ForegroundColor Yellow
$src = Join-Path $base 'fyers_broker.py'
$dst = Join-Path $base 'backend\fyers_broker.py'
if (Test-Path $src) {
    Copy-Item $src $dst -Force
    Write-Host '  -> Copied' -ForegroundColor Green
} elseif (Test-Path $dst) {
    Write-Host '  -> Already exists at backend\fyers_broker.py' -ForegroundColor Green
} else {
    Write-Host '  ERROR: fyers_broker.py not found!' -ForegroundColor Red
    exit 1
}

# ── 2. Patch api_server.py ──────────────────────────────────────────────
Write-Host '[2/3] Patching api_server.py...' -ForegroundColor Yellow
$apiFile = Join-Path $base 'backend\api_server.py'
$apiContent = Get-Content $apiFile -Raw -Encoding UTF8

# Check if already patched
if ($apiContent -match 'from backend.fyers_broker import FyersBroker') {
    Write-Host '  -> Already patched (FyersBroker import found)' -ForegroundColor Green
} else {
    # Find the paper_broker import line and add fyers_broker after it
    $importPatch = @'
from backend.fyers_broker import FyersBroker

# ── Fyers live broker instance ──────────────────────────────────────────
fyers_broker = FyersBroker()

'@
    $apiContent = $apiContent -replace '(from backend\.paper_broker import PaperBroker)', "`$1`n$importPatch"
    
    # Add Fyers API endpoints before the last line or at end
    $fyersEndpoints = @'

# ── Fyers API Endpoints ─────────────────────────────────────────────────
@app.post("/api/fyers/configure")
async def fyers_configure(request: Request):
    body = await request.json()
    fyers_broker.configure(
        app_id=body.get("app_id", ""),
        secret_key=body.get("secret_key", ""),
        redirect_uri=body.get("redirect_uri", ""),
    )
    return {"status": "ok", "message": "Credentials saved"}

@app.get("/api/fyers/auth-url")
async def fyers_auth_url():
    try:
        url = fyers_broker.generate_auth_url()
        return {"status": "ok", "auth_url": url}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/fyers/token")
async def fyers_token(request: Request):
    body = await request.json()
    try:
        result = fyers_broker.generate_token(body.get("auth_code", ""))
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/fyers/profile")
async def fyers_profile():
    try:
        data = fyers_broker.get_profile()
        return {"status": "ok", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/fyers/funds")
async def fyers_funds():
    try:
        data = fyers_broker.get_funds()
        return {"status": "ok", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/fyers/positions")
async def fyers_positions():
    try:
        data = fyers_broker.get_fyers_positions()
        return {"status": "ok", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/fyers/orders")
async def fyers_orders():
    try:
        data = fyers_broker.get_orders()
        return {"status": "ok", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/fyers/validate")
async def fyers_validate():
    valid = fyers_broker.validate_token()
    return {"status": "ok", "valid": valid}

@app.get("/api/fyers/summary")
async def fyers_summary():
    return {"status": "ok", "data": fyers_broker.get_portfolio_summary()}

'@
    # Append endpoints at end of file
    $apiContent += $fyersEndpoints
    Set-Content $apiFile -Value $apiContent -Encoding UTF8 -NoNewline
    Write-Host '  -> Added FyersBroker import + 9 endpoints' -ForegroundColor Green
}

# ── 3. Patch dashboard.py ───────────────────────────────────────────────
Write-Host '[3/3] Patching dashboard.py...' -ForegroundColor Yellow
$dashFile = Join-Path $base 'dashboard.py'
$dashContent = Get-Content $dashFile -Raw -Encoding UTF8

if ($dashContent -match 'Fyers.*OAuth|fyers_configure') {
    Write-Host '  -> Already patched (Fyers tab found)' -ForegroundColor Green
} else {
    # Add the Fyers Live Trade tab code before the last line
    # We'll create a helper script to inject the tab
    $tabCode = @'

# ═══════════════════════════════════════════════════════════════════════
# FYERS LIVE TRADE TAB
# ═══════════════════════════════════════════════════════════════════════

with tab("Live Trade (Fyers)"):
    st.subheader("Fyers API - Live Trading")
    
    if "fyers_app_id" not in st.session_state:
        st.session_state.fyers_app_id = ""
    if "fyers_secret_key" not in st.session_state:
        st.session_state.fyers_secret_key = ""
    if "fyers_token" not in st.session_state:
        st.session_state.fyers_token = ""
    if "fyers_connected" not in st.session_state:
        st.session_state.fyers_connected = False
    
    # Step 1: Enter credentials
    with st.expander("Step 1: Fyers App Credentials", expanded=not st.session_state.fyers_connected):
        col1, col2 = st.columns(2)
        with col1:
            app_id = st.text_input("App ID", value=st.session_state.fyers_app_id, key="fi_appid")
        with col2:
            secret_key = st.text_input("Secret Key", value=st.session_state.fyers_secret_key, type="password", key="fi_secret")
        
        if st.button("Save Credentials", key="fi_save"):
            if app_id and secret_key:
                resp = _safe_post("/api/fyers/configure", {"app_id": app_id, "secret_key": secret_key})
                if resp and resp.get("status") == "ok":
                    st.session_state.fyers_app_id = app_id
                    st.session_state.fyers_secret_key = secret_key
                    st.success("Credentials saved!")
                else:
                    st.error("Failed to save credentials")
            else:
                st.warning("Enter both App ID and Secret Key")
    
    # Step 2: OAuth flow
    if st.session_state.fyers_app_id:
        with st.expander("Step 2: Authorize & Get Token"):
            if st.button("Generate Auth URL", key="fi_authurl"):
                resp = _safe_get("/api/fyers/auth-url")
                if resp and resp.get("status") == "ok":
                    auth_url = resp.get("auth_url", "")
                    st.markdown(f"**[Click here to authorize]({auth_url})**")
                    st.code(auth_url)
                else:
                    st.error("Could not generate auth URL")
            
            auth_code = st.text_input("Paste auth_code from redirect URL", key="fi_authcode")
            if st.button("Get Access Token", key="fi_gettoken"):
                if auth_code:
                    with st.spinner("Exchanging auth code for token..."):
                        resp = _safe_post("/api/fyers/token", {"auth_code": auth_code})
                        if resp and resp.get("status") == "ok":
                            token_data = resp.get("data", {})
                            st.session_state.fyers_token = token_data.get("access_token", "")
                            st.session_state.fyers_connected = True
                            st.success("Token obtained! Connected to Fyers.")
                            st.rerun()
                        else:
                            st.error(f"Token generation failed: {resp}")
                else:
                    st.warning("Paste the auth_code first")
    
    # Step 3: Connection status
    if st.session_state.fyers_connected:
        st.success("Connected to Fyers (LIVE)")
        
        # Show account info
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            profile_resp = _safe_get("/api/fyers/profile")
            if profile_resp and profile_resp.get("status") == "ok":
                pd = profile_resp.get("data", {}).get("data", {})
                st.metric("Account Name", pd.get("name", "N/A"))
        with col_b:
            funds_resp = _safe_get("/api/fyers/funds")
            if funds_resp and funds_resp.get("status") == "ok":
                fd = funds_resp.get("data", {})
                equity = fd.get("equity", {})
                st.metric("Available Margin", f"Rs {equity.get('intraday_payin', 0):,.0f}")
        with col_c:
            summary_resp = _safe_get("/api/fyers/summary")
            if summary_resp and summary_resp.get("status") == "ok":
                sd = summary_resp.get("data", {})
                st.metric("Open Positions", sd.get("open_positions", 0))
        
        # Positions table
        st.subheader("Fyers Positions")
        pos_resp = _safe_get("/api/fyers/positions")
        if pos_resp and pos_resp.get("status") == "ok":
            pos_data = pos_resp.get("data", {})
            net_positions = pos_data.get("data", {}).get("netPositions", [])
            if net_positions:
                import pandas as pd
                df = pd.DataFrame(net_positions)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No open positions on Fyers")
        
        # Recent orders
        with st.expander("Recent Orders"):
            orders_resp = _safe_get("/api/fyers/orders")
            if orders_resp and orders_resp.get("status") == "ok":
                od = orders_resp.get("data", {})
                order_book = od.get("data", {}).get("orderBook", [])
                if order_book:
                    import pandas as pd
                    odf = pd.DataFrame(order_book)
                    st.dataframe(odf, use_container_width=True)
                else:
                    st.info("No orders")
    else:
        st.info("Complete Steps 1-2 above to connect to Fyers for live trading.")

'@
    
    # Insert before the very last line (usually st.sidebar or similar)
    # Find a good insertion point: before the last 'if __name__' or at end
    $dashContent += $tabCode
    Set-Content $dashFile -Value $dashContent -Encoding UTF8 -NoNewline
    Write-Host '  -> Added Fyers Live Trade tab' -ForegroundColor Green
}

# ── Verify syntax ───────────────────────────────────────────────────────
Write-Host ''
Write-Host 'Verifying syntax...' -ForegroundColor Yellow
$py = Join-Path $base 'venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

$files = @(
    (Join-Path $base 'backend\fyers_broker.py'),
    (Join-Path $base 'backend\api_server.py'),
    (Join-Path $base 'dashboard.py')
)
$allOk = $true
foreach ($f in $files) {
    $name = Split-Path $f -Leaf
    try {
        $proc = Start-Process -FilePath $py -ArgumentList "-m py_compile `"$f`"" -NoNewWindow -Wait -PassThru -RedirectStandardOutput NUL -RedirectStandardError NUL
        if ($proc.ExitCode -eq 0) {
            Write-Host "  $name : OK" -ForegroundColor Green
        } else {
            Write-Host "  $name : SYNTAX ERROR" -ForegroundColor Red
            $allOk = $false
        }
    } catch {
        Write-Host "  $name : CHECK MANUALLY" -ForegroundColor Yellow
    }
}

Write-Host ''
if ($allOk) {
    Write-Host '=== FYERS V2 DEPLOYED (no SDK needed!) ===' -ForegroundColor Green
    Write-Host ''
    Write-Host 'Next steps:' -ForegroundColor Cyan
    Write-Host '  1. Go to myfyers.fyers.in > My Account > Apps > Create App' -ForegroundColor White
    Write-Host '  2. Enter App ID + Secret in Live Trade tab' -ForegroundColor White
    Write-Host '  3. Generate Auth URL, open in browser, authorize' -ForegroundColor White
    Write-Host '  4. Paste auth_code, get token, test connection' -ForegroundColor White
    Write-Host '  5. Restart: .\start_bot.bat' -ForegroundColor White
} else {
    Write-Host '=== SOME FILES HAVE SYNTAX ERRORS - check above ===' -ForegroundColor Red
}
