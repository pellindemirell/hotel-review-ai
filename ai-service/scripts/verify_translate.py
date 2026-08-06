import json
path = r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002_translated.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
non_tr = [a for a in data if a.get("language", "en") not in {"tr", "az", "tk"}]
with_tr = [a for a in non_tr if a.get("review_text_translated")]
print(f"Non-Turkish: {len(non_tr)}")
print(f"With translation: {len(with_tr)} ({len(with_tr)/len(non_tr)*100:.1f}%)")
if len(non_tr) > len(with_tr):
    print(f"MISSING: {len(non_tr) - len(with_tr)} reviews still need translation")
else:
    print("ALL TRANSLATIONS COMPLETE!")
