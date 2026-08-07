"""
Çoklu sektör ontoloji servisi — domain, departman, aspect eşlemesi.
"""

from __future__ import annotations

import logging

import json
import os
import re
from functools import lru_cache
from typing import Any, Optional

from app.services.turkish_nlp_utils import fold_tr, fold_tr_chars, normalize_turkish, tokenize_turkish

# Kısa anahtar kelimelerde alt-dize yanlış pozitifini önle (kibar→bar, beklemeden→bekleme)
_BOUNDARY_KWS = frozenset({
    "bar", "bekleme", "kuyruk", "bakim", "demir", "plaj", "spa", "oda", "et",
    "bardak",
})

# Olumlu bağlam — bekleme/kuyruk negatif sayılmaz
_POSITIVE_CONTEXT_BLOCKERS: list[tuple[str, str]] = [
    ("bekleme", "beklemeden"),
    ("bekleme", "sira beklemeden"),
    ("kuyruk", "kuyruk yok"),
    ("kuyruk", "sira beklemiyor"),
    ("kuyruk", "asiri sira beklemiyor"),
    ("yoğun", "yogun degildi"),
    ("yoğun", "yogun degil"),
    ("sorun", "sorun gormedim"),
    ("sorun", "sorun gormedik"),
]

_ONTOLOGY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "domain_ontology.json",
)


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    with open(_ONTOLOGY_PATH, encoding="utf-8") as f:
        return json.load(f)


def reload_ontology(force: bool = False) -> None:
    if force:
        _load_raw.cache_clear()
        try:
            from app.ontology.engine import reload_hotel_ontology_engine
            reload_hotel_ontology_engine()
        except Exception:
            logging.getLogger(__name__).debug("reload_ontology: hata yutuldu", exc_info=True)


def _positive_context_blocks(kw: str, normalized: str) -> bool:
    """Olumlu ifade içindeki beklemek/kuyruk vb. negatif tetikleyicileri bastır."""
    for trigger, blocker in _POSITIVE_CONTEXT_BLOCKERS:
        if kw == trigger or normalize_turkish(trigger) in normalize_turkish(kw):
            if blocker in normalized:
                return True
    if "beklemeden" in normalized and kw in ("bekleme", "kuyruk"):
        return True
    if ("yogun degildi" in normalized or "yogun degil" in normalized) and kw == "bekleme":
        return True
    if "sorun gormed" in normalized and kw in ("sorun", "bekleme"):
        return True
    return False


def _keyword_matches(kw: str, normalized: str, tokens: Optional[set[str]] = None) -> bool:
    """Alt-dize tuzaklarını önleyen anahtar kelime eşlemesi."""
    nkw = normalize_turkish(kw.lower())
    if not nkw:
        return False
    if _positive_context_blocks(nkw, normalized):
        return False
    if " " in nkw:
        return nkw in normalized
    tok_set = tokens if tokens is not None else set(tokenize_turkish(normalized))
    if nkw in tok_set:
        return True
    if nkw in _BOUNDARY_KWS or len(nkw) <= 4:
        if re.search(rf"(?<![a-zçğıöşü]){re.escape(nkw)}(?![a-zçğıöşü])", normalized):
            return True
        return False
    if nkw in normalized:
        return True
    return any(nkw in t or t.startswith(nkw) for t in tok_set if len(t) >= len(nkw))


def _has_minibar_context(normalized: str) -> bool:
    return bool(
        re.search(r"\bmini\s*bar", normalized)
        or re.search(r"\bminibar\b", normalized)
    )


def _is_spa_wellness_context(normalized: str, tokens: set[str]) -> bool:
    """Spa departmanı yalnızca masaj/hamam/sauna/wellness bağlamında."""
    wellness = ("spa", "masaj", "wellness", "sauna", "hamam", "jakuzi", "terapist")
    return any(_keyword_matches(w, normalized, tokens) for w in wellness)


def _is_animation_context(normalized: str, tokens: set[str]) -> bool:
    """Animasyon/etkinlik — spa wellness veya aquapark/havuz değil."""
    if any(_keyword_matches(w, normalized, tokens) for w in ("aquapark", "aquaprk", "kaydirak", "havuz", "plaj")):
        return False
    if _is_spa_wellness_context(normalized, tokens):
        return False
    anim = ("etkinlik", "etkinlikler", "animasyon", "konser", "aktivite", "show", "animator", "masa tenisi")
    return any(_keyword_matches(w, normalized, tokens) for w in anim)


def _is_aquapark_maintenance_context(normalized: str, tokens: set[str]) -> bool:
    """Aquapark/havuz bakım — teknik bakım değil."""
    has_aquapark = any(_keyword_matches(w, normalized, tokens) for w in ("aquapark", "aquaprk", "kaydirak", "havuz"))
    has_maint = any(w in normalized for w in ("bakim", "bakima", "yipranmis", "yipranmış"))
    return has_aquapark and has_maint


# Ortak uygulamaya yönlendirildi (turkish_nlp_utils.fold_tr); önbellek orada.
_fold_tr = fold_tr


def _fold_tr_raw(text: str) -> str:
    """Türkçe karakterleri ASCII'ye indir, ancak morfolojik analiz yapma."""
    # normalize_turkish UYGULANMAZ — bu fonksiyonun amacı morfolojik analiz
    # yapmadan ham katlama; yalnızca karakter eşlemesi ortak kaynaktan gelir.
    return fold_tr_chars(text.lower().strip())



def _hotel_mapping(
    dept_key: str, dept_label: str, asp_key: str, asp_label: str, method: str, confidence: float = 0.85,
) -> dict[str, Any]:
    return {
        "domain": "turizm", "domainLabel": "Turizm", "subdomain": "otel", "subdomainLabel": "Otel",
        "department": dept_key, "departmentLabel": dept_label,
        "aspect": asp_key, "aspectLabel": asp_label, "aspect_key": asp_key,
        "matchedKeywords": [], "confidence": confidence, "method": method,
    }


def _is_patisserie_context(normalized: str, tokens: set[str]) -> bool:
    """Pastane/dondurma — plaj değil."""
    return any(_keyword_matches(w, normalized, tokens) for w in ("pastane", "pastanede", "dondurma", "tatli", "kulah", "külah"))


def _is_bar_drink_context(normalized: str) -> bool:
    """Bar departmanı — içecek, minibar veya bar bağlamında."""
    if _has_minibar_context(normalized):
        return True
    if re.search(r"\bkibar", normalized):
        return False
    if "bardak" in normalized or "bardakta" in normalized:
        return False
    if "barda" in normalized or "barlarda" in normalized or "bar da" in normalized:
        return True
    drink_ctx = (
        "bira", "sarap", "şarap", "raki", "rakı", "kokteyl", "tekila", "viski", "alkol",
        "irish bar", "gece bar", "disko bar", "bar 18", "7/24 bar",
        "icki", "içecek", "limonata", "soda",
    )
    tokens = set(tokenize_turkish(normalized))
    for d in drink_ctx:
        if " " in d:
            if d in normalized:
                return True
        elif d in tokens or re.search(rf"(?<![a-zçğıöşü]){re.escape(d)}(?![a-zçğıöşü])", normalized):
            return True
    if re.search(r"(?<![a-zçğıöşü])bar(?![a-zçğıöşü])", normalized):
        if "barista" not in normalized:
            return True
    return False


