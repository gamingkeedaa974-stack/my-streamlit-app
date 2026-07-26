import pathlib, re
f = pathlib.Path("dashboard.py")
text = f.read_text(encoding="utf-8")
# Fix double-encoding: original UTF-8 bytes were misread as latin-1,
# then written back as UTF-8. Reverse: encode as latin-1, decode as UTF-8.
result = []
buf = []
for ch in text:
    if ord(ch) <= 255:
        buf.append(ch)
    else:
        if buf:
            chunk = "".join(buf)
            try:
                result.append(chunk.encode("latin-1").decode("utf-8"))
            except Exception:
                result.append(chunk)
            buf = []
        result.append(ch)
if buf:
    chunk = "".join(buf)
    try:
        result.append(chunk.encode("latin-1").decode("utf-8"))
    except Exception:
        result.append(chunk)
fixed = "".join(result)
changed = fixed != text
f.write_text(fixed, encoding="utf-8")
print(f"Changed: {changed}")
if changed:
    print("Emojis fixed!")
else:
    print("No change - dumping sample for debug:")
    for m in re.finditer(r"[\u0080-\u00ff]{2,}", text):
        pos = m.start()
        snippet = text[pos:pos+20]
        raw = snippet.encode("utf-8")
        print(f"  pos={pos}: {repr(snippet)} bytes={raw[:30].hex()}")
