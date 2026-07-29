"""
Guvenilir toplu ceviri — her 50 yorumda bir kaydeder, durdurulup devam edilebilir.
Kotasi yok, sadece Google rate-limit'e takilmamak icin 1sn bekleme ekler.
"""
import json, sys, time, os
from pathlib import Path
from deep_translator import GoogleTranslator

ANNOTATED_PATH = Path(
    r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002.json"
)
OUTPUT_PATH = ANNOTATED_PATH.parent / "annotated_batch_002_translated.json"

TRANSLATOR = GoogleTranslator(source="auto", target="tr")
TURKISH_LANGS = {"tr", "az", "tk"}
DELAY = 0.3  # 0.3 saniye — Google rate-limit korumasi (hizlandirildi)


def translate(text):
    if not text or len(text.strip()) < 3:
        return text
    try:
        if len(text) <= 4500:
            return TRANSLATOR.translate(text[:4500])
        return _chunked_translate(text)
    except Exception as e:
        print(f"    CEVIRI HATASI: {e}")
        time.sleep(3)
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


# Resume kontrolu
if OUTPUT_PATH.exists():
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        annotations = json.load(f)
    print(f"Kaldigin yerden devam: {OUTPUT_PATH}")
else:
    with open(ANNOTATED_PATH, "r", encoding="utf-8") as f:
        annotations = json.load(f)
    print(f"Sifirdan basliyor: {len(annotations)} yorum")

# Cevrilecekleri bul
to_translate = [
    a for a in annotations
    if a.get("language", "en") not in TURKISH_LANGS
    and not a.get("review_text_translated")
]
total_foreign = len([a for a in annotations if a.get("language", "en") not in TURKISH_LANGS])
done_before = total_foreign - len(to_translate)
print(f"Yabanci yorum: {total_foreign}")
print(f"Onceden cevrilmis: {done_before}")
print(f"Kalan: {len(to_translate)}")
print()

if not to_translate:
    print("TUMU CEVRILMIS!")
    sys.exit(0)

# Batch'ler halinde cevir
batch_size = 50
total_batches = (len(to_translate) + batch_size - 1) // batch_size

for batch_idx in range(total_batches):
    start = batch_idx * batch_size
    end = min(start + batch_size, len(to_translate))
    batch = to_translate[start:end]

    print(f"Batch {batch_idx + 1}/{total_batches} ({start + 1}-{end} / {len(to_translate)})")

    for i, ann in enumerate(batch):
        idx = start + i + 1
        text = ann.get("review_text", "")

        # Ana metin
        if text and len(text.strip()) >= 3:
            ann["review_text_translated"] = translate(text)

        # Clause'lar
        for c in ann.get("clauses", []):
            ct = c.get("text", "")
            if ct and not c.get("text_translated"):
                c["text_translated"] = translate(ct)

        # Failure aciklamalari
        for pf in ann.get("process_failures", []):
            desc = pf.get("description", "")
            if desc and not pf.get("description_translated"):
                pf["description_translated"] = translate(desc)

        if idx % 10 == 0:
            print(f"  [{idx}/{len(to_translate)}]")

        time.sleep(DELAY)

    # Her batch sonu kaydet
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(annotations, f, ensure_ascii=False, indent=2)
    print(f"  -> Kaydedildi ({done_before + end}/{total_foreign})")
    print()

print(f"\nTAMAM! {total_foreign} yabanci yorum cevrildi.")
print(f"Kayit: {OUTPUT_PATH}")