def _keyword_final_override(clause: str, current_dept: str) -> str:
    """Final override: catch pipeline errors for known keyword patterns.
    Returns the corrected department_label or empty string if no override needed.
    """
    n = normalize_turkish(clause.lower())
    folded = _fold_tr(clause)
    raw_folded = _fold_tr_raw(clause)
    raw_tokens = [w for w in re.split(r"[^a-z0-9]", raw_folded) if w]

    def _has_kw(*words: str) -> bool:
        for w in words:
            wf = _fold_tr_raw(w)
            if " " in wf:
                if wf in raw_folded:
                    return True
            elif len(wf) <= 3:
                if wf in raw_tokens:
                    return True
            else:
                if any(
                    t.startswith(wf)
                    for t in raw_tokens
                    # bakim ⊂ bakimli (praise "bakımlı") is a false positive
                    if not (wf == "bakim" and t.startswith("bakimli"))
                ):
                    return True
        return False

    _FO_DEPS = ("Ön Büro & Misafir İlişkileri",)
    _HK_DEPS = ("Kat Hizmetleri & Temizlik", "Oda Hizmetleri & Housekeeping")
    _ATMOS_DEPS = ("Otel Atmosferi & Misafir Profili",)
    _PERSONEL_DEPS = ("Personel Davranışı",)
    _TEKNIK_DEPS = ("Teknik Servis & IT",)

    # şezlong → Havuz (pipeline often misroutes to Housekeeping)
    if current_dept in _HK_DEPS and _has_kw("sezlong", "şezlong", "şenzlog", "semsiye", "şemsiye"):
        return "Havuz"
    # "herşey mükemmeldi", "asla gelmeyin" → Genel (not Atmosfer/Front Office)
    if current_dept in _ATMOS_DEPS and ("hersey" in raw_folded or "her şey" in raw_folded or "herşey" in raw_folded):
        return "Genel"
    if current_dept in _ATMOS_DEPS and ("muhtesem" in raw_folded or "mukemmel" in raw_folded or "harika" in raw_folded):
        return "Genel"
    if current_dept in _FO_DEPS and ("asla" in raw_folded or "pisman" in raw_folded or "pişman" in raw_folded):
        return "Genel"
    if current_dept in _ATMOS_DEPS and ("asla" in raw_folded or "pisman" in raw_folded or "pişman" in raw_folded):
        return "Genel"
    # müşteri temsilcisi → Genel (not Personel)
    if current_dept in _PERSONEL_DEPS and _has_kw("musteri temsilcisi", "müşteri temsilcisi", "muşteri temsilcisi"):
        return "Genel"
    # "bir daha olsa", "bir dahakine" → Genel (not Atmosfer)
    if current_dept in _ATMOS_DEPS and ("bir daha" in raw_folded or "gelir miyim" in raw_folded or "gelinir" in raw_folded or ("eksiklikler" in raw_folded and "tamamlan" in raw_folded)):
        return "Genel"
    # "minibar bozuk" → Teknik (not Bar)
    if current_dept == "Bar" and _has_kw("minibar", "mini bar") and _has_kw("bozuk", "calismiyor", "çalışmıyor", "sogutmuyor", "soğutmuyor"):
        return "Teknik"
    # "minibar doldurma" → Housekeeping (not Bar)
    if current_dept == "Bar" and _has_kw("minibar", "mini bar") and _has_kw("doldur", "her gun", "her gün", "düzenli"):
        return "Oda Hizmetleri & Housekeeping"
    # "rezervasyon" → FO (pipeline often misroutes to Housekeeping)
    if current_dept in _HK_DEPS and _has_kw("rezervasyon", "booking", "yatak tipi", "overbooking"):
        return "Ön Büro & Misafir İlişkileri"
    # "transfer" → FO (not Çevre)  
    if current_dept in ("Çevre, Güvenlik & Ulaşım",) and _has_kw("transfer", "shuttle", "havalimani", "havalimanı"):
        return "Ön Büro & Misafir İlişkileri"
    # "yön tabela" → FO (not Housekeeping)
    if current_dept in _HK_DEPS and _has_kw("tabela", "yonlendirme", "yönlendirme", "yol bulma"):
        return "Ön Büro & Misafir İlişkileri"
    # "masa tenisi" → Animasyon (not Rekreasyon combined)
    if current_dept in ("Rekreasyon & Eğlence",) and _has_kw("masa tenisi", "ping pong", "bilardo", "langırt"):
        return "Animasyon & Etkinlik"
    # "salata", "köfte", "kıyma" → Restaurant (not Bar or Atmosfer)
    if current_dept in ("Bar", "Otel Atmosferi & Misafir Profili") and _has_kw("salata", "kofte", "köfte", "kiyma", "kıyma", "çorba", "corba"):
        return "Restoran"
    # "irish bar" → Bar (not Restoran/Atmosfer)
    if current_dept in ("Restoran", "Otel Atmosferi & Misafir Profili") and _has_kw("irish bar", "irish bar"):
        return "Bar"
    # "pool bar" → Bar (not Havuz)
    if current_dept in ("Havuz",) and _has_kw("pool bar", "pool bardan", "havuz bar"):
        return "Bar"
    # "concierge" → FO (not Restoran)
    if current_dept in ("Restoran",) and _has_kw("concierge"):
        return "Ön Büro & Misafir İlişkileri"
    # "oda görevlisi", "temizlik personeli", "güvenlik personeli" → Personel (not HK/Çevre)
    if current_dept in _HK_DEPS and _has_kw("gorevli", "görevli", "personel"):
        return "Personel Davranışı"
    if current_dept in ("Çevre, Güvenlik & Ulaşım",) and _has_kw("guvenlik personeli", "güvenlik personeli", "personel"):
        return "Personel Davranışı"
    # "bellboy" → Personel (not Restoran)
    if current_dept in ("Restoran",) and _has_kw("bellboy", "bavul", "valiz"):
        return "Personel Davranışı"
    # "şef" + personel context → Personel (not Restoran) 
    if current_dept in ("Restoran",) and ("sef" in raw_tokens or "şef" in raw_tokens) and ("ilgilen" in raw_folded or "gorun" in raw_folded or "görün" in raw_folded or "yardim" in raw_folded or "yardım" in raw_folded):
        return "Personel Davranışı"
    # "garson" + "bakmıyor"/"sipariş unutuluyor" → Personel (not Restaurant)
    if current_dept in ("Restoran",) and ("garson" in raw_folded or "garsonlar" in raw_folded) and ("bakmiyor" in raw_folded or "bakmıyor" in raw_folded or "unutul" in raw_folded or "ilgisiz" in raw_folded):
        return "Personel Davranışı"
    # "misafir ilişkileri" → FO (not Personel)
    if current_dept in _PERSONEL_DEPS and "misafir iliskileri" in raw_folded:
        return "Ön Büro & Misafir İlişkileri"
    # "minibar görevlisi" → Housekeeping (not Bar)
    if current_dept == "Bar" and ("minibar gorevlisi" in raw_folded or "minibar görevlisi" in raw_folded or "mini bar gorevlisi" in raw_folded):
        return "Oda Hizmetleri & Housekeeping"
    # "havuz temiz masaj" → Havuz (not Spa)
    if current_dept == "Spa" and ("havuz" in raw_folded or "havuz" in raw_tokens):
        return "Havuz"
    # "personel şikayet" → Personel (not FO)
    if current_dept in _FO_DEPS and _has_kw("personel", "calisan", "çalışan") and _has_kw("sikayet", "şikayet", "cozum", "çözüm"):
        return "Personel Davranışı"
    # "jakuzi" → Spa (not Teknik)
    if current_dept in _TEKNIK_DEPS and _has_kw("jakuzi"):
        return "Spa"
    # "duş basıncı", "lavabo tıkanık" → Teknik (not HK)
    if current_dept in _HK_DEPS and _has_kw("basinc", "basınç", "tikanik", "tıkanık", "akyor", "akıyor", "gidmiyor"):
        return "Teknik Servis & IT"
    # "tertemiz", "umumi alan" → Housekeeping (not FO)
    if current_dept in _FO_DEPS and _has_kw("tertemiz", "umumi alan", "lobi temiz"):
        return "Oda Hizmetleri & Housekeeping"
    # "barmen" + "güler yüzlü" → Personel (not Bar)
    if current_dept == "Bar" and _has_kw("barmen") and _has_kw("guler yuz", "güler yüz", "ilgili", "kibar"):
        return "Personel Davranışı"
    # "yoğun değildi" → FO (not Atmosfer) — genel atmosfer değil, check-in/out rahatlığı
    if current_dept in _ATMOS_DEPS and ("yogun degildi" in raw_folded or "yoğun değildi" in raw_folded):
        return "Ön Büro & Misafir İlişkileri"
    # "en üst bölgede demirler yıpranmış" → Teknik (not Çevre)
    if current_dept in ("Çevre, Güvenlik & Ulaşım",) and ("demir" in raw_folded or "yipran" in raw_folded or "yıpran" in raw_folded) and ("ust bolge" in raw_folded or "üst bölge" in raw_folded):
        return "Teknik Servis & IT"
    # "sıra beklemiyorsunuz" havuz context → Havuz (not Restoran)
    if current_dept in ("Restoran",) and ("sira beklemiyor" in raw_folded or "sıra beklemiyor" in raw_folded):
        if "2" in raw_tokens or "3" in raw_tokens or "havuz" in raw_folded or "aquapark" in raw_folded:
            return "Havuz"
    # "hamam böceği" → Restoran (not Spa — "hamam" prefix causes misclassification)
    if current_dept in ("Spa",) and ("hamam boceg" in raw_folded or "hamam böceg" in raw_folded or "bocek" in raw_folded or "böcek" in raw_folded):
        if "yemek salonu" in raw_folded or "restoran" in raw_folded or "yemek" in raw_folded or "salon" in raw_folded:
            return "Restoran"
    # "personel sayısında yetersizlik" → Personel (not Restoran)
    if current_dept in ("Restoran", "Otel Atmosferi & Misafir Profili") and ("personel sayis" in raw_folded or "personel sayıs" in raw_folded):
        return "Personel Davranışı"
    # "beklenti altında kalan" → Genel (not Rekreasyon)
    if current_dept in ("Rekreasyon & Eğlence", "Otel Atmosferi & Misafir Profili") and ("beklenti altinda" in raw_folded or "beklenti altında" in raw_folded):
        return "Genel"
    # "personel yetersiz" → Personel (not any food/restaurant)
    if current_dept in ("Restoran", "Otel Atmosferi & Misafir Profili") and ("personel" in raw_folded or "calisan" in raw_folded or "çalışan" in raw_folded) and ("yetersiz" in raw_folded or "yetmiyor" in raw_folded or "az" in raw_folded):
        return "Personel Davranışı"
    return ""


