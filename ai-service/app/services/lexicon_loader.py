"""
Otel NLP leksikon yükleyici — simulation/hotel_phrase_lexicon.json (+ opsiyonel generated).
Runtime'da modüllere birleştirilmiş kalıp listeleri sağlar.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Optional

_LEXICON_CACHE: Optional[dict[str, Any]] = None


def _lexicon_paths() -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    sim = os.path.join(root, "simulation")
    return [
        os.path.join(sim, "hotel_phrase_lexicon.json"),
        os.path.join(sim, "hotel_phrase_lexicon_generated.json"),
        os.path.join(sim, "hotel_phrase_lexicon_learned.json"),
    ]


# Öğrenilmiş leksikondan tek kelime parçaları duygu skorunu bozar (örn. "en", "bar", "güzel")
_LEXICON_STOPWORDS: frozenset[str] = frozenset({
    "en", "et", "in", "li", "me", "di", "de", "da", "ve", "bir", "bu", "ile", "icin", "için",
    "lar", "ler", "lik", "kinlik", "gun", "gün", "aksam", "akşam", "bar", "oda", "yemek",
    "havuz", "plaj", "otel", "genel", "daha", "cok", "çok", "guzel", "güzel", "harik", "harika",
    "bekleme", "değildi", "degildi", "haziran", "mayis", "mayıs", "personel", "restoran",
    "kahvalti", "kahvaltı", "animasyon", "pastane", "temiz", "memnun", "fena", "iyi",
})

_STRONG_SINGLE_PHRASES: frozenset[str] = frozenset({
    "kalitesiz", "yetersiz", "lezzetsiz", "berbat", "mukemmel", "mükemmel", "harika",
    "tertemiz", "rezalet", "igrenc", "iğrenç", "korkunc", "korkunç", "basarili", "başarılı",
    "eglenceli", "eğlenceli", "eglenceliydi", "eğlenceliydi", "yardimci", "yardımcı",
})


def _is_valid_learned_phrase(phrase: str) -> bool:
    """Öğrenilmiş leksikondan yalnızca anlamlı ifadeleri kabul et."""
    p = str(phrase).strip().lower()
    if not p or len(p) < 4:
        return False
    if p in _LEXICON_STOPWORDS:
        return False
    if " " in p:
        return len(p) >= 8
    if p in _STRONG_SINGLE_PHRASES:
        return True
    return len(p) >= 7 and any(p.endswith(s) for s in ("siz", "sız", "suz", "süz", "memiş", "memis", "medi", "madı"))


def _merge_unique(base: list, extra: list) -> list:
    seen: set[str] = set()
    out: list = []
    for item in list(base) + list(extra):
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (list, dict)) else str(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _merge_dict_lists(base: dict[str, list], extra: dict[str, list]) -> dict[str, list]:
    out = {k: list(v) for k, v in base.items()}
    for cat, items in (extra or {}).items():
        out[cat] = _merge_unique(out.get(cat, []), items)
    return out


@lru_cache(maxsize=1)
def load_lexicon() -> dict[str, Any]:
    """Ana + generated leksikon dosyalarını birleştir."""
    merged: dict[str, Any] = {}
    for path in _lexicon_paths():
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for key, val in data.items():
            if key == "meta":
                merged.setdefault("meta", {}).update(val if isinstance(val, dict) else {})
                continue
            if key not in merged:
                merged[key] = val
            elif isinstance(val, list) and isinstance(merged[key], list):
                merged[key] = _merge_unique(merged[key], val)
            elif isinstance(val, dict) and isinstance(merged[key], dict):
                if all(isinstance(v, list) for v in val.values()):
                    merged[key] = _merge_dict_lists(merged[key], val)
                else:
                    merged[key].update(val)
    return merged


def merge_phrase_lists(base: list[str], key: str) -> list[str]:
    lex = load_lexicon()
    extra = [p for p in lex.get(key, []) if _is_valid_learned_phrase(p)]
    return _merge_unique(base, extra)


def merge_category_keywords(base: dict[str, list[str]]) -> dict[str, list[str]]:
    lex = load_lexicon()
    return _merge_dict_lists(base, lex.get("category_keywords", {}))


def merge_category_phrases(base: dict[str, list]) -> dict[str, list]:
    lex = load_lexicon()
    extra = lex.get("category_phrases", {})
    out = {k: list(v) for k, v in base.items()}
    for cat, items in extra.items():
        existing = {(p, w) if isinstance(p, str) else tuple(p) for p, w in out.get(cat, [])}
        for entry in items:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                phrase, weight = entry[0], float(entry[1])
            elif isinstance(entry, dict):
                phrase, weight = entry["phrase"], float(entry.get("weight", 5.0))
            else:
                continue
            key = (phrase, weight)
            if key not in existing:
                out.setdefault(cat, []).append((phrase, weight))
                existing.add(key)
    return out


def get_suggestion_rules_from_lexicon() -> dict[str, list[dict]]:
    return load_lexicon().get("suggestion_rules", {})


def lexicon_stats() -> dict[str, int]:
    """Yüklü leksikon boyut özeti."""
    lex = load_lexicon()
    stats: dict[str, int] = {}
    for key in (
        "positive_phrases", "negative_phrases", "negative_hyperbole",
        "joke_markers", "joke_context_markers", "manipulation_patterns",
        "mixed_review_splitters", "positive_idioms",
    ):
        stats[key] = len(lex.get(key, []))
    ck = lex.get("category_keywords", {})
    stats["category_keywords_total"] = sum(len(v) for v in ck.values())
    cp = lex.get("category_phrases", {})
    stats["category_phrases_total"] = sum(len(v) for v in cp.values())
    sr = lex.get("suggestion_rules", {})
    stats["suggestion_rule_groups"] = sum(len(v) for v in sr.values())
    stats["suggestion_pattern_triggers"] = sum(
        len(r.get("patterns", [])) for rules in sr.values() for r in rules
    )
    return stats
