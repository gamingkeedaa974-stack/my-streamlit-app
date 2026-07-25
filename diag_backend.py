import requests, json, time
print("=== Backend Health Check ===")
base = "http://localhost:8000"
# 1. Can we reach the backend at all?
try:
    r = requests.get(f"{base}/docs", timeout=3)
    print(f"  Backend reachable: YES (status {r.status_code})")
except:
    print(f"  Backend reachable: NO - backend is not running!")
    exit(1)
# 2. Login and get JWT
try:
    r = requests.post(f"{base}/api/login", json={"username": "admin", "password": "password123"}, timeout=5)
    if r.status_code == 200:
        token = r.json()["access_token"]
        print(f"  Login: OK (token: {token[:30]}...)")
    else:
        print(f"  Login: FAILED (status {r.status_code}, body: {r.text[:200]})")
        exit(1)
except Exception as e:
    print(f"  Login: ERROR {e}")
    exit(1)
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
# 3. Test /api/dashboard
try:
    r = requests.get(f"{base}/api/dashboard", headers=headers, timeout=5)
    print(f"  /api/dashboard: status {r.status_code}")
    if r.status_code != 200:
        print(f"    Body: {r.text[:300]}")
except Exception as e:
    print(f"  /api/dashboard: ERROR {e}")
# 4. Test /api/backtest (this is what the UI calls)
try:
    r = requests.post(f"{base}/api/backtest", headers=headers, json={
        "strategy": "orb", "symbol": "NIFTY50", "days": 5, "mode": "synthetic"
    }, timeout=30)
    print(f"  /api/backtest: status {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"    Trades: {data.get('total_trades', 'N/A')}, PnL: {data.get('total_pnl_pct', 'N/A')}%")
    else:
        print(f"    ERROR BODY: {r.text[:500]}")
except Exception as e:
    print(f"  /api/backtest: ERROR {e}")
print("\nDone.")
