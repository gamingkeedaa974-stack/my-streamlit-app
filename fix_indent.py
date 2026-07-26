# fix_indent.py
import pathlib, re
f = pathlib.Path("dashboard.py")
txt = f.read_text(encoding="utf-8")
# Remove the wrongly-indented Fyers tab block
pattern = r'\nwith tabs\[-1\]:.*?(?=\n(?:with tabs|\Z))'
m = re.search(pattern, txt, re.DOTALL)
if m:
    txt = txt[:m.start()] + "\n" + txt[m.end():]
    print("[OK] Removed wrongly-indented Fyers tab")
else:
    print("[WARN] Could not find Fyers tab to remove")
# Remove "Live Trade (Fyers)" from tabs list if it was added
txt = txt.replace(',\n    "Live Trade (Fyers)",', "")
print("[OK] Removed Fyers from tabs list")
f.write_text(txt, encoding="utf-8")
print("[OK] Saved. Dashboard restored to working state.")
