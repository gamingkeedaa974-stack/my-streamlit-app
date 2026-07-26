import json, urllib.request, sys
BASE='http://127.0.0.1:8000'
creds={'username':'admin','password':'password123'}
req=urllib.request.Request(BASE+'/api/login', data=json.dumps(creds).encode(), headers={'Content-Type':'application/json'})
try:
    with urllib.request.urlopen(req, timeout=5) as r:
        body=json.loads(r.read().decode())
        token=body.get('access_token')
        print('LOGIN OK, token present:', bool(token))
except Exception as e:
    print('LOGIN FAILED:', e)
    sys.exit(2)

if not token:
    print('No token returned')
    sys.exit(2)

req2=urllib.request.Request(BASE+'/api/status', headers={'Authorization':f'Bearer {token}'})
try:
    with urllib.request.urlopen(req2, timeout=5) as r:
        print('STATUS OK', r.status)
        print(r.read().decode())
except Exception as e:
    print('STATUS FAILED:', e)
    sys.exit(3)
