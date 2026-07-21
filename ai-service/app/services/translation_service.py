import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from langdetect import detect
from deep_translator import GoogleTranslator

logger = logging.getLogger("ai_service")
_TRANSLATE_TIMEOUT_SEC = 3  # UI yolunu Google ile bloke etmesin
_translate_pool = ThreadPoolExecutor(max_workers=2)
_TR_CHAR_RE = None

def _has_turkish_chars(text: str) -> bool:
    global _TR_CHAR_RE
    if _TR_CHAR_RE is None:
        import re
        _TR_CHAR_RE = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
    return bool(_TR_CHAR_RE.search(text))

class TranslationService:
    @staticmethod
    def translate_to_turkish(text: str, source_lang: str = None) -> tuple[str, str]:
        """
        Yorumun dilini tespit eder ve Türkçe değilse çevirir.
        Geri dönüş değeri: (çevrilmiş_metin, tespit_edilen_dil)
        """
        if not text or not text.strip():
            return "", "unknown"

        # 1. Dil Tespiti — TR karakterleri varsa langdetect/Google atlanır
        detected_lang = source_lang
        if not detected_lang and _has_turkish_chars(text):
            detected_lang = "tr"
        if not detected_lang:
            try:
                detected_lang = detect(text)
            except Exception as e:
                logger.warning(f"Dil tespiti hatası, varsayılan 'en' seçildi: {e}")
                detected_lang = "en"

        # 2. Türkçe ise Çevirme
        if detected_lang.lower() == 'tr':
            return text, 'tr'

        # 2b. Bilinen kalıplar için çevrimdışı sözlük (ağ gerekmez)
        from app.services.turkish_nlp_utils import apply_offline_translation
        offline = apply_offline_translation(text)
        if offline != text:
            return offline, detected_lang

        # 3. Yabancı Dil Çeviri İşlemi
        try:
            future = _translate_pool.submit(
                GoogleTranslator(source='auto', target='tr').translate, text,
            )
            translated = future.result(timeout=_TRANSLATE_TIMEOUT_SEC)
            return translated, detected_lang
        except FuturesTimeoutError:
            logger.warning(f"Çeviri zaman aşımı ({_TRANSLATE_TIMEOUT_SEC}s), offline fallback")
        except Exception as e:
            logger.error(f"Çeviri servisinde hata oluştu: {e}")
        from app.services.turkish_nlp_utils import apply_offline_translation
        fallback = apply_offline_translation(text)
        if fallback != text:
            return fallback, detected_lang
        return text, detected_lang
