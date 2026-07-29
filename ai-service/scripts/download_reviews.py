import csv
import os
from apify_client import ApifyClient

API_TOKEN = os.environ.get("APIFY_API_TOKEN", "")
DATASET_ID = "TMlpPHG1sqQZKArFc"
OUTPUT_DIR = r"D:\KodYazılımModelEğitimiVeri"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "crystal_waterworld_reviews.csv")

client = ApifyClient(API_TOKEN)
dataset = client.dataset(DATASET_ID)
items = dataset.list_items(clean=True).items

print(f"Total items: {len(items)}")

fieldnames = [
    "text", "textTranslated", "stars", "publishAt", "publishedAtDate",
    "language", "originalLanguage", "name", "city",
    "reviewerNumberOfReviews", "isLocalGuide", "responseFromOwnerText",
    "visitedIn", "reviewUrl"
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for item in items:
        row = {k: (item.get(k) or "") for k in fieldnames}
        writer.writerow(row)

print(f"Saved to: {OUTPUT_FILE}")
print(f"Total: {len(items)} reviews")
