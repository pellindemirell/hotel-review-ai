"""
Aspect-Based Sentiment Analysis (ABSA) — çoklu departman / çoklu boyut / çoklu domain analizi.
Yorumları cümleciklere ayırır; her biri için domain, departman, duygu, aspect ve öncelik üretir.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from app.services.category_rules import _prepare_text, _score_categories, _sorted_category_scores
from app.services.keyword_service import KeywordService
from app.services.ontology_service import OntologyService
from app.services.satisfaction_scale import empty_satisfaction_counts, resolve_satisfaction_label
from app.services.sentiment_service import SentimentService
from app.services.turkish_nlp_utils import (
    ALL_CATEGORIES,
    CAT_CLEANING,
    CAT_FINANCE,
    CAT_FOOD,
    CAT_GROUNDS,
    CAT_OTHER,
    CAT_RECEPTION,
    CAT_SPA,
    CAT_STAFF,
    CAT_TECH,
    COORDINATION_ADJECTIVES,
    MIXED_REVIEW_SPLITTERS,
    detect_strong_sentiment,
    normalize_turkish,
    tokenize_turkish,
)

# (regex_pattern, aspect_label, preferred_department)
ASPECT_RULES: list[tuple[str, str, str]] = [
    # Room SIZE before generic oda→cleaning (frame-sensitive aspect typing)
    (r"\b(odalar?)\b.*\b(kucuk|küçük|dar|minik|genis|geniş)\b", "Genel oda konforu", CAT_OTHER),
    (r"\b(kucuk|küçük|dar)\b.*\b(oda|odalar)\b", "Genel oda konforu", CAT_OTHER),
    (r"\b(ses\s*yalit|ses\s*yalıt|yalitim|yalıtım|yan\s*oda)\b", "Oda Ses / Konfor", CAT_OTHER),
    (r"\b(oda|odalar|odamiz|banyo|havlu|carsaf|yatak|temizlik|hijyen|toz|pis|kirli)\b", "Oda & Banyo Temizliği", CAT_CLEANING),
    (r"\b(yemek|yemekler|kahvalti|bufe|restoran|lezzet|corba|mutfak|tatli|menu|pastane|dondurma|meyve|meyveler|cesitlilik|kaymak|kiyma|kıyma|catal|çatal|bicak|bıçak|pankek)\b", "Yemek & Restoran", CAT_FOOD),
    (r"\b(masa).*(temiz|kirli|sil)", "Masa / Servis Temizliği", CAT_FOOD),
    (r"\b(minibar|mini\s*bar)\b", "Minibar", CAT_FOOD),
    (r"\b(kuyruk|kuyruklar|sira|sıra|bekleme|bekleniyor)\b.*\b(icecek|içecek|bar|limonata)?", "Servis / Kuyruk", CAT_FOOD),
    (r"\b(icecek|içecek).*\b(sira|sıra|kuyruk|dakika|bekleniyor)\b", "Servis / Kuyruk", CAT_FOOD),
    (r"\b(tekila|cesit alkol|çeşit alkol|belli bar|konsept)\b", "İçecek Çeşitliliği", CAT_FOOD),
    (r"\b(sarap|saraplar|raki|bira|icecek|alkol|limonata|soda)\b", "İçecek & Bar", CAT_FOOD),
    (r"\b(masaj|spa|wellness|sauna|hamam|jakuzi)\b", "Spa & Masaj", CAT_SPA),
    (r"\b(etkinlik|etkinlikler|animasyon|konser|aktivite|show|masa\s*tenisi)\b", "Animasyon & Etkinlik", CAT_SPA),
    (r"\b(sezlong|şezlong)\b", "Şezlong / Havuz Alanı", CAT_SPA),
    (r"\b(havuz|plaj|deniz|aquapark|aquaprk|kaydirak|cakil)\b", "Havuz & Aktivite", CAT_SPA),
    (r"\b(wifi|wi-?fi|internet)\b", "WiFi / İnternet", CAT_TECH),
    (r"\b(klima|tv|asansor|elektrik|priz|sicak su|duş|demirler)\b", "Teknik Altyapı", CAT_TECH),
    (r"\b(garson|personel|calisan|kaba|ilgisiz|saygisiz|hostes|turkce|türkçe)\b", "Personel Davranışı", CAT_STAFF),
    (r"\b(resepsiyon|check.?in|check.?out|giris|cikis|lobi|kayit)\b", "Resepsiyon & Giriş", CAT_RECEPTION),
    (r"\b(kuyruk|kuyruklar|sira|sıra|bekleme)\b", "Servis / Kuyruk", CAT_FOOD),
    # Faturalama: para/ekstra tek başına değil (paramız çöp / ekstra karışık tuzak)
    (r"\b(fiyat|fatura|ucret|ücret|depozito|pahali|fahis|odeme|ödeme|overcharge)\b", "Fiyat & Faturalama", CAT_FINANCE),
    (r"\b(paramiz\s*cop|paramız\s*çöp|pişman|pisman|yorgunluk|yorucu)\b", "Genel Deneyim", CAT_OTHER),
    (r"\b(konum|manzara|otel|tatil|genel)\b", "Genel Deneyim", CAT_OTHER),
]

# Bağımsız cümlecik göstergeleri (virgül bölme için)
_CLAUSE_MARKERS = {
    "oda", "odalar", "odamiz", "yemek", "yemekler", "klima", "wifi", "internet",
    "havuz", "masaj", "spa", "garson", "personel", "resepsiyon", "fiyat", "fatura",
    "banyo", "kahvalti", "asansor", "tv", "plaj", "check", "lobi", "temizlik",
    "mutfak", "restoran", "mobil", "uygulama", "musteri", "temsilcisi",
    "etkinlik", "etkinlikler", "calisan", "calisanlar", "minibar", "aquapark",
    "dondurma", "plaj", "demir", "demirler", "hijyen", "cesitlilik",
    "sarap", "raki", "bar", "animasyon", "hamburger", "gozleme", "kahvalti",
    "rakı", "şarap", "bira", "minibar", "aquaprk", "meyve", "meyveler",
    "kavun", "cilek", "kiraz", "kaymak", "kiyma", "kıyma", "catal", "çatal",
    "bicak", "bıçak", "soda", "limonata", "kuyruk", "kuyruklar", "pankek",
    # English clause markers
    "room", "bed", "bathroom", "food", "breakfast", "dinner", "lunch",
    "staff", "waiter", "waitress", "service", "reception", "checkin",
    "pool", "beach", "location", "view", "parking", "clean", "cleaning",
    "towel", "air conditioner", "heating", "shower", "elevator", "wifi",
}

# Demografik / nötr parçalar — şikayet değil
_DEMOGRAPHIC_MARKERS = (
    "kitle", "cocuklu aileler", "çocuklu aileler", "yas üstü", "yaş üstü",
    "belli bir yas", "belli bir yaş", "demografik",
)

# Meta / öneri-only kısa parçalar
_META_CLAUSE_MARKERS = (
    "gün tatil", "gun tatil", "son gununde", "son gününde", "yaziyorum", "yazıyorum",
)
_SUGGESTION_ONLY = (
    "konabilir", "cesitlendirilebilir", "çeşitlendirilebilir", "getirilebilir",
)

# Tek kelime atla — otel anahtar kelimesi yoksa
_SKIP_SINGLE_WORDS = frozenset({
    "haziran", "mayis", "mayıs", "temmuz", "agustos", "ağustos", "kitle",
    "anil", "anil", "ozgul", "özgül",
})


@dataclass
class _TopicContext:
    """Cümlecikler arası aktif konu devralma."""
    minibar: bool = False
    aquapark: bool = False
    food: bool = False
    bar: bool = False
    room: bool = False
    front_office: bool = False


def _should_skip_clause(clause: str) -> bool:
    """Çok kısa, demografik, meta veya anlamsız parçaları atla (pipeline + legacy)."""
    c = clause.strip().lower()
    if len(c) < 4:
        return True
    # Systemic meta/narrative filter (config-driven)
    try:
        from app.services.clause_pipeline import ClausePipeline
        if ClausePipeline.should_drop(clause):
            return True
    except Exception:
        logger.warning("ClausePipeline.should_drop failed", exc_info=True)
    words = c.split()
    if len(words) == 1:
        if words[0] in _SKIP_SINGLE_WORDS:
            return True
        if not (set(words) & _CLAUSE_MARKERS):
            return True
    if len(words) <= 3 and any(m in c for m in _DEMOGRAPHIC_MARKERS):
        if not any(w in c for w in ("kotu", "kötü", "berbat", "sikayet", "şikayet", "olumsuz", "negatif")):
            return True
    # "5 gece 6 gün tatilin son gününde yazıyorum" — meta
    if any(m in c for m in _META_CLAUSE_MARKERS) and not (set(tokenize_turkish(c)) & _CLAUSE_MARKERS):
        return True
    if len(words) <= 4 and any(c.endswith(s) or s in c for s in _SUGGESTION_ONLY):
        # Öneri-only kısa parça; ana şikayet cümlesi yoksa atla
        if not (set(tokenize_turkish(c)) & (_CLAUSE_MARKERS - {"bar"})):
            return True
    # "en azından kutu bira" gibi parantez kalıntısı — bağlam yoksa atla
    if len(words) <= 4 and c.startswith("en azından") and "yetersiz" not in c and "yok" not in c and "bira" not in c:
        return True
    return False


def _apply_pipeline_refine(
    clause: str,
    *,
    sentiment: str,
    score: float,
    mapping: Optional[dict] = None,
    department_label: str = "Genel",
    aspect_label: str = "Genel",
    aspect_key: str = "general",
    category_fallback: str = "",
) -> tuple[str, float, str, str, str, str, int, float, str]:
    """
    Systemic pipeline override: frame → aspect → dept guards → sentiment → severity.
    Returns: sentiment, score, dept_label, aspect_label, aspect_key, priority, priority_score, conf, category

    Only overrides when a *specific* aspect resolved or an explicit modifier fired.
    Weak frames (guest_experience/general) must not wipe ontology/rule categories.
    """
    from app.services.clause_pipeline import ClausePipeline

    decision = ClausePipeline.refine(
        clause,
        sentiment=sentiment,
        score=score,
        mapping=mapping
        or {
            "department": department_label,
            "department_label": department_label,
            "departmentLabel": department_label,
            "aspect_key": aspect_key,
            "aspect_label": aspect_label,
            "aspectLabel": aspect_label,
        },
    )
    if not decision.include:
        return sentiment, score, department_label, aspect_label, aspect_key, "info", 1, 0.5, category_fallback

    _SPECIFIC = frozenset({
        "room_size", "room_cleanliness", "room_noise", "table_cleanliness", "cutlery",
        "food_taste", "meat_quality", "drink_quality", "drink_variety", "service_queue",
        "value_for_money", "guest_experience", "capacity", "staff_behavior", "animation",
        "pool_lounger", "pool_queue", "wifi", "tech_general",
        "front_office", "spa", "housekeeping_service", "minibar_tech", "minibar_supply",
    })
    _HARD_OVERRIDES = frozenset({
        "mediocre_lexicon", "queue_negative", "room_size_negative", "table_dirty",
        "false_friend_lezzet", "anti_finance", "anti_spa", "anti_hk_cleanliness",
        "capacity_negative", "sarcasm_negative", "disappointment_negative",
        "value_waste", "staff_language_negative", "room_noise_negative",
        "drink_variety_negative", "anti_spa_pool_ok",
    })
    hard = bool(set(decision.overrides or []) & _HARD_OVERRIDES)
    specific = decision.aspect_key in _SPECIFIC

    if specific or hard:
        final_dept = decision.department_label if specific else department_label
        final_aspect_label = decision.aspect_label if specific else aspect_label
        final_aspect_key = decision.aspect_key if specific else aspect_key
        final_category = decision.category if specific else category_fallback

        if specific:
            orig_conf = mapping.get("confidence", 0.0) if (mapping and isinstance(mapping, dict)) else 0.0
            if orig_conf >= 0.8 and department_label not in ("Genel", None, ""):
                final_dept = department_label
                final_aspect_label = mapping.get("aspect_label", mapping.get("aspectLabel", aspect_label))
                final_aspect_key = mapping.get("aspect_key", mapping.get("aspect", aspect_key))
                final_category = mapping.get("category", category_fallback)

        # Guard: Helpful staff resolution beats negative queue/capacity overrides
        if sentiment == "Positive" and any(w in clause.lower() for w in ("yardimci ol", "yardımcı ol", "destek ol", "ilgilenerek", "yardimci oluyor", "yardımcı oluyor")):
            return (
                "Positive",
                max(score, 0.78),
                department_label if department_label not in ("Genel", "") else decision.department_label,
                aspect_label if aspect_label not in ("Genel", "") else decision.aspect_label,
                aspect_key if aspect_key not in ("general", "") else decision.aspect_key,
                "INFO",
                1,
                max(0.85, decision.confidence),
                category_fallback,
            )

        return (
            decision.sentiment,
            decision.sentiment_score,
            final_dept,
            final_aspect_label,
            final_aspect_key,
            decision.priority,
            decision.priority_score,
            decision.confidence,
            final_category,
        )


    # Sentiment-only polish (e.g. mediocre already handled above via hard)
    if decision.overrides and decision.sentiment != sentiment:
        return (
            decision.sentiment,
            decision.sentiment_score,
            department_label,
            aspect_label,
            aspect_key,
            decision.priority,
            decision.priority_score,
            max(0.7, decision.confidence),
            category_fallback,
        )
    return sentiment, score, department_label, aspect_label, aspect_key, "", 0, 0.0, category_fallback


def _has_food_context(n: str, toks: set[str]) -> bool:
    """Yiyecek bağlamı — kalabalık→bal gibi tokenizer yanlış pozitiflerini önler."""
    if any(m in n for m in (
        "yemek", "kahvalti", "restoran", "hamburger", "gozleme", "bufe",
        "meyve", "kaymak", "cesitlilik", "çeşitlilik", "dondurma", "pastane",
    )):
        return True
    if "kalabal" in n:
        return False
    return bool(re.search(r"(?<![a-zçğıöşü])bal(?![a-zçğıöşü])", n))


def _update_topic_context(ctx: _TopicContext, clause: str) -> _TopicContext:
    n = normalize_turkish(clause.lower())
    toks = set(tokenize_turkish(n))
    if re.search(r"\bmini\s*bar|\bminibar\b", n):
        ctx.minibar = True
    if any(w in toks or w in n for w in ("aquapark", "aquaprk", "kaydirak", "havuz")):
        ctx.aquapark = True
    if _has_food_context(n, toks):
        ctx.food = True
    drink_words = {"sarap", "raki", "bira", "icki", "kokteyl", "şarap", "rakı"}
    if toks & drink_words or any(w in n for w in ("sarap", "raki", "şarap", "rakı")):
        ctx.bar = True
        ctx.food = True
    if any(w in toks for w in ("oda", "odalar", "banyo", "havlu")) or "bakimli" in n or "bakımlı" in n:
        ctx.room = True
    if any(p in n for p in ("yogun degil", "yoğun değil", "beklemeden")):
        ctx.front_office = True
    return ctx


def _apply_context_to_mapping(clause: str, mapping: dict, ctx: _TopicContext, full_text: str) -> dict:
    """Aktif konu bağlamından departman devral."""
    n = normalize_turkish(clause.lower())
    full_n = normalize_turkish(full_text.lower()) if full_text else n
    dept = mapping.get("departmentLabel", "Genel")

    if dept in ("Genel", "Diğer", "Havuz"):
        if ctx.minibar and any(w in n for w in ("yiyecek", "icecek", "içecek", "bira", "atistirmalik", "atıştırmalık", "yok", "yetersiz")):
            return {**mapping, "department": "food_beverage", "departmentLabel": "Yiyecek & İçecek (F&B)", "aspect": "minibar", "aspectLabel": "Minibar", "aspect_key": "minibar", "method": "context_minibar", "confidence": max(mapping.get("confidence", 0.5), 0.82)}
        if ctx.bar and any(w in n for w in ("sinif", "sınıf", "urun", "ürün", "kalitesiz", "2", "sarap", "şarap", "raki", "rakı")):
            return {**mapping, "department": "food_beverage", "departmentLabel": "Yiyecek & İçecek (F&B)", "aspect": "drink_quality", "aspectLabel": "İçecek Kalitesi", "aspect_key": "drink_quality", "method": "context_bar", "confidence": max(mapping.get("confidence", 0.5), 0.85)}
        if ctx.food and any(w in n for w in ("hamburger", "gozleme", "gözleme", "meyve", "cilek", "çilek", "kiraz", "kavun", "bal", "kaymak", "cesitlilik", "çeşitlilik", "cikmadi", "çıkmadı", "bitiyor", "cesitlendirilebilir", "çeşitlendirilebilir")):
            return {**mapping, "department": "food_beverage", "departmentLabel": "Yiyecek & İçecek (F&B)", "aspect": "food_quality", "aspectLabel": "Yemek Kalitesi", "aspect_key": "food_quality", "method": "context_food", "confidence": max(mapping.get("confidence", 0.5), 0.85)}
        if ctx.aquapark and any(w in n for w in ("aquapark", "aquaprk", "kapali", "kapalı", "yeterli", "sira", "bakim", "bakım", "2", "3")):
            return {**mapping, "department": "leisure", "departmentLabel": "Rekreasyon & Eğlence", "aspect": "pool", "aspectLabel": "Havuz", "aspect_key": "pool_lounger", "method": "context_aquapark", "confidence": max(mapping.get("confidence", 0.5), 0.86)}
        if ctx.room and any(w in n for w in ("bakimli", "bakımlı", "banyo", "oda", "odalar")):
            return {**mapping, "department": "housekeeping", "departmentLabel": "Kat Hizmetleri & Temizlik", "aspect": "room_cleanliness", "aspectLabel": "Oda Temizliği", "aspect_key": "room_cleanliness", "method": "context_room", "confidence": max(mapping.get("confidence", 0.5), 0.85)}
        if ctx.front_office and any(w in n for w in ("yogun", "yoğun", "beklemeden", "erisebiliyorsunuz", "erişebiliyorsunuz")):
            return {**mapping, "department": "front_office", "departmentLabel": "Ön Büro & Misafir İlişkileri", "aspect": "reception_service", "aspectLabel": "Resepsiyon Hizmeti", "aspect_key": "reception_service", "method": "context_front_office", "confidence": max(mapping.get("confidence", 0.5), 0.85)}

    if dept == "Havuz" and ctx.room and any(w in n for w in ("bakimli", "bakımlı", "banyo", "oda")):
        return {**mapping, "department": "housekeeping", "departmentLabel": "Kat Hizmetleri & Temizlik", "aspect": "room_cleanliness", "aspectLabel": "Oda Temizliği", "aspect_key": "room_cleanliness", "method": "context_room_not_pool", "confidence": 0.88}

    if dept == "Havuz" and ctx.food and any(w in set(tokenize_turkish(n)) for w in ("hamburger", "gozleme", "kahvalti")):
        return {**mapping, "department": "food_beverage", "departmentLabel": "Yiyecek & İçecek (F&B)", "aspect": "food_quality", "aspectLabel": "Yemek Kalitesi", "aspect_key": "food_quality", "method": "context_food_not_pool", "confidence": 0.88}

    if dept in ("Genel", "Diğer") and any(w in full_n for w in ("sarap", "şarap", "raki", "rakı")) and any(w in n for w in ("kalitesiz", "sinif", "sınıf", "sarap", "şarap", "raki", "rakı")):
        return {**mapping, "department": "food_beverage", "departmentLabel": "Yiyecek & İçecek (F&B)", "aspect": "drink_quality", "aspectLabel": "İçecek Kalitesi", "aspect_key": "drink_quality", "method": "context_bar_drink", "confidence": 0.86}

    if dept in ("Genel", "Diğer") and any(w in n for w in ("cilek", "çilek", "kiraz", "kavun", "meyve", "cikmadi", "çıkmadı")):
        return {**mapping, "department": "food_beverage", "departmentLabel": "Yiyecek & İçecek (F&B)", "aspect": "food_quality", "aspectLabel": "Yemek Kalitesi", "aspect_key": "food_quality", "method": "context_fruit", "confidence": 0.84}

    if dept in ("Genel", "Diğer") and any(w in n for w in ("aquapark", "aquaprk")):
        return {**mapping, "department": "leisure", "departmentLabel": "Rekreasyon & Eğlence", "aspect": "pool", "aspectLabel": "Havuz", "aspect_key": "pool_lounger", "method": "context_aquaprk", "confidence": 0.88}

    return mapping


def _refine_light_clause_department(clause: str, dept: str, ctx: _TopicContext, full_text: str) -> tuple[str, str]:
    """multidomain=False yolunda Diğer/Genel → gerçek departman."""
    if dept not in (CAT_OTHER, "Genel", "Diğer"):
        # aquaprk yanlışlıkla Teknik'e gitmesin
        n = normalize_turkish(clause.lower())
        if dept == CAT_TECH and any(w in n for w in ("aquapark", "aquaprk", "havuz", "kaydirak")):
            return CAT_SPA, "Havuz & Aktivite"
        return dept, _detect_aspect(clause, dept)

    mapping = {
        "departmentLabel": "Diğer",
        "department": "genel",
        "aspectLabel": "Genel",
        "aspect": "general",
        "aspect_key": "general",
        "confidence": 0.55,
    }
    mapping = _apply_context_to_mapping(clause, mapping, ctx, full_text)
    label = mapping.get("departmentLabel", "Diğer")
    aspect = mapping.get("aspectLabel", "Genel")
    canonical_to_dept = {
        "Yiyecek & İçecek (F&B)": CAT_FOOD,
        "Rekreasyon & Eğlence": CAT_SPA,
        "Kat Hizmetleri & Temizlik": CAT_CLEANING,
        "Oda Hizmetleri & Housekeeping": CAT_CLEANING,
        "Ön Büro & Misafir İlişkileri": CAT_RECEPTION,
        "Personel Davranışı": CAT_STAFF,
        "Teknik Servis & IT": CAT_TECH,
        "Çevre, Güvenlik & Ulaşım": CAT_GROUNDS,
        "Otel Atmosferi & Misafir Profili": CAT_ATMOSPHERE,
    }
    if label in canonical_to_dept:
        return canonical_to_dept[label], aspect
    # Doğrudan anahtar kelime
    n = normalize_turkish(clause.lower())
    if any(w in n for w in ("meyve", "sarap", "şarap", "raki", "rakı", "cesitlilik", "çeşitlilik", "kahvalti", "kahvaltı", "dondurma", "minibar", "mini bar")):
        return CAT_FOOD, _detect_aspect(clause, CAT_FOOD)
    if any(w in n for w in ("aquapark", "aquaprk", "havuz", "plaj", "kaydirak")):
        return CAT_SPA, "Havuz & Aktivite"
    return dept, aspect


def _refine_clause_sentiment(clause: str, full_text: str, ctx: _TopicContext, sentiment: str, score: float) -> tuple[str, float]:
    """Bağlam penceresi ile cümlecik duygu düzeltmesi."""
    from app.services.turkish_nlp_utils import detect_strong_sentiment, normalize_turkish

    n = normalize_turkish(clause.lower())
    full_n = normalize_turkish(full_text.lower()) if full_text else n

    # Helpful staff & positive service indicators (Must run BEFORE detect_strong_sentiment to prevent 'yoğun' penalty false negatives)
    if any(w in n for w in ("yardimci ol", "yardımcı ol", "destek ol", "ilgilenerek", "bir kazanim", "bir kazanım", "nazik ve ilgili", "cok ilgilenerek", "çok ilgilenerek", "yardimci oluyor", "yardımcı oluyor", "sorun gormedim", "sorun görmedim", "sorun yasamadik", "sorun yaşamadık", "sorun olmadi", "sorun olmadı", "problem yok", "sorun yok", "sikayet yok", "şikayet yok", "kusursuzdu", "sorunsuzdu")):
        return "Positive", max(score if score > 0 else 0.78, 0.78)

    if any(w in n for w in ("hizmetinizde", "oldukca fazla", "oldukça fazla", "saatleri genis", "saatleri geniş", "beklentileri karsiliyor", "beklentileri karşılıyor")):
        return "Positive", max(score if score > 0 else 0.65, 0.65)

    ruled_sent, ruled_score = detect_strong_sentiment(clause)
    if ruled_sent != "Neutral" or abs(ruled_score) >= 0.35:
        return ruled_sent, ruled_score

    if ctx.bar or any(w in full_n for w in ("kalitesiz", "sarap", "şarap", "raki", "rakı")):
        if any(w in n for w in ("raki", "rakı", "sarap", "şarap", "kalitesiz", "sinif", "sınıf")):
            return "Negative", min(score, -0.40)

    # Kıyma / et kalitesi düşük
    if any(w in n for w in ("kiyma", "kıyma")) and any(w in n for w in ("dusuk", "düşük", "kotu", "kötü", "kalitesiz", "berbat")):
        return "Negative", min(score if score < 0 else -0.55, -0.55)

    # "soda için geçerli" — önceki bar/limonata şikayetini miras al
    if re.search(r"(?<![a-zçğıöşü])soda(?![a-zçğıöşü])", n) and any(w in n for w in ("gecerli", "geçerli", "yok", "yetersiz")):
        return "Negative", min(score if score < 0 else -0.45, -0.45)
    if "aynı durum" in n or "ayni durum" in n:
        if any(w in full_n for w in ("limonata", "soda", "barda", "icecek", "içecek", "kuyruk")):
            return "Negative", min(score if score < 0 else -0.40, -0.40)

    # Çatal bıçak yok / masa temizlenmedi
    if any(w in n for w in ("catal", "çatal", "bicak", "bıçak")) and any(w in n for w in ("bulamad", "yok", "eksik", "kirli")):
        return "Negative", min(score if score < 0 else -0.50, -0.50)
    if "temizletemed" in n:
        return "Negative", min(score if score < 0 else -0.45, -0.45)

    # Helpful staff & positive service indicators
    if any(w in n for w in ("yardimci ol", "yardımcı ol", "destek ol", "ilgilenerek", "bir kazanim", "bir kazanım", "nazik ve ilgili", "cok ilgilenerek", "çok ilgilenerek", "yardimci oluyor", "yardımcı oluyor")):
        return "Positive", max(score if score > 0 else 0.78, 0.78)

    if any(w in n for w in ("hizmetinizde", "oldukca fazla", "oldukça fazla", "saatleri genis", "saatleri geniş", "beklentileri karsiliyor", "beklentileri karşılıyor")):
        return "Positive", max(score if score > 0 else 0.65, 0.65)

    if "ozellikle banyo" in n or "özellikle banyo" in n:
        if any(w in full_n for w in ("getirilebilir", "bakimli", "bakımlı")):
            return "Negative", -0.35

    return sentiment, score

# Fiil / öneri son ekleri — "ve" bölmesinde sıfat koordinasyonundan ayırır
_VERB_SUFFIXES = (
    "di", "du", "ti", "tu", "mis", "miş", "yor", "iyor", "uyor",
    "abilir", "ebilir", "malı", "meli", "mali", "meli", "dir", "dur",
    "acak", "ecek", "iydi", "erdi", "ar", "ir", "ur",
)


@dataclass
class AbsaAspect:
    clause: str
    aspect: str
    department: str
    sentiment: str
    sentiment_score: float
    confidence: float
    priority: str
    priority_score: int
    satisfaction_level: str
    keywords: list[str] = field(default_factory=list)
    suggestion: str = ""
    rating: Optional[int] = None
    domain: str = "turizm"
    subdomain: str = "otel"
    aspect_label: str = ""
    aspect_key: str = ""
    department_label: str = ""
    domain_label: str = "Turizm"
    action_required: bool = False


@dataclass
class AbsaResult:
    aspects: list[AbsaAspect]
    overall_sentiment: str
    overall_score: float
    is_multi_aspect: bool
    department_summary: dict[str, dict[str, int]]
    domain_summary: dict[str, dict[str, int]] = field(default_factory=dict)
    detected_domains: list[dict] = field(default_factory=list)


@dataclass
class MultiDomainAbsaAspect:
    clause: str
    domain: str
    domain_label: str
    department: str
    department_label: str
    aspect: str
    aspect_label: str
    entity_type: str
    entity_id: Optional[str]
    sentiment: str
    sentiment_score: float
    confidence: float
    priority: str
    priority_score: int
    satisfaction_level: str
    action_required: bool
    keywords: list[str] = field(default_factory=list)
    suggestion: str = ""
    rating: Optional[int] = None

    @property
    def entity(self) -> dict[str, Optional[str]]:
        return {"type": self.entity_type, "id": self.entity_id}


@dataclass
class MultiDomainAbsaResult:
    aspects: list[MultiDomainAbsaAspect]
    overall_sentiment: str
    overall_score: float
    is_multi_aspect: bool
    domain_summary: dict[str, dict]
    department_summary: dict[str, dict]


def _looks_independent(clause: str) -> bool:
    cleaned = clause.rstrip(".,!?;:")
    toks = set(tokenize_turkish(cleaned))
    if len(cleaned.split()) >= 4:
        return True
    return bool(toks & _CLAUSE_MARKERS)


def _preprocess_for_split(text: str) -> str:
    """Cümle sınırları ve parantez — virgül/ve bölmesinden önce normalize et."""
    # Newlines and Emojis -> sentence boundaries
    text = re.sub(r"[\r\n]+", ". ", text)
    text = re.sub(r"[\U0001F300-\U0001F9FF\U00002600-\U000026FF\U00002700-\U000027BF]+", ". ", text)

    text = re.sub(r"\.\(", ". ", text)
    text = re.sub(r"\)\.", ". ", text)
    text = re.sub(r"\)(?=\S)", ") ", text)
    # TripAdvisor / yapışık cümle: "kaldık.Deniz" → "kaldık. Deniz" (harfler arası nokta)
    text = re.sub(r"([.!?])([A-Za-zÇçĞğİıÖöŞşÜü])", r"\1 \2", text)

    # 1. Tarih Aralıkları (ör: 29.06-05.07) ve Tam Tarihler (ör: 12.05.2023, 30.06)
    text = re.sub(r"\b(\d{1,2})[\.\/](\d{1,2})\s*[-–]\s*(\d{1,2})[\.\/](\d{1,2})\b", r"\1§\2-\3§\4", text)
    text = re.sub(r"\b(\d{1,2})[\.\/](\d{1,2})[\.\/](\d{2,4})\b", r"\1§\2§\3", text)
    text = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1§\2", text)

    # 2. Saati & Saat Aralıkları (ör: 18.00-24.00, 14.30)
    text = re.sub(
        r"\b(\d{1,2})\.(\d{2})(\s*[-–]\s*)(\d{1,2})\.(\d{2})\b",
        r"\1§\2\3\4§\5",
        text,
    )

    # 3. Binlik Ayracı (ör: 1.500 TL, 10.000)
    text = re.sub(r"\b(\d{1,3})\.(\d{3})\b", r"\1§\2", text)

    # 4. Ondalık Sayılar Virgüllü (ör: 2,5 saat, 3,5 yıldız) -> Virgül bölmesinde ayrılmamalı!
    text = re.sub(r"\b(\d+),(\d+)\b", r"\1€\2", text)

    # 5. Sıra Sayıları / Belirli İfadeler (ör: 2. hafta, 1. gün, 2. kat)
    text = re.sub(r"(\d+)\.\s*(hafta|haftası|sinif|sınıf|kat|gun|gün)", r"\1§ \2", text, flags=re.IGNORECASE)

    # Pipe ve numaralı madde ayırıcıları
    text = re.sub(r"\s*\|\s*", ". ", text)
    text = re.sub(r"\s+(?=\d+[\.\)\-]\s)", ". ", text)

    text = re.sub(r"\.(?=\S)", ". ", text)
    text = re.sub(r"[!?](?=\S)", lambda m: m.group(0) + " ", text)
    text = re.sub(r";", ". ", text)

    # Oda boyutu + yemek yan yana: "odalar çok küçük yemeklerin lezzeti..."
    text = re.sub(
        r"(odalar?\s+(?:çok\s+|cok\s+)?(?:küçük|kucuk|dar|minik))"
        r"(\s+)(yemek(?:ler(?:in)?)?|lezzet|kahvaltı|kahvalti|kiyma|kıyma)",
        r"\1. \3",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _restore_ordinals(text: str) -> str:
    return text.replace("§", ".").replace("€", ",")


_VERB_SUFFIXES = (
    "dı", "di", "du", "dü", "tı", "ti", "tu", "tü",
    "yordu", "yordu", "acak", "ecek", "miş", "mış", "muş", "müş",
    "malı", "meli", "dık", "dik", "tık", "tik",
    "ıyor", "iyor", "uyor", "üyor", "eriz", "arız",
)


def _has_verb_token(words: list[str]) -> bool:
    for w in words:
        if any(w.endswith(s) for s in _VERB_SUFFIXES):
            return True
    return False


def _is_ve_coordination(left: str, right: str) -> bool:
    """'güzel ve yeterli' / 'kavun, çilek ve kiraz' / 'tatlılar ve waffle çok güzeldi' — cümle bölünmemeli."""
    from app.services.turkish_nlp_utils import POSITIVE_WORDS, NEGATIVE_WORDS
    left = left.rstrip(".,;: ")
    right = right.lstrip(".,;: ")
    if "guzel ve yeterli" in f"{left} ve {right}" or "güzel ve yeterli" in f"{left} ve {right}":
        return True
    if "," in left:
        return True
    left_words = left.split()
    right_words = right.split()
    if right_words and right_words[0] in COORDINATION_ADJECTIVES:
        return True
    if left_words and left_words[-1] in COORDINATION_ADJECTIVES and len(right_words) <= 2:
        return True
    if not _has_verb_token(left_words) and not any(w in left_words for w in POSITIVE_WORDS | NEGATIVE_WORDS):
        return True
    if len(left_words) <= 4 and len(right_words) <= 4:
        if not _has_verb_token(left_words + right_words):
            return True
    return False


def split_clauses_absa(text: str) -> list[str]:
    """
    Karışık yorumları çoklu cümleciklere ayırır.
    ama/fakat/ancak + virgül ile ayrılmış bağımsız ifadeler.
    """
    cleaned = _preprocess_for_split(normalize_turkish(text))
    if not cleaned:
        return []

    def _split_one(clause: str) -> list[str]:
        clause = clause.strip()
        if not clause:
            return []

        for punct_re in (r"\.\s+", r"!\s+", r"\?\s+"):
            if re.search(punct_re, clause):
                parts = [p.strip() for p in re.split(punct_re, clause) if p.strip()]
                if len(parts) >= 2:
                    out: list[str] = []
                    for p in parts:
                        out.extend(_split_one(p))
                    return out

        for sep in MIXED_REVIEW_SPLITTERS + [
            " yine de ", " bununla birlikte ", " öte yandan ", " bir de ",
            " ayrıca ", " üstelik ", " ote yandan ", " bunun disinda ",
            " onun dışında ", " onun disinda ",
        ]:
            if sep in clause:
                parts = [p.strip() for p in re.split(re.escape(sep), clause, flags=re.IGNORECASE) if p.strip()]
                if len(parts) >= 2:
                    out: list[str] = []
                    for p in parts:
                        out.extend(_split_one(p))
                    return out

        if "," in clause or ";" in clause:
            parts = re.split(r"[,;]", clause)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 2 and all(_looks_independent(p) for p in parts):
                out = []
                for p in parts:
                    out.extend(_split_one(p))
                return out

        if " ve " in clause:
            raw_parts = [p.strip().rstrip(".,!?;:") for p in clause.split(" ve ") if p.strip()]
            if len(raw_parts) >= 2 and all(len(p.split()) >= 2 for p in raw_parts):
                coord = any(_is_ve_coordination(raw_parts[i], raw_parts[i + 1]) for i in range(len(raw_parts) - 1))
                if not coord:
                    out = []
                    for p in raw_parts:
                        out.extend(_split_one(p))
                    return out

        if " and " in clause and " ve " not in clause:
            raw_parts = [p.strip().rstrip(".,!?;:") for p in clause.split(" and ") if p.strip()]
            if len(raw_parts) >= 2 and all(len(p.split()) >= 3 for p in raw_parts):
                out = []
                for p in raw_parts:
                    out.extend(_split_one(p))
                return out

        return [clause]

    clauses = _split_one(cleaned)

    # Tek parça ama çoklu aspect iması varsa noktalama yoksa virgül benzeri " fakat " zaten yukarıda
    if len(clauses) == 1 and len(cleaned.split()) > 12:
        for sep in (" ancak ", " lakin ", " yine de ", " and "):
            if sep in cleaned:
                parts = [p.strip() for p in cleaned.split(sep) if p.strip()]
                if len(parts) >= 2:
                    out: list[str] = []
                    for p in parts:
                        out.extend(_split_one(p))
                    return out

    seen: set[str] = set()
    unique: list[str] = []
    for c in clauses:
        restored = _restore_ordinals(c)
        key = restored.lower()
        if key not in seen and len(restored) >= 4 and not _should_skip_clause(restored):
            seen.add(key)
            unique.append(restored)
    return unique


def _detect_aspect(clause: str, department: str) -> str:
    asc = clause.replace("ş", "s").replace("ı", "i").replace("ö", "o").replace("ü", "u").replace("ç", "c").replace("ğ", "g")
    for pattern, label, dept in ASPECT_RULES:
        if re.search(pattern, asc) or re.search(pattern, clause):
            return label
    dept_defaults = {
        CAT_CLEANING: "Oda & Temizlik",
        CAT_FOOD: "Yemek & İçecek",
        CAT_SPA: "Spa & Wellness",
        CAT_TECH: "Teknik Servis",
        CAT_STAFF: "Personel",
        CAT_RECEPTION: "Resepsiyon",
        CAT_FINANCE: "Finans",
        CAT_OTHER: "Genel",
    }
    return dept_defaults.get(department, "Genel")


def _classify_clause(clause: str) -> tuple[str, float]:
    cleaned, tokens = _prepare_text(clause)
    scores = _score_categories(cleaned, tokens)
    ranked = _sorted_category_scores(scores)
    return ranked[0][0], ranked[0][1]


def _confidence_from_score(rule_score: float) -> float:
    if rule_score >= 6.0:
        return 0.92
    if rule_score >= 4.0:
        return 0.88
    if rule_score >= 2.5:
        return 0.82
    if rule_score >= 1.5:
        return 0.75
    if rule_score > 0:
        return 0.65
    return 0.55


def _priority(sentiment: str, score: float, clause: str = "") -> tuple[str, int]:
    """Öncelik — kısa/hafif şikayetlerde KRİTİK şişmesini engelle."""
    n = normalize_turkish(clause.lower()) if clause else ""
    word_count = len(clause.split()) if clause else 99
    mild = any(p in n for p in (
        "arttirilmali", "arttırılmalı", "olabilir", "getirilebilir",
        "cesitlendirilebilir", "çeşitlendirilebilir", "konabilir",
        "daha iyi", "yetersiz", "cesitlilik", "çeşitlilik",
        "ortalamaydi", "ortalamaydı", "ortalama",
    ))
    # Değer pişmanlığı / genel deneyim — finans kritik değil
    value_regret = any(p in n for p in (
        "paramiz cop", "paramız çöp", "para çöp", "pismanlik", "pişmanlık", "pişman",
        "yorucu", "yorgunluk", "karisik", "karışık",
    ))
    short_frag = word_count <= 5
    if sentiment == "Negative":
        if value_regret and not any(w in n for w in ("fatura", "ucret", "ücret", "depozito", "overcharge")):
            return "high", 4
        # KRİTİK: yalnızca güçlü, yeterince uzun şikayetler
        if score <= -0.75 and not mild and not short_frag:
            return "critical", 5
        if score <= -0.35:
            return "high", 4
        if mild or short_frag:
            return "medium", 3
        return "medium", 3
    if sentiment == "Positive":
        if score >= 0.65:
            return "info", 1
        return "low", 2
    return "medium", 2


def _overall_from_aspects(aspects: list[AbsaAspect]) -> tuple[str, float]:
    if not aspects:
        return "Neutral", 0.0
    neg = [a for a in aspects if a.sentiment == "Negative"]
    pos = [a for a in aspects if a.sentiment == "Positive"]
    critical_negs = [a for a in neg if a.priority in ("critical", "high")]
    if len(critical_negs) >= 3 and len(pos) >= 2:
        avg = sum(a.sentiment_score for a in aspects) / len(aspects)
        return "Neutral", round(min(0.2, avg), 2)
    if len(critical_negs) >= 3:
        sc = min(a.sentiment_score for a in critical_negs)
        return "Negative", round(min(-0.2, sc), 2)
    if neg and not pos:
        sc = min(a.sentiment_score for a in neg)
        return "Negative", round(sc, 2)
    if pos and not neg:
        sc = max(a.sentiment_score for a in pos)
        return "Positive", round(sc, 2)
    if neg and pos:
        avg = sum(a.sentiment_score for a in aspects) / len(aspects)
        neg_w = sum(a.priority_score for a in neg)
        pos_w = sum(a.priority_score for a in pos)
        # Tek bir düşük öncelikli negatif, birden çok pozitifi ezmesin
        if len(neg) == 1 and len(pos) >= len(neg):
            return "Positive" if avg > 0 else "Neutral", round(max(0.0, avg), 2)
        if any(a.priority in ("critical", "high") for a in neg):
            if neg_w >= pos_w:
                return "Negative", round(min(-0.2, avg), 2)
        if neg_w > pos_w * 1.2:
            return "Negative", round(min(-0.15, avg), 2)
        if pos_w > neg_w * 1.2:
            return "Positive", round(max(0.15, avg), 2)
        return "Neutral", round(avg, 2)
    avg = sum(a.sentiment_score for a in aspects) / len(aspects)
    label = "Positive" if avg > 0.1 else "Negative" if avg < -0.1 else "Neutral"
    return label, round(avg, 2)


def _department_summary(aspects: list[AbsaAspect]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for a in aspects:
        dept_key = a.department_label or a.department
        block = summary.setdefault(
            dept_key,
            {"total": 0, "negative": 0, "positive": 0, "neutral": 0, "satisfaction": empty_satisfaction_counts()},
        )
        block["total"] += 1
        key = a.sentiment.lower()
        if key in block:
            block[key] += 1
        sat = block["satisfaction"]
        if a.satisfaction_level in sat:
            sat[a.satisfaction_level] += 1
    return summary


def _domain_summary(aspects: list[AbsaAspect]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for a in aspects:
        dom_key = a.domain_label or a.domain
        block = summary.setdefault(
            dom_key,
            {"total": 0, "negative": 0, "positive": 0, "neutral": 0, "satisfaction": empty_satisfaction_counts()},
        )
        block["total"] += 1
        key = a.sentiment.lower()
        if key in block:
            block[key] += 1
        sat = block["satisfaction"]
        if a.satisfaction_level in sat:
            sat[a.satisfaction_level] += 1
    return summary


def _refine_generic_aspects(full_text: str, aspects: list) -> list:
    """Genel/Diğer bucket'ını tam metin bağlamıyla yeniden eşle."""
    if not aspects:
        return aspects
    from app.services.clause_pipeline import _fold
    from app.services.ontology_service import OntologyService

    full_norm = normalize_turkish(full_text.lower())
    refined: list = []
    for a in aspects:
        dept = a.department_label or a.department
        if dept not in ("Genel", "Diğer", "general"):
            refined.append(a)
            continue
        # Pipeline already resolved sarcasm/value/noise — do not remap to pool hygiene
        ak = getattr(a, "aspect_key", getattr(a, "aspect", ""))
        ak = (ak or "").lower()
        cl = (a.clause or "").lower()
        folded = _fold(cl)
        if ak in ("guest_experience", "value_for_money", "room_noise", "staff_behavior", "wifi"):
            if any(
                w in folded
                for w in (
                    "metre", "yuru", "kosmak", "isterseniz", "carcur", "diye tuttuk",
                    "yalitim", "turkce", "wifi", "baglan",
                )
            ):
                refined.append(a)
                continue
        mapping = OntologyService.map_aspect_to_department(full_text, a.clause)
        new_dept = mapping.get("departmentLabel", dept)
        new_aspect = (mapping.get("aspectLabel") or "").lower()
        # Distance sarcasm must never become "Havuz Temizliği"
        if "temiz" in new_aspect and any(w in folded for w in ("metre", "yuru", "kos", "isterseniz")):
            refined.append(a)
            continue
        if (dept in ("Genel", "Diğer", "Restaurant") or new_dept in ("Genel", "Diğer")) and any(
            w in full_norm for w in ("aquapark", "aquaprk", "havuz", "plaj", "kaydirak")
        ):
            if any(w in a.clause.lower() for w in ("yeterli", "kapali", "kapalı", "sira", "bekle", "2", "3", "aquaprk", "aquapark", "bakim", "bakım")):
                if not any(w in a.clause.lower() for w in ("yemek", "kahvalti", "kahvaltı", "restoran", "bufe", "büfe", "bar", "icecek", "içecek", "tekila", "sarap", "şarap", "raki", "rakı")):
                    new_dept = "Havuz"
                    mapping["aspectLabel"] = "Aquapark"
                    mapping["department"] = "havuz"
                    mapping["departmentLabel"] = "Havuz"
                    mapping["aspect_key"] = "aquapark"
        if new_dept != dept:
            if hasattr(a, "aspect_key"):
                a = AbsaAspect(
                    clause=a.clause,
                    aspect=mapping.get("aspectLabel", a.aspect),
                    department=new_dept,
                    sentiment=a.sentiment,
                    sentiment_score=a.sentiment_score,
                    confidence=max(a.confidence, mapping.get("confidence", 0.7)),
                    priority=a.priority,
                    priority_score=a.priority_score,
                    satisfaction_level=a.satisfaction_level,
                    keywords=a.keywords,
                    suggestion=a.suggestion,
                    rating=a.rating,
                    domain=a.domain,
                    subdomain=a.subdomain,
                    aspect_label=mapping.get("aspectLabel", a.aspect_label),
                    aspect_key=mapping.get("aspect_key", a.aspect_key),
                    department_label=new_dept,
                    domain_label=a.domain_label,
                    action_required=a.action_required,
                )
            else:
                a = MultiDomainAbsaAspect(
                    clause=a.clause,
                    domain=mapping.get("domain", a.domain),
                    domain_label=mapping.get("domainLabel", a.domain_label),
                    department=mapping.get("department", a.department),
                    department_label=new_dept,
                    aspect=mapping.get("aspect_key", a.aspect),
                    aspect_label=mapping.get("aspectLabel", a.aspect_label),
                    entity_type=a.entity_type,
                    entity_id=a.entity_id,
                    sentiment=a.sentiment,
                    sentiment_score=a.sentiment_score,
                    confidence=max(a.confidence, mapping.get("confidence", 0.7)),
                    priority=a.priority,
                    priority_score=a.priority_score,
                    satisfaction_level=a.satisfaction_level,
                    action_required=a.action_required,
                    keywords=a.keywords,
                    suggestion=a.suggestion,
                    rating=a.rating,
                )
        refined.append(a)
    return refined


