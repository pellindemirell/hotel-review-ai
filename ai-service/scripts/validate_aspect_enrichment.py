#!/usr/bin/env python3
"""Validate aspect_enrichment.yaml against aspects.yaml.

Checks:
- YAML parses
- every enrichment key exists in aspects.yaml
- no unknown keys introduced
- frequently_confused_with targets exist
- coverage / field non-emptiness stats
- spot-check sample aspects
Writes report to audit_outputs/aspect_enrichment_validation.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("PyYAML required", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / "ai-service"
ASPECTS = AI / "config" / "ontology" / "aspects.yaml"
ENRICH = AI / "config" / "ontology" / "aspect_enrichment.yaml"
REPORT = ROOT / "audit_outputs" / "aspect_enrichment_validation.json"

SPOT_KEYS = [
    "room_cleanliness",
    "room_smell",
    "bed_comfort",
    "bathroom_cleanliness",
    "shower_pressure",
    "hvac_cooling",
    "wifi_speed",
    "food_taste",
    "staff_behavior",
    "pool_cleanliness",
]

REQUIRED_NONEMPTY = [
    "aliases",
    "positive_words",
    "negative_words",
    "multilingual",
    "typos",
    "slang",
]


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    return data


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not ASPECTS.exists():
        print(f"Missing {ASPECTS}", file=sys.stderr)
        return 2
    if not ENRICH.exists():
        print(f"Missing {ENRICH}", file=sys.stderr)
        return 2

    aspects_data = _load(ASPECTS)
    enrich_data = _load(ENRICH)

    aspect_keys: set[str] = set()
    by_cat: dict[str, int] = {}
    for cat, cat_data in aspects_data.get("categories", {}).items():
        n = 0
        for asp in cat_data.get("aspects", []):
            aspect_keys.add(asp["key"])
            n += 1
        by_cat[cat] = n

    enrich_map = enrich_data.get("aspects", {})
    if not isinstance(enrich_map, dict):
        errors.append("'aspects' in enrichment must be a mapping")
        enrich_map = {}

    enrich_keys = set(enrich_map.keys())
    unknown = sorted(enrich_keys - aspect_keys)
    missing = sorted(aspect_keys - enrich_keys)
    if unknown:
        errors.append(f"{len(unknown)} unknown enrichment keys (not in aspects.yaml)")
    if missing:
        warnings.append(f"{len(missing)} aspects.yaml keys lack enrichment")

    bad_confused = 0
    empty_fields = {f: 0 for f in REQUIRED_NONEMPTY}
    enriched_ok = 0
    for key, entry in enrich_map.items():
        if key not in aspect_keys:
            continue
        if not isinstance(entry, dict):
            errors.append(f"{key}: entry is not a mapping")
            continue
        enriched_ok += 1
        for f in REQUIRED_NONEMPTY:
            val = entry.get(f)
            if val is None or val == "" or val == {} or val == []:
                empty_fields[f] += 1
        for other in entry.get("frequently_confused_with") or []:
            if other not in aspect_keys:
                bad_confused += 1
                if bad_confused <= 20:
                    errors.append(f"{key}: confused_with unknown key '{other}'")

    if bad_confused > 20:
        errors.append(f"... and {bad_confused - 20} more invalid confused_with refs")

    spot: dict[str, Any] = {}
    for sk in SPOT_KEYS:
        entry = enrich_map.get(sk)
        if not entry:
            warnings.append(f"spot-check missing: {sk}")
            continue
        spot[sk] = {
            "aliases_n": len(entry.get("aliases") or []),
            "typos_n": len(entry.get("typos") or []),
            "slang_tr_n": len((entry.get("slang") or {}).get("tr") or []),
            "ml_langs": sorted((entry.get("multilingual") or {}).keys()),
            "confused": entry.get("frequently_confused_with") or [],
            "sample_alias": (entry.get("aliases") or [None])[0],
            "sample_typo": (entry.get("typos") or [None])[0],
            "sample_slang_tr": ((entry.get("slang") or {}).get("tr") or [None])[0],
        }

    # Loader import/parse check (optional if path available)
    loader_ok = False
    loader_error = None
    try:
        sys.path.insert(0, str(AI))
        from app.ontology.loader import OntologyConfigLoader  # type: ignore

        loader = OntologyConfigLoader(AI / "config" / "ontology")
        raw = loader.load_aspects()
        meta = loader.get_aspect_enrichment_map()
        merged = loader.load_aspects_merged()
        assert len(meta) == len(enrich_map)
        # ensure raw aspects unchanged in structure
        raw_n = sum(len(c.get("aspects", [])) for c in raw.get("categories", {}).values())
        merged_n = sum(len(c.get("aspects", [])) for c in merged.get("categories", {}).values())
        assert raw_n == merged_n == len(aspect_keys)
        # enrichment present on merged sample
        sample = None
        for c in merged.get("categories", {}).values():
            for a in c.get("aspects", []):
                if a["key"] == "room_cleanliness":
                    sample = a
                    break
        assert sample is not None and "aliases" in sample and "typos" in sample
        # protected fields still from aspects.yaml
        assert sample["key"] == "room_cleanliness"
        loader_ok = True
    except Exception as exc:  # noqa: BLE001
        loader_error = str(exc)
        warnings.append(f"loader check failed: {exc}")

    report = {
        "ok": not errors,
        "aspects_yaml_count": len(aspect_keys),
        "enrichment_count": len(enrich_keys),
        "matched_count": len(aspect_keys & enrich_keys),
        "unknown_keys_count": len(unknown),
        "unknown_keys_sample": unknown[:20],
        "missing_keys_count": len(missing),
        "missing_keys_sample": missing[:20],
        "invalid_confused_with": bad_confused,
        "empty_field_counts": empty_fields,
        "by_category": by_cat,
        "spot_check": spot,
        "loader_merge_ok": loader_ok,
        "loader_error": loader_error,
        "enrichment_path": str(ENRICH),
        "aspects_path": str(ASPECTS),
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({k: report[k] for k in (
        "ok", "aspects_yaml_count", "enrichment_count", "matched_count",
        "unknown_keys_count", "missing_keys_count", "invalid_confused_with",
        "loader_merge_ok",
    )}, indent=2))
    print(f"Report: {REPORT}")
    if errors:
        print("ERRORS:", file=sys.stderr)
        for e in errors[:30]:
            print(f"  - {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
