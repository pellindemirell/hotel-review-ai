from app.services.turkish_nlp_utils import extract_keywords as _extract_keywords


class KeywordService:
    """Anahtar kelime çıkarımı — merkezi tokenize_turkish üzerinden."""

    @classmethod
    def extract_keywords(cls, text: str, max_keywords: int = 3) -> list[str]:
        return _extract_keywords(text, max_keywords=max_keywords)