def _action_required(sentiment: str, priority: str) -> bool:
    return sentiment == "Negative" and priority in ("critical", "high", "medium")


def _consolidate_adjacent_aspects(aspects):
    if not aspects:
        return []
    consolidated = []
    for a in aspects:
        if not consolidated:
            consolidated.append(a)
            continue
        prev = consolidated[-1]
        prev_dept = getattr(prev, "department_label", getattr(prev, "department", ""))
        a_dept = getattr(a, "department_label", getattr(a, "department", ""))
        
        if prev_dept == a_dept and prev.sentiment == a.sentiment:
            prev_ak = getattr(prev, "aspect_key", getattr(prev, "aspect", ""))
            a_ak = getattr(a, "aspect_key", getattr(a, "aspect", ""))
            
            if prev_ak == a_ak or {prev_ak, a_ak} <= {"drink_variety", "drink_quality", "hours_cues", "service_queue", "general", "guest_experience"}:
                combined_clause = f"{prev.clause}. {a.clause}".strip()
                new_score = min(prev.sentiment_score, a.sentiment_score) if prev.sentiment == "Negative" else max(prev.sentiment_score, a.sentiment_score)
                
                best_aspect_lbl = prev.aspect_label
                if prev.aspect_label in ("Genel", "") and a.aspect_label not in ("Genel", ""):
                    best_aspect_lbl = a.aspect_label
                elif "Saatleri" in a.aspect_label:
                    best_aspect_lbl = a.aspect_label

                merged = MultiDomainAbsaAspect(
                    clause=combined_clause,
                    domain=getattr(prev, "domain", "turizm"),
                    domain_label=getattr(prev, "domain_label", "Turizm"),
                    department=getattr(prev, "department", "genel"),
                    department_label=getattr(prev, "department_label", "Genel"),
                    aspect=getattr(prev, "aspect", "general") if getattr(prev, "aspect", "general") != "general" else getattr(a, "aspect", "general"),
                    aspect_label=best_aspect_lbl,
                    entity_type=getattr(prev, "entity_type", "generic_unit"),
                    entity_id=getattr(prev, "entity_id", None),
                    sentiment=prev.sentiment,
                    sentiment_score=new_score,
                    confidence=max(prev.confidence, a.confidence),
                    priority=prev.priority if prev.priority_score >= a.priority_score else a.priority,
                    priority_score=max(prev.priority_score, a.priority_score),
                    satisfaction_level=resolve_satisfaction_label(new_score, prev.sentiment),
                    action_required=prev.action_required or a.action_required,
                    keywords=list(dict.fromkeys(prev.keywords + a.keywords))[:6],
                    suggestion=prev.suggestion,
                    rating=prev.rating or a.rating,
                )
                consolidated[-1] = merged
                continue
        consolidated.append(a)
    return consolidated


