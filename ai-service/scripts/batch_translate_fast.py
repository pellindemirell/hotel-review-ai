import json, sys, time, os, concurrent.futures
from pathlib import Path
from deep_translator import GoogleTranslator

ANNOTATED_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002.json"
)
OUTPUT_PATH = ANNOTATED_PATH.parent / f"{ANNOTATED_PATH.stem}_translated.json"

TURKISH_LANGS = {"tr", "az", "tk"}
WORKERS = 4

def create_translator():
    return GoogleTranslator(source="auto", target="tr")

def translate_text(text, translator):
    if not text or len(text.strip()) < 2:
        return text
    try:
        if len(text) <= 4500:
            return translator.translate(text[:4500])
        return _chunked_translate(text, translator)
    except:
        return text


def _chunked_translate(text: str, translator, max_chunk: int = 4000) -> str:
    import re
    text = text[:50000]
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > max_chunk and current:
            chunks.append(current.strip())
            current = s
        else:
            current = (current + " " + s).strip() if current else s
    if current:
        chunks.append(current.strip())
    parts = []
    for chunk in chunks:
        try:
            parts.append(translator.translate(chunk[:4500]) or chunk[:4500])
        except Exception:
            parts.append(chunk)
    return " ".join(parts)

def process_review(args):
    ann, idx, total = args
    text = ann.get("review_text", "")
    result = {}

    if text and len(text.strip()) >= 5:
        t = create_translator()
        result["review_text_translated"] = translate_text(text, t)
    else:
        result["review_text_translated"] = ""

    # Translate clauses
    result["clauses"] = []
    for c in ann.get("clauses", []):
        ct = c.get("text", "")
        if ct:
            t2 = create_translator()
            result["clauses"].append({"text_translated": translate_text(ct, t2)})
        else:
            result["clauses"].append({"text_translated": ""})

    # Translate failure descriptions
    result["process_failures"] = []
    for pf in ann.get("process_failures", []):
        desc = pf.get("description", "")
        if desc:
            t3 = create_translator()
            result["process_failures"].append({"description_translated": translate_text(desc, t3)})
        else:
            result["process_failures"].append({"description_translated": ""})

    if (idx + 1) % 50 == 0:
        print(f"  {idx + 1}/{total}")

    return ann["_index"], result

# Load
if OUTPUT_PATH.exists():
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        annotations = json.load(f)
    print(f"Resuming: {OUTPUT_PATH} loaded ({len(annotations)} records)")
else:
    with open(ANNOTATED_PATH, "r", encoding="utf-8") as f:
        annotations = json.load(f)
    print(f"Starting fresh: {len(annotations)} records")

# Mark indices
for i, a in enumerate(annotations):
    a["_index"] = i

to_translate = [
    a for a in annotations
    if a.get("language", "en") not in TURKISH_LANGS
    and not a.get("review_text_translated")
]
total = len([a for a in annotations if a.get("language", "en") not in TURKISH_LANGS])
done = total - len(to_translate)
print(f"Foreign total: {total} | Done: {done} | Remaining: {len(to_translate)}")

if not to_translate:
    print("ALL DONE!")
    sys.exit(0)

# Process with thread pool
args_list = [(ann, i, len(to_translate)) for i, ann in enumerate(to_translate)]

with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
    futures = {executor.submit(process_review, args): args for args in args_list}
    for future in concurrent.futures.as_completed(futures):
        try:
            idx, result = future.result()
            ann = annotations[idx]
            ann["review_text_translated"] = result["review_text_translated"]
            for j, c in enumerate(ann.get("clauses", [])):
                if j < len(result["clauses"]) and result["clauses"][j].get("text_translated"):
                    c["text_translated"] = result["clauses"][j]["text_translated"]
            for j, pf in enumerate(ann.get("process_failures", [])):
                if j < len(result["process_failures"]) and result["process_failures"][j].get("description_translated"):
                    pf["description_translated"] = result["process_failures"][j]["description_translated"]
        except Exception as e:
            print(f"Error: {e}")

# Clean up indices
for a in annotations:
    del a["_index"]

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(annotations, f, ensure_ascii=False, indent=2)

print(f"\nDONE! All {total} foreign reviews translated -> {OUTPUT_PATH}")
