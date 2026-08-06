"""
Enhanced ABSA Engine - multi-clause, priority, sentiment score, action suggestion
Delegates to clause_pipeline for accurate department/aspect/sentiment detection.
"""

from __future__ import annotations

import os
import re
import logging
from typing import Any
from pathlib import Path

from app.services.turkish_nlp_utils import _fold_tr_word

logger = logging.getLogger(__name__)

# Sabitler

DOMAIN = "Turizm"

CATEGORIES = [
    "Oda Hizmetleri & Housekeeping",
    "Yiyecek & İçecek (F&B)",
    "Ön Büro & Misafir İlişkileri",
    "Teknik Servis & IT",
    "Rekreasyon & Eğlence",
    "Çevre, Güvenlik & Ulaşım",
    "Otel Atmosferi & Misafir Profili",
    "Personel Davranışı",
]

# Pipeline department → Platform department mapping
PIPELINE_TO_PLATFORM_DEPT = {
    "housekeeping": "Oda Hizmetleri & Housekeeping",
    "rooms": "Oda Hizmetleri & Housekeeping",
    "restaurant": "Yiyecek & İçecek (F&B)",
    "food_beverage": "Yiyecek & İçecek (F&B)",
    "bar": "Yiyecek & İçecek (F&B)",
    "front_office": "Ön Büro & Misafir İlişkileri",
    "teknik": "Teknik Servis & IT",
    "engineering": "Teknik Servis & IT",
    "havuz": "Rekreasyon & Eğlence",
    "leisure": "Rekreasyon & Eğlence",
    "spa": "Rekreasyon & Eğlence",
    "animasyon": "Rekreasyon & Eğlence",
    "personel": "Personel Davranışı",
    "staff": "Personel Davranışı",
    "genel": "Otel Atmosferi & Misafir Profili",
    "atmosphere": "Otel Atmosferi & Misafir Profili",
    "cevre": "Çevre, Güvenlik & Ulaşım",
    "grounds": "Çevre, Güvenlik & Ulaşım",
}

# Gold data normalization: maps any common variant to platform department
GOLD_DEPT_NORMALIZE = {
    "diger": "Otel Atmosferi & Misafir Profili",
    "yiyecek_icecek": "Yiyecek & İçecek (F&B)",
    "kat_hizmetleri": "Oda Hizmetleri & Housekeeping",
    "housekeeping": "Oda Hizmetleri & Housekeeping",
    "spa_wellness": "Rekreasyon & Eğlence",
    "personel_davranis": "Personel Davranışı",
}
# Also build lowercase-lookup for exact platform names with punctuation differences
for k, v in list(PIPELINE_TO_PLATFORM_DEPT.items()):
    GOLD_DEPT_NORMALIZE[k] = v
# Self-map canonical names
for c in CATEGORIES:
    GOLD_DEPT_NORMALIZE[c.lower()] = c

SENTIMENT_LABELS = {"positive": "OLUMLU", "negative": "OLUMSUZ", "neutral": "NOTR"}

PRIORITY_MAP = {
    "critical": "KRITIK",
    "high": "YUKSEK",
    "medium": "ORTA",
    "low": "DUSUK",
    "info": "BILGI",
}


# Clause splitting


# Additional Turkish implicit split markers
_TURKISH_SPLIT_WORDS = (
    "ama|fakat|ancak|lakin|cunku|ayrica|onun disinda|hatta|boylece|yani"
    "|ozellikle|ozetle|ustelik|bir de|yanı sıra|gerek|ister|nitekim|zaten|bunun yaninda"
    "|hem|veya|yahut|ya da|ne var ki|oysa|halbuki|kaldı ki|su durumda|bu yuzden"
    "|and|but|however|although|though|furthermore|moreover|nevertheless|besides"
)


_TOPIC_SHIFT_WORDS = (
    r"her\s+şey|her\s+yer|her\s+konuda|genel\s+olarak|bunun\s+dışında"
    r"|bir\s+de|üstelik|özellikle|ayrıca|hem\s+"
)


