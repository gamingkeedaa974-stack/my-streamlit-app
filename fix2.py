import pathlib
f = pathlib.Path("dashboard.py")
lines = f.read_text(encoding="utf-8").splitlines(True)
# Fix 1: indent "with tabs[4]:" back to 4 spaces
for i, line in enumerate(lines):
    if line.strip() == "with tabs[4]:" and not line.startswith("    "):
        lines[i] = "    with tabs[4]:\n"
        print(f"[OK] Fixed indentation at line {i+1}")
        break
# Fix 2: remove everything after "main()"
out = []
main_found = False
for line in lines:
    if main_found:
        continue
    out.append(line)
    if line.strip() == 'main()':
        main_found = True
print(f"[OK] Truncated {len(lines)-len(out)} lines after main()")
f.write_text("".join(out), encoding="utf-8")
print("[OK] Saved")
