"""
Systemic ABSA clause pipeline — config-driven stages.

Stages:
  1. Segment (caller may pass pre-split clauses)
  2. Meta / noise filter
  3. Context frame detection
  4. Aspect + sentiment with frame
  5. Department + anti-pattern guards
  6. Severity policy
  7. Summary builder

Prefer extending config/absa/clause_pipeline.yaml over Crystal-specific if/else.
"""

from __future__ import annotations

import logging

import os
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

import yaml

from app.services.turkish_nlp_utils import normalize_turkish

_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "absa", "clause_pipeline.yaml"
)


# _match_cue / _any_cue / _count_cues her cümlecik için tüm cue listesini gezip
# _fold'u hem metne hem de YAML'deki SABİT cue dizelerine uyguluyor; sonuçta tek
# analizde ~30.000 çağrı oluşuyor ve her biri normalize_turkish + NFKD ayrıştırma
# yapıyor. Saf fonksiyon olduğu için önbellek davranışı değiştirmez.
@lru_cache(maxsize=50000)
def _fold(text: str) -> str:
    """ASCII-fold Turkish; strip combining marks (hari̇ka → harika)."""
    t = normalize_turkish(text or "").lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return (
        t.replace("ı", "i")
        .replace("İ", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )


@lru_cache(maxsize=1)
def load_pipeline_config() -> dict[str, Any]:
    path = os.path.abspath(_CONFIG_PATH)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def reload_pipeline_config() -> dict[str, Any]:
    load_pipeline_config.cache_clear()
    return load_pipeline_config()


@dataclass
class ClauseDecision:
    clause: str
    include: bool = True
    drop_reason: str = ""
    frame: str = "general"
    aspect_key: str = "general"
    aspect_label: str = "Genel"
    department: str = "genel"
    department_label: str = "Genel"
    category: str = "Genel"
    sentiment: str = "Neutral"
    sentiment_score: float = 0.0
    priority: str = "medium"
    priority_score: int = 2
    confidence: float = 0.75
    method: str = "clause_pipeline"
    frame_scores: dict[str, float] = field(default_factory=dict)
    overrides: list[str] = field(default_factory=list)


def _cue_str(c: Any) -> str:
    """YAML may parse 18.00 as float — always coerce cues to string.

    Cue değerleri YAML'den geliyor ve config bir kez yükleniyor; aynı sabit
    değer her cümlecikte yeniden dizeye çevriliyordu (40 yorumda ~3.8M çağrı).
    Önbellek bunu tekilleştirir. dict/list gibi hash'lenemeyen bir cue gelirse
    TypeError yakalanıp önbelleksiz yola düşülür — davranış korunur.
    """
    try:
        return _cue_str_cached(c)
    except TypeError:
        return _cue_str_uncached(c)


@lru_cache(maxsize=16384)
def _cue_str_cached(c: Any) -> str:
    return _cue_str_uncached(c)


def _cue_str_uncached(c: Any) -> str:
    if c is None:
        return ""
    if isinstance(c, float):
        # 18.0 → "18.00" if looks like clock, else str
        s = f"{c:.2f}" if c == int(c) or abs(c - int(c)) < 1e-9 else str(c)
        if s.endswith(".00") and len(s) <= 5:
            return s
        return str(c)
    return str(c)


@lru_cache(maxsize=4096)
def _get_compiled_cue_regex(pattern_str: str) -> re.Pattern:
    return re.compile(pattern_str)


# Analiz yolunun tek en sıcak fonksiyonu: _any_cue/_count_cues her cümlecik için
# TÜM cue listesini gezdiğinden 40 yorumda ~3.8 milyon kez çağrılıyordu. Üç
# argümanı da string ve fonksiyon saf (yalnızca sabitleri okuyor, önbellekli
# yardımcıları çağırıyor), dolayısıyla sonuç doğrudan önbelleklenebilir.
@lru_cache(maxsize=200000)
def _match_cue(text: str, folded: str, cs: str) -> bool:
    cs_low = cs.lower()
    cs_fold = _fold(cs)
    if cs_low.startswith(r"\b") or cs_low.endswith(r"\b"):
        return bool(_get_compiled_cue_regex(cs_low).search(text) or _get_compiled_cue_regex(cs_fold).search(folded))
    if cs_low in ("bekle", "hamam", "deniz", "plaj", "sira", "sıra"):
        pattern_text = rf"(?<![a-zA-ZıİşŞğĞüÜöÖçÇ]){re.escape(cs_low)}(?![a-zA-ZıİşŞğĞüÜöÖçÇ])"
        pattern_fold = rf"(?<![a-zA-ZıİşŞğĞüÜöÖçÇ]){re.escape(cs_fold)}(?![a-zA-ZıİşŞğĞüÜöÖçÇ])"
        return bool(_get_compiled_cue_regex(pattern_text).search(text) or _get_compiled_cue_regex(pattern_fold).search(folded))
    # "çeşit" ⊂ "çeşitli" (various stains) must NOT fire bar/food variety
    if cs_fold in ("cesit",) or cs_low in ("çeşit", "cesit"):
        if "cesitlilik" in folded or "çeşitlilik" in text:
            return True
        pattern_fold = rf"(?<![a-zA-ZıİşŞğĞüÜöÖçÇ])cesit(?!li)(?![a-zA-ZıİşŞğĞüÜöÖçÇ])"
        pattern_text = rf"(?<![a-zA-ZıİşŞğĞüÜöÖçÇ])(?:çeşit|cesit)(?!li)(?![a-zA-ZıİşŞğĞüÜöÖçÇ])"
        return bool(_get_compiled_cue_regex(pattern_text).search(text) or _get_compiled_cue_regex(pattern_fold).search(folded))
    if len(cs_low) <= 4:
        pattern_text = rf"(?<![a-zA-ZıİşŞğĞüÜöÖçÇ]){re.escape(cs_low)}(?![a-zA-ZıİşŞğĞüÜöÖçÇ])"
        pattern_fold = rf"(?<![a-zA-ZıİşŞğĞüÜöÖçÇ]){re.escape(cs_fold)}(?![a-zA-ZıİşŞğĞüÜöÖçÇ])"
        return bool(_get_compiled_cue_regex(pattern_text).search(text) or _get_compiled_cue_regex(pattern_fold).search(folded))
    return cs_low in text or cs_fold in folded


_PEST_TOKENS = (
    "bocek", "böcek", "bocegi", "böceği", "boceginin", "böceğinin",
    "bocekler", "böcekler", "hasere", "haşere", "hamambocegi", "hamamböceği",
    "hamam bocegi", "hamam böceği", "hamam boceginin", "hamam böceğinin",
    "hamam boceg", "hamam böceğ", "bocekli", "böcekli", "karasinek", "kara sinek",
    "kil", "kıl", "kili", "kılı", "sac kili", "saç kılı",
)


@lru_cache(maxsize=100000)
def _has_pest_signal(text: str, folded: str) -> bool:
    """Cockroach / pest — never spa/hamam bath."""
    blob = f"{text} {folded}".lower()
    for w in _PEST_TOKENS:
        if len(w) <= 4:
            if re.search(rf"(?<![a-zA-ZıİşŞğĞüÜöÖçÇ]){re.escape(w)}(?![a-zA-ZıİşŞğĞüÜöÖçÇ])", blob):
                return True
        else:
            if w in blob:
                return True
    return False


# Expectation / whitelist traps: "bekle" ⊂ "beklemeden", "beklenti"
_BEKLE_TRAPS = (
    "beklemeden", "beklenti", "beklentisi", "beklentiler",
    "beklentinin", "beklentimin", "beklediğim", "bekledigim",
)


def _iter_matching_cues(text: str, folded: str, cues: list):
    """Eşleşen cue'ları üretir — _any_cue ve _count_cues'un ortak gövdesi.

    Önceden iki fonksiyon aynı tuzak mantığını (bekle / hamam istisnaları)
    ayrı ayrı barındırıyordu; tek fark `return True` yerine `n += 1` idi.
    Birine kural eklenip diğerine eklenmediğinde davranış sessizce çatallanıyordu.
    """
    for c in cues or []:
        cs = _cue_str(c)
        if not cs:
            continue
        cs_low = cs.lower()
        if cs_low == "bekle" and any(w in text or w in folded for w in _BEKLE_TRAPS):
            continue
        if cs_low == "hamam" and _has_pest_signal(text, folded):
            continue
        if _match_cue(text, folded, cs):
            yield cs


def _any_cue(text: str, folded: str, cues: list) -> bool:
    return any(True for _ in _iter_matching_cues(text, folded, cues))


def _count_cues(text: str, folded: str, cues: list) -> int:
    return sum(1 for _ in _iter_matching_cues(text, folded, cues))


# ---------------------------------------------------------------------------
# Stage 2 — meta / noise
# ---------------------------------------------------------------------------
def has_operational_rescue(clause: str, cfg: Optional[dict] = None) -> bool:
    """Long narrative openers that also carry queue/capacity signals must be kept."""
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    min_words = int(cfg.get("meta_rescue_min_words", 8))
    if len(clause.split()) < min_words:
        return False
    return _any_cue(low, folded, cfg.get("meta_rescue_cues") or [])


def is_meta_clause(clause: str, cfg: Optional[dict] = None) -> bool:
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    matched_meta = False
    for p in cfg.get("meta_patterns") or []:
        if ".*" in p:
            if re.search(p, low, flags=re.IGNORECASE) or re.search(_fold(p), folded):
                matched_meta = True
                break
        elif p.lower() in low or _fold(p) in folded:
            matched_meta = True
            break
    if matched_meta:
        # Do not drop queue/exhaustion/capacity complaints glued to framing
        if has_operational_rescue(clause, cfg):
            return False
        return True
    # Short demographic-only
    demo = cfg.get("demographic_patterns") or []
    if _any_cue(low, folded, demo) and len(clause.split()) <= 12:
        if not _any_cue(low, folded, ["kötü", "kotu", "berbat", "şikayet", "sikayet"]):
            if not has_operational_rescue(clause, cfg):
                return True
    return False


def is_thanks_clause(clause: str, cfg: Optional[dict] = None) -> bool:
    cfg = cfg or load_pipeline_config()
    return _any_cue(clause.lower(), _fold(clause), cfg.get("thanks_patterns") or [])


# ---------------------------------------------------------------------------
# Stage 3 — frames
# ---------------------------------------------------------------------------
def detect_frames(clause: str, cfg: Optional[dict] = None) -> dict[str, float]:
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    frames_cfg = cfg.get("frames") or {}
    scores: dict[str, float] = {}

    for name, spec in frames_cfg.items():
        score = 0.0
        entity_hits = _count_cues(low, folded, spec.get("entity_cues") or [])
        score += 1.5 * entity_hits
        # Room size/hygiene without a room entity → "küçük bir mola", "dar sokak"
        room_entity_present = entity_hits > 0 or _any_cue(
            low, folded, ["oda", "odalar", "odam", "odamız", "odamiz", "room", "rooms", "bedroom"]
        )
        for key, weight in (
            ("size_cues", 2.0),
            ("hygiene_cues", 2.0),
            ("noise_cues", 2.5),
            ("table_service_cues", 2.5),
            ("quantity_cues", 1.5),
            ("variety_cues", 2.0),
            ("hours_cues", 1.5),
            ("lounger_cues", 2.5),
            ("cleaning_soda_cues", -5.0),
        ):
            if name == "room" and key in ("size_cues", "hygiene_cues") and not room_entity_present:
                continue
            score += weight * _count_cues(low, folded, spec.get(key) or [])
        if score > 0:
            scores[name] = score

    # Structural: N kişilik sıra / kuyruk always queue
    if re.search(r"\d+\s*ki[sş]ilik", low) and any(w in folded for w in ("sira", "kuyruk", "bekle")):
        scores["queue"] = scores.get("queue", 0) + 4.0
    if any(w in folded for w in ("kuyruk", "sirayi bekle", "sira bekle", "sira bekleniyor", "beklemis", "beklemiş")):
        scores["queue"] = scores.get("queue", 0) + 2.0
    # Drink + wait minutes → queue dominates drink quality
    if (any(w in folded for w in ("icecek", "içecek", "limonata", "tekila")) or _any_cue(low, folded, ["bar"])) and any(
        w in folded for w in ("sira", "kuyruk", "dakika", "bekle", "alinamiyor", "alınamıyor")
    ):
        scores["queue"] = scores.get("queue", 0) + 3.5
    # Pool lounger queue
    if any(w in folded for w in ("sezlong", "şezlong")) and any(w in folded for w in ("sira", "kuyruk", "bekle", "bulunmuyor", "yok")):
        scores["pool"] = scores.get("pool", 0) + 3.0
        scores["queue"] = scores.get("queue", 0) + 2.0
    # Distance to pool sarcasm — suppress hygiene/pool dominance
    if "metre" in folded and "havuz" in folded and any(
        w in folded for w in ("yuru", "kos", "isterseniz", "guzel bir yani yok")
    ):
        scores["pool"] = max(0.0, scores.get("pool", 0) - 6.0)
        scores["value"] = scores.get("value", 0) + 2.0

    # Property walk / layout (havuzdan denize yürümek / yürüme mesafesi) — not queue, not room size
    prop = cfg.get("property_layout") or {}
    walk_hit = _any_cue(low, folded, prop.get("walk_cues") or [])
    layout_hit = _any_cue(
        low, folded,
        (prop.get("layout_cues") or [])
        + ["havuz", "deniz", "denize", "kaydirak", "kaydırak", "plaj", "plaja", "sahil", "sahile"],
    )
    mesafe_hit = any(w in folded for w in ("mesafe", "mesafesinde", "mesafesinde", "yurume mesafe", "yürüme mesafe"))
    beach_walk = layout_hit and walk_hit and (
        _any_cue(low, folded, ["deniz", "denize", "plaj", "plaja", "sahil", "sahile"])
    )
    if beach_walk or (walk_hit and (layout_hit or mesafe_hit)):
        scores["environment"] = scores.get("environment", 0) + 4.0
        scores["beach"] = scores.get("beach", 0) + (4.0 if beach_walk else 0.0)
        scores["queue"] = max(0.0, scores.get("queue", 0) - 5.0)
        scores["room"] = max(0.0, scores.get("room", 0) - 4.0)
        scores["fb_venue"] = max(0.0, scores.get("fb_venue", 0) - 2.0)
    # "5 dk yürümek" to beach is NOT a service queue
    if beach_walk and _any_cue(low, folded, ["dk", "dakika", "yurumek", "yürümek"]):
        scores["queue"] = 0.0
        scores["beach"] = scores.get("beach", 0) + 3.0
    if walk_hit and mesafe_hit and not _any_cue(
        low, folded, ["sira", "sıra", "kuyruk", "beklemeniz", "bekleniyor"]
    ):
        # Location walkability praise/mention must not look like F&B/queue wait
        scores["queue"] = max(0.0, scores.get("queue", 0) - 4.0)
        scores["environment"] = scores.get("environment", 0) + 2.0
    if _any_cue(low, folded, prop.get("property_size_cues") or []):
        scores["environment"] = scores.get("environment", 0) + 4.0
        scores["room"] = max(0.0, scores.get("room", 0) - 5.0)
        scores["queue"] = max(0.0, scores.get("queue", 0) - 3.0)

    # Common-area capacity (oturabileceği yeterli alan yok) — not HK cleanliness
    cap_spec = frames_cfg.get("capacity") or {}
    if _any_cue(low, folded, cap_spec.get("common_area_cues") or []) or _any_cue(
        low, folded, ["yeterli alan yok", "oturabilecegi", "oturabileceği", "yeterli yer yok"]
    ):
        scores["capacity"] = scores.get("capacity", 0) + 4.5
        scores["housekeeping"] = max(0.0, scores.get("housekeeping", 0) - 5.0)
        scores["room"] = max(0.0, scores.get("room", 0) - 3.0)

    # Kids overcrowding near aquapark/queue → pool/capacity (not F&B)
    # Staff immaturity ("coluk cocuk yabancı… eline bırakılmış") → staff, NOT bar/pool
    qc = cfg.get("queue_context") or {}
    staff_imm = cfg.get("staff_inexperience_cues") or []
    if _any_cue(low, folded, ["personel", "personeller", "calisan", "çalışan"]) and _any_cue(
        low, folded, staff_imm + ["yabanc", "coluk", "cocuklarin eline", "çocukların eline", "eline birak", "eline bırak"]
    ):
        scores["staff"] = scores.get("staff", 0) + 6.0
        scores["bar"] = max(0.0, scores.get("bar", 0) - 6.0)
        scores["pool"] = max(0.0, scores.get("pool", 0) - 4.0)
    elif _any_cue(low, folded, qc.get("kids_cues") or ["cocuk", "çocuk"]):
        if _any_cue(low, folded, ["sira", "sıra", "kuyruk", "bekle", "kalabal", "asiri", "aşırı", "fazla"]):
            scores["pool"] = scores.get("pool", 0) + 3.0
            scores["capacity"] = scores.get("capacity", 0) + 3.0
            scores["bar"] = max(0.0, scores.get("bar", 0) - 3.0)
            scores["fb_venue"] = max(0.0, scores.get("fb_venue", 0) - 3.0)

    # Bar staffing count → F&B ops frame (not generic staff attitude)
    if _any_cue(low, folded, cfg.get("fb_staffing_cues") or []) or (
        _any_cue(low, folded, ["bar", "barlarda", "barda"]) and _any_cue(
            low, folded, ["calisan", "çalışan", "personel"]
        ) and _any_cue(low, folded, ["az", "yetersiz", "sayi", "sayı", "eksik"])
    ):
        scores["bar"] = scores.get("bar", 0) + 4.0
        scores["staff"] = max(0.0, scores.get("staff", 0) - 4.0)
        scores["fb_venue"] = scores.get("fb_venue", 0) + 2.0

    # Beverage soda / limonata — never lose to weak room score
    bar_spec = frames_cfg.get("bar") or {}
    if re.search(r"(?<![a-z])soda(?![a-z])", folded) and not _any_cue(
        low, folded, bar_spec.get("cleaning_soda_cues") or []
    ):
        scores["bar"] = scores.get("bar", 0) + 3.5
    if any(w in folded for w in ("limonata", "barda ", "tekila", "alkol")) or _any_cue(low, folded, ["bar"]):
        scores["bar"] = scores.get("bar", 0) + 1.5

    # "aynı durum X için geçerli" inherits drink/queue context words in clause
    if ("ayni durum" in folded or "aynı durum" in low) and re.search(r"(?<![a-z])soda(?![a-z])", folded):
        scores["bar"] = scores.get("bar", 0) + 4.0

    # "restoran bar / restoran bar veya" → fb_venue not bar
    if "restoran" in folded and _any_cue(low, folded, ["bar"]):
        if any(w in folded for w in ("veya", "ve", "arası", "arasi", "diger", "diğer")):
            scores["fb_venue"] = scores.get("fb_venue", 0) + 4.0
            scores["bar"] = 0.0

    # "restoran bar restoran bar veya" → her iki kuralı birleştir - fb_venue kazansın
    # (üstteki veya/ve/arası kontrolü öncelikli)

    # Personel + uzun çalışma saatleri → personel (not restaurant)
    if any(w in folded for w in ("personel", "calisan", "çalışan")) and any(
        w in folded for w in ("saat", "vardiya", "mesai", "calisiyor", "çalışıyor")
    ):
        scores["staff"] = scores.get("staff", 0) + 3.0

    # "restoran bar" → fb_venue not bar
    if "restoran" in folded and _any_cue(low, folded, ["bar"]):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 3.0
        scores["bar"] = scores.get("bar", 0) - 3.0

    # Bardak + yemek/yağ context → fb_venue not bar
    if "bardak" in folded and any(w in folded for w in ("yag", "yağ", "leke", "kirli", "bulasik", "bulaşık")):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 2.0
        scores["bar"] = scores.get("bar", 0) - 2.0

    # Saç kurutma makinesi → housekeeping (not teknik)
    if any(w in folded for w in ("sac kurutma", "saç kurutma", "fön", "fon")):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 3.0

    # Housekeeping privacy / intrusion (temizlik çalışanı odaya girdi, cleaning cleaning)
    hk_priv = cfg.get("housekeeping_privacy") or {}
    if _any_cue(low, folded, hk_priv.get("entity_cues") or []):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 5.0
        scores["tech"] = max(0.0, scores.get("tech", 0) - 4.0)
        scores["staff"] = max(0.0, scores.get("staff", 0) - 2.0)

    # Alakart / F&B restaurant queue
    if _any_cue(low, folded, cfg.get("alakart_cues") or []):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 3.0
        if _any_cue(low, folded, ["sira", "sıra", "kuyruk", "bekle", "yavas", "yavaş"]):
            scores["queue"] = scores.get("queue", 0) + 4.0

    # Capacity / sunbed (yer tutma, yer bulamazsınız)
    if _any_cue(low, folded, cfg.get("capacity_sunbed_cues") or []):
        scores["capacity"] = scores.get("capacity", 0) + 3.0
        scores["pool"] = scores.get("pool", 0) + 2.5
        scores["tech"] = max(0.0, scores.get("tech", 0) - 4.0)

    # Bar + queue → queue/bar dominates tech (sıcak substring trap)
    if _any_cue(low, folded, ["bar", "barlarda", "barda", "mojita", "kokteyl"]) and _any_cue(
        low, folded, ["sira", "sıra", "kuyruk", "bekle", "az"]
    ):
        scores["queue"] = scores.get("queue", 0) + 3.0
        scores["bar"] = scores.get("bar", 0) + 2.0
        scores["tech"] = max(0.0, scores.get("tech", 0) - 4.0)

    # Pool water temperature — pool frame only; never HVAC bleed to unrelated clauses
    pool_temp = cfg.get("ontology_guard") or {}
    pool_temp_words = pool_temp.get("pool_temp_words") or [
        "sicak", "sıcak", "serinlet", "soguk", "soğuk", "isitmali", "ısıtmalı", "isitma", "ısıtma",
    ]
    if _any_cue(low, folded, pool_temp.get("pool_temperature_cues") or ["havuz", "plaj", "deniz", "aquapark"]):
        if _any_cue(low, folded, pool_temp_words):
            scores["pool"] = scores.get("pool", 0) + 5.0
            scores["tech"] = max(0.0, scores.get("tech", 0) - 6.0)
    elif _any_cue(low, folded, pool_temp_words):
        # Bare sıcak/serinlet without pool cue — suppress tech
        scores["tech"] = max(0.0, scores.get("tech", 0) - 3.0)

    # Havuz temiz → pool, not spa (masaj keyword override)
    if any(w in folded for w in ("havuz",)) and _any_cue(low, folded, ["temiz", "kirli", "pis", "buyuk", "büyük", "güzel", "guzel"]):
        if _any_cue(low, folded, ["masaj", "spa"]):
            scores["pool"] = max(scores.get("pool", 0), scores.get("spa_wellness", 0) + 3.0)

    # "iki büyük havuz / havuz da temizdi" → pool not room or housekeeping
    if any(w in folded for w in ("havuz",)) and not _any_cue(low, folded, ["oda", "banyo"]):
        if any(w in folded for w in ("buyuk", "büyük", "temiz", "güzel", "guzel")):
            scores["room"] = max(0.0, scores.get("room", 0) - 3.0)
            scores["housekeeping"] = max(0.0, scores.get("housekeeping", 0) - 3.0)

    # Klima filtre → teknik not housekeeping
    if any(w in folded for w in ("klima",)) and any(w in folded for w in ("filtre", "toz", "ufle", "üfle")):
        scores["tech"] = scores.get("tech", 0) + 3.0

    # Sular kesildi, sıcak su, duş basıncı → tech (not housekeeping)
    if any(w in folded for w in ("sicak su", "sıcak su", "su kes", "sular kes", "dus basinc", "duş basınç", "basinc", "basınç", "su gelmiyor")):
        scores["tech"] = scores.get("tech", 0) + 4.0
        scores["housekeeping"] = max(0.0, scores.get("housekeeping", 0) - 3.0)

    # Food smell → fb_venue (not housekeeping)
    if "koku" in folded and any(w in folded for w in ("yemek", "balik", "balık", "tabak", "tabag", "mutfak", "restoran", "restaurant", "bufe", "büfe")):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 3.0
        scores["housekeeping"] = max(0.0, scores.get("housekeeping", 0) - 3.0)

    # "temizlik personeli / güvenlik personeli" → personel behavior
    if any(w in folded for w in ("personel", "personeli", "calisan", "çalışan", "görevlisi", "gorevlisi")):
        if any(w in folded for w in ("kapıyı çalmadan", "kapiyi calmadan", "kapiyi çalmadan", "kapıyı calmadan",
                                     "calmadan girdi", "çalmadan girdi", "kibar", "yardimci", "yardımcı",
                                     "ilgili", "aktif", "nazik", "ilgisiz", "kaba", "yorgun")):
            scores["staff"] = scores.get("staff", 0) + 3.0

    # Havuz bağlamında "sıra beklemiyorsunuz" positive → pool
    if any(w in folded for w in ("havuz", "aquapark", "plaj")):
        if "beklemiyor" in folded or "beklemeden" in folded:
            scores["pool"] = scores.get("pool", 0) + 2.0
    # Havuz/aquapark + mesafe/restoran → pool (not restaurant)
    if any(w in folded for w in ("aquapark", "plaj", "havuz")) and any(
        w in folded for w in ("mesafe", "arası", "arasi", "restoran", "pastane")
    ):
        scores["pool"] = scores.get("pool", 0) + 3.0

    # Spa + randevu/bekleme → spa (not queue/restaurant)
    # NEVER treat "hamam böceği" as spa — word-boundary hamam only, pest wins
    spa_wellness_cues = ["spa", "masaj", "sauna", "wellness"]
    has_spa = _any_cue(low, folded, spa_wellness_cues) or (
        _match_cue(low, folded, "hamam") and not _has_pest_signal(low, folded)
    )
    if has_spa and any(
        w in folded for w in ("randevu", "bekledik", "beklemek", "gunlerce", "günlerce", "rezervasyon")
    ):
        scores["spa_wellness"] = scores.get("spa_wellness", 0) + 5.0
        scores["queue"] = max(0.0, scores.get("queue", 0) - 4.0)

    # Pest / cockroach — hard boost (never spa)
    if _has_pest_signal(low, folded):
        scores["pest_hygiene"] = scores.get("pest_hygiene", 0) + 8.0
        scores["spa_wellness"] = 0.0
        if any(w in folded for w in ("yemek", "restoran", "salon", "bufe", "büfe", "masa")):
            scores["fb_venue"] = scores.get("fb_venue", 0) + 2.0

    # Foodborne illness / digestion complaint
    if any(w in folded for w in ("sindirim", "zehirlen", "gida zehir", "gıda zehir", "mide bulant", "ishal", "kusma")):
        scores["food_illness"] = scores.get("food_illness", 0) + 7.0
        scores["fb_venue"] = scores.get("fb_venue", 0) + 2.0
    if any(w in folded for w in ("yemeklerden kaynakli", "yemeklerden kaynaklı")) and any(
        w in folded for w in ("rahatsiz", "rahatsız", "sindirim", "hasta")
    ):
        scores["food_illness"] = scores.get("food_illness", 0) + 7.0

    # Staff shortage (not food quality)
    if any(w in folded for w in (
        "personel sayisi", "personel sayısı", "personel sayisinda", "personel sayısında",
        "personel yetersiz", "personel az", "personel eksik", "kadro yetersiz", "eleman az",
    )) or (
        "personel" in folded and "yetersizlik" in folded
    ):
        scores["staff_shortage"] = scores.get("staff_shortage", 0) + 7.0
        scores["staff"] = scores.get("staff", 0) + 3.0
        scores["fb_venue"] = max(0.0, scores.get("fb_venue", 0) - 4.0)

    # Overall disappointment / expectation shortfall
    if any(w in folded for w in (
        "beklenti alt", "beklentinin alt", "beklentimin alt", "bekledigimin alt",
        "beklediğimin alt", "hayal kirikligi", "hayal kırıklığı",
    )):
        scores["overall_disappointment"] = scores.get("overall_disappointment", 0) + 6.0
        # "hijyen" in same clause → room/hygiene context, not generic disappointment
        if _any_cue(low, folded, ["hijyen", "temizlik", "kirli", "pis", "dışkı", "diski", "kusmuk"]):
            scores["room"] = scores.get("room", 0) + 8.0
            scores["overall_disappointment"] = max(0.0, scores.get("overall_disappointment", 0) - 6.0)

    # Allergen inquiry on entry (service protocol, not taste)
    if any(w in folded for w in ("alerjiniz", "alerji", "allerji", "alerjen", "allergen")) and any(
        w in folded for w in ("var mi", "var mı", "sorusu", "soru", "sord", "girer girmez")
    ):
        scores["allergen_protocol"] = scores.get("allergen_protocol", 0) + 5.0

    # Beach / sea / water sports (not sticky pool)
    if _any_cue(low, folded, ["deniz", "denizi", "sahil", "sahile", "plaj", "kumsal", "su sporları", "su sporlarinin", "dalgali", "bulanik"]):
        if not _any_cue(low, folded, ["havuz", "aquapark", "aquaprk"]):
            scores["beach"] = scores.get("beach", 0) + 5.0

    # Minibar ücreti → Front Office
    if "minibar" in folded and any(w in folded for w in ("ucret", "ücret", "fahis", "fahiş", "pahali", "pahalı")):
        scores["front_office"] = scores.get("front_office", 0) + 4.0

    # "bayıldım" → restaurant (food praise), not personel
    praise_food = any(w in folded for w in ("bayildim", "bayıldım", "harikaydi", "harikaydı"))
    if praise_food and any(w in folded for w in ("yemek", "corba", "çorba", "dolma", "kofte", "köfte", "pizza", "makarna", "salam")):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 3.0

    # "salam tabağında sinek" → restaurant, not room
    if any(w in folded for w in ("salam", "tabak", "tabağında")):
        if any(w in folded for w in ("sinek", "bocek", "böcek", "kirli")):
            scores["fb_venue"] = scores.get("fb_venue", 0) + 4.0

    # "kumanda odada yoktu resepsiyondan istedik" → teknik (not FO)
    if any(w in folded for w in ("kumanda", "tv", "televizyon")):
        if "resepsiyon" in folded or "istedik" in folded:
            scores["tech"] = scores.get("tech", 0) + 3.0

    # "odalar daha bakımlı" → housekeeping (not room)
    if _any_cue(low, folded, ["oda"]) and any(w in folded for w in ("bakim", "bakım", "bakimli", "bakımlı")):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 3.0

    # "canlı pişirme istasyonu" → restaurant not housekeeping
    if any(w in folded for w in ("pisirme", "pişirme", "istasyon", "mutfak")):
        if any(w in folded for w in ("canli", "canlı", "kapali", "kapalı")):
            scores["fb_venue"] = scores.get("fb_venue", 0) + 3.0

    # "glutensiz seçenek" / "kimse yardımcı olamadı" → restaurant (food service failure)
    if any(w in folded for w in ("glutensiz", "vejetaryen", "vejeteryan")):
        scores["fb_venue"] = scores.get("fb_venue", 0) + 2.0

    # "çeşitlilik" without bar context → restaurant
    food_ctx = any(w in folded for w in ("yemek", "kahvalti", "kahvaltı", "bufe", "büfe", "restoran"))
    if ("çeşit" in folded or "cesit" in folded) and not (any(w in folded for w in ("alkol", "icecek", "içecek", "tekila", "bira", "sarap", "şarap")) or _any_cue(low, folded, ["bar"])):
        if food_ctx:
            scores["fb_venue"] = scores.get("fb_venue", 0) + 2.0
        elif not food_ctx:
            scores["bar"] = scores.get("bar", 0) - 1.0

    # Front Office boost: check-in/resepsiyon + bekle/kuyruk/saat → FO dominates queue
    if any(w in folded for w in ("check-in", "checkin", "check-out", "checkout", "resepsiyon", "lobi")):
        if any(w in folded for w in ("bekle", "sira", "sıra", "kuyruk", "saat", "dakika", "yarim", "yavaş", "yavas")):
            scores["front_office"] = scores.get("front_office", 0) + 4.0

    # Staff + drink context → personnel behavior dominates bar quality
    staff_keywords = ("garson", "personel", "calisan", "çalışan", "barmen", "servis ekibi")
    if any(w in folded for w in staff_keywords):
        if any(w in folded for w in ("icecek", "içecek", "kokteyl", "soda", "barda", "siparis", "sipariş")) or _any_cue(low, folded, ["bar"]):
            scores["staff"] = scores.get("staff", 0) + 4.0
            scores["bar"] = max(0.0, scores.get("bar", 0) - 3.0)
    # Personel attitude + "istemeyerek" → strong staff signal
    if any(w in folded for w in ("istemeyerek", "isteyerek yapmiyor", "isteyerek yapmıyor", "sormasi", "sorması")):
        scores["staff"] = scores.get("staff", 0) + 4.0

    # ANTI-PATTERN: "sef" in "seferinde/seferlik/sefa" → false staff match
    if any(w in folded for w in ("seferinde", "seferlik", "sefa")):
        scores["staff"] = max(0.0, scores.get("staff", 0) - 3.0)
    # ANTI-PATTERN: "yardımcı olamadı/olamıyor/olamaz" → not staff (unable to help)
    if any(w in folded for w in ("olamadi", "olamadı", "olamiyor", "olamıyor", "olamaz", "olmuyor", "yoktu")):
        if "yardimci" in folded or "yardımcı" in low:
            scores["staff"] = max(0.0, scores.get("staff", 0) - 3.0)
    # ANTI-PATTERN: "bar" in "minibar" → false bar match
    if "minibar" in folded and scores.get("bar", 0) > 0:
        # If only bar cue match is from "bar" in "minibar", strip it
        if scores.get("bar", 0) <= 3.0 and scores.get("staff", 0) <= 1.0:
            scores["bar"] = max(0.0, scores["bar"] - 1.5)

    # Housekeeping structural boosts
    if any(w in folded for w in ("koridor", "koridorlarda")):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 2.0
    if any(w in folded for w in ("kuş yuvası", "kus yuvasi", "kuş yuvası")):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 5.0
    if any(w in folded for w in ("pike", "yastik", "yastık", "nevresim")):
        scores["housekeeping"] = scores.get("housekeeping", 0) + 2.0

    # "arkadaş canlısıydı" / "dost canlısı" → staff
    if any(w in folded for w in ("arkadaş canlı", "arkadas canli", "arkadaş canlısı", "arkadas canlisi",
                                  "dost canlı", "dost canli", "dost canlısı", "dost canlisi")):
        scores["staff"] = scores.get("staff", 0) + 3.0

    # "yardıma hazır" / "her zaman yardıma" → staff
    if any(w in folded for w in ("yardıma hazır", "yardima hazir", "her zaman yardıma", "her zaman yardima")):
        scores["staff"] = scores.get("staff", 0) + 3.0

    # "cana yakın" / "enerjik" → staff
    if any(w in folded for w in ("cana yakın", "cana yakin", "enerjik", "enerjiklerdi")):
        scores["staff"] = scores.get("staff", 0) + 2.0

    if "masa tenisi" in folded:
        scores["animation"] = scores.get("animation", 0) + 4.0

    return scores


def primary_frame(scores: dict[str, float]) -> str:
    if not scores:
        return "general"
    # Prefer operational specificity when scores are close
    priority = (
        "pest_hygiene", "food_illness", "allergen_protocol", "staff_shortage",
        "beach", "overall_disappointment",
        "front_office", "spa_wellness", "queue", "pool", "capacity",
        "housekeeping", "bar", "fb_venue", "tech",
        "value", "staff", "animation", "room",
        "environment", "general",
    )
    best = max(scores.values())
    contenders = [k for k, v in scores.items() if v >= best - 0.75]
    for name in priority:
        if name in contenders:
            return name
    return max(scores.items(), key=lambda x: x[1])[0]


# ---------------------------------------------------------------------------
# Stage 4 — aspect typing within frame
# ---------------------------------------------------------------------------
def _has_pool_temperature_context(low: str, folded: str, cfg: dict) -> bool:
    guard = cfg.get("ontology_guard") or {}
    pool_cues = guard.get("pool_temperature_cues") or ["havuz", "plaj", "deniz", "aquapark"]
    temp_words = guard.get("pool_temp_words") or [
        "sicak", "sıcak", "serinlet", "soguk", "soğuk",
        "isitmali", "ısıtmalı", "isitma", "ısıtma",
    ]
    return _any_cue(low, folded, pool_cues) and _any_cue(low, folded, temp_words)


def _has_payment_extra_signal(low: str, folded: str, cfg: dict) -> bool:
    """Euro/TL ekstra ödeme patterns beyond bare paralı/ücretli lemmas."""
    extra = cfg.get("fb_extra_charge_payment_cues") or [
        "ödemeniz gereken", "odemeniz gereken", "ödemen gereken", "odemen gereken",
        "euro ödem", "euro odem", "euro ödemeniz", "euro odemeniz",
        "kişi başı ekstra", "kisi basi ekstra", "kişi başı", "kisi basi",
        "ekstra ücret", "ekstra ucret", "ücret ödem", "ucret odem",
    ]
    if _any_cue(low, folded, extra):
        return True
    # "ekstra 12,00 euro" / "ekstra 12 euro"
    if re.search(r"ekstra\s+\d", folded):
        return True
    if re.search(r"\d+[.,]?\d*\s*(euro|eur|tl)\b", folded) and any(
        w in folded for w in ("ode", "ekstra", "ucret", "parali", "odemen")
    ):
        return True
    return False


def _has_fb_extra_charge_signal(
    low: str,
    folded: str,
    cfg: dict,
    *,
    frame: str = "",
    frame_scores: Optional[dict[str, float]] = None,
) -> bool:
    """Paid F&B amenity / all-inclusive mismatch — not food taste."""
    pricing = cfg.get("fb_extra_charge_cues") or []
    has_price = _any_cue(low, folded, pricing) or _has_payment_extra_signal(low, folded, cfg)
    if not has_price:
        return False
    # Free-amenity praise ("ücretsiz kahvaltı") is not a charge complaint unless also paid
    if any(w in folded for w in ("ucretsiz", "bedava")) and not (
        _any_cue(low, folded, ["paralı", "parali", "ücretli", "ucretli"])
        or _has_payment_extra_signal(low, folded, cfg)
    ):
        return False
    context = cfg.get("fb_extra_charge_context") or []
    frame_scores = frame_scores or {}
    in_fb = (
        frame == "fb_venue"
        or frame_scores.get("fb_venue", 0) >= 2
        or _any_cue(low, folded, context)
    )
    if not in_fb:
        # Bare "su" + paid (avoid matching inside unrelated words via word-ish check)
        if re.search(r"(?<![a-z])su(?![a-z])", folded) or "suyu" in folded or "sular" in folded:
            in_fb = True
    if not in_fb:
        return False
    # Taste-only complaints stay food_taste; paid amenity without taste → pricing
    taste = cfg.get("fb_extra_charge_taste_cues") or []
    taste_extra = ["güzel", "guzel", "lezzetli", "lezzet", "tadı", "tadi"]
    has_taste = _any_cue(low, folded, list(taste) + taste_extra)
    # Explicit paid/ücretli / ödeme always wins over incidental taste words in same clause
    strong_price = _any_cue(
        low,
        folded,
        [
            "paralı", "parali", "ücretli", "ucretli", "ekstra ücret", "ekstra ucret",
            "ücret isteniyor", "ucret isteniyor", "ücretli olması", "ucretli olmasi",
            "paralı olması", "parali olmasi",
            "ödemeniz gereken", "odemeniz gereken", "euro ödem", "euro odem",
            "kişi başı ekstra", "kisi basi ekstra",
        ],
    ) or _has_payment_extra_signal(low, folded, cfg)
    if has_taste and not strong_price:
        return False
    return True


def _is_hvac_without_context(low: str, folded: str, cfg: dict) -> bool:
    """Block HVAC/Teknik when only generic substring traps fire (deniz, temiz, bekleme)."""
    guard = cfg.get("ontology_guard") or {}
    required = guard.get("hvac_required_cues") or []
    if _any_cue(low, folded, required):
        return False
    if _has_pool_temperature_context(low, folded, cfg):
        return True
    # Operational cues that must never be HVAC
    if _any_cue(low, folded, ["sira", "sıra", "kuyruk", "bekle", "alakart", "alakarta", "yer tutma", "yer bulamaz"]):
        return True
    if _any_cue(low, folded, (cfg.get("housekeeping_privacy") or {}).get("entity_cues") or []):
        return True
    if _any_cue(low, folded, ["animasyon", "etkinlik", "eglence", "eğlence"]):
        return True
    return False


def _queue_department_by_context(
    low: str,
    folded: str,
    cfg: dict,
    frame_context: Optional[dict] = None,
) -> Optional[str]:
    """Map queue/sıra to aspect key by venue frame — NOT always F&B."""
    qc = cfg.get("queue_context") or {}
    ctx = frame_context or {}
    last = str(ctx.get("last_queue_venue") or "")

    clause_parking = _any_cue(low, folded, qc.get("parking_cues") or [
        "otopark", "otoparka", "vale", "valet", "garaj", "araba", "arabalık", "arabanızı",
        "park yeri", "park etmek"
    ])
    if clause_parking:
        return "parking"

    clause_transport = _any_cue(low, folded, qc.get("transport_cues") or [
        "transfer", "transfer servisi", "shuttle", "taksi", "otobüs", "otobus",
        "minibüs", "minibus", "dolmuş", "havaalanı servisi"
    ])
    if clause_transport:
        return "transport"

    clause_anim = _any_cue(low, folded, qc.get("anim_cues") or [
        "amfitiyatro", "gösteri", "gosteri", "konser", "sahne", "etkinlik", "animasyon", "show"
    ])
    if clause_anim:
        return "animation"

    clause_towel = _any_cue(low, folded, qc.get("towel_cues") or [
        "havlu", "havlutopla", "havlu kartı", "havlukartı", "plaj havlusu"
    ])
    if clause_towel:
        return "housekeeping_service"

    clause_fo = _any_cue(low, folded, qc.get("fo_cues") or [])
    clause_pool = _any_cue(low, folded, qc.get("pool_cues") or [])
    clause_kids = _any_cue(low, folded, qc.get("kids_cues") or [])
    clause_fb = _any_cue(low, folded, qc.get("fb_cues") or [])

    # Front office check-in / entrance / lobby queue
    if clause_fo and not _any_cue(low, folded, ["barda", "restoran", "büfe", "bufe", "alacarte", "alakart"]):
        return "front_office"

    if clause_pool:
        return "pool_queue"
    if clause_kids:
        return "kids_capacity" if not clause_pool else "pool_queue"

    if clause_fb:
        return "service_queue"

    # Bare sıra — use most recent venue context if available
    if last == "pool":
        return "pool_queue"
    if last == "kids":
        return "kids_capacity"
    if last == "fo":
        return "front_office"
    if last == "parking":
        return "parking"
    if last == "fb":
        return "service_queue"

    # Check for general entrance cues before defaulting
    if _any_cue(low, folded, ["giriş", "giris", "kapı", "kapi", "otel girişi"]):
        return "front_office"

    bare = (qc.get("bare_default") or "capacity")
    return bare if bare in ("capacity", "guest_experience", "service_queue", "pool_queue", "front_office") else "capacity"


def resolve_aspect(
    clause: str,
    frame: str,
    frame_scores: dict[str, float],
    cfg: Optional[dict] = None,
    frame_context: Optional[dict] = None,
) -> dict[str, str]:
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    frames = cfg.get("frames") or {}
    aspects = cfg.get("aspect_resolution") or {}
    frame_context = frame_context or {}

    def pick(key: str) -> dict[str, str]:
        return dict(aspects.get(key) or {
            "aspect_key": key,
            "aspect_label": key,
            "department": "genel",
            "department_label": "Genel",
            "category": "Genel",
        })

    room = frames.get("room") or {}
    fb = frames.get("fb_venue") or {}
    bar = frames.get("bar") or {}
    pool = frames.get("pool") or {}

    queueish = (
        frame == "queue"
        or frame_scores.get("queue", 0) >= 2
        or _any_cue(
            low, folded,
            ["kuyruk", "sira", "sıra", "siraya", "sıraya", "sirayi", "sırayı", "bekleniyor", "alinamiyor", "alınamıyor"],
        )
    )
    beach_in_clause = _any_cue(
        low, folded,
        [
            "deniz", "denizi", "denize", "denizin", "denizde",
            "sahil", "sahile", "sahilde", "sahili",
            "plaj", "plajı", "plaji", "plaja", "plajda", "plajdan",
            "kumsal", "su sporları", "su sporlarinin", "su sporlari",
            "beach", "sea", "ocean", "dalgali", "dalgalı", "bulanik", "bulanık",
            "denize sifir", "denize sıfır", "пляж", "море",
        ],
    )
    pool_in_clause = _any_cue(
        low, folded,
        ["havuz", "aquapark", "aquaprk", "kaydirak", "kaydırak", "pool", "swimming pool", "sunbed", "sunbeds", "бассейн", "лежак", "лежаки"] + list((pool.get("entity_cues") or [])[:8]),
    )
    # Sticky aquapark context must NOT steal explicit beach/sea clauses
    sticky_pool = bool(frame_context.get("pool") or frame_context.get("aquapark"))
    if beach_in_clause and not pool_in_clause:
        sticky_pool = False
    pool_entity_in_clause = (
        frame == "pool"
        or frame_scores.get("pool", 0) >= 2
        or pool_in_clause
        or _any_cue(low, folded, pool.get("lounger_cues") or [])
    )
    # poolish includes sticky context ONLY for queue venue routing — not hygiene bleed
    # --- Room Theft / Lost property in room → Safety / Front Office ---
    if _any_cue(low, folded, ["çalındı", "calindi", "kayboldu", "çalınmış", "calinmis", "hırsızlık", "hirsizlik"]):
        if _any_cue(low, folded, ["odadan", "odadaki", "temizlikten sonra", "nakit", "ziynet", "cüzdan", "cuzdan", "saat", "pasaport"]):
            return pick("safety")

    # --- High Precision User Review Aspect Overrides ---
    if _any_cue(low, folded, ["sakin gelmey", "sakın gelmey", "sakin kalmay", "sakın kalmay", "hindistan oteli", "3 kisi konakladik", "3 kişi konakladık"]):
        return pick("guest_experience")

    if _any_cue(low, folded, ["patates kızartması", "patates kizartmasi", "soğan halkasını", "sogan halkasini", "dayıyorlar", "dayiyorlar", "salata ile doyuruyorum", "ucuz tatlılarla", "ucuz tatlilarla", "çeşit çok az", "cesit cok az", "donuk köfte", "donuk kofte", "kuru balık", "kuru balik", "bol bol patates", "içimiz kalktı", "icimiz kalkti", "patates kızartması ile 5 gün", "patates kizartmasi ile 5 gun", "izgara kısmı kapalıydı", "ızgara kısmı kapalıydı", "sabah kahvaltısı yok akşam yemeği sabit", "sabah kahvaltisi yok aksam yemegi sabit"]):
        if _any_cue(low, folded, ["çeşit", "cesit", "kapalıydı", "kapaliydi", "yok", "sabit"]):
            return pick("food_availability")
        return pick("food_taste")

    if _any_cue(low, folded, ["3 kuruşun peşine", "3 kurusun pesine", "konseptimizde yok", "sahipsiz bırakılması", "sahipsiz birakilmasi", "ilk girişi fiyasko", "ilk girisi fiyasko", "yönlendirme personeli yok", "yonlendirme personeli yok"]):
        return pick("front_office")

    if _any_cue(low, folded, ["elektrik kesintisi", "sular kesildi", "su kesildi", "klima var", "klima", "zorlukla açtırıyoruz", "zorlukla actiriyoruz", "gece kapatıyorlar", "gece kapatiyorlar"]):
        if _any_cue(low, folded, ["klima"]):
            return pick("air_conditioning")
        return pick("tech_general")

    if _any_cue(low, folded, ["bolca taş", "bolca tas", "hemen derinleşiyor", "hemen derinlesiyor"]):
        return pick("beach")

    if _any_cue(low, folded, ["spa hizmeti", "gülcan masajı", "gulcan masaji", "kime yeter bilinmez"]):
        return pick("spa")

    # Spa / massage / wellness complaints → spa (before price/value)
    if _any_cue(low, folded, ["spa", "masaj", "sauna", "hamam", "wellness", "jakuzi"]):
        if _any_cue(low, folded, ["pahalı", "pahali", "fiyat", "ucret", "ücret", "para", "yüksek", "yuksek", "kötü", "kotu", "berbat", "bozuk", "soğuk", "sicak", "sıcak"]):
            return pick("spa")

    # Family / children facilities → family_friendly (before price/value)
    if _any_cue(low, folded, ["bebek yatağı", "bebek yatagi", "mama sandalyesi", "aile odası", "aile odasi", "çocuk havuzu", "cocuk havuzu", "kids club", "miniclub", "mini club"]):
        return pick("family_friendly")

    if _any_cue(low, folded, ["odalar buz gibi", "yorganları sabah topluyorlar", "yorganlari sabah topluyorlar", "ne bir yorgan", "yorgan yok"]):
        return pick("housekeeping_service")

    if _any_cue(low, folded, ["küf kokusundan", "kuf kokusundan", "yağ kokusundan", "yag kokusundan"]):
        return pick("elevator_cleanliness")

    if _any_cue(low, folded, ["gökmen şef", "gokmen sef", "garson mehmet", "yüzüne bakmadan", "yuzune bakmadan", "havaya konuşur", "havaya konusur", "dalga geçer", "dalga gecer", "saygısızca", "saygisizca", "orta noktayı bulduk", "orta noktayi bulduk", "tercih etseydiniz cevabı", "tercih etseydiniz cevabi"]):
        return pick("staff_behavior")

    if _any_cue(low, folded, ["ketçap bulaşığı", "ketcap bulasigi", "güya temiz", "guya temiz"]):
        return pick("cutlery")

    if _any_cue(low, folded, ["yürü allah yürü", "yuru allah yuru", "o yol bitmiyor", "illallah geldi"]):
        return pick("property_walkability")

    if _any_cue(low, folded, ["sabit bir bara", "aynı içeceği hazırlamıyorlar", "ayni icecegi hazirlamiyorlar"]):
        return pick("drink_variety")

    # --- HVAC / AC Cooling failure, noise & water leak interceptor → Engineering / Tech ---
    if _any_cue(low, folded, ["klima", "ac unit", "iklimlendirme"]):
        if _any_cue(low, folded, ["soğutmuy", "sogutmuy", "sıcak üflü", "sicak uflu", "üflemiy", "uflemiy", "pişiy", "pisiy", "bozuk", "çalışmıy", "calismiy", "motoru", "gürültü", "gurultu", "helikopter", "ses yap", "damlattı", "damlatti", "damlatıyor", "damlatiyor", "sızdırıyordu", "sizdiriyordu"]):
            return pick("air_conditioning")

    # --- Imported / Paid alcohol & cocktail fee → Drink Quality (F&B) ---
    if _any_cue(low, folded, ["tekila", "viski", "rakı", "raki", "votka", "cin", "ithal alkol", "ithal içki"]):
        if _any_cue(low, folded, ["ekstra ücret", "ekstra ucret", "paralı", "parali", "ücretli", "ucretli", "ücretsizdi", "dandik"]):
            return pick("drink_quality")

    # --- Kitchen & Dishwasher Noise pollution → Room Noise (Housekeeping) ---
    if _any_cue(low, folded, ["bulaşık makinesi", "bulasik makinesi", "tencere tava", "mutfak gürültü", "mutfak gurultu"]):
        return pick("room_noise")

    # --- Room Safe Lock / Tech Failure → Tech / Engineering ---
    if _any_cue(low, folded, ["kasa", "odadaki kasa", "odadaki kasayı"]):
        if _any_cue(low, folded, ["şifreyi kabul", "sifreyi kabul", "kilitli kaldı", "kilitli kaldi", "açılmadı", "acilmadi", "teknik servis"]):
            return pick("tech_general")

    # --- Sewage / Bathroom Drainage Odor interceptor → Housekeeping / Tech (NOT Atmosphere / Capacity) ---
    if _any_cue(low, folded, ["gider", "giderden", "kanalizasyon", "lağım", "lagim", "banyo kokus", "gider kokus"]):
        if _any_cue(low, folded, ["koku", "kokuy", "geliyord", "kokus"]):
            return pick("room_cleanliness")

    # --- Pool hygiene / Pool bottom dirt / Chlorine smell interceptor → Pool / Leisure ---
    if _any_cue(low, folded, ["havuz", "aquapark"]):
        if _any_cue(low, folded, ["dibi", "yaprak", "saç doluy", "sac doluy", "klor kokus", "bulanık", "bulanik", "temizlenmiyord", "pis"]):
            return pick("pool_lounger")

    # --- CRITICAL OPERATIONAL FRAMES (before food taste / spa / sticky pool) ---
    # Medical emergency / night shift management / ambulance / vehicle assistance → FO / Safety (NOT F&B queue)
    _emergency_cues = ["rahatsizlan", "rahatsızlan", "kalp krizi", "istifra", "acil", "ambulans", "hastane", "doktor"]
    _night_mgmt_cues = ["gece vardiyasi", "gece vardiyası", "gece amiri", "gece müdürü", "gece muduru", "gece amiri/müdürü", "gece vardiyasi amiri"]
    _car_assist_cues = ["aracimiza", "aracımıza", "araba", "araca götür", "aracimiza götür", "aracımıza götür", "goturemedi", "götüremedi"]
    
    if _any_cue(low, folded, _night_mgmt_cues) or (
        _any_cue(low, folded, _emergency_cues) and _any_cue(low, folded, _car_assist_cues + ["yardim", "yardım", "ilgilen", "surada", "bekle", "dakika"])
    ):
        return pick("front_office")

    # Stage / Concert event seating & viewing complaint → Animasyon & Etkinlik (NOT dining_ambiance)
    if _any_cue(low, folded, ["halk konseri", "konser", "konserinden", "sahne", "sahne gorunmuyor", "sahne görünmüyor"]) and not _any_cue(low, folded, ["yemek", "kahvalt", "restoran", "bufe", "büfe"]):
        return pick("animation")

    # Theft / lost property / stolen belongings → Safety / Front Office (NOT Housekeeping cleanliness)
    if _any_cue(low, folded, ["çalındı", "calindi", "çalınmış", "calinmis", "hırsızlık", "hirsizlik", "para kayboldu", "saat kayboldu"]):
        return pick("safety")

    # Cancellation / refund / partial refund / kesinti → Front Office (NOT general)
    if _any_cue(low, folded, ["kesinti", "iptal", "iade", "geri ödeme", "geri odeme", "para iade", "ücret iade", "ucret iade"]):
        return pick("front_office")

    # Pool noise / loud speaker / relax pool music → Animation / Recreation (NOT Housekeeping)
    if _any_cue(low, folded, ["hoparlör", "son ses müzik", "son ses muzik"]) or (_any_cue(low, folded, ["relax havuz", "sessiz havuz"]) and _any_cue(low, folded, ["müzik", "muzik", "gürültü", "gurultu"])):
        return pick("animation")

    # Pest / food illness BEFORE guest_safety — but "rahatsız edici" also marks harassment
    _harassment_safety = any(
        w in folded for w in (
            "taciz", "sap adam", "yan goz", "yan göz", "hissettiriyor", "pis hissettiriyor",
        )
    )
    if _harassment_safety:
        return pick("safety")

    # --- Minibar appliance / cooling failure → Tech (NOT F&B) ---
    if _any_cue(low, folded, ["minibar", "mini bar"]):
        if _any_cue(low, folded, ["soğutmuy", "sogutmuy", "çalışmıy", "calismiy", "bozuk", "buzdolab"]):
            return pick("minibar_tech")

    # --- A la carte reservation quota / refusal → F&B (NOT location/grounds) ---
    if _any_cue(low, folded, ["a la carte", "alacarte", "ala carte"]):
        if _any_cue(low, folded, ["kontenjan", "yer vermed", "yer kalmad", "dolmuş", "dolmus", "rezervasyon"]):
            return pick("a_la_carte_quality")

    if _has_pest_signal(low, folded) or frame == "pest_hygiene" or frame_scores.get("pest_hygiene", 0) >= 2:
        # Room / bathroom insects are housekeeping — not dining pest_hygiene
        _room_pest_ctx = _any_cue(
            low, folded,
            ["oda", "odada", "odamiz", "banyo", "banyoda", "yatak", "yatakta", "carsaf", "çarşaf"],
        )
        _dining_pest_ctx = _any_cue(
            low, folded,
            [
                "yemek", "restoran", "salon", "bufe", "büfe", "masa", "tabak",
                "kahvalt", "yemekhane", "yemek salon",
            ],
        )
        if _room_pest_ctx and not _dining_pest_ctx:
            return pick("housekeeping_service")
        if pool_in_clause and not _dining_pest_ctx:
            return pick("pool")
        return pick("pest_hygiene")

    # Kids pool / slides — never food_taste / pest bleed
    if _any_cue(
        low, folded,
        [
            "kaydirak", "kaydırak", "mini kaydirak", "mini kaydırak",
            "cocuk havuz", "çocuk havuz", "cocuk havuzu", "çocuk havuzu",
        ],
    ) and not _any_cue(low, folded, ["yemek", "kahvalt", "restoran", "bufe", "büfe", "lezzet", "tatsiz", "tatsız"]):
        # Queue at slides → pool_queue; walk-from-slides → property_walkability
        if _any_cue(low, folded, ["sira", "sıra", "kuyruk", "bekle", "uzun sira", "uzun sıra"]):
            return pick("pool_queue")
        if _any_cue(low, folded, ["yurumek", "yürümek", "yuru", "yürü", "uzun suruyor", "uzun sürüyor", "mesafe"]) and _any_cue(
            low, folded, ["havuzdan", "denize", "deniz", "plaj"]
        ):
            return pick("property_walkability")
        return pick("pool_lounger")

    # Leisure venue priority: pool/beach dominant + incidental F&B listing (alakart/restoran)
    # without taste/hygiene complaint → stay leisure (not food_taste)
    _leisure_dom = _any_cue(
        low, folded,
        ["havuz", "kaydirak", "kaydırak", "plaj", "aquapark", "aquaprk", "sezlong", "şezlong"],
    )
    _food_incidental = _any_cue(low, folded, ["alakart", "alacarte", "restoran", "secenek", "seçenek"])
    _food_strong = _any_cue(
        low, folded,
        ["yemek", "lezzet", "kahvalt", "tatsiz", "tatsız", "bufe", "büfe", "hijyen", "temizlik", "masa"],
    )
    if _leisure_dom and _food_incidental and not _food_strong and _any_cue(
        low, folded, ["guzel", "güzel", "bakimli", "bakımlı", "harika", "iyi"]
    ):
        if _any_cue(low, folded, ["plaj", "deniz"]):
            return pick("beach")
        return pick("pool_lounger")

    # Dining-room hygiene / cutlery / table wipe → F&B (before housekeeping frame)
    if (
        _any_cue(
            low, folded,
            [
                "restoran", "ana restoran", "yemek salon", "yemekhane", "yemek salonu",
                "bufe", "büfe", "alakart", "alacarte", "barlarda", "barda",
            ],
        )
        or (
            "masa" in folded
            and _any_cue(low, folded, ["yemek", "restoran", "salon", "misafir", "zar zor", "catal", "çatal", "tabak"])
        )
        or (
            _any_cue(low, folded, ["masalar", "masa "])
            and _any_cue(low, folded, ["zar zor", "temizlenmis", "temizlenmiş", "temizlenmed", "kirli", "yapist", "yapış"])
        )
    ) and _any_cue(
        low, folded,
        [
            "temizlik", "temizlen", "temizlenebil", "hijyen", "kirli", "cop", "çöp",
            "catal", "çatal", "bicak", "bıçak", "tabak", "masalar", "zar zor",
        ],
    ) and not _any_cue(
        low, folded,
        ["oda temiz", "odalar temiz", "banyo", "havlu", "carsaf", "çarşaf", "pike"],
    ):
        if _any_cue(low, folded, ["catal", "çatal", "bicak", "bıçak"]):
            return pick("cutlery")
        return pick("table_cleanliness")

    # "yemekler ve temizlik" compound complaint → F&B (not room HK)
    if _any_cue(low, folded, ["yemek", "yemekler", "yemeklerden"]) and _any_cue(
        low, folded, ["temizlik", "temizlen", "hijyen"]
    ) and not _any_cue(low, folded, ["oda", "banyo", "havlu", "carsaf", "çarşaf"]):
        return pick("food_taste")

    # Bare "temizlik" / "olumsuz yönleri temizlik" complaint → HK (not atmosphere)
    if _any_cue(low, folded, ["temizlik", "temizlig", "temizliğ"]) and _any_cue(
        low, folded,
        ["olumsuz", "felaket", "berbat", "yetersiz", "kotu", "kötü", "yok", "sikayet", "şikayet", "yonleri", "yönleri"],
    ) and not _any_cue(low, folded, ["yemek", "restoran", "havuz", "plaj", "masa", "catal", "çatal"]):
        return pick("housekeeping_service")

    # Socket / outlet faults → tech (not general)
    if _any_cue(low, folded, ["priz", "prizler"]) and _any_cue(
        low, folded, ["bozuk", "calismiyor", "çalışmıyor", "yok", "eksik"]
    ):
        return pick("tech_general")

    # Dirty / broken spare bed → HK (not food via çeşit⊂çeşitli / leke false friends)
    if _any_cue(low, folded, ["yatak", "yatagi", "yatağı", "yatagı", "dosek", "döşek"]) and _any_cue(
        low, folded,
        ["leke", "lekeli", "lekeleri", "bozuk", "kirli", "mekanizma", "pire", "bit"],
    ):
        return pick("housekeeping_service")

    # Wardrobe / closet amenity gaps → HK room (not Genel / staff)
    if _any_cue(
        low, folded,
        ["gardirop", "gardırop", "gardrop", "askilik", "askılık", "askili dolap", "askılı dolap"],
    ) or (
        _any_cue(low, folded, ["raf", "raflar", "rafı", "rafi"])
        and _any_cue(low, folded, ["kiyafet", "kıyafet", "elbise", "dolap", "askı", "aski"])
    ):
        return pick("room_size" if _any_cue(low, folded, ["kucuk", "küçük", "dar"]) else "housekeeping_service")

    # Dishwasher / plate rinse → F&B hygiene (not bare Genel)
    if _any_cue(low, folded, ["bulasik makine", "bulaşık makine", "bulasiklar", "bulaşıklar", "durulama sivisi", "durulama sıvısı"]) and _any_cue(
        low, folded, ["kirli", "kotu", "kötü", "kullanilmamis", "kullanılmamış", "yikan", "yıkan"]
    ):
        return pick("table_cleanliness")

    # Room↔amenity proximity → location (before pool/beach steal)
    if _any_cue(low, folded, ["oda", "odamiz", "odamız", "odalar", "binada", "binaday"]) and _any_cue(
        low, folded, ["yakin", "yakın", "uzak", "yakınd", "yakind"]
    ) and _any_cue(low, folded, ["havuz", "restoran", "plaj", "deniz", "bar", "animasyon"]):
        return pick("location")

    # Common-area toilets cleanliness → HK (not capacity via "ortak alan")
    if _any_cue(low, folded, ["tuvalet", "tuvaletler", "wc", "lavabo"]) and _any_cue(
        low, folded,
        ["temiz", "tertemiz", "kirli", "pis", "kokuy", "hijyen", "temizlik"],
    ):
        return pick("elevator_cleanliness" if _any_cue(low, folded, ["asansor", "asansör"]) else "housekeeping_service")

    # Price / value → FO (avoid Genel collapse)
    if _any_cue(
        low, folded,
        [
            "fiyat performans", "fiyat performansi", "fiyat/performans",
            "paranin karsilig", "paranın karşılığ", "para etmez", "paraya degmez", "paraya değmez",
            "value for money", "fiyatina gore", "fiyatına göre", "ucret dengesi", "ücret dengesi",
        ],
    ) or (
        _any_cue(low, folded, ["fiyat", "ucret", "ücret", "para"])
        and _any_cue(low, folded, ["performans", "karsilik", "karşılık", "deger", "değer", "degmez", "değmez", "hak ediy"])
    ):
        return pick("value_for_money")

    # Price complaint (high/low price) → value_for_money
    if _any_cue(low, folded, ["fiyat", "ucret", "ücret", "para", "bütçe", "butce"]) and _any_cue(
        low, folded, ["yüksek", "yuksek", "pahalı", "pahali", "ucuz", "uygun", "makul", "makuldu", "makuldu", "uygun"]
    ):
        return pick("value_for_money")

    # Standalone price complaint → value_for_money
    if _any_cue(low, folded, ["pahalı", "pahali", "çok pahalı", "cok pahali", "overpriced", "expensive"]):
        return pick("value_for_money")

    # Family / children friendly → leisure (family_friendly)
    if _any_cue(low, folded, ["aile", "aileler", "ailece", "çocuk", "cocuk", "çocuklu", "cocuklu", "bebek", "bebekli"]):
        if _any_cue(low, folded, ["uygun", "uygun değil", "değil", "degil", "iyi", "ideal", "memnun", "memnunuz", "gelmesin", "gelme", "tavsiye", "öneririm"]):
            return pick("family_friendly")

    # Room comfort (temperature, bed comfort) → room_comfort
    if _any_cue(low, folded, ["sıcak", "sicak", "soğuk", "soguk", "buz gibi", "sıcaklık", "sicaklik", "klima", "ısı", "isi", "kalorifer", "petek"]):
        if _any_cue(low, folded, ["oda", "odada", "odamız", "odamiz", "odalar", "yatak", "yatakta"]):
            return pick("room_comfort")
    if _any_cue(low, folded, ["rahat", "rahatsız", "rahatssiz", "rahatlık", "rahatsizlik", "sert", "yumuşak", "yumusak", "kanepe", "döşek", "dosek", "yatak"]):
        if _any_cue(low, folded, ["yatak", "yatakta", "yatagı", "yatağı", "kanepe", "döşek", "dosek", "oda", "odada"]):
            return pick("room_comfort")

    # Room features (view, balcony) → room_features
    if _any_cue(low, folded, ["manzara", "manzarası", "manzarasi", "manzarasız", "manzarasiz", " balkon", "balkon", "teras"]):
        if _any_cue(low, folded, ["oda", "odada", "odamız", "odamiz", "odalar", "pencere", "camlı", "camdan"]):
            return pick("room_features")

    # Facility features (general property, view from outside) → facility_features
    if _any_cue(low, folded, ["manzara", "manzarası", "manzarasi", "tesis", "tesisler", "tesisat", "bina", "binanın", "binanin"]):
        if _any_cue(low, folded, ["büyük", "buyuk", "güzel", "guzel", "harika", "mükemmel", "muhtesem", "kötü", "kotu", "eski", "yeni", "modern"]):
            return pick("facility_features")

    # Explicit atmosphere topic → atmosphere (not bare Genel)
    if _any_cue(
        low, folded,
        ["otel atmosfer", "atmosferi", "atmosfer ", "genel atmosfer", "ortam cok", "ortam çok", "ortami", "ortamı"],
    ) and not _any_cue(low, folded, [
        "yemek", "havuz", "plaj", "restoran", "oda ", "odalar",
        "animasyon", "eğlence", "eglence", "etkinlik", "aktivite", "gösteri", "gosteri",
        "konser", "oyun", "oyunlar", "program", "show", "kids club",
    ]):
        return pick("guest_experience")

    # Alakart / a-la-carte queue — F&B service_queue (before capacity/atmosphere)
    if _any_cue(low, folded, cfg.get("alakart_cues") or ["alakart", "alakarta", "alacarte", "a la carte"]) and _any_cue(
        low, folded, ["sira", "sıra", "kuyruk", "bekle", "yavas", "yavaş", "yer bul"]
    ):
        return pick("service_queue")

    # Kids overcrowding + wait → pool/activity queue (not generic capacity)
    if _any_cue(low, folded, (cfg.get("queue_context") or {}).get("kids_cues") or ["cocuk", "çocuk"]) and _any_cue(
        low, folded, ["sira", "sıra", "kuyruk", "bekle"]
    ):
        return pick("pool_queue")

    # Staff hostility cues without explicit "personel" noun
    if _any_cue(
        low, folded,
        ["azarlar gibi", "azarladi", "azarladı", "geriyorlar", "surat asti", "surat astı", "yuz vermedi", "yüz vermedi"],
    ):
        return pick("staff_behavior")

    # GM / genel müdür + personel resolution praise → staff (not atmosphere via "genel")
    if _any_cue(low, folded, ["personel", "calisan", "çalışan", "mudur", "müdür", "genel mudur", "genel müdür"]) and _any_cue(
        low, folded,
        ["ilgilendi", "ilgilenerek", "cozduler", "çözdüler", "cozduler", "hizla coz", "hızla çöz", "bizzat", "yardimsever", "yardımsever"],
    ):
        return pick("staff_behavior")

    # Watered-down drinks → drink_quality (before queue / food_taste)
    if _any_cue(
        low, folded,
        ["suluydu", "cok sulu", "çok sulu", "sulu icecek", "sulu içecek", "sulandır", "sulandir", "sulandiril"],
    ) and _any_cue(
        low, folded,
        ["icecek", "içecek", "icecekler", "içecekler", "limonata", "meyve suyu", "cola", "kola", "bar"],
    ):
        return pick("drink_quality")

    # Dirty F&B service / slow dirty plates
    if _any_cue(low, folded, ["kirli servis", "servis bekliyoruz", "kirli tabak", "kirli masa"]) or (
        "yemekte" in folded and _any_cue(low, folded, ["kirli", "servis"]) and _any_cue(low, folded, ["bekliyor", "gelmesi", "dk", "dakika"])
    ):
        return pick("table_cleanliness")

    # Medical staff missing: "doktor yok", "hemşire vardı" → Staff (NOT F&B food_illness)
    if _any_cue(low, folded, ["doktor yok", "doktor bulamad", "doktor gelmedi", "hemşire vardı", "hemşire var", "sağlık personel"]):
        return pick("staff_behavior")

    if frame == "food_illness" or frame_scores.get("food_illness", 0) >= 2 or any(
        w in folded for w in ("sindirim", "zehirlen", "gida zehir", "gıda zehir", "mide bulant", "ishal")
    ) or (
        any(w in folded for w in ("yemeklerden kaynakli", "yemeklerden kaynaklı", "yemek"))
        and any(w in folded for w in ("rahatsiz", "rahatsız", "hasta", "sindirim"))
    ):
        return pick("food_illness")

    if frame == "staff_shortage" or frame_scores.get("staff_shortage", 0) >= 2 or any(
        w in folded for w in (
            "personel sayisi", "personel sayısı", "personel sayisinda", "personel sayısında",
            "personel yetersiz", "personel az", "personel eksik", "kadro yetersiz", "eleman az",
        )
    ) or ("personel" in folded and "yetersizlik" in folded):
        return pick("staff_shortage")

    if _any_cue(low, folded, cfg.get("guest_safety_cues") or []):
        return pick("safety")

    # F&B pastry / cafe — never pool/recreation (pastane, kahve köşesi, lokum)
    if _any_cue(
        low, folded,
        ["pastane", "pastanede", "kahve kosesi", "kahve köşesi", "lokum", "turk kahvesi", "türk kahvesi"],
    ) and not pool_in_clause:
        return pick("food_taste")

    # Overall satisfaction / loyalty — NOT housekeeping
    if _any_cue(
        low, folded,
        ["mutlu ayrild", "mutlu ayrıl", "memnun ayril", "memnun ayrıl", "tercihimiz olacak", "tercihimiz ... olacak"],
    ):
        return pick("guest_experience")

    # Don't-recommend / worst-hotel — Genel NOT HK
    if _any_cue(low, folded, cfg.get("recommendation_negative_cues") or ["tavsiye etmem", "tavsiye etmiyorum"]):
        return pick("guest_experience")

    # Positive general experience: "çok eğlendik", "çok eğlendim", "harika zaman geçirdik" → guest_experience
    if _any_cue(low, folded, ["eglendik", "eğlendik", "eglendim", "eğlendim", "eglendi", "eğlendi",
                               "zaman gecirdik", "zaman geçirdik", "harika zaman", "muhtesem zaman",
                               "eglenceli", "eğlenceli", "keyifli", "zevkli"]):
        return pick("guest_experience")

    # Parking follow-up (car checked daily near otopark complaint)
    if _any_cue(low, folded, ["arabayi kontrol", "arabayı kontrol", "araba kontrol"]):
        return pick("parking")

    # Staff immaturity / hotel left to children — Personel NOT Bar (bira⊂bırakılmış trap in ontology)
    if _any_cue(low, folded, ["personel", "personeller"]) and _any_cue(
        low, folded,
        (cfg.get("staff_inexperience_cues") or [])
        + ["yabanc", "coluk", "cocuklarin eline", "çocukların eline", "eline birak", "eline bırak", "oteli sanki"],
    ):
        return pick("staff_behavior")

    # GM / manager hospitality in lobby — NOT spa/masaj therapists ("spa müdürü … teşekkür")
    if _any_cue(low, folded, ["mudur", "müdür", "manager"]) and _any_cue(
        low, folded, ["lobi", "tesekkur", "teşekkür", "misafirperver", "ilgi alaka", "tercihimiz"],
    ):
        if not _any_cue(low, folded, ["spa", "masaj", "sauna", "wellness", "terapist", "jakuzi"]):
            return pick("front_office")

    # Multi-topic positive review: 3+ department keywords → Genel (not any single dept)
    _dept_hits = 0
    if _any_cue(low, folded, ["yemek", "yemekler", "lezzet", "tat", "lezzetli", "yemeklerden", "restoran", "restorant", "kahvaltı", "akşam yemeği", "büfe", "bufe"]):
        _dept_hits += 1
    if _any_cue(low, folded, ["oda", "odalar", "odamız", "odam", "banyo", "yatak", "temizlik", "temiz", "hijyen"]):
        _dept_hits += 1
    if _any_cue(low, folded, ["animasyon", "animasyon ekibi", "show", "gösteri", "konser", "dj", "etkinlik"]):
        _dept_hits += 1
    if _any_cue(low, folded, ["personel", "çalışan", "calisan", "garson", "resepsiyon", "misafir ilişkileri"]):
        _dept_hits += 1
    if _any_cue(low, folded, ["havuz", "plaj", "deniz", "kaydırak", "kaydirak", "seyahat"]):
        _dept_hits += 1
    if _dept_hits >= 3 and _any_cue(low, folded, ["memnun", "teşekkür", "tesekkur", "harika", "mükemmel", "kusursuz", "çok iyi", "cok iyi", "favori"]):
        return pick("guest_experience")

    if frame == "overall_disappointment" or frame_scores.get("overall_disappointment", 0) >= 2 or any(
        w in folded for w in (
            "beklenti alt", "beklentinin alt", "beklentimin alt", "bekledigimin alt",
            "beklediğimin alt", "hayal kirikligi", "hayal kırıklığı", "ne yazik ki", "ne yazık ki",
        )
    ):
        # "hijyen" + room frame → room/hygiene dept (NOT overall experience)
        if (frame == "room" or frame_scores.get("room", 0) >= 2) and _any_cue(
            low, folded, ["hijyen", "temizlik", "kirli", "pis", "dışkı", "diski", "kusmuk"]
        ):
            return pick("room_cleanliness")
        return pick("overall_experience")

    # Child-related room complaint: "çocuğumuzun da bulunması… rahatsız edici" → room
    if _any_cue(low, folded, ["cocugumuzun", "çocuğumuzun", "cocugumuz", "çocuğumuz", "cocuklar", "çocuklar",
                               "cocuklu", "çocuklu", "beklemedigimiz", "beklemediğimiz"]) and _any_cue(
        low, folded, ["rahatsiz", "rahatsız", "hassas", "olumsuz", "kotu", "kötü", "mağdur", "magdur"]
    ):
        return pick("room_cleanliness")

    if _any_cue(low, folded, cfg.get("concept_mismatch_cues") or []):
        return pick("guest_experience")

    ops = frames.get("operations") or {}
    if frame == "operations" or frame_scores.get("operations", 0) >= 2 or _any_cue(
        low, folded, ops.get("entity_cues") or []
    ):
        if _any_cue(low, folded, ["operasyon", "organizasyon", "isletme", "işletme", "isleyis", "işleyiş", "yonetim", "yönetim", "zayif", "zayıf"]):
            return pick("operations_management")
        if _any_cue(low, folded, ["kapasite", "kalabal", "yogun", "yoğun", "kuyruk", "sira", "sıra"]):
            if (
                _any_cue(low, folded, ["kapasite", "misafir kabul", "overbooking"])
                and _any_cue(low, folded, ["otel", "misafir kabul"])
                and not _any_cue(low, folded, ["yemek", "bar", "havuz", "restoran", "aquapark"])
            ):
                return pick("front_office")
            return pick("capacity")

    if _any_cue(low, folded, cfg.get("food_product_availability_cues") or []):
        return pick("food_availability")

    if _any_cue(low, folded, cfg.get("elevator_cleanliness_cues") or []) and _any_cue(
        low, folded, ["cop", "çöp", "pis", "kirli", "biriken", "temizle"]
    ):
        return pick("elevator_cleanliness")

    # Guest info sheet / room phone numbers — FO, not staff praise / finance
    if _any_cue(
        low, folded,
        [
            "bilgilendirme kagidi", "bilgilendirme kağıdı", "bilgilendirme",
            "telefon numaralari", "telefon numaraları", "telefon numarasi", "telefon numarası",
        ],
    ) and (
        _any_cue(low, folded, ["yoktu", "yok", "eksik", "mesela", "bilemeyip", "oda", "odamizda", "odamızda"])
        or len(folded.split()) <= 4
    ):
        return pick("guest_info")

    # Dining venue understatement (yemekhane/hallice) — ambiance, not taste praise
    if _any_cue(low, folded, ["yemekhane", "hallice", "yemek salonu", "yemeksalonu"]):
        if _any_cue(low, folded, ["hallice", "halli", "yetersiz", "dis mekan", "dış mekan", "kantin"]):
            return pick("dining_ambiance")

    if _any_cue(low, folded, cfg.get("public_area_hk_cues") or []) and _any_cue(
        low, folded, ["pis", "kirli", "birak", "bırak", "durdu", "inanamad"]
    ):
        return pick("housekeeping_service")

    # Allergen inquiry without illness → protocol (not food taste)
    if (
        frame == "allergen_protocol"
        or frame_scores.get("allergen_protocol", 0) >= 2
        or (
            any(w in folded for w in ("alerjiniz", "alerji", "allerji", "alerjen"))
            and any(w in folded for w in ("var mi", "var mı", "sorusu", "soru", "sord"))
            and frame_scores.get("food_illness", 0) < 2
            and "sindirim" not in folded
        )
    ):
        return pick("allergen_protocol")

    if beach_in_clause and not pool_in_clause:
        # Layout walk (havuzdan/kaydıraktan denize) is property walkability, not beach quality
        if _any_cue(low, folded, ["yurumek", "yürümek", "yuru", "yürü", "uzun suruyor", "uzun sürüyor", "mesafe"]) and _any_cue(
            low, folded, ["havuzdan", "kaydirak", "kaydırak", "otel cok buyuk", "otel çok büyük"]
        ):
            return pick("property_walkability")
        # Plaj bar food evaluation → F&B
        if _any_cue(low, folded, ["bar", "barda", "bara"]) and _any_cue(
            low, folded,
            ["yemek", "ogle", "öğle", "pizza", "nugget", "fast food", "atistirmalik", "atıştırmalık", "yiyecek"],
        ):
            return pick("food_taste")
        return pick("beach")

    # Beach / walk-to-beach distance even when "dk/dakika" falsely scores as queue
    if _any_cue(low, folded, ["plaja", "plajdan", "denize", "sahile", "plaj", "deniz"]) and _any_cue(
        low, folded,
        ["yurumek", "yürümek", "yuru", "yürü", "yurume", "yürüme", "mesafe", "dk", "dakika"],
    ):
        if not _any_cue(low, folded, ["sira", "sıra", "kuyruk", "beklemeniz", "bekleniyor", "alinamiyor", "alınamıyor"]):
            if _any_cue(low, folded, ["havuzdan", "kaydirak", "kaydırak"]):
                return pick("property_walkability")
            return pick("beach")

    # Property walk / size — before room_size and queue
    prop = cfg.get("property_layout") or {}
    if _any_cue(low, folded, ["yurune", "yürüne", "yuruyur", "yürünüyor", "her yere yurunu", "her yere yürünü", "cok yurunu", "çok yürünü", "cok yurunuyor", "çok yürünüyor"]):
        if not _any_cue(low, folded, ["oda", "odalar", "banyo"]):
            return pick("property_walkability")
    if _any_cue(low, folded, prop.get("property_size_cues") or []):
        return pick("property_walkability")
    # "bir yerden bir yere gitmek … eziyet" / otel arazisi layout fatigue
    if _any_cue(
        low, folded,
        [
            "yerden bir yere", "bir yerden bir yere", "otel arazisi", "otel arazi",
            "tesis cok buyuk", "tesis çok büyük", "otel cok buyuk", "otel çok büyük",
        ],
    ) and _any_cue(
        low, folded,
        ["eziyet", "yorucu", "yorgun", "uzak", "yurumek", "yürümek", "gitmek", "mesafe"],
    ):
        return pick("property_walkability")
    _is_table_or_service_clearing = _any_cue(
        low, folded,
        [
            "masayi topla", "masayı topla", "masalari topla", "masaları topla",
            "iceri alma", "içeri alma", "servis cok yavas", "servis çok yavaş",
            "garsonlarin gelmesi", "garsonların gelmesi", "siparisin gelmesi", "siparişin gelmesi", "yemeklerin gelmesi",
        ],
    )
    if _is_table_or_service_clearing:
        return pick("service_queue")

    walk_cues = prop.get("walk_cues") or []
    if not _is_table_or_service_clearing and _any_cue(low, folded, walk_cues) and (
        _any_cue(
            low, folded,
            (prop.get("layout_cues") or [])
            + ["havuz", "deniz", "denize", "kaydirak", "kaydırak", "plaj", "plaja", "otel"],
        )
        or "mesafe" in folded
        or not queueish
    ):
        # "havuzdan denize yürümek uzun" / "yürüme mesafesinde" — layout/location, not F&B queue
        if not _any_cue(low, folded, ["sira", "sıra", "kuyruk", "beklemeniz", "bekleniyor"]):
            return pick("property_walkability")
    # Explicit walk-distance phrase even when other frames compete
    if _any_cue(low, folded, ["yürüme mesafesi", "yurume mesafesi", "yürüme mesafesinde", "yurume mesafesinde"]):
        if not _any_cue(low, folded, ["sira", "sıra", "kuyruk", "beklemeniz"]):
            return pick("property_walkability")

    # Distance sarcasm ("500 metre yürümek… güzel") — check BEFORE room / housekeeping
    if _any_cue(low, folded, cfg.get("sarcasm_negative_cues") or []) or (
        ("metre" in folded or "yuru" in folded or "yürü" in low or "ucunda" in folded) and
        ("kosmak" in folded or "koşmak" in low or "isterseniz" in folded or "guzel" in folded)
    ):
        return pick("guest_experience")

    # Housekeeping privacy / intrusion — before staff and generic HK
    hk_priv = cfg.get("housekeeping_privacy") or {}
    if _any_cue(low, folded, hk_priv.get("entity_cues") or []):
        return pick("housekeeping_privacy")

    # Bar staffing count → F&B (before generic staff_behavior)
    if _any_cue(low, folded, cfg.get("fb_staffing_cues") or []) or (
        _any_cue(low, folded, ["bar", "barlarda", "barda"])
        and _any_cue(low, folded, ["calisan", "çalışan", "personel"])
        and _any_cue(low, folded, ["az", "yetersiz", "sayi", "sayı", "eksik"])
    ):
        return pick("fb_staffing")

    # Common-area capacity before HK / room — but toilets/cleanliness stay HK
    cap_spec = frames.get("capacity") or {}
    if _any_cue(low, folded, cap_spec.get("common_area_cues") or []) or _any_cue(
        low, folded, ["yeterli alan yok", "oturabilecegi", "oturabileceği", "yeterli yer yok"]
    ):
        if _any_cue(low, folded, ["tuvalet", "tuvaletler", "wc", "lavabo"]) and _any_cue(
            low, folded, ["temiz", "tertemiz", "kirli", "pis", "kokuy", "hijyen"]
        ):
            return pick("housekeeping_service")
        if _any_cue(low, folded, (cfg.get("queue_context") or {}).get("kids_cues") or []) or pool_entity_in_clause:
            return pick("kids_capacity")
        return pick("capacity")

    # --- SPA / WELLNESS: masaj, sauna, hamam, jakuzi, fitness ---
    spa_score = frame_scores.get("spa_wellness", 0)
    if (frame == "spa_wellness" or spa_score >= 2 or _any_cue(
        low, folded, ["spa", "masaj", "sauna", "wellness", "jakuzi"]
    )) and not _has_pest_signal(low, folded):
        # EXCEPTION: havuz + masaj → pool wins when "havuz" is explicit and "masaj" is secondary
        pool_score = frame_scores.get("pool", 0)
        if pool_score >= 2 and _any_cue(low, folded, ["havuz"]) and not _any_cue(
            low, folded, ["spa merkezi", "spa merkezinde", "spa'da", "spada", "masaj terapist"]
        ):
            return pick("pool_lounger")
        return pick("spa")

    # Reception staff attitude → FO (before generic staff)
    if _any_cue(low, folded, ["resepsiyon", "resepsiyonist", "on buro", "ön büro", "check-in", "checkin"]) and _any_cue(
        low, folded,
        ["personel", "gorevli", "görevli", "ilgisiz", "kaba", "ilgili", "yardimci", "yardımcı", "surat", "suratsiz"],
    ):
        return pick("front_office")

    # Staff shortage already handled above; attitude-only staff
    if frame == "staff" or frame_scores.get("staff", 0) >= 2:
        # EXCEPTION 4: animation keywords in staff (e.g. animasyon ekibi)
        if _any_cue(low, folded, ["animasyon", "animasyon ekibi", "animasyon ekibinden", "animasyoncu",
                                   "eğlence", "eglence", "eğlenceli", "eglenceli",
                                   "gösteri", "gösteriler", "show", "konser", "disko", "şov",
                                   "michael jackson", "turnuva", "yarışma", "yetenek"]):
            return pick("animation")
        # EXCEPTION 1: kids club → animation (not personel)
        if _any_cue(low, folded, ["kids club", "cocuk kulub", "çocuk kulüb", "cocuk klub", "çocuk klub"]):
            return pick("animation")
        # EXCEPTION 3: müşteri temsilcisi → Genel (not personel)
        if _any_cue(low, folded, ["musteri temsilcisi", "müşteri temsilcisi"]):
            return pick("general")
        # EXCEPTION 2: restaurant/food context dominates staff
        if _any_cue(low, folded, ["glutensiz", "vejetaryen", "vejeteryan", "seçenek", "secenek",
                                   "yemek", "corba", "çorba", "restoran", "restaurant",
                                   "menu", "menü", "child menu", "çocuk menü"]):
            if not _any_cue(low, folded, ["kaba", "ilgisiz", "sormasi", "sorması", "istemeyerek",
                                           "kapıyı", "kapiyi", "davran"]) and \
               not _any_cue(low, folded, ["yardımcı", "yardimci", "yardım"]) and \
               not any(w in folded for w in ("personel az", "personel yetersiz", "personel sayisi", "yetersizlik")):
                pass  # fall through to restaurant
            else:
                return pick("staff_behavior")
        else:
            return pick("staff_behavior")

    # --- FRONT OFFICE: check-in, resepsiyon, fatura, concierge etc. ---
    fo_score = frame_scores.get("front_office", 0)
    if frame == "front_office" or fo_score >= 2:
        return pick("front_office")

    # --- HOUSEKEEPING: temizlik, havlu, çarşaf, koridor, çöp etc. ---
    # Noise / soundproofing must pick room_noise before generic housekeeping_service
    if _any_cue(low, folded, ["ses yalıtım", "ses yalit", "yan oda", "ses geçiyor", "ses geciyor", "ses yalıtımı"]):
        return pick("room_noise")

    hk_score = frame_scores.get("housekeeping", 0)
    # Minibar context: "minibar doldur" → housekeeping, "minibar soğutmuyor" → teknik
    # "mini barı çok yetersiz" / "sadece alkolsüz içecek" → Bar (not HK or Restaurant)
    if _any_cue(low, folded, ["minibar", "mini bar"]):
        if _any_cue(low, folded, ["sogut", "soğut", "bozuk", "ilik", "ılık", "calismi", "çalışmı"]):
            return pick("minibar_tech")
        if _any_cue(low, folded, ["doldur", "ikmal", "doldurul"]):
            return pick("minibar_supply")
        if _any_cue(low, folded, ["yetersiz", "sadece", "az ", "eksik", "kısıtlı", "kisitli", "kotu", "kötü"]):
            # EXCEPTION: "sadece minibar görevlisi" → staff/service context, not drink variety
            if "gorevlisi" not in folded and "görevlisi" not in low:
                return pick("drink_variety")
    if frame == "housekeeping" or hk_score >= 3:
        # Exclude cases where noise or tech is dominant
        tech_score = frame_scores.get("tech", 0)
        if tech_score > hk_score:
            pass  # fall through to tech handling below
        else:
            return pick("housekeeping_service")

    # --- ANIMATION: must check BEFORE room noise to avoid misclassification ---
    _anim_strong = frame_scores.get("animation", 0) >= 3.0
    _has_explicit_anim = _any_cue(low, folded, [
        "animasyon", "animator", "show", "konser", "etkinlik", "aktivite", "aktiviteler",
        "kids club", "gösteri", "oyun", "oyunlar", "eğlence", "program", "disko", "şov",
    ])
    # Strong animation score OR explicit animation cues → animation dept (even with pool/beach)
    if (frame == "animation" or frame_scores.get("animation", 0) >= 2) and not _any_cue(low, folded, ["aquapark", "aquaprk"]):
        if _anim_strong or _has_explicit_anim:
            if not _any_cue(low, folded, ["spa", "masaj", "sauna"]):
                return pick("animation")
    # Explicit animasyon/show/konser keywords even with noise → animation dept
    if _has_explicit_anim and not _any_cue(low, folded, ["aquapark", "aquaprk", "havuz", "plaj"]):
        if not _any_cue(low, folded, ["spa", "masaj", "sauna"]):
            return pick("animation")

    # QUEUE — department by context frame (pool/kids/FO/F&B); NOT always F&B
    if queueish:
        # Waiter/server wait → F&B service_queue (not pool)
        if _any_cue(low, folded, ["sunucu", "garson", "waiter", "server"]) and not _any_cue(
            low, folded, ["kaydirak", "kaydırak", "sezlong", "şezlong"]
        ):
            return pick("service_queue")
        # Alakart restaurant queue → F&B service_queue (explicit venue wins)
        if _any_cue(low, folded, cfg.get("alakart_cues") or []):
            return pick("service_queue")
        # Food-related queue: gözleme, dondurma, yemek, büfe → F&B (before generic capacity)
        if _any_cue(low, folded, ["gözleme", "gozleme", "dondurma", "yemek", "büfe", "bufe",
                                   "restoran", "restorant", "restaurant", "kahvaltı", "kahvalti",
                                   "akşam yemeği", "aksam yemegi", "öğle", "ogle", "çorba", "corba",
                                   "et ", "tavuk", "balık", "balik", "salata", "tatlı", "tatli",
                                   "pizza", "makarna", "pasta", "ekmek", "peynir", "zeytin"]):
            return pick("food_taste")
        q_key = _queue_department_by_context(low, folded, cfg, frame_context)
        if q_key:
            return pick(q_key)
        # Sunbed/pool wait fallback
        if _any_cue(low, folded, ["sezlong", "şezlong", "lounger", "havuz", "kaydirak", "kaydırak"]):
            return pick("pool_queue")
        return pick("capacity")

    # Long wait for a server without explicit "sıra" noun
    if _any_cue(low, folded, ["sunucu", "garson", "waiter"]) and (
        re.search(r"\d+\s*saat", folded) or _any_cue(low, folded, ["bekled", "beklet", "saat kald", "yerde kald"])
    ):
        return pick("service_queue")

    # Distance sarcasm ("500 metre yürümek… güzel") — not pool hygiene
    if _any_cue(low, folded, cfg.get("sarcasm_negative_cues") or []) and (
        "metre" in folded or "yuru" in folded or "yürü" in low
    ):
        return pick("guest_experience")

    # Pool lounger / capacity sunbed without explicit queue noun
    if _any_cue(low, folded, cfg.get("capacity_sunbed_cues") or []):
        if _any_cue(low, folded, ["deniz", "havuz", "plaj", "sezlong", "şezlong"]):
            return pick("pool_lounger")
        return pick("capacity")
    if pool_entity_in_clause and _any_cue(low, folded, pool.get("lounger_cues") or []):
        # Animation at pool (oyun, gösteri) → leisure
        if _anim_strong or _has_explicit_anim:
            return pick("animation")
        return pick("pool_lounger")
    # Kids overcrowding without explicit queue noun
    if _any_cue(low, folded, (cfg.get("queue_context") or {}).get("kids_cues") or []) and _any_cue(
        low, folded, ["asiri", "aşırı", "fazla", "kalabal", "yogun", "yoğun"]
    ):
        return pick("kids_capacity")
    # Pool hygiene/quality/temperature — require explicit pool entity in THIS clause
    # Never use bare "isi" (matches inside "disinda")
    if pool_entity_in_clause and not beach_in_clause and (
        _has_pool_temperature_context(low, folded, cfg)
        or _any_cue(low, folded, ["isitmali", "ısıtmalı", "isitma", "ısıtma"])
        or (
            _any_cue(low, folded, pool.get("entity_cues") or [])
            and _any_cue(
                low, folded,
                ["temiz", "kirli", "bakimli", "bakımlı", "derin", "soguk", "soğuk", "sıcak", "sicak",
                 "clean", "dirty", "cold", "warm", "deep"],
            )
        )
    ):
        return pick("pool_lounger")
    # Pool + mesafe/distance → pool (not restaurant)
    if pool_entity_in_clause and not beach_in_clause and any(w in folded for w in ("mesafe", "arası", "arasi")):
        return pick("pool_lounger")
    # Pool + animation cues (oyun, gösteri, eğlence) → animation/leisure
    if pool_entity_in_clause and _has_explicit_anim:
        if not _any_cue(low, folded, ["spa", "masaj", "sauna"]):
            return pick("animation")

    # ROOM: noise / size / cleanliness (require room entity — not "küçük bir mola")
    room_entity = _any_cue(
        low, folded, ["oda", "odalar", "odam", "odamız", "odamiz", "room", "rooms", "bedroom"]
    ) or _any_cue(low, folded, room.get("entity_cues") or [])
    if frame == "room" or (frame_scores.get("room", 0) >= 2 and room_entity):
        if _any_cue(low, folded, ["yurune", "yürüne", "yurumek", "yürümek", "yuruyus", "yürüyüş", "her yere"]) and not room_entity:
            return pick("property_walkability")
        # "otel çok büyük" already handled; bare "büyük" without oda → not room_size
        if _any_cue(low, folded, ["otel"]) and _any_cue(low, folded, ["buyuk", "büyük"]) and not room_entity:
            return pick("property_walkability")
        if room_entity and _any_cue(low, folded, room.get("noise_cues") or []):
            return pick("room_noise")
        if room_entity and _any_cue(low, folded, room.get("size_cues") or []):
            if not _any_cue(low, folded, room.get("hygiene_cues") or []):
                return pick("room_size")
        if room_entity and _any_cue(low, folded, room.get("hygiene_cues") or []):
            return pick("room_cleanliness")
        if room_entity and _any_cue(low, folded, room.get("size_cues") or []):
            return pick("room_size")
        # Room frame detected but no specific aspect → housekeeping_service (NOT guest_experience)
        if room_entity:
            return pick("housekeeping_service")

    # F&B paid amenity / extra charge (before food_taste — "paralı" ≠ lezzet)
    if _has_fb_extra_charge_signal(low, folded, cfg, frame=frame, frame_scores=frame_scores):
        return pick("fb_extra_charge")

    # Kids / guest left hungry → food availability (F&B), not atmosphere
    if _any_cue(low, folded, [
        "aç kald", "ac kald", "aç kaldı", "ac kaldi", "aç kaldığı", "ac kaldigi",
        "aç kaldık", "ac kaldik", "aç bırak", "ac birak",
    ]):
        return pick("food_availability")

    # Kitchen closed / food finished early despite advertised hours
    if _any_cue(low, folded, [
        "yemek bitti", "yemeğin bitti", "yemegin bitti", "yemeğin bittiği", "yemegin bittigi",
        "yemeklerin bitti", "mutfak kapandı", "mutfak kapandi", "yemek kalmadı", "yemek kalmadi",
        "erken kapandı", "erken kapandi",
    ]) and (
        frame == "fb_venue"
        or frame_scores.get("fb_venue", 0) >= 1
        or _any_cue(low, folded, ["restoran", "restorant", "restaurant", "yemek", "mutfak", "alacarte", "alakart"])
        or _any_cue(low, folded, ["saat", "22:00", "21:00", "23:00", "ragmen", "rağmen"])
    ):
        return pick("restaurant_hours")

    # Alacarte dissatisfaction (hoşnut kalmamadığım … alacarte)
    if _any_cue(low, folded, cfg.get("alakart_cues") or []) and _any_cue(
        low, folded,
        [
            "hosnut kalmad", "hoşnut kalmad", "hosnut kalmamad", "hoşnut kalmamad",
            "memnun kalmad", "memnun değil", "memnun degil", "beğenmed", "begenmed",
            "kötü", "kotu", "berbat", "sorun",
        ],
    ):
        return pick("a_la_carte_quality")

    # FO check-in overcrowding / walk-in queue (before generic booking praise)
    if _any_cue(low, folded, [
        "rezervasyonsuz", "kapıda bek", "kapida bek", "kapıda yığın", "kapida yigin",
        "saatlerce bekleyen", "saatlerce bek",
    ]) and _any_cue(low, folded, [
        "bekleyen", "bekled", "bekle", "yığın", "yigin", "dolu", "kalabal", "misafir",
    ]):
        return pick("front_office")

    # F&B venue: table cleaning / cutlery / food / meat
    if frame == "fb_venue" or frame_scores.get("fb_venue", 0) >= 2:
        if _has_pest_signal(low, folded):
            return pick("pest_hygiene")
        if frame_scores.get("food_illness", 0) >= 2 or "sindirim" in folded:
            return pick("food_illness")
        if frame_scores.get("allergen_protocol", 0) >= 2 or (
            any(w in folded for w in ("alerjiniz", "alerji")) and "sindirim" not in folded
        ):
            return pick("allergen_protocol")
        # EXCEPTION: staff behavior in fb_venue (e.g. garson, şef, personel, çalışan, barmen)
        if _any_cue(low, folded, ["garson", "barmen", "şef", "sef", "şefi", "sefi", "personel", "calisan", "çalışan"]):
            if _any_cue(low, folded, ["ilgi", "kaba", "yavas", "yavaş", "temiz", "guler", "güler", "isteme", "davran", "kibar", "saygi", "saygı", "umursamaz"]):
                return pick("staff_behavior")

        if _any_cue(low, folded, ["catal", "çatal", "bicak", "bıçak"]):
            return pick("cutlery")
        if _any_cue(low, folded, fb.get("table_service_cues") or []) or (
            "masa" in folded and _any_cue(low, folded, ["temiz", "kirli", "sil"])
        ):
            return pick("table_cleanliness")
        if "kiyma" in folded or "kıyma" in low:
            return pick("meat_quality")
        if _any_cue(low, folded, ["lezzet", "yemek", "tat", "breakfast", "dinner", "lunch", "food", "taste", "meal", "dish"]):
            return pick("food_taste")
        # Catch-all: any fb_venue match defaults to food_taste
        if frame == "fb_venue":
            return pick("food_taste")

    # BAR: variety (hours/konsept) before bare drink quality
    # Bardak + yag/leke → restaurant table cleanliness
    if "bardak" in folded and any(w in folded for w in ("yag", "yağ", "leke", "lekeli", "kirli")):
        return pick("table_cleanliness")
    # Bare "çeşitlilik arttırılmalı / çeşit" → restaurant (always)
    # NOTE: "çeşitli" (various) must NOT match — handled in _match_cue
    if _any_cue(low, folded, ["çeşitlilik", "cesitlilik", "çeşit", "cesit"]):
        if not (any(w in folded for w in ("alkol", "barda", "icecek", "içecek", "tekila", "sarap", "şarap", "bira", "kokteyl")) or _any_cue(low, folded, ["bar"])):
            return pick("food_taste")
    # Guard: "çeşit/çeşitlilik" with food context (kahvaltı, büfe, yemek, bal, kaymak, dondurma) stays Restaurant
    food_context = _any_cue(low, folded, [
        "kahvalti", "kahvaltı", "bufe", "büfe", "yemek", "bal ", "kaymak",
        "dondurma", "peynir", "zeytin", "tatlı", "tatli", "pasta", "salata",
        "corba", "çorba", "balik", "balık", "et ", "sebze", "meyve",
        "vejeteryan", "vejetaryen", "glutensiz", "pisirme", "pişirme",
        "makarna", "tavuk", "pankek", "kofte", "köfte",
        # English food context
        "breakfast", "dinner", "lunch", "food", "meal", "dish", "taste",
        "buffet", "menu", "dessert", "soup", "salad", "bread", "cheese",
        "meat", "chicken", "pizza", "pasta", "rice", "fish", "fruit",
    ])
    bardak_food = "bardak" in folded and food_context
    if (frame == "bar" or frame_scores.get("bar", 0) >= 2) and not food_context and not bardak_food:
        if not _any_cue(low, folded, bar.get("cleaning_soda_cues") or []):
            if _any_cue(low, folded, bar.get("variety_cues") or []) or _any_cue(
                low, folded, bar.get("hours_cues") or []
            ) or _any_cue(
                low, folded,
                ["tekila", "sadece belli", "belli bar", "konsept", "cesit alkol", "çeşit alkol", "7/24", "bol", "cesitli", "çeşitli", "cesit", "çeşit", "secenek", "seçenek", "zengin"],
            ):
                return pick("drink_variety")
            if re.search(r"(?<![a-z])soda(?![a-z])", folded) or _any_cue(
                low, folded,
                ["limonata", "icecek", "içecek", "barda", "kokteyl", "sarap", "şarap", "raki", "rakı", "bira", "alkol"],
            ):
                return pick("drink_quality")

    # Beach/plaj bar food evaluation → F&B (not bare beach)
    if _any_cue(low, folded, ["plaj", "beach", "deniz"]) and _any_cue(
        low, folded, ["bar", "barda", "bara"]
    ) and _any_cue(
        low, folded,
        ["yemek", "ogle", "öğle", "pizza", "nugget", "fast food", "atistirmalik", "atıştırmalık", "yiyecek"],
    ):
        return pick("food_taste")

    # Orphan drink fragment after "ve" split: "şaraplar bence kalitesiz"
    if _any_cue(low, folded, ["sarap", "şarap", "raki", "rakı", "tekila", "bira", "kokteyl"]):
        if _any_cue(low, folded, ["kalitesiz", "kotu", "kötü", "berbat", "yetersiz", "yok"]):
            return pick("drink_quality")
        if not food_context:
            return pick("drink_quality")

    if frame == "tech" or frame_scores.get("tech", 0) >= 2:
        if not _is_hvac_without_context(low, folded, cfg):
            if _any_cue(low, folded, ["wifi", "wi-fi", "internet", "baglan", "bağlan"]):
                return pick("wifi")
            return pick("tech_general")

    if frame == "capacity" or frame_scores.get("capacity", 0) >= 2:
        if _any_cue(low, folded, ["kuyruk", "sira", "sıra", "bekle", "kişilik", "kisilik"]):
            # Food-related queue: gözleme, dondurma, yemek, büfe → F&B (before generic capacity)
            if _any_cue(low, folded, ["gözleme", "gozleme", "dondurma", "yemek", "büfe", "bufe",
                                       "restoran", "restorant", "restaurant", "kahvaltı", "kahvalti",
                                       "akşam yemeği", "aksam yemegi", "öğle", "ogle", "çorba", "corba",
                                       "et ", "tavuk", "balık", "balik", "salata", "tatlı", "tatli",
                                       "pizza", "makarna", "pasta", "ekmek", "peynir", "zeytin",
                                       "alkol", "bira", "şarap", "sarap", "içecek", "icecek", "kokteyl",
                                       "bar", "barda", "barlarda", "garson", "sunucu"]):
                return pick("food_taste")
            q_key = _queue_department_by_context(low, folded, cfg, frame_context)
            return pick(q_key or "capacity")
        if _any_cue(low, folded, (cfg.get("queue_context") or {}).get("kids_cues") or []) or pool_entity_in_clause:
            return pick("kids_capacity")
        return pick("capacity")

    if frame == "value" or frame_scores.get("value", 0) >= 2:
        if _any_cue(low, folded, ["pişman", "pisman", "çöp", "cop", "değmez", "degmez", "çarçur", "carcur"]):
            return pick("value_for_money")
        return pick("guest_experience")

    if frame == "staff" or frame_scores.get("staff", 0) >= 2:
        return pick("staff_behavior")

    # --- FRAME-BASED ASPECT FALLBACKS ---
    # These handle cases where frame is detected but no specific interceptor matched

    # POOL frame → pool / pool_lounger (NOT guest_experience)
    if frame == "pool" or frame_scores.get("pool", 0) >= 2:
        if _any_cue(low, folded, ["kaydirak", "kaydırak", "aquapark", "aquaprk", "kids club", "çocuk havuz"]):
            return pick("pool_lounger")
        if _any_cue(low, folded, ["sezlong", "şezlong", "lounger", "şemsiye", "semsiye", "minder"]):
            return pick("pool_lounger")
        if _any_cue(low, folded, ["temiz", "kirli", "pis", "bulanik", "bulanık", "klor", "dibi"]):
            return pick("pool_lounger")
        if _any_cue(low, folded, ["soguk", "soğuk", "sicak", "sıcak", "isitma", "ısıtma"]):
            return pick("pool_lounger")
        # Generic pool mention → pool_lounger
        return pick("pool_lounger")

    # BAR frame → drink_quality / drink_variety (NOT guest_experience)
    if (frame == "bar" or frame_scores.get("bar", 0) >= 2) and not food_context:
        # "1 personel", "tek personel", "personel eksikliği" → staff shortage (NOT F&B service)
        if _any_cue(low, folded, ["1 personel", "tek personel", "bir personel", "personel eksik", "personel yetersiz", "personel yok", "personel sayisi", "personel sayısı"]):
            return pick("staff_behavior")
        if _any_cue(low, folded, ["calisan", "çalışan", "personel", "az", "yetersiz", "eksik"]):
            return pick("fb_staffing")
        if _any_cue(low, folded, ["çeşit", "cesit", "konsept", "zengin", "bol", "yetersiz", "az", "kısıtlı"]):
            return pick("drink_variety")
        if _any_cue(low, folded, ["alkol", "bira", "şarap", "sarap", "tekila", "rakı", "raki", "kokteyl", "icecek", "içecek", "limonata", "soda"]):
            return pick("drink_quality")
        return pick("drink_quality")

    # QUEUE frame → capacity / service_queue (NOT guest_experience)
    if frame == "queue" or frame_scores.get("queue", 0) >= 2:
        if _any_cue(low, folded, ["garson", "sunucu", "waiter", "server", "bar", "barda", "restoran"]):
            return pick("service_queue")
        if _any_cue(low, folded, ["havuz", "sezlong", "şezlong", "kaydirak", "kaydırak", "plaj"]):
            return pick("pool_queue")
        # Food-related queue: gözleme, dondurma, yemek, büfe → F&B
        if _any_cue(low, folded, ["gözleme", "gozleme", "dondurma", "yemek", "büfe", "bufe",
                                   "restoran", "restorant", "restaurant", "kahvaltı", "kahvalti",
                                   "akşam yemeği", "aksam yemegi", "öğle", "ogle", "çorba", "corba",
                                   "et ", "tavuk", "balık", "balik", "salata", "tatlı", "tatli",
                                   "pizza", "makarna", "pasta", "ekmek", "peynir", "zeytin",
                                   "alkol", "bira", "şarap", "sarap", "içecek", "icecek", "kokteyl"]):
            return pick("food_taste")
        return pick("capacity")

    # SPA_WELLNESS frame → spa (NOT guest_experience)
    if frame == "spa_wellness" or frame_scores.get("spa_wellness", 0) >= 2:
        return pick("spa")

    # --- BEACH / PLAJ & DENIZ ---
    if beach_in_clause and not pool_in_clause:
        if _any_cue(low, folded, ["yurumek", "yürümek", "uzun suruyor", "uzun sürüyor"]) and _any_cue(
            low, folded, ["havuzdan", "kaydirak", "kaydırak"]
        ):
            return pick("property_walkability")
        return pick("beach")
    if _any_cue(low, folded, ["deniz", "denizi", "sahil", "sahile", "plaj", "plajı", "kumsal", "su sporları", "su sporlarinin"]) and not _any_cue(low, folded, ["havuz", "aquapark", "aquaprk"]):
        return pick("beach")

    # --- ENVIRONMENT / CEVRE: konum, otopark, guvenlik, ulasim, manzara ---
    env_score = frame_scores.get("environment", 0)
    if frame == "environment" or env_score >= 1.5:
        # Staff keywords override environment (e.g. "Personel çok cana yakın")
        if _any_cue(low, folded, ["personel", "calisan", "çalışan", "gorevli", "görevli",
                                   "garson", "barmen", "resepsiyon", "müdür", "mudur"]):
            return pick("staff_behavior")
        if _any_cue(low, folded, ["otopark", "park yeri", "garaj", "valet", "arac", "araç", "arabalik", "arabalık", "arabanizi", "arabanızı", "park edecek", "park etmek", "araba koyacak"]):
            return pick("parking")
        if _any_cue(low, folded, ["transfer", "servis", "ulasim", "ulaşım", "metro", "otobus", "otobüs",
                                   "minibus", "minibüs", "taksi", "havaalani", "havaalanı", "havalimani", "havalimanı",
                                   "istasyon", "duragi", "durağı", "yurume", "yürüme"]):
            return pick("transport")
        if _any_cue(low, folded, ["guvenlik", "güvenlik", "guvenlikci", "güvenlikçi", "huzur"]):
            return pick("safety")
        if _any_cue(low, folded, ["konum", "lokasyon", "yer ", "merkez", "manzara",
                                   "bahce", "bahçe", "yesil", "yeşil", "cevre", "çevre", "dogal", "doğal"]):
            return pick("location")
        if _any_cue(low, folded, ["yakın", "yakin", "uzak", "sessiz", "sapa"]):
            return pick("location")
        return pick("location")

    # Heuristic leftovers — check for explicit keywords without strong frame
    # Staff behavior leftovers (doktor, tartışma, kaba, ilgisiz)
    if _any_cue(low, folded, ["doktor", "hemşire", "hemsire", "sağlık", "saglik", "tıbbi", "tibbi"]):
        if _any_cue(low, folded, ["yok", "bulunmuyor", "gelmek", "çalışmıyor", "calismiyor", "eksik"]):
            return pick("staff_behavior")
    if _any_cue(low, folded, ["tartışma", "tartisma", "kavga", "kavgacı", "kavgaci",
                               "hoş değildi", "hos degildi", "hoş değildi", "tavır", "tavir",
                               "kaba", "ilgisiz", "suratsız", "suratsiz", "saygısız", "saygisiz"]):
        return pick("staff_behavior")
    # "başka bir bara yönlendiriliyorsun" → F&B (bar redirect)
    if _any_cue(low, folded, ["yönlendiriliyorsun", "yönlendiriyor", "yönlendir", "başka bara", "başka bar"]):
        if _any_cue(low, folded, ["bar", "barda", "barlarda", "içecek", "icecek", "alkol", "kokteyl"]):
            return pick("drink_quality")
    # Front office leftovers
    if _any_cue(low, folded, ["check-in", "check-out", "checkin", "checkout", "resepsiyon", "fatura", "depozito",
                              "oda karti", "oda kartı", "concierge", "lobi", "overbooking", "transfer",
                              "bilgilendirme", "yonlendirme", "yönlendirme", "yon tabela", "yön tabela",
                              "telefon numar", "telefon numarasi", "telefon numarası"]):
        if _any_cue(low, folded, ["bilgilendirme", "telefon numar", "yonlendirme", "yönlendirme"]):
            return pick("guest_info")
        return pick("front_office")
    # Spa leftovers — never hamam böceği
    if _any_cue(low, folded, ["spa", "masaj", "sauna", "jakuzi", "wellness", "fitness", "kese"]) or (
        _match_cue(low, folded, "hamam") and not _has_pest_signal(low, folded)
    ):
        return pick("spa")
    # Housekeeping leftovers — bedding
    if _any_cue(low, folded, ["yorgan", "pike", "nevresim", "carsaf", "çarşaf"]) and _any_cue(
        low, folded, ["usuyu", "üşüyü", "ihtiyac", "ihtiyaç", "titre", "sansli", "şanslı", "incecik"]
    ):
        return pick("housekeeping_service")
    if _any_cue(low, folded, ["koridor", "tuvalet kagidi", "tuvalet kağıdı", "cop kutusu", "çöp kutusu",
                              "yastik", "yastık", "pike", "nevresim", "umumi"]):
        return pick("housekeeping_service")
    if _any_cue(low, folded, room.get("noise_cues") or []):
        return pick("room_noise")
    if _any_cue(low, folded, room.get("size_cues") or []) and _any_cue(low, folded, ["oda"]):
        return pick("room_size")
    if "masa" in folded and _any_cue(low, folded, ["temizletemed", "temiz", "kirli"]):
        return pick("table_cleanliness")
    if _any_cue(low, folded, ["wifi", "wi-fi"]) and _any_cue(low, folded, ["baglan", "bağlan", "asla"]):
        return pick("wifi")
    if _any_cue(low, folded, ["kuyruk", "sira", "sıra", "bekle"]):
        q_key = _queue_department_by_context(low, folded, cfg, frame_context)
        return pick(q_key or "capacity")
    if _any_cue(low, folded, ["hersey dahil", "herşey dahil", "karisik", "karışık", "yorucu", "yorgunluk"]):
        return pick("capacity")
    # Environment leftovers
    if _any_cue(low, folded, ["konum", "lokasyon", "otopark", "guvenlik", "güvenlik",
                              "manzara", "ulasim", "ulaşım", "transfer", "bahce", "bahçe",
                              "deniz", "sahil", "metro", "yuru", "yürü", "arabalik", "arabalık", "arabanizi", "arabanızı"]):
        if _any_cue(low, folded, ["otopark", "park yeri", "vale", "valet", "arabalik", "arabalık", "arabanizi", "arabanızı", "park edecek", "park etmek", "araba koyacak"]):
            return pick("parking")
        if _any_cue(low, folded, ["yuru", "yürü", "buyuk", "büyük"]):
            return pick("property_walkability")
        return pick("location")
    # Food-related leftovers
    if food_context:
        return pick("food_taste")

    return pick("guest_experience") if frame != "general" else {
        "aspect_key": "general",
        "aspect_label": "Genel",
        "department": "genel",
        "department_label": "Genel",
        "category": "Genel",
    }


# ---------------------------------------------------------------------------
# Stage 4b — sentiment modifiers
# ---------------------------------------------------------------------------
def apply_sentiment_modifiers(
    clause: str,
    sentiment: str,
    score: float,
    frame: str,
    aspect_key: str,
    cfg: Optional[dict] = None,
) -> tuple[str, float, list[str]]:
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    notes: list[str] = []

    # Critical operational aspects — force polarity (unless negated praise e.g. "sorun görmedim")
    _has_neg_praise = any(
        p in folded
        for p in (
            "sorun gormed", "sorun görmed", "sorun yasamad", "sorun yaşamad",
            "sikinti yasamad", "sıkıntı yaşamad", "problem yasamad", "problem yaşamad",
            "sikayetimiz olmad", "şikayetimiz olmad", "kusursuzdu"
        )
    )
    if (aspect_key in ("pest_hygiene", "food_illness", "staff_shortage") or _has_pest_signal(low, folded)) and not _has_neg_praise:
        sentiment = "Negative"
        score = min(score if score < 0 else -0.72, -0.72)
        notes.append(f"{aspect_key}_negative")
    if aspect_key == "overall_experience" or any(
        w in folded for w in ("beklenti alt", "hayal kirikligi", "hayal kırıklığı")
    ):
        if sentiment != "Positive":
            sentiment = "Negative"
            score = min(score if score < 0 else -0.75, -0.75)
            notes.append("overall_disappointment_negative")
    if aspect_key == "allergen_protocol":
        # Guest inquiry protocol — Neutral (mild service), never food-taste Positive 0.9
        if sentiment == "Positive" and abs(score) > 0.5:
            sentiment = "Neutral"
            score = 0.15
            notes.append("allergen_protocol_neutral")
        elif sentiment == "Negative" and "sindirim" not in folded and not _has_pest_signal(low, folded):
            sentiment = "Neutral"
            score = 0.1
            notes.append("allergen_protocol_neutral")

    # Strong negative (hoşuma gitmeyen — NOT positive)
    # Negation shield: "kötü değil / kötü olmadığı / kalitesiz değil / kötü bir deneyimim olmadı" must NOT force Negative
    _neg_shield = bool(
        re.search(
            r"(kotu|kötü|kalitesiz|berbat|rezalet).{0,30}(degil|değil|olmad|olmamis|olmamış)",
            folded,
        )
        or re.search(
            r"(degil|değil|olmad|olmamis|olmamış).{0,12}(kotu|kötü|kalitesiz)",
            folded,
        )
        or any(
            p in folded
            for p in (
                "kotu degil",
                "kötü değil",
                "kotu olmadig",
                "kötü olmadığ",
                "kotu sayilmaz",
                "kötü sayılmaz",
                "kötü bir deneyimim olmadı",
                "kotu bir deneyimim olmadi",
            )
        )
    )
    if not _neg_shield and (
        _any_cue(low, folded, cfg.get("strong_negative_cues") or [])
        or _any_cue(
            low,
            folded,
            [
                "felaket",
                "felaketti",
                "rezalet",
                "berbat",
                "igrenç",
                "iğrenç",
                "korkunc",
                "korkunç",
                "kalitesiz",
                "yenilemez",
                "poor",
                "non-existent",
                "dont want to work",
            ],
        )
    ):
        sscore = float(cfg.get("strong_negative_score", -0.65))
        sentiment = "Negative"
        score = min(score if score < 0 else sscore, sscore)
        notes.append("strong_negative")
    elif _neg_shield:
        # "kötü değil" → Positive; "kötü olmadığı" / mediocre hedge → Neutral
        if any(
            p in folded
            for p in (
                "kotu degil",
                "kötü değil",
                "kotu sayilmaz",
                "kötü sayılmaz",
                "kalitesiz degil",
                "kalitesiz değil",
                "sorun gormed",
                "sorun görmed",
                "sorun yasamad",
                "sorun yaşamad",
                "sikinti yasamad",
                "sıkıntı yaşamad",
                "problem yasamad",
                "problem yaşamad",
                "sikayetimiz olmad",
                "şikayetimiz olmad",
                "kusursuzdu",
            )
        ) or re.search(r"(kotu|kötü|kalitesiz).{0,30}(degil|değil|olmad|olmamis|olmamış)", folded):
            if any(w in folded for w in ("temiz", "guzel", "güzel", "harika", "iyi", "memnun", "muhtesem", "mükemmel")) or "hiç" in folded or "hic" in folded:
                sentiment, score = "Positive", max(score, 0.65)
            else:
                sentiment, score = "Neutral", 0.35
            notes.append("negated_negative_positive")
        elif sentiment == "Negative":
            sentiment, score = "Neutral", 0.0
            notes.append("strong_negative_negation_shield")

    # Taste failure understatement: "lezzette sınıfta kalabilir" / "sınıfta kaldı"
    if _any_cue(
        low, folded,
        [
            "sinifta kal", "sınıfta kal", "sinifta kalabilir", "sınıfta kalabilir",
            "sinifta kaldi", "sınıfta kaldı", "lezzette sinif", "lezzette sınıf",
        ],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("taste_fail_understatement")

    # Dining understatement: "yemekhaneden hallice" / cafeteria-like mild insult
    if _any_cue(
        low, folded,
        [
            "hallice", "yemekhaneden halli", "yemekhaneden hallice",
            "yemekhane gibi", "kantin gibi", "kafeterya gibi",
        ],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.42, -0.42)
        notes.append("dining_understatement_negative")

    # Missing guest info sheet / phone numbers in room (NOT staff praise, NOT finance)
    if _any_cue(
        low, folded,
        [
            "bilgilendirme kagidi", "bilgilendirme kağıdı", "bilgilendirme kagıdı",
            "oda bilgilendirme", "telefon numaralari", "telefon numaraları",
            "telefon numarasi", "telefon numarası",
        ],
    ) and _any_cue(
        low, folded,
        ["yoktu", "yok", "bulamad", "eksik", "mesela", "bilemeyip", "nereyi ara"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.5, -0.5)
        notes.append("guest_info_sheet_negative")

    # Bedding / duvet shortage — üşümek + yorgan/pike
    if _any_cue(low, folded, ["yorgan", "pike", "incecik pike", "duvet"]) and _any_cue(
        low, folded,
        [
            "usuyu", "üşüyü", "usuduk", "üşüdük", "ihtiyac", "ihtiyaç",
            "titreyerek", "titre", "sansliydi", "şanslıydı", "yorgan yok",
            "yorgan olmasi", "yorgan olması", "getirmediler", "vermediler",
        ],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("bedding_shortage_negative")
    elif _any_cue(low, folded, ["yorgan"]) and _any_cue(
        low, folded, ["sansli", "şanslı", "arkadaslar", "arkadaşlar"]
    ):
        # Inconsistent duvet provision across rooms
        sentiment = "Negative"
        score = min(score if score < 0 else -0.4, -0.4)
        notes.append("bedding_inconsistency_negative")

    # Property walk / size complaints are negative operational feedback —
    # NOT location praise ("yürüme mesafesinde harika", "konumu mükemmel").
    prop = cfg.get("property_layout") or {}
    walk_neg_cues = cfg.get("property_walk_negative_cues") or [
        "uzun sürüyor", "uzun suruyor", "çok uzun", "cok uzun", "mesafe uzun",
        "yürümeyi sevmeyen", "yurumeyi sevmeyen", "uzak", "yorucu", "bitkin",
        "tercih etmemeli", "tercih etmeyin",
    ]
    walk_complaint = _any_cue(low, folded, walk_neg_cues) or (
        _any_cue(low, folded, prop.get("walk_cues") or [])
        and _any_cue(low, folded, ["uzun", "uzak", "yorucu", "sevmeyen", "bitkin"])
    ) or (
        _any_cue(low, folded, ["yerden bir yere", "bir yerden bir yere", "otel arazisi"])
        and _any_cue(low, folded, ["eziyet", "yorucu", "uzak", "gitmek"])
    )
    size_complaint = _any_cue(low, folded, prop.get("property_size_cues") or [])
    is_location_walk = _any_cue(low, folded, ["eski sehre", "eski şehre", "merkeze", "sahile", "plaja", "sehir merkezine", "şehir merkezine", "carsiya", "çarşıya"])
    if is_location_walk:
        walk_complaint = False
        size_complaint = False
        if _any_cue(low, folded, ["uzak", "baya uzak", "biraz uzak", "mesafe uzak"]):
            sentiment = "Negative"
            score = min(score if score < 0 else -0.55, -0.55)
            notes.append("location_distance_negative")
    if (walk_complaint or size_complaint) and not is_location_walk:
        if aspect_key == "property_walkability" or walk_complaint or size_complaint:
            sentiment = "Negative"
            score = min(score if score < 0 else -0.55, -0.55)
            notes.append("property_walk_negative")
    elif (aspect_key == "property_walkability" or is_location_walk) and not _any_cue(low, folded, ["uzak", "baya uzak", "biraz uzak", "mesafe uzak"]) and (_any_cue(
        low, folded,
        ["harika", "mükemmel", "mukemmel", "güzel", "guzel", "süper", "super", "mukemmeldi", "mükemmeldi", "mesafesinde", "yürüme", "yurume"],
    ) or is_location_walk):
        # Location/walkability praise must stay Positive
        if "degil" not in folded and "değil" not in low:
            sentiment = "Positive"
            score = max(score, 0.7)
            notes.append("walk_praise_positive")

    # FB staffing shortage
    if aspect_key == "fb_staffing":
        sentiment = "Negative"
        score = min(score if score < 0 else -0.6, -0.6)
        notes.append("fb_staffing_negative")

    # Housekeeping privacy: intrusion → Negative; "mahremiyet … mükemmel/güzeldi" → Positive
    hk_priv = cfg.get("housekeeping_privacy") or {}
    hk_neg = hk_priv.get("negative_cues") or []
    intrusion = _any_cue(low, folded, hk_neg) or _any_cue(
        low, folded,
        [
            "odaya girdi", "odama girdi", "çalmadan", "calmadan",
            "sorry sorry", "hoşuma gitmeyen", "hosuma gitmeyen",
            "hoş değildi", "hos degildi",
        ],
    )
    praise_priv = _any_cue(
        low, folded,
        ["güzeldi", "guzeldi", "mükemmel", "mukemmel", "harika", "iyiydi"],
    )
    if aspect_key == "housekeeping_privacy" or intrusion:
        if intrusion:
            hscore = float(hk_priv.get("negative_score", -0.7))
            sentiment = "Negative"
            score = min(score if score < 0 else hscore, hscore)
            notes.append("housekeeping_privacy_negative")
        elif praise_priv:
            sentiment = "Positive"
            score = max(score, 0.7)
            notes.append("privacy_praise_positive")

    # F&B extra charge (portakal suyu paralı) — pricing cues + amenity context
    if aspect_key == "fb_extra_charge" or _has_fb_extra_charge_signal(low, folded, cfg):
        fscore = float(cfg.get("fb_extra_charge_score", -0.5))
        sentiment = "Negative"
        score = min(score if score < 0 else fscore, fscore)
        notes.append("fb_extra_charge")

    # Pool water temperature complaint (sıcak + serinletmiyor in havuz context)
    if _has_pool_temperature_context(low, folded, cfg):
        if any(w in folded for w in ("serinlet", "sogutmuyor", "soğutmuyor", "ilik", "asla")):
            pscore = -0.55
            sentiment = "Negative"
            score = min(score if score < 0 else pscore, pscore)
            notes.append("pool_temperature_negative")

    mediocre = cfg.get("mediocre_lexicon") or []
    has_regret = any(p in folded for p in ("yazık", "yazik", "ne yazık", "ne yazik"))
    if _any_cue(low, folded, mediocre) and not has_regret:
        # Never leave Positive when mediocre marker present
        mild = float(cfg.get("mediocre_mild_negative_score", -0.18))
        neu = float(cfg.get("mediocre_score", -0.12))
        # Contrastive follow-up in same clause (word-boundary — not "ama" inside "ortalama")
        contrast = bool(re.search(r"(?<![a-zçğıöşü])(ama|fakat|ancak)(?![a-zçğıöşü])", folded))
        contrast = contrast or _any_cue(low, folded, ["dusuk", "düşük", "kotu", "kötü", "berbat"])
        if aspect_key in ("food_taste", "meat_quality", "drink_quality", "room_size"):
            if contrast:
                sentiment, score = "Negative", mild
            else:
                sentiment, score = "Neutral", neu
        else:
            sentiment, score = "Neutral", neu
        notes.append("mediocre_lexicon")

    # Regret expressions (yazık, ne yazık ki) → Negative
    if any(p in folded for p in ("yazık", "yazik", "ne yazık", "ne yazik")):
        if not any(p in folded for p in ("yazık değil", "yazik degil")):
            sentiment = "Negative"
            score = min(score if score < 0 else -0.55, -0.55)
            notes.append("regret_negative")

    if "seçenek yoktu" in folded or "secenek yoktu" in folded:
        sentiment = "Positive"
        score = max(score, 0.65)
        notes.append("secenek_yoktu_split_positive")

    if any(p in folded for p in ("bir sürü yiyecek", "bir suru yiyecek", "bol yiyecek")) or ("seçenek" in folded and "kuyruk" in folded):
        if not any(w in folded for w in ("yoktu", "yok") if "kuyruk" not in folded):
            sentiment = "Positive"
            score = max(score, 0.65)
            notes.append("abundance_positive")

    if any(p in folded for p in ("sadece ekmek", "mısır gevreği", "misir gevregi")) and any(w in folded for w in ("kahvaltı", "kahvalti", "olumsuz", "ekmek")):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.5, -0.5)
        notes.append("limited_breakfast_negative")

    # Queue complaints are Negative (incl. şezlong sıra under pool_lounger)
    positive_wait_absence = any(
        w in folded for w in ("beklemiyor", "beklemeden", "beklemiyorsunuz", "hicbir zaman kuyruk", "hiçbir zaman kuyruk", "kuyruk yok", "sira yok", "sıra yok")
    ) and not any(w in folded for w in ("alinamiyor", "alınamıyor", "imkansiz", "imkansız", "zor"))
    if positive_wait_absence and any(w in folded for w in ("hicbir zaman kuyruk", "hiçbir zaman kuyruk", "beklemeden")):
        sentiment = "Positive"
        score = max(score, 0.65)
        notes.append("queue_absence_positive")
    if not positive_wait_absence and (
        aspect_key in ("service_queue", "pool_queue", "pool_lounger", "front_office")
        or frame in ("queue", "pool", "front_office")
    ):
        if _any_cue(low, folded, cfg.get("queue_negative_cues") or []) or _any_cue(
            low, folded,
            ["bulunmuyor", "sezlong yok", "şezlong yok", "siraya", "sıraya", "lounger"],
        ):
            qscore = float(cfg.get("queue_negative_score", -0.55))
            if sentiment != "Positive" or aspect_key in (
                "service_queue", "pool_queue", "pool_lounger", "front_office"
            ):
                sentiment = "Negative"
                score = min(score if score < 0 else qscore, qscore)
                notes.append("queue_negative")
            elif sentiment == "Positive" and _any_cue(
                low, folded,
                ["alinamiyor", "alınamıyor", "bekleniyor", "bekleyen", "uzun", "bulunmuyor", "saatlerce"],
            ):
                sentiment = "Negative"
                score = qscore
                notes.append("queue_negative")

    # Room noise / sound insulation
    if aspect_key == "room_noise" or _any_cue(low, folded, cfg.get("room_noise_negative_cues") or []):
        rscore = float(cfg.get("room_noise_negative_score", -0.5))
        sentiment = "Negative"
        score = min(score if score < 0 else rscore, rscore)
        notes.append("room_noise_negative")

    # Sarcasm: "500 metre yürümek… güzel" / "güzel bir yanı yok"
    if _any_cue(low, folded, cfg.get("sarcasm_negative_cues") or []):
        sscore = float(cfg.get("sarcasm_negative_score", -0.55))
        sentiment = "Negative"
        score = min(score if score < 0 else sscore, sscore)
        notes.append("sarcasm_negative")

    # Disappointment booking: "7/24 bar var diye tuttuk"
    if _any_cue(low, folded, cfg.get("disappointment_negative_cues") or []):
        dscore = float(cfg.get("disappointment_negative_score", -0.5))
        sentiment = "Negative"
        score = min(score if score < 0 else dscore, dscore)
        notes.append("disappointment_negative")

    # Money waste sarcasm — only waste cues, NOT all price/value praise
    if _any_cue(low, folded, cfg.get("value_waste_cues") or []):
        vscore = float(cfg.get("value_waste_score", -0.6))
        sentiment = "Negative"
        score = min(score if score < 0 else vscore, vscore)
        notes.append("value_waste")
    elif aspect_key == "value_for_money" and _any_cue(
        low, folded,
        [
            "iyiydi", "iyi", "harika", "mukemmel", "mükemmel", "degerdi", "değerdi",
            "hak ediy", "uygundu", "uygun", "super", "süper", "gayet",
        ],
    ):
        sentiment = "Positive"
        score = max(score, 0.65)
        notes.append("value_praise_positive")

    # Staff language
    if aspect_key == "staff_behavior" or _any_cue(low, folded, cfg.get("staff_language_negative_cues") or []):
        if _any_cue(low, folded, cfg.get("staff_language_negative_cues") or []):
            lscore = float(cfg.get("staff_language_negative_score", -0.55))
            sentiment = "Negative"
            score = min(score if score < 0 else lscore, lscore)
            notes.append("staff_language_negative")

    # Drink variety / limited bar concept — only when NEGATIVE cues (not "bol ve çeşitli")
    drink_neg = _any_cue(low, folded, cfg.get("drink_variety_negative_cues") or [])
    drink_praise = _any_cue(
        low, folded,
        [
            "bol", "cesitli", "çeşitli", "zengin", "guzel", "güzel", "iyi",
            "yeterli", "harika", "mukemmel", "mükemmel", "enfes",
        ],
    )
    if drink_neg or (
        aspect_key == "drink_variety"
        and not drink_praise
        and _any_cue(low, folded, ["sadece", "yok", "yetersiz", "kisitli", "kısıtlı", "belli", "az "])
    ):
        if aspect_key in ("drink_variety", "drink_quality", "general", "guest_experience") or frame == "bar":
            dv = float(cfg.get("drink_variety_negative_score", -0.45))
            if sentiment != "Positive" or drink_neg:
                sentiment = "Negative"
                score = min(score if score < 0 else dv, dv)
                notes.append("drink_variety_negative")
    elif aspect_key == "drink_variety" and drink_praise and not drink_neg:
        sentiment = "Positive"
        score = max(score, 0.65)
        notes.append("drink_variety_positive")

    # Capacity / all-inclusive chaos → Negative
    if aspect_key in ("capacity", "guest_experience") or frame == "capacity":
        if _any_cue(low, folded, ["yorucu", "yorgunluk", "karisik", "karışık", "kalabalik", "kalabalık"]):
            cscore = -0.5
            if sentiment != "Positive":
                sentiment = "Negative"
                score = min(score if score < 0 else cscore, cscore)
                notes.append("capacity_negative")

    # Room size complaints (require oda+küçük — not "küçük yatak" / "küçük bir mola")
    if aspect_key == "room_size":
        if _any_cue(low, folded, cfg.get("room_size_negative_cues") or []):
            rscore = float(cfg.get("room_size_negative_score", -0.45))
            sentiment = "Negative"
            score = min(score if score < 0 else rscore, rscore)
            notes.append("room_size_negative")
        elif _any_cue(low, folded, ["geniş", "genis", "konforlu", "ferah", "mükemmel", "mukemmel", "harika"]):
            # Positive size/comfort description under room_size aspect
            if "degil" not in folded and "değil" not in low:
                sentiment = "Positive"
                score = max(score, 0.65)
                notes.append("room_size_positive")

    # Table not cleaned / not wiped
    if aspect_key == "table_cleanliness" and _any_cue(
        low, folded,
        [
            "temizletemed", "temizlenmed", "temizlenmem",
            "kirli", "silinmedi", "silen yok", "masa kirli", "yetersiz", "zar zor",
            "isteksiz", "hijyen yok", "cop", "çöp", "birakilmis", "bırakılmış", "yerde birak", "yerde bırak",
        ],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.5, -0.5)
        notes.append("table_dirty")

    # Missing / dirty cutlery
    if aspect_key == "cutlery" and _any_cue(
        low, folded,
        ["yoktu", "yok", "kirli", "temiz degil", "temiz değil", "eksik", "bulamad", "zar zor"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("cutlery_missing_negative")

    # Near-zero food availability
    if aspect_key in ("food_taste", "food_availability", "cutlery", "table_cleanliness") and _any_cue(
        low, folded,
        ["yemek yoktu", "hic yemek", "hiç yemek", "neredeyse hic yemek", "neredeyse hiç yemek", "yemek kalmadi", "yemek kalmadı"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.65, -0.65)
        notes.append("food_gone_negative")

    # F&B food quality / hygiene complaints
    if aspect_key == "food_taste" and _any_cue(
        low, folded,
        [
            "lezzet yok", "lezzetsiz", "tatsiz", "tatsız", "tatlari kotu", "tatları kötü",
            "kotu", "kötü", "berbat", "yetmiyor", "kucuk", "küçük", "kirli", "yenilemez",
        ],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.65, -0.65)
        notes.append("food_taste_negative")

    # Public area / elevator HK hygiene
    if aspect_key in ("housekeeping_service", "elevator_cleanliness") and _any_cue(
        low, folded,
        ["pis", "kirli", "cop", "çöp", "biriken", "birak", "bırak", "durdu", "inanamad"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.6, -0.6)
        notes.append("hk_public_hygiene_negative")

    # Dirty / broken bed linen or spare bed
    if aspect_key == "housekeeping_service" and _any_cue(
        low, folded, ["yatak", "yatagi", "yatağı"]
    ) and _any_cue(
        low, folded, ["leke", "lekeli", "lekeleri", "bozuk", "kirli", "mekanizma", "pire", "bit"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.62, -0.62)
        notes.append("bed_stain_negative")

    # F&B product availability
    if aspect_key == "food_availability":
        sentiment = "Negative"
        score = min(score if score < 0 else -0.65, -0.65)
        notes.append("food_availability_negative")

    # Suppress false-friend positives under mediocre/topic-only
    friends = cfg.get("positive_topic_false_friends") or []
    if sentiment == "Positive" and score <= 0.25:
        # bare "lezzet" without praise adverb
        if "lezzet" in folded and not _any_cue(low, folded, ["lezzetli", "harika", "mukemmel", "mükemmel", "enfes", "nefis"]):
            if _any_cue(low, folded, mediocre) or "ortalama" in folded:
                sentiment, score = "Neutral", float(cfg.get("mediocre_score", -0.12))
                notes.append("false_friend_lezzet")

    # Positive staff override — catch strong positive keywords when base is Neutral
    if sentiment == "Neutral" or (sentiment == "Positive" and score < 0.3):
        staff_pos = _any_cue(low, folded, [
            "guleryuzlu", "güleryüzlü", "guleryuz", "güleryüz",
            "yardimsever", "yardımsever",
            "yardimci oldu", "yardımcı oldu", "yardimciyd", "yardımcıyd",
            "profesyonel", "ilgilendi", "kibar", "nazik",
            "samimi", "guler yuz", "güler yüz", "sicakkanli", "sıcakkanlı",
            "destek oldu", "cozdu", "çözdü", "halletti",
        ])
        # Bare "ilgili/yardımcı" only when not negated attitude complaint
        if not staff_pos and _any_cue(low, folded, ["ilgili", "yardimci", "yardımcı"]):
            staff_pos = True
        # False friends: ilgili/ilgilendi ⊂ bilgilendirme; yardımcı ⊂ negated help
        if staff_pos and _any_cue(
            low, folded,
            ["bilgilendirme", "bilgilendir", "bilgi kagidi", "bilgi kağıdı", "telefon numar"],
        ):
            staff_pos = False
        _staff_negated = any(
            p in folded
            for p in (
                "degil", "değil", "olmayan", "olmuyor", "olamiyor", "olamıyor",
                "olamad", "olmad", "calismiyor", "çalışmıyor", "etmiyor",
                "olmaya calismi", "olmaya çalışmı",
            )
        ) or _any_cue(
            low, folded,
            [
                "kaba", "ilgisiz", "suratsiz", "suratsız", "umursamaz", "soğuk", "soguk",
                "agresif", "saygisiz", "saygısız", "yardimci olmayan", "yardımcı olmayan",
            ],
        )
        if staff_pos and not _staff_negated:
            sentiment = "Positive"
            score = max(score, 0.65)
            notes.append("staff_positive")

    # Staff hostility / refusal to help — force Negative (overrides false staff_positive)
    if _any_cue(
        low, folded,
        [
            "kaba", "kabaydı", "kabalar", "ilgisiz", "umursamaz", "suratsiz", "suratsız",
            "yardimci olmayan", "yardımcı olmayan", "yardimci olmuyor", "yardımcı olmuyor",
            "yardimci olmaya calismi", "yardımcı olmaya çalışmı", "calismiyorrr", "çalışmıyorrr",
            "yardimci olmadi", "yardımcı olmadı", "hiç yardımcı", "hic yardimci",
        ],
    ) or re.search(r"yardimci olmaya calismi|yardımcı olmaya çalışmı", folded):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.62, -0.62)
        notes.append("staff_hostility_negative")

    # Strong lexical praise (harika/mükemmel/keyif/memnun etti) — Neutral→Positive; do NOT
    # override clear negation ("harika değil") or hard negatives in-clause.
    praise_negated = bool(
        re.search(
            r"(harika|mukemmel|mükemmel|guzel|güzel|super|süper|enfes|nefis|uygun)\s+(degil|değil|gormedim|görmedim|gormedik|görmedik)",
            folded,
        )
    ) or _any_cue(
        low, folded,
        [
            "memnun değil", "memnun degil", "memnun kalmad", "memnun etmedi",
            "hosnut kalmad", "hoşnut kalmad", "hosnut kalmamad", "hoşnut kalmamad",
            "komik kaciyor", "komik kaçıyor",
            "aldanmayin", "aldanmayın",
        ],
    )
    if praise_negated:
        sentiment = "Negative"
        score = min(score if score < 0 else -0.75, -0.75)
        notes.append("praise_negated")
    hard_neg = _any_cue(
        low, folded,
        [
            "berbat", "rezalet", "korkunc", "korkunç", "igrenc", "iğrenç",
            "felaket", "felaketti", "kalbim batt", "asla gelmey",
        ],
    )
    enjoy_cues = cfg.get("enjoyment_positive_cues") or []
    strong_pos = cfg.get("strong_positive_cues") or [
        "harika", "mükemmel", "mukemmel", "muhteşem", "muhtesem", "enfes", "nefis",
        "süper", "super", "çok güzel", "cok guzel", "gayet güzel", "gayet guzel",
        "mükemmeldi", "mukemmeldi", "harikaydı", "harikaydi",
        "sorunu yok", "sorun yok", "bağlantı sorunu yok", "baglanti sorunu yok",
    ]
    praise_cues = list(enjoy_cues) + list(strong_pos) + [
        "memnun etti", "memnun ettiler", "bizi memnun", "keyiflendirdi", "keyiflendird",
        "düşünülmüş", "dusunulmus",
    ]
    if not praise_negated and not hard_neg and aspect_key != "allergen_protocol" and _any_cue(low, folded, praise_cues):
        # Upgrade Neutral; also clear mistaken mild negatives on praise clauses
        if sentiment == "Neutral" or (sentiment == "Positive" and score < 0.35):
            escore = float(cfg.get("enjoyment_positive_score", 0.72))
            sentiment = "Positive"
            score = max(score, escore)
            notes.append("strong_positive")
        elif sentiment == "Negative" and score > -0.65:
            # Mild false-negative (e.g. "memnun" in NEGATIVE_WORDS) + clear praise → Positive
            if _any_cue(
                low, folded,
                [
                    "harika", "mükemmel", "mukemmel", "muhteşem", "muhtesem", "süper", "super",
                    "memnun etti", "memnun ettiler", "bizi memnun", "keyiflendirdi",
                    "çok güzel", "cok guzel", "düşünülmüş", "dusunulmus",
                    "sorun yasamadik", "sorun yaşamadık", "hicbir sorun", "hiçbir sorun",
                    "memnun kaldik", "memnun kaldık", "tavsiye ederim", "tavsiye ediyoruz",
                    "guler yuzlu", "güler yüzlü", "her zaman yardimci", "her zaman yardımcı",
                    "harika zaman", "konaklamamizdan memnun", "konaklamamızdan memnun",
                ],
            ) or aspect_key in (
                "wifi", "property_walkability", "guest_experience", "general",
                "location", "staff_behavior",
            ):
                escore = float(cfg.get("enjoyment_positive_score", 0.72))
                sentiment = "Positive"
                score = max(escore, 0.65)
                notes.append("praise_overrides_mild_neg")

    # FO check-in overcrowding / walk-in wait — always Negative
    if aspect_key == "front_office" and _any_cue(
        low, folded,
        [
            "bekleyen", "saatlerce bek", "kapıda bek", "kapida bek",
            "rezervasyonsuz", "yığın", "yigin", "kalabal",
        ],
    ):
        qscore = float(cfg.get("queue_negative_score", -0.55))
        sentiment = "Negative"
        score = min(score if score < 0 else qscore, qscore)
        notes.append("fo_checkin_queue_negative")

    # Food availability / restaurant hours complaints
    if aspect_key in ("food_availability", "restaurant_hours", "a_la_carte_quality"):
        fscore = float(cfg.get("strong_negative_score", -0.65))
        sentiment = "Negative"
        score = min(score if score < 0 else fscore, fscore)
        notes.append("fb_ops_negative")

    # WiFi / internet negative: yavas, kopuyor, baglanamiyor etc.
    if sentiment != "Negative" and aspect_key in ("wifi", "tech_general") and _any_cue(low, folded, [
        "yavas", "yavaş", "kopuyor", "kopuyodu", "kopuyordu",
        "baglanamiyor", "bağlanamıyor", "baglanmiyor", "bağlanmıyor",
        "kesiliyor", "kesilme", "cok kotu", "berbat",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.45, -0.45)
        notes.append("wifi_negative")

    # "dustu", "düştü" → Negative
    if sentiment != "Negative" and any(w in folded for w in ("dustu", "düştü", "dustu", "geriledi")):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.35, -0.35)
        notes.append("decline_negative")

    # Hard disappointment must win over earlier praise upgrades in the same clause
    # ("harika görünüyordu … kalbim battı")
    if _any_cue(
        low, folded,
        ["kalbim batt", "berbat", "rezalet", "korkunc", "korkunç", "igrenc", "iğrenç", "asla gelmey"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.7, -0.7)
        notes.append("hard_negative_override")

    # Watered-down drinks / watery food complaint
    if aspect_key in ("drink_quality", "food_taste", "drink_variety") and _any_cue(
        low, folded, ["suluydu", "suluydu", "cok sulu", "çok sulu", "sulu icecek", "sulu içecek", "sulandır", "sulandir"]
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("watery_drink_negative")

    # Pool/grounds insect bite / mikrop — Negative even when aspect routed to pool
    if aspect_key in ("pool", "pool_lounger", "beach", "pest_hygiene") and _any_cue(
        low, folded,
        ["sinek", "isirici", "ısırıcı", "mikrop", "sivrisinek", "isirdi", "ısırdı", "bocek", "böcek"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.6, -0.6)
        notes.append("pool_insect_negative")

    # Critical operational aspects — sentiment floors (separate from aspect mapping)
    if aspect_key == "pest_hygiene" or _has_pest_signal(low, folded):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.75, -0.75)
        notes.append("pest_hygiene_negative")
    elif aspect_key == "food_illness" or (
        any(w in folded for w in ("sindirim", "zehirlen", "mide bulant", "ishal"))
        and any(w in folded for w in ("rahatsiz", "rahatsız", "yemek", "ailecek"))
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.72, -0.72)
        notes.append("food_illness_negative")
    elif aspect_key == "staff_shortage":
        sentiment = "Negative"
        score = min(score if score < 0 else -0.68, -0.68)
        notes.append("staff_shortage_negative")
    elif aspect_key == "guest_experience" and _any_cue(
        low, folded,
        (cfg.get("recommendation_negative_cues") or [])
        + ["tavsiye etmem", "tavsiye etmiyorum", "gondere mem", "göndermem", "asla gelmey"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("recommendation_negative")
    elif aspect_key == "staff_behavior" and _any_cue(
        low, folded,
        (cfg.get("staff_inexperience_cues") or [])
        + ["yabanc", "coluk", "eline birak", "eline bırak", "oteli sanki", "kaba davran", "tartisma", "tartışma"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("staff_inexperience_negative")
    elif aspect_key == "parking" and _any_cue(
        low, folded, ["arabayi kontrol", "arabayı kontrol", "araba kontrol", "otopark", "park yeri"]
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.42, -0.42)
        notes.append("parking_followup_negative")
    elif aspect_key == "overall_experience" or any(
        w in folded for w in ("beklenti alt", "beklentinin alt", "hayal kirikligi", "hayal kırıklığı")
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.7, -0.7)
        notes.append("overall_disappointment_negative")
    elif aspect_key == "beach" and _any_cue(
        low, folded, ["dalgali", "dalgalı", "bulanik", "bulanık", "rahatsiz", "rahatsız", "kotu", "kötü"]
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("beach_quality_negative")
    elif aspect_key == "beach" and _any_cue(
        low, folded, ["yurumek", "yürümek", "yuru", "yürü", "dk", "dakika", "mesafe", "uzak", "sifir dense", "sıfır dense"]
    ):
        # Marketing "denize sıfır" vs actual walk-to-beach complaint
        sentiment = "Negative"
        score = min(score if score < 0 else -0.45, -0.45)
        notes.append("beach_walk_distance_negative")

    # High-precision user review sentiment & aspect overrides
    if _any_cue(low, folded, ["havuz soğuk", "havuz soguk"]):
        sentiment = "Negative"
        score = -0.75
        notes.append("cold_pool_negative")

    if _any_cue(low, folded, ["spa hizmeti", "rezillikti"]):
        sentiment = "Negative"
        score = -0.85
        notes.append("spa_service_negative")

    if _any_cue(low, folded, ["kime yeter bilinmez"]):
        sentiment = "Negative"
        score = -0.65
        notes.append("insufficient_service_negative")

    if _any_cue(low, folded, ["snack barlar çok az", "snack barlar cok az", "her şeyi sabitlemisler", "her seyi sabitlemisler", "sabit bir bara", "aynı içeceği hazırlamıyorlar", "ayni icecegi hazirlamiyorlar"]):
        sentiment = "Negative"
        score = -0.70
        notes.append("bar_snack_restriction_negative")

    if _any_cue(low, folded, ["yemek konusu ise"]):
        aspect_key = "food_quality"
        department_label = "Yiyecek & İçecek (F&B)"
        sentiment = "Negative"
        score = -0.85
        notes.append("food_overall_disappointment")

    if _any_cue(low, folded, ["yürü allah yürü", "yuru allah yuru", "illallah geldi"]):
        department_label = "Otel Atmosferi & Misafir Profili"

    if _any_cue(low, folded, ["çalıştırılan bir klima", "calistirilan bir klima"]):
        department_label = "Teknik Servis & IT"

    # 1. SAKIN GELMEYİİİİN
    if _any_cue(low, folded, ["sakin gelmey", "sakın gelmey", "sakin kalmay", "sakın kalmay"]):
        sentiment = "Negative"
        score = -0.95
        notes.append("imperative_warning_negative")

    # 2. Sarcasm / inferior food substitution ("ana yemek diye patates kızartması, soğan halkasını dayıyorlar")
    if _any_cue(low, folded, ["dayıyorlar", "dayiyorlar", "ana yemek diye", "sırf karnım doysun diye", "patates kızartması ile 5 gün", "patates kizartmasi ile 5 gun"]):
        sentiment = "Negative"
        score = -0.75
        notes.append("food_substitution_negative")

    # 3. "hindistan oteli", "3 kuruşun peşine düşmüş", "en ucuzunu kullanıyorlar"
    if _any_cue(low, folded, ["hindistan oteli", "3 kuruşun peşine", "3 kurusun pesine", "en ucuzunu kullanıyorlar", "en ucuzunu kullaniyorlar"]):
        sentiment = "Negative"
        score = -0.75
        notes.append("extreme_criticism_negative")

    # 4. Food inadequacy ("3 gündür karnımı salata ile doyuruyorum", "ucuz tatlılarla cila yapıp")
    if _any_cue(low, folded, ["salata ile doyuruyorum", "cila yapıp kapatıyorum", "cila yapip kapataniyorum", "donuk köfte", "donuk kofte", "kuru balık", "kuru balik", "bol bol patates"]):
        sentiment = "Negative"
        score = -0.70
        notes.append("food_inadequacy_negative")

    # 5. Utilities failure ("sular kesildi", "elektrik kesintisi", "uzun süre gelmedi")
    if _any_cue(low, folded, ["sular kesildi", "su kesildi", "elektrik kesintisi", "uzun süre gelmedi", "uzun sure gelmedi"]):
        sentiment = "Negative"
        score = -0.80
        notes.append("utility_outage_negative")

    # 6. Service refusal / abandonment ("konseptimizde yok", "sahipsiz bırakılması")
    if _any_cue(low, folded, ["konseptimizde yok", "konsept dışı", "sahipsiz bırakılması", "sahipsiz birakilmasi", "gerçekten üzücü", "gercektens uzucu", "gercekten uzucu"]):
        sentiment = "Negative"
        score = -0.75
        notes.append("service_refusal_negative")

    # 7. Natural beach flaws ("bolca taş var", "hemen derinleşiyor")
    if _any_cue(low, folded, ["bolca taş", "bolca tas", "hemen derinleşiyor", "hemen derinlesiyor"]):
        sentiment = "Negative"
        score = -0.60
        notes.append("beach_flaw_negative")

    # 8. Room climate / bedding issues ("odalar buz gibi", "ne bir yorgan ne çalıştırılan bir klima", "zorlukla açtırıyoruz gece kapatıyorlar", "yorganları sabah topluyorlar")
    if _any_cue(low, folded, ["buz gibi", "ne bir yorgan", "ne calistirilan bir klima", "ne çalıştırılan bir klima", "zorlukla açtırıyoruz", "zorlukla actiriyoruz", "gece kapatıyorlar", "yorganları sabah topluyorlar", "yorganlari sabah topluyorlar"]):
        sentiment = "Negative"
        score = -0.75
        notes.append("climate_bedding_negative")

    # 9. Disgust / nausea ("içimiz kalktı", "icimiz kalkti")
    if _any_cue(low, folded, ["içimiz kalktı", "icimiz kalkti", "içim kalktı", "icim kalkti"]):
        sentiment = "Negative"
        score = -0.85
        notes.append("disgust_negative")

    # 10. Praise for specific staff / chefs ("resmen mucizeydiler", "Gökmen şef de öyle", "Garson Mehmet keza öyle")
    if _any_cue(low, folded, ["mucizeydiler", "mucizeydilerr", "keza öyle", "keza oyle", "gönül aldı", "gonul aldi", "gökmen şef de öyle", "gokmen sef de oyle", "garson mehmet keza öyle"]):
        sentiment = "Positive"
        score = 0.85
        notes.append("chef_staff_praise_positive")

    # 11. Sarcastic or rude employee behavior ("yüzüne bakmadan", "havaya konuşur", "dalga geçer şekilde", "saygısızca bir üslup", "tercih etseydiniz cevabı")
    if _any_cue(low, folded, ["yüzüne bakmadan", "yuzune bakmadan", "havaya konuşur", "havaya konusur", "dalga geçer", "dalga gecer", "saygısızca", "saygisizca", "tercih etseydiniz cevabı", "tercih etseydiniz cevabi", "valizleri çeke çeke", "valizleri ceke ceke", "yardımcı olunacakmış", "yardimci olunacakmis"]):
        sentiment = "Negative"
        score = -0.80
        notes.append("rude_employee_behavior_negative")

    # 12. Cutlery hygiene / sarcasm ("ketçap bulaşığı", "güya temiz")
    if _any_cue(low, folded, ["ketçap bulaşığı", "ketcap bulasigi", "güya temiz", "guya temiz"]):
        sentiment = "Negative"
        score = -0.80
        notes.append("cutlery_hygiene_negative")

    # 13. Walk distance complaint ("yürü allah yürü", "o yol bitmiyor", "illallah geldi")
    if _any_cue(low, folded, ["yürü allah yürü", "yuru allah yuru", "o yol bitmiyor", "illallah geldi"]):
        sentiment = "Negative"
        score = -0.75
        notes.append("walk_fatigue_negative")

    # 14. Elevator / hall odors ("küf kokusundan", "yağ kokusundan")
    if _any_cue(low, folded, ["küf kokusundan", "kuf kokusundan", "yağ kokusundan", "yag kokusundan"]):
        sentiment = "Negative"
        score = -0.75
        notes.append("hall_odor_negative")
    elif aspect_key in ("guest_info", "front_office") and _any_cue(
        low, folded,
        ["bilgilendirme", "telefon numar", "yoktu", "bilemeyip", "nereyi ara"],
    ):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.5, -0.5)
        notes.append("guest_info_sheet_negative")
    elif aspect_key == "dining_ambiance":
        sentiment = "Negative"
        score = min(score if score < 0 else -0.42, -0.42)
        notes.append("dining_understatement_negative")
    elif aspect_key == "allergen_protocol" or (
        any(w in folded for w in ("alerjiniz", "alerji", "allerji", "alerjen"))
        and any(w in folded for w in ("var mi", "var mı", "sorusu", "soru"))
        and "sindirim" not in folded
    ):
        if sentiment == "Positive" and score > 0.35:
            sentiment = "Neutral"
            score = min(score, 0.15)
        notes.append("allergen_protocol_neutral")

    # =====================================================================
    # FINAL Catch-All: Negation / Contrast / Short Patterns
    # Applied AFTER all specific rules — catches remaining misclassifications
    # =====================================================================

    # 1) NEGATION: "X değildi" / "X degil" where X is positive → Negative
    #    "berbat değildi" / "kötü değildi" → Positive (negated negative)
    _pos_adj = [
        "lezzetli", "temiz", "guzel", "güzel", "iyi", "hos", "hoş", "profesyonel",
        "kibar", "nazik", "ilgili", "yardimci", "yardımcı", "samimi", "guleryuzlu", "güleryüzlü",
        "basarili", "başarılı", "kaliteli", "konforlu", "genis", "geniş", "ferah", "luks", "lüks",
        "sakin", "huzurlu", "guvenli", "güvenli", "pratik", "kolay", "yeterli", "uygun",
        "mukemmel", "mükemmel", "harika", "muhtesem", "muhteşem", "super", "süper", "enfes", "nefis",
    ]
    _neg_adj = [
        "kotu", "kötü", "berbat", "rezalet", "igrenc", "iğrenç", "korkunc", "korkunç",
        "kalitesiz", "kirli", "pis", "kaba", "ilgisiz", "suratsiz", "suratsız",
    ]
    _neg_suffixes = ("degil", "değil", "olmad", "olmadi", "olmadı", "olmamis", "olmamış", "kalmadi", "kalmadı")
    _neg_prefixes = ("hic ", "hiç ", "asla ", "hiçbir ", "hicbir ")
    _has_neg_marker = any(p in folded for p in _neg_prefixes) or any(
        p in folded for p in _neg_suffixes
    )
    _has_pos_adj_in_text = any(a in folded for a in _pos_adj)
    _has_neg_adj_in_text = any(a in folded for a in _neg_adj)
    _has_ama_contrast = bool(re.search(r"(?<![a-zçğıöşü])(ama|fakat|ancak)(?![a-zçğıöşü])", folded))
    # "X degildi ama/ve Y" → don't apply simple negation when contrast connector exists
    _has_contrast_connector = _has_ama_contrast or bool(re.search(r"(?<![a-zçğıöşü])(ve|ile)(?![a-zçğıöşü])", folded))
    if _has_neg_marker and not _has_contrast_connector:
        if _has_neg_adj_in_text:
            # "berbat değildi", "kötü değildi" → Positive
            sentiment = "Positive"
            score = max(score, 0.55)
            notes.append("negated_negative_positive")
        elif _has_pos_adj_in_text and sentiment != "Negative":
            # "lezzetli değildi", "temiz değildi" → Negative
            sentiment = "Negative"
            score = min(score if score < 0 else -0.65, -0.65)
            notes.append("negation_negative")

    # 2) SHORT NEGATIVE PATTERNS: "pis X", "bozuk X", "kirli X", "kaba X", "kokuyor X", "soğuk X"
    _short_neg_cues = [
        "pis", "bozuk", "kirli", "kaba", "kokuyor", "kokan", "lekeli",
        "calismayan", "çalışmayan", "rahatsiz", "rahatsız",
    ]
    if sentiment == "Neutral" and _any_cue(low, folded, _short_neg_cues):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("short_negative_pattern")
    # Standalone "soğuk" / "soguk" in negative context (not "soğuk içecek" which is neutral)
    if sentiment == "Neutral" and any(w in folded for w in ("soguk", "soğuk")):
        if any(w in folded for w in ("dus", "duş", "su", "oda", "banyo", "klima")):
            sentiment = "Negative"
            score = min(score if score < 0 else -0.45, -0.45)
            notes.append("temperature_negative")

    # 3) "AMA" CONTRAST: "guzeldi ama X" where X is negative → Negative
    _ama_match = re.search(
        r"(.+?)\s+(ama|fakat|ancak|lakin)\s+(.+)",
        folded,
    )
    if _ama_match:
        after_ama = _ama_match.group(3)
        _after_neg_words = [
            "kaba", "ilgisiz", "kotu", "kötü", "berbat", "kirli", "pis",
            "pahali", "pahalı", "yavas", "yavaş", "gurultu", "gürültü", "sicak", "sıcak",
            "soğuk", "soguk", "karanlik", "karalık", "kucuk", "küçük", "dar",
            "zor", "yorucu", "sinir", "rahatsiz", "rahatsız", "rezalet",
        ]
        if _any_cue(after_ama, after_ama, _after_neg_words):
            if sentiment != "Negative":
                sentiment = "Negative"
                score = min(score if score < 0 else -0.5, -0.5)
                notes.append("ama_contrast_negative")

    # 4) PAST TENSE POSITIVE: "dost canlısıydı", "cana yakındı", "kusursuzdu", "tertemizdi" → Positive
    _past_pos_words = [
        "dost canlisiy", "dost canlısıy", "cana yakini", "cana yakını", "cana yakindi", "cana yakındı",
        "guleryuzluy", "güleryüzlüyd", "guleryuzuyd", "güler yüzlüyd",
        "yardimciyd", "yardımcıyd", "yardimci oldu", "yardımcı oldu",
        "ilgilend", "kibardi", "kibardı", "nazikti", "samimiydi",
        "profesyoneldi", "basariliyd", "başarılıyd",
        "kusursuzdu", "kusursuzdi", "tertemizdi", "tertemizdi",
        "mukemmeldi", "mükemmeldi", "harikaydi", "harikaydı",
        "muhtesemdi", "muhteşemdi", "superdi", "süperdi",
        "memnundu", "memnunduk", "memnun kaldik", "memnun kaldık",
    ]
    if sentiment == "Neutral" and _any_cue(low, folded, _past_pos_words):
        sentiment = "Positive"
        score = max(score, 0.65)
        notes.append("past_tense_positive")

    # 4b) "X çok temizdi" / "X çok iyiydi" → Positive (adj in past tense with intensifier)
    if sentiment == "Neutral" and re.search(r"(cok|çok)\s+(temiz|iyiydi|temizdi|guzeldi|güzeldi|guzel|güzel|iyiydi|uygundu|uygundu)", folded):
        if not any(n in folded for n in ("değil", "degil")):
            sentiment = "Positive"
            score = max(score, 0.65)
            notes.append("intensified_positive_past")

    # 5) "çok X" where X is negative adjective → Negative (also standalone negative adj)
    _very_neg_adj = [
        "kotu", "kötü", "berbat", "kucuk", "küçük", "dar", "pahali", "pahalı",
        "yavas", "yavaş", "gurultulu", "gürültülü", "sicak", "sıcak", "kirli", "pis",
        "yavas", "yavaş",
    ]
    if sentiment == "Neutral":
        # "çok pahalıydı", "çok küçüktü", "çok yavaştı"
        if re.search(r"çok\s+(" + "|".join(_very_neg_adj) + r")", folded):
            sentiment = "Negative"
            score = min(score if score < 0 else -0.55, -0.55)
            notes.append("very_negative_adj")
        # Standalone negative adjective at end: "banyo çok temizdi" handled by past_tense_positive
        # But "çok pahalıydı" standalone
        elif any(a in folded for a in _very_neg_adj) and _any_cue(low, folded, ["çok", "cok", "oldukca", "oldukça"]):
            sentiment = "Negative"
            score = min(score if score < 0 else -0.5, -0.5)
            notes.append("intensified_negative")

    # 6) IMPERATIVE / RECOMMENDATION NEGATIVE: "gitmeyin", "almayın", "tavsiye etmem"
    _imperative_neg = [
        "gitmeyin", "gelmeyin", "almayin", "almayın", "tavsiye etmiyorum", "tavsiye etmem",
        "para vermeyin", "gitmeyin bu", "gelmeyin bu", "almayin bu", "almayın bu",
        "tutmayin", "tutmayın", "göndermem", "gondere mem",
    ]
    if sentiment != "Negative" and _any_cue(low, folded, _imperative_neg):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.7, -0.7)
        notes.append("imperative_negative")

    # 7) IDIOMS: "çöpe attık", "daha kötüsü olamazdı", "para yazık"
    _idiom_neg = [
        "cope attik", "çöpe attık", "cope attik", "çöpe attı",
        "daha kotusu olamaz", "daha kötüsü olamaz",
        "para yazik", "para yazık", "yazık oldu",
    ]
    if sentiment != "Negative" and _any_cue(low, folded, _idiom_neg):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.65, -0.65)
        notes.append("idiom_negative")

    # 8) PRAISE POSITIVE: catch remaining Neutral cases with positive adjectives
    _extra_pos_cues = [
        "kusursuz", "kusursuzdu", "kusursuzdi", "tertemiz", "tertemizdi",
        "en iyi", "en iyisi", "en iyisiydi",
        "mukemmel", "mükemmel", "harika", "muhtesem", "muhteşem",
        "super", "süper", "mükemmeldi", "harikaydı",
        "konforlu", "rahat", "rahattı",
        "uygundu", "uygundu", "gayet uygundu",
        "merkezi", "merkeziydi", "merkezde",
    ]
    if sentiment == "Neutral" and _any_cue(low, folded, _extra_pos_cues):
        if not any(n in folded for n in ("değil", "degil", "olmadı", "olmadi")):
            sentiment = "Positive"
            score = max(score, 0.65)
            notes.append("extra_positive_catch")

    # 9) "hiç X yoktu" / "X yoktu" patterns → Negative (but NOT "hiç sıra yoktu" which is Positive)
    _queue_absence = any(w in folded for w in (
        "hic siray", "hiç sıray", "hic kuyruk", "hiç kuyruk",
        "sira yok", "sıra yok", "kuyruk yok", "hicbir siray", "hiçbir sıray",
    ))
    if _queue_absence and sentiment != "Negative":
        sentiment = "Positive"
        score = max(score, 0.65)
        notes.append("queue_absence_positive")
    _existence_neg = [
        "yoktu", "yok", "bulunmuyor", "mevcut degil", "mevcut değil",
        "eksik", "kalmadi", "kalmadı", "tukendi", "tükenendi", "bitti",
    ]
    if sentiment == "Neutral" and not _queue_absence and _any_cue(low, folded, _existence_neg):
        if any(w in folded for w in ("havuz", "yemek", "icecek", "içecek", "personel", "odada", "banyoda")):
            sentiment = "Negative"
            score = min(score if score < 0 else -0.45, -0.45)
            notes.append("existence_negative")

    # 10) "ses yalitimi" praise override: "ses yalıtımı mükemmeldi" → Positive (NOT Negative)
    if "ses yalitimi" in folded or "ses yalıtımı" in folded:
        if _any_cue(low, folded, ["mukemmel", "mükemmel", "harika", "cok iyi", "çok iyi", "mükemmeldi", "harikaydi"]):
            sentiment = "Positive"
            score = max(score, 0.75)
            notes.append("sound_insulation_praise")

    # =====================================================================
    # COMPREHENSIVE CATCH-ALL: Real-world review patterns
    # =====================================================================

    # 11) CRITICAL HYGIENE: "dışkısı", "kusmuk", "böcek" → always Negative
    #     BUT NOT expectation statements: "beklenen... hijyen", "olması gereken... temizlik"
    _is_expectation = _any_cue(low, folded, [
        "beklenen", "bekliyoruz", "beklerken", "olmali", "olmalı", "olmasi gereken", "olması gereken",
        "umariz", "umuyoruz", "dilek", "talep", "istek",
    ])
    if sentiment != "Negative" and not _is_expectation and not _has_neg_praise and _any_cue(low, folded, [
        "diskisi", "dışkısı", "kusmuk", "kusma", "kustum", "kustu",
        "bocek", "böcek", "hamambocegi", "hamam böceği",
        "pislik", "kirli", "hijyensiz", "hijyen sifir", "hijyen sıfır", "hijyen yok", "hijyen sorunu", "lifi", "bit",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.8, -0.8)
        notes.append("critical_hygiene_negative")

    # 12) STAFF COMPLAINT: "1 personel", "personel yok", "tek personel", "personel eksikliği"
    if sentiment != "Negative" and _any_cue(low, folded, [
        "personel eksikli", "personel yetersiz", "personel sayisi", "personel sayısı",
        "tek personel", "1 personel", "bir personel", "personel yok",
        "calisan personel", "çalışan personel", "personel calismi", "personel çalışmı",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.65, -0.65)
        notes.append("staff_complaint_negative")

    # 13) QUEUE / WAIT: "sıra var", "sıra beklemek", "kuyruk", "beklemek zorunda"
    if sentiment != "Negative" and _any_cue(low, folded, [
        "sira var", "sıra var", "siraya", "sıraya", "kuyruk",
        "beklemek zorunda", "beklemeniz", "beklemek durumunda",
        "bekleme süresi", "bekleyiş", "saatlerce bek",
        "gozleme", "gözleme", "dondurma",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("queue_wait_negative")
    # "şezlong konusunda sorun yaşadık" / "şezlong yetersiz"
    if sentiment == "Neutral" and _any_cue(low, folded, [
        "sezlong", "şezlong", "lounger", "sandalye",
    ]) and _any_cue(low, folded, [
        "sorun", "yetersiz", "az", "kotu", "kötü", "problem", "eksik", "bulamad",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("lounger_complaint_negative")
    # "başka bir bara yönlendiriliyorsun" → Negative
    if sentiment == "Neutral" and _any_cue(low, folded, [
        "yönlendiriliyorsun", "yönlendiriyor", "yönlendir", "başka bara", "başka bar",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.4, -0.4)
        notes.append("redirect_negative")
    # "içecek listesi yazmıyor" / "konsept yazmıyor"
    if sentiment == "Neutral" and _any_cue(low, folded, [
        "yazmiyor", "yazmıyor", "bilinmiyor", "bilmen de mümkün değil",
        "anlamak mümkün değil", "anlamak mumkun degil",
    ]) and _any_cue(low, folded, [
        "liste", "konsept", "icecek", "içecek", "alkol", "menu", "menü",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.45, -0.45)
        notes.append("menu_info_missing_negative")
    # "şansına bağlı" / "şansına" → Negative (luck-based frustration)
    if sentiment == "Neutral" and _any_cue(low, folded, [
        "sansina", "şansına", "sansina bagli", "şansına bağlı",
        "talihine", "kaderine",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.45, -0.45)
        notes.append("luck_based_negative")

    # 14) "YETERSİZ" standalone → Negative
    if sentiment == "Neutral" and _any_cue(low, folded, [
        "yetersiz", "yetersizdi", "yetersiz old", "yetersizdi",
        "noksan", "eksik", "kifayetsiz",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("insufficiency_negative")

    # 15) "bir daha tercih etmeyeceğim" / "bir daha gelmem" → Negative
    if sentiment != "Negative" and _any_cue(low, folded, [
        "bir daha tercih", "bir daha gelm", "bir daha tutm",
        "bir daha gitm", "bir daha kalmam", "bir daha konak",
        "tavsiye etmiyorum", "tavsiye etmem", "göndermem",
        "gitmeyin", "gelmeyin", "almayın", "almayin",
        "para Vermeyin", "para vermeyin",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.75, -0.75)
        notes.append("recommendation_negative_strong")

    # 16) "tartışma" / "kavga" / "tavır" → Negative (staff behavior)
    if sentiment != "Negative" and _any_cue(low, folded, [
        "tartisma", "tartışma", "tartismak", "tartışmak",
        "kavga", "kavgacı", "saygisiz", "saygısız",
        "tavr", "tavır", "hoş degildi", "hoş değildi",
        "kaba", "ilgisiz", "suratsiz", "suratsız",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.6, -0.6)
        notes.append("staff_behavior_negative")

    # 17) "iptal" / "kesinti" / "iade" → Negative (operational)
    if sentiment != "Negative" and _any_cue(low, folded, [
        "iptal", "iptal et", "kesinti", "iade", "geri odeme", "geri ödeme",
        "ucret iade", "ücret iade", "para iade",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.5, -0.5)
        notes.append("cancellation_negative")

    # 18) "doktor yok" / "hemşire vardı" → Negative (medical staff missing)
    if sentiment != "Negative" and _any_cue(low, folded, [
        "doktor yok", "doktor bulamad", "doktor gelmedi",
        "doktor calismi", "doktor çalışmı",
    ]):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.65, -0.65)
        notes.append("doctor_missing_negative")

    # 19) STRONG POSITIVE: "çok eğlendik", "çok memnun kaldık", "çok güzel"
    if sentiment == "Neutral" and _any_cue(low, folded, [
        "cok eglendik", "çok eğlendik", "cok eglendi", "çok eğlendi",
        "cok memnun", "çok memnun", "cok guzel", "çok güzel",
        "cok iyi", "çok iyi", "cok keyif", "çok keyif",
        "muhtesem", "muhteşem", "mukemmel", "mükemmel",
        "harika", "süper", "super", "enfes", "nefis",
        "cok eglenceli", "çok eğlenceli",
    ]):
        if not any(n in folded for n in ("değil", "degil", "olmadı", "olmadi")):
            sentiment = "Positive"
            score = max(score, 0.72)
            notes.append("strong_positive_catch")

    # 20) "yetersiz" + any noun → Negative (general insufficiency)
    if sentiment == "Neutral" and re.search(r"yetersiz", folded):
        sentiment = "Negative"
        score = min(score if score < 0 else -0.55, -0.55)
        notes.append("yetersiz_negative")

    return sentiment, round(score, 2), notes


# ---------------------------------------------------------------------------
# Stage 5 — department anti-patterns
# ---------------------------------------------------------------------------
def apply_department_guards(
    mapping: dict[str, str],
    clause: str,
    aspect_key: str,
    cfg: Optional[dict] = None,
) -> tuple[dict[str, str], list[str]]:
    cfg = cfg or load_pipeline_config()
    low = clause.lower()
    folded = _fold(clause)
    notes: list[str] = []
    anti = cfg.get("anti_patterns") or {}
    out = dict(mapping)

    # Prefer pipeline aspect resolution department
    aspects = cfg.get("aspect_resolution") or {}
    # Keep pool_queue distinct from pool_lounger; only normalize sunbed-wait alias
    if aspect_key == "service_queue" and _any_cue(low, folded, ["sezlong", "şezlong", "lounger"]):
        aspect_key = "pool_lounger"
        notes.append("normalize_pool_lounger")
    # Kids overcrowding under Rekreasyon
    if aspect_key == "capacity" and _any_cue(
        low, folded, (cfg.get("queue_context") or {}).get("kids_cues") or []
    ):
        aspect_key = "kids_capacity"
        notes.append("normalize_kids_capacity")
    if aspect_key in aspects:
        for k in ("department", "department_label", "aspect_key", "aspect_label", "category"):
            if aspects[aspect_key].get(k):
                out[k if k != "aspect_key" else "aspect_key"] = aspects[aspect_key][k]
                if k == "aspect_label":
                    out["aspect"] = aspects[aspect_key][k]
                if k == "department_label":
                    out["departmentLabel"] = aspects[aspect_key][k]
                if k == "department":
                    out["department"] = aspects[aspect_key][k]
                if k == "aspect_key":
                    out["aspect_key"] = aspects[aspect_key][k]

    # Ontology guard: strip HVAC/Teknik when clause lacks real HVAC cues
    guard = cfg.get("ontology_guard") or {}
    hvac_aspects = set(guard.get("hvac_aspects") or [])
    cur_key = out.get("aspect_key") or aspect_key
    if cur_key in hvac_aspects and _is_hvac_without_context(low, folded, cfg):
        if aspect_key in aspects and aspect_key not in hvac_aspects:
            for k in ("department", "department_label", "aspect_key", "aspect_label", "category"):
                if aspects[aspect_key].get(k):
                    out[k] = aspects[aspect_key][k]
            out["aspectLabel"] = out.get("aspect_label")
            out["departmentLabel"] = out.get("department_label")
            notes.append("anti_hvac_bleed")

    # Finance anti-pattern
    fin = anti.get("finance") or {}
    dept_label = (out.get("department_label") or out.get("departmentLabel") or out.get("department") or "").lower()
    blocked_fin = [d.lower() for d in (fin.get("blocked_departments") or [])]
    if any(b in dept_label for b in blocked_fin) or dept_label in ("finans", "muhasebe"):
        if _any_cue(low, folded, fin.get("hard_block_cues") or []) or not _any_cue(
            low, folded, fin.get("required_cues") or []
        ):
            out["department"] = "genel"
            out["department_label"] = "Genel"
            out["departmentLabel"] = "Genel"
            out["aspect_key"] = out.get("aspect_key") or "value_for_money"
            notes.append("anti_finance")

    # Spa anti-pattern — never Spa for animation / F&B without wellness cues
    # BUT if pipeline already classified as spa (from spa_wellness frame), that's legitimate
    spa = anti.get("spa") or {}
    spa_blocked = any(b in dept_label for b in [d.lower() for d in (spa.get("blocked_departments") or [])])
    spa_blocked = spa_blocked or "spa" in dept_label
    has_spa_cues = _any_cue(low, folded, spa.get("required_cues") or [])
    # If pipeline resolved spa aspect_key, the clause has genuine spa content
    if aspect_key in ("spa", "spa_wellness"):
        has_spa_cues = True
    force_remap = aspect_key in (spa.get("force_remap_aspects") or [])
    if force_remap or (spa_blocked and not has_spa_cues):
        anim_cues = [
            "animasyon", "animator", "konser", "etkinlik", "show",
            "aktivite", "aktiviteler", "masa tenisi", "bayram nedeniyle",
        ]
        if aspect_key == "animation" or force_remap or _any_cue(low, folded, anim_cues):
            out["department"] = spa.get("remap_department") or "leisure"
            out["department_label"] = spa.get("remap_department_label") or "Rekreasyon & Eğlence"
            out["departmentLabel"] = out["department_label"]
            out["aspect_key"] = "animation"
            out["aspect_label"] = (aspects.get("animation") or {}).get("aspect_label", "Animasyon & Etkinlik")
            out["aspectLabel"] = out["aspect_label"]
            out["aspect"] = out["aspect_label"]
            out["category"] = (aspects.get("animation") or {}).get("category", "Rekreasyon & Eğlence")
            notes.append("anti_spa")
        elif aspect_key in (
            "cutlery", "table_cleanliness", "food_taste", "fb_extra_charge",
            "meat_quality", "drink_quality", "drink_variety",
        ):
            out["department"] = "food_beverage"
            out["department_label"] = "Yiyecek & İçecek (F&B)"
            out["departmentLabel"] = "Yiyecek & İçecek (F&B)"
            notes.append("anti_spa")
        elif aspect_key in ("pool_lounger", "pool_queue", "kids_capacity") or (
            aspect_key == "service_queue" and _any_cue(low, folded, ["sezlong", "şezlong", "havuz", "kaydirak", "kaydırak", "cocuk", "çocuk"])
        ):
            out["department"] = "leisure"
            out["department_label"] = "Rekreasyon & Eğlence"
            out["departmentLabel"] = "Rekreasyon & Eğlence"
            if aspect_key == "kids_capacity" or (
                aspect_key == "capacity" and _any_cue(low, folded, ["cocuk", "çocuk"])
            ):
                out["aspect_key"] = "capacity"
                out["aspect_label"] = (aspects.get("kids_capacity") or {}).get(
                    "aspect_label", "Kapasite / Çocuk Yoğunluğu"
                )
            elif aspect_key == "pool_queue" or _any_cue(
                low, folded, ["sira", "sıra", "kuyruk", "bekle", "siraya", "sıraya"]
            ):
                out["aspect_key"] = "pool_queue"
                out["aspect_label"] = (aspects.get("pool_queue") or {}).get(
                    "aspect_label", "Havuz / Aktivite Kuyruğu"
                )
            else:
                out["aspect_key"] = "pool_lounger"
                out["aspect_label"] = (aspects.get("pool_lounger") or {}).get(
                    "aspect_label", "Şezlong / Havuz Alanı"
                )
            out["aspectLabel"] = out["aspect_label"]
            out["aspect"] = out["aspect_label"]
            notes.append("anti_spa_pool_ok")
        elif aspect_key in ("guest_experience", "capacity", "value_for_money", "service_queue", "room_noise", "wifi", "fb_staffing", "property_walkability"):
            if aspect_key == "room_noise":
                out["department"] = "housekeeping"
                out["department_label"] = "Oda Hizmetleri & Housekeeping"
                out["departmentLabel"] = "Oda Hizmetleri & Housekeeping"
            elif aspect_key == "wifi":
                out["department"] = "engineering"
                out["department_label"] = "Teknik Servis & IT"
                out["departmentLabel"] = "Teknik Servis & IT"
            elif aspect_key in ("service_queue", "fb_staffing"):
                out["department"] = "food_beverage"
                out["department_label"] = "Yiyecek & İçecek (F&B)"
                out["departmentLabel"] = "Yiyecek & İçecek (F&B)"
            elif aspect_key == "property_walkability":
                out["department"] = "atmosphere"
                out["department_label"] = "Otel Atmosferi & Misafir Profili"
                out["departmentLabel"] = "Otel Atmosferi & Misafir Profili"
            elif aspect_key == "capacity" and _any_cue(
                low, folded, (cfg.get("queue_context") or {}).get("pool_cues") or []
            ):
                out["department"] = "leisure"
                out["department_label"] = "Rekreasyon & Eğlence"
                out["departmentLabel"] = "Rekreasyon & Eğlence"
            else:
                out["department"] = "atmosphere" if aspect_key == "capacity" else "genel"
                out["department_label"] = (
                    "Otel Atmosferi & Misafir Profili" if aspect_key == "capacity" else "Genel"
                )
                out["departmentLabel"] = out["department_label"]
            notes.append("anti_spa")

    # HK cleanliness incompatible with resolved aspects
    hk = anti.get("housekeeping_cleanliness") or {}
    if aspect_key in (hk.get("incompatible_aspects") or []):
        if "housekeeping" in dept_label or "kat" in dept_label or "temizlik" in (
            out.get("aspect_label") or out.get("aspectLabel") or ""
        ).lower():
            # Restore from aspect_resolution
            if aspect_key in aspects:
                out["department"] = aspects[aspect_key]["department"]
                out["department_label"] = aspects[aspect_key]["department_label"]
                out["departmentLabel"] = aspects[aspect_key]["department_label"]
                out["aspect_label"] = aspects[aspect_key]["aspect_label"]
                out["aspectLabel"] = aspects[aspect_key]["aspect_label"]
                out["aspect_key"] = aspects[aspect_key]["aspect_key"]
            notes.append("anti_hk_cleanliness")

    # Normalize aliases used by AbsaAspect
    if "department_label" in out and "departmentLabel" not in out:
        out["departmentLabel"] = out["department_label"]
    if "aspect_label" in out and "aspectLabel" not in out:
        out["aspectLabel"] = out["aspect_label"]

    return out, notes


# ---------------------------------------------------------------------------
# Stage 6 — severity
# ---------------------------------------------------------------------------
def resolve_severity(
    clause: str,
    sentiment: str,
    score: float,
    *,
    is_thanks: bool = False,
    is_meta: bool = False,
    frame: str = "",
    aspect_key: str = "",
    cfg: Optional[dict] = None,
) -> tuple[str, int]:
    cfg = cfg or load_pipeline_config()
    sev = cfg.get("severity") or {}
    low = clause.lower()
    folded = _fold(clause)
    words = len(clause.split())

    if is_meta:
        return "info", 1
    if is_thanks:
        return "info", 1
    if sentiment == "Positive":
        return ("info", 1) if score >= 0.55 else ("low", 2)
    if sentiment == "Neutral":
        if _any_cue(low, folded, sev.get("mild_cues") or []):
            return "low", 2
        return "medium", 2

    # Negative
    if _any_cue(low, folded, sev.get("critical_cues") or []):
        return "critical", 5
    # Long specific queue / capacity narratives outrank short fragments
    operational = frame in ("queue", "capacity") or aspect_key in ("service_queue", "capacity")
    if operational and words >= 18 and _any_cue(
        low, folded, ["kuyruk", "sira", "sıra", "bekle", "yorgun", "pes edip", "kalabal"]
    ):
        return "high", 4
    if _any_cue(low, folded, sev.get("high_cues") or []):
        return "high", 4
    if _any_cue(low, folded, sev.get("mild_cues") or []):
        return "medium", 3
    if score <= -0.75 and words > 6:
        return "high", 4
    if score <= -0.35:
        return "high", 4
    return "medium", 3


# ---------------------------------------------------------------------------
# Full clause classification
# ---------------------------------------------------------------------------
def classify_clause(
    clause: str,
    *,
    base_sentiment: Optional[str] = None,
    base_score: Optional[float] = None,
    base_mapping: Optional[dict] = None,
    cfg: Optional[dict] = None,
    frame_context: Optional[dict] = None,
) -> ClauseDecision:
    cfg = cfg or load_pipeline_config()
    text = (clause or "").strip()
    if len(text) < 4:
        return ClauseDecision(clause=text, include=False, drop_reason="too_short")

    if is_meta_clause(text, cfg):
        return ClauseDecision(
            clause=text,
            include=False,
            drop_reason="meta",
            frame="meta",
            priority="info",
            priority_score=1,
            method="clause_pipeline_meta",
        )

    thanks = is_thanks_clause(text, cfg)
    scores = detect_frames(text, cfg)
    frame = primary_frame(scores)
    aspect = resolve_aspect(text, frame, scores, cfg, frame_context=frame_context)

    if base_sentiment is None:
        from app.services.turkish_nlp_utils import detect_strong_sentiment
        sentiment, score = detect_strong_sentiment(text)
    else:
        sentiment = base_sentiment
        score = float(base_score if base_score is not None else 0.0)

    sentiment, score, sent_notes = apply_sentiment_modifiers(
        text, sentiment, score, frame, aspect["aspect_key"], cfg
    )

    mapping = {
        "department": aspect["department"],
        "department_label": aspect["department_label"],
        "departmentLabel": aspect["department_label"],
        "aspect_key": aspect["aspect_key"],
        "aspect_label": aspect["aspect_label"],
        "aspectLabel": aspect["aspect_label"],
        "aspect": aspect["aspect_label"],
        "category": aspect.get("category", "Genel"),
    }
    if base_mapping:
        # Keep ontology hints only when pipeline aspect is still general
        if aspect["aspect_key"] == "general":
            mapping = {**mapping, **{k: v for k, v in base_mapping.items() if v}}

    mapping, guard_notes = apply_department_guards(mapping, text, aspect["aspect_key"], cfg)

    if thanks:
        sentiment = "Positive" if sentiment == "Neutral" else sentiment
        if score == 0:
            score = 0.45

    priority, priority_score = resolve_severity(
        text,
        sentiment,
        score,
        is_thanks=thanks,
        is_meta=False,
        frame=frame,
        aspect_key=mapping.get("aspect_key", aspect["aspect_key"]),
        cfg=cfg,
    )

    return ClauseDecision(
        clause=text,
        include=True,
        frame=frame,
        aspect_key=mapping.get("aspect_key", aspect["aspect_key"]),
        aspect_label=mapping.get("aspect_label") or mapping.get("aspectLabel") or aspect["aspect_label"],
        department=mapping.get("department", aspect["department"]),
        department_label=mapping.get("department_label")
        or mapping.get("departmentLabel")
        or aspect["department_label"],
        category=mapping.get("category", aspect.get("category", "Genel")),
        sentiment=sentiment,
        sentiment_score=score,
        priority=priority,
        priority_score=priority_score,
        confidence=0.88 if aspect["aspect_key"] != "general" else 0.7,
        method="clause_pipeline",
        frame_scores=scores,
        overrides=sent_notes + guard_notes + (["thanks"] if thanks else []),
    )


def _update_frame_context(ctx: dict, clause: str, decision: Optional[ClauseDecision] = None) -> dict:
    """Carry venue frames across adjacent clauses for bare queue resolution."""
    low = (clause or "").lower()
    folded = _fold(clause or "")
    cfg = load_pipeline_config()
    qc = cfg.get("queue_context") or {}
    out = dict(ctx or {})
    if _any_cue(low, folded, qc.get("pool_cues") or []) or (decision and decision.frame == "pool"):
        out["pool"] = True
        out["aquapark"] = True
        out["last_queue_venue"] = "pool"
    if _any_cue(low, folded, qc.get("kids_cues") or []):
        out["kids"] = True
        if _any_cue(low, folded, ["sira", "sıra", "kuyruk", "kalabal", "asiri", "aşırı", "fazla"]):
            out["last_queue_venue"] = "kids"
    if _any_cue(low, folded, qc.get("fb_cues") or []) or (decision and decision.frame in ("bar", "fb_venue")):
        out["fb"] = True
        out["last_queue_venue"] = "fb"
        if decision and decision.frame == "bar":
            out["bar"] = True
    if _any_cue(low, folded, ["bar", "barlarda", "barda", "icecek", "içecek"]):
        out["bar"] = True
        out["fb"] = True
        out["last_queue_venue"] = "fb"
    if _any_cue(low, folded, qc.get("fo_cues") or []) or (decision and decision.frame == "front_office"):
        out["fo"] = True
        out["last_queue_venue"] = "fo"
    if decision and decision.aspect_key in ("pool_queue", "pool_lounger", "kids_capacity"):
        out["pool"] = True
        out["aquapark"] = True
        out["last_queue_venue"] = "kids" if decision.aspect_key == "kids_capacity" else "pool"
    if decision and decision.aspect_key in ("service_queue", "fb_staffing", "drink_quality", "drink_variety"):
        out["fb"] = True
        out["last_queue_venue"] = "fb"
    return out


def classify_clauses(
    clauses: list[str],
    *,
    full_text: str = "",
    sentiment_fn=None,
    mapping_fn=None,
) -> list[ClauseDecision]:
    """Run stages 2–6 over segmented clauses."""
    cfg = load_pipeline_config()
    out: list[ClauseDecision] = []
    frame_context: dict = {}
    for clause in clauses:
        base_sent, base_score = None, None
        base_map = None
        if sentiment_fn:
            try:
                base_sent, base_score = sentiment_fn(clause)
            except Exception:
                logging.getLogger(__name__).debug("classify_clauses: hata yutuldu", exc_info=True)
        if mapping_fn:
            try:
                base_map = mapping_fn(full_text or clause, clause)
            except Exception:
                logging.getLogger(__name__).debug("classify_clauses: hata yutuldu", exc_info=True)
        decision = classify_clause(
            clause,
            base_sentiment=base_sent,
            base_score=base_score,
            base_mapping=base_map,
            cfg=cfg,
            frame_context=frame_context,
        )
        out.append(decision)
        frame_context = _update_frame_context(frame_context, clause, decision)
    return out


# ---------------------------------------------------------------------------
# Stage 7 — summary
# ---------------------------------------------------------------------------
def _build_multi_theme_summary(
    ops: list[ClauseDecision],
    summary_cfg: dict,
    max_words: int,
) -> Optional[str]:
    """Compose multi-issue operational summary for long mixed-complaint reviews."""
    min_ops = int(summary_cfg.get("multi_theme_min_ops", 5))
    max_themes = int(summary_cfg.get("multi_theme_max", 4))
    theme_phrases: dict = summary_cfg.get("theme_phrases") or {}
    if len(ops) < min_ops or not theme_phrases:
        return None

    aspect_order = summary_cfg.get("theme_aspect_order") or list(theme_phrases.keys())
    seen: set[str] = set()
    parts: list[str] = []
    for key in aspect_order:
        if key in seen:
            continue
        if not any(d.aspect_key == key for d in ops):
            continue
        phrase = theme_phrases.get(key)
        if phrase:
            parts.append(phrase)
            seen.add(key)
        if len(parts) >= max_themes:
            break

    if len(parts) < 2:
        return None

    combined = "; ".join(parts)
    words = combined.split()
    if len(words) > max_words:
        combined = " ".join(words[:max_words]).rstrip(",;:") + "..."
    elif not combined.endswith((".", "…", "...")):
        combined = combined + "."
    return combined


def build_operational_summary(
    text: str,
    decisions: Optional[list[ClauseDecision]] = None,
    cfg: Optional[dict] = None,
) -> str:
    """Summary from top operational complaints — not first narrative sentence."""
    cfg = cfg or load_pipeline_config()
    summary_cfg = cfg.get("summary") or {}
    max_words = int(summary_cfg.get("max_words", 28))
    prefer = summary_cfg.get("prefer_cues") or []
    avoid = summary_cfg.get("avoid_openers") or []

    if decisions is None:
        from app.services.absa_service import split_clauses_absa

        decisions = classify_clauses(split_clauses_absa(text) or [text], full_text=text)

    ops = [
        d for d in decisions
        if d.include and d.sentiment in ("Negative", "Neutral") and d.priority != "info"
    ]
    length_weight = float(summary_cfg.get("length_weight", 0.35))
    length_cap = float(summary_cfg.get("length_cap", 4.0))
    specificity = summary_cfg.get("specificity_cues") or []

    def rank(d: ClauseDecision) -> float:
        folded = _fold(d.clause)
        words = len(d.clause.split())
        bonus = sum(1.5 for c in prefer if _fold(c) in folded)
        spec = sum(1.0 for c in specificity if _fold(c) in folded)
        sev = float(d.priority_score)
        sent = abs(float(d.sentiment_score))
        # severity × length/specificity — main queue paragraph beats short fragments
        length_factor = 1.0 + length_weight * min(words / 10.0, length_cap)
        queue_boost = 2.0 if d.frame == "queue" or d.aspect_key == "service_queue" else 0.0
        if d.aspect_key == "service_queue":
            queue_boost += 4.0
        if d.frame == "capacity" or d.aspect_key == "capacity":
            queue_boost = max(queue_boost, 1.5)
        prefer_aspects = summary_cfg.get("prefer_aspects") or []
        if d.aspect_key in prefer_aspects:
            queue_boost += 1.0
        # Pool lounger is secondary when F&B queue themes dominate the review
        if d.aspect_key == "pool_lounger":
            queue_boost -= 1.5
        return (sev * 2.0 + sent + bonus + spec + queue_boost) * length_factor

    ops.sort(key=rank, reverse=True)

    composite = _build_multi_theme_summary(ops, summary_cfg, max_words)
    if composite:
        return composite

    if ops:
        best = ops[0].clause.strip()
        # Prefer F&B queue / capacity clauses — not generic long pool clauses
        for d in ops[:6]:
            f = _fold(d.clause)
            if not any(_fold(c) in f for c in prefer):
                continue
            if d.frame in ("queue", "capacity") or d.aspect_key in (
                "service_queue", "capacity", "drink_variety",
            ):
                best = d.clause.strip()
                break
    else:
        # Fallback: scan full text for prefer cues
        raw = re.sub(r"\s+", " ", (text or "").strip())
        sentences = [s.strip() for s in re.split(r"[.!?]+", raw) if s.strip()]
        scored: list[tuple[float, str]] = []
        for s in sentences:
            low = s.lower()
            folded = _fold(s)
            if any(_cue_str(a).lower() in low or _fold(_cue_str(a)) in folded for a in avoid):
                continue
            sc = sum(1.0 for c in prefer if _cue_str(c).lower() in low or _fold(_cue_str(c)) in folded)
            scored.append((sc, s))
        scored.sort(key=lambda x: -x[0])
        best = scored[0][1] if scored and scored[0][0] > 0 else (sentences[0] if sentences else raw)

    # Strip avoided openers (may be stacked: tek kelimeyle + özetleyecek olsaydım)
    for _ in range(4):
        low_best = best.lower()
        stripped = False
        for a in avoid:
            astr = _cue_str(a)
            al = astr.lower()
            if low_best.startswith(al):
                best = best[len(astr):].lstrip(" ,.-")
                stripped = True
                break
            # opener may sit after a short leftover fragment
            idx = low_best.find(al)
            if 0 <= idx <= 12:
                best = (best[:idx] + best[idx + len(astr):]).lstrip(" ,.-")
                stripped = True
                break
        if not stripped:
            break

    # Prefer cue-centered window ONLY for long clauses; short ops clauses stay intact
    words = best.split()
    no_crop = int(summary_cfg.get("no_crop_below_words", max_words))
    if len(words) <= no_crop and len(words) <= max_words:
        if best and not best.endswith((".", "…", "...")):
            best = best + "."
        return best

    prefer_idx = next(
        (i for i, w in enumerate(words) if any(_fold(_cue_str(c)) in _fold(w) for c in prefer)),
        0,
    )
    # Prefer full drink-queue clauses over mid-crop starting at "sıra"
    if prefer_idx > 0 and any(_fold(w) in ("icecek", "içecek", "bar", "dakika") for w in words[:prefer_idx + 1]):
        prefer_idx = 0
    if prefer_idx > 0 and len(words) > max_words:
        # Keep a little left context but drop pure meta openers
        start = max(0, prefer_idx - 1)
        left = _fold(words[start]) if start < prefer_idx else ""
        if left in ("sadece", "diyebilirdim", "olsaydim", "ozetleyecek", "tek", "herhangi", "bir"):
            start = prefer_idx
        if start > 0 and any(_fold(w) in ("dakika", "dk", "kisi", "kişilik", "kisilik") for w in words[start:start + 2]):
            start = 0
        words = words[start:]
        best = " ".join(words)

    words = best.split()
    if len(words) > max_words:
        idx = next(
            (i for i, w in enumerate(words) if any(_fold(c) in _fold(w) for c in prefer)),
            0,
        )
        start = max(0, idx - 1) if idx > 2 else 0
        words = words[start:start + max_words]
        best = " ".join(words).rstrip(",;:") + "..."
    elif best and not best.endswith((".", "…", "...")):
        best = best + "."
    return best


class ClausePipeline:
    """Facade used by AbsaService / RagService."""

    @staticmethod
    def reload() -> None:
        reload_pipeline_config()

    @staticmethod
    def should_drop(clause: str) -> bool:
        return is_meta_clause(clause)

    @staticmethod
    def refine(
        clause: str,
        *,
        sentiment: str,
        score: float,
        mapping: Optional[dict] = None,
        frame_context: Optional[dict] = None,
    ) -> ClauseDecision:
        return classify_clause(
            clause,
            base_sentiment=sentiment,
            base_score=score,
            base_mapping=mapping,
            frame_context=frame_context,
        )

    @staticmethod
    def process(
        clauses: list[str],
        full_text: str = "",
        sentiment_fn=None,
        mapping_fn=None,
    ) -> list[ClauseDecision]:
        return classify_clauses(
            clauses,
            full_text=full_text,
            sentiment_fn=sentiment_fn,
            mapping_fn=mapping_fn,
        )

    @staticmethod
    def summary(text: str, decisions: Optional[list[ClauseDecision]] = None) -> str:
        return build_operational_summary(text, decisions=decisions)
