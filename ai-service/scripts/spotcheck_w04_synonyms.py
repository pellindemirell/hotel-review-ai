#!/usr/bin/env python3
"""Spot-check W04 batch2 synonym resolution."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ontology.engine import get_hotel_ontology_engine


def count_terms(path: Path) -> int:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return sum(len(e.get("terms", [])) for e in data.get("synonyms", []))


def main() -> None:
    hotel = ROOT.parent / "hotel-ai" / "datasets" / "ontology" / "v1" / "synonyms"
    ai = ROOT / "config" / "ontology" / "synonyms"
    for lang in ("tr", "en"):
        h = count_terms(hotel / f"{lang}.yaml")
        a = count_terms(ai / f"{lang}.yaml")
        print(f"{lang}: hotel-ai={h} ai-service={a} sync={'OK' if h == a else 'MISMATCH'}")

    e = get_hotel_ontology_engine()
    entity_checks = ["klima", "minibar", "wifi"]
    aspect_checks = ["aquaprk", "bal kaymak", "resepsiyon"]
    for term in entity_checks:
        r = e.resolve_term(term, "tr")
        print(
            f"resolve_term({term!r}): entity_id={r.entity_id!r} "
            f"conf={r.confidence:.2f} matched={r.matched_term!r}"
        )
    for term in aspect_checks:
        r = e.resolve_term(term, "tr")
        m = e.map_aspect(term, "tr")
        print(
            f"resolve_term({term!r}): entity_id={r.entity_id!r} conf={r.confidence:.2f}; "
            f"map_aspect={m.aspect!r} conf={m.confidence:.2f} method={m.method!r}"
        )


if __name__ == "__main__":
    main()
