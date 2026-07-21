"""
Otel terminoloji ansiklopedisi yukleyici.
simulation/hotel_terminology_encyclopedia.json -> NLP modullerine birlestirme.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

ALL_CATEGORIES = [
    "Kat Hizmetleri & Temizlik",
    "Yiyecek & İçecek & Yemekler",
    "Resepsiyon & Ön Büro",
    "Teknik Servis (Maintenance)",
    "Spa & Wellness / Aktivite",
    "Muhasebe & Finans",
    "Personel Davranışı & İletişim",
    "Diğer",
]


def _encyclopedia_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(root, "simulation", "hotel_terminology_encyclopedia.json")


@lru_cache(maxsize=1)
def load_encyclopedia() -> dict[str, Any]:
    path = _encyclopedia_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _terms(items: list) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            t = item.get("term", "")
        else:
            t = str(item)
        if t and t not in out:
            out.append(t)
    return out


def get_strong_positive_words() -> set[str]:
    enc = load_encyclopedia()
    return set(_terms(enc.get("global", {}).get("strong_positive_words", [])))


def get_strong_negative_words() -> set[str]:
    enc = load_encyclopedia()
    return set(_terms(enc.get("global", {}).get("strong_negative_words", [])))


def get_twitter_slang_positive() -> list[str]:
    enc = load_encyclopedia()
    return _terms(enc.get("global", {}).get("twitter_slang_positive", []))


def get_twitter_slang_negative() -> list[str]:
    enc = load_encyclopedia()
    return _terms(enc.get("global", {}).get("twitter_slang_negative", []))


def get_conjunctions() -> list[str]:
    enc = load_encyclopedia()
    return list(enc.get("global", {}).get("conjunctions", []))


def get_mixed_splitters() -> list[str]:
    enc = load_encyclopedia()
    return list(enc.get("global", {}).get("mixed_review_splitters", []))


def get_literary_positive() -> list[str]:
    enc = load_encyclopedia()
    return list(enc.get("global", {}).get("literary_hyperbole_positive", []))


def get_literary_negative() -> list[str]:
    enc = load_encyclopedia()
    return list(enc.get("global", {}).get("literary_hyperbole_negative", []))


def get_category_keywords(base: dict[str, list[str]]) -> dict[str, list[str]]:
    """Kategori basina freq-ranked terimleri anahtar kelime listesine ekle."""
    enc = load_encyclopedia()
    cats = enc.get("categories", {})
    out = {k: list(v) for k, v in base.items()}
    seen: dict[str, set[str]] = {k: set(v) for k, v in out.items()}

    for cat in ALL_CATEGORIES:
        block = cats.get(cat, {})
        for key in ("positive_terms", "negative_terms", "positive_bigrams", "negative_bigrams"):
            for term in _terms(block.get(key, [])):
                if term not in seen.setdefault(cat, set()):
                    out.setdefault(cat, []).append(term)
                    seen[cat].add(term)
    return out


def get_phrase_sentiment_weights() -> list[tuple[str, float]]:
    """Bigram/template bazli duygu agirliklari."""
    enc = load_encyclopedia()
    weights: list[tuple[str, float]] = []
    for cat, block in enc.get("categories", {}).items():
        for item in block.get("positive_bigrams", [])[:40]:
            t = item["term"] if isinstance(item, dict) else str(item)
            freq = item.get("freq", 1) if isinstance(item, dict) else 1
            w = min(4.0, 1.5 + (freq ** 0.5) / 20)
            weights.append((t, w))
        for item in block.get("negative_bigrams", [])[:40]:
            t = item["term"] if isinstance(item, dict) else str(item)
            freq = item.get("freq", 1) if isinstance(item, dict) else 1
            w = min(4.0, 1.5 + (freq ** 0.5) / 20)
            weights.append((t, -w))
    return weights


def encyclopedia_stats() -> dict[str, int]:
    enc = load_encyclopedia()
    if not enc:
        return {"loaded": 0}
    g = enc.get("global", {})
    cats = enc.get("categories", {})
    return {
        "loaded": 1,
        "rows_processed": enc.get("meta", {}).get("rows_processed", 0),
        "strong_positive": len(g.get("strong_positive_words", [])),
        "strong_negative": len(g.get("strong_negative_words", [])),
        "twitter_pos": len(g.get("twitter_slang_positive", [])),
        "twitter_neg": len(g.get("twitter_slang_negative", [])),
        "category_blocks": len(cats),
        "total_category_terms": sum(
            len(c.get("positive_terms", [])) + len(c.get("negative_terms", []))
            for c in cats.values()
        ),
    }


def merge_word_set(base: set[str], extra: set[str]) -> set[str]:
    return base | extra


def merge_phrase_list(base: list[str], extra: list[str]) -> list[str]:
    seen = set(base)
    out = list(base)
    for item in extra:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out
