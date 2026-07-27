"""
Merkezi Türkçe otel yorumu NLP yardımcıları.
Sentiment, kategori, anahtar kelime ve çelişki tespiti için paylaşılan sözlükler ve fonksiyonlar.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kategori sabitleri (ML model + kural motoru ile uyumlu)
# ---------------------------------------------------------------------------
CAT_CLEANING = "Kat Hizmetleri & Temizlik"
CAT_FOOD = "Yiyecek & İçecek & Yemekler"
CAT_RECEPTION = "Resepsiyon & Ön Büro"
CAT_TECH = "Teknik Servis (Maintenance)"
CAT_SPA = "Spa & Wellness / Aktivite"
CAT_GROUNDS = "Çevre, Güvenlik & Ulaşım"
CAT_STAFF = "Personel Davranışı & İletişim"
CAT_OTHER = "Diğer"

# Ontology-aligned aliases
CAT_HOUSEKEEPING = CAT_CLEANING
CAT_FRONT_OFFICE = CAT_RECEPTION
CAT_LEISURE = CAT_SPA
CAT_ATMOSPHERE = "Otel Atmosferi & Misafir Profili"
CAT_FINANCE = "Muhasebe & Finans"

ALL_CATEGORIES = [
    CAT_CLEANING, CAT_FOOD, CAT_RECEPTION, CAT_TECH,
    CAT_SPA, CAT_FINANCE, CAT_STAFF, CAT_OTHER,
]

# ---------------------------------------------------------------------------
# Duygu sözlükleri (100+ kelime / ifade)
# ---------------------------------------------------------------------------
POSITIVE_WORDS: set[str] = {
    "harika", "mükemmel", "muhteşem", "süper", "fantastik", "şahane", "harikulade", "enfes", "nefis",
    # normalized (ASCII) duplicates for matching after normalize_turkish()
    "mukemmel", "muhtesem", "super", "sahane", "harikulade",
    "güzel", "güzeldi", "harikaydı", "mükemmeldi", "iyiydi", "başarılı", "kusursuz", "müthiş", "olağanüstü",
    # normalized
    "guzel", "guzeldi", "harikaydi", "mukemmeldi", "iyiydi", "basarili", "kusursuz", "muthis", "olaganustu",
    "temiz", "tertemiz", "pırıl", "hijyenik", "mis", "ferah", "konforlu", "rahat", "düzenli", "özenli",
    # normalized
    "piril", "hijyenik", "konforlu", "duzenli", "ozenli",
    "leziz", "lezzetli", "lezzet", "taptaze", "taze", "sıcak", "doyurucu", "bol", "çeşitli", "zengin",
    # normalized
    "sicak", "doyurucu", "cesitli",
    "memnun", "mutlu", "keyifli", "huzurlu", "dinlendirici", "eğlenceli", "güvenli", "sessiz",
    # normalized
    "keyifli", "huzurlu", "dinlendirici", "eglenceli", "guvenli",
    "kibar", "nazik", "ilgili", "yardımsever", "samimi", "profesyonel", "güler", "sıcakkanlı",
    # normalized + staff keywords
    "yardimsever", "yardimseverdi", "guleryuzlu", "guleryuz", "guler", "sicakkanli",
    "profesyonel", "profesyoneldi", "ilgili", "ilgilendi", "kibar", "nazik", "samimi",
    "hızlı", "çabuk", "pratik", "kolay", "sorunsuz", "akıcı",
    # normalized
    "hizli", "cabuk", "pratik", "sorunsuz", "akici",
    "tavsiye", "öneririm", "öneriyorum", "gelmelisiniz", "gelin", "tekrar", "döneceğiz", "döneriz",
    # normalized
    "oneririm", "oneriyorum", "gelmelisiniz", "donecegiz", "doneriz",
    "bayıldım", "bayıldık", "bayıl", "beğendim", "beğendik", "sevdik", "sevdim", "hayran",
    # normalized
    "bayildim", "bayildik", "bayil", "begenim", "begenik", "sevdik", "sevdim", "hayran",
    "efsane", "müthiş", "muthis", "helal", "bombası", "bombasi",
    # normalized
    "muthis",
    "teşekkür", "teşekkürler", "bravo", "aferin", "ellerinize", "sağlık",
    # normalized
    "tesekkur", "tesekkurler", "saglik",
    "iyi", "idare", "fena", "değil", "herşey", "hersey", "hepsi", "genel", "mükemmeldi",
    # normalized
    "degil", "hersey", "mukemmeldi",
    "kaliteli", "modern", "yeni", "lüks", "şık", "dekor", "manzara", "muhteşemdi",
    # normalized
    "luks", "sik", "manzara", "muhtesemdi",
    "kahvaltı", "lezzetliydi", "harikaydı", "enfesdi", "nefisti",
    # normalized
    "kahvalti", "lezzetliydi", "harikaydi", "enfesdi", "nefisti",
    # extra positive staff keywords
    "yardim", "yardimci", "yardimciydi", "destek", "destekledi",
    "guleryuzlu", "guleryuz", "guler",
    "beraber", "cozdu", "cozumu", "halletti", "halli",
    "memnuniyet", "profesyonelce",
    # specific positive words
    "lekesiz", "mis", "mis gibi",
}

NEGATIVE_WORDS: set[str] = {
    "kötü", "berbat", "rezalet", "felaket", "iğrenç", "tiksin", "dehşet", "skandal", "utanç",
    "kirli", "pis", "lekeli", "kokulu", "koku", "küflü", "tozlu", "saçlı", "hijyensiz", "iğrenç",
    "lezzetsiz", "tatsız", "bayat", "soğuk", "çiğ", "yanmış", "az", "yetersiz", "kötüydü",
    "yavaş", "gecikme", "bekledik", "bekleme", "gecikti", "uzun", "süründü",
    "kaba", "saygısız", "ilgisiz", "umursamaz", "kılıksız", "agresif", "bağırdı", "küfür",
    "bozuk", "arızalı", "çalışmıyor", "bozuldu", "kırık", "sızıntı", "ısınmıyor", "soğuk su",
    "pahalı", "fahiş", "dolandırıcı", "gizli", "fatura", "hata", "yanlış",
    "gürültülü", "gürültü", "kalabalık", "dar", "küçük", "eski", "yıpranmış", "yırtık", "sökük",
    "haşere", "böcek", "sivrisinek", "fare", "hamam", "sigara", "duman",
    "pişman", "asla", "tavsiye", "hiç", "beğenmedim", "gelmem", "gitmeyin", "kaçın", "uzak",
    "çöp", "cop", "fiyasko", "hiç olmaz", "hic olmaz",
    "hayal", "kırıklığı", "şok", "mahvetti", "mahvoldu", "berbat", "rezil", "korkunç", "dehşet",
    "memnun", "değil", "kalmadık", "kalmadım", "şikayet", "problem", "sorun", "eksik",
    "kirliydi", "soğuktu", "bozuktu", "pahalıydı", "kabadı", "yavaştı", "berbatı",
    "yapılmamış", "dağınık", "gelmiyor", "yoktu", "yok", "kalabalık", "fahiş", "edilmedi",
    "uzun", "gecikti", "alamadık", "alamadım",
    "kalitesiz", "yetersiz", "zayıf", "zayif", "bulunmuyor", "bulamıyor",
    "bulamiyor", "alınamıyor", "alinamiyor", "getirilmedi", "getirmediler", "alakasız",
    "alakasiz", "kaldırılmış", "kaldirilmis", "kapalı", "kapali", "ihtiyacı", "ihtiyaci",
    "kısıtlı", "kisitli", "azdı", "azdi", "rahatsız", "rahatsiz", "gıcık", "rahatsızlık",
    "rahatsizlik", "tıkalı", "tikali", "tıkanık", "tikanik", "gitmiyor", "ılık",
    "soğutmuyor", "sogutmuyor", "soğutmuyorlar", "sogutmuyorlar", "soğutma", "overbooking",
    "baskı", "baski",
}

POSITIVE_PHRASES: list[str] = [
    "mis gibi", "mis gibi kokuyor", "mis gibi kokuyordu",
    "çok iyi", "çok güzel", "çok güzeldi", "herşey güzel", "herşey çok güzel", "hersey güzel",
    "hersey çok güzel", "her şey güzeldi", "herşey çok güzeldi", "herşey mükemmel", "herşey harika",
    "kesin gel", "mutlaka gel", "tavsiye ederim", "tavsiye ediyorum", "kesinlikle gel", "gelmelisiniz",
    "kesin gelmelisiniz", "mutlaka gelin", "bayıldım", "bayıldık", "harika bir", "mükemmel bir",
    "mükemmel tatil", "harika tatil", "genel olarak güzel", "herşey iyiydi", "herşey güzeldi",
    "tekrar gel", "tekrar geleceğiz", "memnun kaldık", "çok memnun", "çok beğendik",
    "domates çorbası", "kabak dolması", "açık büfe", "kahvaltı harika", "yemek harika",
    "hemen getirdi", "hemen getirdiler", "hemen getirdiler.",
]

NEGATIVE_PHRASES: list[str] = [
    "asla tavsiye", "hiç beğenmedim", "memnun kalmadık", "memnun kalmadım", "pişman olduk",
    "pişman oldum", "bir daha gelmem", "asla gelmeyin", "gitmeyin", "kaçının", "uzak durun",
    "hayal kırıklığı", "para tuzağı", "zaman kaybı", "vakit kaybı", "rezalet bir",
    "berbat bir", "korkunç bir", "iğrenç bir", "felaket bir",
    "geç geldi", "gec geldi", "housekeeping geç",
    "su kesildi", "sular kesildi", "su kesintisi",
    "daha iyi olabilir", "arttırılmalı", "arttirilmali", "olmaması negatif",
    "kalitesiz", "yetersiz", "zayıf", "zayif", "bulunmuyor", "bulamıyorsunuz",
    "getirilmedi", "getirmediler", "alakasız", "alakasiz", "kaldırılmış",
    "bitiyor", "cikmadi", "çıkmadı", "eksik", "ogrenmeleri gerekiyor", "öğrenmeleri gerekiyor",
    "o ne diye", "bırakılmamış", "birakilmamis", "temizlenmedi", "yapılmamış",
    "parasını çarçur", "parasini carcur", "çarçur etmek", "carcur etmek",
    "türkçe bile bilmiyor", "turkce bile bilmiyor", "türkçe bilmiyor",
    "diye tuttuk", "sıra bekleniyor", "sira bekleniyor", "alınamıyor", "alinamiyor",
    "güzel bir yanı yok", "guzel bir yani yok", "ses yalıtımı çok kötü",
    "bağlanılamıyor", "baglanilamiyor",
    "isterseniz güzel", "isterseniz guzel", "metre yürümek", "koşmak isterseniz",
    "bahşiş baskısı", "bahsis baskisi", "bahşiş beklentisi", "bahsis beklentisi",
    "bahşiş için sürekli baskı", "bahsis icin surekli baski", "kartı açmadı", "kart açmadı",
    "kartı okumadı", "kart okumadı", "kart çalışmadı", "kart çalışmıyor",
    "kartı çalışmadı", "kartı çalışmıyor", "ek ücret", "ekstra ücret", "ilave ücret",
    "ücret istediler", "para istediler", "başka otele yönlendirildik", "kapıyı çalmadan",
    "kapı çalmadan", "kapi calmadan", "çalmadan", "uyuyamadım", "uyuyamadık",
    "ses yapıyor", "ses yapıyordu", "kesildi", "kesilmesi", "kesinti", "geç devreye",
    "gec devreye", "ne kadar yer kaplayabilir",
]

STRONG_POSITIVE: set[str] = {
    "bayıldım", "bayıldık", "bayıl", "muhteşem", "mükemmel", "harika", "süper",
    "güzeldi", "harikaydı", "mükemmeldi", "enfes", "nefis", "tertemiz", "kusursuz",
    "eglenceliydi", "eğlenceliydi", "eglenceli", "eğlenceli", "yardımcı", "yardimci",
    # normalized + staff
    "guleryuzlu", "guleryuz", "yardimsever", "yardimseverdi",
    "profesyonel", "profesyoneldi", "ilgili", "ilgilendi",
    "mukemmel", "muhtesem", "super", "guzel", "guzeldi",
    "harikaydi", "mukemmeldi", "tertemiz",
    # atmosphere / experience keywords
    "basarili", "başarılı", "sicak", "sıcak", "davetkar", "davetkardi", "davetkâr",
    "uygun", "uygundu", "huzurlu", "huzur", "dinlendirici",
    "lekesiz", "lezzetli", "lezzetliydi",
}

STRONG_NEGATIVE: set[str] = {
    "berbat", "rezalet", "iğrenç", "felaket", "asla tavsiye", "hiç beğenmedim",
    "pişman", "korkunç", "dehşet", "skandal", "çarçur", "carcur",
}

SARCASM_INDICATORS: list[str] = [
    "öne çıksın", "üste çıksın", "görünsün diye", "asla tavsiye", "hiç beğenmedim",
    "5 yıldız vermek zorundaydım", "puan vermek zorunda", "yorum yazmak zorunda",
    "metre yürümek", "metre yurumek", "koşmak isterseniz güzel", "kosmak isterseniz guzel",
    "çarçur etmek isteyen", "carcur etmek isteyen",
]

# Sahte olumlu puan / görünürlük manipülasyonu — yüksek puan + olumsuz metin
MANIPULATION_PATTERNS: list[str] = [
    "öne çıksın", "öne ciksin", "üste çıksın", "üste ciksin",
    "görünsün diye", "gorunsun diye", "görünsün", "gorunsun",
    "yorumum görünsün", "yorum görünsün", "yorumum gorunsun",
    "5 yıldız veriyorum", "5 yildiz veriyorum", "beş yıldız veriyorum",
    "yıldız veriyorum", "yildiz veriyorum", "5 yıldız vermek zorunda",
    "yıldız vermek zorunda", "puan vermek zorunda", "yorum yazmak zorunda",
    "5 yıldız vermek zorundaydım", "puan vermek zorundaydım",
    "yorum yazmak zorundaydım", "5 yıldız verdim", "beş yıldız verdim",
]

# Mizah / şaka — olumsuz ifade + şaka işareti → ciddi şikayet DEĞİL (manipülasyondan ayrı)
JOKE_MARKERS: list[str] = [
    "(saka)", "(şaka)", "saka)", "şaka)",
    "saka yap", "şaka yap", "saka yapiyorum", "şaka yapıyorum",
    "espri", "ironik", "troll", "saka ya", "şaka ya",
    "saka tabii", "şaka tabii", "şaka bir yana", "saka bir yana",
    "şaka bir yana", "tabii ki saka", "tabii ki şaka",
]

JOKE_CONTEXT_MARKERS: list[str] = [
    "yok artık", "yok artik", "inşallah", "insallah",
]

# Olumsuz abartı / hiperbol — "bayıldım" (olumlu) DEĞİL, "bayılacaktım" (kötülükten bayılma)
NEGATIVE_HYPERBOLE: list[str] = [
    "bayılacaktım", "bayilacaktim", "bayılırım", "bayilirim",
    "bayılacak kadar", "bayilacak kadar", "bayılacak", "bayilacak",
    "ölecektim", "olecektim", "ölecek kadar", "olecek kadar", "ölecek kadar kötü",
    "gebercektim", "geberirim", "geberirdim", "kusacaktım", "kusacak kadar",
    "o kadar kötüydü", "o kadar kotuydu", "o kadar berbat", "o kadar kötü ki",
    "o kadar lezzetsiz", "o kadar igrenc", "o kadar iğrenç",
]

# İfade düzeyinde duygu ağırlıkları (tek kelimeden yüksek öncelik)
PHRASE_SENTIMENT_WEIGHTS: list[tuple[str, float]] = [
    # Olumlu (+)
    ("herşey çok güzeldi", 4.0), ("herşey mükemmel", 3.5), ("çok güzeldi", 3.0),
    ("mükemmel tatil", 3.0), ("harika tatil", 3.0), ("tavsiye ederim", 2.5),
    ("kesinlikle gelin", 2.5), ("bayıldım", 3.0), ("yemek lezzetli", 2.5),
    ("yemek harika", 2.5), ("kahvaltı harika", 2.5), ("oda tertemiz", 2.5),
    ("personel kibar", 2.0), ("garson güler yüzlü", 2.0),
    # Olumsuz (-)
    ("asla tavsiye", -4.0), ("asla gelmeyin", -3.5), ("hiç beğenmedim", -3.5),
    ("pişman olduk", -3.0), ("pişman oldum", -3.0), ("hayal kırıklığı", -3.0),
    ("oda kirli", -3.0), ("yemek soğuk", -3.0), ("yemek berbat", -3.0),
    ("garson kaba", -3.0), ("personel ilgisiz", -3.0), ("klima bozuk", -3.0),
    ("havuz kirli", -3.0), ("fatura hatası", -3.0), ("memnun kalmadık", -3.5),
    ("berbat bir otel", -3.5), ("para tuzağı", -3.0), ("temizlik yapılmamış", -3.0),
    ("5 yıldız veriyorum", -2.0), ("öne çıksın diye", -4.0),
    ("o kadar kötüydü ki", -3.5),     ("bayılacaktım", -3.5), ("ölecek kadar kötü", -4.0),
    ("efsane otel", 3.5), ("otel efsane", 3.5), ("10/10", 4.0), ("fena değil", 2.0),
    ("rezalet la", -3.8), ("berbat la", -3.8), ("çöp gibi", -3.5), ("cehennem gibi", -3.5),
    ("cennet gibi", 3.5), ("kabus gibi", -3.5),
    ("paramız çöp", -3.5), ("paramiz cop", -3.5), ("para çöp oldu", -3.5),
    ("kıyma kalitesi", -2.5), ("kiyma kalitesi", -2.5), ("kalitesi çok düşük", -3.0),
    ("kalitesi cok dusuk", -3.0), ("karışık ve yorucu", -3.0), ("karisik ve yorucu", -3.0),
    ("çatal bıçak bulamad", -2.5), ("catal bicak bulamad", -2.5),
    ("inanılmaz kuyruklar", -3.0), ("inanilmaz kuyruklar", -3.0),
]

# Türkçe mecaz / hyperbolik övgü — kelime kelime analiz kaçırır
POSITIVE_IDIOMS: list[str] = [
    "keyiften ölebilirim", "keyiften öldüm", "keyiften geberirim", "keyiften geçerim",
    "cennet gibi", "rüya gibi", "hayatımın tatili", "hayatimin tatili",
    "bayılıyorum buraya", "buraya bayılıyorum", "burada keyiften",
    "mükemmel bir deneyim", "unutulmaz bir tatil", "her şey harikaydı",
]

# Twitter / sosyal medya / informal (leksikon ile genişler)
TWITTER_SLANG_POSITIVE: list[str] = [
    "efsane", "efsane otel", "otel efsane", "10/10", "fena değil", "helal olsun",
    "on numara", "idare eder", "gayet iyi", "baya iyi", "süper lan", "müthiş lan",
]
TWITTER_SLANG_NEGATIVE: list[str] = [
    "rezalet la", "berbat la", "çöp gibi", "cop gibi", "hiç olmaz", "fiyasko",
    "pişman oldum aga", "gitmeyin la", "berbat harbiden",
]
SHORT_REVIEW_PATTERNS: list[tuple[str, str, float]] = [
    ("otel efsane", "Positive", 3.5), ("rezalet la", "Negative", 3.8),
    ("fena değil", "Positive", 2.2), ("10/10", "Positive", 4.0),
    ("oda pis", "Negative", 3.0), ("yemek berbat", "Negative", 3.5),
    ("klima yok", "Negative", 3.0), ("idare eder", "Positive", 1.8),
]
INTERNET_ABBREV_MAP: dict[str, str] = {
    "tşk": "teşekkür", "tsk": "teşekkür", "slm": "selam", "sleam": "selam", "çalışmıyo": "çalışmıyor",
    "calismiyo": "çalışmıyor", "güzeeel": "güzel", "guzeeel": "güzel", "efsaane": "efsane",
    "berbaaat": "berbat", "⭐⭐⭐⭐⭐": "5 yıldız", "5/5": "5 yıldız mükemmel",
}
LITERARY_HYPERBOLE_POSITIVE: list[str] = ["cennet gibi", "rüya gibi", "masal gibi", "pamuk gibi"]
LITERARY_HYPERBOLE_NEGATIVE: list[str] = ["cehennem gibi", "ölüm gibi", "kabus gibi", "zehir gibi", "çöplük gibi"]
CASUAL_CONNECTORS: set[str] = {
    "la", "ya", "aga", "ağa", "valla", "cidden", "harbiden", "yani", "lan", "knk", "kanka", "abi", "yaw",
}

MIXED_REVIEW_SPLITTERS: list[str] = [
    " ama ", " fakat ", " ancak ", " lakin ",
    " however ", " but ", " although ", " though ",
    " on the other hand ", " in addition ", " furthermore ",
    " onun dışında ", " onun disinda ", " bunun dışında ", " bunun disinda ",
]

# Olumlu bağlam — negatif kelime tetiklenmez
POSITIVE_NEGATION_WHITELIST: list[str] = [
    "beklemeden", "sira beklemeden", "beklemeden erisebiliyorsunuz", "beklemeden alinamiyor",
    "yogun degildi", "yogun degil", "kalabalik degildi", "kalabalik degil",
    "sorun gormedim", "sorun gormedik", "sorun yasamadim", "sorun yasamadik",
    "hic bir olumsuzluk yasamadim", "hicbir olumsuzluk yasamadim",
]

# Koşullu olumlu — genel olumsuz değil, karışık-pozitif
CONDITIONAL_POSITIVE_PATTERNS: list[str] = [
    "tamamlanirsa gelinir", "tamamlanırsa gelinir", "tamamlanirsa gelirim",
    "tamamlanırsa gelirim", "giderilirse tekrar", "duzeltilirse tekrar",
    "eksiklikler tamamlanirsa", "eksiklikler giderilirse", "duzeltilirse gelirim",
    "duzeltilirse gelinir", "bir daha olsa gelir miyim",
]

MILD_NEGATIVE_PATTERNS: list[str] = [
    "getirilebilir", "yapilabilir", "yapılabilir", "olabilir", "arttirilmali",
    "arttırılmalı", "ogrenmeleri gerekiyor", "öğrenmeleri gerekiyor",
    "gerekiyor", "bekliyor", "bekleniyor", "birakilmamis", "bırakılmamış",
    "getirilmedi", "getirmediler", "bulunmuyor", "bulamiyorsunuz", "bulamıyorsunuz",
    "kus yuvasi", "kuş yuvası", "ciddi mesafeler", "o ne diye", "istemeyerek",
    "derinlesiyor", "derinleşiyor", "kapaliydi", "kapalıydı",
    "bakimda", "bakımda", "bakimdaydi", "bakımdaydı",
]

COORDINATION_ADJECTIVES: set[str] = {
    "guzel", "güzel", "yeterli", "iyi", "kotu", "kötü", "berbat", "harika",
    "mukemmel", "mükemmel", "lezzetli", "taze", "sicak", "soguk", "temiz", "kirli",
}

GENERAL_PRAISE: list[str] = [
    "herşey güzel", "herşey çok güzel", "hersey güzel", "çok güzeldi", "herşey mükemmel",
    "genel olarak güzel", "herşey harikaydı", "herşey iyiydi", "herşey güzeldi",
    "mükemmel tatil", "harika tatil", "süper tatil", "muhteşem tatil", "herşey süper",
]

GENERAL_COMPLAINT: list[str] = [
    "asla gelmeyin", "gitmeyin", "kaçının", "pişman olduk", "pişman oldum",
    "bir daha gelmem", "asla tavsiye etmem", "hayal kırıklığı", "rezalet bir otel",
    "berbat bir otel", "para tuzağı", "zaman kaybı",
    "paramız çöp", "paramiz cop", "para çöp oldu", "pişmanlıktan öteye",
    "karışık ve yorucu", "karisik ve yorucu",
]

DEPT_HINTS: set[str] = {
    "oda", "yemek", "havuz", "klima", "resepsiyon", "fiyat", "garson", "spa",
    "banyo", "wifi", "kahvaltı", "restoran", "masaj", "fatura", "çorba", "domates",
    "kabak", "dolma", "büfe", "tatlı", "plaj", "deniz", "animasyon", "asansör",
}

# Tek başına güçlü olumsuz sinyal veren kelimeler
SINGLE_NEGATIVE_STRONG: set[str] = {
    "kirli", "pis", "lekeli", "berbat", "rezalet", "iğrenç", "lezzetsiz", "kaba",
    "bozuk", "arızalı", "çalışmıyor", "pahalı", "soğuk", "bayat", "yavaş", "ilgisiz",
    "saygısız", "pişman", "korkunç", "felaket", "yapılmamış", "gelmiyor",
    "kötü", "kotu",
}

# ---------------------------------------------------------------------------
# Kategori anahtar kelime haritaları (50+ terim / kategori)
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    CAT_CLEANING: [
        "oda", "yatak", "banyo", "tuvalet", "temizlik", "temiz", "kirli", "pis", "havlu",
        "buklet", "sampuan", "sabun", "bonoz", "terlik", "genis", "kucuk", "dar", "konfor",
        "rahat", "ergonomi", "ses yalitimi", "yalitim", "yatak rahat", "yatak konfor",
        "carsaf", "nevresim", "yorgan", "yastik", "duz", "oda buyuk", "oda genis", "oda kucuk",
        "odalardan ses", "ses geliyor", "kapi alti", "balkon", "manzara", "minibar",
        "calisma masasi", "aydinlatma", "lamba",
    ],
    CAT_FOOD: [
        "yemek", "kahvalti", "restoran", "bar", "minibar", "bufe", "lezzet", "lezzetli",
        "lezzetsiz", "taze", "sicak", "soguk", "cesit", "cesitlilik", "menü", "menu",
        "pankek", "kiyma", "limonata", "soda", "alkol", "icki", "kokteyl", "bira", "sarap",
        "doldurulmus", "minibar dolu", "icecek soguk", "kahvalti cesit", "bufe zengin",
        "domates", "corba", "et", "tavuk", "balik", "makarna", "pilav", "salata", "tatli",
        "meyve", "peynir", "zeytin", "recel", "bal", "ekmek", "dondurma", "krep",
    ],
    CAT_RECEPTION: [
        "resepsiyon", "giris", "cikis", "check", "rezervasyon", "kayit", "karsilama",
        "odeme", "fatura", "muhasebe", "satis", "destek", "sikayet", "cozum", "cozuldu",
        "organizasyon", "ozel gun", "kutlama", "dogum gunu", "yil donumu",
        "lobi", "concierge", "bellboy", "valiz", "oda anahtari", "kart", "upgrade",
        "oda degisikligi", "erken giris", "gec cikis", "misafir iliskileri",
    ],
    CAT_TECH: [
        "klima", "wifi", "internet", "tv", "televizyon", "kumanda", "ariza", "bozuk",
        "tamir", "bakim", "mobil", "uygulama", "elektrik", "priz", "ampul", "lamba",
        "asansor", "lift", "sogutma", "isitma", "calismiyor", "bozuldu", "sizinti",
        "wifi yavas", "internet yok", "klima bozuk", "tv bozuk", "sinyal", "baglanti",
        "kanal", "kart kilidi", "saç kurutma", "fon", "su basinci",
    ],
    CAT_SPA: [
        "havuz", "spa", "sauna", "masaj", "wellness", "jakuzi", "hamam", "sezlong",
        "semsiye", "animasyon", "konser", "show", "sov", "muzik", "eglence", "aktivite",
        "cocuk", "kulubu", "mini kulup", "cocuk havuz", "oyun alani", "spor", "fitness",
        "tenis", "basketbol", "voleybol", "su sporlari", "dalış", "sörf", "yelken",
        "buhar odasi", "tuz odasi", "gym", "pilates", "yoga", "dans",
    ],
    CAT_GROUNDS: [
        "cevre", "bahce", "peyzaj", "yesil alan", "cim", "agac", "cicek", "otopark",
        "park", "vale", "park yeri", "transfer", "havaalani", "shuttle", "servis",
        "guvenlik", "kamera", "kasa", "kilit", "konum", "merkez", "sehir merkezi",
        "ulasim", "dolmus", "otobus", "metro", "deniz", "sahil", "kumsal", "cakil",
        "iskele", "manzara", "dag manzarasi",
    ],
    CAT_OTHER: [
        "gurultu", "gurultulu", "sessiz", "sakin", "huzurlu", "kalabalik", "tenha",
        "misafir profili", "profil", "prestij", "atmosfer", "kitle", "aile", "cift",
        "yasli", "grup", "kalite", "ortam", "dekor", "tema", "müzik seviyesi",
        "disiplin", "saygi", "huzur", "rahatsiz",
    ],
    CAT_STAFF: [
        "personel", "calisan", "garson", "resepsiyonist", "kibar", "guler yuz", "guleryuz",
        "yardimsever", "ilgili", "davranis", "bakim", "profesyonel", "kaba", "ilgisiz",
        "saygisiz", "kibar personel", "garson kaba", "personel ilgisiz", "yardimci oldu",
        "ilgi alaka", "motivasyon", "egitim", "hostes", "host", "mudur", "yonetici",
        "asci", "sef", "barmen", "animator", "canayakin", "sicakkanli",
    ],
}

# Personel davranışı vs resepsiyon ayrımı: garson/personel kaba → staff; giriş/bekleme → reception
STAFF_ONLY: set[str] = {"garson", "garsonlar", "personel kaba", "calisan kaba", "ilgisiz personel", "saygisiz", "guler yuz", "kibar personel"}
RECEPTION_ONLY: set[str] = {"check-in", "check-out", "checkin", "checkout", "giris", "cikis", "kayit", "rezervasyon", "odeme", "fatura", "muhasebe"}

STOP_WORDS: set[str] = {
    "ve", "veya", "ama", "fakat", "lakin", "ancak", "ise", "ki", "de", "da", "mi", "mı", "mu", "mü",
    "bir", "bu", "şu", "o", "ne", "nasıl", "neden", "niçin", "kim", "nerede", "her", "hepsi", "tüm",
    "için", "gibi", "kadar", "olan", "olarak", "ben", "sen", "biz", "siz", "onlar", "bizi",
    "beni", "bana", "sana", "size", "bize", "ile", "daha", "en", "hiç", "hep", "sadece", "bile",
    "miydi", "mıydı", "idi", "ken", "çünkü", "bazı", "bazen", "şimdi", "kendi", "the", "and", "was",
    "that", "this", "with", "from", "have", "been", "very", "not",
    "la", "ya", "aga", "ağa", "valla", "cidden", "harbiden", "yani", "lan", "knk", "kanka", "abi", "yaw", "yav",
}

KEEP_WORDS: set[str] = {"çok", "herşey", "hersey", "hiç", "daha", "en", "burada", "keyiften", "keyif", "asla", "şaka", "saka", "espri", "ironik", "gelmeyin"}

HOTEL_TERMS: set[str] = set().union(*CATEGORY_KEYWORDS.values()) | {
    "güzel", "güzeldi", "harika", "mükemmel", "bayıldım", "bayıldık", "beğendim", "beğendik", "kötü", "berbat",
    "herşey", "hersey", "çok", "lezzet", "temiz", "kirli", "keyiften", "keyif", "burada", "ölebilirim", "klima", "havuz",
    "efsane", "rezalet", "çöp", "cop", "fiyasko", "otel", "pis", "yok",
}

PRIORITY_TERMS: set[str] = HOTEL_TERMS | STRONG_POSITIVE | STRONG_NEGATIVE

# Çevrimdışı çeviri ipuçları (EN/DE/RU → TR kısa yollar)
OFFLINE_TRANSLATIONS: dict[str, str] = {
    "the room was dirty": "oda kirliydi",
    "room was dirty": "oda kirliydi",
    "dirty room": "kirli oda",
    "food was excellent": "yemek mükemmeldi",
    "excellent food": "yemek mükemmeldi",
    "the food was cold": "yemek soğuktu",
    "food was cold": "yemek soğuktu",
    "staff was rude": "personel kabadı",
    "rude staff": "kaba personel",
    "slow reception": "resepsiyon yavaş",
    "broken air conditioning": "klima bozuk",
    "air conditioning broken": "klima bozuk",
    "pool was dirty": "havuz kirliydi",
    "everything was perfect": "herşey mükemmeldi",
    "everything was great": "herşey harikaydı",
    "never come back": "bir daha asla gelmem",
    "do not recommend": "asla tavsiye etmem",
    "do not come back": "bir daha gelmeyin",
    "would not recommend": "asla tavsiye etmem",
    "rude reception": "resepsiyon kaba",
    "slow wifi": "wifi yavaş",
    "broken wifi": "wifi bozuk",
    "das zimmer war schmutzig": "oda kirliydi",
    "das essen war kalt": "yemek soğuktu",
    "комната была грязной": "oda kirliydi",
    "еда была холодной": "yemek soğuktu",
}

# ---------------------------------------------------------------------------
# Normalizasyon & tokenizasyon
# ---------------------------------------------------------------------------
_TYPO_MAP = {
    "hersey": "herşey", "her sey": "herşey", "herseyi": "herşey",
    "guzel": "güzel", "guzeldi": "güzeldi", "cok": "çok", "cok guzel": "çok güzel",
    "mukemmel": "mükemmel", "harika": "harika", "lezzetli": "lezzetli",
    "kirliydi": "kirli", "soğuktu": "soğuk", "bozuktu": "bozuk",
    "calismiyor": "çalışmıyor", "calismiyordu": "çalışmıyor",
    "calismiyo": "çalışmıyor", "çalışmıyo": "çalışmıyor",
    "saka": "şaka", "saka)": "şaka)",
    "efsaane": "efsane", "berbaaat": "berbat", "güzeeel": "güzel", "guzeeel": "güzel",
    "fena degil": "fena değil", "pisman": "pişman", "igrenc": "iğrenç",
}


def _expand_internet_abbrev(text: str) -> str:
    t = text
    for abbr, full in sorted(INTERNET_ABBREV_MAP.items(), key=lambda x: -len(x[0])):
        t = t.replace(abbr, full)
    t = re.sub(r"(\d+)\s*/\s*(\d+)", r"\1/\2", t)
    return t


def _collapse_repeated_letters(text: str) -> str:
    """güzeeel → güzel, berbaaat → berbat (3+ tekrar → 1-2)."""
    known = {
        "güzeeel": "güzel", "guzeeel": "güzel", "berbaaat": "berbat", "efsaane": "efsane",
        "mükemmell": "mükemmel", "mukemmell": "mükemmel", "rezalet": "rezalet",
        "harikaaa": "harika", "süpeeerr": "süper", "supeeerr": "süper",
    }
    t = text
    for k, v in known.items():
        t = t.replace(k, v)
    t = re.sub(r"(.)\1{3,}", r"\1\1", t)
    t = re.sub(r"([aeiouüöıâAEIOUÜÖİ])\1{2,}", r"\1", t)
    return t


def is_casual_register(text: str) -> bool:
    """Twitter/sosyal medya informal kayıt tespiti."""
    cleaned = normalize_turkish(text)
    if any(p in cleaned for p in TWITTER_SLANG_POSITIVE + TWITTER_SLANG_NEGATIVE):
        return True
    tokens = set(cleaned.split())
    if tokens & CASUAL_CONNECTORS:
        return True
    if re.search(r"\d+\s*/\s*\d+", cleaned):
        return True
    if len(cleaned.split()) <= 6 and any(w in cleaned for w in ("la", "aga", "valla", "lan", "harbiden")):
        return True
    return False


def normalize_turkish(text: str) -> str:
    """Küçük harf, NFKC, slang, tekrarlı harf, bitişik kelimeler."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text.lower().strip())
    t = _expand_internet_abbrev(t)
    for old, new in _TYPO_MAP.items():
        t = t.replace(old, new)
    t = _collapse_repeated_letters(t)
    t = re.sub(r"herşeygüzeldi", "herşey çok güzeldi", t, flags=re.UNICODE)
    t = re.sub(r"herseyguzeldi", "herşey çok güzeldi", t, flags=re.IGNORECASE)
    t = re.sub(r"(herşey)(güzeldi|güzel|çok|mükemmel|harika|süper)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(çok)(güzel|iyi|kötü|berbat|güzeldi)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(yemek)(soğuk|harika|berbat|lezzetli)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(oda)(kirli|temiz|büyük|küçük|pis|berbat)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(havuz)(kirli|temiz|soğuk|pis|berbat)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(klima)(bozuk|çalışmıyor|arızalı|yok|calismiyor)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(klima)(çok soğuk|soğuk|soğuktu)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(otel)(rezalet|berbat|efsane|harika|mükemmel|super|süper)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(yemek)(berbat|berbaaat|rezalet|çöp|cop)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(wifi)(yok|bozuk|calismiyor|çalışmıyor)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(burada)(keyiften)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(keyiften)(ölebilirim|öldüm|geberirim|geçerim)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(havuzu)(çok)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"(asla)(gelmeyin|gelmem|gitmeyin|tavsiye)", r"\1 \2", t, flags=re.UNICODE)
    t = re.sub(r"aslaaslgelmeyin", "asla gelmeyin", t, flags=re.UNICODE)
    t = re.sub(r"otelrezalet", "otel rezalet", t, flags=re.UNICODE)
    t = re.sub(r"otelberbat", "otel berbat", t, flags=re.UNICODE)
    t = re.sub(r"otelefsane", "otel efsane", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def split_glued_words(text: str) -> str:
    lowered = normalize_turkish(text)
    for term in sorted(PRIORITY_TERMS, key=len, reverse=True):
        if len(term) < 3:
            continue
        # Only split when term appears as a word boundary (preceded/followed by non-letter)
        # This prevents "temizlik" from splitting into "temiz" + "lik"
        lowered = re.sub(
            rf"(?<![a-z]){re.escape(term)}(?![a-z])",
            f" {term} ",
            lowered,
            flags=re.IGNORECASE,
        )
    return re.sub(r"\s+", " ", lowered).strip()


def light_stem(word: str) -> list[str]:
    """Hafif Türkçe kök çıkarma."""
    stems: list[str] = []
    m = re.match(
        r"^(güzel|harika|mükemmel|kötü|berbat|iyi|leziz|kirli|temiz|soğuk|bozuk|pahalı|kaba|yavaş|keyif)"
        r"(di|dı|du|dü|ti|tı|tu|tü|miş|mış|muş|müş|ydi|ydı|ydu|ydü|ten)$",
        word,
    )
    if m:
        stems.append(m.group(1))
    suffix_stem = re.sub(
        r"(ları|leri|mize|nize|siniz|lar|ler|sin|m|n|na|da|de|dan|den|yi|yı|yu|yü|sı|si|su|sü|a|e|ı|i|u|ü|dır|dir|dur|dür)$",
        "",
        word,
    )
    if suffix_stem and len(suffix_stem) >= 3 and suffix_stem != word:
        stems.append(suffix_stem)
    return stems


def tokenize_turkish(text: str) -> list[str]:
    """Türkçe metni anlamlı tokenlara ayırır."""
    if not text or not text.strip():
        return []
    normalized = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    normalized = split_glued_words(normalized)
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in normalized.split():
        word = raw.lower().strip()
        if len(word) < 2:
            continue
        if word in STOP_WORDS and word not in KEEP_WORDS:
            continue
        if word not in seen:
            tokens.append(word)
            seen.add(word)
        for stem in light_stem(word):
            if len(stem) < 3:
                continue
            if stem not in seen and stem not in STOP_WORDS:
                tokens.append(stem)
                seen.add(stem)
    return tokens


def apply_offline_translation(text: str) -> str:
    """Çevrimdışı ortamda yaygın yabancı otel yorumu kalıplarını Türkçeye çevirir."""
    key = text.lower().strip()
    if key in OFFLINE_TRANSLATIONS:
        return OFFLINE_TRANSLATIONS[key]
    for phrase, tr in OFFLINE_TRANSLATIONS.items():
        if phrase in key:
            return tr
    return text


# ---------------------------------------------------------------------------
# Mecazi övgü & karışık (ama/fakat) yorum analizi
# ---------------------------------------------------------------------------
@dataclass
class MixedReviewResult:
    is_mixed: bool
    clauses: list[str]
    primary_category: Optional[str] = None
    secondary_category: Optional[str] = None
    overall_sentiment: Optional[str] = None
    overall_score: Optional[float] = None


def has_positive_idiom(text: str) -> bool:
    cleaned = normalize_turkish(text)
    return any(idiom in cleaned for idiom in POSITIVE_IDIOMS)


def _has_positive_whitelist(cleaned: str) -> bool:
    if not any(p in cleaned for p in POSITIVE_NEGATION_WHITELIST):
        return False
    if any(n in cleaned for n in (
        "alamiyor", "alınamıyor", "alinamiyor", "yok", "yetersiz", "kotu", "kötü",
        "kalitesiz", "berbat", "zayif", "zayıf", "bulamiyor", "bulamıyor", "kaldırılmış",
        "kaldirilmis", "getirilmedi", "getirmediler", "kapalıydı", "kapaliydi",
    )):
        return False
    return True


def _has_conditional_positive(cleaned: str) -> bool:
    return any(p in cleaned for p in CONDITIONAL_POSITIVE_PATTERNS)


def split_review_clauses(text: str) -> list[str]:
    """'ama', 'fakat', 'ancak' ile cümle bölme; uzun yorumlarda çoklu ayraç."""
    cleaned = normalize_turkish(text)
    for sep in MIXED_REVIEW_SPLITTERS:
        if sep in cleaned:
            parts = [p.strip() for p in cleaned.split(sep, 1) if p.strip()]
            if len(parts) >= 2:
                return parts
    if len(cleaned.split()) >= 20:
        for sep in (
            " yine de ", " ne var ki ", " bunun disinda ", " bunun dışında ",
            " onun dışında ", " onun disinda ", " ancak ", " ayrıca ",
        ):
            if sep in cleaned:
                parts = [p.strip() for p in cleaned.split(sep, 1) if p.strip()]
                if len(parts) >= 2:
                    return parts
        # Nokta ile çoklu cümle
        dotted = [p.strip() for p in re.split(r"[.!?]+", cleaned) if p.strip() and len(p.strip()) >= 12]
        if len(dotted) >= 3:
            return dotted
    return [cleaned] if cleaned else []


def _clause_category(clause: str) -> tuple[str, float]:
    """Tek cümlecik için kategori skoru (category_rules delegasyonu)."""
    from app.services.category_rules import _prepare_text, _score_categories, _sorted_category_scores
    cleaned, tokens = _prepare_text(clause)
    scores = _score_categories(cleaned, tokens)
    ranked = _sorted_category_scores(scores)
    return ranked[0][0], ranked[0][1]


# Şikayet birincil önceliği — Genel/Diğer en sonda
_COMPLAINT_CATEGORY_WEIGHT: dict[str, int] = {
    CAT_FOOD: 10,
    CAT_TECH: 9,
    CAT_CLEANING: 8,
    CAT_STAFF: 7,
    CAT_SPA: 6,
    CAT_RECEPTION: 5,
    CAT_FINANCE: 4,
    CAT_OTHER: 0,
}


def _best_complaint_category(items: list[dict]) -> Optional[str]:
    """En güçlü departman şikayetini seç; Diğer'i mümkün olduğunca atla."""
    best_cat: Optional[str] = None
    best_rank = (-1, -1.0)
    for c in items:
        cat = c.get("category") or CAT_OTHER
        if cat == CAT_OTHER:
            continue
        weight = _COMPLAINT_CATEGORY_WEIGHT.get(cat, 1)
        rank = (weight, float(c.get("cat_score") or 0.0))
        if rank > best_rank:
            best_rank = rank
            best_cat = cat
    if best_cat:
        return best_cat
    for c in items:
        if c.get("category"):
            return c["category"]
    return None


def _best_praise_category(items: list[dict]) -> Optional[str]:
    best_cat: Optional[str] = None
    best_rank = (-1, -1.0)
    for c in items:
        cat = c.get("category") or CAT_OTHER
        if cat == CAT_OTHER:
            continue
        weight = _COMPLAINT_CATEGORY_WEIGHT.get(cat, 1)
        rank = (weight, float(c.get("cat_score") or 0.0))
        if rank > best_rank:
            best_rank = rank
            best_cat = cat
    if best_cat:
        return best_cat
    for c in items:
        if c.get("category"):
            return c["category"]
    return None


def analyze_mixed_review(text: str) -> MixedReviewResult:
    """
    Karışık yorum: olumsuz + olumlu cümlecikler.
    Birincil kategori = en güçlü şikayet departmanı; ikincil = övgü.
    Koşullu dönüş ('eksiklikler tamamlanırsa gelinir') uzun şikayetli
    yorumlarda Diğer/Positive 0.35 short-circuit yapmaz.
    """
    clauses = split_review_clauses(text)
    cleaned_full = normalize_turkish(text)
    word_count = len(cleaned_full.split())
    conditional = _has_conditional_positive(cleaned_full)

    # Uzun yorum "ama" ile 2 dev blok olsa bile alt cümlelerden karışık tespit
    if word_count >= 40 and len(clauses) <= 2:
        try:
            from app.services.absa_service import split_clauses_absa

            sub_clauses = split_clauses_absa(text)
        except Exception:
            logger.warning("Failed to split clauses for mixed review analysis", exc_info=True)
            sub_clauses = []
        if len(sub_clauses) >= 5:
            clause_data = []
            for sc in sub_clauses:
                sent, score = detect_strong_sentiment(sc)
                cat, cat_score = _clause_category(sc)
                clause_data.append({
                    "clause": sc, "sentiment": sent, "score": score,
                    "category": cat, "cat_score": cat_score,
                })
            neg = [c for c in clause_data if c["sentiment"] == "Negative" or c["score"] < -0.05]
            pos = [c for c in clause_data if c["sentiment"] == "Positive" or c["score"] > 0.05]
            if len(pos) >= 1 and len(neg) >= 3:
                primary_cat = _best_complaint_category(neg) or CAT_OTHER
                secondary_cat = _best_praise_category(pos) or CAT_OTHER
                food_hits = sum(
                    1 for w in (
                        "yemek", "kiyma", "kıyma", "restoran", "kahvaltı", "kuyruk", "pankek", "soda",
                        "limonata", "icecek", "içecek", "tekila", "sira", "sıra", "bar", "dakika",
                    )
                    if w in cleaned_full
                )
                if food_hits >= 3:
                    primary_cat = CAT_FOOD
                spa_true = any(w in cleaned_full for w in ("klor", "masaj", "sauna", "hamam", "wellness"))
                if food_hits >= 4 and not spa_true and primary_cat == CAT_SPA:
                    primary_cat = CAT_FOOD
                overall_sent = "Negative" if any(
                    w in cleaned_full for w in (
                        "kuyruk", "sira", "sıra", "pisman", "pişman", "yorucu", "paramiz", "paramız",
                        "carcur", "çarçur", "cop oldu", "çöp oldu",
                    )
                ) else "Neutral"
                overall_sc = -0.3 if overall_sent == "Negative" else 0.05
                return MixedReviewResult(
                    is_mixed=True, clauses=sub_clauses,
                    primary_category=primary_cat, secondary_category=secondary_cat,
                    overall_sentiment=overall_sent, overall_score=overall_sc,
                )

    # Kısa, departmansız koşullu dönüş → hafif olumlu genel
    if conditional and word_count < 25 and not any(
        h in cleaned_full for h in (
            "yemek", "kahvalti", "kahvaltı", "minibar", "mini bar", "aquapark", "aquaprk",
            "oda", "banyo", "klima", "havuz", "personel", "garson",
        )
    ):
        return MixedReviewResult(
            is_mixed=True, clauses=clauses,
            primary_category=CAT_OTHER, secondary_category=CAT_OTHER,
            overall_sentiment="Positive", overall_score=0.35,
        )

    if len(clauses) < 2:
        if word_count >= 25:
            sub_clauses = [p.strip() for p in re.split(r"[.;]\s+", cleaned_full) if p.strip() and len(p.strip()) >= 8]
            if len(sub_clauses) >= 3:
                clause_data = []
                for sc in sub_clauses:
                    sent, score = detect_strong_sentiment(sc)
                    cat, cat_score = _clause_category(sc)
                    clause_data.append({
                        "clause": sc, "sentiment": sent, "score": score,
                        "category": cat, "cat_score": cat_score,
                    })
                neg = [c for c in clause_data if c["sentiment"] == "Negative" or c["score"] < -0.1]
                pos = [c for c in clause_data if c["sentiment"] == "Positive" or c["score"] > 0.1]
                # Uzun yorum: en az 1 övgü + 1 şikayet yeterli
                if len(pos) >= 1 and len(neg) >= 1 and (len(pos) + len(neg) >= 3 or word_count >= 40):
                    primary_cat = _best_complaint_category(neg) or CAT_OTHER
                    secondary_cat = _best_praise_category(pos) or CAT_OTHER
                    food_hits = sum(
                        1 for w in ("yemek", "kiyma", "kıyma", "restoran", "kahvaltı", "kuyruk", "pankek", "soda", "limonata")
                        if w in cleaned_full
                    )
                    if food_hits >= 2:
                        primary_cat = CAT_FOOD
                    overall_sent, overall_sc = "Neutral", 0.10 if conditional else -0.05
                    if any(w in cleaned_full for w in ("kuyruk", "pişman", "pisman", "yorucu", "paramız", "paramiz")):
                        overall_sent, overall_sc = "Negative", -0.25
                    return MixedReviewResult(
                        is_mixed=True, clauses=sub_clauses,
                        primary_category=primary_cat,
                        secondary_category=secondary_cat,
                        overall_sentiment=overall_sent, overall_score=overall_sc,
                    )
        return MixedReviewResult(is_mixed=False, clauses=clauses)

    clause_data = []
    for clause in clauses:
        sent, score = detect_strong_sentiment(clause)
        cat, cat_score = _clause_category(clause)
        clause_data.append({
            "clause": clause, "sentiment": sent, "score": score,
            "category": cat, "cat_score": cat_score,
        })

    neg = [c for c in clause_data if c["sentiment"] == "Negative" or c["score"] < -0.05]
    pos = [c for c in clause_data if c["sentiment"] == "Positive" or c["score"] > 0.05]

    primary_cat = secondary_cat = None
    if neg and pos:
        primary_cat = _best_complaint_category(neg) or neg[0]["category"]
        secondary_cat = _best_praise_category(pos) or pos[0]["category"]
        if "klima" in cleaned_full and any(w in cleaned_full for w in ("soğuk", "soğuktu", "bozuk")):
            primary_cat = CAT_TECH
        if "havuz" in cleaned_full and any(w in cleaned_full for w in ("beğendik", "beğendim", "harika", "güzel")):
            if secondary_cat != CAT_SPA:
                secondary_cat = CAT_SPA
        # Tam metin F&B şikayeti baskınsa birincil yiyecek
        food_neg_hits = sum(
            1 for w in (
                "cesitlilik", "çeşitlilik", "yetersiz", "kalitesiz", "minibar", "mini bar",
                "kahvalti", "kahvaltı", "yemek", "meyve", "sarap", "şarap", "raki", "rakı",
                "kiyma", "kıyma", "kuyruk", "pankek", "icecek", "içecek", "tekila", "sira", "sıra",
                "bar", "dakika",
            )
            if w in cleaned_full
        )
        if food_neg_hits >= 3 and any(c["category"] == CAT_FOOD for c in neg):
            primary_cat = CAT_FOOD
        spa_true = any(w in cleaned_full for w in ("klor", "masaj", "sauna", "hamam", "wellness"))
        if food_neg_hits >= 4 and not spa_true and primary_cat == CAT_SPA:
            primary_cat = CAT_FOOD
        pos_strength = max(c["score"] for c in pos)
        neg_strength = min(c["score"] for c in neg)
        if conditional:
            # Koşullu dönüş = karışık; net Positive değil
            overall_sent, overall_sc = "Neutral", round(max(-0.1, min(0.25, (pos_strength + neg_strength) / 2)), 2)
        elif pos_strength + neg_strength > 0.3:
            overall_sent, overall_sc = "Positive", round(min(0.65, pos_strength * 0.7), 2)
        else:
            overall_sent, overall_sc = "Neutral", round((pos_strength + neg_strength) / 2, 2)
        return MixedReviewResult(
            is_mixed=True, clauses=clauses,
            primary_category=primary_cat, secondary_category=secondary_cat,
            overall_sentiment=overall_sent, overall_score=overall_sc,
        )

    # Uzun yorum: erken "ama" bölmesi duyguyu tek tarafa yığsa bile övgü+şikayet varsa karışık
    if word_count >= 40:
        praise = any(w in cleaned_full for w in (
            "tesekkur", "teşekkür", "basarili", "başarılı", "iyiydi", "guzeldi", "güzeldi",
            "personel cabalari", "personel çabaları", "harika", "mukemmel", "mükemmel",
            "iyi bir otel", "konusunda iyi",
        ))
        complaint = any(w in cleaned_full for w in (
            "kuyruk", "sira", "sıra", "pisman", "pişman", "yorucu", "yorgunluk", "paramiz", "paramız",
            "cop oldu", "çöp oldu", "bulamad", "dusuk", "düşük", "temizletemed", "berbat",
            "carcur", "çarçur", "wifi", "yalitim", "yalıtım", "sezlong", "şezlong",
        ))
        if praise and complaint:
            food_hits = sum(
                1 for w in ("yemek", "kiyma", "kıyma", "restoran", "kuyruk", "pankek", "soda", "limonata")
                if w in cleaned_full
            )
            primary = CAT_FOOD if food_hits >= 2 else (_best_complaint_category(neg) if neg else CAT_OTHER)
            secondary = _best_praise_category(pos) if pos else CAT_STAFF
            overall_sent = "Negative" if any(w in cleaned_full for w in ("kuyruk", "pişman", "pisman", "yorucu", "paramız", "paramiz")) else "Neutral"
            overall_sc = -0.25 if overall_sent == "Negative" else 0.05
            return MixedReviewResult(
                is_mixed=True, clauses=clauses,
                primary_category=primary, secondary_category=secondary,
                overall_sentiment=overall_sent, overall_score=overall_sc,
            )

    return MixedReviewResult(is_mixed=False, clauses=clauses)


# ---------------------------------------------------------------------------
# N-gram & ifade düzeyinde eşleşme
# ---------------------------------------------------------------------------
def extract_ngrams(text: str, min_n: int = 2, max_n: int = 3) -> list[str]:
    """2-3 kelimelik pencere n-gramları (deterministik sıra)."""
    cleaned = normalize_turkish(text)
    tokens = tokenize_turkish(cleaned)
    if not tokens:
        return []
    ngrams: list[str] = []
    for n in range(min_n, min(max_n, len(tokens)) + 1):
        for i in range(len(tokens) - n + 1):
            ngrams.append(" ".join(tokens[i : i + n]))
    return ngrams


def score_phrase_patterns(cleaned: str) -> tuple[float, float, list[str]]:
    """
    İfade düzeyinde duygu skoru. Tek kelime skorundan yüksek ağırlık.
    Returns: (pos_weight, neg_weight, matched_phrases)
    """
    pos_w = neg_w = 0.0
    matched: list[str] = []
    ngram_set = set(extract_ngrams(cleaned, 2, 3))
    ngram_set.add(cleaned)

    for phrase in POSITIVE_PHRASES:
        if phrase in cleaned:
            pos_w += 2.5
            matched.append(phrase)
    for phrase in NEGATIVE_PHRASES:
        if phrase in cleaned:
            neg_w += 2.5
            matched.append(phrase)
    for phrase, weight in PHRASE_SENTIMENT_WEIGHTS:
        if phrase in cleaned or phrase in ngram_set:
            if weight > 0:
                pos_w += weight
            else:
                neg_w += abs(weight)
            matched.append(phrase)
    # n-gram pencerelerinde kısmi ifade eşleşmesi
    for ng in ngram_set:
        for phrase in POSITIVE_PHRASES:
            if len(phrase) > 6 and phrase in ng and phrase not in matched:
                pos_w += 1.5
                matched.append(phrase)
        for phrase in NEGATIVE_PHRASES:
            if len(phrase) > 6 and phrase in ng and phrase not in matched:
                neg_w += 1.5
                matched.append(phrase)
    return pos_w, neg_w, matched


def detect_negative_hyperbole(text: str) -> bool:
    """
    Olumsuz abartı: 'yemekler o kadar kötüydü ki bayılacaktım'.
    'bayıldım' (olumlu) ile karıştırılmamalı.
    """
    cleaned = normalize_turkish(text)
    ascii_clean = (
        cleaned.replace("ş", "s").replace("ı", "i").replace("ö", "o")
        .replace("ü", "u").replace("ğ", "g").replace("ç", "c").replace("î", "i")
    )
    for marker in NEGATIVE_HYPERBOLE:
        mn = marker.replace("ş", "s").replace("ı", "i").replace("ö", "o").replace("ü", "u").replace("ğ", "g").replace("ç", "c")
        if mn in ascii_clean or marker in cleaned:
            return True
    if re.search(r"(kotu|berbat|igrenc|lezzetsiz|pis|tatsiz).*(bayilac|bayilir|olecek|geber|kusac)", ascii_clean):
        return True
    if re.search(r"(bayilac|bayilir|olecek|geber|kusac).*(kotu|berbat|igrenc|lezzetsiz)", ascii_clean):
        return True
    return False


def _positive_bayil_allowed(cleaned: str) -> bool:
    """'bayıldım' olumlu sayılır; 'bayılacaktım' bağlamında olumlu bayıl sayılmaz."""
    if detect_negative_hyperbole(cleaned):
        return False
    ascii_clean = cleaned.replace("ş", "s").replace("ı", "i")
    if re.search(r"bayil(ac|ir|acak)", ascii_clean):
        return False
    return True


def detect_humor(text: str) -> bool:
    """
    Mizahi / şaka yorum tespiti — manipülasyondan ayrı.
    'asla gelmeyin (şaka)' → şaka; '5 yıldız öne çıksın diye' → manipülasyon.
    """
    cleaned = normalize_turkish(text)
    ascii_clean = cleaned.replace("ş", "s").replace("ı", "i").replace("ğ", "g")
    for marker in JOKE_MARKERS:
        m = marker.replace("ş", "s").replace("ı", "i")
        if m in ascii_clean or marker in cleaned:
            return True
    if re.search(r"\b(saka|şaka)\b", cleaned) or re.search(r"\bsaka\b", ascii_clean):
        return True
    fake_neg = any(p in cleaned for p in ("asla gelmeyin", "gitmeyin", "pişman", "asla tavsiye"))
    for ctx in JOKE_CONTEXT_MARKERS:
        c = ctx.replace("ş", "s").replace("ı", "i")
        if (ctx in cleaned or c in ascii_clean) and fake_neg:
            return True
    return False


def detect_manipulation(text: str, rating: Optional[int] = None) -> bool:
    """
    Sahte yüksek puan / görünürlük manipülasyonu tespiti.
    öne çıksın, 5 yıldız veriyorum, yorumum görünsün vb.
    Mizah/şaka yorumları manipülasyon sayılmaz.
    """
    if detect_humor(text):
        return False
    cleaned = normalize_turkish(text)
    has_manip = any(p in cleaned for p in MANIPULATION_PATTERNS)
    if not has_manip:
        for ng in extract_ngrams(cleaned, 2, 4):
            if any(p in ng for p in MANIPULATION_PATTERNS):
                has_manip = True
                break
    if not has_manip:
        return False

    # Yüksek puan + manipülasyon kalıbı → kesin manipülasyon
    if rating is not None and rating >= 4:
        return True

    # Görünürlük manipülasyonu (öne çıksın / görünsün) → manipülasyon
    if any(x in cleaned for x in ("öne çıksın", "üste çıksın", "görünsün", "gorunsun", "görünsün diye")):
        return True

    # Manipülasyon + olumsuz içerik
    _, neg, _, strong_neg = count_lexicon_hits(cleaned)
    if strong_neg or neg >= 1:
        return True
    if any(p in cleaned for p in NEGATIVE_PHRASES):
        return True

    # Metinde 5 yıldız verme niyeti + manipülasyon kalıbı
    if any(x in cleaned for x in ("5 yıldız", "5 yildiz", "beş yıldız", "yıldız veriyorum", "yildiz veriyorum")):
        return True
    return False


# ---------------------------------------------------------------------------
# Duygu analizi
# ---------------------------------------------------------------------------
def _word_in_text(word: str, cleaned: str, tokens: list[str]) -> bool:
    """Kelime sınırı duyarlı eşleşme; olumsuz ekleri hariç tutar."""
    if " " in word:
        return word in cleaned
    # Türkçe olumsuzluk ekleri — "temizlik" → "temiz" yanlış pozitifini engeller
    negated_suffixes = ("lenmedi", "lenmemiş", "lenmemis", "lenmiyor", "siz", "sız", "suz", "süz", "mez", "madı", "medi")
    # İsim yapım ekleri — "temizlik", "temizci", "güzellik" gibi sözcükler yanlış eşleşmesin
    noun_suffixes = ("lik", "lık", "lik", "luk", "lük", "ci", "cı", "ci", "cü", "lı", "li", "lu", "lü")
    negated_temiz = (
        "temizlenmedi" in cleaned
        or "temizlenmemiş" in cleaned
        or "temizlenmemis" in cleaned
    )
    for i, tok in enumerate(tokens):
        if tok == word:
            if word == "temiz" and (negated_temiz or (i + 1 < len(tokens) and tokens[i + 1].startswith("lenme"))):
                continue
            return True
        if word in tok and len(tok) > len(word) and len(word) >= 3:
            rest = tok[len(word):]
            if rest.startswith("le") or any(rest.endswith(s) for s in negated_suffixes):
                continue
            if rest in noun_suffixes:
                continue
            if word == tok[: len(word)]:
                return True
    return word in cleaned.split()


def _phrase_in_text(phrase: str, cleaned: str) -> bool:
    """İfade düzeyi eşleşme — kısa parçaların alt-dize yanlış pozitifini önler."""
    p = phrase.strip().lower()
    if not p:
        return False
    if len(p) <= 3 and " " not in p:
        return False
    if " " in p:
        return p in cleaned
    tokens = tokenize_turkish(cleaned)
    return _word_in_text(p, cleaned, tokens)


def count_lexicon_hits(cleaned: str) -> tuple[int, int, bool, bool]:
    tokens = tokenize_turkish(cleaned)
    hyperbole = detect_negative_hyperbole(cleaned)
    pos = 0
    for w in POSITIVE_WORDS:
        if w in {"bayıl", "bayıldım", "bayıldık", "bayıl"} and not _positive_bayil_allowed(cleaned):
            continue
        if _word_in_text(w, cleaned, tokens):
            pos += 1
    neg = sum(1 for w in NEGATIVE_WORDS if _word_in_text(w, cleaned, tokens))

    if _has_positive_whitelist(cleaned):
        neg = max(0, neg - 2)
        if "bekleme" in cleaned and "beklemeden" in cleaned:
            neg = max(0, neg - 1)
        if "sorun" in cleaned and "sorun gormed" in cleaned:
            neg = 0

    if "kapali havuz" in cleaned or "kapalı havuz" in cleaned:
        if "iyi calis" in cleaned or "iyi çalış" in cleaned or "guzel" in cleaned or "güzel" in cleaned or "harika" in cleaned or "temiz" in cleaned:
            neg = max(0, neg - 1)

    if _has_conditional_positive(cleaned):
        neg = max(0, neg - 1)

    for pattern in MILD_NEGATIVE_PATTERNS:
        if pattern in cleaned:
            neg += 1
            if pattern in ("kus yuvasi", "kuş yuvası", "getirilmedi", "bırakılmamış", "kalitesiz", "ciddi mesafeler"):
                neg += 2

    # İfade düzeyi skor (tek kelimeye baskın)
    phrase_pos, phrase_neg, _ = score_phrase_patterns(cleaned)
    pos += int(phrase_pos / 1.5)
    neg += int(phrase_neg / 1.5)

    pos += sum(2 for p in POSITIVE_PHRASES if _phrase_in_text(p, cleaned))
    neg += sum(2 for p in NEGATIVE_PHRASES if _phrase_in_text(p, cleaned))
    pos += sum(2 for p in TWITTER_SLANG_POSITIVE if p in cleaned)
    neg += sum(2 for p in TWITTER_SLANG_NEGATIVE if p in cleaned)
    pos += sum(2 for p in LITERARY_HYPERBOLE_POSITIVE if p in cleaned)
    neg += sum(2 for p in LITERARY_HYPERBOLE_NEGATIVE if p in cleaned)
    has_pos_phrase = any(_phrase_in_text(p, cleaned) for p in POSITIVE_PHRASES + TWITTER_SLANG_POSITIVE + LITERARY_HYPERBOLE_POSITIVE)
    has_neg_phrase = any(_phrase_in_text(p, cleaned) for p in NEGATIVE_PHRASES + TWITTER_SLANG_NEGATIVE + LITERARY_HYPERBOLE_NEGATIVE)
    has_strong_pos = any(
        _word_in_text(w, cleaned, tokens)
        for w in STRONG_POSITIVE
        if w not in {"bayıl", "bayıldım", "bayıldık"} or _positive_bayil_allowed(cleaned)
    )
    has_strong_neg = any(_word_in_text(w, cleaned, tokens) for w in STRONG_NEGATIVE)
    if hyperbole:
        has_strong_neg = True
        neg += 3
        has_strong_pos = False
        has_pos_phrase = False
        pos = max(0, pos - 2)
    has_single_neg = any(_word_in_text(w, cleaned, tokens) for w in SINGLE_NEGATIVE_STRONG)
    if "güzeldi" in cleaned or "çok güzel" in cleaned:
        if not any(n in cleaned for n in ("lezzetsiz", "berbat", "soğuk", "kötü", "iğrenç")):
            has_strong_pos = True
    if "herşey" in cleaned and any(w in cleaned for w in ("güzel", "mükemmel", "harika", "süper")):
        if not has_neg_phrase and not has_single_neg:
            has_pos_phrase = True
    if "memnun değil" in cleaned or "memnun kalmad" in cleaned:
        has_strong_neg = True
        neg += 2
    if "fena değil" in cleaned or "fena degil" in cleaned:
        has_strong_pos = True
        pos += 2
    elif "idare eder" in cleaned or "gayet iyi" in cleaned or "baya iyi" in cleaned:
        has_strong_pos = True
        pos += 1
    if re.search(r"10\s*/\s*10", cleaned) or "10/10" in cleaned:
        has_strong_pos = True
        pos += 3
    if "efsane" in cleaned and not any(n in cleaned for n in ("berbat", "rezalet", "çöp", "cop", "fiyasko")):
        has_strong_pos = True
        pos += 2
    if has_single_neg:
        neg += 1
        has_strong_neg = True
    if "temizlenmedi" in cleaned or "yapılmamış" in cleaned or "gelmedi" in cleaned:
        has_strong_neg = True
        neg += 2
    if any(n in cleaned for n in ("lezzetsiz", "berbat", "soğuk", "bayat", "iğrenç")):
        has_pos_phrase = False
        has_strong_pos = False
        pos = max(0, pos - 2)
    strong_pos = pos >= 2 or has_pos_phrase or has_strong_pos
    strong_neg = neg >= 1 or has_neg_phrase or has_strong_neg
    return pos, neg, strong_pos, strong_neg


def _apply_rule_sentiment(cleaned: str) -> Optional[tuple[str, float]]:
    """Yüksek güvenilir kural tabanlı duygu — leksikon öncesi."""
    if any(w in cleaned for w in ("cozume kavustur", "çözüme kavuştur", "ciddiye aldi", "ciddiye aldı")):
        if not any(w in cleaned for w in ("mad", "med", "olamadi", "olamadı", "olmadi", "olmadı")):
            return "Positive", 0.55
    if "gormemis olabilir" in cleaned or "görmemiş olabilir" in cleaned:
        return "Neutral", 0.0

    # Systemic mediocre / sarcasm / queue classes (config) — never Positive
    try:
        from app.services.clause_pipeline import load_pipeline_config, _any_cue, _fold
        cfg = load_pipeline_config()
        mediocre = cfg.get("mediocre_lexicon") or []
        folded = _fold(cleaned)
        if _any_cue(cleaned, folded, mediocre):
            return "Neutral", float(cfg.get("mediocre_score", -0.12))
        # Queue quantity complaints
        if re.search(r"\d+\s*ki[sş]ilik", cleaned) and any(w in folded for w in ("sira", "kuyruk", "bekle")):
            if not any(w in folded for w in ("beklemiyor", "beklemeden")):
                return "Negative", float(cfg.get("queue_negative_score", -0.55))
        # Positive absence-of-wait must not inherit queue-negative cues ("sıra beklemiyorsunuz")
        positive_wait_absence = any(
            w in folded for w in ("beklemiyor", "beklemeden", "beklemiyorsunuz", "yogun degil", "yoğun değil")
        )
        for key, score_key, default in (
            ("sarcasm_negative_cues", "sarcasm_negative_score", -0.55),
            ("disappointment_negative_cues", "disappointment_negative_score", -0.5),
            ("value_waste_cues", "value_waste_score", -0.6),
            ("staff_language_negative_cues", "staff_language_negative_score", -0.55),
            ("drink_variety_negative_cues", "drink_variety_negative_score", -0.45),
            ("room_noise_negative_cues", "room_noise_negative_score", -0.5),
            ("queue_negative_cues", "queue_negative_score", -0.55),
        ):
            if key == "queue_negative_cues" and positive_wait_absence:
                continue
            if _any_cue(cleaned, folded, cfg.get(key) or []):
                return "Negative", float(cfg.get(score_key, default))
    except Exception:
        logger.warning("Failed in _apply_rule_sentiment checks", exc_info=True)
    if _has_conditional_positive(cleaned):
        return "Positive", 0.40
    if any(p in cleaned for p in (
        "pes edip", "pes edip ciktigimi", "sinekler", "olmüştü", "olmustu",
        "gecik calis", "gecik çalış", "bilmiyorlar", "bulamazsiniz", "bulamazsınız",
        "lekeleri", "kapmaca", "almadan direkt", "calsiz", "çalışsız", "durdu",
        "derinlesiyor", "derinleşiyor", "ciddi mesafeler",
        "parasini carcur", "parasını çarçur", "carcur etmek", "çarçur etmek",
        "diye tuttuk", "turkce bile bilmiyor", "türkçe bile bilmiyor",
        "metre yurumek", "metre yürümek", "kosmak isterseniz", "koşmak isterseniz",
        "guzel bir yani yok", "güzel bir yanı yok", "sira bekleniyor", "sıra bekleniyor",
        "alinamiyor", "alınamıyor", "baglanilamiyor", "bağlanılamıyor",
    )):
        return "Negative", -0.50
    if "18.30" in cleaned or "18 30" in cleaned or "18.00" in cleaned or "18 00" in cleaned:
        return "Negative", -0.45
    if "corbaci" in cleaned or "çorbacı" in cleaned or "corb" in cleaned and "cevril" in cleaned:
        return "Negative", -0.50
    if "oda temizligi geliyor" in cleaned or "oda temizliği geliyor" in cleaned:
        if "almadan" in cleaned or "calmadan" in cleaned or "çalmadan" in cleaned:
            return "Negative", -0.55
    if any(p in cleaned for p in (
        "daha iyi olabilir", "getirilebilir", "ogrenmeleri gerekiyor", "öğrenmeleri gerekiyor",
    )):
        return "Negative", -0.45
    if "cesitlendirilebilir" in cleaned or "çeşitlendirilebilir" in cleaned:
        return "Negative", -0.40
    if any(w in cleaned for w in ("kalitesiz", "yetersiz", "bitiyor", "cikmadi", "çıkmadı", "eksik")):
        return "Negative", -0.50
    if "bakima ihtiyaci" in cleaned or "bakıma ihtiyacı" in cleaned:
        return "Negative", -0.45
    if any(p in cleaned for p in ("sular kesildi", "su kesildi", "su kesintisi")):
        return "Negative", -0.65
    if any(p in cleaned for p in ("bırakılmamış", "birakilmamis", "getirilmedi", "temizlenmedi", "yapılmamış")):
        return "Negative", -0.55
    if "o ne diye" in cleaned:
        return "Negative", -0.60
    if any(w in cleaned for w in ("eglenceliydi", "eğlenceliydi", "eglenceli", "eğlenceli")):
        return "Positive", 0.65
    if "tertemiz" in cleaned:
        return "Positive", 0.60
    if ("yeterliydi" in cleaned or "yeterli" in cleaned.split()) and "beklemiyor" in cleaned:
        return "Positive", 0.55
    if "yardimci oldu" in cleaned or "yardımcı oldu" in cleaned:
        return "Positive", 0.55
    if "olabilir" in cleaned and any(w in cleaned for w in ("daha", "bakimli", "bakımlı", "iyilestir", "iyileştir")):
        return "Negative", -0.40
    return None


def detect_strong_sentiment(text: str) -> tuple[str, float]:
    """
    Metinden duygu etiketi ve skor döner.
    Returns: (Positive|Negative|Neutral, score -1..1)
    """
    cleaned = normalize_turkish(text)
    ruled = _apply_rule_sentiment(cleaned)
    if ruled:
        return ruled
    pos, neg, strong_pos, strong_neg = count_lexicon_hits(cleaned)
    adjustment = (pos - neg) * 0.12
    if any(_phrase_in_text(p, cleaned) for p in POSITIVE_PHRASES):
        adjustment += 0.40
    if any(w in cleaned for w in STRONG_POSITIVE):
        adjustment += 0.35
    # Sarcasm distance: "500 metre yürümek… güzel" must not stay Positive
    if any(p in cleaned for p in ("metre yürümek", "metre yurumek", "koşmak isterseniz", "kosmak isterseniz")):
        if "güzel" in cleaned or "guzel" in cleaned:
            adjustment -= 0.70
    if "güzeldi" in cleaned or "çok güzel" in cleaned:
        if not any(p in cleaned for p in ("metre", "çarçur", "carcur", "yanı yok", "yani yok")):
            adjustment += 0.45
    if "herşey" in cleaned and "güzel" in cleaned:
        adjustment += 0.50
    if any(_phrase_in_text(p, cleaned) for p in NEGATIVE_PHRASES):
        adjustment -= 0.45
    if any(p in cleaned for p in ("çarçur", "carcur", "diye tuttuk", "bilmiyor", "alınamıyor", "alinamiyor")):
        adjustment -= 0.35
    if _has_positive_whitelist(cleaned):
        adjustment += 0.35
    if _has_conditional_positive(cleaned):
        adjustment += 0.40
    if any(p in cleaned for p in ("daha iyi olabilir", "arttırılmalı", "arttirilmali", "cesitlilik arttirilmali")):
        adjustment -= 0.35
    if any(w in cleaned for w in ("kalitesiz", "yetersiz", "zayif", "zayıf", "bulunmuyor", "bulamiyor", "bulamıyor")):
        adjustment -= 0.30
    if any(w in cleaned for w in ("getirilmedi", "getirmediler", "alakasiz", "alakasız", "kaldırılmış", "kapaliydi", "kapalıydı")):
        adjustment -= 0.35
    for pattern in MILD_NEGATIVE_PATTERNS:
        if pattern in cleaned:
            adjustment -= 0.20
    if "olabilir" in cleaned and any(w in cleaned for w in ("daha", "arttir", "arttır", "iyilestir", "iyileştir", "bakimli", "bakımlı")):
        adjustment -= 0.30
    if any(w in cleaned for w in ("bitiyor", "cikmadi", "çıkmadı", "eksik")):
        adjustment -= 0.35
    if ("yeterliydi" in cleaned or "yeterli" in cleaned) and "beklemiyor" in cleaned:
        adjustment += 0.40
    if any(w in cleaned for w in STRONG_NEGATIVE):
        adjustment -= 0.40

    if strong_pos and not strong_neg:
        score = max(0.55, adjustment + 0.50)
    elif strong_neg and not strong_pos:
        score = min(-0.35, adjustment - 0.25)
    elif strong_neg and strong_pos:
        score = adjustment - 0.20 if neg >= pos else adjustment + 0.10
    else:
        score = adjustment if adjustment != 0 else 0.0

    score = max(-1.0, min(1.0, score))
    if score > 0.08:
        label = "Positive"
    elif score < -0.08:
        label = "Negative"
    else:
        label = "Neutral"
    return label, round(score, 2)


def rating_to_score(rating: int) -> float:
    if rating >= 5:
        return 0.9
    if rating == 4:
        return 0.5
    if rating == 3:
        return 0.0
    if rating == 2:
        return -0.5
    return -0.9


def analyze_negative_hyperbole_sentiment(text: str) -> Optional[tuple[str, float]]:
    if not detect_negative_hyperbole(text):
        return None
    if has_positive_idiom(text):
        return None
    cleaned = normalize_turkish(text)
    if re.search(r"bayildim|bayıldım|bayildik|bayıldık", cleaned.replace("ş", "s")):
        if not re.search(r"bayilac|bayilir|olecek|geber", cleaned.replace("ş", "s").replace("ı", "i")):
            return None
    return "Negative", -0.85


def analyze_humor_sentiment(text: str) -> Optional[tuple[str, float]]:
    """Olumsuz görünen ama şaka olan yorumlar için nötr/ hafif olumlu skor."""
    if not detect_humor(text):
        return None
    cleaned = normalize_turkish(text)
    fake_neg = any(
        p in cleaned
        for p in ("asla gelmeyin", "gitmeyin", "pişman", "asla tavsiye", "kaçın", "uzak durun")
    )
    if fake_neg or any(w in cleaned for w in ("asla", "gelmeyin", "pişman")):
        return "Neutral", 0.42
    return "Positive", 0.48


def analyze_short_informal_review(text: str) -> Optional[tuple[str, float]]:
    """Kısa Twitter/sosyal medya tarzı yorumlar için hızlı duygu."""
    cleaned = normalize_turkish(text)
    if len(cleaned.split()) > 10:
        return None
    for phrase, sentiment, weight in SHORT_REVIEW_PATTERNS:
        if phrase in cleaned:
            score = min(1.0, weight / 4.0) if sentiment == "Positive" else max(-1.0, -weight / 4.0)
            return sentiment, round(score, 2)
    if re.search(r"10\s*/\s*10", cleaned):
        return "Positive", 0.95
    if "efsane" in cleaned and "berbat" not in cleaned and "rezalet" not in cleaned:
        return "Positive", 0.80
    if any(p in cleaned for p in ("rezalet la", "berbat la", "çöp gibi", "cop gibi")):
        return "Negative", -0.75
    return None


def analyze_literary_hyperbole_sentiment(text: str) -> Optional[tuple[str, float]]:
    cleaned = normalize_turkish(text)
    for phrase in LITERARY_HYPERBOLE_NEGATIVE:
        if phrase in cleaned:
            return "Negative", -0.70
    for phrase in LITERARY_HYPERBOLE_POSITIVE:
        if phrase in cleaned:
            return "Positive", 0.80
    return None


def analyze_sentiment_with_rating(text: str, rating: Optional[int] = None) -> tuple[str, float]:
    """Metin + opsiyonel puan ile duygu; manipülasyon, mizah, mecaz ve karışık yorum öncelikli."""
    cleaned = normalize_turkish(text)

    if detect_manipulation(text, rating):
        return "Negative", -0.85

    hyperbole = analyze_negative_hyperbole_sentiment(text)
    if hyperbole:
        return hyperbole

    humor = analyze_humor_sentiment(text)
    if humor:
        return humor

    if has_positive_idiom(text):
        return "Positive", 0.85

    literary = analyze_literary_hyperbole_sentiment(text)
    if literary:
        return literary

    short_informal = analyze_short_informal_review(text)
    if short_informal:
        return short_informal

    mixed = analyze_mixed_review(text)
    if mixed.is_mixed and mixed.overall_sentiment and mixed.overall_score is not None:
        return mixed.overall_sentiment, mixed.overall_score

    ruled = _apply_rule_sentiment(cleaned)
    if ruled:
        return ruled

    pos, neg, strong_pos, strong_neg = count_lexicon_hits(cleaned)
    phrase_pos, phrase_neg, _ = score_phrase_patterns(cleaned)
    text_adj = (pos - neg) * 0.12 + (phrase_pos - phrase_neg) * 0.08
    if any(_phrase_in_text(p, cleaned) for p in POSITIVE_PHRASES):
        text_adj += 0.40
    _tokens = tokenize_turkish(cleaned)
    if any(_word_in_text(w, cleaned, _tokens) for w in STRONG_POSITIVE):
        text_adj += 0.35

    if "güzeldi" in cleaned or "çok güzel" in cleaned:
        text_adj += 0.45
    if "herşey" in cleaned and "güzel" in cleaned:
        text_adj += 0.50
    if any(_phrase_in_text(p, cleaned) for p in NEGATIVE_PHRASES):
        text_adj -= 0.45
    if _has_positive_whitelist(cleaned):
        text_adj += 0.35
    if _has_conditional_positive(cleaned):
        text_adj += 0.40
    if any(p in cleaned for p in ("daha iyi olabilir", "arttırılmalı", "arttirilmali", "cesitlilik arttirilmali")):
        text_adj -= 0.35
    if any(w in cleaned for w in ("kalitesiz", "yetersiz", "zayif", "zayıf", "bulunmuyor", "bulamiyor", "bulamıyor", "bitiyor", "cikmadi", "çıkmadı")):
        text_adj -= 0.30
    if any(w in cleaned for w in ("getirilmedi", "getirmediler", "alakasiz", "alakasız", "kaldırılmış", "kapaliydi", "kapalıydı")):
        text_adj -= 0.35
    if "olabilir" in cleaned and any(w in cleaned for w in ("daha", "arttir", "arttır", "iyilestir", "iyileştir", "bakimli", "bakımlı")):
        text_adj -= 0.30
    if ("yeterliydi" in cleaned or "yeterli" in cleaned) and "beklemiyor" in cleaned:
        text_adj += 0.40
    if any(n in cleaned for n in ("asla tavsiye", "hiç beğenmedim")):
        text_adj -= 0.35

    rating_score = rating_to_score(rating) if rating is not None else 0.0

    high_rating_contradiction = False
    if rating is not None and rating >= 4:
        has_pos_negation = any(
            p in cleaned
            for p in (
                "sorun gormedim", "sorun görmedim", "sorun yok", "sorun yasamadim", "sorun yaşamadım",
                "sikayetim yok", "şikayetim yok", "problem yok", "kusur yok", "lezzetliydi", "temizdi"
            )
        )
        if (detect_manipulation(text, rating) or any(s in cleaned for s in SARCASM_INDICATORS) or strong_neg) and not has_pos_negation:
            high_rating_contradiction = True

    low_rating_positive_text = rating is not None and rating <= 2 and strong_pos and not strong_neg

    if high_rating_contradiction:
        score = -0.80
    elif low_rating_positive_text or (strong_pos and not strong_neg and rating is None):
        score = max(0.55, text_adj + 0.50)
    elif low_rating_positive_text or (strong_pos and not strong_neg):
        score = max(0.55, text_adj + 0.50)
    elif strong_neg and not strong_pos:
        score = min(-0.35, text_adj - 0.25)
    elif strong_neg and strong_pos:
        # Uzun karışık yorum: poz/neg dengeli → nötr/karışık
        if abs(pos - neg) <= 3 and len(cleaned.split()) >= 25:
            score = max(-0.15, min(0.25, text_adj * 0.35))
        else:
            score = text_adj - 0.25 if neg >= pos else text_adj + 0.15
    elif rating is not None:
        score = (text_adj * 0.7 + rating_score * 0.3) if strong_pos else rating_score + text_adj
    else:
        score = text_adj if text_adj != 0 else (0.5 if strong_pos else 0.0)

    score = max(-1.0, min(1.0, score))
    if score > 0.10:
        sentiment = "Positive"
    elif score < -0.10:
        sentiment = "Negative"
    else:
        sentiment = "Neutral"
    return sentiment, round(score, 2)


def predict_star_rating(text: str, sentiment: str, sentiment_score: float) -> int:
    if detect_humor(text):
        if sentiment == "Positive" or sentiment_score >= 0.45:
            return 5
        return 4
    cleaned = normalize_turkish(text)
    if has_positive_idiom(text):
        return 5
    _, _, strong_pos, strong_neg = count_lexicon_hits(cleaned)
    if "fena değil" in cleaned or "idare eder" in cleaned:
        return 3

    praise_signals = any(w in cleaned for w in (
        "teşekkür", "tesekkur", "başarılı", "basarili", "iyiydi", "güzeldi", "guzeldi",
        "personel çabaları", "personel cabalari", "italyan restoran",
    ))
    complaint_signals = any(w in cleaned for w in (
        "kuyruk", "pişman", "pisman", "yorucu", "paramız", "paramiz", "çöp", "cop oldu",
        "bulamad", "düşük", "dusuk", "temizletemed",
    ))

    mixed = analyze_mixed_review(text)
    if mixed.is_mixed:
        # Karışık yorumda 5 yıldız yok — şikayet + övgü dengesi
        if sentiment == "Negative" or sentiment_score <= -0.25:
            # Övgü de varsa 1 yıldız fazla sert → 2
            if praise_signals or (mixed.secondary_category and mixed.secondary_category != CAT_OTHER):
                return 2
            return 2 if sentiment_score <= -0.55 or strong_neg else 3
        if sentiment == "Neutral" or sentiment_score < 0.45:
            return 2 if complaint_signals and praise_signals else 3
        return 4

    # Karışık tespit edilmese bile uzun yorumda övgü+şikayet → 2
    if praise_signals and complaint_signals and len(cleaned.split()) >= 40:
        return 2

    if sentiment == "Positive":
        if sentiment_score < 0.45:
            return 3
        return 5 if sentiment_score >= 0.75 or strong_pos else 4
    if sentiment == "Negative":
        if praise_signals and len(cleaned.split()) >= 30:
            return 2
        return 1 if sentiment_score <= -0.75 or (strong_neg and not praise_signals) else 2
    if strong_pos and strong_neg:
        return 3
    if strong_pos:
        return 4
    if strong_neg:
        return 2
    return 3


def detect_contradiction(text: str, rating: Optional[int]) -> bool:
    """Yüksek puan + olumsuz metin, alay veya manipülasyon."""
    if detect_humor(text):
        return False
    if detect_manipulation(text, rating):
        return True
    if rating is None:
        return False
    cleaned = normalize_turkish(text)
    _, neg, _, strong_neg = count_lexicon_hits(cleaned)
    if rating >= 4:
        return any(s in cleaned for s in SARCASM_INDICATORS) or strong_neg or neg >= 2
    if rating <= 2:
        _, _, strong_pos, _ = count_lexicon_hits(cleaned)
        return strong_pos
    return False


# ---------------------------------------------------------------------------
# Kategori sınıflandırma (category_rules delegasyonu)
# ---------------------------------------------------------------------------
def classify_by_keywords(text: str) -> tuple[str, float]:
    """Geriye uyumluluk — deterministik category_rules."""
    from app.services.category_rules import classify_by_rules
    result = classify_by_rules(text)
    return result.category, result.confidence


def classify_by_keywords_with_method(text: str) -> tuple[str, float, str]:
    from app.services.category_rules import classify_by_rules
    result = classify_by_rules(text)
    return result.category, result.confidence, result.method


def extract_keywords(text: str, max_keywords: int = 3) -> list[str]:
    cleaned = normalize_turkish(text)
    is_humor = detect_humor(text)
    tokens = tokenize_turkish(text)
    if not tokens:
        return []
    word_scores: dict[str, float] = {}
    for word in tokens:
        score = 1.0
        if word in HOTEL_TERMS or word in KEEP_WORDS:
            score += 4
        if word in STRONG_POSITIVE or word in {"beğendim", "beğendik", "lezzet", "temiz", "kirli", "keyiften", "keyif", "burada"}:
            score += 3
        if word in STRONG_NEGATIVE or word in {
            "sıra", "sira", "kuyruk", "şezlong", "sezlong", "yalıtım", "yalitim",
            "tekila", "wifi", "çarçur", "carcur", "dakika", "alkol", "içecek", "icecek",
            "bar", "aktivite", "baglan", "bağlan",
        }:
            score += 5
        if is_humor and (
            word in {"saka", "şaka", "espri", "ironik", "troll", "asla", "gelmeyin"}
            or "saka" in word.replace("ş", "s")
            or "espri" in word
        ):
            score += 8
        word_scores[word] = word_scores.get(word, 0) + score

    # Mizah yorumlarında anlamlı kelimeleri önceliklendir (kök birleşimlerini ele)
    if is_humor:
        preferred = []
        for cand in ("asla", "gelmeyin", "saka", "şaka", "espri", "ironik"):
            for tok in tokens:
                tok_ascii = tok.replace("ş", "s").replace("ı", "i")
                cand_ascii = cand.replace("ş", "s").replace("ı", "i")
                if (cand_ascii in tok_ascii or tok_ascii == cand_ascii) and len(tok) <= len(cand) + 3:
                    if tok not in preferred:
                        preferred.append(tok)
                    break
        sorted_words = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)
        result: list[str] = []
        for w in preferred:
            if w not in result:
                result.append(w)
        for word, _ in sorted_words:
            if word not in result and len(word) >= 3:
                result.append(word)
            if len(result) >= max_keywords:
                break
        return result[:max_keywords]

    sorted_words = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)
    result: list[str] = []
    for word, _ in sorted_words:
        if word not in result:
            result.append(word)
        if len(result) >= max_keywords:
            break
    return result