class AbsaService:
    """Aspect-Based Sentiment Analysis servisi — çoklu domain destekli."""

    @classmethod
    def analyze(cls, text: str, rating: Optional[int] = None, multidomain: bool = True) -> AbsaResult:
        clauses = split_clauses_absa(text)
        if not clauses:
            clauses = [normalize_turkish(text)] if text.strip() else []

        detected_domains = OntologyService.detect_domain(text) if multidomain else []

        aspects: list[AbsaAspect] = []
        ctx = _TopicContext()
        for clause in clauses:
            if _should_skip_clause(clause):
                continue
            ctx = _update_topic_context(ctx, clause)

            # Hotel UI yolu: kural tabanlı duygu (ML/lexicon tekrarını atla)
            if multidomain:
                sentiment, score = SentimentService.analyze_sentiment(clause, rating=None)
                if sentiment == "Neutral":
                    sentiment, score = detect_strong_sentiment(clause)
            else:
                sentiment, score = detect_strong_sentiment(clause)
            sentiment, score = _refine_clause_sentiment(clause, text, ctx, sentiment, score)

            if multidomain:
                mapping = OntologyService.map_aspect_to_department(text, clause)
                mapping = _apply_context_to_mapping(clause, mapping, ctx, text)
                dept = mapping.get("departmentLabel", mapping.get("department", "Genel"))
                aspect = mapping.get("aspectLabel", mapping.get("aspect", "Genel"))
                aspect_key = mapping.get("aspect_key", mapping.get("aspect", "general"))
                conf = mapping.get("confidence", 0.75)
                domain = mapping.get("domain", "turizm")
                subdomain = mapping.get("subdomain", "otel")
                domain_label = mapping.get("domainLabel", domain)
                department_label = mapping.get("departmentLabel", dept)
            else:
                dept, rule_score = _classify_clause(clause)
                dept, aspect = _refine_light_clause_department(clause, dept, ctx, text)
                aspect_key = aspect
                conf = _confidence_from_score(rule_score)
                domain, subdomain = "turizm", "otel"
                domain_label, department_label = "Turizm", dept
                mapping = {
                    "department": dept,
                    "departmentLabel": department_label,
                    "aspect_key": aspect_key,
                    "aspectLabel": aspect,
                }

            # Systemic clause pipeline: frames / mediocre / anti-patterns / severity
            (
                sentiment, score, department_label, aspect, aspect_key,
                pipe_priority, pipe_ps, pipe_conf, pipe_cat,
            ) = _apply_pipeline_refine(
                clause,
                sentiment=sentiment,
                score=score,
                mapping=mapping if isinstance(mapping, dict) else None,
                department_label=department_label,
                aspect_label=aspect,
                aspect_key=str(aspect_key),
                category_fallback=dept if not multidomain else department_label,
            )
            if pipe_conf:
                conf = max(conf, pipe_conf)
            if not multidomain and pipe_cat:
                # Light path: department field is CAT_* label
                dept = pipe_cat
                department_label = pipe_cat
            elif multidomain:
                dept = department_label

            if pipe_priority:
                priority, priority_score = pipe_priority, pipe_ps
            else:
                priority, priority_score = _priority(sentiment, score, clause)
            keywords = KeywordService.extract_keywords(clause, max_keywords=3) if multidomain else []
            suggestion = f"{department_label if multidomain else dept}: {sentiment}"
            aspect_rating = rating if len(clauses) == 1 and rating is not None else None
            satisfaction = resolve_satisfaction_label(score, sentiment, aspect_rating)

            aspects.append(AbsaAspect(
                clause=clause,
                aspect=aspect,
                department=dept if multidomain else dept,
                sentiment=sentiment,
                sentiment_score=score,
                confidence=conf,
                priority=priority,
                priority_score=priority_score,
                satisfaction_level=satisfaction,
                keywords=keywords,
                suggestion=suggestion,
                rating=aspect_rating,
                domain=domain,
                subdomain=subdomain,
                aspect_label=aspect,
                aspect_key=aspect_key,
                department_label=department_label,
                domain_label=domain_label,
                action_required=_action_required(sentiment, priority),
            ))

        # UI hotel yolu: ontology tarama (map_aspect ~1s/cümle) atlanır
        if multidomain:
            aspects = _refine_generic_aspects(text, aspects)
        aspects.sort(key=lambda a: (-a.priority_score, a.sentiment == "Negative", -abs(a.sentiment_score)))

        overall_sent, overall_sc = _overall_from_aspects(aspects)
        if multidomain:
            if rating is not None and len(aspects) == 1:
                overall_sent, overall_sc = SentimentService.analyze_sentiment(text, rating)
            elif rating is not None and len(aspects) > 1:
                rating_sent, rating_sc = SentimentService.analyze_sentiment(text, rating)
                if rating_sent == "Negative" and overall_sent == "Positive":
                    overall_sent, overall_sc = rating_sent, rating_sc
        elif rating is not None and aspects:
            # Hotel UI: rating ile tek seferlik hizala, clause başına ML yok
            if len(aspects) == 1 or (overall_sent == "Positive" and rating <= 2):
                from app.services.turkish_nlp_utils import analyze_sentiment_with_rating
                overall_sent, overall_sc = analyze_sentiment_with_rating(text, rating)

        return AbsaResult(
            aspects=aspects,
            overall_sentiment=overall_sent,
            overall_score=overall_sc,
            is_multi_aspect=len(aspects) >= 2,
            department_summary=_department_summary(aspects),
            domain_summary=_domain_summary(aspects),
            detected_domains=detected_domains,
        )

    @classmethod
    def analyze_multidomain(
        cls,
        text: str,
        rating: Optional[int] = None,
        domain_hint: Optional[str] = None,
    ) -> MultiDomainAbsaResult:
        """Ontology-driven çok alanlı ABSA."""
        clauses = split_clauses_absa(text)
        if not clauses:
            clauses = [normalize_turkish(text)] if text.strip() else []

        aspects: list[MultiDomainAbsaAspect] = []
        ctx = _TopicContext()
        for clause in clauses:
            if _should_skip_clause(clause):
                continue
            ctx = _update_topic_context(ctx, clause)

            sentiment, score = SentimentService.analyze_sentiment(clause, rating=None)
            if sentiment == "Neutral":
                sentiment, score = detect_strong_sentiment(clause)
            sentiment, score = _refine_clause_sentiment(clause, text, ctx, sentiment, score)

            mapping = OntologyService.map_aspect_to_department(text, clause)
            mapping = _apply_context_to_mapping(clause, mapping, ctx, text)
            domain_id = mapping.get("domain", "turizm")
            domain_label = mapping.get("domainLabel", "Turizm")
            dept_id = mapping.get("department", "genel")
            dept_label = mapping.get("departmentLabel", "Genel")
            aspect_key = mapping.get("aspect_key", "general")
            aspect_label = mapping.get("aspectLabel", "Genel")
            conf = mapping.get("confidence", 0.75)

            if domain_hint:
                domain_id, domain_label, _ = OntologyService.resolve_domain(clause, hint=domain_hint)

            (
                sentiment, score, dept_label, aspect_label, aspect_key,
                pipe_priority, pipe_ps, pipe_conf, _pipe_cat,
            ) = _apply_pipeline_refine(
                clause,
                sentiment=sentiment,
                score=score,
                mapping=mapping,
                department_label=dept_label,
                aspect_label=aspect_label,
                aspect_key=str(aspect_key),
            )
            if pipe_conf:
                conf = max(conf, pipe_conf)
            if pipe_priority:
                priority, priority_score = pipe_priority, pipe_ps
            else:
                priority, priority_score = _priority(sentiment, score, clause)
            if dept_label in ("Genel", "genel"):
                try:
                    from app.services.transformer_absa import get_transformer_absa_engine
                    t_spans = get_transformer_absa_engine().predict_spans(clause)
                    if t_spans:
                        best_t = t_spans[0]
                        if best_t.confidence > conf:
                            dept_label = best_t.department_label
                            dept_id = best_t.department
                            aspect_label = best_t.aspect_label
                            aspect_key = best_t.aspect
                            if best_t.sentiment != "Neutral":
                                sentiment = best_t.sentiment
                            conf = max(conf, best_t.confidence)
                except Exception:
                    logger.warning("Transformer ABSA engine predict_spans failed", exc_info=True)

            # Keep dept_id aligned with refined label; canonicalize the label
            if pipe_priority or aspect_key not in ("general", ""):
                dept_id = mapping.get("department", dept_id)
                _label_to_canonical = {
                    "Restaurant": "Yiyecek & İçecek (F&B)", "Bar": "Yiyecek & İçecek (F&B)",
                    "Housekeeping": "Kat Hizmetleri & Temizlik", "Odalar": "Kat Hizmetleri & Temizlik",
                    "Personel": "Personel Davranışı",
                    "Animasyon": "Rekreasyon & Eğlence", "Animasyon & Etkinlik": "Rekreasyon & Eğlence",
                    "Havuz": "Rekreasyon & Eğlence",
                    "Front Office": "Ön Büro & Misafir İlişkileri",
                    "Teknik": "Teknik Servis & IT",
                }
                dept_label = _label_to_canonical.get(dept_label, dept_label)
                # Prefer pipeline department keys from decision via label map
                _label_to_key = {
                    "Yiyecek & İçecek (F&B)": "food_beverage",
                    "Kat Hizmetleri & Temizlik": "housekeeping", "Oda Hizmetleri & Housekeeping": "housekeeping",
                    "Personel Davranışı": "staff",
                    "Rekreasyon & Eğlence": "leisure",
                    "Ön Büro & Misafir İlişkileri": "front_office",
                    "Teknik Servis & IT": "engineering",
                    "Çevre, Güvenlik & Ulaşım": "grounds",
                    "Otel Atmosferi & Misafir Profili": "atmosphere",
                    "Genel": "genel",
                }
                dept_id = _label_to_key.get(dept_label, dept_id)

            keywords = KeywordService.extract_keywords(clause, max_keywords=4)
            from app.services.rag_service import RagService
            suggestion = RagService.generate_suggestion(
                category=dept_label,
                text=clause,
                keywords=keywords,
                sentiment=sentiment,
                is_mixed=False,
                secondary_category=None,
                is_manipulation=False,
            )
            aspect_rating = rating if len(clauses) == 1 and rating is not None else None
            satisfaction = resolve_satisfaction_label(score, sentiment, aspect_rating)
            action_required = _action_required(sentiment, priority)

            entities = OntologyService.search_entity(clause)
            entity = entities[0] if entities else None

            aspects.append(MultiDomainAbsaAspect(
                clause=clause,
                domain=domain_id,
                domain_label=domain_label,
                department=dept_id,
                department_label=dept_label,
                aspect=aspect_key,
                aspect_label=aspect_label,
                entity_type=entity.get("entity_type", "generic_unit") if entity else "generic_unit",
                entity_id=entity.get("entity_key") if entity else None,
                sentiment=sentiment,
                sentiment_score=score,
                confidence=conf,
                priority=priority,
                priority_score=priority_score,
                satisfaction_level=satisfaction,
                action_required=action_required,
                keywords=keywords,
                suggestion=suggestion,
                rating=aspect_rating,
            ))

        aspects = _consolidate_adjacent_aspects(aspects)
        aspects.sort(key=lambda a: (-a.priority_score, a.sentiment == "Negative", -abs(a.sentiment_score)))

        # Genel bucket yeniden eşleme
        for i, a in enumerate(aspects):
            if a.department_label not in ("Genel", "Diğer"):
                continue
            mapping = OntologyService.map_aspect_to_department(text, a.clause)
            nd = mapping.get("departmentLabel", a.department_label)
            if nd not in ("Genel", "Diğer"):
                aspects[i] = MultiDomainAbsaAspect(
                    clause=a.clause, domain=mapping.get("domain", a.domain),
                    domain_label=mapping.get("domainLabel", a.domain_label),
                    department=mapping.get("department", a.department),
                    department_label=nd,
                    aspect=mapping.get("aspect_key", a.aspect),
                    aspect_label=mapping.get("aspectLabel", a.aspect_label),
                    entity_type=a.entity_type, entity_id=a.entity_id,
                    sentiment=a.sentiment, sentiment_score=a.sentiment_score,
                    confidence=max(a.confidence, mapping.get("confidence", 0.7)),
                    priority=a.priority, priority_score=a.priority_score,
                    satisfaction_level=a.satisfaction_level, action_required=a.action_required,
                    keywords=a.keywords, suggestion=a.suggestion, rating=a.rating,
                )

        legacy_aspects = [
            AbsaAspect(
                clause=a.clause,
                aspect=a.aspect_label,
                department=a.department_label,
                sentiment=a.sentiment,
                sentiment_score=a.sentiment_score,
                confidence=a.confidence,
                priority=a.priority,
                priority_score=a.priority_score,
                satisfaction_level=a.satisfaction_level,
                keywords=a.keywords,
                suggestion=a.suggestion,
                rating=a.rating,
                domain=a.domain,
                domain_label=a.domain_label,
            )
            for a in aspects
        ]
        aspects = _refine_generic_aspects(text, aspects)
        aspects.sort(key=lambda a: (-a.priority_score, a.sentiment == "Negative", -abs(a.sentiment_score)))

        overall_sent, overall_sc = _overall_from_aspects(aspects)
        if rating is not None and len(aspects) == 1:
            overall_sent, overall_sc = SentimentService.analyze_sentiment(text, rating)
        elif rating is not None and len(aspects) > 1 and rating <= 2:
            rating_sent, _ = SentimentService.analyze_sentiment(text, rating)
            if rating_sent == "Negative" and overall_sent == "Positive":
                overall_sent = rating_sent

        return MultiDomainAbsaResult(
            aspects=aspects,
            overall_sentiment=overall_sent,
            overall_score=overall_sc,
            is_multi_aspect=len(aspects) >= 2,
            domain_summary=_multidomain_domain_summary(aspects),
            department_summary=_multidomain_department_summary(aspects),
        )

    @classmethod
    def to_dict(cls, result: AbsaResult) -> dict:
        return {
            "aspects": [
                {
                    "clause": a.clause,
                    "aspect": a.aspect,
                    "aspectLabel": a.aspect_label or a.aspect,
                    "aspectKey": a.aspect_key,
                    "department": a.department_label or a.department,
                    "departmentKey": a.department,
                    "domain": a.domain,
                    "domainLabel": a.domain_label,
                    "subdomain": a.subdomain,
                    "sentiment": a.sentiment,
                    "sentimentScore": a.sentiment_score,
                    "confidence": a.confidence,
                    "priority": a.priority,
                    "priorityScore": a.priority_score,
                    "satisfactionLevel": a.satisfaction_level,
                    "actionRequired": a.action_required,
                    "keywords": a.keywords,
                    "suggestion": a.suggestion,
                }
                for a in result.aspects
            ],
            "overallSentiment": result.overall_sentiment,
            "overallScore": result.overall_score,
            "isMultiAspect": result.is_multi_aspect,
            "aspectCount": len(result.aspects),
            "departmentSummary": result.department_summary,
            "domainSummary": result.domain_summary,
            "detectedDomains": result.detected_domains,
        }

    @classmethod
    def to_multidomain_dict(cls, result: MultiDomainAbsaResult) -> dict:
        return {
            "aspects": [
                {
                    "clause": a.clause,
                    "domain": a.domain,
                    "domainLabel": a.domain_label,
                    "subdomain": a.domain,
                    "department": a.department,
                    "departmentLabel": a.department_label,
                    "aspect": a.aspect,
                    "aspectLabel": a.aspect_label,
                    "entity": a.entity,
                    "entityType": a.entity_type,
                    "entityId": a.entity_id,
                    "sentiment": a.sentiment,
                    "sentimentScore": a.sentiment_score,
                    "confidence": a.confidence,
                    "priority": a.priority,
                    "priorityScore": a.priority_score,
                    "satisfactionLevel": a.satisfaction_level,
                    "actionRequired": a.action_required,
                    "keywords": a.keywords,
                    "suggestion": a.suggestion,
                }
                for a in result.aspects
            ],
            "overallSentiment": result.overall_sentiment,
            "overallScore": result.overall_score,
            "isMultiAspect": result.is_multi_aspect,
            "aspectCount": len(result.aspects),
            "domainSummary": result.domain_summary,
            "departmentSummary": result.department_summary,
        }