def _split_long_clause(c: str) -> list[str]:
    """Try to split a long clause using topic-shift heuristics."""
    if len(c) <= 40:
        return [c]

    # Strategy 1: split on "çok + adj" topic boundaries, only when the word
    # before "çok" is a known department keyword stem (not a generic word like "ekibi")
    words = c.split()
    if len(words) >= 4:
        for i, w in enumerate(words):
            wl = w.lower().strip(".,!?")
            if wl == "çok" and i >= 1:
                prev = words[i-1].lower().strip(".,!?")
                # Only split if prev word is a known topic trigger
                if any(prev.startswith(trig) for trig in _COK_TRIGGER_WORDS):
                    # Split at position i-1 (between prev and çok)
                    part1 = ' '.join(words[:i-1]).strip()
                    part2 = ' '.join(words[i-1:]).strip()
                    if len(part1) > 8 and len(part2) > 8:
                        # Only split if both parts have a department keyword
                        low1 = part1.lower()
                        low2 = part2.lower()
                        p1_has_dept = any(any(kw in low1 for kw in kws) for kws in _DEPT_KEYWORDS.values())
                        p2_has_dept = any(any(kw in low2 for kw in kws) for kws in _DEPT_KEYWORDS.values())
                        if p1_has_dept and p2_has_dept:
                            return [part1, part2]

    # Strategy 2: split on topic-shift words
    s2 = re.sub(rf"\s+({_TOPIC_SHIFT_WORDS})\s+", r" | ", c, flags=re.IGNORECASE)
    if s2 != c:
        parts = [p.strip() for p in s2.split("|") if len(p.strip()) > 8]
        if len(parts) > 1:
            return parts

    # Strategy 3a: split at "personel/çalışan/staff" when it appears after
    # a non-staff department mention, even if at/near end of clause
    _STAFF_WORDS = {"personel", "calisan", "çalışan", "görevli", "gorevli", "staff", "waiter", "garson"}
    for i, w in enumerate(words):
        wl = w.lower().strip(".,!?")
        if wl in _STAFF_WORDS and i >= 2:
            part1 = ' '.join(words[:i])
            part2 = ' '.join(words[i:])
            if len(part1) > 8 and len(part2) > 8:
                low1 = part1.lower()
                has_other_dept = any(
                    any(kw in low1 for kw in kws)
                    for dept, kws in _DEPT_KEYWORDS.items()
                    if dept != "Personel Davranışı"
                )
                if has_other_dept:
                    return [part1, part2]

    # Strategy 3b: keyword-cluster based topic-boundary split
    low = c.lower()
    words = c.split()
    if len(words) >= 6:
        # Assign each word to a department if it matches a keyword
        word_depts = []
        for w in words:
            wl = w.lower()
            matched = None
            for dept, kws in _DEPT_KEYWORDS.items():
                if any(kw in wl for kw in kws):
                    matched = dept
                    break
            word_depts.append(matched)
        
        # Find positions where department transitions (null → dept → other dept)
        splits = []
        last_dept = None
        for i in range(len(words)):
            curr_d = word_depts[i]
            if last_dept and curr_d and curr_d != last_dept:
                # Require that ≥2 different words (not same word repeated) match new dept
                matching_indices = [idx for idx, d in enumerate(word_depts) if d == curr_d]
                unique_words = set(words[idx].lower() for idx in matching_indices)
                if len(unique_words) >= 2:
                    splits.append(i)
            if curr_d:
                last_dept = curr_d
        if splits:
            # Split at ALL department transition points
            result_parts = []
            prev = 0
            for s in sorted(splits):
                part = ' '.join(words[prev:s])
                if len(part) >= 12:
                    result_parts.append(part.strip())
                prev = s
            rest_part = ' '.join(words[prev:])
            if len(rest_part) >= 12:
                result_parts.append(rest_part.strip())
            if len(result_parts) > 1:
                return result_parts

    return [c]


def split_clauses(text: str) -> list[str]:
    """Smart clause splitting — punctuation, conjunctions, newlines, and topic-boundary heuristics."""
    from app.services.ml_splitter import split_clauses_ml
    ml_split = split_clauses_ml(text)
    if ml_split is not None:
        return ml_split[:60]

    text = re.sub(r"\s+", " ", text.strip())
    # Protect dates like 29.06, 30.06, 05.07 before splitting on dots
    text = re.sub(r"(\d{1,2})\.(\d{1,2})", r"\1__DOT__\2", text)
    text = re.sub(r"[.!?]+", " | ", text)
    text = re.sub(r"\n+", " | ", text)
    text = re.sub(r"[,;:]", " | ", text)
    text = re.sub(rf"\s+({_TURKISH_SPLIT_WORDS})\s+", r" \1 | ", text)
    text = re.sub(r"\s+(diye|bile|ise|karsi|gore)\s+", " | ", text)
    # Restore dates
    text = text.replace("__DOT__", ".")

    _TRAILING_CONJ = re.compile(
        r"\s+(ama|fakat|ancak|lakin|cunku|ayrica|hatta|boylece|yani"
        r"|ozellikle|ozetle|ustelik|bir de|nitekim|zaten"
        r"|hem|veya|yahut|ya da|ve|ile|diye|bile|ise)$", re.IGNORECASE)
    raw_clauses = []
    for part in text.split("|"):
        p = _TRAILING_CONJ.sub("", part.strip())
        if len(p) > 10:
            raw_clauses.append(p)

    result = []
    for c in raw_clauses:
        queue = list(_split_long_clause(c))
        while queue:
            p = queue.pop(0)
            subs = _split_long_clause(p)
            if len(subs) > 1:
                # Also trim trailing conjunctions from split parts
                trimmed = [_TRAILING_CONJ.sub("", s.strip()) for s in subs if s.strip()]
                trimmed = [t for t in trimmed if len(t) >= 10 and len(t.split()) >= 2]
                if trimmed:
                    queue.extend(trimmed)
            elif len(p) >= 10 and len(p.split()) >= 2:
                trimmed = _TRAILING_CONJ.sub("", p.strip())
                if len(trimmed) >= 10 and len(trimmed.split()) >= 2:
                    result.append(trimmed)

    # Fallback: if every clause was too short, keep the original text
    if not result and len(text.strip()) >= 4:
        result = [text.strip()]

    return result[:60]


# Pipeline-powered analysis