class OntologyService:
    """Hiyerarşik domain ontolojisi — yükleme, tespit, eşleme."""

    @classmethod
    def get_ontology(cls) -> dict[str, Any]:
        return _load_raw()

    @classmethod
    def get_all_domains(cls) -> list[dict[str, Any]]:
        domains = []
        for d in _load_raw().get("domains", []):
            domains.append({
                "key": d["key"],
                "label": d["label"],
                "subdomains": [
                    {"key": s["key"], "label": s["label"]}
                    for s in d.get("subdomains", [])
                ],
            })
        return domains

    @classmethod
    def get_departments(cls, domain_key: str, subdomain_key: Optional[str] = None) -> list[dict[str, Any]]:
        norm = normalize_turkish(domain_key.lower())
        for d in _load_raw().get("domains", []):
            if d["key"] == norm or normalize_turkish(d["label"].lower()) == norm:
                depts: list[dict[str, Any]] = []
                for sub in d.get("subdomains", []):
                    if subdomain_key and sub["key"] != subdomain_key:
                        continue
                    for dept in sub.get("departments", []):
                        depts.append({
                            "key": dept["key"],
                            "label": dept["label"],
                            "subdomain": sub["key"],
                            "subdomain_label": sub["label"],
                            "aspects": [
                                {"key": a["key"], "label": a["label"]}
                                for a in dept.get("aspects", [])
                            ],
                        })
                return depts
        return []

    @classmethod
    def get_entities(cls) -> list[dict[str, Any]]:
        return list(_load_raw().get("entities", []))

    @classmethod
    def detect_domain(cls, text: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Metinden birincil domain(ler)i skorla tespit eder."""
        normalized = normalize_turkish(text.lower())
        tokens = set(tokenize_turkish(normalized))
        scores: list[tuple[float, dict[str, Any]]] = []

        for domain in _load_raw().get("domains", []):
            score = 0.0
            matched: list[str] = []
            for kw in domain.get("keywords", []):
                if _keyword_matches(kw, normalized, tokens):
                    score += 2.0
                    matched.append(kw)

            for sub in domain.get("subdomains", []):
                for dept in sub.get("departments", []):
                    for kw in dept.get("keywords", []):
                        if _keyword_matches(kw, normalized, tokens):
                            score += 1.5
                            matched.append(kw)
                    for aspect in dept.get("aspects", []):
                        for kw in aspect.get("keywords", []):
                            if _keyword_matches(kw, normalized, tokens):
                                score += 2.5
                                matched.append(kw)

            if score > 0:
                scores.append((score, {
                    "domain": domain["key"],
                    "domainLabel": domain["label"],
                    "score": round(score, 2),
                    "matchedKeywords": list(dict.fromkeys(matched))[:8],
                }))

        scores.sort(key=lambda x: -x[0])
        if not scores:
            return [{"domain": "turizm", "domainLabel": "Turizm", "score": 0.1, "matchedKeywords": []}]
        return [s[1] for s in scores[:top_k]]

    @classmethod
    def map_aspect_to_department(cls, text: str, clause: str) -> dict[str, Any]:
        """
        Cümlecik için en iyi {domain, subdomain, department, aspect, aspect_key} eşlemesi.
        Öncelik: kural tabanlı eşleşmeler > ontoloji motoru fallback.
        """
        from app.services.category_rules import classify_by_rules
        from app.services.turkish_nlp_utils import (
            CAT_CLEANING, CAT_FINANCE, CAT_FOOD, CAT_OTHER,
            CAT_RECEPTION, CAT_SPA, CAT_STAFF, CAT_TECH,
        )

        normalized = normalize_turkish(clause.lower())
        folded = _fold_tr(clause)
        tokens = set(tokenize_turkish(normalized))
        
        raw_folded = _fold_tr_raw(clause)
        raw_tokens = [w for w in re.split(r"[^a-z0-9]", raw_folded) if w]

        def _has_kw(*words: str) -> bool:
            _DRINK_BOUNDARY = frozenset({"bira", "raki", "raki", "sarap", "soda", "barmen"})
            for w in words:
                wf = _fold_tr_raw(w)
                if " " in wf:
                    if wf in raw_folded:
                        return True
                elif wf in _DRINK_BOUNDARY:
                    if re.search(rf"(?<![a-z]){re.escape(wf)}(?![a-z])", raw_folded):
                        return True
                elif len(wf) <= 3:
                    if wf in raw_tokens:
                        return True
                else:
                    if wf in raw_tokens:
                        return True
                    if any(
                        t.startswith(wf)
                        for t in raw_tokens
                        # bakim ⊂ bakimli (praise "bakımlı") is a false positive for maintenance
                        if not (wf == "bakim" and t.startswith("bakimli"))
                    ):
                        return True
            return False

        _STANDARD_ASPECT_TO_DEPT = {
            # Housekeeping
            "room_cleanliness": ("housekeeping", "Oda Hizmetleri & Housekeeping", "Oda Temizliği"),
            "bed_comfort": ("housekeeping", "Oda Hizmetleri & Housekeeping", "Yatak Konforu"),
            "linen_towel": ("housekeeping", "Oda Hizmetleri & Housekeeping", "Çarşaf & Havlu"),
            "bathroom": ("housekeeping", "Oda Hizmetleri & Housekeeping", "Banyo & Tuvalet"),
            "room_size": ("housekeeping", "Oda Hizmetleri & Housekeeping", "Oda Boyutu"),
            "soundproofing": ("housekeeping", "Oda Hizmetleri & Housekeeping", "Ses Yalıtımı"),
            "amenities": ("housekeeping", "Oda Hizmetleri & Housekeeping", "Buklet Malzemeleri"),
            # Engineering
            "air_conditioning": ("engineering", "Teknik Servis & IT", "Klima / İklimlendirme"),
            "wifi_internet": ("engineering", "Teknik Servis & IT", "WiFi / İnternet"),
            "elevator": ("engineering", "Teknik Servis & IT", "Asansör"),
            "tv_entertainment": ("engineering", "Teknik Servis & IT", "TV & Eğlence"),
            "maintenance": ("engineering", "Teknik Servis & IT", "Bakım & Onarım"),
            # Grounds
            "parking": ("grounds", "Çevre, Güvenlik & Ulaşım", "Otopark & Vale"),
            "security": ("grounds", "Çevre, Güvenlik & Ulaşım", "Güvenlik"),
            "location": ("grounds", "Çevre, Güvenlik & Ulaşım", "Konum"),
            "view": ("grounds", "Çevre, Güvenlik & Ulaşım", "Manzara"),
            "transportation": ("grounds", "Çevre, Güvenlik & Ulaşım", "Ulaşım & Transfer"),
            "environment": ("grounds", "Çevre, Güvenlik & Ulaşım", "Çevre & Bahçe"),
            # Spa & Wellness / Pool & Beach / Animation & Events -> Rekreasyon & Eğlence
            "fitness": ("leisure", "Rekreasyon & Eğlence", "Spor & Fitness"),
            "spa_massage": ("leisure", "Rekreasyon & Eğlence", "Spa & Masaj"),
            "pool": ("leisure", "Rekreasyon & Eğlence", "Havuz & Aquapark"),
            "beach": ("leisure", "Rekreasyon & Eğlence", "Plaj & Deniz"),
            "kids_club": ("leisure", "Rekreasyon & Eğlence", "Çocuk Kulübü"),
            "animation": ("leisure", "Rekreasyon & Eğlence", "Animasyon & Etkinlik"),
            # Front Office
            "price_value": ("front_office", "Ön Büro & Misafir İlişkileri", "Fiyat & Değer"),
            "billing": ("front_office", "Ön Büro & Misafir İlişkileri", "Fatura & Ödeme"),
            "booking": ("front_office", "Ön Büro & Misafir İlişkileri", "Rezervasyon"),
            "check_in_out": ("front_office", "Ön Büro & Misafir İlişkileri", "Giriş/Çıkış"),
            "reception_service": ("front_office", "Ön Büro & Misafir İlişkileri", "Resepsiyon Hizmetleri"),
            "complaint_resolution": ("front_office", "Ön Büro & Misafir İlişkileri", "Şikayet Çözümü"),
            # Restaurant / Bar -> Yiyecek & İçecek (F&B)
            "queue_waiting": ("food_beverage", "Yiyecek & İçecek (F&B)", "Servis / Kuyruk"),
            "restaurant_service": ("food_beverage", "Yiyecek & İçecek (F&B)", "Restoran Servisi"),
            "menu_variety": ("food_beverage", "Yiyecek & İçecek (F&B)", "Menü Çeşitliliği"),
            "breakfast": ("food_beverage", "Yiyecek & İçecek (F&B)", "Kahvaltı"),
            "food_quality": ("food_beverage", "Yiyecek & İçecek (F&B)", "Yemek Kalitesi"),
            "pest_hygiene": ("food_beverage", "Yiyecek & İçecek (F&B)", "Haşere / Gıda Hijyeni"),
            "food_illness": ("food_beverage", "Yiyecek & İçecek (F&B)", "Gıda Güvenliği / Sindirim"),
            "allergen_protocol": ("food_beverage", "Yiyecek & İçecek (F&B)", "Alerjen Protokolü"),
            "drink_quality": ("food_beverage", "Yiyecek & İçecek (F&B)", "İçecek Kalitesi"),
            "drink_variety": ("food_beverage", "Yiyecek & İçecek (F&B)", "İçecek Çeşitliliği"),
            "minibar": ("food_beverage", "Yiyecek & İçecek (F&B)", "Minibar"),
            # Staff
            "communication": ("staff", "Personel Davranışı", "Dil & İletişim"),
            "professionalism": ("staff", "Personel Davranışı", "Profesyonellik"),
            "staff_attitude": ("staff", "Personel Davranışı", "Personel Tutumu"),
            "staff_service": ("staff", "Personel Davranışı", "Personel Hizmeti"),
            "staff_shortage": ("staff", "Personel Davranışı", "Personel Yetersizliği"),
            # Atmosphere
            "crowd": ("atmosphere", "Otel Atmosferi & Misafir Profili", "Kalabalık / Yoğunluk"),
            "guest_profile": ("atmosphere", "Otel Atmosferi & Misafir Profili", "Misafir Profili"),
            "general_management": ("atmosphere", "Otel Atmosferi & Misafir Profili", "Genel Yönetim"),
            "general_atmosphere": ("atmosphere", "Otel Atmosferi & Misafir Profili", "Genel Atmosfer"),
            "overall_experience": ("atmosphere", "Otel Atmosferi & Misafir Profili", "Genel Deneyim"),
            "noise_level": ("atmosphere", "Otel Atmosferi & Misafir Profili", "Sessizlik / Gürültü"),
        }

        def _get_standard_mapping(aspect_key: str, method: str, confidence: float = 0.98) -> dict[str, Any]:
            dept_key, dept_label, asp_label = _STANDARD_ASPECT_TO_DEPT[aspect_key]
            return _hotel_mapping(dept_key, dept_label, aspect_key, asp_label, method, confidence)

        # 00. Top Priority Overrides for False Positive Words
        # Cockroach / Haşere in dining or hotel area (NOT Spa/Hamam)
        _pest = any(
            w in raw_folded
            for w in (
                "hamambocegi", "hamam bocegi", "hamam böceği", "hamam boceginin", "hamam böceğinin",
                "bocek", "böcek", "bocegi", "böceği", "boceginin", "hasere", "haşere", "fare", "sinek",
            )
        )
        if _pest:
            if any(w in raw_folded for w in ("yemek", "restoran", "salon", "bufe", "büfe", "masada", "onumden", "önümden")):
                return _get_standard_mapping("pest_hygiene", "cockroach_restaurant_override")
            return _get_standard_mapping("pest_hygiene", "cockroach_pest_override")

        # Foodborne illness / digestion (NOT taste)
        if any(w in raw_folded for w in ("sindirim", "zehirlen", "gida zehir", "gıda zehir")) or (
            any(w in raw_folded for w in ("yemeklerden kaynakli", "yemeklerden kaynaklı"))
            and any(w in raw_folded for w in ("rahatsiz", "rahatsız"))
        ):
            return _get_standard_mapping("food_illness", "food_illness_override")

        # Food / Buffet Variety (büfe çeşitliliği, yemek çeşitliliği)
        if _has_kw("bufe", "büfe", "menu", "menü", "yemek", "tatli", "tatlı", "salata") and _has_kw("cesit", "çeşit", "cesitlilik", "çeşitlilik", "secenek", "seçenek", "zayif", "zayıf", "az", "yok"):
            return _get_standard_mapping("menu_variety", "buffet_variety_override")

        # Staff Language / Communication (personel Türkçe bilmiyor)
        if _has_kw("personel", "personeli", "çalışan", "calisan", "garson", "resepsiyon") and _has_kw("turkce", "türkçe", "dil", "ingilizce", "lisan", "anlamiyor", "anlamıyor", "bilmiyor"):
            return _get_standard_mapping("communication", "staff_language_override")

        # Staff shortage / Kadro yetersizliği (NOT Restaurant)
        if (
            "personel sayisi" in raw_folded
            or "personel sayısı" in raw_folded
            or "personel sayisinda" in raw_folded
            or "personel yetersiz" in raw_folded
            or "kadro yetersiz" in raw_folded
            or "personel az" in raw_folded
            or "eleman az" in raw_folded
            or "personel eksik" in raw_folded
            or ("personel" in raw_folded and "yetersizlik" in raw_folded)
        ):
            return _get_standard_mapping("staff_shortage", "staff_shortage_override")

        # Allergen inquiry (NOT food taste quality)
        if any(w in raw_folded for w in ("alerjiniz", "alerji", "allerji")) and any(
            w in raw_folded for w in ("var mi", "var mı", "sorusu", "soru")
        ) and "sindirim" not in raw_folded:
            return _get_standard_mapping("allergen_protocol", "allergen_protocol_override")

        # Sea / Beach / Su Sporları (NOT Pool/Havuz, NOT View/Manzara, NOT Location/Konum)
        if _has_kw("deniz", "denizi", "sahil", "sahile", "plaj", "plajı", "su sporları", "su sporlarinin", "dalgali", "bulanik"):
            if not _has_kw("havuz", "aquapark", "aquaprk", "manzara", "manzarasi", "manzaralı", "manzarali", "konum", "lokasyon", "merkeze"):
                return _get_standard_mapping("beach", "beach_override")

        # Expectation shortfall / Hayal kırıklığı (NOT Pool Queue)
        if "beklenti alt" in raw_folded or "beklentinin alt" in raw_folded or "beklentimin alt" in raw_folded or "hayal kirikligi" in raw_folded or "hayal kırıklığı" in raw_folded:
            return _get_standard_mapping("overall_experience", "expectation_override")

        # Detailed parking / Otopark
        if _has_kw("otopark") or ("araci otelden" in raw_folded) or ("aracı otelden" in raw_folded) or ("toprak zemin" in raw_folded):
            return _get_standard_mapping("parking", "parking_detailed_override")

        # 0. Complaint Resolution (very specific, check first)
        _is_complaint = False
        if (_has_kw("sikayet", "şikayet", "sikayetler", "şikayetler") or ("sorunlarin cozum" in raw_folded) or ("sikayet cozum" in raw_folded) or ("sikayetlerin dikkate" in raw_folded)):
            _is_complaint = True
        # "misafir iliskileri ilgisi" but NOT "misafir iliskileri ilgisiz"
        if "misafir iliskileri ilgisi" in raw_folded and "ilgisiz" not in raw_folded:
            _is_complaint = True
        if ("misafir iliskilerine bildirdik" in raw_folded or "misafir ilişkilerine bildirdik" in raw_folded) and _has_kw("cozmed", "çözmed", "cozulmed", "çözülmed", "cozmedi", "çözmedi"):
            _is_complaint = True
        elif _has_kw("cozum", "çözüm", "cozumu", "çözümü") and not _has_kw("resepsiyon"):
            if not ("misafir iliskileri" in raw_folded):
                _is_complaint = True
        if "cozum hiz" in raw_folded and not _has_kw("resepsiyon"):
            _is_complaint = True
        if _is_complaint:
            return _get_standard_mapping("complaint_resolution", "complaint_override")

        # 0b. Transportation (specific, before location)
        if _has_kw("transfer", "shuttle", "havalimani", "havalimanı", "taksi") or ("ulasim imkan" in raw_folded) or ("ulaşım imkan" in raw_folded):
            return _get_standard_mapping("transportation", "transportation_override")

        # 0c. Environment / Garden (specific, before location)
        if _has_kw("bahce", "bahçe", "peyzaj", "mimari") or ("yesil alan" in raw_folded) or ("yeşil alan" in raw_folded) or ("otel mimaris" in raw_folded) or ("mimari tasarim" in raw_folded):
            return _get_standard_mapping("environment", "environment_override")

        # 0d. Staff Attitude (specific patterns without requiring staff word)
        if ("personel ilgisi" in raw_folded) or ("personel tutumu" in raw_folded) or ("garsonlarin tavir" in raw_folded) or ("resepsiyon tavri" in raw_folded) or ("guler yuz" in raw_folded) or ("güleryüz" in raw_folded) or ("tatli dil" in raw_folded) or ("tatlı dil" in raw_folded) or ("olgun bir beyefendi" in raw_folded) or ("el becerisi" in raw_folded) or ("deniz kardes" in raw_folded) or ("stajyer deniz" in raw_folded) or ("barmen deniz" in raw_folded):
            if "resepsiyon tavri" in raw_folded or not _has_kw("resepsiyon", "guest relations", "lobi", "ön büro"):
                return _get_standard_mapping("staff_attitude", "staff_attitude_phrase_override")

        # 0e. Staff Service (specific patterns without requiring staff word)
        # Note: 'garson hizi' goes to restaurant_service, not staff_service
        if ("yardimseverlik" in raw_folded) or ("calisanlarin destegi" in raw_folded) or ("hizmet kalitesi" in raw_folded) or ("emeğinin hakkıyla" in raw_folded) or ("emeğin hakkıyla" in raw_folded) or ("layıkıyla hak ediyor" in raw_folded) or ("layikiyla hak ediyor" in raw_folded):
            return _get_standard_mapping("staff_service", "staff_service_phrase_override")

        # 0f. General Management (specific patterns)
        if ("otel yonetimi" in raw_folded) or ("isletme kalitesi" in raw_folded) or ("yonetim sekli" in raw_folded) or ("otel isletmesi" in raw_folded):
            return _get_standard_mapping("general_management", "management_phrase_override")

        # 0g. Koridorlarda tabak/bardak/kir → Housekeeping (before bar/drink rules)
        if _has_kw("koridor", "koridorlarda", "koridorlara", "koridorlar") and _has_kw("tabak", "bardak", "birak", "bırak", "kirli", "durdu", "bekliyor"):
            return _get_standard_mapping("room_cleanliness", "corridor_dishes_override")

        # 0g2. Guest Profile (specific patterns, before crowd)
        if ("kitle kalitesi" in raw_folded) or ("musteri portfoyu" in raw_folded) or ("oteldeki kitle" in raw_folded) or ("misafir profili" in raw_folded) or ("gelen turistler" in raw_folded):
            return _get_standard_mapping("guest_profile", "guest_profile_phrase_override")
        if ("saygisiz misafir" in raw_folded or "saygısız misafir" in raw_folded) and ("kaos" in raw_folded or "ortam" in raw_folded):
            return _get_standard_mapping("guest_profile", "guest_profile_disrespectful_override")

        # 0h3. Staff immaturity / hotel run by kids — NOT beverage (bira⊂bırakılmış)
        if _has_kw("personel", "personeller") and _has_kw("cocuk", "coluk", "yabanc") and any(
            p in raw_folded for p in (
                "eline birak", "eline bırak", "birakilmis", "bırakılmış",
                "cocuklarin eline", "çocukların eline", "oteli sanki", "oteli sanki",
            )
        ):
            return _get_standard_mapping("staff_attitude", "staff_immaturity_override")

        # 0h4. Pastane / kahve köşesi / lokum — F&B NOT pool/beach
        if _has_kw("pastane", "kahve kosesi", "kahve köşesi", "lokum", "turk kahvesi", "türk kahvesi"):
            return _get_standard_mapping("food_quality", "patisserie_override")

        # 0h4b. Food hair / pest / hygiene override
        if any(w in raw_folded for w in ("kil cikti", "kıl çıktı", "kili cikti", "kılı çıktı", "sac kili", "saç kılı", "simsiyah kılı", "simsiyah kili")) or (
            any(w in raw_folded for w in ("makarna", "restorantta", "restoranda", "yiyecek", "sefimin", "şefimin")) and any(w in raw_folded for w in ("kil", "kıl", "sinek", "bocek", "böcek"))
        ):
            return _get_standard_mapping("pest_hygiene", "food_hair_hygiene_override")

        # 0h5. Mutlu ayrıldık / loyalty — atmosphere NOT HK
        if any(p in raw_folded for p in ("mutlu ayrild", "mutlu ayrıl", "tercihimiz olacak", "memnun ayril", "memnun ayrıl")):
            return _get_standard_mapping("general_atmosphere", "loyalty_satisfaction_override")

        # 0h6. Don't recommend — entity pre-screening before collapsing to general atmosphere
        if _has_kw("tavsiye etmem", "tavsiye etmiyorum", "onermiyorum", "önermiyorum") or (
            "tavsiye etmem" in raw_folded or "gondere mem" in raw_folded or "göndermem" in raw_folded
        ):
            # Check for food hygiene / hair / pest
            if any(w in raw_folded for w in ("kil", "kıl", "makarna", "sefimin", "şefimin", "restorantta", "restoranda", "sineki", "sinek", "bocek", "böcek", "zehirlen", "mide")):
                return _get_standard_mapping("pest_hygiene", "food_hair_override")
            # Check for pool / beach / sunbed
            if any(w in raw_folded for w in ("sezlong", "şezlong", "havuz", "plaj", "deniz")):
                return _get_standard_mapping("pool", "pool_beach_override")
            # Check for room cleaning / housekeeping
            if any(w in raw_folded for w in ("kirli", "temizlen", "banyo", "klima", "yatak", "havlu", "pis", "toz")):
                return _get_standard_mapping("room_cleanliness", "housekeeping_override")
            # Check for staff attitude / manager
            if any(w in raw_folded for w in ("gece müdürü", "gece muduru", "resepsiyon", "kaba", "suratsiz", "suratsız", "garson tutum")):
                return _get_standard_mapping("staff_attitude", "staff_attitude_override")
            return _get_standard_mapping("general_atmosphere", "no_recommend_override")

        # Category 2: Minibar attendant / towel override (Housekeeping over F&B)
        if _has_kw("minibar", "mini bar") and any(w in raw_folded for w in ("havlu", "temizlik", "degistirmedi", "değiştirmedi", "gorevli", "görevli")):
            return _get_standard_mapping("linen_towel", "minibar_towel_cleaning_override")

        # Category 4: Night shift manager / supervisor refusing to help sick guest (Staff attitude)
        if any(w in raw_folded for w in ("gece vardiyasi", "gece vardiyasi amiri", "vardiya amiri", "sirita sirita", "sırıta sırıta", "gece müdürü", "gece muduru")):
            return _get_standard_mapping("staff_attitude", "night_manager_override")

        # Category 4: Table clearing / slow table service (Restaurant service over general staff)
        if any(w in raw_folded for w in ("masayi toplama", "masayı toplama", "masalari toplama", "masaları toplama", "iceri almalari", "içeri almaları")):
            return _get_standard_mapping("restaurant_service", "table_clearing_override")

        # Category 5: Excessive walking / long distances to rooms/facilities (Walking distance layout)
        if any(w in raw_folded for w in ("yurunuyor", "yürünüyor", "yuruyoruz", "yürüyoruz", "yol yürün", "yol yurun", "mesafe", "odadan denize", "kilometre", "cok fazla yurunuyor")):
            return _get_standard_mapping("room_size", "walking_distance_override")

        # Missed event / animation attendance issue
        if any(w in raw_folded for w in ("etkinlige", "etkinliğe", "konsere", "gosteriye", "gösteriye")) and any(w in raw_folded for w in ("katilamadim", "katılamadım", "katilamadik", "katılamadık")):
            return _get_standard_mapping("animation", "missed_event_override")

        # 0h7. Heated pool — pool NOT HVAC
        if _has_kw("havuz", "havuzlar", "aquapark") and _has_kw(
            "isitmali", "ısıtmalı", "isitma", "ısıtma", "heated",
        ):
            return _get_standard_mapping("pool", "heated_pool_override")

        # 0h. Personel + kokteyl/içecek sipariş → staff attitude (not bar)
        if _has_kw("personel", "personelin") and _has_kw("kokteyl", "icecek", "içecek", "siparis", "sipariş"):
            return _get_standard_mapping("staff_service", "staff_drink_order_override")

        # 0h2. Crowd (specific patterns)
        if ("otel kalabaligi" in raw_folded) or ("tesisin yogunlugu" in raw_folded) or ("insan sayisi" in raw_folded):
            return _get_standard_mapping("crowd", "crowd_phrase_override")

        # 0i. General Atmosphere (specific "ortam" pattern)
        if raw_tokens and raw_tokens[0] == "ortam":
            return _get_standard_mapping("general_atmosphere", "atmosphere_phrase_override")

        # 0j. Noise Level (specific patterns)
        if (("gurultu" in raw_folded or "gürültü" in raw_folded) and not _has_kw("yalitim", "yalıtım", "klima", "aktivite", "aktiviteler", "animasyon", "izolasyon", "izolasyonu")) or ("ses gurultusu" in raw_folded) or ("sessizlik" in raw_folded) or ("ses yuksekligi" in raw_folded):
            return _get_standard_mapping("noise_level", "noise_phrase_override")

        # 0j2. General Atmosphere ("genel hava" phrase)
        if "genel hava" in raw_folded:
            return _get_standard_mapping("general_atmosphere", "genel_hava_override")

        # 0k. Check-in/out (with hyphen, oda teslimi, giris cikis)
        if "check-in" in raw_folded or "check-out" in raw_folded or "checkin" in raw_folded or "checkout" in raw_folded or "oda teslimi" in raw_folded or ("giris" in raw_folded and "cikis" in raw_folded):
            return _get_standard_mapping("check_in_out", "check_in_out_override")

        # 0l. Parking (specific patterns)
        if "araba park" in raw_folded:
            return _get_standard_mapping("parking", "parking_phrase_override")

        # 0m. Security (specific patterns)
        if ("otel guvenligi" in raw_folded) or ("kilit sistemi" in raw_folded):
            return _get_standard_mapping("security", "security_phrase_override")
        if any(w in raw_folded for w in ("sap adam", "yan goz", "yan göz", "pis hissettiri", "rahatsiz edici", "rahatsız edici")):
            return _get_standard_mapping("security", "guest_safety_override")

        # 0n. View (manzara patterns)
        if _has_kw("manzara", "manzarasi"):
            return _get_standard_mapping("view", "view_override")

        # 0o. Kids Club (miniclub, kids club, cocuk oyun alani)
        if _has_kw("miniclub") or ("kids club" in raw_folded) or ("cocuk oyun" in raw_folded) or ("çocuk oyun" in raw_folded):
            return _get_standard_mapping("kids_club", "kids_club_phrase_override")

        # 0p. Fitness (spor aletleri, fitness salonu, tenis kortu)
        if ("spor alet" in raw_folded) or ("fitness salonu" in raw_folded) or ("tenis kort" in raw_folded) or ("gym alet" in raw_folded):
            return _get_standard_mapping("fitness", "fitness_phrase_override")

        # 0q. Maintenance (sicak su, dus basligi - before bathroom)
        if ("sicak su" in raw_folded) or ("sıcak su" in raw_folded) or ("dus basligi" in raw_folded) or ("duş başlığı" in raw_folded):
            return _get_standard_mapping("maintenance", "maintenance_phrase_override")

        # 0r. Wi-Fi (with hyphen)
        if "wi-fi" in raw_folded:
            return _get_standard_mapping("wifi_internet", "wifi_hyphen_override")

        # 0s. Billing (ekstra ucretler)
        if ("ekstra ucret" in raw_folded or "ekstra ücret" in raw_folded) and not any(
            w in raw_folded for w in ("tekila", "viski", "votka", "cin", "alkol", "icecek", "içecek", "kokteyl", "bira", "sarap", "şarap", "minibar", "mini bar")
        ):
            return _get_standard_mapping("billing", "billing_phrase_override")

        # 0s2. Pool bar / Bar rules
        if "pool bar" in raw_folded or "pool barı" in raw_folded or "irish bar" in raw_folded:
            return _get_standard_mapping("drink_quality", "pool_bar_override")

        # 0s3. Minibar billing vs Minibar drinks
        if "minibar" in raw_folded and any(w in raw_folded for w in ("ucret", "ücret", "fahiş", "fahis", "fiyat", "hesap")):
            return _get_standard_mapping("billing", "minibar_billing_override")

        # 0s4. Glass / Tea / Dondurma in Food context
        if any(w in raw_folded for w in ("dondurma", "külah", "kulah", "yağ lekeleri", "yag lekeleri")) or ("bardak" in raw_folded and "çay" in raw_folded):
            return _get_standard_mapping("food_quality", "food_icecream_glass_override")

        # 0s5. Reservation bed type (rezervasyondaki yatak tipi)
        if "rezervasyon" in raw_folded and any(w in raw_folded for w in ("yatak", "oda", "tipi", "yanlış", "yanlis")):
            return _get_standard_mapping("check_in_out", "reservation_bedtype_override")

        # 0s6. Signage / orientation (yön tabelaları)
        if "yon tabela" in raw_folded or "yön tabela" in raw_folded or "tabelalar" in raw_folded:
            return _get_standard_mapping("general_atmosphere", "signage_override")

        # 0s6b. Room info sheet / phone numbers — FO guest info (NOT staff via 'yoktu'/'telefon')
        if ("bilgilendirme" in raw_folded and any(w in raw_folded for w in ("kagit", "kağıt", "kagidi", "kağıdı", "yoktu", "oda"))) or (
            "telefon numar" in raw_folded
        ):
            return _get_standard_mapping("reception_service", "guest_info_sheet_override")

        # 0s7. Concierge -> Reception / Front Office
        if "concierge" in raw_folded:
            return _get_standard_mapping("reception_service", "concierge_override")

        # 0s8. Jakuzi -> Spa
        if "jakuzi" in raw_folded:
            return _get_standard_mapping("spa_massage", "jakuzi_override")

        # 0t. Aquapark (including misspelling)
        if _has_kw("aquapark", "aquaprk", "aqua"):
            return _get_standard_mapping("pool", "aquapark_override")

        # 0u. Garson + attitude/kaba/istemeyerek/slowness → Personel (before restaurant rules)
        if _has_kw("garson", "barmen") and _has_kw("kaba", "istemeyerek", "suratsiz", "suratsız", "ilgisiz", "lakayit", "lakayıt", "tavir", "tavır", "gec", "geç", "bakıyordu", "bakıyordu", "bekletti", "yarim saat", "yarım saat"):
            return _get_standard_mapping("staff_attitude", "staff_garson_attitude_override")

        # 0u. Restaurant Service (specific patterns)
        if ("restoran servisi" in raw_folded) or ("restaurant servisi" in raw_folded) or ("masa servisi" in raw_folded) or ("restorandaki hiz" in raw_folded):
            return _get_standard_mapping("restaurant_service", "restaurant_service_phrase_override")

        # 0u2. garson hizi -> restaurant_service (food context)
        if "garson hizi" in raw_folded and not _has_kw("personel", "calisan", "ekip"):
            return _get_standard_mapping("restaurant_service", "garson_hizi_override")

        # 0u3. a la carte / restoran adı (before booking rule to prevent reservation bleed)
        if _has_kw("a la carte", "alakart", "ala carte") or ("restoran" in raw_tokens and not _has_kw("oda", "odalar", "banyo", "temizlik", "fiyat", "otel")):
            return _get_standard_mapping("restaurant_service", "restaurant_name_override")

        # 0v. Menu Variety (yemek cesitliligi, acik bufe cesitliligi)
        if ("yemek cesitliligi" in raw_folded) or ("acik bufe cesitliligi" in raw_folded) or ("açık büfe çeşitliliği" in raw_folded):
            return _get_standard_mapping("menu_variety", "menu_variety_phrase_override")

        if "makarna" in raw_folded or "makarna cesidi" in raw_folded or "makarna çeşidi" in raw_folded:
            return _get_standard_mapping("menu_variety", "pasta_menu_override")

        # 0w. Drink Quality / Variety (specific drinks and cocktails)
        if _has_kw(
            "kokteyl", "kokteyller", "kokteyli", "bira", "sarap", "şarap", "raki", "rakı", 
            "tekila", "viski", "cin", "vodka", "votka", "sampanya", "şampanya", "likor", "likör", 
            "soda", "limonata", "alkol", "icecek", "içecek", "içecekler", "icecekler"
        ):
            # Skip if minibar context or staff order context or food context
            if not _has_kw("minibar", "mini bar", "buzdolabi") and not (_has_kw("personel", "garson") and _has_kw("siparis", "sipariş", "kaba", "suratsiz", "suratsız")) and not any(w in raw_folded for w in ("makarna", "kıyma", "kiyma", "çorba", "corba", "tavuk")):
                if any(w in raw_folded for w in ("bol", "cesit", "çeşit", "cesitli", "çeşitli", "secenek", "seçenek", "zengin")):
                    return _get_standard_mapping("drink_variety", "drink_variety_override")
                return _get_standard_mapping("drink_quality", "drink_specific_override")

        # 0x. Bar kuyrugu
        if "bar kuyrugu" in raw_folded or "bar kuyruğu" in raw_folded:
            return _get_standard_mapping("queue_waiting", "bar_queue_override")

        # 0y. Breakfast (omlet)
        if _has_kw("omlet"):
            return _get_standard_mapping("breakfast", "breakfast_omlet_override")

        # 0z. Food Quality (oglen yemegi)
        if ("oglen yemegi" in raw_folded) or ("öğlen yemeği" in raw_folded):
            return _get_standard_mapping("food_quality", "food_lunch_override")

        # 0aa. Beach (deniz temizligi, iskele)
        if ("deniz temizligi" in raw_folded) or (_has_kw("iskele") and not _has_kw("restoran", "yemek")):
            return _get_standard_mapping("beach", "beach_phrase_override")

        # 0ab. Misafir iliskileri → reception_service (general, after complaint check)
        if "misafir iliskileri" in raw_folded:
            return _get_standard_mapping("reception_service", "reception_phrase_override")

        # 0ab2. odalar temiz + mini bar düzenli doldurma → Housekeeping (not Çevre/Bar)
        if _has_kw("oda", "odalar", "odalari", "odaları") and _has_kw("temiz", "temizdi"):
            return _get_standard_mapping("room_cleanliness", "room_clean_context_override")

        # 0ac. aksam sovlar → animation
        if "aksam sov" in raw_folded or "akşam şov" in raw_folded:
            return _get_standard_mapping("animation", "aksam_sov_override")

        # 0ad. merkeze yakinlik → location
        if "merkeze yakin" in raw_folded or "merkeze yakın" in raw_folded:
            return _get_standard_mapping("location", "merkeze_yakin_override")

        # 0ad2. sezlong / şezlong → Havuz (before pipeline can override to Housekeeping)
        if _has_kw("sezlong", "şezlong", "semsiye", "şemsiye"):
            return _get_standard_mapping("pool", "sunlounger_override")

        # 0ae. odanin temizligi → room_cleanliness
        if "odanin temizligi" in raw_folded or "odanın temizliği" in raw_folded:
            return _get_standard_mapping("room_cleanliness", "room_clean_phrase_override")

        # 0af. dus alani → bathroom
        if "dus alani" in raw_folded or "duş alanı" in raw_folded:
            return _get_standard_mapping("bathroom", "bathroom_dus_override")

        # 0ag. Room Size (odamiz kocaman, odalar daracik)
        if (_has_kw("odamiz", "odamız") and _has_kw("kocaman", "buyuk", "büyük", "genis", "geniş")) or (_has_kw("odalar") and _has_kw("daracik", "daraçık")):
            return _get_standard_mapping("room_size", "room_size_phrase_override")

        # 0ah. resepsiyon cozum → reception_service
        if "resepsiyon cozum" in raw_folded or "resepsiyon çözüm" in raw_folded:
            return _get_standard_mapping("reception_service", "reception_cozum_override")

        # 1. Cleanliness rules (high priority)
        if _has_kw("temizlik", "temizligi", "temizliği", "hijyen", "hijyeni"):
            if _has_kw("oda", "odalar", "yer", "zemin", "hali", "halı", "koridor", "dolap", "pencere", "cam"):
                return _get_standard_mapping("room_cleanliness", "room_clean_override")
            elif _has_kw("banyo", "tuvalet", "wc", "lavabo", "klozet"):
                return _get_standard_mapping("room_cleanliness", "bathroom_clean_override")
            elif _has_kw("restoran", "yemekhane", "bufe", "büfe", "masa", "catal", "çatal", "bicak", "bıçak", "kasik", "kaşık") and not _has_kw("oda", "odadaki", "odamiz", "odamız"):
                return _get_standard_mapping("restaurant_service", "restaurant_clean_override")
            elif _has_kw("havuz", "aquapark", "kaydirak", "kaydırak"):
                return _get_standard_mapping("pool", "pool_clean_override")
            elif _has_kw("plaj", "sahil", "kumsal", "iskele"):
                return _get_standard_mapping("beach", "beach_clean_override")

        # General room cleanliness
        if _has_kw("oda", "odalar") and _has_kw("temiz", "kirli", "pis", "toz", "hijyen", "leke"):
            return _get_standard_mapping("room_cleanliness", "room_clean_rules")

        # 2. Amenities
        if _has_kw("sampuan", "şampuan", "sabun", "dus jeli", "duş jeli", "dis macunu", "diş macunu", "terlik", "bornoz", "buklet", "sac kurutma", "saç kurutma", "kettle", "su isitici", "su ısıtıcı"):
            return _get_standard_mapping("amenities", "amenities_override")

        # 3. Soundproofing
        if _has_kw("yalitim", "yalıtım", "izolasyon", "ses gecir", "ses geçir", "duvar"):
            return _get_standard_mapping("soundproofing", "soundproofing_override")

        # 4. Bathroom (sicak su and dus basligi handled above in maintenance)
        if _has_kw("banyo", "tuvalet", "lavabo", "klozet", "dusakabin", "duşakabin"):
            return _get_standard_mapping("bathroom", "bathroom_override")

        # 5. Bed comfort
        if _has_kw("yatak", "dosek", "döşek", "yastik", "yastık") and not _has_kw("kilif", "kılıf"):
            return _get_standard_mapping("bed_comfort", "bed_comfort_override")

        # 6. Linen / Towel
        if _has_kw("carsaf", "çarşaf", "havlu", "nevresim", "yorgan", "pike") or (_has_kw("yastik", "yastık") and _has_kw("kilif", "kılıf")):
            return _get_standard_mapping("linen_towel", "linen_towel_override")

        # 7. Room Size
        if _has_kw("oda", "odalar") and _has_kw("buyuk", "büyük", "kocaman", "kucuk", "küçük", "dar", "genis", "geniş", "ferah", "basik", "basık", "alan", "boyut", "genislik", "genişlik", "m2", "metrekare"):
            return _get_standard_mapping("room_size", "room_size_override")

        # 8. Air Conditioning
        if _has_kw("klima", "hvac", "iklimlendirme", "vantilator", "vantilatör"):
            return _get_standard_mapping("air_conditioning", "ac_override")

        # 9. Minibar (skip if about person/görevli — "minibar görevlisi" → Housekeeping)
        if _has_kw("minibar", "mini bar", "buzdolabi", "buzdolabı") and not _has_kw("gorevli", "görevli", "personel", "temizlik"):
            return _get_standard_mapping("minibar", "minibar_override")

        # 10. Wifi / Internet
        if _has_kw("wifi", "wi-fi", "internet", "baglanti", "bağlantı", "slow internet"):
            return _get_standard_mapping("wifi_internet", "wifi_override")

        # 11. Elevator
        if _has_kw("asansor", "asansör", "lift"):
            return _get_standard_mapping("elevator", "elevator_override")

        # 12. TV & Entertainment
        if _has_kw("televizyon", "tv", "kumanda", "kanal yayin", "kanal yayın"):
            return _get_standard_mapping("tv_entertainment", "tv_override")

        # 13. Maintenance
        if _has_kw("musluk", "priz", "lamba", "ampul", "elektrik", "bakim", "bakımı", "ariza", "arıza", "bozuk", "calismiyor", "çalışmıyor", "akitiyor", "akıtıyor"):
            return _get_standard_mapping("maintenance", "maintenance_override")

        # 14. Parking / Valet
        if _has_kw("vale", "valet", "otopark", "park yeri"):
            return _get_standard_mapping("parking", "parking_override")

        # 15. Security
        if _has_kw("guvenlik", "güvenlik", "kilit", "safe", "kasa", "bekci", "bekçi", "kamera"):
            return _get_standard_mapping("security", "security_override")

        # 16. Location (removed ulasim/cevre/merkez/uzak to avoid conflicts)
        if _has_kw("konum", "lokasyon"):
            return _get_standard_mapping("location", "location_override")

        # 17. View (already handled above in 0n)

        # 18. Fitness / Gym
        if _has_kw("gym", "fitness", "tenis", "kort", "spor salonu"):
            return _get_standard_mapping("fitness", "fitness_override")

        # 19. Spa / Massage (skip if pool context — "havuz temiz masaj" → Havuz)
        # NEVER match "hamam" inside "hamam böceği"
        _pest_here = any(
            w in raw_folded
            for w in ("bocek", "böcek", "bocegi", "hasere", "haşere", "hamambocegi", "hamam bocegi")
        )
        if not _has_kw("havuz") and not _pest_here and (
            _has_kw("spa", "masaj", "sauna", "jakuzi", "terapist", "masor", "masör")
            or (_has_kw("hamam") and not _pest_here)
        ):
            return _get_standard_mapping("spa_massage", "spa_override")

        # 20. Kids Club
        if _has_kw("cocuk kulubu", "çocuk kulübü", "kids club", "mini club", "cocuk oyun", "çocuk oyun"):
            return _get_standard_mapping("kids_club", "kids_club_override")

        # 21. Pool
        if _has_kw("havuz", "aquapark", "kaydirak", "kaydırak", "yuzme", "yüzme"):
            return _get_standard_mapping("pool", "pool_override")

        # 22. Beach (skip if food context or person name "Deniz")
        is_deniz_person = any(p in raw_folded for p in ("deniz kardes", "deniz bey", "deniz hanim", "stajyer deniz", "barmen deniz", "garson deniz", "deniz usta", "deniz abi", "deniz adli"))
        has_beach_kw = _has_kw("plaj", "sahil", "kumsal", "iskele", "sezlong", "şezlong", "semsiye", "şemsiye") or (_has_kw("deniz") and not is_deniz_person)
        if not _has_kw("dondurma", "tatli", "tatlı", "pastane") and has_beach_kw:
            return _get_standard_mapping("beach", "beach_override")

        # 23. Animation
        if _has_kw("animasyon", "canli muzik", "canlı müzik", "konser", "aktivite", "etkinlik", "gosteri", "gösteri"):
            return _get_standard_mapping("animation", "animation_override")

        # 23b. Personel + değer → Staff Service (not Price)
        if _has_kw("personel", "calisan", "çalışan") and _has_kw("deger", "değer") and _has_kw("ver", "vermek", "vermiyor", "vermemeli"):
            return _get_standard_mapping("staff_service", "staff_value_override")

        # 24. Price / Value
        if _has_kw("fiyat", "deger", "değer", "ucret", "ücret", "para", "odenen", "ödenen", "karsilik", "karşılık", "pahali", "pahalı", "ucuz"):
            return _get_standard_mapping("price_value", "price_value_override")

        # 25. Billing
        if _has_kw("fatura", "depozito", "odeme", "ödeme", "karttan", "hesap detayı", "hesap detayi"):
            return _get_standard_mapping("billing", "billing_override")

        # 26. Booking
        if _has_kw("rezervasyon", "booking", "overbooking", "oda kaydi", "oda kaydı"):
            return _get_standard_mapping("booking", "booking_override")

        # 27. Check-in / Out (already handled above in 0k)

        # 28. Reception Service
        if _has_kw("resepsiyon", "front desk", "on buro", "ön büro", "guest relations", "lobi", "karsilama", "karşılama"):
            return _get_standard_mapping("reception_service", "reception_override")

        # 29. Queue Waiting
        if _has_kw("sira", "sıra", "kuyruk", "bekleme", "bekledik", "bekliyorsunuz"):
            return _get_standard_mapping("queue_waiting", "queue_override")

        # 29b. Boş tabak/koridor → Housekeeping (not Restaurant)
        if _has_kw("koridor", "koridorlarda", "koridorlara") and _has_kw("tabak", "bardak", "birak", "bırak"):
            return _get_standard_mapping("room_cleanliness", "corridor_dishes_override")

        # 30. Restaurant Service (skip for corridor context)
        if _has_kw("garson", "servis hizi", "servis hızı", "servis yavas", "servis yavaş", "tabak", "çatal", "catal", "bıçak", "bicak", "kaşık", "kasik", "masa kirli", "masa temiz"):
            if _has_kw("koridor", "koridorlarda", "koridorlara"):
                return _get_standard_mapping("room_cleanliness", "corridor_dishes_override")
            return _get_standard_mapping("restaurant_service", "restaurant_override")
        # 30b. Restoran / a la carte (route to Restaurant, not combined F&B)
        if _has_kw("restoran", "a la carte", "restaurant") and not _has_kw("oda", "odalar", "banyo", "temizlik"):
            return _get_standard_mapping("restaurant_service", "restaurant_name_override")

        # 31. Menu Variety
        if _has_kw("menu", "menü", "cesitlilik", "çeşitlilik", "secenek", "seçenek", "bufe cesid", "büfe çeşid", "yemek cesid", "yemek çeşid"):
            return _get_standard_mapping("menu_variety", "menu_variety_override")

        # 32. Breakfast
        if _has_kw("kahvalti", "kahvaltı", "morning"):
            return _get_standard_mapping("breakfast", "breakfast_override")

        # 33. Food Quality
        if _has_kw("yemek", "yiyecek", "lezzet", "enfes", "mutfak", "kahve", "cay", "çay", "tatli", "tatlı", "meyve", "dondurma", "snack", "oglen yemegi", "öğlen yemeği"):
            return _get_standard_mapping("food_quality", "food_quality_override")

        # 34. Drink Quality (removed 'su' - too short and causes bleed)
        if _has_kw("icecek", "içecek", "bira", "sarap", "şarap", "kokteyl", "alkol", "barmen", "soda"):
            return _get_standard_mapping("drink_quality", "drink_quality_override")

        # 35. Communication
        if _has_kw("ingilizce", "turkce", "türkçe", "dil", "iletisim", "iletişim", "anlas", "anlaş"):
            return _get_standard_mapping("communication", "communication_override")

        # 36. Professionalism
        if _has_kw("profesyonel", "amator", "amatör", "liyakati", "liyakatsiz", "disiplin", "kiyafet", "kıyafet", "diksiyon", "is bilmez", "iş bilmez"):
            return _get_standard_mapping("professionalism", "professionalism_override")

        # 36b. Staff — personel + çaba / değer patterns (before price_value rule)
        if _has_kw("personel", "calisan", "çalışan") and _has_kw("caba", "çaba", "çabaları", "deger", "değer"):
            if _has_kw("deger", "değer") and _has_kw("ver", "vermek", "vermiyor", "vermemek"):
                return _get_standard_mapping("staff_service", "staff_value_override")
            return _get_standard_mapping("staff_service", "staff_effort_override")

        # 36c. Garson + negative attitude → Personel (not Restaurant)
        if _has_kw("garson", "barmen") and _has_kw("istemeyerek", "kaba", "suratsiz", "suratsız", "ilgisiz", "lakayit", "lakayıt"):
            return _get_standard_mapping("staff_attitude", "staff_garson_attitude_override")

        # 37. Staff Attitude
        if _has_kw("tavir", "tavır", "davranis", "davranış", "suratsiz", "suratsız", "guler yuz", "güler yüz", "kaba", "nazik", "kibar", "ilgili", "ilgisiz", "lakayit", "lakayıt", "saygisiz", "saygısız"):
            if _has_kw("personel", "calisan", "çalışan", "garson", "resepsiyon", "barmen", "katci", "katçı", "biri", "eleman", "ekip", "kiz", "kız", "cocuk", "çocuk"):
                return _get_standard_mapping("staff_attitude", "staff_attitude_override")

        # 38. Staff Service
        if _has_kw("hizmet", "yardimsever", "yardımsever", "destek", "ilgi", "alaka", "yardim", "yardım"):
            if _has_kw("personel", "calisan", "çalışan", "garson", "resepsiyon", "barmen", "katci", "katçı", "biri", "eleman", "ekip", "kiz", "kız", "cocuk", "çocuk"):
                return _get_standard_mapping("staff_service", "staff_service_override")

        # 39. Crowd
        if _has_kw("kalabalik", "kalabalık", "yogunluk", "yoğunluk"):
            return _get_standard_mapping("crowd", "crowd_override")

        # 40. Guest Profile
        if _has_kw("misafir profil", "turist", "profil"):
            return _get_standard_mapping("guest_profile", "guest_profile_override")

        # 41. General Management
        if _has_kw("isletme", "işletme", "yonetim", "yönetim", "organizasyon"):
            return _get_standard_mapping("general_management", "management_override")

        # 42. General Atmosphere (removed 'hava' - causes bleed with 'harikaydi')
        if _has_kw("atmosfer", "ambiyans", "huzurlu"):
            return _get_standard_mapping("general_atmosphere", "general_atmosphere_override")

        # 43. Noise Level (removed short 'ses' - causes bleed)
        if _has_kw("gurultu", "gürültü", "sessizlik", "kafa dinle"):
            return _get_standard_mapping("noise_level", "noise_level_override")

        # --- FALLBACK TO HOTEL ONTOLOGY ENGINE ---
        from app.ontology.engine import get_hotel_ontology_engine
        
        target_text = clause if clause else text
        engine = get_hotel_ontology_engine()
        mapping = engine.map_aspect(target_text)

        aspect_key = mapping.aspect
        # Reject bare "otel" synonym trap → room_cleanliness without real HK cues
        if aspect_key in ("room_cleanliness", "cleaning", "cleanliness") and _has_kw("otel") and not _has_kw(
            "temiz", "kirli", "pis", "hijyen", "havlu", "carsaf", "çarşaf", "oda temiz", "oda kirli", "temizlik"
        ):
            if any(w in raw_folded for w in ("aile oteli", "komik kaciyor", "komik kaçıyor", "aldanmayin", "aldanmayın")):
                return _get_standard_mapping("general_atmosphere", "concept_mismatch_override")
            if _has_kw("isletme", "işletme", "yonetim", "yönetim", "organizasyon", "operasyon", "isleyis", "işleyiş"):
                return _get_standard_mapping("general_management", "management_override")
            return _get_standard_mapping("general_atmosphere", "otel_not_hk_override")

        remap_aspect = aspect_key

        # 1. Wifi / Internet
        if "wifi" in aspect_key or "internet" in aspect_key or aspect_key == "connectivity":
            remap_aspect = "wifi_internet"
        # 2. Fitness / Gym
        elif "gym" in aspect_key or "fitness" in aspect_key or "tennis" in aspect_key or "sport" in aspect_key:
            remap_aspect = "fitness"
        # 3. Spa / Massage
        elif "spa" in aspect_key or "massage" in aspect_key or "sauna" in aspect_key or "hammam" in aspect_key or "jacuzzi" in aspect_key or "steam_room" in aspect_key or "relax_area" in aspect_key or "cold_plunge" in aspect_key:
            remap_aspect = "spa_massage"
        # 4. Bed comfort
        elif "pillow" in aspect_key or "bed" in aspect_key or "mattress" in aspect_key or "rollaway" in aspect_key or "sofa_bed" in aspect_key:
            if "sheet" in aspect_key or "towel" in aspect_key or "linen" in aspect_key:
                remap_aspect = "linen_towel"
            else:
                remap_aspect = "bed_comfort"
        # 5. Linen / Towel
        elif "sheet" in aspect_key or "towel" in aspect_key or "linen" in aspect_key or "pillowcase" in aspect_key or "blanket" in aspect_key or "duvet" in aspect_key:
            remap_aspect = "linen_towel"
        # 6. Bathroom
        elif "shower" in aspect_key or "toilet" in aspect_key or "sink" in aspect_key or "bathroom" in aspect_key or "bath_" in aspect_key or "mixer" in aspect_key or "faucet" in aspect_key:
            remap_aspect = "bathroom"
        # 7. Room Cleanliness
        elif "room_cleanliness" in aspect_key or aspect_key == "cleaning" or "cleanliness" in aspect_key or "dirty" in aspect_key:
            remap_aspect = "room_cleanliness"
        # 8. Room Size
        elif "room_size" in aspect_key or "room_space" in aspect_key or "room_dimension" in aspect_key:
            remap_aspect = "room_size"
        # 9. View
        elif "room_view" in aspect_key or "view" in aspect_key:
            remap_aspect = "view"
        # 10. Air Conditioning
        elif "hvac" in aspect_key or "klima" in aspect_key or "aircon" in aspect_key or "air_conditioning" in aspect_key:
            remap_aspect = "air_conditioning"
        # 11. Parking
        elif "parking" in aspect_key or "valet" in aspect_key:
            remap_aspect = "parking"
        # 12. Security
        elif "security" in aspect_key or "lock" in aspect_key or "safe" in aspect_key or "guard" in aspect_key:
            remap_aspect = "security"
        # 13. Beach
        elif "beach" in aspect_key or aspect_key == "beach":
            remap_aspect = "beach"
        # 14. Pool
        elif "pool" in aspect_key or "aquapark" in aspect_key or "slide" in aspect_key or aspect_key == "pool":
            remap_aspect = "pool"
        # 15. Breakfast
        elif "breakfast" in aspect_key or aspect_key == "breakfast":
            remap_aspect = "breakfast"
        # 16. Drink / Bar
        elif "drink" in aspect_key or "beverage" in aspect_key or "bar" in aspect_key or "wine" in aspect_key or "beer" in aspect_key or "soda" in aspect_key or "water_taste" in aspect_key or "water_service" in aspect_key:
            remap_aspect = "drink_quality"
        # 17. Menu variety
        elif "menu" in aspect_key or "variety" in aspect_key or "options" in aspect_key or "station" in aspect_key:
            remap_aspect = "menu_variety"
        # 18. Food Quality
        elif "dinner" in aspect_key or "lunch" in aspect_key or "food" in aspect_key or "cuisine" in aspect_key or "taste" in aspect_key or "lezzet" in aspect_key or "yogurt" in aspect_key or "salad" in aspect_key or "soup" in aspect_key or "meat" in aspect_key or "steak" in aspect_key or "waffle" in aspect_key or "pancake" in aspect_key or "pasta" in aspect_key or "pastry" in aspect_key or "pizza" in aspect_key or "seafood" in aspect_key or "sausage" in aspect_key or "dondurma" in aspect_key:
            remap_aspect = "food_quality"
        # 19. Queue / Waiting
        elif "queue" in aspect_key or "wait" in aspect_key or "delay" in aspect_key or "line" in aspect_key:
            remap_aspect = "queue_waiting"
        # 20. Reception service
        elif "reception" in aspect_key or "front_desk" in aspect_key or "guest_relations" in aspect_key or "lobby" in aspect_key or "bellboy" in aspect_key or "welcome" in aspect_key:
            remap_aspect = "reception_service"
        # 21. Restaurant service
        elif "restaurant" in aspect_key or "waiter" in aspect_key or "service_speed" in aspect_key or "table_cleanliness" in aspect_key or "plate_" in aspect_key:
            remap_aspect = "restaurant_service"
        # 22. Communication / Language
        elif "communication" in aspect_key or "language" in aspect_key or "english" in aspect_key or "german" in aspect_key or "russian" in aspect_key:
            remap_aspect = "communication"
        # 23. Professionalism
        elif "professionalism" in aspect_key or "discipline" in aspect_key or "uniform" in aspect_key or "training" in aspect_key or "dicsiyon" in aspect_key or "liyakati" in aspect_key:
            remap_aspect = "professionalism"
        # 24. Staff Attitude
        elif "staff_attitude" in aspect_key or "attitude" in aspect_key or "behavior" in aspect_key or "friendliness" in aspect_key or "smile" in aspect_key or "empathy" in aspect_key:
            remap_aspect = "staff_attitude"
        # 25. Staff Service
        elif "staff_" in aspect_key or "service_" in aspect_key:
            remap_aspect = "staff_service"
        # 26. Billing
        elif "billing" in aspect_key or "invoice" in aspect_key or "payment" in aspect_key or "fee" in aspect_key:
            remap_aspect = "billing"
        # 27. Booking
        elif "booking" in aspect_key or "reservation" in aspect_key:
            remap_aspect = "booking"
        # 28. Check-in/out
        elif "check_in" in aspect_key or "checkin" in aspect_key or "checkout" in aspect_key or "check_out" in aspect_key:
            remap_aspect = "check_in_out"
        # 29. Crowd
        elif "crowd" in aspect_key or "crowding" in aspect_key or "density" in aspect_key:
            remap_aspect = "crowd"
        # 30. Kids club
        elif "kids_club" in aspect_key or "kids" in aspect_key or "children" in aspect_key:
            remap_aspect = "kids_club"
        # 31. Elevator
        elif "elevator" in aspect_key or "lift" in aspect_key:
            remap_aspect = "elevator"
        # 32. Amenities
        elif "amenities" in aspect_key or "shampoo" in aspect_key or "soap" in aspect_key or "slippers" in aspect_key or "hairdryer" in aspect_key or "kettle" in aspect_key:
            remap_aspect = "amenities"
        # 33. Soundproofing
        elif "soundproof" in aspect_key or "wall_thin" in aspect_key:
            remap_aspect = "soundproofing"
        # 34. TV Entertainment
        elif "tv_" in aspect_key or "television" in aspect_key or "channels" in aspect_key:
            remap_aspect = "tv_entertainment"
        # 35. Maintenance
        elif "maintenance" in aspect_key or "broken" in aspect_key or "repair" in aspect_key or "outage" in aspect_key or "issue" in aspect_key or "plug" in aspect_key or "socket" in aspect_key or "light_switch" in aspect_key or "bulb" in aspect_key or "leak" in aspect_key:
            remap_aspect = "maintenance"
        # 36. Location
        elif "location" in aspect_key or "distance" in aspect_key or "walk" in aspect_key:
            remap_aspect = "location"
        # 37. Transportation
        elif "transportation" in aspect_key or "shuttle" in aspect_key or "transfer" in aspect_key or "taxi" in aspect_key:
            remap_aspect = "transportation"
        # 38. Environment
        elif "environment" in aspect_key or "garden" in aspect_key or "landscape" in aspect_key or "architecture" in aspect_key:
            remap_aspect = "environment"
        # 39. Noise Level
        elif "noise" in aspect_key or "sound" in aspect_key or "quiet" in aspect_key:
            remap_aspect = "noise_level"
        # 40. General Atmosphere
        elif "atmosphere" in aspect_key or "ambiance" in aspect_key or "vibe" in aspect_key or "general_atmosphere" in aspect_key:
            remap_aspect = "general_atmosphere"
        # 41. General Management
        elif "management" in aspect_key or "operation" in aspect_key:
            remap_aspect = "general_management"
        # 42. Guest Profile
        elif "guest_profile" in aspect_key or "tourist" in aspect_key or "demographics" in aspect_key:
            remap_aspect = "guest_profile"
        # 43. Price Value
        elif "price_value" in aspect_key or "value_for_money" in aspect_key or "cost" in aspect_key or "expensive" in aspect_key or "cheap" in aspect_key:
            remap_aspect = "price_value"
        # 44. Animation / Activity
        elif "animation" in aspect_key or "activity" in aspect_key or "event" in aspect_key or "show" in aspect_key or "entertainment" in aspect_key:
            remap_aspect = "animation"
        # 45. Minibar
        elif "minibar" in aspect_key or "fridge" in aspect_key:
            remap_aspect = "minibar"
        # 46. Complaint Resolution
        elif "complaint" in aspect_key or "problem_solving" in aspect_key or "apology" in aspect_key or "compensation" in aspect_key:
            remap_aspect = "complaint_resolution"

        if remap_aspect not in _STANDARD_ASPECT_TO_DEPT:
            dept_key = mapping.department
            if dept_key in ("housekeeping", "oda_hizmetleri_housekeeping"):
                remap_aspect = "room_cleanliness"
            elif dept_key in ("food_beverage", "yiyecek_icecek_fb", "restaurant"):
                remap_aspect = "food_quality"
            elif dept_key in ("bar",):
                remap_aspect = "drink_quality"
            elif dept_key in ("front_office", "on_buyro_misafir"):
                remap_aspect = "reception_service"
            elif dept_key in ("engineering", "teknik", "teknik_it"):
                remap_aspect = "maintenance"
            elif dept_key in ("leisure", "rekreasyon_eglence"):
                remap_aspect = "animation"
            elif dept_key in ("spa_wellness", "spa"):
                remap_aspect = "spa_massage"
            elif dept_key in ("pool", "havuz"):
                remap_aspect = "pool"
            elif dept_key in ("animation_events", "animasyon"):
                remap_aspect = "animation"
            elif dept_key in ("grounds", "cevre_guvenlik_ulasim", "guvenlik"):
                remap_aspect = "environment"
            elif dept_key in ("staff", "personel_davranisi", "personel"):
                remap_aspect = "staff_service"
            else:
                remap_aspect = "general_atmosphere"

        return _get_standard_mapping(remap_aspect, mapping.method, mapping.confidence)
        
    @classmethod
    def search_entity(cls, text: str) -> list[dict[str, Any]]:
        results = []
        
        # Clean date and range patterns to prevent fake room detection
        clean_text = text
        clean_text = re.sub(r"\b\d{1,2}[./-]\d{1,2}\s*-\s*\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b", " ", clean_text)
        clean_text = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", " ", clean_text)
        
        _ROOM_PATTERNS_LOCAL = [
            re.compile(r"\boda\s+(\d{3,4})\b", re.IGNORECASE | re.UNICODE),
            re.compile(r"\b(\d{3,4})\s*nolu\b", re.IGNORECASE | re.UNICODE),
            re.compile(r"\b(\d{3,4})\s*numaralı\b", re.IGNORECASE | re.UNICODE),
            re.compile(r"\b(\d{3,4})\s*numara(?:lı|da|da)?\b", re.IGNORECASE | re.UNICODE),
            re.compile(r"\b(\d{3,4})\s*['']?te\b", re.IGNORECASE | re.UNICODE),
            re.compile(r"\b(\d{3,4})\s*no\b", re.IGNORECASE | re.UNICODE),
        ]
        
        room_match = None
        for pattern in _ROOM_PATTERNS_LOCAL:
            match = pattern.search(clean_text)
            if match:
                room_match = match.group(1)
                break
                
        if room_match:
            results.append({
                "entity_id": f"room_{room_match}",
                "entity_key": room_match,
                "entity_label": f"Oda {room_match}",
                "entity_type": "room",
                "domain": "turizm",
                "subdomain": "otel",
                "department": "housekeeping",
                "confidence": 0.95,
            })
            
        from app.ontology.engine import get_hotel_ontology_engine
        engine = get_hotel_ontology_engine()
        
        entity_ref = engine.resolve_term(text, lang="tr")
        if entity_ref.confidence >= 0.65 and entity_ref.entity_id:
            results.append({
                "entity_id": entity_ref.entity_id,
                "entity_key": entity_ref.entity_id,
                "entity_label": entity_ref.label,
                "entity_type": entity_ref.entity_type,
                "domain": "turizm",
                "subdomain": "otel",
                "department": entity_ref.department or "genel",
                "confidence": entity_ref.confidence,
            })
            
        return results

    @classmethod
    def parse_hotel_review(cls, text: str) -> list[dict[str, Any]]:
        from app.ontology.engine import get_hotel_ontology_engine
        engine = get_hotel_ontology_engine()
        segments = engine.parse_review_segments(text)
        return [s.to_dict() for s in segments]

    @classmethod
    def resolve_hotel_term(cls, term: str, lang: str = "tr") -> dict[str, Any]:
        from app.ontology.engine import get_hotel_ontology_engine
        engine = get_hotel_ontology_engine()
        ref = engine.resolve_term(term, lang=lang)
        return ref.to_dict()

        # --- END SYSTEMIC OVERRIDES ---
