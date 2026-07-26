# backend/exchange.py
from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

CLIENT_ID = os.environ.get("FYERS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("FYERS_CLIENT_SECRET")
TOKEN_URL = "https://api-t1.fyers.in/api/v3/token"  # confirm with provider docs

if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("Set FYERS_CLIENT_ID and FYERS_CLIENT_SECRET environment variables")

@app.route("/exchange", methods=["POST"])
def exchange():
    data = request.json or {}
    code = data.get("code")
    redirect_uri = data.get("redirect_uri")
    if not code or not redirect_uri:
        return jsonify({"error": "missing code or redirect_uri"}), 400

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": redirect_uri
    }

    try:
        r = requests.post(TOKEN_URL, data=payload, timeout=15)
    except Exception as e:
        return jsonify({"error": "request failed", "details": str(e)}), 502

    if r.status_code != 200:
        return jsonify({"error": "token exchange failed", "status_code": r.status_code, "details": r.text}), r.status_code

    tokens = r.json()
    # TODO: store tokens securely (DB or secrets manager)
    return jsonify({"status": "ok", "tokens": tokens})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
