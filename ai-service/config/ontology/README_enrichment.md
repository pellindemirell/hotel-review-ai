# Aspect enrichment (companion metadata)

Keys in `aspects.yaml` are **frozen**. This directory keeps operational /
linguistic metadata in a companion file so ABSA runtime, the 8-department UI,
and `clause_pipeline.yaml` stay unchanged.

## Files

| File | Role |
|------|------|
| `aspects.yaml` | Canonical aspect keys, labels, department, keywords (~861). **Do not rename/add keys here for enrichment.** |
| `aspect_enrichment.yaml` | Metadata keyed by existing `key` (aliases, multilingual, typos, slang, cues, examples, ops). |
| `README_enrichment.md` | This note. |

## Schema (per aspect key)

Optional fields under `aspects.<key>` in `aspect_enrichment.yaml`:

- `aliases` / `synonyms` — guest phrases (TR+EN minimum)
- `multilingual` — `{tr, en, de, ru, ar}` short phrase lists (TR richest, EN strong, DE/RU/AR lighter)
- `typos` — misspellings / keyboard variants (esp. Turkish diacritics)
- `slang` — `{tr, en, ...}` colloquial guest language
- `positive_words` / `negative_words` — sentiment cues
- `verbs` / `objects` — short lists
- `common_phrases` — guest-like phrases
- `positive_examples` / `negative_examples` / `counter_examples`
- `frequently_confused_with` — **existing** aspect keys only
- `related_processes` / `related_sop` / `related_root_causes` / `related_actions`
- `description_tr` / `description_en`

## How to consume (no pipeline rewrite)

```python
from app.ontology.loader import OntologyConfigLoader

loader = OntologyConfigLoader()
# Raw frozen ontology (runtime ABSA / engine index continue using this)
raw = loader.load_aspects()

# Companion map only
meta = loader.get_aspect_enrichment_map()
room = meta["room_cleanliness"]
aliases = room["aliases"] + room.get("typos", []) + room.get("slang", {}).get("tr", [])

# Or merged view for KG / HODIP / offline analysis (does not change AbsaService)
merged = loader.load_aspects_merged()
```

**ABSA / clause pipeline:** keep matching on `aspects.yaml` keywords + pipeline rules.
Use enrichment for:

- Knowledge Graph node attributes / edge suggestions (`frequently_confused_with`, root causes)
- HODIP / ops playbooks (`related_*`)
- Offline lexicon expansion (aliases, typos, slang, multilingual) when explicitly enabled

Do **not** auto-wire all 861 enriched aspects into `clause_pipeline.yaml`.

## Regenerate

```bash
python ai-service/scripts/generate_aspect_enrichment.py
python ai-service/scripts/validate_aspect_enrichment.py
```

Regeneration overwrites `aspect_enrichment.yaml` from templates + keyword expansion +
hand overrides for high-value aspects. Core `aspects.yaml` keys are never modified.

## Validation rules

1. Every enrichment key must exist in `aspects.yaml`
2. No new aspect keys
3. `frequently_confused_with` entries must exist in `aspects.yaml`
4. YAML must parse
