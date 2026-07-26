import pathlib
f = pathlib.Path("dashboard.py")
text = f.read_text(encoding="utf-8")
def corrupted(original):
    return original.encode("utf-8").decode("cp1252")
# Use unicode escapes so PowerShell doesnt mangle them
emojis = [
    "\u25cf",      # black circle
    "\u20b9",      # rupee
    "\U0001f4ca",  # chart
    "\U0001f534",  # red circle
    "\u26a1",      # lightning
    "\u2699",      # gear
    "\U0001f4c8",  # chart up
    "\U0001f4c9",  # chart down
    "\U0001f4cb",  # clipboard
    "\u2014",      # em dash
    "\U0001f7e9",  # green square
    "\u2600",      # sun
    "\u26a0",      # warning
    "\ufe0f",      # variation selector
]
# Debug: show what corrupted forms look like
for e in emojis:
    c = corrupted(e)
    if c in text:
        print(f"FOUND: {e} -> corrupted={repr(c)}")
    else:
        # show what IS around the expected location
        print(f"MISS: {e} -> corrupted={repr(c)}")
# Also try the full file encode/decode
try:
    fixed = text.encode("cp1252").decode("utf-8")
    if fixed != text:
        f.write_text(fixed, encoding="utf-8")
        print("\nFull cp1252 roundtrip FIXED the file")
    else:
        print("\nRoundtrip produced identical text - no double-encoding detected")
except UnicodeEncodeError as ex:
    bad_char = text[ex.start:ex.start+1]
    print(f"\nRoundtrip failed at pos {ex.start}: {repr(bad_char)} (U+{ord(bad_char):04X})")
    print("This char is not in cp1252 - likely from a previous fix script")
    # Remove the bad char and try again
    cleaned = text.replace(bad_char, "")
    try:
        fixed = cleaned.encode("cp1252").decode("utf-8")
        f.write_text(fixed, encoding="utf-8")
        print("Fixed after removing non-cp1252 chars")
    except Exception as e2:
        print(f"Still failed: {e2}")