def _keyword_sentiment(clause: str) -> tuple[str, float]:
    """Simple keyword sentiment baseline for the pipeline."""
    low = clause.lower()
    low_folded = _fold_tr_word(low)
    pos = 0.0
    neg = 0.0
    positive_words = ["guzel", "güzel", "harika", "mukemmel", "mükemmel", "basarili", "başarılı",
                       "tesekkur", "teşekkür", "memnun", "keyifli", "eglenceli", "eğlenceli",
                       "yardimsever", "yardımsever", "kibar", "profesyonel", "rahat", "temiz",
                       "lezzetli", "sessiz", "hizli", "hızlı", "iyi", "begen", "beğen",
                       "ilgili", "ilgiliydi", "güzeldi", "guzeldi", "basariliydi",
                       "yardimci", "yardımcı", "yardım", "yardim", "nazik", "güleryüz",
                       "guleryuz", "ilgilen", "ilgilendi", "destek", "coşuyor", "cosuyor",
                       "başarılıydı", "basariliydi", "beğendik", "begeni", "beğeni",
                       "güzel", "guzel", "iyiydi", "iyi"]
    negative_words = ["kotu", "kötü", "berbat", "pis", "kirli", "yorgun", "pisman", "pişman",
                       "cop", "çöp", "dar", "kucuk", "küçük", "soguk", "soğuk", "yavas", "yavaş",
                       "karisik", "karışık", "yorucu", "kaba", "ilgisiz", "gurultu", "gürültü",
                       "ariza", "arıza", "bozuk", "çalışmıyor", "calismiyor", "sorun", "hata",
                       "bekleme", "kuyruk", "dusuk", "düşük", "yok", "bulamiyor", "bulamıyor",
                       "ugras", "uğraş", "beklemiyordum", "beklemezdim"]

    # Match both native Turkish and ASCII-folded forms
    for w in positive_words:
        if w in low or _fold_tr_word(w) in low_folded:
            pos += 1
    for w in negative_words:
        if w in low or _fold_tr_word(w) in low_folded:
            neg += 1
    # Negation handling: "olmadı", "değil", "yok" after a positive word flips the sentiment
    negators = ["olmadı", "olmadi", "olmadig", "olmadig", "değil", "degil",
                "yapılmadı", "yapilmadi", "yok", "bulunmuyor", "bulunmuyordu"]
    for negator in negators:
        if negator in low or _fold_tr_word(negator) in low_folded:
            neg += 0.5  # add mild negative weight for negated context
    if pos > neg:
        return "Positive", round(min(0.5 + 0.15 * (pos - neg), 1.0), 2)
    elif neg > pos:
        return "Negative", round(max(-1.0, -0.5 - 0.15 * (neg - pos)), 2)
    return "Neutral", 0.0


