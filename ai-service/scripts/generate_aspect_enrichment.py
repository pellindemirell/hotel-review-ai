#!/usr/bin/env python3
"""Generate companion aspect enrichment metadata for all keys in aspects.yaml.

Does NOT modify aspects.yaml keys. Writes:
  ai-service/config/ontology/aspect_enrichment.yaml

Includes: aliases, synonyms, multilingual, typos, slang, sentiment cues,
examples, confused_with, ops fields.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("PyYAML required", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
ASPECTS_PATH = ROOT / "config" / "ontology" / "aspects.yaml"
OUT_PATH = ROOT / "config" / "ontology" / "aspect_enrichment.yaml"

# Token → multilingual guest phrases (TR richest)
TOKEN_PHRASES: dict[str, dict[str, list[str]]] = {
    "cleanliness": {
        "tr": ["temizlik", "hijyen", "temiz", "kirli", "pis", "tozlu"],
        "en": ["cleanliness", "hygiene", "dirty", "filthy", "spotless"],
        "de": ["sauberkeit", "schmutzig"],
        "ru": ["чистота", "грязно"],
        "ar": ["نظافة", "وسخ"],
    },
    "clean": {
        "tr": ["temiz", "tertemiz", "hijyenik"],
        "en": ["clean", "spotless"],
        "de": ["sauber"],
        "ru": ["чистый"],
        "ar": ["نظيف"],
    },
    "smell": {
        "tr": ["koku", "kokuyor", "kötü koku", "koku var"],
        "en": ["smell", "odor", "stinks", "musty"],
        "de": ["geruch", "riecht"],
        "ru": ["запах", "воняет"],
        "ar": ["رائحة"],
    },
    "odor": {
        "tr": ["koku", "kokusu", "kötü koku"],
        "en": ["odor", "smell", "stench"],
        "de": ["geruch"],
        "ru": ["запах"],
        "ar": ["رائحة"],
    },
    "noise": {
        "tr": ["gürültü", "ses", "gürültülü", "sessiz"],
        "en": ["noise", "noisy", "loud", "quiet"],
        "de": ["lärm", "laut"],
        "ru": ["шум", "шумный"],
        "ar": ["ضوضاء"],
    },
    "size": {
        "tr": ["boyut", "büyük", "küçük", "dar", "geniş"],
        "en": ["size", "spacious", "tiny", "cramped"],
        "de": ["größe", "klein"],
        "ru": ["размер", "тесный"],
        "ar": ["حجم"],
    },
    "comfort": {
        "tr": ["rahat", "konfor", "rahatlık"],
        "en": ["comfort", "comfortable", "cozy"],
        "de": ["komfort", "bequem"],
        "ru": ["комфорт"],
        "ar": ["راحة"],
    },
    "quality": {
        "tr": ["kalite", "kaliteli", "kalitesiz"],
        "en": ["quality", "poor quality"],
        "de": ["qualität"],
        "ru": ["качество"],
        "ar": ["جودة"],
    },
    "temperature": {
        "tr": ["sıcaklık", "sıcak", "soğuk", "ılık"],
        "en": ["temperature", "hot", "cold", "warm"],
        "de": ["temperatur", "heiß", "kalt"],
        "ru": ["температура", "жарко", "холодно"],
        "ar": ["درجة الحرارة"],
    },
    "pressure": {
        "tr": ["basınç", "su basıncı", "zayıf su", "güçlü su"],
        "en": ["pressure", "water pressure", "weak flow"],
        "de": ["wasserdruck"],
        "ru": ["напор воды"],
        "ar": ["ضغط الماء"],
    },
    "speed": {
        "tr": ["hız", "yavaş", "hızlı", "gecikme"],
        "en": ["speed", "slow", "fast", "lag"],
        "de": ["geschwindigkeit", "langsam"],
        "ru": ["скорость", "медленно"],
        "ar": ["سرعة"],
    },
    "coverage": {
        "tr": ["kapsama", "çekmiyor", "sinyal"],
        "en": ["coverage", "signal", "dead zone"],
        "de": ["abdeckung", "empfang"],
        "ru": ["покрытие", "сигнал"],
        "ar": ["تغطية"],
    },
    "behavior": {
        "tr": ["davranış", "tavır", "tutum", "kaba", "kibar"],
        "en": ["behavior", "attitude", "rude", "polite"],
        "de": ["verhalten", "unhöflich"],
        "ru": ["поведение", "грубый"],
        "ar": ["سلوك"],
    },
    "helpfulness": {
        "tr": ["yardımsever", "ilgili", "ilgisiz"],
        "en": ["helpful", "unhelpful", "attentive"],
        "de": ["hilfsbereit"],
        "ru": ["отзывчивый"],
        "ar": ["متعاون"],
    },
    "queue": {
        "tr": ["kuyruk", "sıra", "bekleme", "kalabalık"],
        "en": ["queue", "wait", "line", "crowded"],
        "de": ["schlange", "warten"],
        "ru": ["очередь", "ожидание"],
        "ar": ["طابور"],
    },
    "hygiene": {
        "tr": ["hijyen", "hijyenik", "sağlık"],
        "en": ["hygiene", "unsanitary"],
        "de": ["hygiene"],
        "ru": ["гигиена"],
        "ar": ["نظافة"],
    },
    "mold": {
        "tr": ["küf", "mantar", "küflü"],
        "en": ["mold", "mould", "mildew"],
        "de": ["schimmel"],
        "ru": ["плесень"],
        "ar": ["عفن"],
    },
    "leak": {
        "tr": ["sızıntı", "akıyor", "su kaçağı"],
        "en": ["leak", "leaking", "drip"],
        "de": ["undicht", "leck"],
        "ru": ["протечка"],
        "ar": ["تسرب"],
    },
    "drain": {
        "tr": ["gider", "tıkanık", "akmıyor"],
        "en": ["drain", "clogged", "blocked"],
        "de": ["abfluss", "verstopft"],
        "ru": ["сток", "засор"],
        "ar": ["مصرف"],
    },
    "cooling": {
        "tr": ["soğutma", "soğutmuyor", "klima soğuk vermiyor"],
        "en": ["cooling", "not cooling", "AC warm"],
        "de": ["kühlung"],
        "ru": ["охлаждение"],
        "ar": ["تبريد"],
    },
    "heating": {
        "tr": ["ısıtma", "ısıtmıyor", "kalorifer"],
        "en": ["heating", "not heating", "radiator"],
        "de": ["heizung"],
        "ru": ["отопление"],
        "ar": ["تدفئة"],
    },
    "wifi": {
        "tr": ["wifi", "wi-fi", "internet", "kablosuz"],
        "en": ["wifi", "wi-fi", "wireless", "internet"],
        "de": ["wlan", "wifi"],
        "ru": ["вайфай", "wifi"],
        "ar": ["واي فاي"],
    },
    "linen": {
        "tr": ["çarşaf", "nevresim", "yatak örtüsü"],
        "en": ["linen", "sheets", "bedding"],
        "de": ["bettwäsche"],
        "ru": ["белье", "простыни"],
        "ar": ["ملاءات"],
    },
    "pillow": {
        "tr": ["yastık", "yastıklar"],
        "en": ["pillow", "pillows"],
        "de": ["kissen"],
        "ru": ["подушка"],
        "ar": ["وسادة"],
    },
    "mattress": {
        "tr": ["yatak", "minder", "sünger"],
        "en": ["mattress"],
        "de": ["matratze"],
        "ru": ["матрас"],
        "ar": ["مرتبة"],
    },
    "towel": {
        "tr": ["havlu", "havlular"],
        "en": ["towel", "towels"],
        "de": ["handtuch"],
        "ru": ["полотенце"],
        "ar": ["منشفة"],
    },
    "shower": {
        "tr": ["duş", "duş başlığı"],
        "en": ["shower"],
        "de": ["dusche"],
        "ru": ["душ"],
        "ar": ["دوش"],
    },
    "toilet": {
        "tr": ["tuvalet", "klozet", "wc"],
        "en": ["toilet", "wc", "bathroom"],
        "de": ["toilette"],
        "ru": ["туалет"],
        "ar": ["مرحاض"],
    },
    "pool": {
        "tr": ["havuz", "yüzme havuzu"],
        "en": ["pool", "swimming pool"],
        "de": ["pool", "schwimmbad"],
        "ru": ["бассейн"],
        "ar": ["مسبح"],
    },
    "beach": {
        "tr": ["plaj", "sahil", "kumsal"],
        "en": ["beach", "shore"],
        "de": ["strand"],
        "ru": ["пляж"],
        "ar": ["شاطئ"],
    },
    "staff": {
        "tr": ["personel", "çalışanlar", "görevli"],
        "en": ["staff", "employees", "crew"],
        "de": ["personal", "mitarbeiter"],
        "ru": ["персонал", "сотрудники"],
        "ar": ["طاقم", "موظفون"],
    },
    "food": {
        "tr": ["yemek", "yemekler", "yiyecek"],
        "en": ["food", "meal", "cuisine"],
        "de": ["essen", "speisen"],
        "ru": ["еда", "кухня"],
        "ar": ["طعام"],
    },
    "breakfast": {
        "tr": ["kahvaltı", "kahvaltı büfesi"],
        "en": ["breakfast", "breakfast buffet"],
        "de": ["frühstück"],
        "ru": ["завтрак"],
        "ar": ["فطور"],
    },
    "buffet": {
        "tr": ["büfe", "açık büfe"],
        "en": ["buffet"],
        "de": ["buffet"],
        "ru": ["шведский стол"],
        "ar": ["بوفيه"],
    },
    "checkin": {
        "tr": ["check-in", "giriş", "resepsiyon giriş"],
        "en": ["check-in", "checkin", "arrival"],
        "de": ["check-in", "einchecken"],
        "ru": ["заселение"],
        "ar": ["تسجيل الوصول"],
    },
    "checkout": {
        "tr": ["check-out", "çıkış"],
        "en": ["check-out", "checkout", "departure"],
        "de": ["check-out", "auschecken"],
        "ru": ["выселение"],
        "ar": ["تسجيل المغادرة"],
    },
}

# Aspect-key fragment → pos/neg cue banks
FRAGMENT_CUES: dict[str, dict[str, list[str]]] = {
    "clean": {
        "pos": ["temiz", "tertemiz", "spotless", "hijyenik", "immaculate", "lekesiz"],
        "neg": ["kirli", "pis", "tozlu", "leke", "dirty", "filthy", "hijyenik değil"],
    },
    "smell": {
        "pos": ["güzel koku", "ferah", "fresh smell", "kokusu yok"],
        "neg": ["kötü koku", "kokuyor", "rutubet", "küf kokusu", "stinks", "musty"],
    },
    "odor": {
        "pos": ["ferah", "temiz koku", "no odor"],
        "neg": ["kötü koku", "sigara kokusu", "kimyasal koku", "lağım kokusu", "reek"],
    },
    "noise": {
        "pos": ["sessiz", "sakin", "quiet", "huzurlu"],
        "neg": ["gürültülü", "ses geliyor", "noisy", "loud", "uyuyamadık"],
    },
    "size": {
        "pos": ["geniş", "ferah", "spacious", "büyük"],
        "neg": ["küçük", "dar", "cramped", "tiny", "basık"],
    },
    "comfort": {
        "pos": ["rahat", "konforlu", "comfortable", "yumuşak"],
        "neg": ["rahatsız", "sert", "uncomfortable", "acıyor"],
    },
    "quality": {
        "pos": ["kaliteli", "iyi", "excellent", "üst düzey"],
        "neg": ["kalitesiz", "kötü", "poor", "ucuz malzeme"],
    },
    "temperature": {
        "pos": ["ideal sıcaklık", "tam ayar", "comfortable temp"],
        "neg": ["çok sıcak", "çok soğuk", "ayarlanmıyor", "boğucu"],
    },
    "pressure": {
        "pos": ["güçlü su", "iyi basınç", "strong pressure"],
        "neg": ["zayıf su", "damlıyor", "weak pressure", "su gelmiyor"],
    },
    "speed": {
        "pos": ["hızlı", "çabuk", "fast", "smooth"],
        "neg": ["yavaş", "geç", "slow", "laggy", "donuyor"],
    },
    "behavior": {
        "pos": ["kibar", "güler yüzlü", "friendly", "nazik"],
        "neg": ["kaba", "ilgisiz", "rude", "suratsız", "saygısız"],
    },
    "helpfulness": {
        "pos": ["yardımsever", "ilgili", "helpful", "çözüm odaklı"],
        "neg": ["ilgisiz", "yardım etmedi", "unhelpful", "umursamaz"],
    },
    "shortage": {
        "pos": ["yeterli personel", "well staffed"],
        "neg": ["personel yetersiz", "kimse yok", "understaffed", "eksik kadro"],
    },
    "queue": {
        "pos": ["sıra yok", "bekletmeden", "no wait"],
        "neg": ["uzun kuyruk", "çok bekledik", "long queue", "saatlerce"],
    },
    "cooling": {
        "pos": ["iyi soğutuyor", "serin", "cooling well"],
        "neg": ["soğutmuyor", "sıcak üflüyor", "not cooling", "klima çalışmıyor"],
    },
    "heating": {
        "pos": ["iyi ısıtıyor", "sıcak tutuyor"],
        "neg": ["ısıtmıyor", "buz gibi", "not heating"],
    },
    "mold": {
        "pos": ["küf yok", "temiz duvar"],
        "neg": ["küf var", "mantar", "mold", "siyah lekeler"],
    },
    "leak": {
        "pos": ["sızıntı yok"],
        "neg": ["akıyor", "sızıntı", "damlıyor", "leaking"],
    },
    "wifi": {
        "pos": ["hızlı internet", "iyi çekiyor", "stable wifi"],
        "neg": ["internet yok", "yavaş wifi", "kopuyor", "çekmiyor"],
    },
    "taste": {
        "pos": ["lezzetli", "çok güzel", "delicious", "tadı harika"],
        "neg": ["tatsız", "bayat", "bland", "kötü tat"],
    },
    "hygiene": {
        "pos": ["hijyenik", "sağlıklı"],
        "neg": ["hijyen sorunlu", "böcek", "unsanitary", "kirli tabak"],
    },
    "variety": {
        "pos": ["çeşit bol", "seçenek çok", "great variety"],
        "neg": ["çeşit az", "hep aynı", "limited options"],
    },
    "portion": {
        "pos": ["porsiyon doyurucu", "generous portion"],
        "neg": ["porsiyon küçük", "az geldi", "tiny portion"],
    },
    "freshness": {
        "pos": ["taze", "fresh"],
        "neg": ["bayat", "eski", "stale", "solmuş"],
    },
    "safety": {
        "pos": ["güvenli", "safe"],
        "neg": ["güvensiz", "tehlikeli", "unsafe"],
    },
    "crowd": {
        "pos": ["sakin", "kalabalık değil"],
        "neg": ["aşırı kalabalık", "packed", "yer yok"],
    },
    "clarity": {
        "pos": ["berrak", "clear water"],
        "neg": ["bulanık", "yeşil su", "cloudy"],
    },
    "chlorine": {
        "pos": ["klor dengeli"],
        "neg": ["aşırı klor", "göz yakıyor", "chlorine sting"],
    },
}

CATEGORY_OPS: dict[str, dict[str, list[str]]] = {
    "ROOM": {
        "related_processes": ["oda hazırlık", "housekeeping denetim", "oda denetimi"],
        "related_sop": ["HK oda temizlik SOP", "oda check SOP"],
        "related_root_causes": [
            "eksik temizlik turu",
            "malzeme/ekipman arızası",
            "önceki misafir hasarı",
            "bakım gecikmesi",
            "ventilasyon yetersiz",
        ],
        "related_actions": [
            "oda yeniden temizlensin",
            "teknik iş emri açılsın",
            "oda değişimi teklif edilsin",
            "supervisor denetimi",
            "misafire takip mesajı",
        ],
    },
    "BED": {
        "related_processes": ["yatak hazırlama", "çarşaf değişimi", "turndown"],
        "related_sop": ["bedding change SOP", "yatak setup SOP"],
        "related_root_causes": [
            "eski yatak/minder",
            "yanlış yastık tipi",
            "çarşaf stok/kalite",
            "alerjen örtü eksik",
            "kurulum hatası",
        ],
        "related_actions": [
            "yastık menüsü sunulsun",
            "çarşaf değiştirilsin",
            "yatak/oda değiştirilsin",
            "topper eklensin",
            "alerjen örtü takılsın",
        ],
    },
    "BATHROOM": {
        "related_processes": ["banyo temizlik", "tesisat bakım", "amenities refill"],
        "related_sop": ["banyo hijyen SOP", "su basıncı kontrol SOP"],
        "related_root_causes": [
            "yetersiz banyo temizliği",
            "tıkanık gider",
            "sıcak su kazan/hat sorunu",
            "amenities stok",
            "havalandırma arızası",
        ],
        "related_actions": [
            "banyo derin temizlik",
            "tesisat iş emri",
            "amenities yenile",
            "havlu değiştir",
            "oda/banyo değişimi",
        ],
    },
    "HVAC": {
        "related_processes": ["klima arıza", "filtre bakımı", "BMS kontrol"],
        "related_sop": ["HVAC guest complaint SOP", "filtre PM SOP"],
        "related_root_causes": [
            "filtre kirli",
            "gaz/soğutma arızası",
            "termostat hatası",
            "dış ünite arızası",
            "yanlış mod ayarı",
        ],
        "related_actions": [
            "teknik odaya gitsin",
            "filtre değiştirilsin",
            "geçici vantilatör",
            "oda değişimi",
            "setpoint/mod ayarı anlatılsın",
        ],
    },
    "INTERNET": {
        "related_processes": ["wifi destek", "AP kapasite", "captive portal"],
        "related_sop": ["IT guest wifi SOP", "bandwidth fair-use SOP"],
        "related_root_causes": [
            "AP yoğunluğu",
            "yanlış şifre/portal",
            "bandwidth limit",
            "ölü nokta",
            "DNS/ISP kesintisi",
        ],
        "related_actions": [
            "IT ticket açılsın",
            "AP restart/kanal",
            "ethernet alternatif",
            "premium wifi teklif",
            "cihaz limit artır",
        ],
    },
    "FOOD": {
        "related_processes": ["mutfak üretim", "büfe refill", "alerjen bilgilendirme"],
        "related_sop": ["F&B hijyen SOP", "sıcaklık kontrol SOP", "alerjen SOP"],
        "related_root_causes": [
            "üretim kalite kontrol eksik",
            "sıcak tutma/soğuk zincir",
            "çeşit planlama zayıf",
            "personel yetersiz",
            "etiket/alerjen bilgi eksik",
        ],
        "related_actions": [
            "şef bilgilendirilsin",
            "ürün değiştirilsin",
            "refill hızlandırılsın",
            "kompansasyon/ikram",
            "hijyen denetimi",
        ],
    },
    "STAFF": {
        "related_processes": ["misafir ilişkileri", "şikayet yönetimi", "eğitim"],
        "related_sop": ["guest complaint SOP", "service recovery SOP"],
        "related_root_causes": [
            "eğitim eksikliği",
            "aşırı iş yükü",
            "dil yetersizliği",
            "motivasyon/tutum",
            "süreç belirsizliği",
        ],
        "related_actions": [
            "özür + çözüm",
            "duty manager müdahalesi",
            "eğitim kaydı",
            "kompansasyon",
            "vardiya takviyesi",
        ],
    },
    "POOL": {
        "related_processes": ["havuz kimyasal", "şezlong yönetimi", "can kurtaran"],
        "related_sop": ["pool chemistry SOP", "beach/pool safety SOP"],
        "related_root_causes": [
            "kimyasal dengesizlik",
            "kapasite aşımı",
            "bakım gecikmesi",
            "havlu/şezlong eksik",
            "gölgelik yetersiz",
        ],
        "related_actions": [
            "kimyasal ölçüm/düzeltme",
            "şezlong rezervasyon netleştir",
            "havlu servisi artır",
            "bakım iş emri",
            "can kurtaran pozisyon kontrol",
        ],
    },
    "OPERATIONS": {
        "related_processes": ["ön büro operasyon", "rezervasyon", "kapasite yönetimi"],
        "related_sop": ["check-in/out SOP", "overbooking SOP", "billing SOP"],
        "related_root_causes": [
            "süreç yavaşlığı",
            "bilgi/OTA uyumsuzluğu",
            "kadrosuzluk",
            "sistem/POS arızası",
            "yanlış rezervasyon notu",
        ],
        "related_actions": [
            "duty manager bilgilendir",
            "süreç hızlandır",
            "ücret/fatura düzelt",
            "oda/upgrade teklif",
            "kompansasyon + takip",
        ],
    },
}

CATEGORY_SLANG: dict[str, dict[str, list[str]]] = {
    "ROOM": {
        "tr": ["oda rezalet", "oda bomboş gibi", "oda efsane", "oda berbat", "tam bir hayal kırıklığı"],
        "en": ["room was a dump", "room slapped", "room was mid", "absolute wreck of a room"],
    },
    "BED": {
        "tr": ["yatak tahta gibi", "yatak bulut gibi", "sırtım mahvoldu", "yastık yok hükmünde"],
        "en": ["bed was a rock", "slept like a baby", "mattress was trash"],
    },
    "BATHROOM": {
        "tr": ["banyo iğrenç", "duştan damlıyor", "tuvalet felaket", "banyo okey"],
        "en": ["bathroom was gross", "shower was pathetic", "bath was decent"],
    },
    "HVAC": {
        "tr": ["klima ölmüş", "klima ful çalışıyor", "oda fırın gibi", "buzdolabı gibi"],
        "en": ["AC is dead", "AC blasting", "sauna in here", "freezer vibes"],
    },
    "INTERNET": {
        "tr": ["internet yok hükmünde", "wifi kaplumbağa", "net uçuyor", "wifi şaka gibi"],
        "en": ["wifi is a joke", "net crawling", "wifi blazing", "dead wifi"],
    },
    "FOOD": {
        "tr": ["yemek efsane", "yemek rezalet", "büfe bomboş", "lezzet şahane", "yemek mid"],
        "en": ["food slapped", "food was mid", "buffet was trash", "meals were fire"],
    },
    "STAFF": {
        "tr": ["personel süper", "personel surat asık", "ilgi sıfır", "adamlar çok iyi"],
        "en": ["staff were legends", "staff ghosted us", "zero vibes from staff"],
    },
    "POOL": {
        "tr": ["havuz harika", "havuz çorba gibi", "şezlong savaşı", "plaj efsane"],
        "en": ["pool was fire", "pool soup", "sunbed war", "beach slapped"],
    },
    "OPERATIONS": {
        "tr": ["check-in işkence", "işler tıkırında", "resepsiyon kaos", "organizasyon sıfır"],
        "en": ["check-in nightmare", "ops on point", "front desk chaos"],
    },
}

GENERIC_POS = ["iyi", "güzel", "harika", "mükemmel", "süper", "great", "excellent", "perfect"]
GENERIC_NEG = ["kötü", "berbat", "rezalet", "felaket", "kötüydü", "bad", "terrible", "awful", "poor"]

TR_SLANG_POS = ["efsane", "şahane", "full puan", "bayıldık", "çok iyiydi"]
TR_SLANG_NEG = ["rezalet", "berbat", "çok kötü", "hayal kırıklığı", "yazık"]
EN_SLANG_POS = ["slapped", "fire", "solid", "on point"]
EN_SLANG_NEG = ["mid", "trash", "a joke", "rough"]

# Known confusion clusters (only keys that exist will be kept)
CONFUSION_HINTS: dict[str, list[str]] = {
    "room_cleanliness": ["room_smell", "room_carpet_stain", "bathroom_cleanliness", "room_mold"],
    "room_smell": ["room_odor_smoke", "room_odor_chemical", "room_odor_sewage", "room_mold_smell", "room_dampness"],
    "room_odor_smoke": ["room_smell", "room_smoking_policy"],
    "room_noise": ["room_noise_hallway", "room_noise_neighbors", "room_noise_street", "room_soundproof"],
    "room_noise_neighbors": ["room_noise", "room_wall_thin", "room_soundproofing"],
    "room_size": ["room_size_small", "room_layout", "room_storage_space"],
    "room_temperature": ["room_temperature_control", "hvac_temperature", "hvac_too_hot", "hvac_too_cold"],
    "room_wifi_signal": ["wifi_coverage", "wifi_room", "wifi_room_dead_zone"],
    "bed_comfort": ["mattress_quality", "bed_too_soft", "bed_too_firm", "bed_sagging"],
    "bed_linen": ["sheet_stain", "bed_linen_smell", "bed_linen_rough", "bed_stain"],
    "pillow_quality": ["pillow_firmness", "pillow_too_high", "pillow_too_flat", "pillow_smell"],
    "mattress_quality": ["bed_comfort", "mattress_firmness", "bed_too_soft", "bed_too_firm"],
    "bed_bug_concern": ["bed_bug_inspection", "room_insects", "room_pest_control"],
    "bathroom_cleanliness": ["shower_glass_clean", "bathtub_cleanliness", "bathroom_hair", "bathroom_mold"],
    "shower_pressure": ["shower_pressure_low", "shower_pressure_high", "bathroom_water_pressure_general", "faucet_pressure"],
    "hot_water": ["hot_water_wait", "hot_water_runout", "shower_temperature"],
    "bathroom_smell": ["bathroom_drain_smell", "bathroom_mold", "room_odor_sewage"],
    "bathroom_mold": ["shower_curtain_mold", "bathroom_tile_grout_mold", "bathroom_grout"],
    "towel_quality": ["bathroom_towel_quality", "bathroom_towel_stock", "bathroom_towel_stain"],
    "hvac_cooling": ["hvac_not_cooling", "hvac_too_hot", "hvac_slow_cool", "room_temperature"],
    "hvac_heating": ["hvac_not_heating", "hvac_too_cold", "hvac_slow_heat"],
    "hvac_noise": ["hvac_night_noise", "hvac_fan_noise", "hvac_rattle", "hvac_vibration"],
    "hvac_smell_burning": ["hvac_smell_burn", "hvac_smell_plastic", "hvac_odor_mold"],
    "hvac_filter": ["hvac_filter_dirty", "hvac_dust_blow", "hvac_allergy_filter"],
    "wifi_speed": ["wifi_slow_evening", "wifi_download", "wifi_upload", "wifi_latency"],
    "wifi_coverage": ["wifi_room_dead_zone", "wifi_pool_coverage", "wifi_beach_coverage", "room_wifi_signal"],
    "wifi_login": ["wifi_password_issue", "wifi_captive_portal", "wifi_sms_code", "wifi_room_number_auth"],
    "wifi_stability": ["wifi_disconnect", "wifi_roaming"],
    "food_quality": ["food_taste", "food_freshness", "buffet_quality", "food_hygiene"],
    "food_taste": ["food_quality", "food_spice_level", "meat_quality"],
    "food_hygiene": ["buffet_hygiene", "table_cleanliness", "fly_insect_food", "food_poisoning_concern"],
    "food_temperature": ["food_temperature_hot", "food_temperature_cold", "room_service_temperature"],
    "breakfast_variety": ["breakfast_quality", "buffet_quality", "food_variety"],
    "food_queue": ["breakfast_queue", "buffet_crowd", "bar_queue"],
    "staff_behavior": ["staff_attitude_front", "staff_friendliness", "staff_front_desk_attitude"],
    "staff_helpfulness": ["staff_proactivity", "staff_attentiveness", "staff_problem_solving"],
    "staff_shortage": ["staff_overwork", "staff_overworked", "staff_availability"],
    "reception_service": ["staff_checkin_speed", "staff_front_desk_attitude", "ops_checkin_process"],
    "pool_cleanliness": ["pool_water_clarity", "pool_algae", "pool_chemical_balance", "pool_chlorine_smell"],
    "pool_lounger": ["pool_sunbed", "pool_sunbed_reservation", "pool_shade"],
    "pool_crowd": ["pool_aquapark_queue", "beach_crowd"],
    "beach_quality": ["beach_cleanliness", "beach_sand_quality", "beach_access"],
    "ops_checkin_process": ["ops_online_checkin", "staff_checkin_speed", "ops_queue_lobby"],
    "ops_checkout_process": ["staff_checkout_speed", "ops_late_checkout"],
    "ops_value_for_money": ["ops_extra_charges", "ops_rate_transparency"],
    "ops_overbooking": ["ops_walk_to_other_hotel", "ops_room_assignment"],
}


def _uniq(items: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        s = (x or "").strip()
        if not s:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if limit is not None and len(out) >= limit:
            break
    return out


def _fold_tr(s: str) -> str:
    t = s.casefold()
    for a, b in (("ş", "s"), ("ı", "i"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("ç", "c")):
        t = t.replace(a, b)
    return t


def _turkish_typos(phrase: str) -> list[str]:
    """Generate light Turkish misspelling variants."""
    out: list[str] = []
    folded = _fold_tr(phrase)
    if folded != phrase.casefold():
        out.append(folded)
    # common guest typos
    replacements = [
        ("ğ", "g"), ("ş", "s"), ("ı", "i"), ("İ", "I"), ("ü", "u"), ("ö", "o"), ("ç", "c"),
        ("aa", "a"), ("ee", "e"), ("ll", "l"), ("kk", "k"),
    ]
    base = phrase.casefold()
    for a, b in replacements:
        if a in base:
            out.append(base.replace(a, b, 1))
    # drop one vowel (short words only)
    if 4 <= len(base) <= 14 and " " not in base:
        for i, ch in enumerate(base):
            if ch in "aeıioöuü":
                out.append(base[:i] + base[i + 1 :])
                break
    # doubled consonant slip
    if " " not in base and len(base) >= 5:
        out.append(base + base[-1])
    return _uniq(out, 6)


def _key_tokens(key: str) -> list[str]:
    return [t for t in key.split("_") if t and t not in {"a", "the", "of", "and", "or"}]


def _label_aliases(label_tr: str, label_en: str) -> list[str]:
    out = [label_tr, label_en]
    if label_tr:
        out.append(_fold_tr(label_tr))
    if label_en:
        out.append(label_en.casefold())
    return out


def _multilingual_for_aspect(key: str, label_tr: str, label_en: str, keywords: list[str]) -> dict[str, list[str]]:
    ml: dict[str, list[str]] = {"tr": [], "en": [], "de": [], "ru": [], "ar": []}
    ml["tr"].extend([label_tr] + keywords[:8])
    ml["en"].append(label_en)
    for tok in _key_tokens(key):
        bank = TOKEN_PHRASES.get(tok)
        if not bank:
            # fuzzy: substring match on token banks
            for bt, phrases in TOKEN_PHRASES.items():
                if bt in tok or tok in bt:
                    bank = phrases
                    break
        if bank:
            for lang, phrases in bank.items():
                ml.setdefault(lang, []).extend(phrases)
    # light DE/RU/AR from label_en word
    if label_en:
        ml["de"].append(label_en)
        ml["ru"].append(label_en)
        ml["ar"].append(label_en)
    return {lang: _uniq(vals, 10 if lang in ("tr", "en") else 4) for lang, vals in ml.items() if vals}


def _cues_for_aspect(key: str, category: str) -> tuple[list[str], list[str]]:
    pos: list[str] = []
    neg: list[str] = []
    for tok in _key_tokens(key):
        for frag, bank in FRAGMENT_CUES.items():
            if frag in tok or tok in frag:
                pos.extend(bank["pos"])
                neg.extend(bank["neg"])
    # category defaults
    cat_defaults = {
        "ROOM": (["oda güzel", "oda ferah"], ["oda kötü", "oda sorunlu"]),
        "BED": (["rahat uyuduk", "yatak iyi"], ["uyuyamadık", "yatak kötü"]),
        "BATHROOM": (["banyo temiz", "duş iyi"], ["banyo kirli", "su sorunu"]),
        "HVAC": (["klima iyi", "sıcaklık ideal"], ["klima bozuk", "oda sıcak/soğuk"]),
        "INTERNET": (["internet iyi", "wifi hızlı"], ["internet yok", "wifi yavaş"]),
        "FOOD": (["yemek lezzetli", "büfe zengin"], ["yemek kötü", "çeşit az"]),
        "STAFF": (["personel ilgili", "güler yüzlü"], ["personel kaba", "ilgisiz"]),
        "POOL": (["havuz güzel", "plaj iyi"], ["havuz kirli", "kalabalık"]),
        "OPERATIONS": (["işlem hızlı", "sorunsuz"], ["beklettiler", "organizasyon kötü"]),
    }
    dp, dn = cat_defaults.get(category, ([], []))
    pos.extend(dp)
    neg.extend(dn)
    pos.extend(GENERIC_POS[:4])
    neg.extend(GENERIC_NEG[:4])
    return _uniq(pos, 10), _uniq(neg, 10)


def _slang_for_aspect(key: str, category: str) -> dict[str, list[str]]:
    bank = CATEGORY_SLANG.get(category, {})
    tr = list(bank.get("tr", [])) + TR_SLANG_POS[:2] + TR_SLANG_NEG[:2]
    en = list(bank.get("en", [])) + EN_SLANG_POS[:2] + EN_SLANG_NEG[:2]
    # key-specific sprinkle
    tokens = " ".join(_key_tokens(key))
    if "wifi" in tokens or "internet" in tokens:
        tr.extend(["net yok", "wifi şaka"])
        en.extend(["wifi LOL", "no bars"])
    if "staff" in tokens or "personel" in tokens:
        tr.extend(["adamlar süper", "suratlar asık"])
    if "clean" in tokens:
        tr.extend(["pislik ayakta", "tertemiz ya"])
    return {"tr": _uniq(tr, 8), "en": _uniq(en, 6)}


def _typos_for_aspect(
    key: str, keywords: list[str], label_tr: str, aliases: list[str]
) -> list[str]:
    seeds = _uniq([label_tr] + keywords[:6] + aliases[:6] + key.split("_"), 12)
    out: list[str] = []
    for s in seeds:
        out.extend(_turkish_typos(s))
        folded = _fold_tr(s)
        if folded and folded != s.casefold():
            out.append(folded)
        if " " in s:
            out.append(s.replace(" ", ""))
            out.append(s.replace(" ", "-"))
        if "-" in s:
            out.append(s.replace("-", ""))
            out.append(s.replace("-", " "))
    # common hotel-domain typos
    extra_map = {
        "wifi": ["wifii", "wi fi", "vayfay", "vay fay", "wi-fi"],
        "klima": ["klimasi", "klimaası", "climası"],
        "havuz": ["havuzzz", "havus", "hawuz"],
        "kahvaltı": ["kahvalti", "kahvaltıı", "kahvalt"],
        "personel": ["personell", "persone", "personalı"],
        "resepsiyon": ["reception", "resepsion", "resepsyon"],
        "temizlik": ["temzlik", "temizlk", "temizilik"],
        "gürültü": ["gurultu", "gürültüu", "gurult"],
        "yastık": ["yastik", "yastıkk", "yasti"],
        "çarşaf": ["carsaf", "çarşaff", "carsaff"],
    }
    blob = " ".join(seeds).casefold()
    for needle, variants in extra_map.items():
        if needle in blob or _fold_tr(needle) in _fold_tr(blob):
            out.extend(variants)
    # guarantee non-empty: key-based ascii slips
    if not out:
        base = key.replace("_", " ")
        out.extend([base, base.replace(" ", ""), key.replace("_", ""), key + "i"])
    return _uniq(out, 12)


def _verbs_objects(key: str, category: str) -> tuple[list[str], list[str]]:
    verbs_map = {
        "ROOM": (["temizlemek", "kokmak", "gürültü yapmak", "ayarlamak"], ["oda", "halı", "perde", "balkon"]),
        "BED": (["yatmak", "uyumak", "değiştirmek"], ["yatak", "yastık", "çarşaf", "yorgan"]),
        "BATHROOM": (["duş almak", "akıtmak", "tıkanmak", "kokmak"], ["duş", "tuvalet", "havlu", "lavabo"]),
        "HVAC": (["soğutmak", "ısıtmak", "ses yapmak", "üflemek"], ["klima", "termostat", "filtre", "vantilatör"]),
        "INTERNET": (["bağlanmak", "kopmak", "yavaşlamak"], ["wifi", "sinyal", "modem", "şifre"]),
        "FOOD": (["yemek", "tadına bakmak", "bekletmek", "servis etmek"], ["yemek", "büfe", "tabak", "içecek"]),
        "STAFF": (["yardım etmek", "karşılamak", "özür dilemek"], ["personel", "resepsiyon", "garson"]),
        "POOL": (["yüzmek", "şezlong kapmak", "bekletmek"], ["havuz", "şezlong", "plaj", "havlu"]),
        "OPERATIONS": (["check-in yapmak", "bekletmek", "faturalamak"], ["resepsiyon", "rezervasyon", "anahtar"]),
    }
    v, o = verbs_map.get(category, (["etkilemek"], ["hizmet"]))
    # token-informed
    for tok in _key_tokens(key):
        if tok in ("clean", "cleanliness"):
            v = _uniq(["temizlemek", "silmek"] + v, 5)
        if tok in ("smell", "odor"):
            v = _uniq(["kokmak", "gidermek"] + v, 5)
        if tok in ("noise",):
            v = _uniq(["gürültü yapmak", "duymak"] + v, 5)
    return _uniq(v, 5), _uniq(o, 5)


def _examples(key: str, label_tr: str, label_en: str, category: str, pos: list[str], neg: list[str]) -> dict[str, list[str]]:
    p0 = pos[0] if pos else "iyi"
    n0 = neg[0] if neg else "kötü"
    topic_tr = label_tr or key
    topic_en = label_en or key
    return {
        "positive_examples": _uniq([
            f"{topic_tr} gerçekten {p0}.",
            f"We loved the {topic_en.lower()} — {p0}.",
            f"{topic_tr} konusunda hiç sorun yaşamadık.",
        ], 3),
        "negative_examples": _uniq([
            f"{topic_tr} {n0}; şikayetçi olduk.",
            f"The {topic_en.lower()} was {n0}.",
            f"{topic_tr} yüzünden konforumuz bozuldu.",
        ], 3),
        "counter_examples": _uniq([
            f"Genel otel güzeldi ama bu cümle {topic_tr} değil.",
            f"Mentioned {topic_en.lower()} only as location context, not complaint.",
        ], 2),
    }


def _confused_with(key: str, category: str, by_cat: dict[str, list[str]], all_keys: set[str]) -> list[str]:
    out: list[str] = []
    if key in CONFUSION_HINTS:
        out.extend(CONFUSION_HINTS[key])
    # same-prefix siblings
    prefix = "_".join(key.split("_")[:2]) if key.count("_") >= 1 else key
    siblings = [k for k in by_cat.get(category, []) if k != key and (k.startswith(prefix) or prefix.startswith(k.split("_")[0]))]
    out.extend(siblings[:4])
    # shared first token
    tok0 = key.split("_")[0]
    same_tok = [k for k in by_cat.get(category, []) if k != key and k.split("_")[0] == tok0]
    out.extend(same_tok[:3])
    return _uniq([k for k in out if k in all_keys and k != key], 4)


def _descriptions(label_tr: str, label_en: str, category: str, dept: str) -> tuple[str, str]:
    d_tr = f"{label_tr}: misafir yorumlarında {category} kategorisi / {dept} sorumluluğu altında izlenen operasyonel yön."
    d_en = f"{label_en}: operational guest-feedback facet under {category} (dept: {dept})."
    return d_tr, d_en


def _common_phrases(label_tr: str, label_en: str, keywords: list[str], pos: list[str], neg: list[str]) -> list[str]:
    phrases = [
        f"{label_tr} çok iyiydi",
        f"{label_tr} sorunluydu",
        f"{label_en} was great",
        f"{label_en} was poor",
    ]
    for kw in keywords[:4]:
        phrases.append(f"{kw} vardı")
        phrases.append(f"{kw} yoktu")
    if pos:
        phrases.append(f"{label_tr} {pos[0]}")
    if neg:
        phrases.append(f"{label_tr} {neg[0]}")
    return _uniq(phrases, 8)


def _high_value_overrides() -> dict[str, dict[str, Any]]:
    """Hand-refined enrichment for critical ABSA / guest-facing aspects."""
    return {
        "room_cleanliness": {
            "aliases": [
                "oda temizliği", "kirli oda", "oda pis", "room dirty", "spotless room",
                "toz içinde oda", "hijyen oda", "temiz oda",
            ],
            "slang": {
                "tr": ["oda rezalet kirli", "oda tertemiz ya", "pislik ayakta"],
                "en": ["room was a dump", "spotless vibes"],
            },
            "typos": ["oda temzligi", "kirli odaa", "oda temizlik", "room cleenliness"],
            "frequently_confused_with": ["room_smell", "room_carpet_stain", "bathroom_cleanliness", "room_mold"],
            "negative_examples": [
                "Oda kirliydi, yerlerde toz ve saç vardı.",
                "The room was filthy on arrival.",
            ],
            "positive_examples": [
                "Oda tertemiz teslim edildi.",
                "Room was spotless.",
            ],
        },
        "room_smell": {
            "aliases": ["oda kokusu", "küf kokusu", "rutubet", "musty room", "room stinks"],
            "typos": ["oda koksu", "kuf kokusu", "rutubet kokuyor"],
            "slang": {"tr": ["oda kokuyor resmen", "lağım gibi"], "en": ["room reeks"]},
            "frequently_confused_with": ["room_odor_smoke", "room_odor_sewage", "room_mold_smell", "room_dampness"],
        },
        "room_noise": {
            "aliases": ["oda gürültüsü", "komşu sesi", "noisy room", "corridor noise"],
            "typos": ["gurultu", "oda gurultusu", "komsu sesi"],
            "slang": {"tr": ["gece uyku yok sesden", "gürültü çılgın"], "en": ["zero sleep, so loud"]},
            "frequently_confused_with": ["room_noise_neighbors", "room_noise_hallway", "room_soundproof"],
        },
        "bed_comfort": {
            "aliases": ["yatak rahatlığı", "sert yatak", "yumuşak yatak", "bed comfort", "uncomfortable bed"],
            "typos": ["yatak rahatligi", "sert yatakk"],
            "slang": {"tr": ["yatak tahta", "yatak bulut"], "en": ["bed was a rock"]},
            "frequently_confused_with": ["mattress_quality", "bed_too_soft", "bed_too_firm"],
        },
        "bed_linen": {
            "aliases": ["çarşaf", "nevresim", "kirli çarşaf", "bedding", "dirty sheets"],
            "typos": ["carsaf", "nevresim", "kirli carsaf"],
            "slang": {"tr": ["çarşaf iğrenç", "nevresim leke"], "en": ["sheets were nasty"]},
        },
        "bathroom_cleanliness": {
            "aliases": ["banyo temizliği", "pis banyo", "dirty bathroom", "tuvalet kirli"],
            "typos": ["banyo temzligi", "pis banyoo"],
            "slang": {"tr": ["banyo iğrenç", "tuvalet felaket"], "en": ["bathroom was gross"]},
            "frequently_confused_with": ["bathroom_mold", "shower_glass_clean", "bathroom_hair"],
        },
        "shower_pressure": {
            "aliases": ["duş basıncı", "su basıncı", "zayıf duş", "weak shower pressure"],
            "typos": ["dus basinci", "su basnci", "zayif su"],
            "slang": {"tr": ["duştan damlıyor", "su yok gibi"], "en": ["shower is a trickle"]},
        },
        "hot_water": {
            "aliases": ["sıcak su", "su ısınmıyor", "no hot water", "su soğuk"],
            "typos": ["sicak su", "su isinmiyor", "ilik su"],
            "slang": {"tr": ["sıcak su hayal", "buz gibi su"], "en": ["hot water MIA"]},
        },
        "hvac_cooling": {
            "aliases": ["klima soğutmuyor", "soğutma", "AC not cooling", "oda sıcak klima"],
            "typos": ["klima sogutmiyor", "sogutma", "klima bozuk"],
            "slang": {"tr": ["klima ölmüş", "oda fırın"], "en": ["AC is dead", "sauna room"]},
            "frequently_confused_with": ["hvac_not_cooling", "hvac_too_hot", "room_temperature"],
        },
        "hvac_noise": {
            "aliases": ["klima sesi", "klima gürültüsü", "noisy AC"],
            "typos": ["klima sesi", "klima gurultusu"],
            "slang": {"tr": ["klima motor gibi", "gece klima gürültü"], "en": ["AC roaring all night"]},
        },
        "wifi_speed": {
            "aliases": ["wifi hızı", "yavaş internet", "slow wifi", "internet yavaş"],
            "typos": ["wifii hizi", "yavas internet", "vayfay yavas"],
            "slang": {"tr": ["wifi kaplumbağa", "net yok hükmünde"], "en": ["wifi is a joke"]},
            "frequently_confused_with": ["wifi_stability", "wifi_coverage", "wifi_slow_evening"],
        },
        "wifi_coverage": {
            "aliases": ["wifi kapsamı", "çekmiyor", "dead zone", "sinyal yok"],
            "typos": ["cekmiyor", "wifi kapsama", "sinyal yok"],
            "slang": {"tr": ["odada çekmiyor", "sinyal şaka"], "en": ["dead wifi zone"]},
        },
        "food_quality": {
            "aliases": ["yemek kalitesi", "yemekler", "food quality", "kötü yemek"],
            "typos": ["yemek kalitesi", "yemekler kotu"],
            "slang": {"tr": ["yemek efsane", "yemek rezalet", "yemek mid"], "en": ["food slapped", "food was mid"]},
            "frequently_confused_with": ["food_taste", "food_freshness", "buffet_quality"],
        },
        "food_taste": {
            "aliases": ["lezzet", "yemek tadı", "tatsız", "delicious", "bland food"],
            "typos": ["lezet", "tatsiz", "yemek tadi"],
            "slang": {"tr": ["tadı bomboş", "lezzet şahane"], "en": ["tastes like cardboard", "flavor fire"]},
        },
        "food_hygiene": {
            "aliases": ["yemek hijyeni", "kirli tabak", "food hygiene", "böcek yemek"],
            "typos": ["yemek hijyeni", "hijyen sorun"],
            "slang": {"tr": ["hijyen rezalet", "tabak kirli çıktı"], "en": ["hygiene nightmare"]},
            "frequently_confused_with": ["buffet_hygiene", "table_cleanliness", "fly_insect_food"],
        },
        "breakfast_variety": {
            "aliases": ["kahvaltı çeşitliliği", "kahvaltı zayıf", "breakfast variety"],
            "typos": ["kahvalti cesit", "kahvaltı zayif"],
            "slang": {"tr": ["kahvaltı bomboş", "çeşit yok"], "en": ["breakfast options thin"]},
        },
        "staff_behavior": {
            "aliases": ["personel davranışı", "kaba personel", "staff attitude", "rude staff"],
            "typos": ["personel davranisi", "kaba personell"],
            "slang": {"tr": ["surat asık", "adamlar süper", "ilgi sıfır"], "en": ["staff ghosted us", "staff were legends"]},
            "frequently_confused_with": ["staff_friendliness", "staff_attitude_front", "staff_front_desk_attitude"],
        },
        "staff_helpfulness": {
            "aliases": ["yardımsever personel", "ilgisiz personel", "helpful staff"],
            "typos": ["yardimsever", "ilgisiz personel"],
            "slang": {"tr": ["yardım etmediler", "ellerinden geleni yaptılar"], "en": ["zero help", "super helpful"]},
        },
        "staff_shortage": {
            "aliases": ["personel yetersiz", "understaffed", "kimse yok", "eksik kadro"],
            "typos": ["personel yetersiz", "personel eksik"],
            "slang": {"tr": ["personel yok gibi", "tek kişiye kaldık"], "en": ["ghost town staffing"]},
        },
        "reception_service": {
            "aliases": ["resepsiyon hizmeti", "karşılama", "front desk", "check-in service"],
            "typos": ["resepsion", "resepsyon", "reception"],
            "slang": {"tr": ["resepsiyon kaos", "karşılama süper"], "en": ["front desk chaos"]},
        },
        "pool_cleanliness": {
            "aliases": ["havuz temizliği", "kirli havuz", "pool dirty", "klor"],
            "typos": ["havuz temzligi", "kirli havuz"],
            "slang": {"tr": ["havuz çorba", "havuz berrak"], "en": ["pool soup", "crystal pool"]},
            "frequently_confused_with": ["pool_water_clarity", "pool_chlorine_smell", "pool_algae"],
        },
        "pool_lounger": {
            "aliases": ["şezlong", "şezlong yok", "sunbed", "lounger"],
            "typos": ["sezlong", "şezlongg", "sun bed"],
            "slang": {"tr": ["şezlong savaşı", "havlu ile kapmışlar"], "en": ["sunbed war"]},
        },
        "ops_checkin_process": {
            "aliases": ["check-in süreci", "giriş işlemi", "checkin slow"],
            "typos": ["checkin sureci", "giris islemi", "chek-in"],
            "slang": {"tr": ["check-in işkence", "giriş tıkırında"], "en": ["check-in nightmare"]},
        },
        "ops_value_for_money": {
            "aliases": ["fiyat performans", "paranın karşılığı", "value for money", "pahalı"],
            "typos": ["fiyat performans", "paranin karsiligi"],
            "slang": {"tr": ["parasına değmez", "full fiyat performans"], "en": ["not worth the cash"]},
        },
    }


def build_enrichment(aspects_data: dict[str, Any]) -> dict[str, Any]:
    by_cat: dict[str, list[str]] = {}
    records: list[dict[str, Any]] = []
    all_keys: set[str] = set()
    for cat, cat_data in aspects_data.get("categories", {}).items():
        keys = []
        for asp in cat_data.get("aspects", []):
            keys.append(asp["key"])
            all_keys.add(asp["key"])
            records.append({**asp, "category": cat})
        by_cat[cat] = keys

    overrides = _high_value_overrides()
    aspects_out: dict[str, Any] = {}

    for asp in records:
        key = asp["key"]
        cat = asp["category"]
        dept = asp.get("department", "genel")
        label_tr = asp.get("label_tr", key)
        label_en = asp.get("label_en", key)
        keywords = list(asp.get("keywords") or [])

        aliases = _uniq(_label_aliases(label_tr, label_en) + keywords, 14)
        # expand aliases from token banks
        for tok in _key_tokens(key):
            bank = TOKEN_PHRASES.get(tok)
            if bank:
                aliases.extend(bank.get("tr", [])[:3])
                aliases.extend(bank.get("en", [])[:3])
        aliases = _uniq(aliases, 14)

        synonyms = _uniq(
            [label_tr, label_en, _fold_tr(label_tr)]
            + [k for k in keywords if k not in aliases][:6],
            10,
        )
        pos, neg = _cues_for_aspect(key, cat)
        verbs, objects = _verbs_objects(key, cat)
        ml = _multilingual_for_aspect(key, label_tr, label_en, keywords)
        slang = _slang_for_aspect(key, cat)
        typos = _typos_for_aspect(key, keywords, label_tr, aliases)
        ops = CATEGORY_OPS.get(cat, {})
        desc_tr, desc_en = _descriptions(label_tr, label_en, cat, dept)
        examples = _examples(key, label_tr, label_en, cat, pos, neg)

        entry: dict[str, Any] = {
            "category": cat,
            "aliases": aliases,
            "synonyms": synonyms,
            "positive_words": pos,
            "negative_words": neg,
            "verbs": verbs,
            "objects": objects,
            "common_phrases": _common_phrases(label_tr, label_en, keywords, pos, neg),
            "positive_examples": examples["positive_examples"],
            "negative_examples": examples["negative_examples"],
            "counter_examples": examples["counter_examples"],
            "frequently_confused_with": _confused_with(key, cat, by_cat, all_keys),
            "related_processes": list(ops.get("related_processes", []))[:4],
            "related_sop": list(ops.get("related_sop", []))[:3],
            "related_root_causes": list(ops.get("related_root_causes", []))[:5],
            "related_actions": list(ops.get("related_actions", []))[:5],
            "multilingual": ml,
            "typos": typos,
            "slang": slang,
            "description_tr": desc_tr,
            "description_en": desc_en,
        }

        # apply hand overrides (merge, don't drop generated structure)
        ov = overrides.get(key)
        if ov:
            for k, v in ov.items():
                if isinstance(v, list) and isinstance(entry.get(k), list):
                    entry[k] = _uniq(list(v) + list(entry[k]), 16)
                elif isinstance(v, dict) and isinstance(entry.get(k), dict):
                    merged = dict(entry[k])
                    for lk, lv in v.items():
                        merged[lk] = _uniq(list(lv) + list(merged.get(lk, [])), 10)
                    entry[k] = merged
                else:
                    entry[k] = v

        aspects_out[key] = entry

    return {
        "version": "1.0",
        "description": (
            "Companion enrichment for aspects.yaml. Keys are FROZEN — must match "
            "existing aspect keys only. Consumed by OntologyService merge helper; "
            "does not alter clause_pipeline / 8-department runtime."
        ),
        "source_aspects": "aspects.yaml",
        "schema": {
            "aliases": "list[str] — guest phrases TR+EN (+folded)",
            "synonyms": "list[str]",
            "positive_words": "list[str]",
            "negative_words": "list[str]",
            "verbs": "list[str]",
            "objects": "list[str]",
            "common_phrases": "list[str]",
            "positive_examples": "list[str]",
            "negative_examples": "list[str]",
            "counter_examples": "list[str]",
            "frequently_confused_with": "list[str] — existing aspect keys only",
            "related_processes": "list[str]",
            "related_sop": "list[str]",
            "related_root_causes": "list[str]",
            "related_actions": "list[str]",
            "multilingual": "dict[lang, list[str]] — tr/en/de/ru/ar",
            "typos": "list[str] — misspellings (esp. Turkish)",
            "slang": "dict[lang, list[str]] — colloquial guest language",
            "description_tr": "str",
            "description_en": "str",
        },
        "aspect_count": len(aspects_out),
        "aspects": aspects_out,
    }


class _NoAliasDumper(yaml.SafeDumper):
    pass


def _repr_str(dumper, data):  # type: ignore[no-untyped-def]
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_NoAliasDumper.add_representer(str, _repr_str)
_NoAliasDumper.ignore_aliases = lambda *args: True  # type: ignore[method-assign]


def main() -> int:
    data = yaml.safe_load(ASPECTS_PATH.read_text(encoding="utf-8"))
    enrichment = build_enrichment(data)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.dump(
        enrichment,
        Dumper=_NoAliasDumper,
        allow_unicode=True,
        sort_keys=False,
        width=100,
        default_flow_style=False,
    )
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT_PATH} with {enrichment['aspect_count']} aspects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
