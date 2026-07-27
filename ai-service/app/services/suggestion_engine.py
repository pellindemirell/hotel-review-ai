"""
Bağlam odaklı departman aksiyon önerisi motoru.
Metin, kategori, duygu ve alt kalıplara göre spesifik Türkçe öneri üretir.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from app.services.turkish_nlp_utils import (
    CAT_CLEANING,
    CAT_FINANCE,
    CAT_FOOD,
    CAT_OTHER,
    CAT_RECEPTION,
    CAT_SPA,
    CAT_STAFF,
    CAT_TECH,
    normalize_turkish,
    split_review_clauses,
)


@dataclass
class SuggestionContext:
    category: str
    text: str
    keywords: list[str] = field(default_factory=list)
    sentiment: str = "Neutral"
    is_mixed: bool = False
    secondary_category: Optional[str] = None
    is_humor: bool = False
    is_manipulation: bool = False


def _ascii(text: str) -> str:
    return (
        text.replace("ş", "s").replace("ı", "i").replace("ö", "o")
        .replace("ü", "u").replace("ğ", "g").replace("ç", "c").replace("î", "i")
    )


def _has_any(cleaned: str, patterns: tuple[str, ...]) -> bool:
    asc = _ascii(cleaned)
    return any(p in cleaned or p in asc for p in patterns)


@dataclass
class _SubRule:
    patterns: tuple[str, ...]
    suggestion: str
    weight: int = 1
    sentiment_hint: Optional[str] = None  # Negative, Positive, or None


def _pick_best(rules: list[_SubRule], cleaned: str, sentiment: str) -> Optional[str]:
    asc = _ascii(cleaned)
    scored: list[tuple[int, str]] = []
    for rule in rules:
        match_count = sum(1 for p in rule.patterns if p in cleaned or p in asc)
        if match_count == 0:
            continue
        bonus = 0
        if rule.sentiment_hint == sentiment:
            bonus = 3
        elif rule.sentiment_hint is None:
            bonus = 1
        scored.append((rule.weight + match_count * 4 + bonus, rule.suggestion))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


# ---------------------------------------------------------------------------
# Alt kalıp kuralları (kategori bazlı)
# ---------------------------------------------------------------------------
FOOD_RULES = [
    _SubRule(
        ("kötü", "berbat", "lezzetsiz", "tatsız", "iğrenç", "bayılac", "bayilac", "ölecek", "olecek", "kötüydü", "kotuydu", "iğrençti"),
        "Mutfak şefi acilen menü tadım ve lezzet kalite kontrolü yapmalı; tarif/reçete standardı ve malzeme tazeliği gözden geçirilmeli, gerekirse menü revizyonu planlanmalı.",
        weight=10,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("sıra", "sira", "kuyruk", "dakika bek", "bekleniyor", "alınamıyor", "alinamiyor", "15 20", "30-45"),
        "F&B/bar operasyonu yoğun saatlerde servis noktalarını ve personel sayısını artırmalı; içecek kuyruk süresi ölçülüp 10 dk altına indirilecek aksiyon planı uygulanmalı.",
        weight=12,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("tekila", "çeşit alkol", "cesit alkol", "belli bar", "konsept", "7/24", "alkol"),
        "F&B müdürü bar konseptini ve alkol çeşitliliğini gözden geçirmeli; popüler içecekler birden fazla noktada ve daha geniş saat aralığında sunulmalı.",
        weight=11,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("soğuk", "soguk", "bayat", "ılık", "isınmamış", "soguktu"),
        "Mutfak ve servis ekibi yemek çıkış sıcaklığı ile büfe/isıtıcı süreçlerini kontrol etmeli; tabaklar servis öncesi sıcaklık testinden geçirilmeli.",
        weight=8,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("çeşit", "cesit", "monoton", "eintönig", "az çeşit", "yetersiz çeşit"),
        "F&B müdürü kahvaltı/akşam büfe menü çeşitliliğini artırmalı; haftalık rotasyon menüsü hazırlanmalı.",
        weight=7,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("porsiyon", "az porsiyon", "küçük porsiyon"),
        "Mutfak şefi porsiyon standartlarını denetlemeli; servis personeline porsiyon kontrolü hatırlatılmalı.",
        weight=7,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("servis yavaş", "geç geldi", "bekledik", "servis hız"),
        "Restoran müdürü servis akışını gözden geçirmeli; yoğun saatlerde garson sayısı ve sipariş takip süreci optimize edilmeli.",
        weight=6,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("lezzetli", "harika", "bayıldım", "bayildim", "mükemmel", "nefis", "enfes"),
        "Olumlu geri bildirim mutfak şefi ve ilgili istasyon ekibiyle paylaşılmalı; başarılı tarifler menüde korunmalı.",
        weight=5,
        sentiment_hint="Positive",
    ),
]

CLEANING_RULES = [
    _SubRule(
        ("havlu", "banyo", "çarşaf", "carsaf", "leke", "lekeli", "havlular"),
        "Housekeeping banyo/havlu kontrol listesini güncellemeli; oda çıkış ve giriş öncesi havlu/çarşaf leke kontrolü zorunlu hale getirilmeli.",
        weight=10,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("koku", "kokuyordu", "koktu", "pis koku"),
        "Kat hizmetleri oda havalandırma ve koku kaynağı (banyo/sifon/klima filtresi) kontrol protokolü uygulamalı.",
        weight=9,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("toz", "tozlu", "toz her"),
        "Housekeeping detaylı toz alma ve yüzey silme prosedürü uygulamalı; oda denetiminde toz kontrolü eklenmeli.",
        weight=8,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("kirli", "pis", "temizlenmedi", "dağınık", "yapılmamış"),
        "Kat hizmetleri oda temizlik checklistini sıkılaştırmalı; eksik temizlik tespit edilen odalar için süpervizör denetimi yapılmalı.",
        weight=7,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("tertemiz", "temiz", "pırıl", "hijyenik"),
        "Olumlu temizlik geri bildirimi housekeeping ekibiyle paylaşılmalı; uygulanan standart korunmalı.",
        weight=5,
        sentiment_hint="Positive",
    ),
]

TECH_RULES = [
    _SubRule(
        ("klima", "termostat", "klimasi", "kliması"),
        "Teknik servis ilgili odanın klima/termostat ayarını kontrol etmeli; sıcaklık sensörü ve filtre bakımı için acil iş emri açılmalı.",
        weight=10,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("klima", "soğuk", "soguk", "sıcak", "ısınm", "isınm"),
        "Teknik servis klima üfleme/sıcaklık ayarını denetlemeli; termostat kalibrasyonu ve oda sıcaklık dengesi sağlanmalı.",
        weight=9,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("wifi", "wi-fi", "internet", "bağlantı", "baglanti"),
        "IT/teknik ekip ilgili bölgedeki Wi-Fi/internet erişim noktası ve bant genişliğini test etmeli; gerekirse access point yenilenmeli.",
        weight=11,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("tv", "televizyon", "kumanda", "televizyonu"),
        "Teknik servis odadaki TV/kumanda ve kablo bağlantılarını kontrol etmeli; arızalı ekipman değiştirilmeli.",
        weight=11,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("asansör", "asansor", "elevator"),
        "Teknik servis asansör bakım ekibini bilgilendirmeli; arıza kaydı acilen kapatılmalı.",
        weight=8,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("priz", "lamba", "kilit", "sızıntı", "bozuk", "arızalı"),
        "Teknik servis ilgili odaya bakım iş emri açmalı; arıza giderilene kadar misafir bilgilendirilmeli.",
        weight=7,
        sentiment_hint="Negative",
    ),
]

SPA_RULES = [
    _SubRule(
        ("şezlong", "sezlong", "lounger"),
        "Havuz operasyonu şezlong kapasitesini ve yerleştirme planını artırmalı; yoğun saatlerde lounger kuyruğunu azaltacak ek alan/rotasyon uygulanmalı.",
        weight=12,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("klor", "klorlu", "göz yak", "goz yak", "su kalite", "havuz kirli", "havuz hijyen", "pH"),
        "Spa/havuz ekibi su kalitesi ve hijyen ölçümlerini sıklaştırmalı; klor/pH değerleri günlük raporlanmalı.",
        weight=11,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("masaj", "spa", "sauna", "wellness", "hamam"),
        "Spa müdürü ilgili hizmet kalitesini değerlendirmeli; olumsuzsa terapist/hizmet protokolü gözden geçirilmeli.",
        weight=7,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("beğendik", "begendik", "beğendim", "harika", "temiz"),
        "Havuz/spa hakkındaki olumlu geri bildirim ilgili ekiple paylaşılmalı; mevcut hijyen ve hizmet standardı korunmalı.",
        weight=6,
        sentiment_hint="Positive",
    ),
    _SubRule(
        ("animasyon", "aktivite", "etkinlik", "masa tenisi", "kaldırılmış", "kaldirilmis"),
        "Animasyon/aktivite ekibi iptal edilen programları dengelemek için alternatif etkinlik (masa tenisi vb.) planlamalı; bayram yoğunluğunda program sürekliliği sağlanmalı.",
        weight=10,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("gürültü", "gurultu", "ses"),
        "Aktivite ekibi ses seviyesi ve program saatlerini gözden geçirmeli; dinlenme alanlarına yakın aktiviteler sınırlandırılmalı.",
        weight=7,
        sentiment_hint="Negative",
    ),
]

STAFF_RULES = [
    _SubRule(
        ("türkçe", "turkce", "dil bilmiyor", "bile bilmiyor"),
        "İnsan kaynakları ve ilgili birim müdürü misafir temas noktalarında Türkçe yeterliliğini denetlemeli; dil eğitimi veya yerli personel planlaması yapılmalı.",
        weight=12,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("garson", "servis personeli", "barmen"),
        "Restoran müdürü ilgili garson/servis personelini tespit etmeli; müşteri iletişimi ve servis nezaketi eğitimi planlanmalı.",
        weight=10,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("resepsiyonist", "resepsiyon", "check-in", "check-out", "giriş"),
        "Ön büro müdürü resepsiyon ekibine misafir karşılama ve bekleme süresi protokolü eğitimi verilmeli.",
        weight=9,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("kaba", "saygısız", "ilgisiz", "bağırdı", "küfür"),
        "İnsan kaynakları ve departman müdürü olay kaydı oluşturmalı; personel görüşmesi, iletişim eğitimi ve uyarı/hatırlatma süreci başlatılmalı.",
        weight=8,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("güler yüzlü", "guler yuzlu", "kibar", "profesyonel", "yardımsever"),
        "Olumlu personel geri bildirimi ilgili çalışana ve departman müdürüne iletilmeli; takdir notu eklenmeli.",
        weight=5,
        sentiment_hint="Positive",
    ),
]

RECEPTION_RULES = [
    _SubRule(
        ("bekle", "bekleme", "bekletti", "yavaş", "gecikme", "sırada"),
        "Ön büro müdürü yoğunluk saatlerinde personel planlamasını gözden geçirmeli; bekleme süresi takip panosu kurulmalı.",
        weight=9,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("hızlı", "kolay", "sorunsuz"),
        "Olumlu check-in/check-out deneyimi ön büro ekibiyle paylaşılmalı; uygulanan süreç standart hale getirilmeli.",
        weight=5,
        sentiment_hint="Positive",
    ),
]

FINANCE_RULES = [
    _SubRule(
        ("fatura", "depozito", "iade", "ekstra", "ücret", "ucret", "pahalı", "fahiş"),
        "Muhasebe/finans departmanı fatura ve ekstra ücret kalemlerini misafir kaydıyla karşılaştırmalı; iade/ düzeltme süreci başlatılmalı.",
        weight=9,
        sentiment_hint="Negative",
    ),
]

CATEGORY_RULES: dict[str, list[_SubRule]] = {
    CAT_FOOD: FOOD_RULES,
    CAT_CLEANING: CLEANING_RULES,
    CAT_TECH: TECH_RULES,
    CAT_STAFF: STAFF_RULES,
    CAT_SPA: SPA_RULES,
    CAT_RECEPTION: RECEPTION_RULES,
    CAT_FINANCE: FINANCE_RULES,
}


def _apply_lexicon_suggestion_rules() -> None:
    """Leksikondaki ek alt kalıp kurallarını mevcut kurallara birleştir."""
    try:
        from app.services.lexicon_loader import get_suggestion_rules_from_lexicon

        lex_rules = get_suggestion_rules_from_lexicon()
        for cat, rules in lex_rules.items():
            converted: list[_SubRule] = []
            for r in rules:
                patterns = tuple(r.get("patterns", []))
                if not patterns:
                    continue
                hint = r.get("sentiment")
                if hint == "Negative":
                    hint = "Negative"
                elif hint == "Positive":
                    hint = "Positive"
                else:
                    hint = None
                converted.append(_SubRule(
                    patterns=patterns,
                    suggestion=r.get("suggestion", ""),
                    weight=int(r.get("weight", 5)),
                    sentiment_hint=hint,
                ))
            if cat not in CATEGORY_RULES:
                CATEGORY_RULES[cat] = converted
                continue
            existing_sugs = {rule.suggestion for rule in CATEGORY_RULES[cat]}
            for rule in converted:
                if rule.suggestion and rule.suggestion not in existing_sugs:
                    CATEGORY_RULES[cat].append(rule)
                    existing_sugs.add(rule.suggestion)
    except Exception:
        logger.warning("Failed to apply lexicon suggestion rules", exc_info=True)


_apply_lexicon_suggestion_rules()

CATEGORY_DEFAULTS: dict[str, str] = {
    CAT_FOOD: "F&B müdürü geri bildirimi değerlendirmeli; mutfak ve servis süreçlerinde iyileştirme planı oluşturulmalı.",
    CAT_CLEANING: "Kat hizmetleri müdürü oda temizlik standartlarını gözden geçirmeli; denetim sıklığı artırılmalı.",
    CAT_TECH: "Teknik servis müdürü arıza kaydını önceliklendirmeli; ilgili oda/bölge kontrol edilmeli.",
    CAT_STAFF: "İlgili departman müdürü personel davranışını incelemeli; gerekirse eğitim veya uyarı süreci başlatılmalı.",
    CAT_SPA: "Spa/wellness müdürü hizmet ve tesis geri bildirimini değerlendirmeli; gerekli düzeltici aksiyon planlanmalı.",
    CAT_RECEPTION: "Ön büro müdürü misafir kabul süreçlerini gözden geçirmeli; bekleme ve iletişim standartları güncellenmeli.",
    CAT_FINANCE: "Finans departmanı fatura/ücret mutabakatını kontrol etmeli; misafirle doğrudan iletişim kurulmalı.",
    CAT_OTHER: "Geri bildirim müşteri ilişkileri tarafından sınıflandırılıp ilgili departmana yönlendirilmeli.",
}


# Cross-category dominant complaint patterns — win over wrong primary category
_DOMINANT_OPS_RULES: list[_SubRule] = [
    _SubRule(
        ("sıra", "sira", "kuyruk", "dakika", "bekleniyor", "alınamıyor", "icecek", "içecek"),
        "Operasyon ve F&B yönetimi bar/restoran servis noktalarını çoğaltmalı; içecek kuyruk süreleri ölçülüp yoğun saat planı güncellenmeli.",
        weight=20,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("şezlong", "sezlong"),
        "Havuz operasyonu şezlong kapasitesini artırmalı; lounger kuyruğunu azaltacak yerleşim ve rotasyon planı uygulanmalı.",
        weight=18,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("tekila", "belli bar", "çeşit alkol", "cesit alkol", "7/24"),
        "F&B müdürü bar konsepti ve alkol çeşitliliğini genişletmeli; popüler ürünler daha fazla noktada ve daha uzun saat sunulmalı.",
        weight=17,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("yalıtım", "yalitim", "yan oda", "ses geç"),
        "Teknik/kat hizmetleri oda ses yalıtımı ve gürültü şikayetlerini incelemeli; problemli odalar için sessiz oda tahsisi veya yapısal iyileştirme planlanmalı.",
        weight=16,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("wifi", "wi-fi", "internet", "bağlanılamıyor", "baglanilamiyor"),
        "IT/teknik ekip Wi-Fi ve internet erişim noktası ile kaplama alanını test etmeli; bağlantı kopmaları için access point kapasitesi artırılmalı.",
        weight=16,
        sentiment_hint="Negative",
    ),
    _SubRule(
        ("çarçur", "carcur", "para çöp", "para cop"),
        "Müşteri ilişkileri değer algısı şikayetini departman bazlı kök nedenlerle (kuyruk, bar, mesafe) ilişkilendirip aksiyon takibi açmalı.",
        weight=14,
        sentiment_hint="Negative",
    ),
]


def _resolve_category_key(category: str) -> str:
    """Kategori adını bilinen sabitlerle eşleştir."""
    cat_lower = category.lower()
    mapping = [
        ("yiyecek", CAT_FOOD), ("yemek", CAT_FOOD),
        ("kat hizmet", CAT_CLEANING), ("temizlik", CAT_CLEANING),
        ("teknik", CAT_TECH), ("maintenance", CAT_TECH),
        ("personel", CAT_STAFF), ("iletişim", CAT_STAFF),
        ("spa", CAT_SPA), ("wellness", CAT_SPA), ("aktivite", CAT_SPA), ("havuz", CAT_SPA),
        ("resepsiyon", CAT_RECEPTION), ("ön büro", CAT_RECEPTION),
        ("muhasebe", CAT_FINANCE), ("finans", CAT_FINANCE),
        ("oda", CAT_OTHER), ("genel", CAT_OTHER),
    ]
    for needle, key in mapping:
        if needle in cat_lower:
            return key
    return category if category in CATEGORY_DEFAULTS else CAT_OTHER


def _suggest_for_text(
    category: str,
    text: str,
    keywords: list[str],
    sentiment: str,
) -> str:
    cleaned = normalize_turkish(text)
    kw_blob = " ".join(keywords).lower()
    combined = f"{cleaned} {kw_blob}"

    # Dominant complaint patterns beat a mis-assigned primary category (e.g. Spa+chlorine)
    dominant = _pick_best(_DOMINANT_OPS_RULES, combined, sentiment)
    if dominant and sentiment != "Positive":
        # Require at least one strong ops cue in text (not only keywords)
        return dominant

    cat_key = _resolve_category_key(category)
    rules = CATEGORY_RULES.get(cat_key, [])
    result = _pick_best(rules, combined, sentiment)
    if result:
        # Block false chlorine action when no water-quality cue exists
        if "klor" in result.lower() or "pH" in result or "ph değer" in result.lower():
            if not _has_any(combined, ("klor", "ph", "su kalite", "göz yak", "goz yak", "havuz kirli")):
                result = None
        if result:
            return result

    if sentiment == "Positive":
        pos = _pick_best(rules, combined, "Positive")
        if pos:
            return pos
        return "Başarılı hizmet yaklaşımı ve yüksek memnuniyet standartları korunmalı; emeği geçen ekibe teşekkür iletilmeli."

    return CATEGORY_DEFAULTS.get(cat_key, CATEGORY_DEFAULTS[CAT_OTHER])


def _mixed_suggestion(ctx: SuggestionContext) -> str:
    clauses = split_review_clauses(ctx.text)
    neg_text = clauses[0] if clauses else ctx.text
    pos_text = clauses[1] if len(clauses) > 1 else ""

    primary = _suggest_for_text(ctx.category, neg_text, ctx.keywords, "Negative")
    secondary_cat = ctx.secondary_category or CAT_OTHER
    secondary = _suggest_for_text(secondary_cat, pos_text, [], "Positive") if pos_text else ""

    if secondary:
        return f"Şikayet için: {primary} Olumlu not: {secondary}"
    return primary


def build_suggestion(ctx: SuggestionContext) -> str:
    if ctx.is_humor:
        return "Mizahi/ironik yorum tespit edildi; ciddi departman aksiyonu gerekmez, genel memnuniyet takibi yeterlidir."

    if ctx.is_manipulation:
        return (
            "Sahte puan/manipülasyon şüphesi: Gerçek şikayet içeriği ayrıştırılmalı; "
            "ilgili departman müdürüne metin bazlı inceleme iletilmeli, puan güvenilirliği not edilmeli."
        )

    if ctx.is_mixed:
        return _mixed_suggestion(ctx)

    return _suggest_for_text(ctx.category, ctx.text, ctx.keywords, ctx.sentiment)
