# scripts/run_backend.ps1
$env:FYERS_CLIENT_ID = "52BLZ2KYCL-100"  # replace or set externally
$env:FYERS_CLIENT_SECRET = "YOUR_CLIENT_SECRET"  # replace or set externally
python -m pip install -r requirements-backend.txt  # optional
python backend/exchange.py
