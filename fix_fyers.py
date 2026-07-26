# fix_fyers.py
import pathlib
# Fix 1: fyers_broker.py docstring
fb = pathlib.Path("backend/fyers_broker.py")
txt = fb.read_text(encoding="utf-8")
txt = txt.replace('"""\nFyersBroker', '"""FyersBroker', 1)
# Also fix any remaining broken opening
if txt.startswith('""'):
    txt = '"' + txt
fb.write_text(txt, encoding="utf-8")
print("[OK] fyers_broker.py docstring fixed")
# Fix 2: api_server.py import line
api = pathlib.Path("backend/api_server.py")
atxt = api.read_text(encoding="utf-8")
atxt = atxt.replace(
    "from backend.fyers_broker import FyersBroker, FyersConfig",
    "from backend.fyers_broker import FyersBroker"
)
api.write_text(atxt, encoding="utf-8")
print("[OK] api_server.py import fixed (removed FyersConfig)")