# Department keyword gates (clause must match at least 2 to pass)
_DEPT_KEYWORDS = {
    "Oda Hizmetleri & Housekeeping": ["oda", "temiz", "yatak", "banyo", "havlu",
        "buklet", "balkon", "manzara", "minibar", "oda servis", "kat hizmet",
        "room", "bed", "bathroom", "clean", "towel", "pillow",
        "comfortable", "shower", "bedroom",
        "oda geniş", "oda ferah", "oda koku", "oda sicak", "oda soguk",
        "küvet", "kuvet", "duş", "dus", "musluk", "lavabo", "klozet",
        "gardırop", "gardrop", "dolap", "komodin", "ayna", "aydinlatma",
        "perde", "halı", "hali", "pencere", "cam",
        "kettle", "çaydanlık", "caydanlik", "su ısıtıcı", "su isitici",
        "rutubet", "nem", "küf", "kuf", "mantar", "böcek", "bocek",
        "bornoz", "terlik", "şampuan", "sampuan", "sabun", "losyon",
        "koku", "sigara kokusu",
        "konfor", "rahatlık", "rahatlik", "teras",
        "temizlikçi", "kathizmet", "kat hizmetcileri",
        "camasir", "çamaşır", "utu", "ütü",
        "oda buyuk", "oda kucuk", "oda dar", "oda genis",
        "yatak rahat", "yatak sert", "yatak yumuşak", "yatak yumusak",
        "yastik", "yorgan", "carsaf", "nevresim",
        "leke", "lekeli", "toz", "kir", "pis"],
    "Yiyecek & İçecek (F&B)": ["yemek", "kahvaltı", "restoran", "bar", "minibar",
        "yiyecek", "içecek", "lezzet", "menü", "büfe", "akşam", "öğle", "mutfak",
        "çatal", "bıçak", "tabak", "servis", "garson",
        "food", "breakfast", "dinner", "lunch", "menu", "drink", "meal",
        "taste", "delicious", "buffet", "restaurant", "wine", "beer",
        "dondurma", "pizza", "kumpir", "gözleme", "gozleme",
        "kahvalti", "bufe", "menu", "ogle", "mutfak", "catal", "bicak",
        "restorant", "bardak", "kasik", "peçete", "pecete",
        "corba", "çorba", "et", "tavuk", "balik", "makarna", "pilav", "salata",
        "domates", "kabak", "kiyma", "kıyma", "kofte", "köfte",
        "meyve", "meyveler", "tatli", "baklava", "borek", "börek",
        "pogaca", "poğaça", "kurabiye", "simit", "pasta",
        "kahve", "cay", "çay", "limonata", "meyve suyu", "soda", "kola",
        "bira", "raki", "sarap", "alkol", "icki", "icecek",
        "bal", "kaymak", "recel", "reçel", "zeytin", "peynir",
        "omlet", "menemen", "tost", "ekmek",
        "tuzlu", "yagli", "yağlı", "baharatli", "aci", "acı",
        "kursun", "kuşun", "kuyruk", "sira", "sıra",
        "cesit", "cesitlilik", "çeşit", "çeşitlilik", "zengin", "yetersiz",
        "soguk", "sicak", "sıcak", "soğuk", "bayat", "taze",
        "lezzetli", "lezzetsiz", "harika", "berbat",
        "ala carte", "a la carte", "acik bufe", "açık büfe",
        "canli istasyon", "canlı istasyon", "omlet istasyonu"],
    "Ön Büro & Misafir İlişkileri": ["resepsiyon", "check-in", "checkin",
        "giriş", "çıkış", "karşılama", "rezervasyon", "misafir ilişki",
        "reception", "check out", "checkout", "booking", "front desk",
        "invoice", "payment", "check in",
        "giris", "cikis", "karsilama", "lobi", "lobby", "concierge",
        "bellboy", "valiz", "bagaj", "baggage", "upgrade", "oda degisikligi",
        "erken giris", "early checkin", "gec cikis", "late checkout",
        "misafir iliskileri", "guest relations", "anahtar", "key card",
        "kart", "odeme", "fatura", "bekleme", "kuyruk",
        "cagri merkezi", "çağrı merkezi", "musteri hizmet", "müşteri hizmet",
        "musteri temsilci", "müşteri temsilci",
        "bekleme suresi", "bekleme salonu",
        "arac", "araç", "transfer", "tur", "gezi",
        "cozum", "çözüm", "yardim", "yardım", "destek",
        "sikayet", "şikayet", "problem", "sorun",
        "guleryuz", "güleryüz", "ilgi", "alaka",
        "otel hakkinda", "bilgi", "yonlendirme", "yönlendirme",
        "misafir memnuniyet", "guest satisfaction"],
    "Teknik Servis & IT": ["klima", "wifi", "televizyon", "tv", "elektrik",
        "arıza", "bozuk", "çalışmıyor", "teknik", "internet", "kumanda",
        "çekmiyor", "kopuyor", "bağlantı",
        "air conditioner", "heating", "water pressure", "elevator",
        "remote", "channel", "wi-fi",
        "ariza", "calismiyor", "calismayan", "teknik", "baglanti",
        "sıcak su", "sicak su", "soguk su", "soğuk su",
        "su basinci", "su basıncı", "su akis", "su akış",
        "isitma", "ısıtma", "kalorifer", "radyator", "radyatör",
        "kart", "anahtar", "kilit", "manyetik",
        "telefon", "hat", "sinyal", "şebeke", "sebeke",
        "onarim", "onarım", "bakim", "bakım", "teknik servis",
        "tikali", "tıkalı", "tikanik", "tıkanık", "gider",
        "su kacagi", "su kaçağı",
        "priz", "voltaj", "sigorta",
        "klima sogutmuyor", "klima isitmiyor",
        "sogutma", "soğutma", "fan", "pervane",
        "cekmiyor", "kopma", "kopuyor",
        "asansör", "asansor", "lift",
        "saç kurutma", "sac kurutma", "fon"],
    "Rekreasyon & Eğlence": ["havuz", "spa", "animasyon", "plaj",
        "eğlence", "aktivite", "aqua", "aquapark", "sauna", "hamam", "fitness",
        "çocuk", "şezlong", "şemsiye",
        "pool", "beach", "entertainment", "activity", "kids club",
        "sunbed", "lounger", "performance", "show", "dance",
        "eglence", "animasyon", "cocuk", "sezlong", "semsiye",
        "su parki", "su parkı", "kaydirak", "kaydırak", "su kaydirak",
        "aquapark kapali", "aquapark yetersiz",
        "tenis", "basketbol", "voleybol", "futbol", "saha",
        "bilardo", "langirt", "langırt", "masa futbolu",
        "playstation", "disko", "canli muzik", "canlı müzik",
        "oyun", "oyuncak", "egitmen", "eğitmen",
        "spor", "fitness", "yoga", "pilates", "zumba",
        "bisiklet", "yuruyus", "yürüyüş",
        "konser", "show", "gosteri", "gösteri", "tiyatro",
        "parti", "gece eglence", "gece kulubu", "gece kulübü",
        "cocuk havuz", "cocuk klub", "cocuk kulubu",
        "sezlong yetersiz", "semsiye yetersiz",
        "masaj", "jakuzi", "wellness", "buhar", "tuz odasi"],
    "Çevre, Güvenlik & Ulaşım": ["otopark", "park", "konum", "çevre", "güvenlik",
        "transfer", "ulaşım", "bahçe", "manzara", "deniz", "plaj",
        "location", "parking", "transport", "security", "garden",
        "distance", "walk", "station", "airport", "bus", "metro", "taxi",
        "cevre", "guvenlik", "ulasim", "bahce",
        "konum guzel", "konum iyi", "merkez", "merkezi",
        "sevk", "servis arac", "ring", "shuttle",
        "yakın", "yakin", "uzak", "yurume", "yürüme",
        "cankurtaran", "can simidi", "can simidi",
        "engelli", "rampa", "kamera", "bekci", "bekçi",
        "kumsal", "sahil", "cakil", "çakıl",
        "dolmus", "dolmuş", "otobus", "otobüs",
        "havaalani", "havaalanı", "tren", "gar",
        "cevre duzenleme", "peyzaj",
        "koruma", "hirsiz", "hırsız", "kasa", "emniyet",
        "sokak", "cadde", "bulvar",
        "camasirhane", "çamaşırhane", "kuru temizleme",
        "insaat", "inşaat", "gurultu kirliligi"],
    "Otel Atmosferi & Misafir Profili": ["atmosfer", "ortam", "aile", "sakin",
        "huzurlu", "kalabalık", "gürültü", "dekorasyon", "fiyat", "performans",
        "tavsiye", "genel",
        "atmosphere", "quiet", "noise", "price", "value", "overall",
        "recommend", "experience", "decoration", "family",
        "kalabalik", "gurultu", "dekor",
        "sessiz", "huzurlu",
        "konsept", "tema", "mimari",
        "kalite", "standart", "sinif", "sınıf",
        "ucuz", "pahali", "pahalı",
        "tatil", "deneyim",
        "musteri profili", "müşteri profili", "kitle", "profil",
        "cift", "çift", "genç", "genc", "yasli", "yaşlı",
        "butik", "zincir",
        "yenilenmis", "yenilenmiş", "restore", "modern", "klasik",
        "tadilat", "yenileme",
        "rahatsiz", "rahatsız",
        "samimi", "sıcak", "profesyonel",
        "kalite dusuk", "kalite iyi",
        "otelin durumu", "genel durum",
        "konsept otel", "tema otel",
        "aile otel", "ciftler icin", "gencler icin",
        "manzara guzel", "ortam guzel",
        "beklenti", "hayal kirikligi", "hayal kırıklığı",
        "memnun", "memnuniyet", "memnun kaldi", "memnun kaldik"],
    "Personel Davranışı": ["personel", "çalışan", "görevli", "servis",
        "güleryüz", "ilgili", "yardımsever", "kibar", "profesyonel",
        "teşekkür", "ilgi",
        "staff", "friendly", "helpful", "service", "manager",
        "receptionist", "waiter", "polite", "professional", "thank",
        "guleryuz", "guleryuzlu", "guler yuz", "guler yuzlu",
        "canayakin", "sicakkanli", "sıcakkanlı",
        "yonetici", "mudur", "midur",
        "hostes", "host", "barmen", "asci", "sef",
        "animator", "ekip", "egitimli", "egitim", "tebessum",
        "calisan", "gorevli",
        "garson", "komi", "kasap", "bulaşık", "temizlikci",
        "muamele", "davranis", "davranış", "tavir", "tavır",
        "suratsiz", "suratsız", "kaba", "ilgisiz", "saygisiz", "saygısız",
        "azarlayan", "bagiran", "bağıran",
        "nazik", "saygili", "saygılı",
        "anaslayışlı", "anlayışlı", "dusunceli", "düşünceli",
        "beceriksiz", "deneyimsiz", "acemi",
        "motivasyon", "yonetim", "yönetim",
        "egitim", "eğitim", "donanimli", "donanımlı",
        "yardim", "yardım", "destek",
        "sagol", "sağol", "eyvallah", "tesekkur ederim",
        "gorev", "görev", "sorumluluk",
        "personel yetersiz", "personel ilgili",
        "calisan memnuniyet", "ekip calismasi", "takim", "takım"],
}

