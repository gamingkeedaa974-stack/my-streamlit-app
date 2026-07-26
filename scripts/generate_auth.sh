#!/usr/bin/env bash
CLIENT_ID="${FYERS_CLIENT_ID}"
REDIRECT_URI="${REDIRECT_URI}"

if [ -z "$CLIENT_ID" ] || [ -z "$REDIRECT_URI" ]; then
  echo "Set FYERS_CLIENT_ID and REDIRECT_URI environment variables first."
  exit 1
fi

STATE=$(openssl rand -hex 12)
echo "$STATE" > .oauth_state

URL="https://api-t1.fyers.in/api/v3/generate-authcode?client_id=${CLIENT_ID}&redirect_uri=$(python - <<PY
import urllib.parse, sys
print(urllib.parse.quote(sys.argv[1], safe=''))
PY
 "$REDIRECT_URI")&response_type=code&state=${STATE}"

echo "Opening $URL"
xdg-open "$URL" || open "$URL"
