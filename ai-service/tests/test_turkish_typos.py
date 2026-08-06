import pytest
from app.services.turkish_nlp_utils import (
    normalize_turkish,
    count_lexicon_hits,
    classify_by_keywords,
    CAT_CLEANING,
    CAT_FOOD,
    CAT_RECEPTION,
    CAT_TECH,
    CAT_STAFF,
)

def test_normalize_turkish_typos():
    # De-asciification (folded match)
    assert normalize_turkish("muthis") == "müthiş"
    assert "temizlik" in normalize_turkish("temizlk")
    
    # Edit distance 1 (folded DL 1 match)
    assert "klima" in normalize_turkish("kilma")
    assert "çalışmıyor" in normalize_turkish("calismiyor")
    
    # Sentence level correction with punctuation
    norm_sentence = normalize_turkish("oda temizlk ve kilma calismiyor.")
    assert "temizlik" in norm_sentence
    assert "klima" in norm_sentence
    assert "çalışmıyor" in norm_sentence

def test_sentiment_predictions_slang():
    # Test positive slang phrases
    _, _, p1_sp, p1_sn = count_lexicon_hits("oda temiz yikiliyor buralar")
    assert p1_sp > 0
    
    _, _, p2_sp, p2_sn = count_lexicon_hits("hersey krallar gibi")
    assert p2_sp > 0
    
    _, _, p3_sp, p3_sn = count_lexicon_hits("on numara bes yildiz")
    assert p3_sp > 0

    # Test negative slang phrases
    _, _, n1_sp, n1_sn = count_lexicon_hits("oda les gibi kirli")
    assert n1_sn > 0
    
    _, _, n2_sp, n2_sn = count_lexicon_hits("burnumuzdan getirdiler tatili")
    assert n2_sn > 0
    
    _, _, n3_sp, n3_sn = count_lexicon_hits("resmen paranla rezil oluyorsun")
    assert n3_sn > 0

def test_category_classification_slang():
    # Test aspect classification on slang
    cat1, _ = classify_by_keywords("oda les gibi")
    assert cat1 == CAT_CLEANING
    
    cat2, _ = classify_by_keywords("klima uflemiyor")
    assert cat2 == CAT_TECH
    
    cat3, _ = classify_by_keywords("personel suratsiz")
    assert cat3 == CAT_STAFF
    
    cat4, _ = classify_by_keywords("yemekler cop")
    assert cat4 == CAT_FOOD
    
    cat5, _ = classify_by_keywords("giris iskence")
    assert cat5 == CAT_RECEPTION