# Build _COK_TRIGGER_WORDS as a flat set of keyword stems from all departments
# These are words that legitimately introduce a new "çok + adj" evaluation topic
_COK_TRIGGER_WORDS: set[str] = set()
for kws in _DEPT_KEYWORDS.values():
    for kw in kws:
        _COK_TRIGGER_WORDS.add(kw[:4])


# Aspect resolution per department (when ML overrides pipeline)
_DEPT_ASPECT_KEYWORDS: dict[str, list[tuple[str, str, list[str]]]] = {
    "Oda Hizmetleri & Housekeeping": [
        ("room_cleanliness", "Oda & Banyo Temizliği", ["temiz", "kirli", "pis", "kok", "hijyen",
            "banyo", "havlu", "buklet"]),
        ("room_size", "Genel oda konforu", ["geniş", "dar", "küçük", "oda büyük", "ferah",
            "sıkışık"]),
        ("room_noise", "Oda Ses / Konfor", ["gürültü", "ses", "sessiz", "komşu", "trafik",
            "yatak", "rahat"]),
        ("housekeeping_service", "Kat Hizmetleri", ["kat hizmet", "temizlik", "oda temiz",
            "çamaşır"]),
        ("minibar_supply", "Minibar İkmal", ["minibar", "ikmal", "eksik", "stok"]),
        ("minibar_tech", "Minibar Teknik", ["minibar", "bozuk", "soğutmuyor", "çalışmıyor"]),
    ],
    "Yiyecek & İçecek (F&B)": [
        ("food_taste", "Yemek Lezzeti", ["lezzet", "güzel", "harika", "berbat", "tad",
            "yemek", "kahvaltı"]),
        ("drink_quality", "İçecek Kalitesi", ["içecek", "kahve", "çay", "meyve suyu", "kola"]),
        ("drink_variety", "İçecek Çeşitliliği", ["çeşit", "içecek çeşit", "az", "yok"]),
        ("service_queue", "Servis / Kuyruk", ["kuyruk", "bekleme", "sıra", "servis yavaş",
            "garson"]),
        ("table_cleanliness", "Masa / Servis Temizliği", ["masa temiz", "masa kirli",
            "peçete", "örtü"]),
        ("cutlery", "Çatal Bıçak", ["çatal", "bıçak", "kaşık", "tabak"]),
        ("meat_quality", "Et / Kıyma Kalitesi", ["et", "kıyma", "köfte", "biftek", "tavuk"]),
    ],
    "Ön Büro & Misafir İlişkileri": [
        ("front_office", "Resepsiyon / Check-in", ["resepsiyon", "check-in", "giriş", "çıkış",
            "karşılama", "rezervasyon", "kayıt"]),
    ],
    "Teknik Servis & IT": [
        ("wifi", "WiFi / İnternet", ["wifi", "internet", "bağlantı", "şebeke", "çekmiyor"]),
        ("tech_general", "Teknik Sorunlar", ["klima", "arıza", "bozuk", "çalışmıyor",
            "televizyon", "tv", "kumanda", "elektrik"]),
    ],
    "Rekreasyon & Eğlence": [
        ("pool_lounger", "Havuz / Aktivite", ["havuz", "şezlong", "şemsiye", "aquapark",
            "su kaydırağı"]),
        ("spa", "Spa & Wellness", ["spa", "sauna", "hamam", "masaj", "wellness", "fitness"]),
        ("animation", "Animasyon & Etkinlik", ["animasyon", "eğlence", "aktivite", "çocuk",
            "mini kulüp", "etkinlik"]),
    ],
    "Çevre, Güvenlik & Ulaşım": [
        ("location", "Konum / Çevre", ["konum", "çevre", "merkez", "ulaşım", "manzara",
            "deniz", "plaj"]),
        ("parking", "Otopark", ["otopark", "park", "araç"]),
        ("transport", "Ulaşım Servis", ["transfer", "servis", "ulaşım", "shuttle"]),
        ("safety", "Güvenlik", ["güvenlik", "hırsız", "kasa", "emniyet"]),
    ],
    "Otel Atmosferi & Misafir Profili": [
        ("guest_experience", "Genel Deneyim", ["genel", "deneyim", "atmosfer", "ortam",
            "otelin", "tavsiye"]),
        ("value_for_money", "Fiyat / Performans", ["fiyat", "performans", "pahalı", "ucuz",
            "değer", "para"]),
        ("capacity", "Kapasite / Yoğunluk", ["kalabalık", "yoğun", "kapasite", "dolu"]),
    ],
    "Personel Davranışı": [
        ("staff_behavior", "Personel Davranışı", ["personel", "çalışan", "görevli",
            "güleryüz", "ilgili", "yardımsever", "kibar", "profesyonel", "ilgi",
            "teşekkür", "memnun"]),
    ],
}