# ---------------------------------------------------------------------------
# Leksikon genişletmesi (simulation/hotel_phrase_lexicon.json)
# ---------------------------------------------------------------------------
def _apply_lexicon_extensions() -> None:
    try:
        from app.services.lexicon_loader import merge_category_keywords, merge_phrase_lists

        global POSITIVE_PHRASES, NEGATIVE_PHRASES, NEGATIVE_HYPERBOLE
        global JOKE_MARKERS, JOKE_CONTEXT_MARKERS, MANIPULATION_PATTERNS
        global MIXED_REVIEW_SPLITTERS, POSITIVE_IDIOMS, CATEGORY_KEYWORDS
        global TWITTER_SLANG_POSITIVE, TWITTER_SLANG_NEGATIVE
        global LITERARY_HYPERBOLE_POSITIVE, LITERARY_HYPERBOLE_NEGATIVE
        global HOTEL_TERMS, DEPT_HINTS

        POSITIVE_PHRASES = merge_phrase_lists(POSITIVE_PHRASES, "positive_phrases")
        NEGATIVE_PHRASES = merge_phrase_lists(NEGATIVE_PHRASES, "negative_phrases")
        NEGATIVE_HYPERBOLE = merge_phrase_lists(NEGATIVE_HYPERBOLE, "negative_hyperbole")
        JOKE_MARKERS = merge_phrase_lists(JOKE_MARKERS, "joke_markers")
        JOKE_CONTEXT_MARKERS = merge_phrase_lists(JOKE_CONTEXT_MARKERS, "joke_context_markers")
        MANIPULATION_PATTERNS = merge_phrase_lists(MANIPULATION_PATTERNS, "manipulation_patterns")
        MIXED_REVIEW_SPLITTERS = merge_phrase_lists(MIXED_REVIEW_SPLITTERS, "mixed_review_splitters")
        POSITIVE_IDIOMS = merge_phrase_lists(POSITIVE_IDIOMS, "positive_idioms")
        TWITTER_SLANG_POSITIVE = merge_phrase_lists(TWITTER_SLANG_POSITIVE, "twitter_slang_positive")
        TWITTER_SLANG_NEGATIVE = merge_phrase_lists(TWITTER_SLANG_NEGATIVE, "twitter_slang_negative")
        LITERARY_HYPERBOLE_POSITIVE = merge_phrase_lists(LITERARY_HYPERBOLE_POSITIVE, "literary_hyperbole_positive")
        LITERARY_HYPERBOLE_NEGATIVE = merge_phrase_lists(LITERARY_HYPERBOLE_NEGATIVE, "literary_hyperbole_negative")
        MIXED_REVIEW_SPLITTERS = merge_phrase_lists(MIXED_REVIEW_SPLITTERS, "mixed_review_splitters")
        CATEGORY_KEYWORDS = merge_category_keywords(CATEGORY_KEYWORDS)

        HOTEL_TERMS = set().union(*CATEGORY_KEYWORDS.values()) | {
            "güzel", "güzeldi", "harika", "mükemmel", "bayıldım", "bayıldık", "beğendim", "beğendik", "kötü", "berbat",
            "herşey", "hersey", "çok", "lezzet", "temiz", "kirli", "keyiften", "keyif", "burada", "ölebilirim", "klima", "havuz",
        }
        DEPT_HINTS.update(w for w in HOTEL_TERMS if len(w) >= 4)
    except Exception:
        logger.warning("Failed to apply lexicon extensions", exc_info=True)


