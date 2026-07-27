"""
Deterministik otel departmanı kategori sınıflandırması.
Aynı girdi → her zaman aynı çıktı. Rastgelelik yok.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

from app.services.turkish_nlp_utils import (
    ALL_CATEGORIES,
    CAT_CLEANING,
    CAT_FINANCE,
    CAT_FOOD,
    CAT_OTHER,
    CAT_RECEPTION,
    CAT_SPA,
    CAT_STAFF,
    CAT_TECH,
    DEPT_HINTS,
    GENERAL_COMPLAINT,
    GENERAL_PRAISE,
    extract_ngrams,
    normalize_turkish,
    tokenize_turkish,
)

# Skor eşikleri
RULE_SCORE_THRESHOLD = 3.0
RULE_MARGIN = 1.5
MODEL_CONFIDENCE_MIN = 0.85
RULE_CONFIDENCE_WIN = 0.78       # Kurallar bu güvenin üstünde modeli geçersiz kılar
CONFIDENCE_MIN = 0.50            # Anlamlı metin asla altına düşmez
CONFIDENCE_FALLBACK_MIN = 0.55   # Boş/zayıf fallback tabanı

# Olumsuz bağlam: bu kalıplar varsa "temiz" vb. pozitif kelime sayılmaz
NEGATED_CLEANING = ("temizlenmedi", "temizlenmemiş", "temizlik yok", "yapılmamış", "yapılmadı")
NEGATED_TECH = ("çalışmıyor", "bozuk", "arızalı", "gelmiyor", "yok")

# (phrase, weight) — yüksek ağırlık = yüksek öncelik
CATEGORY_PHRASES: dict[str, list[tuple[str, float]]] = {
    CAT_CLEANING: [
        ("oda kirli", 6.0), ("oda temiz", 5.0), ("oda tertemiz", 5.5), ("oda temizliği", 5.0),
        ("banyo kirli", 5.5), ("banyo pis", 5.0), ("banyo temiz", 4.5),
        ("havlu lekeli", 5.0), ("çarşaf lekeli", 5.0), ("yatak kirli", 5.0),
        ("temizlik yapılmamış", 6.0), ("temizlik harika", 4.5), ("oda dağınık", 4.5),
        ("housekeeping geç", 5.0), ("havlu değiştirilmedi", 5.5), ("toz her yerde", 4.0),
        ("hijyen berbat", 5.0), ("oda kokuyordu", 4.5), ("pis banyo", 5.0),
        ("boş tabaklar", 5.5), ("bos tabaklar", 5.5), ("koridorlara bırakılan", 5.5),
        ("pike istedik", 5.5), ("pike getirilmedi", 5.5),
        # room_size / table service — NOT cleaning phrases (see clause_pipeline frames)
    ],
    CAT_FOOD: [
        ("yemek soğuk", 6.0), ("yemek lezzetli", 5.5), ("yemek berbat", 5.5), ("yemek harika", 5.0),
        ("yemek harika", 5.5),
        ("kahvaltı berbat", 5.5), ("kahvaltı harika", 5.0), ("kahvaltı mükemmel", 5.0),
        ("açık büfe", 4.5), ("açık büfe lezzetsiz", 6.0), ("restoran yemekleri", 4.5),
        ("domates çorbası", 5.5), ("kabak dolması", 5.5), ("kabak dolmasına", 5.5),
        ("çorba soğuk", 5.5), ("çorba bayat", 5.0), ("lezzetsiz yemek", 6.0),
        ("mutfak lezzetli", 5.0), ("akşam yemeği", 4.0), ("tatlılar enfes", 4.5),
        ("menü zengin", 4.0), ("yemekler harika", 5.0),
        ("güzel ve yeterli", 5.5), ("guzel ve yeterli", 5.5),
        ("hamburger güzel", 5.0), ("gözleme güzel", 5.0), ("çeşitlilik yetersiz", 5.5),
        ("çeşitlilik arttırılmalı", 5.5), ("cesitlilik arttirilmali", 5.5),
        ("çeşitlilik yetersiz", 5.5), ("cesitlilik yetersiz", 5.5),
        ("bardakta dondurma", 5.0), ("paket dondurma", 5.0), ("dondurma pastanede", 5.5),
        ("pastanede dondurma", 5.5), ("dondurma", 6.0), ("dondurma servis", 6.5),
        ("kumpir", 6.0), ("çıtır tavuk", 6.0), ("citir tavuk", 6.0), ("pizza", 5.5),
        ("gözleme", 5.5), ("gozleme", 5.5),
        ("uzun kuyruklar", 4.5), ("uzun sira", 4.5), ("kuyruk bekledik", 5.0),
        ("inanilmaz kuyruklar", 5.5), ("pankek sirasinda", 5.5),
        ("icecek icin sira", 6.5), ("içecek için sıra", 6.5),
        ("dakika sıra bekleniyor", 7.0), ("dakika sira bekleniyor", 7.0),
        ("sıra beklemeden", 6.0), ("sira beklemeden", 6.0),
        ("7/24 bar", 6.5), ("tekila yok", 6.5), ("belli barlarda", 6.0),
        ("fried chicken", 5.0), ("koefte yapmayi", 5.0), ("köfte yapmayı", 5.0),
        ("mini barı çok yetersiz", 6.5), ("mini bari cok yetersiz", 6.5),
        ("minibar yetersiz", 6.0), ("bal kaymak bitiyor", 6.0), ("bal kaymak", 5.0),
        ("meyveler hiç çıkmadı", 6.0), ("meyveler hic cikmadi", 6.0),
        ("rakı ve şaraplar", 5.5), ("raki ve saraplar", 5.5),
        ("şaraplar bence kalitesiz", 6.0), ("saraplar bence kalitesiz", 6.0),
        ("kıyma kalitesi", 6.5), ("kiyma kalitesi", 6.5), ("kıyma kalitesi çok düşük", 7.0),
        ("çatal bıçak", 6.5), ("catal bicak", 6.5), ("çatal bıçak bulamadık", 7.0),
        ("masalarda çatal", 6.5), ("masalarda catal", 6.5),
        ("limonata yok", 6.0), ("soda için geçerli", 6.0), ("soda icin gecerli", 6.0),
        ("soda yok", 5.5), ("barda limonata", 5.5), ("italyan restoran", 5.5),
        ("a la carte", 5.0), ("alacarte", 5.0),
        # F&B table service (not housekeeping)
        ("masa temizletemedik", 6.5), ("temizletemediğimiz", 6.5), ("temizletemedigimiz", 6.5),
        ("oturacak bir masa", 5.5), ("masa kirli", 6.0),
        ("yemeklerin lezzeti ortalamaydı", 5.0), ("lezzeti ortalamaydı", 5.0),
        ("lezzeti ortalama", 5.0),
    ],
    CAT_OTHER: [
        ("herşey çok güzel", 5.0), ("herşey mükemmel", 5.0), ("mükemmel tatil", 5.0),
        ("harika tatil", 5.0), ("asla gelmeyin", 5.0), ("pişman olduk", 4.5),
        ("berbat bir otel", 4.5), ("hayal kırıklığı", 4.0),
        ("paramız çöp", 6.5), ("paramiz cop", 6.5), ("para çöp oldu", 6.5),
        ("pişmanlıktan öteye", 6.0), ("pismanliktan oteye", 6.0),
        ("herşey dahil", 3.5), ("hersey dahil", 3.5),
        ("ekstra karışık", 6.0), ("ekstra karisik", 6.0),
        ("karışık ve yorucu", 6.5), ("karisik ve yorucu", 6.5),
        ("yorucuydu", 5.0), ("sadece yorgunluk", 5.5),
        # Room SIZE / comfort — not housekeeping cleanliness
        ("odalar çok küçük", 6.5), ("odalar cok kucuk", 6.5), ("oda çok küçük", 6.5),
        ("oda küçük", 5.5), ("odalar küçük", 5.5), ("odalar dar", 5.5),
        ("genel oda konforu", 4.0),
    ],
    CAT_STAFF: [
        ("garson kaba", 6.5), ("garson ilgisiz", 6.0), ("garson yavaş", 5.5),
        ("personel kaba", 6.0), ("personel ilgisiz", 6.0), ("personel yavaş", 5.5),
        ("çalışan kaba", 5.5), ("çalışanlar kibar", 6.5), ("calisanlar kibar", 6.5),
        ("çalışanlar kibardı", 6.5), ("calisanlar kibardi", 6.5),
        ("saygısız konuştu", 5.5), ("kaba davrandı", 5.5),
        ("ilgisiz personel", 5.5), ("garson güler yüzlü", 5.0), ("personel kibar", 5.0),
        ("yardımsever personel", 4.5), ("kötü muamele", 5.5), ("bağırdı", 5.0),
        ("resepsiyonist kaba", 6.0), ("resepsiyonist saygısız", 6.0),
        ("kibar insanlar", 5.5), ("ne kadar kibar", 5.5),
        ("şef ilgisiz", 5.5), ("sef ilgisiz", 5.5), ("restorant şefi", 5.5),
    ],
    CAT_RECEPTION: [
        ("check-in yavaş", 6.0), ("check-in çok yavaş", 6.5), ("check-in", 4.0),
        ("check-out", 4.0), ("giriş işlemi", 5.0), ("çıkış işlemi", 5.0),
        ("resepsiyon bekletti", 6.0), ("resepsiyon yavaş", 5.5), ("girişte bekledik", 5.5),
        ("saatlerce bekledik", 4.5), ("lobide giriş", 4.5), ("rezervasyon hatası", 5.0),
        ("resepsiyon hızlı", 4.5), ("giriş kolaydı", 4.0), ("bellboy", 4.0),
        ("beklemeden erişebiliyorsunuz", 6.0), ("beklemeden erisebiliyorsunuz", 6.0),
        ("yoğun değildi", 5.0), ("yogun degildi", 5.0),
    ],
    CAT_TECH: [
        ("klima bozuk", 6.5), ("klima çalışmıyor", 6.5), ("klima arızalı", 6.0),
        ("klima soğuk", 6.5), ("klima çok soğuk", 7.0), ("klima soğuktu", 7.0), ("çok soğuktu", 4.0),
        ("wifi çalışmıyor", 6.0), ("wifi yavaş", 5.5), ("internet yok", 5.5),
        ("tv bozuk", 5.5), ("kumanda çalışmıyor", 5.5), ("sıcak su gelmiyor", 6.0),
        ("duş alamadık", 5.0), ("asansör bozuk", 6.0), ("priz bozuk", 5.5),
        ("lamba yanmıyor", 5.0), ("minibar bozuk", 5.0), ("klima arızası", 5.5),
        ("demirler yıpranmış", 6.5), ("demirler yipranmis", 6.5),
        ("demir bakım", 6.0),
        ("sular kesildi", 6.5), ("su kesildi", 6.5), ("su kesintisi", 6.0),
    ],
    CAT_SPA: [
        ("havuz kirli", 6.0), ("havuz temiz", 5.5), ("havuz kirliydi", 6.0),
        ("masaj harika", 5.5), ("spa harika", 5.0), ("spa mükemmel", 5.0),
        ("şezlong yok", 4.0), ("plaj kalabalık", 4.5), ("plaj çakıl", 5.5),
        ("deniz kirli", 5.0), ("etkinlikler güzel", 6.0), ("etkinlik güzel", 6.0),
        ("animasyon harika", 5.0), ("animasyon eğlenceli", 5.0), ("wellness mükemmel", 5.0),
        ("sauna harika", 5.0), ("jakuzi", 4.0), ("su sporları", 4.0),
        ("aquapark kapalı", 6.0), ("aquapark yeterli", 5.5), ("kaydırak", 5.0),
        ("aquapark bakim", 6.5), ("aquapark bakima", 6.5), ("bakima ihtiyaci", 5.5),
        ("aquaprk", 5.5), ("aqua park", 5.5), ("3 aquaprk", 6.0),
        # Soft animation signals — must not outrank F&B queue/bar on multi-complaint reviews
        ("masa tenisi", 3.0), ("aktivite kaldırılmış", 3.5),
    ],
    CAT_FINANCE: [
        ("fatura hatası", 6.5), ("fatura yanlış", 6.0), ("fiyat pahalı", 5.5),
        ("çok pahalı", 5.0), ("ekstra ücret", 6.0), ("gizli ücret", 6.0),
        ("para tuzağı", 5.5), ("fahiş fiyat", 5.5), ("minibar ücreti", 5.0),
        ("depozito iade", 5.5), ("depozito iade edilmedi", 6.0), ("overcharge", 5.0),
        ("ödeme sorunu", 5.0), ("fiyat performans", 4.0),
        ("yanlış fatura", 6.0), ("ekstra ucret", 6.0),
    ],
}

try:
    from app.services.lexicon_loader import merge_category_phrases
    CATEGORY_PHRASES = merge_category_phrases(CATEGORY_PHRASES)
except Exception:
    logger.warning("Failed to merge category phrases from lexicon", exc_info=True)

# Tek kelime ağırlıkları
CATEGORY_KEYWORD_WEIGHTS: dict[str, dict[str, float]] = {
    CAT_CLEANING: {
        "oda": 2.0, "banyo": 2.5, "havlu": 2.5, "çarşaf": 2.5, "yatak": 2.0, "temizlik": 3.0,
        "temiz": 2.0, "kirli": 2.5, "lekeli": 2.5, "pis": 2.5, "hijyen": 2.5, "toz": 2.0,
        "duş": 1.5, "tuvalet": 2.0, "housekeeping": 3.0, "dağınık": 2.0,
    },
    CAT_FOOD: {
        "yemek": 3.0, "lezzet": 2.5, "lezzetli": 2.5, "lezzetsiz": 3.0, "kahvaltı": 3.0,
        "büfe": 2.5, "restoran": 2.5, "mutfak": 2.5, "çorba": 3.0, "domates": 2.5,
        "kabak": 3.0, "dolma": 3.0, "tatlı": 2.0, "menü": 2.0, "içecek": 2.0, "aşçı": 2.5,
        "minibar": 2.5, "sarap": 3.0, "şarap": 3.0, "saraplar": 3.0, "şaraplar": 3.0,
        "raki": 3.0, "rakı": 3.0, "dondurma": 2.5, "cesitlilik": 2.5, "çeşitlilik": 2.5,
        "hamburger": 2.5, "gözleme": 2.5, "yiyecek": 2.5,
        "chicken": 2.5, "kofte": 2.5, "köfte": 2.5, "pike": 2.5,
        "meyve": 3.0, "meyveler": 3.0, "kavun": 2.5, "cilek": 2.5, "çilek": 2.5,
        "kiraz": 2.5, "kaymak": 2.5, "bira": 2.0, "atistirmalik": 2.0, "atıştırmalık": 2.0,
        "kiyma": 3.5, "kıyma": 3.5, "catal": 3.0, "çatal": 3.0, "bicak": 3.0, "bıçak": 3.0,
        "soda": 3.0, "limonata": 3.0, "pankek": 3.0, "kuyruk": 2.5, "kuyruklar": 2.5,
    },
    CAT_STAFF: {
        "garson": 3.5, "personel": 2.5, "çalışan": 2.5, "çalışanlar": 3.0, "calisanlar": 3.0,
        "kaba": 2.5, "ilgisiz": 2.5, "kibar": 3.5, "kibardı": 3.5, "kibardi": 3.5,
        "saygısız": 2.5, "yavaş": 1.5, "hostes": 2.5, "resepsiyonist": 2.0,
    },
    CAT_RECEPTION: {
        "resepsiyon": 2.5, "giriş": 2.5, "çıkış": 2.5, "check": 2.0, "checkin": 2.5,
        "checkout": 2.5, "lobi": 2.0, "rezervasyon": 2.5, "bellboy": 2.5, "kayıt": 2.0,
    },
    CAT_TECH: {
        "klima": 3.5, "wifi": 3.0, "internet": 2.5, "tv": 2.5, "televizyon": 2.5,
        "kumanda": 2.5, "bozuk": 2.0, "arıza": 2.5, "arızalı": 2.5, "çalışmıyor": 2.5,
        "priz": 2.5, "asansör": 3.0, "minibar": 2.0, "sıcak": 1.5,
        "demir": 2.5, "demirler": 2.5, "yipranmis": 2.5, "yıpranmış": 2.5, "bakim": 2.0,
    },
    CAT_SPA: {
        "havuz": 3.5, "spa": 3.0, "masaj": 3.0, "plaj": 2.5, "deniz": 2.0, "şezlong": 2.5,
        "animasyon": 3.0, "wellness": 3.0, "sauna": 2.5, "jakuzi": 2.5, "fitness": 2.0,
        "etkinlik": 3.0, "etkinlikler": 3.0, "aquapark": 3.5, "aquaprk": 3.5, "kaydirak": 2.5,
        "tenis": 2.5, "cakil": 2.0, "çakıl": 2.0,
    },
    CAT_FINANCE: {
        # "para"/"ekstra" kasıtlı yok — paramız çöp / ekstra karışık yanlış pozitif
        "fiyat": 2.5, "fatura": 3.0, "ücret": 2.5, "ucret": 2.5, "pahalı": 2.5, "fahiş": 2.5,
        "depozito": 2.5, "iade": 2.0, "ödeme": 2.5, "odeme": 2.5, "overcharge": 3.0,
    },
}

# Alt-dize tuzakları — yalnızca tam token / kelime sınırı ile eşleşir
_STRICT_TOKEN_KEYWORDS = frozenset({
    "para", "ekstra", "masa", "bar", "oda", "et", "bal", "su",
})


@dataclass(frozen=True)
class RuleClassificationResult:
    category: str
    confidence: float
    method: str
    rule_score: float
    scores: dict[str, float]
    secondary_category: Optional[str] = None
    is_mixed: bool = False


def _prepare_text(text: str) -> tuple[str, list[str]]:
    cleaned = normalize_turkish(text)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    tokens = tokenize_turkish(cleaned)
    return cleaned, tokens


def _has_negated_cleaning(cleaned: str) -> bool:
    return any(n in cleaned for n in NEGATED_CLEANING)


def _keyword_match(word: str, tokens: list[str], cleaned: str) -> bool:
    if word in tokens:
        return True
    if word in cleaned.split():
        return True
    # Kısa/çok anlamlı kelimelerde alt-dize eşleşmesi yasak (para→paramız, masa→masalarda)
    if word in _STRICT_TOKEN_KEYWORDS or len(word) <= 3:
        return bool(re.search(rf"(?<![a-zçğıöşü]){re.escape(word)}(?![a-zçğıöşü])", cleaned))
    return word in cleaned and len(word) >= 4


def _is_value_regret_context(cleaned: str) -> bool:
    """Para/pişman = değer pişmanlığı (Genel), fatura/ücret değil."""
    markers = (
        "paramiz cop", "paramız çöp", "para cop", "para çöp", "paralarimiz cop",
        "paralarimiz çöp", "paralarımız çöp", "para yazik", "para yazık",
        "pismanliktan", "pişmanlıktan", "pişman olduk", "pişman oldum", "pişman",
        "paranın karşılığı", "paranin karsiligi", "paraya değmez", "paraya degmez",
        "carcur", "çarçur", "parasini carcur", "parasını çarçur",
    )
    return any(m in cleaned for m in markers)


def _is_all_inclusive_experience(cleaned: str) -> bool:
    """Her şey dahil kaos/yorucu deneyim — finans değil."""
    has_ai = any(p in cleaned for p in ("hersey dahil", "herşey dahil", "all inclusive", "her sey dahil"))
    has_exp = any(p in cleaned for p in (
        "karisik", "karışık", "yorucu", "yorucuydu", "yorgunluk", "kalabalik", "kalabalık",
        "kuyruk", "sira", "sıra",
    ))
    # "ekstra karışık/yorucu" — ekstra ücret değil
    if any(p in cleaned for p in ("ekstra karisik", "ekstra karışık", "ekstra yorucu")):
        return True
    return has_ai and has_exp


def _is_beverage_soda(cleaned: str, tokens: list[str]) -> bool:
    """İçecek soda — temizlik sodası / soda tabancası değil."""
    if "soda tabanc" in cleaned or "temizlik soda" in cleaned or "soda ile temiz" in cleaned:
        return False
    if "soda" not in tokens and "soda" not in cleaned.split() and not re.search(
        r"(?<![a-zçğıöşü])soda(?![a-zçğıöşü])", cleaned
    ):
        return False
    # Bar/içecek bağlamı veya yalnız "soda" şikayeti → içecek
    drink_ctx = (
        "limonata", "icecek", "içecek", "bar", "barda", "icki", "alkol", "bira",
        "gecerli", "geçerli", "yok", "bulamiyor", "bulamıyor",
    )
    if any(w in tokens or w in cleaned for w in drink_ctx):
        return True
    # Temizlik bağlamı yoksa varsayılan içecek
    if not any(w in cleaned for w in ("temizlik", "temizle", "deterjan", "tabanca", "lek")):
        return True
    return False


def _score_categories(cleaned: str, tokens: list[str]) -> dict[str, float]:
    scores: dict[str, float] = {cat: 0.0 for cat in ALL_CATEGORIES}
    negated_clean = _has_negated_cleaning(cleaned)

    # 1. İfade kalıpları (en yüksek öncelik) + n-gram pencereleri
    ngrams = set(extract_ngrams(cleaned, 2, 3))
    for category, phrases in CATEGORY_PHRASES.items():
        target_cat = category
        if target_cat not in scores:
            continue
        for phrase, weight in phrases:
            if phrase in cleaned:
                scores[target_cat] += weight
            elif phrase in ngrams:
                scores[target_cat] += weight * 0.85

    # 2. Anahtar kelime ağırlıkları
    for category, kw_weights in CATEGORY_KEYWORD_WEIGHTS.items():
        target_cat = category
        if target_cat not in scores:
            continue
        for kw, weight in kw_weights.items():
            if not _keyword_match(kw, tokens, cleaned):
                continue
            # Olumsuz bağlam: temiz → temizlenmedi
            if target_cat == CAT_CLEANING and kw in ("temiz", "temizlik") and negated_clean:
                continue
            if target_cat == CAT_CLEANING and kw == "temiz" and "temizlenmedi" in cleaned:
                continue
            scores[target_cat] += weight


    # 3. Deterministik ayrıştırma kuralları (sabit bonus/ceza)
    _apply_disambiguation(cleaned, tokens, scores)
    return scores


def _apply_disambiguation(cleaned: str, tokens: list[str], scores: dict[str, float]) -> None:
    """Departman çakışmalarını deterministik çöz."""
    # kibar/kibardı → Personel; bar alt-dizesi tuzaklarını engelle
    if any(w in tokens or w in cleaned for w in ("kibar", "kibardı", "kibardi", "kibarca")):
        scores[CAT_STAFF] += 6.0
        scores[CAT_FOOD] -= 3.0

    # Değer pişmanlığı / para çöp → Genel Deneyim (Muhasebe DEĞİL)
    if _is_value_regret_context(cleaned):
        scores[CAT_OTHER] += 7.0
        scores[CAT_FINANCE] -= 8.0

    # Her şey dahil kaos deneyimi → Genel (finans/ekstra ücret değil)
    if _is_all_inclusive_experience(cleaned):
        scores[CAT_OTHER] += 6.5
        scores[CAT_FINANCE] -= 8.0

    # Çatal/bıçak / kıyma → F&B; masa tenisi → Animasyon/aktivite (bütün yorum Spa yapma)
    if any(w in tokens or w in cleaned for w in ("catal", "çatal", "bicak", "bıçak", "kiyma", "kıyma")):
        scores[CAT_FOOD] += 6.0
        scores[CAT_SPA] -= 5.0
        scores[CAT_OTHER] -= 2.0
    if "masa tenisi" in cleaned:
        scores[CAT_SPA] += 2.0  # lokal animasyon sinyali; global Spa şişirme
    elif any(w in cleaned for w in ("masalarda", "masa bul", "masa kirli", "masa temiz", "oturacak bir masa")):
        scores[CAT_FOOD] += 5.0
        scores[CAT_SPA] -= 4.0
        scores[CAT_CLEANING] -= 4.0  # restaurant table ≠ room HK
        if "temizletemed" in cleaned or "kirli" in cleaned:
            scores[CAT_FOOD] += 3.0

    # Servis kuyruğu + içecek / bar saatleri → F&B dominant (Spa klor/havuz değil)
    queue_drink = any(w in cleaned for w in ("sira", "sıra", "kuyruk", "bekleniyor", "dakika")) and any(
        w in cleaned for w in ("icecek", "içecek", "bar", "tekila", "alkol", "limonata")
    )
    if queue_drink or any(w in cleaned for w in ("15 20 dakika", "30-45 dakika", "30 45 dakika", "sira bekleniyor", "sıra bekleniyor")):
        scores[CAT_FOOD] += 7.0
        scores[CAT_SPA] -= 5.0
        scores[CAT_RECEPTION] -= 2.0
    if any(w in cleaned for w in ("tekila", "7/24 bar", "belli barlarda", "cesit alkoller", "çeşit alkoller")):
        scores[CAT_FOOD] += 5.0
        scores[CAT_SPA] -= 3.0

    # Dominant F&B ops (kuyruk/içecek/bar) → primary F&B; soft spa/havuz/aktivite şişirme engelle
    fb_ops = sum(
        1 for w in (
            "sira", "sıra", "kuyruk", "icecek", "içecek", "bar", "tekila", "alkol",
            "dakika", "çarçur", "carcur", "wifi", "bekleniyor", "alinamiyor",
        ) if w in cleaned
    )
    wellness_true = any(w in cleaned for w in ("klor", "masaj", "spa ", " sauna", "hamam", "wellness", "havuz kirli"))
    if fb_ops >= 4 and not wellness_true:
        scores[CAT_FOOD] += 10.0
        scores[CAT_SPA] -= 12.0
        scores[CAT_OTHER] += 1.5
    # Mesafe/konum "havuz 500 metre" — havuz hijyeni değil
    if any(w in cleaned for w in ("metre", "yürümek", "yurume", "koşmak", "kosmak")) and "havuz" in cleaned:
        if not wellness_true and "şezlong" not in cleaned and "sezlong" not in cleaned:
            scores[CAT_SPA] -= 4.0

    # Ses yalıtımı → oda konfor (HK temizlik değil)
    if any(w in cleaned for w in ("ses yalitim", "ses yalıtım", "yalitimi", "yalıtımı", "yan odadaki")):
        scores[CAT_OTHER] += 4.0
        scores[CAT_CLEANING] -= 3.0
        scores[CAT_SPA] -= 2.0

    # Personel dil
    if any(w in cleaned for w in ("turkce bilmiyor", "türkçe bilmiyor", "turkce bile", "türkçe bile")):
        scores[CAT_STAFF] += 6.0

    # İçecek soda (temizlik sodası değil)
    if _is_beverage_soda(cleaned, tokens):
        scores[CAT_FOOD] += 6.0
        scores[CAT_CLEANING] -= 5.0

    # Oda boyutu → Genel/konfor (temizlik değil)
    if any(p in cleaned for p in ("odalar cok kucuk", "odalar çok küçük", "oda cok kucuk", "oda çok küçük", "odalar kucuk", "odalar dar")):
        scores[CAT_OTHER] += 6.0
        scores[CAT_CLEANING] -= 5.0
        if any(w in cleaned for w in ("yemek", "lezzet", "kiyma", "kıyma")):
            scores[CAT_FOOD] += 4.0

    # mini bar / minibar: yiyecek-içecek eksik → F&B; bozuk → Teknik; ücret → Finans
    if "minibar" in cleaned or "mini bar" in cleaned:
        if any(w in cleaned for w in ("bozuk", "arızalı", "calismiyor", "çalışmıyor")):
            scores[CAT_TECH] += 4.0
        elif any(w in cleaned for w in ("ücret", "ucret", "fatura", "pahalı")):
            scores[CAT_FINANCE] += 3.0
        elif any(w in cleaned for w in (
            "yetersiz", "yiyecek", "icecek", "içecek", "bira", "atistirmalik", "atıştırmalık",
            "alkolsuz", "alkolsüz", "yok",
        )):
            scores[CAT_FOOD] += 5.5
            scores[CAT_CLEANING] += 1.0
        else:
            scores[CAT_CLEANING] += 2.5
            scores[CAT_FOOD] += 2.5

    # Bar içecek bağlamı: rakı/şarap/bira/barda → F&B bar (CAT_FOOD skoru + ontoloji bar)
    drink_markers = {
        "bira", "sarap", "şarap", "saraplar", "şaraplar", "raki", "rakı",
        "kokteyl", "tekila", "viski", "alkol", "icki", "içecek", "limonata", "soda",
    }
    if any(m in tokens or m in cleaned for m in drink_markers):
        scores[CAT_FOOD] += 3.5
    if "barda" in cleaned or "barlarda" in cleaned or re.search(r"(?<![a-zçğıöşü])bar(?![a-zçğıöşü])", cleaned):
        if not re.search(r"\bkibar", cleaned) and "minibar" not in cleaned and "mini bar" not in cleaned:
            scores[CAT_FOOD] += 4.0
    elif any(w in cleaned for w in ("kuyruk", "kuyruklar", "sira", "sıra")) and "bar" not in cleaned:
        scores[CAT_FOOD] += 3.0
        scores[CAT_RECEPTION] -= 2.0
        scores[CAT_FINANCE] -= 2.0

    # Aquapark / sıra bekleme olumlu → Spa/Havuz
    if any(w in cleaned for w in ("sira beklemiyorsunuz", "sira beklemiyor", "asiri sira beklemiyor")):
        scores[CAT_SPA] += 4.0

    # Animatör / şef davranış → Personel
    if any(w in tokens for w in ("sef", "şef", "personel", "personelin", "garson")):
        if any(w in cleaned for w in ("ilgisiz", "ilgi", "alakasiz", "lakayit", "kaba", "kokteyl")):
            scores[CAT_STAFF] += 5.0
            scores[CAT_FOOD] -= 2.0

    # pike / havlu eksik → Kat Hizmetleri
    if "pike" in cleaned or "havlu" in cleaned:
        scores[CAT_CLEANING] += 3.0

    # Yemek övgü ifadesi varken personel şikayeti ikincil
    if any(p in cleaned for p in ("yemek lezzetli", "yemek harika", "yemek mükemmel", "yemekler harika")):
        scores[CAT_FOOD] += 5.0
        if "garson" in tokens and "kaba" not in cleaned and "saygısız" not in cleaned:
            scores[CAT_STAFF] -= 3.0

    # Personel davranışı: garson/personel + olumsuz davranış → Personel
    staff_behavior = {"kaba", "ilgisiz", "saygısız", "yavaş", "küfür", "bağırdı"}
    if ("garson" in tokens or "personel" in tokens or "çalışan" in tokens):
        if any(b in tokens or b in cleaned for b in staff_behavior):
            # Yemek övgüsü baskınsa personel bonusu uygulanmaz
            if not any(p in cleaned for p in ("yemek lezzetli", "yemek harika", "yemek mükemmel")):
                scores[CAT_STAFF] += 4.0
                scores[CAT_FOOD] -= 2.0
                scores[CAT_RECEPTION] -= 1.0

    # Resepsiyonist kaba → Personel (davranış), giriş bekleme → Resepsiyon
    if "resepsiyonist" in tokens and any(b in cleaned for b in ("kaba", "saygısız", "ilgisiz")):
        scores[CAT_STAFF] += 5.0
        scores[CAT_RECEPTION] -= 2.0
    if any(p in cleaned for p in ("girişte bekledik", "check-in", "checkin", "lobide giriş", "saatlerce bekledik")):
        if "kaba" not in cleaned and "saygısız" not in cleaned:
            scores[CAT_RECEPTION] += 3.0
            scores[CAT_STAFF] -= 1.0

    # Yemek vs personel: yemek/lezzet/kahvaltı varsa yemek öncelikli (garson yoksa)
    food_markers = {"yemek", "lezzet", "lezzetli", "lezzetsiz", "kahvaltı", "çorba", "restoran", "büfe", "mutfak", "kiyma", "kıyma"}
    if any(m in tokens or m in cleaned for m in food_markers):
        scores[CAT_FOOD] += 2.0
        if "garson" not in tokens and "personel" not in tokens:
            scores[CAT_STAFF] -= 1.5

    # Spa vs temizlik: havuz/plaj/spa → Spa; oda/banyo → Temizlik
    if any(w in tokens for w in ("havuz", "spa", "masaj", "plaj", "animasyon", "wellness", "sauna")):
        scores[CAT_SPA] += 3.0
        scores[CAT_CLEANING] -= 1.0
    if any(w in tokens for w in ("oda", "odalar", "banyo", "havlu", "çarşaf")) and "havuz" not in tokens:
        scores[CAT_CLEANING] += 1.5
        scores[CAT_SPA] -= 0.5

    # Animatör davranış → Personel; animasyon programı/gürültü → Spa
    if "animatör" in tokens and any(b in tokens or b in cleaned for b in staff_behavior):
        scores[CAT_STAFF] += 3.0
        scores[CAT_SPA] -= 1.0
    elif "animasyon" in tokens:
        if any(w in cleaned for w in ("gürültü", "gurultu", "ses", "show", "eğlence", "eglence")):
            scores[CAT_SPA] += 4.0
            scores[CAT_STAFF] -= 2.0

    # Balık/yemek → Yemek (spa/plaj bağlamı yoksa)
    if any(w in tokens for w in ("balik", "balık", "yemek")) or "deniz urunu" in cleaned.replace("ü", "u"):
        scores[CAT_FOOD] += 3.0
        if "havuz" not in tokens and "plaj" not in tokens:
            scores[CAT_SPA] -= 1.5

    # Teknik vs spa: klima şikayeti birincil
    if "klima" in cleaned and any(w in cleaned for w in ("soğuk", "soğuktu", "bozuk", "arızalı", "çalışmıyor")):
        scores[CAT_TECH] += 5.0
        if "havuz" in cleaned and any(w in cleaned for w in ("beğendik", "beğendim", "güzel", "harika")):
            scores[CAT_SPA] += 2.0
            scores[CAT_TECH] += 2.0
    if any(w in tokens for w in ("klima", "wifi", "internet", "tv", "asansör", "priz", "kumanda")):
        scores[CAT_TECH] += 3.0

    # Finans: yalnızca gerçek fatura/ücret — değer pişmanlığı ve all-inclusive deneyim hariç
    if not _is_value_regret_context(cleaned) and not _is_all_inclusive_experience(cleaned):
        if any(w in tokens for w in ("fatura", "fiyat", "ücret", "ucret", "depozito", "pahalı", "fahiş")):
            if "minibar" in cleaned or "mini bar" in cleaned or "yiyecek" in tokens:
                scores[CAT_FOOD] += 2.0
            else:
                scores[CAT_FINANCE] += 2.5
    else:
        scores[CAT_FINANCE] = min(scores[CAT_FINANCE], 0.0)

    # Aquapark / etkinlik → Spa (aquaprk yazım hatası dahil)
    if any(w in tokens or w in cleaned for w in ("aquapark", "aquaprk", "etkinlik", "etkinlikler", "animasyon")):
        scores[CAT_SPA] += 3.5

    # Bakım / yıpranma: aquapark/havuz bağlamında Spa; demir/oda → Teknik
    if any(w in cleaned for w in ("yipranmis", "yıpranmış", "bakima ihtiyaci", "bakıma ihtiyacı")):
        if any(w in cleaned for w in ("aquapark", "aquaprk", "havuz", "kaydirak", "kaydırak")):
            scores[CAT_SPA] += 4.0
            scores[CAT_TECH] -= 1.0
        elif any(w in cleaned for w in ("demir", "demirler", "oda", "banyo")):
            scores[CAT_TECH] += 3.5
        else:
            scores[CAT_TECH] += 3.0
            scores[CAT_SPA] -= 0.5

    # Meyve / çeşitlilik / bal-kaymak → F&B
    if any(w in cleaned for w in ("meyve", "meyveler", "cesitlilik", "çeşitlilik", "bal kaymak", "kaymak bitiyor")):
        scores[CAT_FOOD] += 3.5
        scores[CAT_OTHER] -= 2.0

    # Yemek vs temizlik: mutfak hijyen / gıda güvenliği → Yemek
    if any(p in cleaned for p in ("mutfak hijyen", "hijyen mutfak", "gıda güvenliği", "böcek mutfak", "pis mutfak")):
        scores[CAT_FOOD] += 4.0
        scores[CAT_CLEANING] -= 2.0

    # Spa vs temizlik: hamam/sauna kirli → Spa (oda/banyo değil)
    if any(p in cleaned for p in ("hamam kirli", "sauna kirli", "spa hijyen", "masaj kötü")):
        scores[CAT_SPA] += 4.0
        scores[CAT_CLEANING] -= 1.5

    # Resepsiyon vs personel: transfer/shuttle gecikme → Resepsiyon
    if any(p in cleaned for p in ("transfer geç", "shuttle gecikti", "pickup gecikti", "overbooking", "oda hazır değil")):
        scores[CAT_RECEPTION] += 3.5
        scores[CAT_STAFF] -= 1.0

    # Teknik vs finans: minibar bozuk → Teknik; minibar ücreti → Finans
    if "minibar" in cleaned:
        if any(w in cleaned for w in ("ücret", "ucret", "fatura", "pahalı", "fahiş")):
            scores[CAT_FINANCE] += 3.0
        elif any(w in cleaned for w in ("bozuk", "çalışmıyor", "arızalı", "soğutmuyor")):
            scores[CAT_TECH] += 3.0


def _is_general_praise(cleaned: str) -> bool:
    if any(p in cleaned for p in GENERAL_PRAISE):
        return not any(w in cleaned for w in DEPT_HINTS)
    if "herşey" in cleaned and "güzel" in cleaned and len(cleaned.split()) <= 6:
        return not any(w in cleaned for w in DEPT_HINTS)
    return False


def _is_general_complaint(cleaned: str) -> bool:
    if any(p in cleaned for p in GENERAL_COMPLAINT):
        return not any(w in cleaned for w in DEPT_HINTS)
    return False


def _sorted_category_scores(scores: dict[str, float]) -> list[tuple[str, float]]:
    """Deterministik sıralama: skor desc, sonra kategori adı asc (tie-break)."""
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))


def _score_to_confidence(best: float, margin: float, phrase_hit: bool = False) -> float:
    """Deterministik güven skoru — asla 0.50 altına düşmez (anlamlı metin)."""
    if phrase_hit and best >= 4.0:
        return 0.95
    if phrase_hit or (best >= 5.0 and margin >= 1.0):
        return 0.92
    if best >= 8.0 and margin >= 3.0:
        return 0.98
    if best >= 6.0 and margin >= 2.0:
        return 0.95
    if best >= 4.0 and margin >= RULE_MARGIN:
        return 0.92
    if best >= RULE_SCORE_THRESHOLD and margin >= RULE_MARGIN:
        return 0.90
    if best >= RULE_SCORE_THRESHOLD:
        return 0.88
    if best >= 2.5:
        return 0.85
    if best >= 2.0:
        return 0.82
    if best >= 1.5:
        return 0.78
    if best >= 1.0:
        return 0.72
    if best > 0:
        return max(CONFIDENCE_FALLBACK_MIN, 0.65)
    return CONFIDENCE_FALLBACK_MIN


def _has_phrase_match(cleaned: str) -> bool:
    for phrases in CATEGORY_PHRASES.values():
        for phrase, _ in phrases:
            if phrase in cleaned:
                return True
    return False


def classify_by_rules(text: str) -> RuleClassificationResult:
    """
    Kural tabanlı deterministik sınıflandırma.
    Karışık yorumlarda şikayet cümlesi birincil kategori olur.
    """
    from app.services.turkish_nlp_utils import analyze_mixed_review, has_positive_idiom

    mixed = analyze_mixed_review(text)
    if mixed.is_mixed and mixed.primary_category:
        return RuleClassificationResult(
            mixed.primary_category, 0.90, "rules", 6.0, {},
            secondary_category=mixed.secondary_category,
            is_mixed=True,
        )

    cleaned, tokens = _prepare_text(text)

    if has_positive_idiom(text):
        return RuleClassificationResult(CAT_OTHER, 0.88, "rules", 5.0, {CAT_OTHER: 5.0})

    if _is_general_praise(cleaned):
        return RuleClassificationResult(CAT_OTHER, 0.92, "rules", 5.0, {CAT_OTHER: 5.0})

    if _is_general_complaint(cleaned):
        return RuleClassificationResult(CAT_OTHER, 0.90, "rules", 4.5, {CAT_OTHER: 4.5})

    scores = _score_categories(cleaned, tokens)
    ranked = _sorted_category_scores(scores)
    best_cat, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score
    phrase_hit = _has_phrase_match(cleaned)

    if best_score >= RULE_SCORE_THRESHOLD and margin >= RULE_MARGIN:
        conf = _score_to_confidence(best_score, margin, phrase_hit)
        return RuleClassificationResult(best_cat, conf, "rules", best_score, scores)

    if best_score >= 2.0 and margin >= 1.0:
        conf = _score_to_confidence(best_score, margin, phrase_hit)
        return RuleClassificationResult(best_cat, conf, "rules", best_score, scores)

    if best_score > 0:
        conf = _score_to_confidence(best_score, max(margin, 0.5), phrase_hit)
        conf = max(conf, CONFIDENCE_FALLBACK_MIN)
        return RuleClassificationResult(best_cat, conf, "fallback", best_score, scores)

    meaningful = len(cleaned.split()) >= 2
    empty_conf = CONFIDENCE_FALLBACK_MIN if meaningful else CONFIDENCE_MIN
    return RuleClassificationResult(CAT_OTHER, empty_conf, "fallback", 0.0, scores)


def rules_win_over_model(rule_result: RuleClassificationResult) -> bool:
    """Belirgin kural eşleşmesi varken ML modeli geçersiz kılınır."""
    if rule_result.confidence >= RULE_CONFIDENCE_WIN:
        return True
    if rule_result.method == "rules" and rule_result.confidence >= 0.78:
        return True
    if rule_result.rule_score >= RULE_SCORE_THRESHOLD:
        return True
    if rule_result.rule_score >= 1.5:
        return True
    ranked = _sorted_category_scores(rule_result.scores) if rule_result.scores else []
    if ranked and ranked[0][1] >= 2.0 and ranked[0][1] - ranked[1][1] >= 1.0:
        return True
    return False
