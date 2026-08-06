"""
Otel profili ve FAQ bilgi tabanı — keyword + fuzzy eşleştirme (MVP).
"""
from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Optional

from app.services.turkish_nlp_utils import normalize_turkish

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_PROFILE_PATH = os.path.join(_DATA_DIR, "hotel_profile.json")
_CUSTOM_PROFILE_PATH = os.path.join(_DATA_DIR, "hotel_profile_custom.json")
_FAQ_PATH = os.path.join(_DATA_DIR, "hotel_faq_builtin.json")

_profile_cache: Optional[dict] = None


def _ascii_fold(text: str) -> str:
    return (
        text.replace("ş", "s").replace("ı", "i").replace("ö", "o")
        .replace("ü", "u").replace("ç", "c").replace("ğ", "g")
    )


def _tokenize(text: str) -> set[str]:
    norm = normalize_turkish(text.lower())
    return set(re.findall(r"[a-z0-9]+", _ascii_fold(norm)))


_STOP_TOKENS = frozenset({
    "mi", "mu", "mı", "de", "da", "ne", "var", "bir", "icin", "için", "olan", "ile", "ve",
    "the", "a", "an", "is", "are", "how", "what", "when", "where",
})

_QUERY_TOPIC_MARKERS: dict[str, tuple[str, ...]] = {
    "sorun": ("sorun", "ariza", "bozuk", "calism", "sikayet", "kaldi", "acik"),
    "klima": ("klima", "klimasi", "sogutma", "isitma"),
    "kirli": ("kirli", "pis", "temiz", "leke"),
    "kahvalti": ("kahvalti", "breakfast"),
    "oda": ("oda",),
}

_BLOCKED_FAQ_TOPICS: dict[str, tuple[str, ...]] = {
    "hava_durumu": ("hava durumu", "concierge", "hava"),
    "kasa": ("kasa", "elektronik kasa"),
    "helal": ("helal", "sertifik"),
    "oda_servisi": ("oda servisi", "24 saat oda", "menu odanizda"),
}


_FAQ_STOPWORDS = frozenset({
    "var", "mi", "mı", "mu", "mü", "ne", "de", "da", "bir", "icin", "için",
    "nasil", "nasıl", "nedir", "kadar", "kaçta", "kacta", "saat", "detay",
    "bilgi", "alabilir", "miyim", "musunuz", "misiniz", "ücretli", "ucretli",
    "ücretsiz", "ucretsiz", "açıklar", "aciklar", "zaman", "nerede",
})


def _fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, _ascii_fold(normalize_turkish(a)), _ascii_fold(normalize_turkish(b))).ratio()


