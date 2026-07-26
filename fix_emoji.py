import pathlib
f = pathlib.Path("dashboard.py")
text = f.read_text(encoding="utf-8")
def corrupted(original):
    return original.encode("utf-8").decode("cp1252")
mapping = {}
for orig in ["?","?","??","??","?","?","??","??","??","?","??","?","?"]:
    c = corrupted(orig)
    if c != orig and c in text:
        mapping[c] = orig
# gear emoji is 2 codepoints
c = corrupted("?") + corrupted("?")
if c in text:
    mapping[c] = "??"
print("Replacements:")
count = 0
for bad, good in mapping.items():
    n = text.count(bad)
    if n:
        text = text.replace(bad, good)
        count += n
        print(f"  {repr(good)} x{n}")
f.write_text(text, encoding="utf-8")
print(f"\nDone: {count} replacements")