def _multidomain_domain_summary(aspects: list[MultiDomainAbsaAspect]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for a in aspects:
        block = summary.setdefault(
            a.domain,
            {
                "label": a.domain_label,
                "total": 0,
                "negative": 0,
                "positive": 0,
                "neutral": 0,
                "satisfaction": empty_satisfaction_counts(),
            },
        )
        block["total"] += 1
        key = a.sentiment.lower()
        if key in block:
            block[key] += 1
        sat = block["satisfaction"]
        if a.satisfaction_level in sat:
            sat[a.satisfaction_level] += 1
    return summary


def _multidomain_department_summary(aspects: list[MultiDomainAbsaAspect]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for a in aspects:
        dept_key = f"{a.domain}:{a.department}"
        block = summary.setdefault(
            dept_key,
            {
                "domain": a.domain,
                "domainLabel": a.domain_label,
                "department": a.department,
                "departmentLabel": a.department_label,
                "total": 0,
                "negative": 0,
                "positive": 0,
                "neutral": 0,
                "satisfaction": empty_satisfaction_counts(),
            },
        )
        block["total"] += 1
        key = a.sentiment.lower()
        if key in block:
            block[key] += 1
        sat = block["satisfaction"]
        if a.satisfaction_level in sat:
            sat[a.satisfaction_level] += 1
    return summary
