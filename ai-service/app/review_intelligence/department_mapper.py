"""Department mapping — ontology responsibility + enterprise taxonomy."""

from __future__ import annotations

from app.review_intelligence.models import DepartmentInfo
from app.ontology.engine import HotelOntologyEngine, get_hotel_ontology_engine
from app.ontology.models import AspectMapping, EntityRef

# Enterprise department routing table (DOC-004)
DEPARTMENT_ROUTING: dict[str, str] = {
    "housekeeping": "Housekeeping",
    "engineering_hvac": "Mühendislik — HVAC",
    "engineering_internet": "Mühendislik — İnternet",
    "engineering_plumbing": "Mühendislik — Tesisat",
    "teknik": "Teknik",
    "restaurant": "Restaurant / F&B",
    "bar": "Bar",
    "personel": "Personel & Hizmet",
    "front_office": "Front Office",
    "spa": "Spa & Wellness",
    "havuz": "Havuz & Aktivite",
    "animasyon": "Animasyon & Etkinlik",
    "guvenlik": "Güvenlik",
    "genel": "Genel Yönetim",
    "oda_hizmetleri_housekeeping": "Kat Hizmetleri & Temizlik",
    "yiyecek_icecek_fb": "Yiyecek & İçecek (F&B)",
    "on_buyro_misafir": "Ön Büro & Misafir İlişkileri",
    "teknik_it": "Teknik Servis & IT",
    "rekreasyon_eglence": "Rekreasyon & Eğlence (Leisure)",
    "cevre_guvenlik_ulasim": "Çevre, Güvenlik & Ulaşım",
    "otel_atmosferi": "Otel Atmosferi & Misafir Profili",
    "personel_davranisi": "Personel Davranışı",
}


class DepartmentMapper:
    """Stage 8: Aspect/entity → responsible department."""

    def __init__(self, engine: HotelOntologyEngine | None = None) -> None:
        self._engine = engine or get_hotel_ontology_engine()

    def map_department(
        self,
        aspect: AspectMapping,
        entities: list[EntityRef],
    ) -> DepartmentInfo:
        dept_key = aspect.department
        if entities:
            entity_dept = self._engine.get_responsible_department(entities[0].entity_id)
            if entity_dept and entity_dept != "genel":
                dept_key = entity_dept

        label = DEPARTMENT_ROUTING.get(dept_key, aspect.department_label)
        return DepartmentInfo(
            key=dept_key,
            label=label,
            confidence=aspect.confidence,
        )