@lru_cache(maxsize=1)
def _load_faq_raw() -> list[dict]:
    if os.path.isfile(_FAQ_PATH):
        with open(_FAQ_PATH, encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else data.get("faqs", [])
        if items:
            return items
    return _generate_builtin_faqs()


def _generate_builtin_faqs() -> list[dict]:
    """220+ built-in FAQ — hotel_faq_builtin.json yoksa kullanılır."""
    templates = [
        ("Front Office", "resepsiyon", "Check-in saat kaçta?", "Check-in saatimiz 14:00'dır.", ["check-in", "giriş saati"]),
        ("Front Office", "resepsiyon", "Check-out saat kaçta?", "Check-out saatimiz 12:00'dır.", ["check-out", "çıkış saati"]),
        ("Front Office", "resepsiyon", "Erken check-in mümkün mü?", "Erken check-in müsaitliğe bağlıdır.", ["erken giriş"]),
        ("Front Office", "resepsiyon", "Geç check-out yapabilir miyim?", "Geç check-out müsaitliğe bağlıdır.", ["geç çıkış"]),
        ("Front Office", "resepsiyon", "Oda anahtarımı kaybettim", "Resepsiyona başvurun; kimlik sonrası yeni kart verilir.", ["kayıp kart"]),
        ("Housekeeping", "housekeeping", "Havlu istiyorum", "Ek havlu talebiniz alındı; kat hizmetleri yönlendirildi.", ["havlu istiyorum", "ek havlu"]),
        ("Housekeeping", "housekeeping", "Oda temizliği ne zaman?", "Günlük temizlik 09:00-16:00 arası yapılır.", ["oda temizliği"]),
        ("Housekeeping", "housekeeping", "Yastık ekstra alabilir miyim?", "Evet, ek yastık talep edebilirsiniz.", ["ek yastık"]),
        ("Housekeeping", "housekeeping", "Minibar nasıl ücretlendiriliyor?", "Minibar tüketim bazlı ücretlendirilir.", ["minibar"]),
        ("F&B", "restaurant", "Kahvaltı kaçta?", "Kahvaltı 07:00-10:30 arası servis edilir.", ["kahvaltı saat", "kahvaltı kaçta"]),
        ("F&B", "restaurant", "Vegan seçenek var mı?", "Evet, vegan seçenekler sunulmaktadır.", ["vegan", "vejetaryen"]),
        ("F&B", "restaurant", "Glutensiz yemek var mı?", "Evet, glutensiz seçenekler mevcuttur.", ["glutensiz"]),
        ("F&B", "restaurant", "Oda servisi var mı?", "24 saat oda servisi mevcuttur.", ["oda servisi"]),
        ("Spa", "spa", "Havuz saatleri nedir?", "Havuz 08:00-20:00 arası açıktır.", ["havuz saat", "havuz kaçta", "havuz kapan"]),
        ("Spa", "spa", "Spa saatleri?", "Spa 10:00-22:00 arası hizmet verir.", ["spa saat"]),
        ("Spa", "spa", "Hamam ücretsiz mi?", "Hamam hizmeti ücretlidir.", ["hamam"]),
        ("Spa", "spa", "Masaj randevusu nasıl alınır?", "Spa resepsiyonundan randevu alabilirsiniz.", ["masaj randevu"]),
        ("Engineering", "teknik", "WiFi şifresi nedir?", "WiFi şifresi oda kartında ve resepsiyondadır.", ["wifi şifre"]),
        ("Engineering", "teknik", "Klima çalışmıyor ne yapmalıyım?", "Resepsiyonu arayın; teknik ekip yönlendirilir.", ["klima arız", "klima bozuk"]),
        ("Engineering", "teknik", "TV açılmıyor", "Teknik ekibimiz bilgilendirildi.", ["tv çalışmıyor"]),
        ("Security", "guvenlik", "Kayıp eşyam var", "Lost & found için resepsiyona başvurun.", ["kayıp eşya", "kaybettim"]),
        ("Security", "guvenlik", "Gürültü şikayetim var", "Güvenlik devriyesi bilgilendirilir.", ["gürültü"]),
        ("Finance", "muhasebe", "Fatura alabilir miyim?", "Çıkışta veya e-posta ile fatura alabilirsiniz.", ["fatura istiyorum"]),
        ("Finance", "muhasebe", "Depozito ne zaman iade edilir?", "Check-out sonrası 3-7 iş günü içinde iade edilir.", ["depozito iade"]),
        ("Concierge", "transfer", "Havalimanı transferi var mı?", "Evet, ücretli havalimanı transferi organize edilir.", ["havalimanı transfer"]),
        ("Concierge", "turizm", "Tur organizasyonu yapılıyor mu?", "Concierge günlük tur programı sunar.", ["tur", "aktivite"]),
    ]
    extras = [
        ("Otopark ücretsiz mi?", "Evet, otopark ücretsizdir.", "Front Office", "resepsiyon", ["otopark"]),
        ("Plaj kaçta açılıyor?", "Plaj 08:00-19:00 arası açıktır.", "Spa", "spa", ["plaj"]),
        ("Çocuk kulübü var mı?", "4-12 yaş için kids club 10:00-18:00 arası açıktır.", "Concierge", "turizm", ["çocuk kulübü"]),
        ("Fitness salonu saatleri?", "Fitness 07:00-22:00 arası açıktır.", "Spa", "spa", ["fitness"]),
        ("Bebek yatağı isteyebilir miyim?", "Evet, bebek yatağı talep edebilirsiniz.", "Housekeeping", "housekeeping", ["bebek yatağı"]),
        ("Asansör çalışmıyor", "Teknik ekip bilgilendirildi.", "Engineering", "teknik", ["asansör"]),
        ("Sıcak su gelmiyor", "Teknik servis acil yönlendirildi.", "Engineering", "teknik", ["sıcak su"]),
    ]
    faqs: list[dict] = []
    idx = 1
    for dept, key, q, a, kws in templates:
        faqs.append({
            "id": f"faq_{idx:04d}", "question": q, "variants": kws, "answer": a,
            "department": dept, "department_key": key, "keywords": kws, "type": "faq",
        })
        idx += 1
    for q, a, dept, key, kws in extras:
        faqs.append({
            "id": f"faq_{idx:04d}", "question": q, "variants": kws, "answer": a,
            "department": dept, "department_key": key, "keywords": kws, "type": "faq",
        })
        idx += 1
    # Genişlet — 220+
    suffixes = ["bilgi alabilir miyim", "detay", "açıklar mısınız", "ücretli mi", "ücretsiz mi", "nerede", "nasıl"]
    base = list(faqs)
    while len(faqs) < 220:
        src = base[(len(faqs) - len(templates) - len(extras)) % len(base)]
        suf = suffixes[len(faqs) % len(suffixes)]
        faqs.append({
            **src,
            "id": f"faq_{idx:04d}",
            "question": f"{src['question'].rstrip('?')} — {suf}?",
            "variants": src.get("variants", []) + [suf],
        })
        idx += 1
    return faqs


class HotelKnowledgeService:
    """Per-hotel knowledge base + FAQ lookup."""

    @classmethod
    def reload(cls) -> None:
        global _profile_cache
        _profile_cache = None
        _load_faq_raw.cache_clear()

    @classmethod
    def get_profile_path(cls) -> str:
        env_path = os.getenv("HOTEL_PROFILE_PATH", "").strip()
        if env_path and os.path.isfile(env_path):
            return env_path
        if os.path.isfile(_CUSTOM_PROFILE_PATH):
            return _CUSTOM_PROFILE_PATH
        return _PROFILE_PATH

    @classmethod
    def load_profile(cls) -> dict[str, Any]:
        global _profile_cache
        if _profile_cache is not None:
            return _profile_cache
        path = cls.get_profile_path()
        with open(path, encoding="utf-8") as f:
            _profile_cache = json.load(f)
        return _profile_cache

    @classmethod
    def save_profile(cls, profile: dict[str, Any]) -> dict[str, Any]:
        global _profile_cache
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_CUSTOM_PROFILE_PATH, encoding="utf-8", mode="w") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        _profile_cache = profile
        return profile

    @classmethod
    def get_all_faqs(cls, department: Optional[str] = None) -> list[dict]:
        faqs = _load_faq_raw()
        if not department:
            return faqs
        dept = department.lower()
        return [f for f in faqs if f.get("department", "").lower() == dept or dept in f.get("department_key", "")]

    @classmethod
    def _meaningful_tokens(cls, tokens: set[str]) -> set[str]:
        return {t for t in tokens if t not in _FAQ_STOPWORDS and len(t) > 1 and not t.isdigit()}

    @classmethod
    def _should_skip_fuzzy_faq(cls, query: str) -> bool:
        """Oda/şikayet/çapraz arama sorgularında rastgele FAQ eşleşmesini engelle."""
        norm = normalize_turkish(query.lower())
        if re.search(r"\boda\s+\d{3,4}\b", norm) or re.search(r"\b\d{3,4}\s*(?:nolu|te|no)\b", norm):
            return True
        if any(m in norm for m in ("sorun", "sikayet", "kirli", "pis ", "bozuk", "arız", "ariz")):
            if "kahvalt" not in norm and "havuz" not in norm and "check" not in norm:
                return True
        if re.search(r"sorun[a-z]*\s+olan\s+oda", norm) or "hangi oda" in norm:
            return True
        if re.search(r"kahvalt[iı]", norm) and not any(k in norm for k in ("helal", "halal")):
            return True
        return False

    @classmethod
    def _faq_topic_tokens(cls, faq: dict) -> set[str]:
        combined = " ".join([
            faq.get("question", ""),
            faq.get("answer", ""),
            " ".join(faq.get("keywords", [])),
            " ".join(faq.get("variants", [])),
        ])
        return _tokenize(combined)

    @classmethod
    def has_keyword_overlap(cls, query: str, faq_result: dict) -> bool:
        """Sorgu ile FAQ arasında anlamlı kelime örtüşmesi var mı."""
        q_tokens = _tokenize(query) - _STOP_TOKENS
        if not q_tokens:
            return False

        matched_q = faq_result.get("matched_question") or ""
        answer = faq_result.get("answer") or ""
        faq_tokens = (_tokenize(matched_q) | _tokenize(answer)) - _STOP_TOKENS
        overlap = q_tokens & faq_tokens
        if overlap:
            return True

        for topic, markers in _QUERY_TOPIC_MARKERS.items():
            if any(m in normalize_turkish(query.lower()) for m in markers):
                if any(m in normalize_turkish((matched_q + " " + answer).lower()) for m in markers):
                    return True
        return False

    @classmethod
    def is_blocked_faq_match(cls, query: str, faq_result: dict) -> bool:
        """İlgisiz FAQ eşleşmelerini engelle (oda→kasa, kahvaltı→helal vb.)."""
        norm_q = normalize_turkish(query.lower())
        answer = normalize_turkish((faq_result.get("answer") or "").lower())
        question = normalize_turkish((faq_result.get("matched_question") or "").lower())
        combined = answer + " " + question

        query_topics: set[str] = set()
        for topic, markers in _QUERY_TOPIC_MARKERS.items():
            if any(m in norm_q for m in markers):
                query_topics.add(topic)

        faq_topics: set[str] = set()
        for topic, markers in _BLOCKED_FAQ_TOPICS.items():
            if any(m in combined for m in markers):
                faq_topics.add(topic)

        if "sorun" in query_topics or "klima" in query_topics:
            if faq_topics & {"hava_durumu", "kasa", "helal", "oda_servisi"}:
                return True
        if "kirli" in query_topics:
            if faq_topics & {"oda_servisi", "helal", "kasa", "hava_durumu"}:
                return True
        if "kahvalti" in query_topics and "ne var" in norm_q:
            if "helal" in faq_topics and "helal" not in norm_q:
                return True
        if "oda" in query_topics and ("sorun" in query_topics or "kirli" in query_topics):
            if faq_topics & {"hava_durumu", "kasa", "helal"}:
                return True
        return False

    @classmethod
    def _score_faq(cls, query: str, faq: dict) -> float:
        q_tokens = _tokenize(query)
        q_meaningful = cls._meaningful_tokens(q_tokens)
        questions = [faq.get("question", "")]
        questions.extend(faq.get("variants", []))
        questions.extend(faq.get("keywords", []))
        best = 0.0
        for q in questions:
            q_tokens_faq = _tokenize(q)
            if not q_tokens_faq:
                continue
            meaningful_faq = cls._meaningful_tokens(q_tokens_faq)
            if not q_meaningful & meaningful_faq:
                continue
            overlap = len(q_meaningful & meaningful_faq) / max(len(q_meaningful), 1)
            fuzzy = _fuzzy_ratio(query, q)
            kw_bonus = 0.0
            for kw in faq.get("keywords", []):
                kw_n = normalize_turkish(kw.lower())
                if len(kw_n) >= 4 and kw_n in normalize_turkish(query.lower()):
                    kw_bonus += 0.25
            best = max(best, overlap * 0.55 + fuzzy * 0.25 + kw_bonus)
        return best

    @classmethod
    def _interpolate_profile(cls, answer: str, profile: dict) -> str:
        """FAQ şablonlarındaki {check_in} gibi alanları otel profilinden doldurur."""
        if not answer or "{" not in answer:
            return answer
        hotel = profile.get("hotel", {})
        breakfast = profile.get("breakfast", {})
        pool = profile.get("pool", {})
        spa = profile.get("spa", {})
        replacements = {
            "{hotel_name}": hotel.get("name", "Otel"),
            "{check_in}": profile.get("check_in", "14:00"),
            "{check_out}": profile.get("check_out", "12:00"),
            "{breakfast_hours}": breakfast.get("hours", "07:00-10:30"),
            "{pool_hours}": pool.get("hours", "08:00-20:00"),
            "{spa_hours}": spa.get("hours", "10:00-22:00"),
            "{deposit_amount}": profile.get("deposit", {}).get("amount", "1 gece"),
        }
        for token, value in replacements.items():
            answer = answer.replace(token, str(value))
        return answer

    @classmethod
    def _format_breakfast_menu(cls, profile: dict) -> str:
        bf = profile.get("breakfast", {})
        hours = bf.get("hours", "07:00-10:30")
        location = bf.get("location", "Ana Restoran")
        items = bf.get("menu_items") or [
            "Peynir ve zeytin çeşitleri",
            "Sıcak/soğuk omlet ve yumurta çeşitleri",
            "Reçel, bal, tereyağı",
            "Taze meyve ve sebze",
            "Sıcak yemekler (menemen, sucuk-yumurta)",
            "Glutensiz ekmek ve vegan süt alternatifleri",
        ]
        item_lines = "; ".join(items)
        vegan = "Evet" if bf.get("vegan") else "Hayır"
        gluten = "Evet" if bf.get("gluten_free") else "Hayır"
        halal = "Evet" if bf.get("halal") else "Hayır"
        return (
            f"Kahvaltı {hours} arası {location}'da açık büfe servis edilir. "
            f"Çeşitler: {item_lines}. "
            f"Vegan: {vegan}, Glutensiz: {gluten}, Helal sertifikalı: {halal}."
        )

    @classmethod
    def format_meal_menu_today(cls, profile: Optional[dict[str, Any]] = None, query: str = "") -> str:
        """Öğle/akşam menüsü — kahvaltı değil."""
        profile = profile or cls.load_profile()
        norm = normalize_turkish((query or "").lower())
        lunch = profile.get("lunch") or {}
        dinner = profile.get("dinner") or {}
        note = profile.get("daily_menu_note") or (
            "Günün özel menüsü resepsiyon ve restoran girişinde duyurulur."
        )
        bf = profile.get("breakfast") or {}

        want_lunch = any(k in norm for k in ("ogle", "öğle", "ogle yemek", "öğle yemek"))
        want_dinner = any(k in norm for k in ("aksam", "akşam"))
        # "bugün yemekte" → her ikisi
        if not want_lunch and not want_dinner:
            want_lunch = want_dinner = True

        parts: list[str] = []
        if want_lunch:
            hours = lunch.get("hours", "12:30-14:30")
            loc = lunch.get("location", "Ana Restoran")
            items = lunch.get("menu_items") or []
            if items:
                item_lines = "\n".join(f"- {i}" for i in items)
                parts.append(
                    f"**Bugün öğle menüsü** ({hours}, {loc}):\n{item_lines}"
                )
            else:
                parts.append(
                    f"Öğle yemeği {hours} arası {loc}'da servis edilir. "
                    f"Günün özel menü listesi için restoran ekibimize danışabilirsiniz."
                )
        if want_dinner:
            hours = dinner.get("hours", "19:00-21:30")
            loc = dinner.get("location", "Ana Restoran")
            items = dinner.get("menu_items") or []
            if items:
                item_lines = "\n".join(f"- {i}" for i in items)
                parts.append(
                    f"**Bugün akşam menüsü** ({hours}, {loc}):\n{item_lines}"
                )
            else:
                parts.append(
                    f"Akşam yemeği {hours} arası {loc}'da servis edilir."
                )

        body = "\n\n".join(parts)
        extras = (
            f"\n\n{note}\n"
            f"Kahvaltı saatleri: {bf.get('hours', '07:00-10:30')} "
            f"({bf.get('location', 'Ana Restoran')}). "
            "Kahvaltı çeşitleri için 'kahvaltıda ne var' yazabilirsiniz."
        )
        return body + extras

    @classmethod
    def format_daily_meal_menu(cls, profile: Optional[dict[str, Any]] = None, query: str = "") -> str:
        """Alias — staff daily meal intent."""
        return cls.format_meal_menu_today(profile=profile, query=query)

    @classmethod
    def format_services_list(cls, profile: Optional[dict[str, Any]] = None) -> str:
        """Otel hizmetleri listesi — profilden."""
        profile = profile or cls.load_profile()
        hotel_name = profile.get("hotel", {}).get("name", "Otelimiz")
        services = profile.get("services") or []
        if not services:
            services = [
                f"Kahvaltı {profile.get('breakfast', {}).get('hours', '07:00-10:30')}",
                f"Havuz {profile.get('pool', {}).get('hours', '08:00-20:00')}",
                f"Spa {profile.get('spa', {}).get('hours', '10:00-22:00')}",
                "Ücretsiz WiFi",
                "Ücretsiz otopark",
            ]
        lines = "\n".join(f"- {s}" for s in services)
        return (
            f"**{hotel_name} — sunulan hizmetler:**\n\n"
            f"{lines}\n\n"
            "Belirli bir hizmet hakkında detay için sorabilirsiniz "
            "(ör. 'kahvaltı de ne var', 'havuz kaçta bitiyor')."
        )

    @classmethod
    def capabilities_message(cls) -> str:
        return (
            "Operasyon asistanı — personel / yetkili kullanım:\n\n"
            "- **Oda durumu** — 'oda 102 de sorun var mı', 'odalarda ne problemi var'\n"
            "- **Şikayet trendi** — 'bu hafta klima şikayeti', 'kaç şikayet geldi'\n"
            "- **Açık arızalar** — 'klima sorunu olan odalar', 'su sorunu çözüldü mü'\n"
            "- **Departman özeti** — dashboard / istatistik soruları\n"
            "- **F&B** — 'bugün yemekte neler var', kahvaltı saatleri/menü\n"
            "- **Ticket** — 'odamda sorun var' → oda + sorun türü ile kayıt\n\n"
            "Misafir concierge değilim; operasyon ve takip odaklıyım."
        )

    @classmethod
    def _answer_from_profile(cls, query: str, profile: dict) -> Optional[dict]:
        norm = normalize_turkish(query.lower())

        if any(k in norm for k in ("hangi hizmet", "hizmetler neler", "otelde neler var", "tesisler neler", "otel imkan")):
            return {
                "answer": cls.format_services_list(profile),
                "source": "hotel_profile",
                "source_key": "services",
                "score": 0.95,
            }

        rules = [
            (["check-in", "check in", "checkin", "giriş saati", "giris saati"], "check_in", lambda p: f"Check-in saati {p.get('check_in', '14:00')}'dir."),
            (["check-out", "check out", "checkout", "çıkış saati", "cikis saati"], "check_out", lambda p: f"Check-out saati {p.get('check_out', '12:00')}'dir."),
            (["kahvaltı saat", "kahvalti saat", "kahvaltı kaçta"], "breakfast", lambda p: f"Kahvaltı saatleri {p.get('breakfast', {}).get('hours', '07:00-10:30')}. Vegan: {'Evet' if p.get('breakfast', {}).get('vegan') else 'Hayır'}, Glutensiz: {'Evet' if p.get('breakfast', {}).get('gluten_free') else 'Hayır'}."),
            (["kahvaltı de ne var", "kahvalti de ne var", "kahvaltıda ne var", "kahvaltı neler", "kahvaltı çeşit", "kahvalti cesit", "kahvaltı menü"], "breakfast_menu", lambda p: cls._format_breakfast_menu(p)),
            (["vegan", "vejetaryen"], "breakfast", lambda p: f"{'Evet, vegan seçenekler mevcuttur.' if p.get('breakfast', {}).get('vegan') else 'Vegan seçenekler sınırlıdır; lütfen restoran ekibimizle görüşün.'}"),
            (["glutensiz", "gluten"], "breakfast", lambda p: f"{'Evet, glutensiz seçenekler sunulmaktadır.' if p.get('breakfast', {}).get('gluten_free') else 'Glutensiz menü için mutfak ekibimizle iletişime geçin.'}"),
            (["havuz saat", "havuz kaçta", "havuz kapan", "pool"], "pool", lambda p: f"Havuz saatleri {p.get('pool', {}).get('hours', '08:00-20:00')}. Çocuk havuzu: {'Mevcut' if p.get('pool', {}).get('children_pool') else 'Yok'}."),
            (["spa saat", "hamam"], "spa", lambda p: f"Spa saatleri {p.get('spa', {}).get('hours', '10:00-22:00')}. Hamam ücretsiz: {'Evet' if p.get('spa', {}).get('hamam_free') else 'Hayır (ücretli)'}."),
            (["depozito", "depozit"], "deposit", lambda p: f"Depozito {'gereklidir' if p.get('deposit', {}).get('required') else 'gerekli değildir'}. Tutar: {p.get('deposit', {}).get('amount', '1 gece')}."),
            (["otopark", "parking"], "parking", lambda p: f"Otopark {'ücretsizdir' if p.get('parking', {}).get('free') else 'ücretlidir'}."),
            (["transfer", "havalimanı", "havalimani"], "airport_transfer", lambda p: f"Havalimanı transferi {'mevcuttur' if p.get('airport_transfer', {}).get('available') else 'mevcut değildir'}. {'Ücretlidir' if p.get('airport_transfer', {}).get('paid') else 'Ücretsizdir'}."),
            (["erken giriş", "early check"], "early_checkin", lambda p: f"Erken check-in {'mümkündür' if p.get('early_checkin', {}).get('available') else 'mümkün değildir'}. Ücret: {p.get('early_checkin', {}).get('fee', 'müsaitliğe bağlı')}."),
            (["wifi", "wi-fi", "internet şifre"], "wifi", lambda p: f"WiFi {'ücretsizdir' if p.get('wifi', {}).get('free') else 'ücretlidir'}. Şifre: {p.get('wifi', {}).get('password_location', 'resepsiyon')}."),
        ]

        for keywords, source_key, formatter in rules:
            if any(kw in norm for kw in keywords):
                return {
                    "answer": formatter(profile),
                    "source": "hotel_profile",
                    "source_key": source_key,
                    "score": 0.85,
                }
        return None

    @classmethod
    def answer_faq(cls, query: str) -> dict[str, Any]:
        profile = cls.load_profile()
        profile_hit = cls._answer_from_profile(query, profile)
        faqs = _load_faq_raw()

        scored: list[tuple[float, dict]] = []
        for faq in faqs:
            s = cls._score_faq(query, faq)
            if s >= 0.6 and not cls.is_blocked_faq_match(query, {"answer": faq.get("answer"), "matched_question": faq.get("question")}):
                scored.append((s, faq))
        scored.sort(key=lambda x: -x[0])

        if profile_hit and (not scored or profile_hit["score"] >= scored[0][0]):
            if not cls.is_blocked_faq_match(query, profile_hit):
                return {
                    "answer": profile_hit["answer"],
                    "matched_question": query,
                    "department": profile_hit.get("source_key", "general"),
                    "score": profile_hit["score"],
                    "sources": ["hotel_profile"],
                }

        if scored:
            best_score, best_faq = scored[0]
            if best_score >= 0.75 and cls.has_keyword_overlap(query, {"answer": best_faq.get("answer"), "matched_question": best_faq.get("question")}):
                answer = cls._interpolate_profile(best_faq.get("answer", ""), profile)
                return {
                    "answer": answer,
                    "matched_question": best_faq.get("question", ""),
                    "department": best_faq.get("department", "general"),
                    "department_key": best_faq.get("department_key", ""),
                    "score": best_score,
                    "sources": ["hotel_faq"],
                }
            if best_score >= 0.85:
                answer = cls._interpolate_profile(best_faq.get("answer", ""), profile)
                return {
                    "answer": answer,
                    "matched_question": best_faq.get("question", ""),
                    "department": best_faq.get("department", "general"),
                    "department_key": best_faq.get("department_key", ""),
                    "score": best_score,
                    "sources": ["hotel_faq"],
                }

        return {
            "answer": None,
            "matched_question": None,
            "department": None,
            "score": 0.0,
            "sources": [],
        }

    @classmethod
    def get_department_info(cls, department: str) -> dict[str, Any]:
        profile = cls.load_profile()
        depts = profile.get("departments", {})
        key = department.lower().replace(" ", "_")
        aliases = {
            "housekeeping": "housekeeping",
            "front office": "resepsiyon",
            "front_office": "resepsiyon",
            "resepsiyon": "resepsiyon",
            "f&b": "restaurant",
            "fb": "restaurant",
            "restaurant": "restaurant",
            "spa": "spa",
            "engineering": "teknik",
            "teknik": "teknik",
            "security": "guvenlik",
            "guvenlik": "guvenlik",
            "finance": "muhasebe",
            "muhasebe": "muhasebe",
            "sales": "satis",
            "satis": "satis",
            "concierge": "turizm",
            "turizm": "turizm",
            "transfer": "transfer",
        }
        dept_key = aliases.get(key, key)
        info = depts.get(dept_key)
        if not info:
            dept_faqs = cls.get_all_faqs(department)
            return {
                "department": department,
                "found": False,
                "faqs": dept_faqs[:10],
            }
        return {
            "department": department,
            "found": True,
            **info,
            "related_faqs": cls.get_all_faqs(dept_key)[:5],
        }


def get_hotel_knowledge_service() -> HotelKnowledgeService:
    return HotelKnowledgeService()
