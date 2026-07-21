"""
Çoklu sektör ontoloji servisi — domain, departman, aspect eşlemesi.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Optional

from app.services.turkish_nlp_utils import normalize_turkish, tokenize_turkish

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


def reload_ontology() -> None:
    _load_raw.cache_clear()


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


def _fold_tr(text: str) -> str:
    """Türkçe karakterleri ASCII'ye indir — kural eşlemesi için."""
    t = normalize_turkish(text)
    for src, dst in (("ş", "s"), ("ı", "i"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("ç", "c")):
        t = t.replace(src, dst)
    return t


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
        Öncelik: category_rules > ontoloji aspect > ontoloji departman.
        """
        from app.services.category_rules import classify_by_rules
        from app.services.turkish_nlp_utils import (
            CAT_CLEANING, CAT_FINANCE, CAT_FOOD, CAT_OTHER,
            CAT_RECEPTION, CAT_SPA, CAT_STAFF, CAT_TECH,
        )

        normalized = normalize_turkish(clause.lower())
        folded = _fold_tr(clause)
        tokens = set(tokenize_turkish(normalized))
        full_norm = normalize_turkish(text.lower()) if text.strip() else normalized
        full_folded = _fold_tr(text) if text.strip() else folded
        full_tokens = set(tokenize_turkish(full_norm))

        # Manzara → Otel Atmosferi (çevre/konum değil)
        if any(w in folded for w in ("manzara",)) and not any(w in folded for w in ("otopark", "ulasim", "ulaşım", "park", "transfer")):
            return _hotel_mapping("atmosphere", "Otel Atmosferi & Misafir Profili", "view", "Manzara", "manzara_rules", 0.90)

        # Güvenlik (possessive forms: guvenligi, guvenligimiz etc.)
        if any(w in folded for w in ("guvenlik", "guvenlig", "guvenligi", "guvenligimiz", "guvenlikci", "guvenlikçi", "huzur")):
            return _hotel_mapping("grounds", "Çevre, Güvenlik & Ulaşım", "security", "Güvenlik", "guvenlik_rules", 0.95)

        # Animasyon → Rekreasyon & Eğlence (ayrı departman değil)
        if any(w in folded for w in ("animasyon", "animator", "animatör", "animasyoncu")):
            return _hotel_mapping("leisure", "Rekreasyon & Eğlence", "animation", "Animasyon & Etkinlik", "animasyon_rules", 0.90)

        # Otel atmosferi / sicak / davetkar → Atmosphere
        if any(w in folded for w in ("atmosfer",)) or (
            any(w in folded for w in ("sicak", "sıcak", "davetkar", "davetkâr"))
            and any(w in folded for w in ("otel", "ortam", "atmosfer"))
        ):
            return _hotel_mapping("atmosphere", "Otel Atmosferi & Misafir Profili", "general_atmosphere", "Genel Atmosfer", "atmosfer_rules", 0.88)

        # High Priority Specific Rules
        if "dondurma" in folded:
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "menu_variety", "Menü Çeşitliliği", "dondurma_rules", 0.95)

        if any(w in folded for w in ("aquapark", "aqua park", "su kaydiragi", "su kaydırağı", "kaydirak", "kaydırak", "botlar")):
            return _hotel_mapping("leisure", "Rekreasyon & Eğlence", "pool", "Havuz", "aquapark_rules", 0.95)

        if "otopark" in folded or "park alani" in folded or "park alanı" in folded:
            return _hotel_mapping("grounds", "Çevre, Güvenlik & Ulaşım", "parking", "Otopark", "otopark_rules", 0.95)

        if "guvenlik" in folded or "güvenlik" in folded:
            return _hotel_mapping("grounds", "Çevre, Güvenlik & Ulaşım", "security", "Güvenlik", "security_rules", 0.95)

        if any(w in folded for w in ("mimarisi", "mimari", "yurumeniz", "yürümeniz", "mesafe", "yokusu", "yokuşu")):
            return _hotel_mapping("grounds", "Çevre, Güvenlik & Ulaşım", "environment", "Çevre & Bahçe", "architecture_rules", 0.90)

        # Otel içi mesafe / İronik sitem (oda otelin bir ucunda havuz bir ucunda 500m...)
        if any(p in folded for p in ("bir ucunda", "500 metre", "yurumek veya kosmak", "yürümek veya koşmak")) or ("metre" in folded and "isterseniz" in folded):
            return _hotel_mapping("grounds", "Çevre, Güvenlik & Ulaşım", "environment", "Çevre & Bahçe", "distance_sarcasm_rules", 0.95)

        # Bar çalışma saatleri & kısıtlılık
        if any(p in folded for p in ("18 - 00", "18-00", "18:00", "arasi calis", "arası çalış")) or (("bar" in folded or "barda" in folded) and any(w in folded for w in ("saat", "arasi", "arası"))):
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "drink_quality", "İçecek Kalitesi", "bar_hours_rules", 0.95)

        # Personel dil / Türkçe yetersizliği
        if any(p in folded for p in ("turkce bile bilmiyor", "türkçe bile bilmiyor", "turkce bilmiyor", "türkçe bilmiyor", "dil bilmiyor")):
            return _hotel_mapping("staff", "Personel Davranışı", "communication", "Dil & İletişim", "staff_language_rules", 0.95)

        # Crystal / otel — yüksek öncelikli cümlecik kuralları
        if "mobil uygulama" in folded or ("mobil" in tokens and "uygulama" in tokens):
            return _hotel_mapping("engineering", "Teknik Servis & IT", "wifi_internet", "WiFi / İnternet", "dijital_rules", 0.88)

        # WiFi / internet
        if any(w in folded for w in ("wifi", "wi-fi", "wi fi")) or (
            "internet" in folded and any(w in folded for w in ("baglan", "bağlan", "asla", "yok", "copuk", "yavaş", "yavas"))
        ):
            return _hotel_mapping("engineering", "Teknik Servis & IT", "wifi_internet", "WiFi / İnternet", "wifi_rules", 0.92)

        # Ses yalıtımı → Oda Hizmetleri
        if any(w in folded for w in ("ses yalitim", "ses yalıtım", "yalitimi", "yalıtımı", "yan odadaki", "ses geciyor", "ses geçiyor")):
            return _hotel_mapping("housekeeping", "Kat Hizmetleri & Temizlik", "soundproofing", "Ses Yalıtımı", "room_noise", 0.92)

        # İçecek + sıra/bekle → Sıra & Bekleme
        if any(w in folded for w in ("icecek", "içecek", "bar", "limonata", "tekila", "alkol")) and any(
            w in folded for w in ("sira", "sıra", "kuyruk", "dakika", "bekleniyor", "alinamiyor", "alınamıyor")
        ):
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "queue_waiting", "Sıra & Bekleme", "drink_queue", 0.92)

        # Alkol çeşitlilik / bar konsept
        if any(w in folded for w in ("tekila", "belli bar", "cesit alkol", "çeşit alkol", "konsept adi", "konsept adı", "7/24 bar")):
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "drink_quality", "İçecek Kalitesi", "drink_variety", 0.9)

        # Değer pişmanlığı
        if any(p in folded for p in (
            "paramiz cop", "paramız çöp", "para cop oldu", "para çöp oldu",
            "pismanliktan", "pişmanlıktan", "paraya degmez", "paraya değmez",
            "paranin karsiligi yok", "paranın karşılığı yok",
            "parasini carcur", "parasını çarçur", "carcur etmek", "çarçur etmek",
        )) or (("pisman" in folded or "pişman" in folded) and ("para" in folded or "cop" in folded or "çöp" in folded)):
            return _hotel_mapping("front_office", "Ön Büro & Misafir İlişkileri", "price_value", "Fiyat & Değer", "value_regret", 0.9)

        # Her şey dahil kaos deneyimi
        if any(p in folded for p in ("hersey dahil", "herşey dahil", "her sey dahil", "all inclusive")):
            if any(p in folded for p in ("karisik", "karışık", "yorucu", "yorgunluk", "kalabalik", "kalabalık", "kuyruk")):
                return _hotel_mapping("atmosphere", "Otel Atmosferi & Misafir Profili", "general_atmosphere", "Genel Atmosfer", "all_inclusive_experience", 0.88)
        if any(p in folded for p in ("ekstra karisik", "ekstra karışık", "ekstra yorucu")):
            return _hotel_mapping("atmosphere", "Otel Atmosferi & Misafir Profili", "general_atmosphere", "Genel Atmosfer", "all_inclusive_experience", 0.88)

        # İçecek soda (temizlik sodası değil)
        if re.search(r"(?<![a-zçğıöşü])soda(?![a-zçğıöşü])", folded):
            if not any(p in folded for p in ("soda tabanc", "temizlik soda", "deterjan")):
                return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "drink_quality", "İçecek Kalitesi", "soda_beverage", 0.9)

        # Çatal / bıçak — restoran servisi
        if any(w in folded for w in ("catal", "çatal", "bicak", "bıçak")):
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "restaurant_service", "Restoran Servisi", "cutlery_rules", 0.92)

        # Kıyma kalitesi → F&B
        if "kiyma" in folded or "kıyma" in folded:
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "food_quality", "Yemek Kalitesi", "meat_quality", 0.92)

        # Oda boyutu
        if any(p in folded for p in ("odalar cok kucuk", "odalar çok küçük", "oda cok kucuk", "oda çok küçük", "odalar kucuk", "odalar dar")):
            if not any(w in folded for w in ("kirli", "pis", "havlu", "temizlik", "toz")):
                return _hotel_mapping("housekeeping", "Kat Hizmetleri & Temizlik", "room_size", "Oda Boyutu", "room_size", 0.9)

        # Restoran masa temizliği
        if any(p in folded for p in ("temizletemed", "masa kirli", "oturacak bir masa", "masa sil")):
            if "oda" not in folded or any(w in folded for w in ("masa", "restoran", "catal", "çatal")):
                return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "restaurant_service", "Restoran Servisi", "table_cleanliness", 0.9)

        if ("si yeterliydi" in folded or "2 si yeterli" in folded) and "beklem" in folded:
            return _hotel_mapping("leisure", "Rekreasyon & Eğlence", "pool", "Havuz", "aquapark_clause", 0.82)

        # Pankek / yemek kuyruğu
        if any(w in folded for w in ("pankek", "kuyruk", "sira bekle")) and any(
            w in folded for w in ("pankek", "yemek", "bufe", "büfe", "kahvalti", "restoran", "sira", "kuyruk")
        ):
            if "check" not in folded and "resepsiyon" not in folded and "lobi" not in folded:
                return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "queue_waiting", "Sıra & Bekleme", "food_queue", 0.88)

        if "musteri temsilcisi" in folded:
            return _hotel_mapping("atmosphere", "Otel Atmosferi & Misafir Profili", "general_management", "Genel Yönetim", "hotel_general", 0.78)

        if "yonlendirme" in folded and "bilgilendirme" in folded:
            return _hotel_mapping("front_office", "Ön Büro & Misafir İlişkileri", "reception_service", "Resepsiyon Hizmeti", "front_office_rules", 0.88)

        if any(w in folded for w in ("senzlog", "senzlong", "sezlong", "sezlong")):
            return _hotel_mapping("leisure", "Rekreasyon & Eğlence", "pool", "Havuz", "havuz_rules", 0.9)

        if any(w in folded for w in ("bakimli hale getirilebilir", "bakımlı hale getirilebilir", "daha bakimli", "daha bakımlı")):
            return _hotel_mapping("engineering", "Teknik Servis & IT", "maintenance", "Bakım & Onarım", "room_maintenance", 0.88)

        if "ozellikle banyo" in folded or "özellikle banyo" in folded:
            return _hotel_mapping("housekeeping", "Kat Hizmetleri & Temizlik", "bathroom", "Banyo & Tuvalet", "room_bathroom", 0.86)

        if any(w in folded for w in ("asansor", "asansör")):
            return _hotel_mapping("engineering", "Teknik Servis & IT", "elevator", "Asansör", "elevator_rules", 0.92)

        if any(w in folded for w in ("laundry", "kuru temizleme", "utu hizmeti", "ütü hizmeti", "havlu degisimi", "havlu değişimi")):
            return _hotel_mapping("housekeeping", "Kat Hizmetleri & Temizlik", "linen_towel", "Çarşaf & Havlu", "laundry_rules", 0.92)

        if any(w in folded for w in ("pastane", "waffle", "kunefe", "künefe", "baklava", "kek", "pasta")):
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "menu_variety", "Menü Çeşitliliği", "patisserie_rules", 0.92)

        if any(w in folded for w in ("turk kahvesi", "türk kahvesi", "espresso", "filtre kahve")):
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "drink_quality", "İçecek Kalitesi", "hot_beverages_rules", 0.92)

        if any(w in folded for w in ("mini club", "miniclub", "cocuk kulubu", "çocuk kulübü", "amfi tiyatro", "gece gosterisi", "gece gösterisi", "canli muzik", "canlı müzik", "animasyon ekibi")):
            return _hotel_mapping("leisure", "Rekreasyon & Eğlence", "animation", "Animasyon & Etkinlik", "animation_rules", 0.92)

        if any(w in folded for w in ("bellboy", "bavul", "valiz", "oda teslimi", "erken giris", "erken giriş", "gec cikis", "geç çıkış", "oda karti", "oda kartı", "karsilama", "karşılama", "guest relation", "misafir iliskileri", "misafir ilişkileri")):
            return _hotel_mapping("front_office", "Ön Büro & Misafir İlişkileri", "check_in_out", "Giriş/Çıkış", "reception_rules", 0.92)

        if any(w in folded for w in ("sicak su", "sıcak su", "dus basligi", "duş başlığı", "su akmiyor", "su akmıyor", "klima sogutmuyor", "klima soğutmuyor")):
            return _hotel_mapping("engineering", "Teknik Servis & IT", "air_conditioning", "Klima", "tech_rules", 0.92)

        if any(w in folded for w in ("hamburger", "gozleme", "gözleme", "kizartma", "kızartma", "ara sicak", "ara sıcak")):
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "food_quality", "Yemek Kalitesi", "food_snack", 0.88)

        if any(w in folded for w in ("bal kaymak", "cesitlilik yetersiz", "çeşitlilik yetersiz")) and "bitiyor" in folded:
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "menu_variety", "Menü Çeşitliliği", "food_variety", 0.88)

        if any(w in folded for w in ("yogun degildi", "yoğun değildi", "yogun degil", "yoğun değil")) and "beklemeden" in folded:
            return _hotel_mapping("atmosphere", "Otel Atmosferi & Misafir Profili", "crowd", "Kalabalık", "front_office_crowd", 0.88)

        if any(w in folded for w in ("cilek", "çilek", "kiraz", "kavun", "meyve")) and any(w in folded for w in ("cikmadi", "çıkmadı", "yok")):
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "menu_variety", "Menü Çeşitliliği", "food_fruit", 0.86)

        if "2 sinif" in folded or "2 sınıf" in folded or "2. sinif" in folded or "2. sınıf" in folded:
            if any(w in full_folded for w in ("raki", "rakı", "sarap", "şarap", "kalitesiz")):
                return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "drink_quality", "İçecek Kalitesi", "bar_quality", 0.88)

        if _has_minibar_context(full_norm) and any(w in folded for w in ("yiyecek yok", "hicbir yiyecek", "hiçbir yiyecek")):
            return _hotel_mapping("food_beverage", "Yiyecek & İçecek (F&B)", "minibar", "Minibar", "minibar_food", 0.88)

        if any(w in folded for w in ("plaj", "deniz", "kumsal", "cakil", "çakıl")) and not _is_patisserie_context(normalized, tokens):
            return _hotel_mapping("leisure", "Rekreasyon & Eğlence", "beach", "Plaj & Deniz", "beach_rules", 0.88)

        if "koridor" in folded and "tabak" in folded:
            return _hotel_mapping("housekeeping", "Kat Hizmetleri & Temizlik", "room_cleanliness", "Oda Temizliği", "housekeeping_rules", 0.88)

        rule_result = classify_by_rules(clause)
        rule_cat = rule_result.category
        rule_conf = rule_result.confidence
        rule_score = rule_result.rule_score

        hotel_cats = {
            CAT_CLEANING, CAT_FOOD, CAT_RECEPTION, CAT_TECH, CAT_SPA, CAT_STAFF, CAT_FINANCE,
        }
        non_hotel_markers = (
            "mobil uygulama",
        )
        force_turizm = (
            rule_cat in hotel_cats
            and not any(m in normalized for m in non_hotel_markers)
        )

        _RULE_TO_ONTOLOGY: dict[str, tuple[str, str, str, str]] = {
            CAT_CLEANING: ("housekeeping", "Kat Hizmetleri & Temizlik", "room_cleanliness", "Oda Temizliği"),
            CAT_FOOD: ("food_beverage", "Yiyecek & İçecek (F&B)", "food_quality", "Yemek Kalitesi"),
            CAT_RECEPTION: ("front_office", "Ön Büro & Misafir İlişkileri", "reception_service", "Resepsiyon Hizmeti"),
            CAT_TECH: ("engineering", "Teknik Servis & IT", "air_conditioning", "Klima"),
            CAT_SPA: ("leisure", "Rekreasyon & Eğlence", "pool", "Havuz"),
            CAT_FINANCE: ("front_office", "Ön Büro & Misafir İlişkileri", "price_value", "Fiyat & Değer"),
            CAT_STAFF: ("staff", "Personel Davranışı", "staff_attitude", "Personel Tutumu"),
            CAT_OTHER: ("atmosphere", "Otel Atmosferi & Misafir Profili", "general_atmosphere", "Genel Atmosfer"),
        }

        spa_keywords = {"spa", "masaj", "wellness", "sauna", "hamam"}
        havuz_keywords = {"havuz", "aquapark", "aquaprk", "plaj", "kaydirak", "sezlong", "senzlong", "deniz", "kumsal"}
        tech_maint_keywords = {"demir", "demirler", "yipranmis"}

        # Tam metin bağlamı — cümlecikte anahtar kelime yoksa üst yorumdan devral
        if not any(_keyword_matches(w, normalized, tokens) for w in havuz_keywords):
            if any(_keyword_matches(w, full_norm, full_tokens) for w in ("aquapark", "aquaprk", "kaydirak", "3 aquaprk")):
                if any(w in normalized for w in ("yeterli", "kapali", "kapalı", "sira", "bekle", "2", "3", "bir tanesi")):
                    return {
                        "domain": "turizm", "domainLabel": "Turizm", "subdomain": "otel", "subdomainLabel": "Otel",
                        "department": "havuz", "departmentLabel": "Havuz",
                        "aspect": "aquapark", "aspectLabel": "Aquapark", "aspect_key": "aquapark",
                        "matchedKeywords": ["context:aquapark"], "confidence": 0.82, "method": "context_inherit",
                    }

        food_queue_markers = ("pankek", "salam", "salam tabagi", "yemek kuyrugu", "restorant", "restoran")
        if any(m in folded for m in food_queue_markers) and "koridor" not in folded:
            if any(w in folded for w in ("pankek", "salam", "sinek", "tabak", "kirli", "kuyruk", "sira", "yemek")):
                return _hotel_mapping("restaurant", "Restaurant", "food_quality", "Yemek Kalitesi", "food_context", 0.88)

        if "senzlong" in normalized or "sezlong" in normalized:
            return {
                "domain": "turizm", "domainLabel": "Turizm", "subdomain": "otel", "subdomainLabel": "Otel",
                "department": "havuz", "departmentLabel": "Havuz",
                "aspect": "pool_lounger", "aspectLabel": "Şezlong", "aspect_key": "pool_lounger",
                "matchedKeywords": ["senzlong"], "confidence": 0.9, "method": "havuz_rules",
            }

        if "otel kapasitesine" in normalized or "kapasitesine ulasmad" in normalized:
            return {
                "domain": "turizm", "domainLabel": "Turizm", "subdomain": "otel", "subdomainLabel": "Otel",
                "department": "front_office", "departmentLabel": "Front Office",
                "aspect": "capacity_management", "aspectLabel": "Kapasite Yönetimi", "aspect_key": "capacity_management",
                "matchedKeywords": [], "confidence": 0.85, "method": "front_office_rules",
            }

        if "yonlendirme" in normalized and "bilgilendirme" in normalized:
            return {
                "domain": "turizm", "domainLabel": "Turizm", "subdomain": "otel", "subdomainLabel": "Otel",
                "department": "front_office", "departmentLabel": "Front Office",
                "aspect": "reception_service", "aspectLabel": "Resepsiyon Hizmeti", "aspect_key": "reception_service",
                "matchedKeywords": [], "confidence": 0.85, "method": "front_office_rules",
            }

        if "garson" in normalized and any(w in normalized for w in ("icecek", "içecek", "siparis", "sipariş", "isteyerek")):
            return {
                "domain": "turizm", "domainLabel": "Turizm", "subdomain": "otel", "subdomainLabel": "Otel",
                "department": "personel", "departmentLabel": "Personel",
                "aspect": "staff_behavior", "aspectLabel": "Personel Davranışı", "aspect_key": "staff_behavior",
                "matchedKeywords": ["garson"], "confidence": 0.9, "method": "staff_rules",
            }

        if "musteri temsilcisi" in normalized:
            return {
                "domain": "turizm", "domainLabel": "Turizm", "subdomain": "otel", "subdomainLabel": "Otel",
                "department": "genel", "departmentLabel": "Genel",
                "aspect": "general", "aspectLabel": "Genel", "aspect_key": "general",
                "matchedKeywords": [], "confidence": 0.75, "method": "hotel_general",
            }

        if (rule_score >= 1.0 or rule_conf >= 0.72) and rule_cat in hotel_cats:
            dept_key, dept_label, asp_key, asp_label = _RULE_TO_ONTOLOGY.get(
                rule_cat, ("genel", "Genel", "general", "Genel")
            )
            if _is_aquapark_maintenance_context(normalized, tokens) or (
                any(w in normalized for w in ("bakim", "bakima", "bakım"))
                and any(_keyword_matches(w, full_norm, full_tokens) for w in ("aquapark", "aquaprk", "kaydirak", "havuz"))
            ):
                dept_key, dept_label, asp_key, asp_label = "leisure", "Rekreasyon & Eğlence", "pool", "Havuz"
            elif any(_keyword_matches(w, normalized, tokens) for w in ("aquapark", "aquaprk", "kaydirak")):
                dept_key, dept_label, asp_key, asp_label = "leisure", "Rekreasyon & Eğlence", "pool", "Havuz"
            elif _is_animation_context(normalized, tokens):
                dept_key, dept_label, asp_key, asp_label = "leisure", "Rekreasyon & Eğlence", "animation", "Animasyon & Etkinlik"
            elif _has_minibar_context(normalized):
                hk_minibar = any(w in normalized for w in (
                    "gorevlisi", "görevlisi", "dolduruyor", "dolduruyorlardi", "dolduruyorlardı",
                    "temizdi", "temiz", "kat hizmet", "housekeeping", "servis geldi",
                ))
                if hk_minibar:
                    dept_key, dept_label, asp_key, asp_label = "housekeeping", "Kat Hizmetleri & Temizlik", "amenities", "Buklet Malzemeleri"
                elif any(w in normalized for w in ("bozuk", "arizali", "arızalı", "calismiyor", "çalışmıyor", "sogutmuyor")):
                    dept_key, dept_label, asp_key, asp_label = "engineering", "Teknik Servis & IT", "maintenance", "Bakım & Onarım"
                elif any(w in normalized for w in ("ucret", "ücret", "fatura", "pahali", "pahalı", "fahis", "fahiş")):
                    dept_key, dept_label, asp_key, asp_label = "front_office", "Ön Büro & Misafir İlişkileri", "billing", "Fatura & Ödeme"
                else:
                    dept_key, dept_label, asp_key, asp_label = "food_beverage", "Yiyecek & İçecek (F&B)", "minibar", "Minibar"
            elif _is_patisserie_context(normalized, tokens):
                dept_key, dept_label, asp_key, asp_label = "food_beverage", "Yiyecek & İçecek (F&B)", "menu_variety", "Menü Çeşitliliği"
            elif any(_keyword_matches(w, normalized, tokens) for w in tech_maint_keywords):
                dept_key, dept_label, asp_key, asp_label = "engineering", "Teknik Servis & IT", "maintenance", "Bakım & Onarım"
            elif any(_keyword_matches(w, normalized, tokens) for w in ("bakim", "bakima")) and not any(
                _keyword_matches(w, normalized, tokens) for w in ("aquapark", "aquaprk", "kaydirak", "havuz")
            ):
                dept_key, dept_label, asp_key, asp_label = "engineering", "Teknik Servis & IT", "maintenance", "Bakım & Onarım"
            elif any(_keyword_matches(w, normalized, tokens) for w in ("etkinlik", "etkinlikler", "animasyon", "konser", "aktivite")):
                dept_key, dept_label, asp_key, asp_label = "leisure", "Rekreasyon & Eğlence", "animation", "Animasyon & Etkinlik"
            elif any(_keyword_matches(w, normalized, tokens) for w in ("plaj", "kumsal", "cakil", "deniz")) and not _is_patisserie_context(normalized, tokens):
                dept_key, dept_label, asp_key, asp_label = "leisure", "Rekreasyon & Eğlence", "beach", "Plaj & Deniz"
            elif any(_keyword_matches(w, normalized, tokens) for w in ("bos tabaklar", "boş tabaklar", "koridorlara", "tabaklar")):
                if "restoran" in normalized or "restorant" in normalized or "ana restorant" in normalized:
                    dept_key, dept_label, asp_key, asp_label = "food_beverage", "Yiyecek & İçecek (F&B)", "restaurant_service", "Restoran Servisi"
                else:
                    dept_key, dept_label, asp_key, asp_label = "housekeeping", "Kat Hizmetleri & Temizlik", "room_cleanliness", "Oda Temizliği"
            elif any(w in normalized for w in ("raki", "rakı", "sarap", "şarap", "bira", "kokteyl", "tekila", "icki", "icecek", "içecek", "limonata", "soda")):
                dept_key, dept_label, asp_key, asp_label = "food_beverage", "Yiyecek & İçecek (F&B)", "drink_quality", "İçecek Kalitesi"
            elif _is_bar_drink_context(normalized):
                dept_key, dept_label, asp_key, asp_label = "food_beverage", "Yiyecek & İçecek (F&B)", "drink_quality", "İçecek Kalitesi"
            if any(w in normalized for w in ("catal", "çatal", "bicak", "bıçak", "kiyma", "kıyma")):
                dept_key, dept_label, asp_key, asp_label = "food_beverage", "Yiyecek & İçecek (F&B)", "food_quality", "Yemek Kalitesi"
            if any(_keyword_matches(w, normalized, tokens) for w in ("personel", "personelin", "garson", "şef", "sef", "calisan")):
                if any(w in normalized for w in ("kokteyl", "kaba", "ilgisiz", "ilgi", "alakasiz", "lakayit", "icecek", "içecek", "siparis", "sipariş", "isteyerek")):
                    dept_key, dept_label, asp_key, asp_label = "staff", "Personel Davranışı", "staff_attitude", "Personel Tutumu"
            if "restoran" in normalized or "restorant" in normalized:
                if any(w in normalized for w in ("sira", "kuyruk", "beklemek", "yemek", "icecek", "içecek", "kalitesiz")):
                    dept_key, dept_label, asp_key, asp_label = "food_beverage", "Yiyecek & İçecek (F&B)", "food_quality", "Yemek Kalitesi"
            if any(_keyword_matches(w, normalized, tokens) for w in ("masa tenisi", "aktivite", "animasyon", "etkinlik", "konser")):
                dept_key, dept_label, asp_key, asp_label = "leisure", "Rekreasyon & Eğlence", "animation", "Animasyon & Etkinlik"
            if "spa" in tokens and _is_spa_wellness_context(normalized, tokens) and "havuz" not in tokens and "aquapark" not in normalized:
                dept_key, dept_label, asp_key, asp_label = "leisure", "Rekreasyon & Eğlence", "spa_massage", "Spa & Masaj"
            # Bar → housekeeping yalnızca gerçek temizlik bağlamında; soda/içecek koru
            if dept_key == "food_beverage" and not _is_bar_drink_context(normalized):
                if any(w in normalized for w in ("temiz", "kirli", "havlu", "carsaf", "çarşaf")):
                    dept_key, dept_label, asp_key, asp_label = "housekeeping", "Kat Hizmetleri & Temizlik", "room_cleanliness", "Oda Temizliği"
            # CAT_FINANCE kuralları değer pişmanlığıysa Ön Büro / Fiyat & Değer'e çevir
            if rule_cat == CAT_FINANCE:
                from app.services.category_rules import _is_value_regret_context, _is_all_inclusive_experience
                if _is_value_regret_context(normalized) or _is_all_inclusive_experience(normalized):
                    dept_key, dept_label, asp_key, asp_label = "front_office", "Ön Büro & Misafir İlişkileri", "price_value", "Fiyat & Değer"
            return {
                "domain": "turizm",
                "domainLabel": "Turizm",
                "subdomain": "otel",
                "subdomainLabel": "Otel",
                "department": dept_key,
                "departmentLabel": dept_label,
                "aspect": asp_key,
                "aspectLabel": asp_label,
                "aspect_key": asp_key,
                "matchedKeywords": [],
                "confidence": min(0.95, rule_conf),
                "method": "rules",
            }

        best_score = 0.0
        best: Optional[dict[str, Any]] = None

        primary_domains = cls.detect_domain(text, top_k=2) if text.strip() else []
        primary_domain_key = primary_domains[0]["domain"] if primary_domains else "turizm"
        primary_domain_score = primary_domains[0]["score"] if primary_domains else 0.0
        restrict_domain = primary_domain_score >= 8.0

        domain_iter = _load_raw().get("domains", [])
        if restrict_domain or force_turizm:
            domain_iter = [d for d in domain_iter if d["key"] == primary_domain_key] or domain_iter
            if force_turizm:
                turizm = [d for d in _load_raw().get("domains", []) if d["key"] == "turizm"]
                if turizm:
                    domain_iter = turizm

        for domain in domain_iter:
            for sub in domain.get("subdomains", []):
                for dept in sub.get("departments", []):
                    if dept["key"] == "bar" and not _is_bar_drink_context(normalized):
                        continue
                    dept_score = 0.0
                    for kw in dept.get("keywords", []):
                        if _keyword_matches(kw, normalized, tokens):
                            dept_score += 1.5

                    for aspect in dept.get("aspects", []):
                        aspect_score = dept_score
                        matched_kw: list[str] = []
                        for kw in aspect.get("keywords", []):
                            if _keyword_matches(kw, normalized, tokens):
                                aspect_score += 3.0
                                matched_kw.append(kw)

                        if aspect_score > best_score:
                            best_score = aspect_score
                            best = {
                                "domain": domain["key"],
                                "domainLabel": domain["label"],
                                "subdomain": sub["key"],
                                "subdomainLabel": sub["label"],
                                "department": dept["key"],
                                "departmentLabel": dept["label"],
                                "aspect": aspect["key"],
                                "aspectLabel": aspect["label"],
                                "aspect_key": aspect["key"],
                                "matchedKeywords": matched_kw,
                                "confidence": min(0.95, 0.55 + aspect_score * 0.08),
                            }

        if best:
            return best

        domains = cls.detect_domain(text, top_k=1)
        primary = domains[0] if domains else {"domain": "turizm", "domainLabel": "Turizm"}
        return {
            "domain": primary["domain"],
            "domainLabel": primary.get("domainLabel", primary["domain"]),
            "subdomain": "otel",
            "subdomainLabel": "Otel",
            "department": "atmosphere",
            "departmentLabel": "Otel Atmosferi & Misafir Profili",
            "aspect": "general_atmosphere",
            "aspectLabel": "Genel Atmosfer",
            "aspect_key": "general_atmosphere",
            "matchedKeywords": [],
            "confidence": 0.5,
        }

    @classmethod
    def search_entity(cls, query: str) -> list[dict[str, Any]]:
        """Sorgudan entity (oda, havuz, mobil uygulama, kargo no vb.) eşleşmesi."""
        normalized = normalize_turkish(query.lower())
        results: list[dict[str, Any]] = []

        room_match = re.search(
            r"\b(?:oda\s+)?(\d{3,4})(?:\s*(?:nolu|numarali|no|te))?\b",
            normalized,
        )
        if room_match or re.search(r"\boda\s+\d{3,4}\b", normalized):
            num = room_match.group(1) if room_match else ""
            if not num:
                fallback = re.search(r"\b(\d{3,4})\b", normalized)
                num = fallback.group(1) if fallback else ""
            if num:
                results.append({
                    "entity_id": f"room_{num}",
                    "entity_key": num,
                    "entity_label": f"Oda {num}",
                    "entity_type": "room",
                    "domain": "turizm",
                    "subdomain": "otel",
                    "department": "housekeeping",
                    "score": 10.0,
                })

        for entity in _load_raw().get("entities", []):
            score = 0.0
            for alias in entity.get("aliases", [entity["key"], entity["label"]]):
                nalias = normalize_turkish(alias.lower())
                if nalias in normalized:
                    score = max(score, len(nalias) * 0.5 + 2.0)
                elif any(nalias in tok for tok in tokenize_turkish(normalized)):
                    score = max(score, 1.5)

            if score > 0:
                results.append({
                    "entity_id": entity["key"],
                    "entity_key": entity["key"],
                    "entity_label": entity["label"],
                    "entity_type": entity.get("type", "facility"),
                    "domain": entity.get("domain"),
                    "subdomain": entity.get("subdomain"),
                    "department": entity.get("department"),
                    "score": round(score, 2),
                })

        if "havuz" in normalized and ("alan" in normalized or "kirli" in normalized or "kucuk" in normalized):
            results.append({
                "entity_id": "havuz_alani",
                "entity_key": "havuz",
                "entity_label": "Havuz Alanı",
                "entity_type": "area",
                "domain": "turizm",
                "subdomain": "otel",
                "department": "havuz",
                "score": 7.0,
            })

        results.sort(key=lambda x: -x["score"])
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in results:
            if r["entity_id"] not in seen:
                seen.add(r["entity_id"])
                unique.append(r)
        return unique

    @classmethod
    def is_entity_query(cls, query: str) -> bool:
        """Entity/place-specific operasyonel sorgu mu?"""
        normalized = normalize_turkish(query.lower())
        operational = (
            "sorun", "sikayet", "en son", "son sorun", "kaldi", "cozuldu",
            "giderildi", "durum", "rapor", "gecmis", "acik", "devam",
            "gecikme", "memnuniyet", "sikayetler",
        )
        has_op = any(k in normalized for k in operational)
        entities = cls.search_entity(query)
        return bool(entities and (has_op or len(entities) > 0))

    @classmethod
    def resolve_domain(cls, text: str, hint: Optional[str] = None) -> tuple[str, str, float]:
        """(domain_key, domain_label, confidence)"""
        if hint:
            for d in _load_raw().get("domains", []):
                if d["key"] == hint or normalize_turkish(d["label"].lower()) == normalize_turkish(hint.lower()):
                    return d["key"], d["label"], 0.9
        detected = cls.detect_domain(text, top_k=1)
        if detected:
            d = detected[0]
            conf = min(0.95, 0.5 + d.get("score", 0) * 0.1)
            return d["domain"], d.get("domainLabel", d["domain"]), conf
        return "turizm", "Turizm", 0.5

    @classmethod
    def resolve_department(cls, text: str, domain_id: str) -> tuple[str, str, float]:
        """(department_key, department_label, confidence)"""
        mapping = cls.map_aspect_to_department(text, text)
        if mapping.get("domain") == domain_id:
            return (
                mapping.get("department", "genel"),
                mapping.get("departmentLabel", "Genel"),
                mapping.get("confidence", 0.6),
            )
        for d in _load_raw().get("domains", []):
            if d["key"] != domain_id:
                continue
            for sub in d.get("subdomains", []):
                for dept in sub.get("departments", []):
                    return dept["key"], dept["label"], 0.55
        return "genel", "Genel", 0.5

    @classmethod
    def resolve_aspect(cls, text: str, domain_id: str, dept_id: str) -> tuple[str, str, float]:
        """(aspect_key, aspect_label, confidence)"""
        mapping = cls.map_aspect_to_department(text, text)
        if mapping.get("domain") == domain_id:
            return (
                mapping.get("aspect_key", mapping.get("aspect", "general")),
                mapping.get("aspectLabel", "Genel"),
                mapping.get("confidence", 0.6),
            )
        return "general", "Genel", 0.5

    @classmethod
    def aspect_department(cls, domain_id: str, aspect_key: str) -> tuple[str, str]:
        """Aspect'in ait olduğu departmanı döner."""
        for d in _load_raw().get("domains", []):
            if d["key"] != domain_id:
                continue
            for sub in d.get("subdomains", []):
                for dept in sub.get("departments", []):
                    for aspect in dept.get("aspects", []):
                        if aspect["key"] == aspect_key:
                            return dept["key"], dept["label"]
        return "genel", "Genel"

    @classmethod
    def list_domains(cls) -> list[dict[str, str]]:
        """API uyumluluğu — tüm domain listesi."""
        return [{"id": d["key"], "label": d["label"]} for d in _load_raw().get("domains", [])]

    @classmethod
    def get_domain(cls, domain_id: str) -> Optional[dict[str, Any]]:
        """Domain detayı — departmanlar düzleştirilmiş."""
        norm = normalize_turkish(domain_id.lower())
        for domain in _load_raw().get("domains", []):
            if domain["key"] == norm or normalize_turkish(domain["label"].lower()) == norm:
                departments: list[dict[str, Any]] = []
                for sub in domain.get("subdomains", []):
                    for dept in sub.get("departments", []):
                        departments.append({
                            "key": dept["key"],
                            "label": dept["label"],
                            "subdomain": sub["key"],
                            "subdomain_label": sub["label"],
                            "aspects": dept.get("aspects", []),
                        })
                return {
                    "id": domain["key"],
                    "key": domain["key"],
                    "label": domain["label"],
                    "keywords": domain.get("keywords", []),
                    "subdomains": domain.get("subdomains", []),
                    "departments": departments,
                }
        return None

    @classmethod
    def _find_domain_block(cls, domain_id: str) -> Optional[dict[str, Any]]:
        norm = normalize_turkish(domain_id.lower())
        for domain in _load_raw().get("domains", []):
            if domain["key"] == norm:
                return domain
        return None

    @classmethod
    def resolve_domain(
        cls,
        text: str,
        hint: Optional[str] = None,
    ) -> tuple[str, str, float]:
        """Cümlecik için birincil domain — (id, label, confidence)."""
        if hint:
            dom = cls.get_domain(hint)
            if dom:
                return dom["key"], dom["label"], 0.85

        detected = cls.detect_domain(text, top_k=1)
        if detected:
            d = detected[0]
            conf = min(0.95, 0.5 + d.get("score", 0) * 0.08)
            return d["domain"], d.get("domainLabel", d["domain"]), conf
        return "turizm", "Turizm", 0.5

    @classmethod
    def resolve_department(cls, text: str, domain_id: str) -> tuple[str, str, float]:
        """Domain içinde en iyi departman."""
        mapping = cls.map_aspect_to_department(text, text)
        if mapping.get("domain") == domain_id or mapping.get("department") != "genel":
            conf = mapping.get("confidence", 0.6)
            return mapping["department"], mapping["departmentLabel"], conf

        normalized = normalize_turkish(text.lower())
        domain = cls._find_domain_block(domain_id)
        if not domain:
            return "genel", "Genel", 0.4

        best_dept = "genel"
        best_label = "Genel"
        best_score = 0.0
        for sub in domain.get("subdomains", []):
            for dept in sub.get("departments", []):
                score = 0.0
                for kw in dept.get("keywords", []):
                    if normalize_turkish(kw) in normalized:
                        score += 1.5
                if score > best_score:
                    best_score = score
                    best_dept = dept["key"]
                    best_label = dept["label"]

        conf = min(0.9, 0.45 + best_score * 0.12) if best_score else 0.4
        return best_dept, best_label, conf

    @classmethod
    def resolve_aspect(
        cls,
        text: str,
        domain_id: str,
        dept_id: str,
    ) -> tuple[str, str, float]:
        """Departman içinde en iyi aspect."""
        mapping = cls.map_aspect_to_department(text, text)
        if mapping.get("aspect") and mapping.get("aspect") != "general":
            return mapping["aspect"], mapping["aspectLabel"], mapping.get("confidence", 0.65)

        normalized = normalize_turkish(text.lower())
        domain = cls._find_domain_block(domain_id)
        if not domain:
            return "general", "Genel", 0.4

        best_key = "general"
        best_label = "Genel"
        best_score = 0.0
        for sub in domain.get("subdomains", []):
            for dept in sub.get("departments", []):
                if dept_id != "genel" and dept["key"] != dept_id:
                    continue
                for aspect in dept.get("aspects", []):
                    score = 0.0
                    for kw in aspect.get("keywords", []):
                        if normalize_turkish(kw) in normalized:
                            score += 2.0
                    if score > best_score:
                        best_score = score
                        best_key = aspect["key"]
                        best_label = aspect["label"]

        conf = min(0.92, 0.5 + best_score * 0.1) if best_score else 0.45
        return best_key, best_label, conf

    @classmethod
    def aspect_department(cls, domain_id: str, aspect_key: str) -> tuple[str, str]:
        """Aspect'in ait olduğu departman."""
        domain = cls._find_domain_block(domain_id)
        if not domain:
            return "genel", "Genel"
        for sub in domain.get("subdomains", []):
            for dept in sub.get("departments", []):
                for aspect in dept.get("aspects", []):
                    if aspect["key"] == aspect_key:
                        return dept["key"], dept["label"]
        return "genel", "Genel"

    @classmethod
    def get_department_path(cls, domain_id: str, dept_id: str) -> str:
        dom = cls.get_domain(domain_id)
        if not dom:
            return f"{domain_id} / {dept_id}"
        for dept in dom.get("departments", []):
            if dept["key"] == dept_id:
                return f"{dom['label']} → {dept['label']}"
        return f"{dom['label']} → {dept_id}"

    @classmethod
    def detect_query_type(cls, query: str) -> dict[str, Any]:
        """Chatbot yönlendirme — entity / domain / department / general."""
        normalized = normalize_turkish(query.lower())

        entities = cls.search_entity(query)
        if entities and any(
            k in normalized
            for k in ("sorun", "sikayet", "son", "durum", "rapor", "cozuldu", "acik", "kaldi", "gecmis")
        ):
            top = entities[0]
            return {
                "type": "entity",
                "entity_type": top.get("entity_type"),
                "entity_id": top.get("entity_key"),
                "entity_label": top.get("entity_label"),
                "domain": top.get("domain"),
            }

        dept_triggers = (
            "departman", "birim", "housekeeping", "teknik servis", "cagri merkezi",
            "cağrı merkezi", "restoran", "havuz", "spa", "resepsiyon",
        )
        if any(k in normalized for k in dept_triggers):
            mapping = cls.map_aspect_to_department(query, query)
            if mapping.get("department") and mapping["department"] != "genel":
                return {
                    "type": "department",
                    "domain": mapping["domain"],
                    "domain_label": mapping["domainLabel"],
                    "department": mapping["department"],
                    "department_label": mapping["departmentLabel"],
                }

        domain_triggers = (
            "otel",
        )
        if any(k in normalized for k in domain_triggers):
            detected = cls.detect_domain(query, top_k=1)
            if detected:
                d = detected[0]
                return {
                    "type": "domain",
                    "domain": d["domain"],
                    "domain_label": d.get("domainLabel", d["domain"]),
                }

        return {"type": "general"}

    _hotel_engine = None

    @classmethod
    def get_hotel_engine(cls):
        """HotelOntologyEngine singleton — DOC-002 config-driven ontology."""
        if cls._hotel_engine is None:
            from app.ontology.engine import get_hotel_ontology_engine
            cls._hotel_engine = get_hotel_ontology_engine()
        return cls._hotel_engine

    @classmethod
    def reload_hotel_ontology(cls) -> None:
        """Reload hotel ontology config (entities, aspects, synonyms)."""
        from app.ontology.engine import _get_engine
        _get_engine.cache_clear()
        cls._hotel_engine = None

    @classmethod
    def resolve_hotel_term(cls, text: str, lang: str = "tr") -> dict[str, Any]:
        """Adapter: synonym → entity (HotelOntologyEngine)."""
        ref = cls.get_hotel_engine().resolve_term(text, lang=lang)
        return ref.to_dict()

    @classmethod
    def parse_hotel_review(cls, text: str, lang: str = "tr") -> list[dict[str, Any]]:
        """Adapter: review → segments per DOC-002 Review Parsing Standard."""
        segments = cls.get_hotel_engine().parse_review_segments(text, lang=lang)
        return [s.to_dict() for s in segments]

    @classmethod
    def map_hotel_aspect(cls, text: str, lang: str = "tr") -> dict[str, Any]:
        """Adapter: text → aspect + department via HotelOntologyEngine."""
        mapping = cls.get_hotel_engine().map_aspect(text, lang=lang)
        return mapping.to_dict()

    @classmethod
    def get_hotel_responsible_department(cls, entity_id: str) -> str:
        """Adapter: entity → primary responsible department."""
        return cls.get_hotel_engine().get_responsible_department(entity_id)

    @classmethod
    def map_clause_to_entity(cls, clause: str, domain_id: Optional[str] = None) -> dict[str, Any]:
        """Geriye dönük uyumluluk — cümlecik eşlemesi."""
        domain, domain_label, _ = cls.resolve_domain(clause, hint=domain_id)
        dept_id, dept_label, _ = cls.resolve_department(clause, domain)
        aspect_key, aspect_label, _ = cls.resolve_aspect(clause, domain, dept_id)
        entities = cls.search_entity(clause)
        entity = entities[0] if entities else {
            "entity_type": "generic_unit",
            "entity_key": None,
            "entity_label": "Genel",
        }
        return {
            "domain": domain,
            "domainLabel": domain_label,
            "department": dept_id,
            "departmentLabel": dept_label,
            "aspect": aspect_key,
            "aspectLabel": aspect_label,
            "entity_type": entity.get("entity_type", "generic_unit"),
            "entity_id": entity.get("entity_key"),
            "entity": {
                "type": entity.get("entity_type", "generic_unit"),
                "id": entity.get("entity_key"),
            },
            "legacy_category": dept_label,
        }