def _resolve_aspect_for_dept(clause: str, dept: str) -> tuple[str, str]:
    """Pick the best aspect_key + label for a clause within a department."""
    low = str(clause).lower()
    low_folded = _fold_tr_word(low)
    aspects = _DEPT_ASPECT_KEYWORDS.get(dept, [])
    if not aspects:
        return ("general", "Genel")
    best_key, best_label, best_score = "general", "Genel", 0
    for key, label, keywords in aspects:
        score = 0
        for kw in keywords:
            if kw in low or _fold_tr_word(kw) in low_folded:
                score += 1
        if score > best_score:
            best_score = score
            best_key, best_label = key, label
    if best_score == 0:
        return (aspects[0][0], aspects[0][1])
    return (best_key, best_label)


def _keyword_dept_score(clause: str) -> list[tuple[str, int]]:
    """Score all departments by keyword match count in clause."""
    low = str(clause).lower()
    low_folded = _fold_tr_word(low)
    scores = []
    for dept, kws in _DEPT_KEYWORDS.items():
        hits = 0
        for kw in kws:
            if kw in low or _fold_tr_word(kw) in low_folded:
                hits += 1
        if hits > 0:
            scores.append((dept, hits))
    return sorted(scores, key=lambda x: -x[1])


def _ml_consensus_agrees(clause: str, dept: str) -> bool:
    """Check if both TF-IDF and embedding models agree on the same department."""
    _load_emb_ml()
    _load_clause_ml()
    tfidf_dept = None
    # Run TF-IDF model
    if _clause_model is not False and _clause_model is not None:
        try:
            cleaned = re.sub(r"[^\w\sçğıöşüÇĞİÖŞÜ]", " ", str(clause or "").lower())
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            vec = _clause_vec.transform([cleaned])
            probs = _clause_model.predict_proba(vec)[0]
            idx = int(probs.argmax())
            tfidf_dept = _clause_labels[idx]
        except Exception:
            pass
    # Run embedding model
    emb_dept = None
    if _emb_model and _emb_sbert and _emb_clf is not None:
        try:
            emb = _emb_sbert.encode([str(clause or "")], show_progress_bar=False, batch_size=1)
            probs = _emb_clf.predict_proba(emb)[0]
            idx = int(probs.argmax())
            emb_dept = _emb_labels[idx]
        except Exception:
            pass
    # Both must agree with the proposed dept
    if tfidf_dept is not None and emb_dept is not None:
        return tfidf_dept == dept and emb_dept == dept
    if tfidf_dept is not None:
        return tfidf_dept == dept
    if emb_dept is not None:
        return emb_dept == dept
    return False


def _select_department(
    clause: str,
    pipe_dept_raw: str,
    decision,
) -> tuple[str, str, str]:
    """
    Select department: pipeline first (when specific AND keyword-supported),
    then ML consensus, then keywords, else atmosphere.
    Pipeline is only trusted when its predicted department has at least one
    keyword match in the clause (prevents generic clauses from getting
    random department assignments).
    """
    pipe_platform = PIPELINE_TO_PLATFORM_DEPT.get(pipe_dept_raw.lower().strip(), "Otel Atmosferi & Misafir Profili")
    kw_scores = _keyword_dept_score(clause)
    kw_best = kw_scores[0][0] if kw_scores else None
    kw_best_score = kw_scores[0][1] if kw_scores else 0

    # Pipeline specific → verify keyword support before trusting
    if pipe_platform != "Otel Atmosferi & Misafir Profili" and pipe_dept_raw.strip():
        low_check = str(clause).lower()
        low_folded_check = _fold_tr_word(low_check)
        pipe_kw_count = sum(
            1 for kw in _DEPT_KEYWORDS.get(pipe_platform, [])
            if kw in low_check or _fold_tr_word(kw) in low_folded_check
        )
        if pipe_kw_count >= 1:
            final = pipe_platform
        else:
            final = "Otel Atmosferi & Misafir Profili"
    else:
        # Pipeline says atmosphere (generic) — try ML consensus (both models agree)
        ml_dept, ml_prob = _clause_ml_predict(clause)
        if ml_dept and ml_prob >= 0.95 and ml_dept != "Otel Atmosferi & Misafir Profili":
            # Verify consensus: second model also predicts the same dept
            _consensus_ok = _ml_consensus_agrees(clause, ml_dept)
            if _consensus_ok:
                final = ml_dept
            else:
                final = "Otel Atmosferi & Misafir Profili"
        elif kw_best and kw_best_score >= 2:
            final = kw_best
        else:
            final = "Otel Atmosferi & Misafir Profili"

    aspect_key, aspect_label = _resolve_aspect_for_dept(clause, final)
    return final, aspect_key, aspect_label


