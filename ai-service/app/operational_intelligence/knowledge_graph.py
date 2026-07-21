"""
Knowledge Graph Engine — builds AOF chains from review clauses.

Pipeline per clause:
  clause → [observation] → [guest_impact] → [process_failure] → [sub_process]
         → [sop_violation] → [root_cause] → [business_impact] → [action]

Cross-clause linking:
  - Merge duplicate facts
  - Detect dependency breaks across departments
  - Build journey cascade
  - Flag new patterns vs known
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from .models import (
    AtomicOperationalFact,
    DependencyNode,
    EscalationInfo,
    Evidence,
    FactType,
    FinancialImpact,
    GuestJourneyPhase,
    LearningSignal,
    OperationalImpact,
    RecoveryAnalysis,
    RecoveryStatus,
    RiskLevel,
    SOPReference,
    SeverityLevel,
)


def _normalize(text: str) -> str:
    tr_to_en = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return text.lower().translate(tr_to_en)


def _pattern(pattern_str: str) -> re.Pattern:
    """Compile a pattern that works on ASCII-normalized text."""
    tr_to_ascii = str.maketrans("çğıöşü", "cgiosu")
    return re.compile(pattern_str.lower().translate(tr_to_ascii))


def _fact_id(prefix: str, review_id: str, idx: int) -> str:
    raw = f"{prefix}_{review_id}_{idx}_{datetime.now(timezone.utc).isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Knowledge base — pattern → AOF chain mappings
# ---------------------------------------------------------------------------

# Note: All patterns use _pattern() for Turkish→ASCII normalization
_OBSERVATION_PATTERNS: dict[str, dict[str, Any]] = {
    "kus_yuvasi": {
        "pattern": _pattern(r"kuş\s*yuvas[ıi]|yuva\s*vard[ıi]"),
        "label": "Bird Nest Found",
        "description": "Misafir odasında kuş yuvası tespit edildi",
        "department": "Kat Hizmetleri",
        "sub_process": "Pre-arrival Inspection",
        "severity": SeverityLevel.CRITICAL,
        "sop_code": "HK-ROOM-001",
        "sop_step": 4,
        "sop_step_name": "Pre-arrival room condition check",
    },
    "klima_ariza": {
        "pattern": _pattern(r"klima\s*(çalışmıyor|bozuk|arızalı|ses\s*yapıyor|soğutmuyor|ısıtmıyor)"),
        "label": "HVAC Malfunction",
        "description": "Klima/ısıtma sistemi çalışmıyor veya yetersiz",
        "department": "Teknik Servis",
        "sub_process": "HVAC Maintenance",
        "severity": SeverityLevel.HIGH,
        "sop_code": "TS-HVAC-001",
        "sop_step": 1,
        "sop_step_name": "Immediate HVAC inspection",
    },
    "havlu_talebi": {
        "pattern": _pattern(r"havlu\s*(ist[e]dik|yoktu|getirmediler|vermediler|ekstra)"),
        "label": "Towel Request Not Fulfilled",
        "description": "Misafir havlü talebi karşılanmamış",
        "department": "Kat Hizmetleri",
        "sub_process": "Guest Request Fulfillment",
        "severity": SeverityLevel.MEDIUM,
        "sop_code": "HK-AMENITY-002",
        "sop_step": 1,
        "sop_step_name": "Deliver requested towel within 15min",
    },
    "yemek_soguk": {
        "pattern": _pattern(r"(yemek|kahvaltı|çorba|ekmek)\s*(soğuk|bayat)"),
        "label": "Food Temperature Issue",
        "description": "Yemekler soğuk servis edilmiş veya bayat",
        "department": "Yiyecek & İçecek",
        "sub_process": "Kitchen Quality Control",
        "severity": SeverityLevel.MEDIUM,
        "sop_code": "FB-KITCHEN-002",
        "sop_step": 3,
        "sop_step_name": "Food temperature check before service",
    },
    "personel_davranis": {
        "pattern": _pattern(r"(personel|garson|resepsiyonist|memur)\s*(kaba|ilgisiz|suratsız|ters|kabaydı|ilgisizdi)"),
        "label": "Staff Attitude Problem",
        "description": "Personel davranışı misafir memnuniyetsizliğine yol açmış",
        "department": "İnsan Kaynakları",
        "sub_process": "Service Attitude",
        "severity": SeverityLevel.HIGH,
        "sop_code": "HR-ATT-001",
        "sop_step": 2,
        "sop_step_name": "Service attitude refresher training",
    },
    "yavas_hizmet": {
        "pattern": _pattern(r"(bekledik|yavaş|gecikti|uzun\s*sürdü)"),
        "label": "Slow Service",
        "description": "Servis hızı beklenenden düşük",
        "department": "Yiyecek & İçecek",
        "sub_process": "Restaurant Service",
        "severity": SeverityLevel.MEDIUM,
        "sop_code": "FB-SERVICE-001",
        "sop_step": 2,
        "sop_step_name": "Service time monitoring",
    },
    "dis_fircasi": {
        "pattern": _pattern(r"diş\s*fırç[ai]s[ıi]|diş\s*fırças[ıi]\s*gelmedi"),
        "label": "Missing Toothbrush",
        "description": "Misafir talebine rağmen diş fırçası teslim edilmemiş",
        "department": "Kat Hizmetleri",
        "sub_process": "Guest Request Fulfillment",
        "severity": SeverityLevel.MEDIUM,
        "sop_code": "HK-AMENITY-003",
        "sop_step": 2,
        "sop_step_name": "Deliver requested amenity within 15min",
    },
    "havlu_alinmis": {
        "pattern": _pattern(r"havlu[lar]?\s*(alınmış|toplanmış|göt[ü]r[ü]lmüş)"),
        "label": "Towels Removed Without Replacement",
        "description": "Kirli havlular alınmış ancak temiz havlular bırakılmamış",
        "department": "Kat Hizmetleri",
        "sub_process": "Linen Management",
        "severity": SeverityLevel.MEDIUM,
        "sop_code": "HK-LINEN-002",
        "sop_step": 3,
        "sop_step_name": "Replace towels immediately after removal",
    },
    "takip_eksik": {
        "pattern": _pattern(r"takip\s*(eksik|yok|hatırlatma)"),
        "label": "Follow-up Failure",
        "description": "Misafir talepleri düzenli takip edilmiyor, birden çok hatırlatma gerekiyor",
        "department": "Kat Hizmetleri",
        "sub_process": "Guest Follow-up",
        "severity": SeverityLevel.HIGH,
        "sop_code": "HK-SERVICE-005",
        "sop_step": 1,
        "sop_step_name": "Log and track every guest request",
    },
    "yemek_kalite": {
        "pattern": _pattern(r"yemek\s*(kalites[ıi]|lezzet)\s*(düşük|k[öo]t[uü]|az)"),
        "label": "Food Quality Below Standard",
        "description": "Yemek kalitesi, lezzet ve çeşitlilik beklentinin altında",
        "department": "Yiyecek & İçecek",
        "sub_process": "Kitchen Quality Control",
        "severity": SeverityLevel.HIGH,
        "sop_code": "FB-KITCHEN-001",
        "sop_step": 5,
        "sop_step_name": "Daily chef tasting and quality sign-off",
    },
    "icecek_yetersiz": {
        "pattern": _pattern(r"iç[ei]cek\s*(yetersiz|az|yetmez)"),
        "label": "Insufficient Beverage Service",
        "description": "İçecek çeşitliliği veya miktarı yetersiz",
        "department": "Yiyecek & İçecek",
        "sub_process": "Beverage Inventory & Service",
        "severity": SeverityLevel.MEDIUM,
        "sop_code": "FB-BEVERAGE-002",
    },
    "kokteyl_bilmiyor": {
        "pattern": _pattern(r"kokteyl\s*(bilmiyor|nedir|yok)"),
        "label": "Bartender Cocktail Knowledge Gap",
        "description": "Bar personeli kokteyl hazırlama bilgisine sahip değil",
        "department": "Yiyecek & İçecek",
        "sub_process": "Bar Staff Training",
        "severity": SeverityLevel.MEDIUM,
        "sop_code": "FB-BAR-001",
        "sop_step": 3,
        "sop_step_name": "Bartender cocktail certification",
    },
    "personel_egitimsiz": {
        "pattern": _pattern(r"personel\s*(eğitimsiz|bilinçsiz|deneyimsiz)"),
        "label": "Staff Training Deficiency",
        "description": "Personel genel hizmet ve davranış eğitimi eksik",
        "department": "İnsan Kaynakları",
        "sub_process": "Staff Onboarding & Training",
        "severity": SeverityLevel.HIGH,
        "sop_code": "HR-TRAIN-001",
        "sop_step": 1,
        "sop_step_name": "Mandatory service training before floor assignment",
    },
    "denetim_yok": {
        "pattern": _pattern(r"denetim\s*(yok|eksik|gözetim)"),
        "label": "Quality Audit Failure",
        "description": "Operasyonel denetim mekanizması çalışmıyor",
        "department": "Kalite Yönetimi",
        "sub_process": "Daily Quality Audit",
        "severity": SeverityLevel.CRITICAL,
        "sop_code": "QA-AUDIT-001",
    },
    "oda_temizlenmemis": {
        "pattern": _pattern(r"(temizlenmemiş|temizlik\s*yapılmamış)"),
        "label": "Room Not Cleaned After Incident",
        "description": "Olay sonrası derin temizlik yapılmamış",
        "department": "Kat Hizmetleri",
        "sub_process": "Post-incident Deep Cleaning",
        "severity": SeverityLevel.HIGH,
        "sop_code": "HK-ROOM-003",
        "sop_step": 2,
        "sop_step_name": "Deep clean room after any hygiene incident",
    },
    "hijyen_eksik": {
        "pattern": _pattern(r"hiyen|hiyen\s*(eksik|kötü|problemi)"),
        "label": "Hygiene Standard Violation",
        "description": "Genel hijyen standartları karşılanmamış",
        "department": "Kat Hizmetleri",
        "sub_process": "Hygiene Control",
        "severity": SeverityLevel.CRITICAL,
        "sop_code": "HK-HYGIENE-001",
    },
    "tavsiye_etmiyor": {
        "pattern": _pattern(r"tavsiye\s*etmiy[o]rum|önermiy[o]rum"),
        "label": "Guest Will Not Recommend",
        "description": "Misafir oteli başkalarına tavsiye etmeyecek",
        "department": "Yönetim",
        "sub_process": "Guest Satisfaction",
        "severity": SeverityLevel.HIGH,
    },
}

_DEPENDENCY_CHAINS: dict[str, list[dict[str, str]]] = {
    "Missing Toothbrush": [
        {"department": "Ön Büro", "process": "Guest Request Logging", "status": "unknown"},
        {"department": "Kat Hizmetleri", "process": "Task Assignment", "status": "unknown"},
        {"department": "Kat Hizmetleri", "process": "Amenity Delivery", "status": "unknown"},
        {"department": "Kat Hizmetleri", "process": "Supervisor Verification", "status": "unknown"},
        {"department": "Kat Hizmetleri", "process": "Completion Confirmation", "status": "unknown"},
    ],
    "Staff Training Deficiency": [
        {"department": "İnsan Kaynakları", "process": "Recruitment", "status": "unknown"},
        {"department": "İnsan Kaynakları", "process": "Onboarding Training", "status": "unknown"},
        {"department": "Departman", "process": "On-the-job Coaching", "status": "unknown"},
        {"department": "Kalite Yönetimi", "process": "Performance Audit", "status": "unknown"},
    ],
    "Quality Audit Failure": [
        {"department": "Kalite Yönetimi", "process": "Daily Walk-through", "status": "unknown"},
        {"department": "Departman Yöneticileri", "process": "Shift Sign-off", "status": "unknown"},
        {"department": "Yönetim", "process": "Weekly Review", "status": "unknown"},
    ],
}

_RECOVERY_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"(kaldırıldı|temizlendi|değiştirildi|getirildi|yapıldı|onarıldı)"), "ATTEMPTED", "Müdahale edilmiş"),
    (re.compile(r"(ama\s+|ancak\s+|fakat\s+)(yine\s+|hala\s+|hâlâ\s+)?(temizlenmemiş|yapılmamış|düzelmemiş|gelmemiş|çözülmemiş|değişmemiş)"), "FAILED", "Müdahaleye rağmen sorun çözülmemiş"),
    (re.compile(r"(özür|teşekkür|telafi|compensation|indirim|ücretsiz)"), "COMPENSATED", "Telafi sunulmuş"),
    (re.compile(r"(söyledik|bildirdik|ilettik|şikayet\s*ettik)"), "REPORTED", "Sorun bildirilmiş"),
]

_ESCALATION_MAP: dict[SeverityLevel, dict[str, Any]] = {
    SeverityLevel.CRITICAL: {
        "level": "critical",
        "notify_roles": ["Kat Hizmetleri Müdürü", "Kalite Müdürü", "Nöbetçi Müdür"],
    },
    SeverityLevel.HIGH: {
        "level": "high",
        "notify_roles": ["Departman Müdürü", "Kalite Sorumlusu"],
    },
    SeverityLevel.MEDIUM: {
        "level": "medium",
        "notify_roles": ["Departman Şefi"],
    },
    SeverityLevel.LOW: {
        "level": "low",
        "notify_roles": ["Departman Sorumlusu"],
    },
    SeverityLevel.INFO: {
        "level": "info",
        "notify_roles": [],
    },
}

_FINANCIAL_IMPACT_MAP: dict[str, dict[str, RiskLevel]] = {
    "tavsiye_etmiyor": {
        "revenue_risk": RiskLevel.HIGH,
        "ota_visibility_risk": RiskLevel.HIGH,
        "brand_risk": RiskLevel.HIGH,
    },
    "kus_yuvasi": {
        "revenue_risk": RiskLevel.CRITICAL,
        "ota_visibility_risk": RiskLevel.CRITICAL,
        "brand_risk": RiskLevel.CRITICAL,
    },
    "hijyen_eksik": {
        "revenue_risk": RiskLevel.CRITICAL,
        "ota_visibility_risk": RiskLevel.HIGH,
        "brand_risk": RiskLevel.CRITICAL,
    },
}

_KNOWN_PATTERNS: set[str] = {
    "Pre-arrival Inspection Failure",
    "Guest Request Fulfillment Failure",
    "Linen Management Failure",
    "Guest Follow-up Failure",
    "Kitchen Quality Control Failure",
    "Beverage Inventory & Service Failure",
    "Bar Staff Training Failure",
    "Staff Onboarding & Training Failure",
    "Daily Quality Audit Failure",
    "Post-incident Deep Cleaning Failure",
    "Hygiene Control Failure",
    "Guest Satisfaction Failure",
    "Guest Request Fulfillment Delay",
    "Linen Management Gap",
    "Follow-up Process Failure",
    "Beverage Inventory Shortage",
    "Staff Training Deficiency",
    "Quality Audit Failure",
    "Hygiene Standard Violation",
    "Bar Staff Knowledge Gap",
}


class KnowledgeGraphBuilder:
    """Builds a linked AOF graph from a single review's clauses."""

    def __init__(self) -> None:
        self._observation_cache: dict[str, dict[str, Any]] = {}

    def build(
        self,
        clauses: list[str],
        review_id: str,
        rating: Optional[int] = None,
    ) -> list[AtomicOperationalFact]:
        facts: list[AtomicOperationalFact] = []

        for i, clause in enumerate(clauses):
            clause_facts = self._analyze_clause(clause, review_id, i)
            facts.extend(clause_facts)

        facts = self._deduplicate(facts)
        facts = self._link_facts(facts)
        facts = self._resolve_journey(facts)
        facts = self._mark_learning(facts)
        facts = self._inject_dependency_breaks(facts)

        return facts

    def _analyze_clause(
        self,
        clause: str,
        review_id: str,
        idx: int,
    ) -> list[AtomicOperationalFact]:
        norm = _normalize(clause)
        clause_facts: list[AtomicOperationalFact] = []

        matched = self._match_patterns(norm, clause)
        if not matched:
            return clause_facts

        for pattern_key, info in matched:
            # 1. Observation
            obs_fact = self._make_fact(
                fact_type=FactType.OBSERVATION,
                label=info["label"],
                description=info["description"],
                clause=clause,
                norm=norm,
                pattern_key=pattern_key,
                confidence=0.95,
                review_id=review_id,
                idx=idx,
                department=info.get("department", ""),
                sub_process=info.get("sub_process", ""),
                severity=info.get("severity", SeverityLevel.MEDIUM),
                sop_code=info.get("sop_code"),
                sop_step=info.get("sop_step"),
                sop_step_name=info.get("sop_step_name"),
            )
            clause_facts.append(obs_fact)

            # 2. Guest Impact
            impact_desc = self._infer_guest_impact(info["label"], clause)
            impact_fact = self._make_fact(
                fact_type=FactType.GUEST_IMPACT,
                label=f"{info['label']} → Guest Impact",
                description=impact_desc,
                clause=clause,
                norm=norm,
                pattern_key=pattern_key,
                confidence=0.85,
                review_id=review_id,
                idx=idx,
                parent_ids=[obs_fact.fact_id],
                department=info.get("department", ""),
                sub_process=info.get("sub_process", ""),
                severity=info.get("severity", SeverityLevel.MEDIUM),
            )
            clause_facts.append(impact_fact)

            # 3. Process Failure
            pf_label = self._infer_process_failure(info["sub_process"])
            pf_fact = self._make_fact(
                fact_type=FactType.PROCESS_FAILURE,
                label=pf_label,
                description=f"{info.get('sub_process', '')} süreci başarısız",
                clause=clause,
                norm=norm,
                pattern_key=pattern_key,
                confidence=0.90,
                review_id=review_id,
                idx=idx,
                parent_ids=[impact_fact.fact_id],
                department=info.get("department", ""),
                sub_process=info.get("sub_process", ""),
                severity=info.get("severity", SeverityLevel.MEDIUM),
            )
            clause_facts.append(pf_fact)

            # 4. SOP Violation
            if info.get("sop_code"):
                sop_fact = self._make_fact(
                    fact_type=FactType.SOP_VIOLATION,
                    label=f"SOP {info['sop_code']} Step {info.get('sop_step', '?')} Violated",
                    description=f"{info['sop_code']} prosedürünün {info.get('sop_step', '?')}. adımı atlanmış/uygulanmamış",
                    clause=clause,
                    norm=norm,
                    pattern_key=pattern_key,
                    confidence=0.85,
                    review_id=review_id,
                    idx=idx,
                    parent_ids=[pf_fact.fact_id],
                    department=info.get("department", ""),
                    sub_process=info.get("sub_process", ""),
                    severity=info.get("severity", SeverityLevel.MEDIUM),
                    sop_code=info.get("sop_code"),
                    sop_step=info.get("sop_step"),
                    sop_step_name=info.get("sop_step_name"),
                )
                clause_facts.append(sop_fact)

            # 5. Root cause
            rc_candidates = self._infer_root_causes(info["label"])
            rc_fact = self._make_fact(
                fact_type=FactType.ROOT_CAUSE,
                label=f"Root Cause: {info['label']}",
                description=rc_candidates[0] if rc_candidates else "Bilinmiyor",
                clause=clause,
                norm=norm,
                pattern_key=pattern_key,
                confidence=0.75,
                review_id=review_id,
                idx=idx,
                parent_ids=[pf_fact.fact_id],
                department=info.get("department", ""),
                sub_process=info.get("sub_process", ""),
                root_cause_candidates=rc_candidates,
            )
            clause_facts.append(rc_fact)

            # 6. Business impact
            biz_fact = self._make_fact(
                fact_type=FactType.BUSINESS_IMPACT,
                label=f"Business Impact: {info['label']}",
                description=self._infer_business_impact(info["label"]),
                clause=clause,
                norm=norm,
                pattern_key=pattern_key,
                confidence=0.80,
                review_id=review_id,
                idx=idx,
                parent_ids=[rc_fact.fact_id],
                department=info.get("department", ""),
                severity=info.get("severity", SeverityLevel.MEDIUM),
            )
            clause_facts.append(biz_fact)

            # 7. Action
            action_fact = self._make_fact(
                fact_type=FactType.ACTION,
                label=f"Action Required: {info['label']}",
                description=self._infer_action(info),
                clause=clause,
                norm=norm,
                pattern_key=pattern_key,
                confidence=0.85,
                review_id=review_id,
                idx=idx,
                parent_ids=[biz_fact.fact_id, rc_fact.fact_id],
                department=info.get("department", ""),
                sub_process=info.get("sub_process", ""),
                severity=SeverityLevel.INFO,
                recommended_action=self._infer_action(info),
                action_owner=info.get("department", ""),
            )
            clause_facts.append(action_fact)

        # Recovery analysis
        recovery_facts = self._analyze_recovery(clause, norm, review_id, idx, clause_facts)
        clause_facts.extend(recovery_facts)

        # Escalation
        escalations = self._infer_escalation(clause_facts)
        clause_facts.extend(escalations)

        # Financial impact
        financial = self._infer_financial(clause_facts, pattern_key if matched else "")
        clause_facts.extend(financial)

        # Dependency
        deps = self._infer_dependency(clause_facts)
        clause_facts.extend(deps)

        return clause_facts

    def _match_patterns(
        self, norm: str, raw: str
    ) -> list[tuple[str, dict[str, Any]]]:
        results: list[tuple[str, dict[str, Any]]] = []
        raw_lower = raw.lower()
        for key, info in _OBSERVATION_PATTERNS.items():
            pat = info["pattern"]
            if pat.search(norm) or pat.search(raw_lower):
                results.append((key, info))
        return results

    def _make_fact(
        self,
        fact_type: FactType,
        label: str,
        description: str,
        clause: str,
        norm: str,
        pattern_key: str,
        confidence: float,
        review_id: str,
        idx: int,
        parent_ids: Optional[list[str]] = None,
        department: str = "",
        sub_process: str = "",
        severity: SeverityLevel = SeverityLevel.INFO,
        sop_code: Optional[str] = None,
        sop_step: Optional[int] = None,
        sop_step_name: Optional[str] = None,
        root_cause_candidates: Optional[list[str]] = None,
        recommended_action: str = "",
        action_owner: str = "",
    ) -> AtomicOperationalFact:
        fid = _fact_id(f"{fact_type.value}_{pattern_key}", review_id, idx)
        ev = Evidence(
            clause=clause,
            normalized_clause=norm,
            confidence=confidence,
            matched_terms=[pattern_key],
        )
        sop = None
        if sop_code:
            sop = SOPReference(
                code=sop_code,
                step_number=sop_step,
                step_name=sop_step_name or "",
                step_skipped=True,
                department=department,
            )

        return AtomicOperationalFact(
            fact_id=fid,
            fact_type=fact_type,
            label=label,
            description=description,
            evidence=[ev],
            confidence=confidence,
            parent_fact_ids=parent_ids or [],
            department=department,
            sub_process=sub_process,
            sop=sop,
            severity=severity,
            root_cause_candidates=root_cause_candidates or [],
            recommended_action=recommended_action,
            action_owner=action_owner,
            source_review_id=review_id,
            source_clause_index=idx,
        )

    def _infer_guest_impact(self, label: str, clause: str) -> str:
        m = re.search(r"(hijyen|temizlenmemiş|kirli|kötü|rahatsız|mutsuz|can\s*sıkıntısı)", clause, re.IGNORECASE)
        if m:
            return f"Misafir hijyen/memnuniyet endişesi: {m.group(1)}"
        return f"Misafir deneyimi olumsuz etkilenmiş: {label}"

    def _infer_process_failure(self, sub_process: str) -> str:
        return f"{sub_process} Failure" if sub_process else "Operasyonel Süreç Başarısızlığı"

    def _infer_root_causes(self, label: str) -> list[str]:
        cause_map: dict[str, list[str]] = {
            "Bird Nest Found": [
                "Checklist atlanmış",
                "Supervisor denetimi yapılmamış",
                "Oda kontrol edilmeden serbest bırakılmış",
            ],
            "Missing Toothbrush": [
                "İstek kaydedilmemiş",
                "Görev hiç açılmamış",
                "Odaya iletilmemiş",
            ],
            "Towels Removed Without Replacement": [
                "Değişim prosedürü atlanmış",
                "Stok takibi yapılmamış",
                "Personel eğitimi eksik",
            ],
            "Follow-up Failure": [
                "Talep takip sistemi kullanılmıyor",
                "Personel sorumluluk bilinci eksik",
                "Yönetici geribildirim mekanizması yok",
            ],
            "Food Quality Below Standard": [
                "Şef tadımı yapılmamış",
                "Malzeme kalitesi düşmüş",
                "Porsiyon kontrolü yok",
            ],
            "Bartender Cocktail Knowledge Gap": [
                "Kokteyl eğitimi alınmamış",
                "Menü bilgisi güncellenmemiş",
                "Bar şefi denetimi yok",
            ],
            "Staff Training Deficiency": [
                "İşbaşı eğitimi yetersiz",
                "Oryantasyon programı eksik",
                "Performans takibi yapılmıyor",
            ],
            "Quality Audit Failure": [
                "Günlük denetim yapılmıyor",
                "Denetim formu doldurulmuyor",
                "Üst yönetim bilgilendirilmiyor",
            ],
        }
        return cause_map.get(label, ["Süreç iyileştirme gerekiyor"])

    def _infer_business_impact(self, label: str) -> str:
        high_risk = {
            "Bird Nest Found": "Yüksek itibar riski, potansiyel hijyen skandalı",
            "Hygiene Standard Violation": "Yüksek itibar riski, sağlık denetimi riski",
            "Missing Toothbrush": "Düşük memnuniyet, tekrar ziyaret riski",
            "Quality Audit Failure": "Sistematik kalite düşüşü, zincirleme başarısızlık",
        }
        return high_risk.get(label, "Orta düzey operasyonel risk")

    def _infer_action(self, info: dict[str, Any]) -> str:
        action_map: dict[str, str] = {
            "Bird Nest Found": "Tüm pre-arrival oda denetimleri gözden geçirilmeli",
            "Missing Toothbrush": "Misafir talep takip sistemi revize edilmeli; tüm talepler dijital kayıt altına alınmalı",
            "Towels Removed Without Replacement": "Havlu değişim prosedürü hatırlatılmalı; stok kontrolü artırılmalı",
            "Follow-up Failure": "Takip sorumlusu atanmalı; bekleme süresi KPI'a bağlanmalı",
            "Food Quality Below Standard": "Günlük şef tadımı zorunlu hale getirilmeli; malzeme tedarik zinciri gözden geçirilmeli",
            "Bartender Cocktail Knowledge Gap": "Tüm bar personeline kokteyl eğitimi verilmeli; menü bilgi kartları hazırlanmalı",
            "Staff Training Deficiency": "Kapsamlı hizmet içi eğitim programı başlatılmalı; her personele mentor atanmalı",
            "Quality Audit Failure": "Günlük kalite denetim formu zorunlu tutulmalı; sonuçlar haftalık toplantıda değerlendirilmeli",
            "Room Not Cleaned After Incident": "Olay sonrası derin temizlik protokolü uygulanmalı; temizlik kontrol listesi imzalanmalı",
            "Hygiene Standard Violation": "Acil hijyen denetimi başlatılmalı; tüm oda ve ortak alanlar taranmalı",
            "Insufficient Beverage Service": "İçecek stok ve çeşitlilik analizi yapılmalı; menü güncellenmeli",
        }
        sub = info.get("sub_process", "")
        label = info.get("label", "")
        return action_map.get(label, f"{sub} süreci incelenmeli ve iyileştirme planı hazırlanmalı")

    def _analyze_recovery(
        self,
        clause: str,
        norm: str,
        review_id: str,
        idx: int,
        existing: list[AtomicOperationalFact],
    ) -> list[AtomicOperationalFact]:
        facts: list[AtomicOperationalFact] = []
        current_status = RecoveryStatus.NOT_ATTEMPTED
        failure_reason = ""
        gap = ""

        full_text = f"{clause} {norm}"
        for pat, status_label, desc in _RECOVERY_PATTERNS:
            if pat.search(full_text):
                if status_label == "ATTEMPTED":
                    current_status = RecoveryStatus.ATTEMPTED_SUCCESSFUL
                elif status_label == "FAILED":
                    current_status = RecoveryStatus.ATTEMPTED_FAILED
                    failure_reason = self._infer_recovery_failure(clause)
                    gap = "Derin temizlik/adresleme yapılmamış"
                elif status_label == "COMPENSATED":
                    current_status = RecoveryStatus.ATTEMPTED_SUCCESSFUL if current_status == RecoveryStatus.NOT_ATTEMPTED else current_status
                elif status_label == "REPORTED":
                    if current_status == RecoveryStatus.NOT_ATTEMPTED:
                        current_status = RecoveryStatus.ATTEMPTED_PARTIAL
                        gap = "Sorun bildirilmiş ancak çözüm tamamlanmamış"

        if current_status != RecoveryStatus.NOT_ATTEMPTED:
            recovery_fact = AtomicOperationalFact(
                fact_id=_fact_id("recovery", review_id, idx),
                fact_type=FactType.RECOVERY_ATTEMPT
                if current_status in (RecoveryStatus.ATTEMPTED_SUCCESSFUL, RecoveryStatus.ATTEMPTED_PARTIAL)
                else FactType.RECOVERY_FAILURE,
                label=f"Recovery: {current_status.value}",
                description=gap or f"Kurtarma girişimi: {current_status.value}",
                evidence=[Evidence(clause=clause, normalized_clause=norm, confidence=0.80)],
                confidence=0.80,
                parent_fact_ids=[f.fact_id for f in existing if f.fact_type == FactType.OBSERVATION],
                recovery=RecoveryAnalysis(
                    status=current_status,
                    attempt_description=f"Misafir bildirimine müdahale edilmiş: {clause[:60]}...",
                    failure_reason=failure_reason,
                    gap=gap,
                ),
                severity=SeverityLevel.MEDIUM,
                source_review_id=review_id,
                source_clause_index=idx,
            )
            facts.append(recovery_fact)

        return facts

    def _infer_recovery_failure(self, clause: str) -> str:
        clause_lower = clause.lower()
        if "temizlenmemiş" in clause_lower or "temizlik" in clause_lower:
            return "Derin temizlik yapılmamış"
        if "gelmedi" in clause_lower or "getirilmemiş" in clause_lower:
            return "Teslimat tamamlanmamış"
        if "değişmemiş" in clause_lower or "düzelmemiş" in clause_lower:
            return "Sorun adreslenmemiş"
        return "Müdahale eksik kalmış"

    def _infer_escalation(
        self, facts: list[AtomicOperationalFact]
    ) -> list[AtomicOperationalFact]:
        escalated: list[AtomicOperationalFact] = []
        for fact in facts:
            if fact.fact_type != FactType.PROCESS_FAILURE:
                continue
            sev = fact.severity
            if sev not in (SeverityLevel.HIGH, SeverityLevel.CRITICAL):
                continue
            esc_info = _ESCALATION_MAP.get(sev, _ESCALATION_MAP[SeverityLevel.INFO])
            esc_fact = AtomicOperationalFact(
                fact_id=_fact_id("escalation", fact.source_review_id, fact.source_clause_index),
                fact_type=FactType.ESCALATION,
                label=f"Escalation Required: {fact.label}",
                description=f"{sev.value} seviye — {' → '.join(esc_info['notify_roles'])} bilgilendirilmeli",
                evidence=fact.evidence,
                confidence=0.90,
                parent_fact_ids=[fact.fact_id],
                department=fact.department,
                severity=sev,
                escalation=EscalationInfo(
                    required=True,
                    level=esc_info["level"],
                    notify_roles=esc_info["notify_roles"],
                    reason=f"{fact.label}: {fact.description}",
                ),
                source_review_id=fact.source_review_id,
                source_clause_index=fact.source_clause_index,
            )
            escalated.append(esc_fact)
        return escalated

    def _infer_financial(
        self, facts: list[AtomicOperationalFact], pattern_key: str
    ) -> list[AtomicOperationalFact]:
        if pattern_key in _FINANCIAL_IMPACT_MAP:
            risk = _FINANCIAL_IMPACT_MAP[pattern_key]
            fi = FinancialImpact(
                revenue_risk=risk.get("revenue_risk", RiskLevel.NONE),
                ota_visibility_risk=risk.get("ota_visibility_risk", RiskLevel.NONE),
                brand_risk=risk.get("brand_risk", RiskLevel.NONE),
            )

            obs_facts = [f for f in facts if f.fact_type == FactType.OBSERVATION]
            parent_id = obs_facts[0].fact_id if obs_facts else ""
            fin_fact = AtomicOperationalFact(
                fact_id=_fact_id("financial", facts[0].source_review_id if facts else "", 0),
                fact_type=FactType.FINANCIAL_RISK,
                label=f"Financial Impact: {pattern_key}",
                description=f"Revenue: {fi.revenue_risk.value}, OTA: {fi.ota_visibility_risk.value}, Brand: {fi.brand_risk.value}",
                evidence=facts[0].evidence if facts else [],
                confidence=0.75,
                parent_fact_ids=[parent_id] if parent_id else [],
                financial_impact=fi,
                severity=SeverityLevel.HIGH if fi.revenue_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else SeverityLevel.MEDIUM,
                source_review_id=facts[0].source_review_id if facts else "",
                source_clause_index=facts[0].source_clause_index if facts else -1,
            )
            return [fin_fact]
        return []

    def _infer_dependency(
        self, facts: list[AtomicOperationalFact]
    ) -> list[AtomicOperationalFact]:
        deps: list[AtomicOperationalFact] = []
        for fact in facts:
            if fact.fact_type != FactType.OBSERVATION:
                continue
            chain_def = _DEPENDENCY_CHAINS.get(fact.label)
            if not chain_def:
                continue
            dep_nodes = [DependencyNode(**node) for node in chain_def]
            break_point = None
            for i, node in enumerate(dep_nodes):
                if node.status == "unknown":
                    break_point = f"{node.department}/{node.process}"
                    node.status = "failed" if i > 0 else "blocked"
                    if i > 0 and dep_nodes[i - 1].status == "failed":
                        pass
                    break

            dep_fact = AtomicOperationalFact(
                fact_id=_fact_id("dependency", fact.source_review_id, fact.source_clause_index),
                fact_type=FactType.DEPENDENCY_ISSUE,
                label=f"Dependency Chain: {fact.label}",
                description=f"Zincir kırılma noktası: {break_point or 'bilinmiyor'}",
                evidence=fact.evidence,
                confidence=0.80,
                parent_fact_ids=[fact.fact_id],
                department=fact.department,
                dependency_chain=dep_nodes,
                dependency_break=break_point,
                severity=SeverityLevel.MEDIUM if break_point else SeverityLevel.LOW,
                source_review_id=fact.source_review_id,
                source_clause_index=fact.source_clause_index,
            )
            deps.append(dep_fact)
        return deps

    def _deduplicate(self, facts: list[AtomicOperationalFact]) -> list[AtomicOperationalFact]:
        seen: set[str] = set()
        unique: list[AtomicOperationalFact] = []
        for f in facts:
            key = f"{f.fact_type.value}_{f.label}_{f.department}"
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique

    def _link_facts(self, facts: list[AtomicOperationalFact]) -> list[AtomicOperationalFact]:
        id_map = {f.fact_id: f for f in facts}
        for fact in facts:
            children = []
            for fid, other in id_map.items():
                if fact.fact_id in other.parent_fact_ids:
                    children.append(fid)
            fact.child_fact_ids = children
        return facts

    def _resolve_journey(self, facts: list[AtomicOperationalFact]) -> list[AtomicOperationalFact]:
        if not facts:
            return facts

        observations = [f for f in facts if f.fact_type == FactType.OBSERVATION]
        first_high_sev_idx = -1
        for i, obs in enumerate(observations):
            if obs.severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL):
                first_high_sev_idx = i
                break

        if first_high_sev_idx >= 0 and first_high_sev_idx + 1 < len(observations):
            for j in range(first_high_sev_idx + 1, min(first_high_sev_idx + 3, len(observations))):
                later_obs = observations[j]
                trigger = observations[first_high_sev_idx]
                cascade_label = f"Journey Cascade: {trigger.label} → {later_obs.label}"
                if any(f.label == cascade_label for f in facts):
                    continue
                ji_fact = AtomicOperationalFact(
                    fact_id=_fact_id("journey", trigger.source_review_id, trigger.source_clause_index),
                    fact_type=FactType.JOURNEY_IMPACT,
                    label=cascade_label,
                    description=f"Önceki olay ({trigger.label}) misafir ruh halini olumsuz etkilemiş, "
                    f"bu nedenle {later_obs.label} daha sert değerlendirilmiş olabilir",
                    evidence=later_obs.evidence,
                    confidence=0.65,
                    parent_fact_ids=[trigger.fact_id, later_obs.fact_id],
                    journey_phase=GuestJourneyPhase.STAY,
                    journey_cascade=f"Zincir: {trigger.label} → mood↓ → {later_obs.label} harsh judgment",
                    severity=SeverityLevel.MEDIUM,
                )
                facts.append(ji_fact)
        return facts

    def _mark_learning(self, facts: list[AtomicOperationalFact]) -> list[AtomicOperationalFact]:
        learning_facts: list[AtomicOperationalFact] = []
        for fact in facts:
            if fact.fact_type in (FactType.PROCESS_FAILURE, FactType.TRAINING_GAP):
                is_new = fact.label not in _KNOWN_PATTERNS
                fact.learning = LearningSignal(
                    is_new_pattern=is_new,
                    pattern_id=_fact_id("pattern", fact.source_review_id, fact.source_clause_index),
                    pattern_description=f"Yeni pattern: {fact.label}" if is_new else f"Bilinen pattern: {fact.label}",
                )
                if is_new:
                    np_fact = AtomicOperationalFact(
                        fact_id=_fact_id("new_pattern", fact.source_review_id, fact.source_clause_index),
                        fact_type=FactType.NEW_PATTERN,
                        label=f"New Pattern: {fact.label}",
                        description=f"Bu yorumdan yeni öğrenilen pattern: {fact.label}",
                        evidence=fact.evidence,
                        confidence=fact.confidence * 0.9,
                        parent_fact_ids=[fact.fact_id],
                        department=fact.department,
                        sub_process=fact.sub_process,
                        learning=LearningSignal(
                            is_new_pattern=True,
                            pattern_id=_fact_id("pattern", fact.source_review_id, fact.source_clause_index),
                            pattern_description=f"Yeni tespit: {fact.label}",
                        ),
                        severity=SeverityLevel.MEDIUM,
                        source_review_id=fact.source_review_id,
                        source_clause_index=fact.source_clause_index,
                    )
                    learning_facts.append(np_fact)
        facts.extend(learning_facts)
        return facts

    def _inject_dependency_breaks(self, facts: list[AtomicOperationalFact]) -> list[AtomicOperationalFact]:
        return facts

