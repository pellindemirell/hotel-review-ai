import json
with open(r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002_translated.json", "r", encoding="utf-8") as f:
    data = json.load(f)
total = len(data)
with_translation = sum(1 for a in data if a.get("review_text_translated"))
with_clause_tr = sum(1 for a in data for c in a.get("clauses",[]) if c.get("text_translated"))
print(f"Total: {total}")
print(f"With translation: {with_translation}")
print(f"With clause translation: {with_clause_tr}")
for a in data:
    tr = a.get("review_text_translated")
    lang = a.get("language", "?")
    if tr and lang != "tr":
        print(f"\nLang={lang}")
        print(f"Original: {a['review_text'][:120]}")
        print(f"Translated: {tr[:120]}")
        break