def analyze_text(text: str) -> list[dict]:
    """Analyze text using clause_pipeline + BERTurk ensemble for accurate detection."""
    from app.services.ontology_service import OntologyService
    from app.services.clause_pipeline import classify_clauses
    from app.services.ml_classifier import classify_berturk, CANONICAL as CANONICAL_DEPTS

    # NOT: Burada her çağrıda reload_ontology() + reload_pipeline_config() yapılıyordu.
    # Bu, lru_cache'leri temizleyip domain_ontology.json ile 3007 satırlık
    # clause_pipeline.yaml dosyasını HER YORUM İÇİN yeniden parse ettiriyordu
    # (500 yorumluk batch'te 500 kez). Config dosyaları çalışma anında değişmediği
    # için yeniden yükleme yalnızca açıkça istendiğinde yapılmalı; ilgili
    # reload_* fonksiyonları hâlâ mevcut ve /ontology/reload gibi uçlardan çağrılabilir.

    clauses = split_clauses(text)
    decisions = classify_clauses(clauses, sentiment_fn=_keyword_sentiment, mapping_fn=OntologyService.map_aspect_to_department)
    results = []

    for clause, decision in zip(clauses, decisions):
        if not decision.include:
            continue

        pipe_dept_raw = (decision.department or "").lower().strip()
        asp_raw = (decision.aspect_key or "").lower().strip()

        # Ontology override: when confident (>0.8) and specific dept, trust ontology
        onto_map = OntologyService.map_aspect_to_department(clause, clause) or {}
        onto_conf = onto_map.get("confidence", 0.0)
        onto_dept = onto_map.get("departmentLabel", "") or onto_map.get("department_label", "")
        if onto_conf >= 0.8 and onto_dept not in ("Genel", "genel", "", None):
            final_dept = onto_dept
            aspect_key = onto_map.get("aspect_key", onto_map.get("aspect", asp_raw))
            aspect_label = onto_map.get("aspectLabel", onto_map.get("aspect_label", decision.aspect_label))
        elif asp_raw not in ("general", "") and pipe_dept_raw not in ("genel", "", "atmosphere"):
            final_dept = decision.department_label or "Otel Atmosferi & Misafir Profili"
            aspect_key = decision.aspect_key
            aspect_label = decision.aspect_label
        else:
            final_dept, aspect_key, aspect_label = _select_department(clause, pipe_dept_raw, decision)

        # BERTurk ensemble:
        # - Never override non-generic departments selected by rules/pipeline.
        # - Only help when current result is generic atmosphere fallback.
        # - Require high confidence + keyword support for predicted department.
        ml_result = classify_berturk(clause)
        kw_scores = _keyword_dept_score(clause)
        kw_best_score = kw_scores[0][1] if kw_scores else 0
        _kw_best_dept = kw_scores[0][0] if kw_scores else None
        allow_override = False
        if (
            ml_result
            and ml_result["confidence"] >= 0.92
            and final_dept == "Otel Atmosferi & Misafir Profili"
        ):
            ml_dept_name = ml_result["department"]
            # Verify BERTurk's prediction has keyword support (even folded)
            low_check = str(clause).lower()
            low_folded_check = _fold_tr_word(low_check)
            ml_kw_count = sum(
                1 for kw in _DEPT_KEYWORDS.get(ml_dept_name, [])
                if kw in low_check or _fold_tr_word(kw) in low_folded_check
            )
            # Strong guard: predicted department should have >=2 keyword hits.
            # This avoids random overrides on generic or very short clauses.
            allow_override = ml_kw_count >= 2 and kw_best_score >= 1
        if allow_override:
            ml_dept = ml_result["department"]
            if ml_dept != final_dept:
                logger.info(
                    "BERTurk override: clause=%r pipeline=%s berturk=%s conf=%.3f",
                    clause[:80], final_dept, ml_dept, ml_result["confidence"]
                )
                final_dept = ml_dept
                aspect_key, aspect_label = _resolve_aspect_for_dept(clause, final_dept)

        sent = decision.sentiment or "Neutral"
        sent_label = SENTIMENT_LABELS.get(sent.lower(), "NOTR")
        priority_label = PRIORITY_MAP.get(decision.priority or "medium", "ORTA")

        results.append({
            "text": clause[:250],
            "domain": DOMAIN,
            "aspect": aspect_key,
            "aspect_label": aspect_label,
            "department": final_dept,
            "sentiment": sent_label,
            "sentiment_score": decision.sentiment_score or 0.0,
            "satisfaction": get_satisfaction(decision.sentiment_score or 0.0),
            "priority": priority_label,
            "suggestion": get_action_suggestion(final_dept, sent_label),
            "confidence": ml_result["confidence"] if ml_result else getattr(decision, 'confidence', 0.95),
        })

    # Frequency filter: keep all specific departments; only filter out
    # Otel Atmosferi (generic/fallback) when it appears once among other depts
    if results:
        dept_counts = {}
        for r in results:
            dept_counts[r['department']] = dept_counts.get(r['department'], 0) + 1
        generic_dept = "Otel Atmosferi & Misafir Profili"
        has_specific = any(d != generic_dept for d in dept_counts)
        if has_specific and dept_counts.get(generic_dept, 0) == 1:
            results = [r for r in results if r['department'] != generic_dept]

    # Dedup by department (keep first)
    seen = set()
    deduped = []
    for r in results:
        if r['department'] not in seen:
            seen.add(r['department'])
            deduped.append(r)
    return deduped


def get_satisfaction(score: float) -> str:
    if score >= 0.7:
        return "Cok Iyi"
    elif score >= 0.3:
        return "Iyi"
    elif score > -0.3:
        return "Kararsiz"
    elif score > -0.7:
        return "Az Memnun"
    else:
        return "Hic Memnun Degil"


