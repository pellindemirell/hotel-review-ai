"""Hotel ontology engine — config-driven resolution and review parsing."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Optional

from app.ontology.loader import OntologyConfigLoader
from app.ontology.models import AspectMapping, EntityRef, Segment
from app.services.turkish_nlp_utils import (
    NEGATIVE_WORDS,
    POSITIVE_WORDS,
    normalize_turkish,
    tokenize_turkish,
)

# Department display labels (aligns with domain_ontology.json + enterprise keys)
_DEPT_LABELS: dict[str, str] = {
    "housekeeping": "Housekeeping",
    "engineering_hvac": "Mühendislik — HVAC",
    "engineering_internet": "Mühendislik — İnternet",
    "engineering_plumbing": "Mühendislik — Tesisat",
    "teknik": "Teknik",
    "restaurant": "Restaurant",
    "bar": "Bar",
    "personel": "Personel",
    "front_office": "Front Office",
    "spa": "Spa",
    "havuz": "Havuz",
    "animasyon": "Animasyon & Etkinlik",
    "guvenlik": "Güvenlik",
    "genel": "Genel",
    "oda_hizmetleri_housekeeping": "Kat Hizmetleri & Temizlik",
    "yiyecek_icecek_fb": "Yiyecek & İçecek (F&B)",
    "on_buyro_misafir": "Ön Büro & Misafir İlişkileri",
    "teknik_it": "Teknik Servis & IT",
    "rekreasyon_eglence": "Rekreasyon & Eğlence (Leisure)",
    "cevre_guvenlik_ulasim": "Çevre, Güvenlik & Ulaşım",
    "otel_atmosferi": "Otel Atmosferi & Misafir Profili",
    "personel_davranisi": "Personel Davranışı",
}


def _dept_label(dept_key: str) -> str:
    return _DEPT_LABELS.get(dept_key, dept_key.replace("_", " ").title())


def _entity_type_for_record(record: dict[str, Any], source_key: str) -> str:
    if source_key in ("physical", "facilities"):
        return "physical" if source_key == "physical" else "facility"
    if source_key == "human":
        return "human"
    return "equipment"


@lru_cache(maxsize=4)
def _get_engine(config_dir: str | None = None) -> "HotelOntologyEngine":
    return HotelOntologyEngine(config_dir=config_dir)


class HotelOntologyEngine:
    """Config-driven hotel ontology — entity, aspect, synonym, review parsing."""

    def __init__(self, config_dir: str | None = None) -> None:
        self._loader = OntologyConfigLoader(config_dir)
        self._entities: dict[str, dict[str, Any]] = {}
        self._entity_index: list[tuple[str, str, str, str]] = []  # term, entity_id, lang, type
        self._aspect_index: list[tuple[str, str, str, str, str, str]] = []
        # term, aspect_key, category, dept, label_tr, label_en
        self._responsibilities: dict[str, str] = {}
        self._managed_by: dict[str, str] = {}
        self._runtime_synonyms: list[dict[str, Any]] = []
        self._aspect_meta_cache: dict[str, dict[str, str]] = {}
        self.reload()

    def reload(self) -> None:
        """Reload all config files and rebuild indexes."""
        self._loader.clear_cache()
        self._entities.clear()
        self._entity_index.clear()
        self._aspect_index.clear()
        self._responsibilities.clear()
        self._managed_by.clear()
        self._aspect_meta_cache.clear()
        self._build_entity_index()
        self._build_aspect_index()
        self._build_aspect_meta_cache()
        self._build_responsibility_index()
        self._build_relationship_index()
        self._index_synonyms()
        self._index_runtime_synonyms()

    def _build_entity_index(self) -> None:
        data = self._loader.load_entities()
        for source_key in ("physical", "facilities", "human", "equipment"):
            for record in data.get(source_key, []):
                eid = record["id"]
                etype = _entity_type_for_record(record, source_key)
                labels = record.get("labels", {})
                self._entities[eid] = {
                    **record,
                    "type": etype,
                    "label_tr": labels.get("tr", eid),
                    "label_en": labels.get("en", eid),
                }

    def _build_aspect_index(self) -> None:
        data = self._loader.load_aspects()
        for category, cat_data in data.get("categories", {}).items():
            for asp in cat_data.get("aspects", []):
                for kw in asp.get("keywords", []):
                    self._aspect_index.append((
                        normalize_turkish(kw.lower()),
                        asp["key"],
                        category,
                        asp.get("department", "genel"),
                        asp.get("label_tr", asp["key"]),
                        asp.get("label_en", asp["key"]),
                    ))

    def _build_aspect_meta_cache(self) -> None:
        data = self._loader.load_aspects()
        for cat, cat_data in data.get("categories", {}).items():
            for asp in cat_data.get("aspects", []):
                self._aspect_meta_cache[asp["key"]] = {
                    "category": cat,
                    "label_tr": asp.get("label_tr", asp["key"]),
                    "label_en": asp.get("label_en", asp["key"]),
                    "department": asp.get("department", "genel"),
                }

    def _build_responsibility_index(self) -> None:
        data = self._loader.load_responsibilities()
        for row in data.get("responsibilities", []):
            if row.get("role") == "primary":
                self._responsibilities[row["entity_id"]] = row["department"]

    def _build_relationship_index(self) -> None:
        data = self._loader.load_relationships()
        for rel in data.get("relationships", []):
            if rel.get("type") == "managed_by":
                self._managed_by[rel["from_id"]] = rel["to_id"]

    def _index_synonyms(self) -> None:
        all_syns = self._loader.load_all_synonyms()
        for lang, entries in all_syns.items():
            for entry in entries:
                eid = entry.get("entity_id")
                if not eid:
                    continue
                entity = self._entities.get(eid)
                if not entity:
                    continue
                for term in entry.get("terms", []):
                    self._entity_index.append((
                        normalize_turkish(term.lower()),
                        eid,
                        lang,
                        entity["type"],
                    ))

    def _index_runtime_synonyms(self) -> None:
        for entry in self._runtime_synonyms:
            eid = entry.get("entity_id")
            if not eid or eid not in self._entities:
                continue
            entity = self._entities[eid]
            for term in entry.get("terms", []):
                self._entity_index.append((
                    normalize_turkish(term.lower()),
                    eid,
                    entry.get("lang", "tr"),
                    entity["type"],
                ))

    def _normalize(self, text: str, lang: str) -> str:
        if lang == "tr":
            return normalize_turkish(text.lower())
        return text.lower().strip()

    def resolve_term(self, text: str, lang: str = "tr") -> EntityRef:
        """Resolve text to entity via synonym dictionary."""
        normalized = self._normalize(text, lang)
        tokens = set(tokenize_turkish(normalized)) if lang == "tr" else set(normalized.split())

        best: Optional[tuple[float, str, str, str]] = None  # score, eid, term, etype

        for term, eid, term_lang, etype in self._entity_index:
            if term_lang != lang and term_lang != "tr":
                continue
            score = 0.0
            if term == normalized:
                score = 0.95 + len(term) * 0.01
            elif " " in term and term in normalized:
                score = 0.90 + len(term) * 0.01
            elif term in tokens:
                score = 0.85 + len(term) * 0.01
            elif len(term) >= 3 and term in normalized:
                score = 0.70 + len(term) * 0.01

            if score > 0 and (best is None or score > best[0]):
                best = (score, eid, term, etype)

        if best is None:
            return EntityRef(
                entity_id="",
                entity_type="unknown",
                label="",
                confidence=0.0,
                lang=lang,
                matched_term=text,
            )

        score, eid, term, etype = best
        entity = self._entities[eid]
        label = entity.get("label_en" if lang == "en" else "label_tr", eid)
        dept = entity.get("department", self.get_responsible_department(eid))
        return EntityRef(
            entity_id=eid,
            entity_type=etype,
            label=label,
            confidence=min(0.98, score),
            lang=lang,
            matched_term=term,
            department=dept,
        )

    def map_aspect(self, text: str, lang: str = "tr") -> AspectMapping:
        """Map text to aspect and department."""
        normalized = self._normalize(text, lang)
        tokens = set(tokenize_turkish(normalized)) if lang == "tr" else set(normalized.split())

        best_score = 0.0
        best: Optional[tuple[str, str, str, str, str, str]] = None

        for term, asp_key, category, dept, label_tr, label_en in self._aspect_index:
            score = 0.0
            if term in normalized:
                if " " in term:
                    score = 3.0 + len(term) * 0.1
                elif term in tokens:
                    score = 2.5 + len(term) * 0.1
                else:
                    score = 2.0 + len(term) * 0.1
            if score > best_score:
                best_score = score
                best = (asp_key, category, dept, label_tr, label_en, term)

        # Synonym-based aspect match (from synonym files with aspect_key)
        all_syns = self._loader.load_all_synonyms()
        syn_list = all_syns.get(lang, []) + all_syns.get("tr", [])
        for entry in syn_list:
            asp_key = entry.get("aspect_key")
            if not asp_key:
                continue
            for syn_term in entry.get("terms", []):
                nterm = self._normalize(syn_term, lang)
                if nterm in normalized or nterm in tokens:
                    asp_meta = self._aspect_meta_cache.get(asp_key)
                    if asp_meta:
                        score = 2.8 + len(nterm) * 0.1
                        if score > best_score:
                            best_score = score
                            best = (
                                asp_key,
                                asp_meta["category"],
                                asp_meta["department"],
                                asp_meta["label_tr"],
                                asp_meta["label_en"],
                                nterm,
                            )

        # Entity-based fallback: resolve equipment → responsibility aspects
        entity_ref = self.resolve_term(text, lang)
        if entity_ref.confidence >= 0.7 and entity_ref.entity_id:
            dept = self.get_responsible_department(entity_ref.entity_id)
            resp_data = self._loader.load_responsibilities()
            for row in resp_data.get("responsibilities", []):
                if row["entity_id"] == entity_ref.entity_id:
                    aspect_keys = row.get("aspect_keys", [])
                    if aspect_keys:
                        asp_key = aspect_keys[0]
                        asp_meta = self._get_aspect_meta(asp_key)
                        if asp_meta and best_score < 2.5:
                            return AspectMapping(
                                aspect=asp_key,
                                aspect_label=asp_meta["label_tr"],
                                department=dept,
                                department_label=_dept_label(dept),
                                category=asp_meta["category"],
                                confidence=0.82,
                                method="entity_responsibility",
                                matched_term=entity_ref.matched_term,
                            )

        if best is None:
            return AspectMapping(
                aspect="general",
                aspect_label="Genel",
                department="genel",
                department_label="Genel",
                category="OTHER",
                confidence=0.4,
                method="fallback",
            )

        asp_key, category, dept, label_tr, label_en, matched = best
        label = label_en if lang == "en" else label_tr
        return AspectMapping(
            aspect=asp_key,
            aspect_label=label,
            department=dept,
            department_label=_dept_label(dept),
            category=category,
            confidence=min(0.95, 0.55 + best_score * 0.08),
            method="config_keyword",
            matched_term=matched,
        )

    def _get_aspect_meta(self, aspect_key: str) -> Optional[dict[str, str]]:
        return self._aspect_meta_cache.get(aspect_key)

    def parse_review_segments(self, text: str, lang: str = "tr") -> list[Segment]:
        """Parse review text into segments per Review Parsing Standard."""
        from app.services.absa_service import split_clauses_absa

        clauses = split_clauses_absa(text)
        if not clauses:
            clauses = [text.strip()] if text.strip() else []

        segments: list[Segment] = []
        for idx, clause in enumerate(clauses):
            if not clause.strip():
                continue
            mapping = self.map_aspect(clause, lang=lang)
            sentiment = self._detect_sentiment(clause)
            entity_refs: list[EntityRef] = []

            entity_ref = self.resolve_term(clause, lang=lang)
            if entity_ref.confidence >= 0.65 and entity_ref.entity_id:
                entity_refs.append(entity_ref)

            segments.append(Segment(
                index=len(segments),
                text=clause.strip(),
                aspect=mapping.aspect if mapping.confidence >= 0.5 else None,
                aspect_category=mapping.category if mapping.confidence >= 0.5 else None,
                department=mapping.department if mapping.confidence >= 0.5 else None,
                department_label=mapping.department_label if mapping.confidence >= 0.5 else None,
                sentiment=sentiment,
                confidence=mapping.confidence,
                entity_refs=entity_refs,
            ))

        return segments

    def _detect_sentiment(self, text: str) -> str:
        normalized = normalize_turkish(text.lower())
        tokens = set(tokenize_turkish(normalized))
        pos = sum(1 for w in POSITIVE_WORDS if w in tokens or w in normalized)
        neg = sum(1 for w in NEGATIVE_WORDS if w in tokens or w in normalized)
        neg_phrases = (
            "ses yapiyor", "ses yapıyor", "ses yapiyordu", "cok ses", "çok ses",
            "gurultu", "gürültü", "calismiyor", "çalışmıyor", "bozuk", "kirli",
            "kotu", "kötü", "lezzetsiz",
        )
        pos_phrases = (
            "tertemiz", "cok guzel", "çok güzel", "guzeldi", "güzeldi", "harika",
            "mukemmel", "mükemmel", "lezzetli",
        )
        if any(p in normalized for p in neg_phrases):
            neg += 2
        if any(p in normalized for p in pos_phrases):
            pos += 2
        if "ama" in tokens or "fakat" in tokens:
            neg += 1
        if pos > neg:
            return "positive"
        if neg > pos:
            return "negative"
        return "neutral"

    def get_responsible_department(self, entity_id: str) -> str:
        """Return primary responsible department for entity."""
        if entity_id in self._responsibilities:
            return self._responsibilities[entity_id]
        if entity_id in self._managed_by:
            dept = self._managed_by[entity_id]
            if dept in _DEPT_LABELS or dept.endswith("_hvac") or dept.endswith("_plumbing"):
                return dept
            return dept
        entity = self._entities.get(entity_id)
        if entity:
            return entity.get("department", "genel")
        return "genel"

    def add_synonym(
        self,
        entity_id: str,
        term: str,
        lang: str = "tr",
        aspect_key: str | None = None,
    ) -> None:
        """Add runtime synonym (in-memory until reload)."""
        entry: dict[str, Any] = {
            "entity_id": entity_id if not aspect_key else None,
            "aspect_key": aspect_key,
            "terms": [term],
            "lang": lang,
        }
        if aspect_key:
            entry["entity_id"] = None
        else:
            entry["aspect_key"] = None
        self._runtime_synonyms.append(entry)
        if entity_id and entity_id in self._entities:
            entity = self._entities[entity_id]
            self._entity_index.append((
                normalize_turkish(term.lower()) if lang == "tr" else term.lower(),
                entity_id,
                lang,
                entity["type"],
            ))

    def get_entity(self, entity_id: str) -> Optional[dict[str, Any]]:
        return self._entities.get(entity_id)

    def list_entities(self, entity_type: str | None = None) -> list[dict[str, Any]]:
        if entity_type:
            return [e for e in self._entities.values() if e.get("type") == entity_type]
        return list(self._entities.values())

    def stats(self) -> dict[str, int]:
        """Return seed counts for gap reporting."""
        equipment = sum(1 for e in self._entities.values() if e.get("type") == "equipment")
        human = sum(1 for e in self._entities.values() if e.get("type") == "human")
        physical = sum(
            1 for e in self._entities.values()
            if e.get("type") in ("physical", "facility")
        )
        asp_data = self._loader.load_aspects()
        aspect_count = sum(
            len(cat.get("aspects", []))
            for cat in asp_data.get("categories", {}).values()
        )
        resp_count = len(self._loader.load_responsibilities().get("responsibilities", []))
        syn_count = sum(
            len(e.get("terms", []))
            for syns in self._loader.load_all_synonyms().values()
            for e in syns
        )
        return {
            "equipment": equipment,
            "human": human,
            "physical": physical,
            "aspects": aspect_count,
            "responsibilities": resp_count,
            "synonym_terms": syn_count,
        }


def get_hotel_ontology_engine(config_dir: str | None = None) -> HotelOntologyEngine:
    """Singleton accessor for HotelOntologyEngine."""
    return _get_engine(config_dir)