def _apply_encyclopedia_extensions() -> None:
    """8M veriden uretilen terminoloji ansiklopedisini NLP sozluklerine birlestir.
    
    NOT: Sentiment sozlukleri (STRONG_POSITIVE, STRONG_NEGATIVE, PHRASE_SENTIMENT_WEIGHTS vb.)
    egitim verisindeki guvenilmez etiketlerden olumsuz etkilendigi icin devre disi birakildi.
    Sadece kategori keywordleri ve hotel terimleri eklenir.
    """
    try:
        from app.services.encyclopedia_loader import (
            get_category_keywords
        )

        global CATEGORY_KEYWORDS, HOTEL_TERMS, DEPT_HINTS

        CATEGORY_KEYWORDS = get_category_keywords(CATEGORY_KEYWORDS)

        HOTEL_TERMS = set().union(*CATEGORY_KEYWORDS.values()) | {
            "güzel", "güzeldi", "harika", "mükemmel", "bayıldım", "bayıldık", "beğendim", "beğendik", "kötü", "berbat",
            "herşey", "hersey", "çok", "lezzet", "temiz", "kirli", "keyiften", "keyif", "burada", "ölebilirim", "klima", "havuz",
            "efsane", "rezalet", "fiyasko",
        }
        DEPT_HINTS.update(w for w in HOTEL_TERMS if len(w) >= 4)
    except Exception:
        logger.warning("Failed to apply encyclopedia extensions", exc_info=True)


_apply_lexicon_extensions()
_apply_encyclopedia_extensions()
