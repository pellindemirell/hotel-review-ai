import json
path = r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
print(f"Loaded {len(data)} annotations")

from collections import Counter
langs = Counter(a.get("language", "unknown") for a in data)
print(f"Languages: {dict(langs)}")

# Show first non-Turkish review
for a in data:
    if a.get("language", "en") not in {"tr", "az", "tk"}:
        print(f'First non-TR: lang={a.get("language","?")} text={a["review_text"][:100]}')
        break
else:
    print("All reviews are Turkish")
