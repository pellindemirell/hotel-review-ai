path = r"D:\KodYazılımStaj1\ai-service\app\absa_platform\absa_engine.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

import re
# Check for UTF-8 Turkish chars
for i, line in enumerate(content.split("\n"), 1):
    has_turkish = any(ord(c) > 127 for c in line)
    if has_turkish:
        # Check if char is valid Turkish or garbled
        for c in line:
            if ord(c) > 127 and c not in "ğüşıöçĞÜŞİÖÇ":
                print(f"Line {i}: BAD CHAR '{c}' (U+{ord(c):04X}) in: {line[:80]}")
                break
        else:
            pass  # valid Turkish

print("Check complete")