def get_action_suggestion(department: str, sentiment_label: str) -> str:
    suggestions = {
        "Oda Hizmetleri & Housekeeping": {
            "OLUMSUZ": "Oda temizlik, buklet malzemeleri ve yatak konforu gozden gecirilmeli.",
            "OLUMLU": "Oda standartlari korunmali.",
        },
        "Yiyecek & İçecek (F&B)": {
            "OLUMSUZ": "Menu kalitesi, cesitliligi ve minibar hizmeti iyilestirilmeli.",
            "OLUMLU": "Yiyecek-icecek kalitesi ve cesitliligi korunmali.",
        },
        "Ön Büro & Misafir İlişkileri": {
            "OLUMSUZ": "Rezervasyon, giris-cikis surecleri ve sikayet cozumu hizlandirilmali.",
            "OLUMLU": "Misafir iliskileri ve karsilama standardi korunmali.",
        },
        "Teknik Servis & IT": {
            "OLUMSUZ": "Klima, wifi ve teknik arizalara mudahale suresi dusurulmeli.",
            "OLUMLU": "Teknik altyapi ve mobil uygulama performansi korunmali.",
        },
        "Rekreasyon & Eğlence": {
            "OLUMSUZ": "Havuz/spa hijyeni, animasyon ve cocuk kulubu hizmetleri iyilestirilmeli.",
            "OLUMLU": "Rekreasyon ve eglence hizmet kalitesi korunmali.",
        },
        "Çevre, Güvenlik & Ulaşım": {
            "OLUMSUZ": "Peyzaj, otopark, guvenlik ve transfer hizmetleri gozden gecirilmeli.",
            "OLUMLU": "Cevre duzeni ve guvenlik standartlari korunmali.",
        },
        "Otel Atmosferi & Misafir Profili": {
            "OLUMSUZ": "Gurultu ve kalabalik yonetimi iyilestirilmeli, misafir profili dengelemeli.",
            "OLUMLU": "Sakin ve huzurlu otel atmosferi korunmali.",
        },
        "Personel Davranışı": {
            "OLUMSUZ": "Personel iletisim ve hizmet kalitesi egitimi verilmeli.",
            "OLUMLU": "Personel motivasyonu ve guler yuzlu hizmet korunmali.",
        },
    }
    dept_actions = suggestions.get(department, {
        "OLUMSUZ": "Sikayet degerlendirilmeli ve aksiyon plani olusturulmali.",
        "OLUMLU": "Olumlu geri bildirim icin tesekkur edilmeli.",
    })
    return dept_actions.get(sentiment_label, "Degerlendirme yapilmali.")


def analyze_batch(text: str) -> dict:
    aspects = analyze_text(text)
    if not aspects:
        return {"clauses": [], "summary": {}}

    scores = [a["sentiment_score"] for a in aspects]
    avg_score = sum(scores) / len(scores) if scores else 0

    departments = list(set(a["department"] for a in aspects))
    has_critical = any(a["priority"] == "KRITIK" for a in aspects)
    critical_count = sum(1 for a in aspects if a["priority"] == "KRITIK")

    return {
        "clauses": aspects,
        "summary": {
            "clause_count": len(aspects),
            "avg_sentiment": round(avg_score, 2),
            "overall_sentiment": "OLUMLU" if avg_score > 0.1 else "OLUMSUZ" if avg_score < -0.1 else "NOTR",
            "departments": departments,
            "critical_count": critical_count,
        },
    }


# ---------------------------------------------------------------------------
# Clause ML models — TF-IDF + LogReg (fallback) and Sentence-Transformer + MLP
# ---------------------------------------------------------------------------

_clause_model = None
_clause_vec = None
_clause_labels = None
_emb_model = None
_emb_clf = None
_emb_labels = None
_emb_sbert = None


def _load_clause_ml():
    global _clause_model, _clause_vec, _clause_labels
    if _clause_model is not None:
        return
    import joblib

    sim_dir = Path(__file__).resolve().parent.parent.parent.parent / "simulation"
    model_path = sim_dir / "clause_model.joblib"
    vec_path = sim_dir / "clause_vectorizer.joblib"
    if not model_path.exists() or not vec_path.exists():
        _clause_model = False
        return
    _clause_model = joblib.load(str(model_path))
    _clause_vec = joblib.load(str(vec_path))
    _clause_labels = _clause_model.classes_.tolist()


def _load_emb_ml():
    global _emb_model, _emb_clf, _emb_labels, _emb_sbert
    if _emb_model is not None:
        return
    _emb_model = False  # BERTurk handles classification; skip SentenceTransformer download


def _clause_ml_predict(text: str) -> tuple[str | None, float]:
    """Return (predicted_department, probability).
    Uses BOTH embedding and TF-IDF models, returns the one with highest probability.
    """
    best_dept, best_prob = None, 0.0

    # Try embedding model (multilingual, good for English)
    _load_emb_ml()
    if _emb_model and _emb_sbert and _emb_clf is not None:
        try:
            emb = _emb_sbert.encode([str(text or "")], show_progress_bar=False, batch_size=1)
            probs = _emb_clf.predict_proba(emb)[0]
            idx = int(probs.argmax())
            if probs[idx] > best_prob:
                best_dept, best_prob = _emb_labels[idx], float(probs[idx])
        except Exception:
            pass

    # Try TF-IDF model (good for Turkish)
    _load_clause_ml()
    if _clause_model is not False and _clause_model is not None:
        try:
            cleaned = re.sub(r"[^\w\sçğıöşüÇĞİÖŞÜ]", " ", str(text or "").lower())
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            vec = _clause_vec.transform([cleaned])
            probs = _clause_model.predict_proba(vec)[0]
            idx = int(probs.argmax())
            if probs[idx] > best_prob:
                best_dept, best_prob = _clause_labels[idx], float(probs[idx])
        except Exception:
            pass

    return best_dept, best_prob
