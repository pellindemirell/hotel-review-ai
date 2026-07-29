from __future__ import annotations

import csv
import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(r"D:\KodYazılımModelEğitimiVeri")
OUTPUT_FILE = OUTPUT_DIR / "crystal_waterworld_reviews_tripadvisor.csv"
OUTPUT_JSON = OUTPUT_DIR / "crystal_waterworld_reviews_tripadvisor.json"

BASE_URL = (
    "https://www.tripadvisor.com/Hotel_Review-g4833191-d3585023-Reviews"
    "-Crystal_Waterworld_Resort_And_Spa-Bogazkent_Serik_District_Turkish_Mediterranean_Coas.html"
)


def scrape_tripadvisor_playwright(max_reviews: int = 25000) -> list[dict]:
    all_reviews = []
    seen_texts = set()
    page_num = 0
    consecutive_empty = 0
    max_empty = 3

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = context.new_page()

        while len(all_reviews) < max_reviews:
            if page_num == 0:
                url = BASE_URL
            else:
                offset = page_num * 10
                url = BASE_URL.replace("-Reviews-", f"-Reviews-or{offset}-")

            print(f"  Page {page_num + 1}: {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)
            except Exception as e:
                print(f"    Timeout/error: {e}")
                break

            # Try clicking "More" buttons
            try:
                more_buttons = page.locator("button:has-text('More'), span:has-text('More'), a:has-text('More')")
                count = more_buttons.count()
                if count > 0:
                    for i in range(min(count, 20)):
                        try:
                            more_buttons.nth(0).click(timeout=2000)
                            page.wait_for_timeout(500)
                        except:
                            break
            except:
                pass

            reviews = extract_reviews_from_page(page, page_num + 1)
            print(f"    Found {len(reviews)} reviews")

            new_count = 0
            for r in reviews:
                text_key = r.get("text", "")[:100]
                if text_key and text_key not in seen_texts:
                    seen_texts.add(text_key)
                    all_reviews.append(r)
                    new_count += 1

            print(f"    New: {new_count} / Total: {len(all_reviews)}")

            if new_count == 0:
                consecutive_empty += 1
                if consecutive_empty >= max_empty:
                    print("    No new reviews for several pages, stopping.")
                    break
            else:
                consecutive_empty = 0

            page_num += 1
            time.sleep(2)

        browser.close()

    return all_reviews


def extract_reviews_from_page(page, page_num: int) -> list[dict]:
    reviews = []

    # Try various selectors for review containers
    selectors = [
        "div[data-automation='reviewCard']",
        "div.reviewSelector",
        "div._c",
        "div.review-card",
        "div[data-test-target='review-card']",
        "div[data-reviewid]",
        "div.review-container",
        "div.prw_rup",
    ]

    containers = None
    used_sel = None
    for sel in selectors:
        containers = page.locator(sel)
        count = containers.count()
        if count > 0:
            used_sel = sel
            break

    if not containers or containers.count() == 0:
        return reviews

    count = containers.count()

    for i in range(count):
        try:
            container = containers.nth(i)
            review = extract_review_from_element(container)
            if review and review.get("text"):
                reviews.append(review)
        except Exception:
            continue

    return reviews


def extract_review_from_element(el) -> Optional[dict]:
    try:
        text = ""
        text_selectors = [
            "q.review-text",
            "span.review-text",
            "p.partial_entry",
            "div.review-text",
            "[data-test-target='review-text']",
            "span[property='reviewBody']",
            "q[property='reviewBody']",
            "div._a",
            "span._a",
            ".review-text",
        ]
        for sel in text_selectors:
            try:
                t = el.locator(sel)
                if t.count() > 0:
                    text = t.first.inner_text()
                    break
            except:
                continue
        if not text:
            text = el.inner_text()[:500]

        # Rating
        rating = 0
        try:
            bubble = el.locator("span[class*=bubble]")
            if bubble.count() > 0:
                class_attr = bubble.first.get_attribute("class") or ""
                m = re.search(r"bubble_(\d+)", class_attr)
                if m:
                    rating = int(m.group(1)) // 10
        except:
            pass
        if rating == 0:
            try:
                img = el.locator("img[alt*='bubble'], img[alt*='rating'], img[alt*='star']")
                if img.count() > 0:
                    alt = img.first.get_attribute("alt") or ""
                    nums = re.findall(r"\d+", alt)
                    if nums:
                        rating = int(nums[0])
            except:
                pass

        # Title
        title = ""
        try:
            title_el = el.locator("a[class*=title], span[class*=title], .review-title, [data-test-target='review-title']")
            if title_el.count() > 0:
                title = title_el.first.inner_text()
        except:
            pass

        # Reviewer
        reviewer = ""
        try:
            name_el = el.locator("a[class*=member], .member_info, [data-test-target='reviewer-name']")
            if name_el.count() > 0:
                reviewer = name_el.first.inner_text()
        except:
            pass

        # Date
        date = ""
        try:
            date_el = el.locator("span[class*=date], .review-date, [data-test-target='review-date']")
            if date_el.count() > 0:
                date = date_el.first.inner_text()
        except:
            pass

        if text:
            return {
                "title": title.strip(),
                "rating": rating,
                "text": text.strip(),
                "reviewer": reviewer.strip(),
                "date": date.strip(),
            }
    except Exception:
        pass

    return None


def main():
    print("=== TripAdvisor Review Scraper (Playwright) ===")
    print("Hotel: Crystal Waterworld Resort & Spa")
    print()

    reviews = scrape_tripadvisor_playwright(max_reviews=25000)

    if not reviews:
        print("No reviews found!")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
    print(f"Saved JSON: {OUTPUT_JSON}")

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["rating", "title", "text", "reviewer", "date"])
        writer.writeheader()
        writer.writerows(reviews)
    print(f"Saved CSV: {OUTPUT_FILE}")

    ratings = [r["rating"] for r in reviews if r.get("rating")]
    print(f"\n=== Stats ===")
    print(f"Total reviews: {len(reviews)}")
    if ratings:
        print(f"Average rating: {sum(ratings) / len(ratings):.2f}")
        dist = Counter(ratings)
        for r in sorted(dist):
            print(f"  {r} star: {dist[r]}")


if __name__ == "__main__":
    main()
