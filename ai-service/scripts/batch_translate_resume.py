import json, sys, time, os
from pathlib import Path
from deep_translator import GoogleTranslator

ANNOTATED_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002.json"
)
OUTPUT_PATH = ANNOTATED_PATH.parent / f"{ANNOTATED_PATH.stem}_translated.json"

TRANSLATOR = GoogleTranslator(source="auto", target="tr")
TURKISH_LANGS = {"tr", "az", "tk"}
DELAY = 0.3

def translate(text):
    if not text or len(text.strip()) < 2:
        return text
    try:
        if len(text) <= 4500:
            return TRANSLATOR.translate(text[:4500])
        return _chunked_translate(text)
    except Exception as e:
        print(f"    HATA: {e}")
        return text


def _chunked_translate(text: str, max_chunk: int = 4000) -> str:
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
            parts.append(GoogleTranslator(source="auto", target="tr").translate(chunk[:4500]) or chunk[:4500])
        except Exception:
            parts.append(chunk)
    return " ".join(parts)

# Load or create
if OUTPUT_PATH.exists():
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        annotations = json.load(f)
    print(f"Devam ediliyor: {OUTPUT_PATH} yuklendi ({len(annotations)} kayit)")
else:
    with open(ANNOTATED_PATH, "r", encoding="utf-8") as f:
        annotations = json.load(f)
    print(f"Yeni basliyor: {len(annotations)} kayit")

to_translate = [
    a for a in annotations
    if a.get("language", "en") not in TURKISH_LANGS
    and not a.get("review_text_translated")
]
total = len([a for a in annotations if a.get("language", "en") not in TURKISH_LANGS])
done = total - len(to_translate)
print(f"Toplam yabanci: {total} | Tamam: {done} | Kalan: {len(to_translate)}")

for i, ann in enumerate(to_translate):
    text = ann.get("review_text", "")
    if text and len(text.strip()) >= 5:
        ann["review_text_translated"] = translate(text)
    else:
        ann["review_text_translated"] = ""

    for c in ann.get("clauses", []):
        ct = c.get("text", "")
        if ct:
            c["text_translated"] = translate(ct)

    for pf in ann.get("process_failures", []):
        desc = pf.get("description", "")
        if desc:
            pf["description_translated"] = translate(desc)

    if (i + 1) % 50 == 0:
        print(f"  {i + 1}/{len(to_translate)} coevrildi ({(done + i + 1)}/{total})")
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(annotations, f, ensure_ascii=False, indent=2)
        print(f"    -> kaydedildi")

    time.sleep(DELAY)

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(annotations, f, ensure_ascii=False, indent=2)
print(f"\nTAMAM! {total} yabanci yorum coevrildi -> {OUTPUT_PATH}")
