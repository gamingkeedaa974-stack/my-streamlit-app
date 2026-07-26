import urllib.request, sys, time
url='http://127.0.0.1:8000/api/status'
for i in range(8):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            print('OK', r.status)
            print(r.read().decode())
            sys.exit(0)
    except Exception as e:
        print('TRY', i+1, 'failed:', e)
        time.sleep(1)
print('FAILED')
sys.exit(1)
