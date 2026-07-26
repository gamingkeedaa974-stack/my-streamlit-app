import pathlib, re, unicodedata
f = pathlib.Path("dashboard.py")
text = f.read_text(encoding="utf-8")
# Normalize: decompose accented chars into base letter + combining mark
text = unicodedata.normalize("NFKD", text)
# Strip all combining marks
text = re.sub(r"[\u0300-\u036f]", "", text)
# Map known symbols to ASCII
text = text.replace("\u20b9", "Rs.")  # rupee
text = text.replace("\u2014", "-")    # em dash
text = text.replace("\u2013", "-")    # en dash
text = text.replace("\u2022", "*")    # bullet
text = text.replace("\u25cf", "*")    # black circle
text = text.replace("\u25cb", "o")    # white circle
# Remove ALL remaining non-ASCII
clean = text.encode("ascii", "ignore").decode("ascii")
# Show what was removed
removed = len(text) - len(clean)
print(f"Removed {removed} non-ASCII characters")
f.write_text(clean, encoding="utf-8")
print("Done - dashboard is now pure ASCII")
