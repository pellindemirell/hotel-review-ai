from __future__ import annotations

import pytest

from app.services.absa_service import AbsaService, split_clauses_absa
from app.services.clause_pipeline import classify_clause, reload_pipeline_config
from app.services.ontology_service import reload_ontology
from app.services.turkish_nlp_utils import normalize_turkish


@pytest.fixture(autouse=True)
def _reload():
    reload_pipeline_config()
    reload_ontology()


def test_contrastive_negation_negative_scope():
    res = AbsaService.analyze_multidomain("personel guleryuzlu ama cozum odakli degil")
    assert res.aspects
    assert any(a.sentiment == "Negative" for a in res.aspects)


def test_contrastive_positive_recovery_after_negation():
    d = classify_clause("oda cok iyi degil ama konumu harika")
    assert d.sentiment in ("Positive", "Neutral")
    assert d.sentiment_score >= 0


def test_contrastive_hard_negative_wins():
    d = classify_clause("kahvalti guzeldi fakat aksam yemegi berbat")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_long_clause_split_preserves_coordinated_items():
    text = (
        "deniz dalgali ve bulanikti ama barda 30 dakika sira bekledik "
        "ve personel yetersizdi ayrica odada wifi cekmiyordu"
    )
    clauses = split_clauses_absa(text)
    assert len(clauses) >= 3
    assert not any(c.strip().startswith("ve bulanikti") for c in clauses)


def test_long_clause_no_false_split_on_generic_praise_boundary():
    text = "personeller ilgiliydi lokum genel olarak guzeldi ve tatilimiz keyifli gecti"
    clauses = split_clauses_absa(text)
    assert len(clauses) <= 3


def test_general_fallback_remap_fb_queue():
    d = classify_clause("barda uzun kuyruk yuzunden icecek almak imkansizdi")
    assert d.aspect_key == "service_queue"
    assert "yiyecek" in (d.department_label or "").lower() or "f&b" in (d.department_label or "").lower()


def test_general_fallback_remap_pool_queue():
    d = classify_clause("havuzda kaydirak icin uzun sira bekledik")
    assert d.aspect_key in ("pool_queue", "pool_lounger")
    assert "rekreasyon" in (d.department_label or "").lower() or "havuz" in (d.department_label or "").lower()


def test_general_fallback_remap_location():
    d = classify_clause("konum merkeze cok uzak oldugu icin ulasim zordu")
    assert d.aspect_key in ("location", "transport", "property_walkability")
    dep = normalize_turkish((d.department_label or "").lower())
    assert "ulasim" in dep or "cevre" in dep


def test_general_fallback_remap_parking():
    d = classify_clause("otopark alani cok kucuk ve park yeri bulamadik")
    assert d.aspect_key == "parking"
    dep = normalize_turkish((d.department_label or "").lower())
    assert "ulasim" in dep or "cevre" in dep


def test_multidomain_reduces_general_bucket():
    text = (
        "barda uzun kuyruk vardi, otopark yetersizdi ve konum merkeze uzakti "
        "ama personel guleryuzluydu"
    )
    res = AbsaService.analyze_multidomain(text)
    assert res.aspects
    non_general = [a for a in res.aspects if (a.department_label or "").lower() not in ("genel", "diğer", "diger")]
    assert len(non_general) >= 3


def test_room_bird_nest_maps_to_housekeeping_negative():
    res = AbsaService.analyze_multidomain("Otele giriş yaptığımızda odamızda kuş yuvası vardı")
    assert res.aspects
    d = res.aspects[0]
    dep = normalize_turkish((d.department_label or "").lower())
    assert "housekeeping" in dep or "kat hizmetleri" in dep or "oda hizmetleri" in dep
    assert d.aspect in ("room_cleanliness", "housekeeping_service", "housekeeping_privacy")
    assert d.sentiment == "Negative"


def test_food_quality_clause_maps_to_fb_negative():
    res = AbsaService.analyze_multidomain("Yemeklerin kalitesi zayıf, çeşit ve lezzet açısından tatmin edici değil")
    assert res.aspects
    d = res.aspects[0]
    dep = normalize_turkish((d.department_label or "").lower())
    assert "yiyecek" in dep or "f&b" in dep or "restoran" in dep
    assert d.aspect in ("food_quality", "food_taste", "menu_variety")
    assert d.sentiment == "Negative"


def test_expectation_statement_stays_neutral():
    d = classify_clause("Bir otelden beklenen en temel şey temiz bir oda, düzenli oda servisi ve hijyendir")
    assert d.sentiment == "Neutral"
    assert abs(d.sentiment_score) <= 0.05


def test_expectation_not_met_is_negative():
    res = AbsaService.analyze_multidomain("Ancak burada yaşadığımız deneyim bu temel beklentilerin bile karşılanmadığını gösterdi")
    assert res.aspects
    d = res.aspects[0]
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_food_pest_clause_maps_to_fb_hygiene_negative():
    res = AbsaService.analyze_multidomain("Marullar böcekli yemekler lezzetli değil")
    assert res.aspects
    d = res.aspects[0]
    dep = normalize_turkish((d.department_label or "").lower())
    assert "yiyecek" in dep or "f&b" in dep or "restoran" in dep
    assert d.aspect in ("food_hygiene", "food_quality", "food_taste")
    assert d.sentiment == "Negative"


def test_safe_dirty_clause_maps_to_housekeeping_negative():
    res = AbsaService.analyze_multidomain("Bir kasanın içi nasıl pis olabilir benim aklım almadı")
    assert res.aspects
    d = res.aspects[0]
    dep = normalize_turkish((d.department_label or "").lower())
    assert "housekeeping" in dep or "oda hizmetleri" in dep or "kat hizmetleri" in dep
    assert d.aspect in ("room_cleanliness", "amenities", "maintenance")
    assert d.sentiment == "Negative"


def test_oily_tea_clause_stays_negative_not_neutral():
    res = AbsaService.analyze_multidomain("Cay koyuyorsun bardağa üzerinde yağ yüzüyor")
    assert res.aspects
    d = res.aspects[0]
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_disclaimer_positive_long_review_not_forced_negative_single_clause():
    text = (
        "olumsuz yorum yapanlara aldırış yapmayın bir cogu doğuştan memnuniyetsiz, "
        "otel 2015 yapımı genç yapı, odalar genis en düşük 25 m2, genis havuzlar ve suparkı mevcut "
        "3000 kişi kapasiteli elbette kalabalık olacak, sabah kahvaltısı 07.00 11.00 kadar bunu hiç bir otelde bulamazsınız, "
        "akşam yemeği 18.30 21.30 yeme içme sınırsız sabaha kadar daha ne olsun, mutfak çeşiti çok zengin yazılanlara inanmayın, "
        "çocuklu ailelere uygun, sadece kötü yanı otel çok büyük, iyi tatiller dilerim"
    )
    clauses = split_clauses_absa(text)
    assert len(clauses) >= 3
    res = AbsaService.analyze_multidomain(text)
    assert res.aspects
    # Should not collapse to pure negative from "olumsuz yorum..." wording.
    assert res.overall_sentiment in ("Positive", "Mixed", "Neutral")


def test_recommendation_negative_kesinlikle_phrase():
    d = classify_clause("Bu oteli kesinlikle tavsiye etmiyorum")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0
    assert d.aspect_key in ("guest_experience", "overall_experience", "general")


def test_recommendation_negative_tekrar_gelmeyecegim():
    d = classify_clause("Hizmet kalitesi kotuydu, tekrar gelmeyecegim")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_disappointment_hayal_kirikligina_ugradim_negative():
    d = classify_clause("Odalar eskiydi ve acikcasi hayal kirikligina ugradim")
    assert d.sentiment == "Negative"
    assert d.sentiment_score <= -0.5


def test_food_repetition_her_gun_ayni_yemekler_negative():
    d = classify_clause("Her gun ayni yemekler cikti")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0
    assert d.aspect_key in ("food_taste", "food_availability", "guest_experience")


def test_queue_zorunda_kaldik_negative():
    d = classify_clause("Icecek almak icin uzun kuyrukta beklemek zorunda kaldik")
    assert d.sentiment == "Negative"
    assert d.sentiment_score <= -0.55
    assert d.aspect_key in ("service_queue", "pool_queue", "front_office")


def test_queue_long_wait_one_hour_negative():
    d = classify_clause("Her bara gittigimizde bir saat bekledik")
    assert d.sentiment == "Negative"
    assert d.sentiment_score <= -0.55
    assert d.aspect_key in ("service_queue", "fb_staffing", "staff_shortage", "capacity")


def test_pool_queue_havuz_kaydirak_uzun_sira_negative():
    d = classify_clause("Havuzda kaydirak icin uzun sira olustu")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0
    assert d.aspect_key in ("pool_queue", "pool_lounger", "service_queue")


def test_pool_lounger_sezlong_bulunmuyor_negative():
    d = classify_clause("Sezlong bulunmuyor ve insanlar erken saatlerde yer tutuyor")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0
    assert d.aspect_key in ("pool_lounger", "pool_queue", "capacity")


def test_staff_inexperience_deneyimsiz_personel_negative():
    d = classify_clause("Deneyimsiz personel surekli yanlis yonlendirme yapiyordu")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0
    assert d.aspect_key in ("staff_behavior", "staff_shortage", "front_office")


def test_staff_inexperience_acemi_personel_negative():
    d = classify_clause("Acemi personel yuzunden check-in sureci cok uzadi")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0
    assert d.aspect_key in ("staff_behavior", "front_office", "service_queue")


def test_split_memnun_kaldik_ama_boundary():
    clauses = split_clauses_absa("Personelden memnun kaldik ama oda temizligi cok kotuydu")
    assert len(clauses) >= 2
    norm = [normalize_turkish(c.lower()) for c in clauses]
    assert any("memnun kald" in c for c in norm)
    assert any("oda" in c and "temiz" in c for c in norm)


def test_split_guzeldi_fakat_boundary():
    text = "Kahvalti guzeldi fakat aksam yemeginde cesit azdi"
    clauses = split_clauses_absa(text)
    assert len(clauses) >= 1
    res = AbsaService.analyze_multidomain(text)
    assert len(res.aspects) >= 1
    assert any(a.sentiment == "Negative" for a in res.aspects)


def test_split_tavsiye_ederim_ama_boundary():
    clauses = split_clauses_absa("Konumu icin tavsiye ederim ama odalar bekledigimiz kadar temiz degildi")
    assert len(clauses) >= 2
    low = [c.lower() for c in clauses]
    assert any("tavsiye ederim" in c for c in low)
    assert any("odalar" in c and "bekledigimiz" in c for c in low)


def test_split_her_sey_dahil_ama_boundary():
    text = "Her sey dahil ama icecek cesidi beklentiyi karsilamadi"
    clauses = split_clauses_absa(text)
    assert len(clauses) >= 1
    res = AbsaService.analyze_multidomain(text)
    assert len(res.aspects) >= 1
    assert any(a.sentiment in ("Negative", "Neutral") for a in res.aspects)


def test_split_ultra_her_sey_dahil_ama_boundary():
    clauses = split_clauses_absa("Ultra her sey dahil ama bar saatleri cok kisitliydi")
    assert len(clauses) >= 2
    low = [c.lower() for c in clauses]
    assert any("bar saat" in c and "kisitli" in c for c in low)


def test_split_food_and_animation_enumeration_into_two_clauses():
    text = (
        "otelin odalar guzel temiz, yemekleri kahvaltisi lezzetli aksam eglenceleri harika "
        "ozellikle animator ekibi cok iyi"
    )
    clauses = split_clauses_absa(text)
    low = [c.lower() for c in clauses]
    assert len(clauses) >= 2
    assert any(("yemek" in c or "kahvalti" in c) for c in low)
    assert any(("eglence" in c or "animasyon" in c or "animator" in c) for c in low)


# --- Overnight 2026-07-29 expansions ---

def test_overnight_positive_recovery_sorun_yasamadik():
    d = classify_clause("Konaklamamiz boyunca hicbir sorun yasamadik")
    assert d.sentiment == "Positive"
    assert d.sentiment_score > 0


def test_overnight_positive_recovery_harika_zaman():
    d = classify_clause("Harika zaman gecirdik ve herkese tavsiye ederim")
    assert d.sentiment == "Positive"
    assert d.sentiment_score > 0


def test_overnight_positive_staff_her_zaman_guler_yuzlu():
    d = classify_clause("Personel her zaman guler yuzlu ve yardimciydi")
    assert d.sentiment == "Positive"
    assert d.aspect_key in ("staff_behavior", "guest_experience", "front_office")


def test_overnight_hygiene_temiz_degildi_negative():
    d = classify_clause("Odalar temiz degildi ve havlular kirliydi")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_overnight_pest_karasinek_fb_or_hk():
    res = AbsaService.analyze_multidomain("Yemek salonunda karasinek kayniyordu")
    assert res.aspects
    d = res.aspects[0]
    assert d.sentiment == "Negative"
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran", "housekeeping", "oda"))


def test_overnight_food_bayat_negative():
    d = classify_clause("Yemekler bayatti ve lezzetsizdi")
    assert d.sentiment == "Negative"
    assert d.aspect_key in ("food_taste", "food_quality", "food_availability", "guest_experience")


def test_overnight_staff_kaba_negative():
    d = classify_clause("Kaba personel yuzunden surekli rahatsiz olduk")
    assert d.sentiment == "Negative"
    assert d.aspect_key in ("staff_behavior", "staff_shortage", "front_office")


def test_overnight_split_guzeldi_ama_boundary():
    clauses = split_clauses_absa("Kahvalti guzeldi ama aksam yemekleri lezzetsizdi")
    assert len(clauses) >= 2
    res = AbsaService.analyze_multidomain("Kahvalti guzeldi ama aksam yemekleri lezzetsizdi")
    assert any(a.sentiment == "Negative" for a in res.aspects)


def test_overnight_recommendation_bir_daha_gelmeyecegiz():
    d = classify_clause("Hizmet kotuydu bir daha gelmeyecegiz")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_overnight_queue_saatlerce_bekledik():
    d = classify_clause("Barda icecek icin saatlerce bekledik")
    assert d.sentiment == "Negative"
    assert d.aspect_key in ("service_queue", "fb_staffing", "staff_shortage", "pool_queue")


def test_overnight_value_fiyatina_degmez():
    d = classify_clause("Bu fiyata degmez paramiza yazik")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_overnight_egitimsiz_personel_maps_staff():
    d = classify_clause("Egitimsiz personel surekli yanlis yonlendirme yapti")
    assert d.sentiment == "Negative"
    assert d.aspect_key in ("staff_behavior", "staff_shortage", "front_office")


def test_overnight_aspect_dept_guard_pest_hygiene():
    res = AbsaService.analyze_multidomain(
        "Ayrica bir kezde olsa hamam boceginin yemek salonunda onumden gecmesi hicde ic acici bir durum degildi"
    )
    assert res.aspects
    d = next(
        (
            a
            for a in res.aspects
            if "bocek" in normalize_turkish((a.clause or "").lower())
            or "böcek" in (a.clause or "").lower()
            or "hamam" in (a.clause or "").lower()
        ),
        res.aspects[0],
    )
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran"))
    ak = (getattr(d, "aspect_key", None) or getattr(d, "aspect", None) or "").lower()
    assert ak in ("pest_hygiene", "food_hygiene", "food_quality", "food_taste") or "hijyen" in (d.aspect_label or "").lower() or "hasere" in normalize_turkish((d.aspect_label or "").lower())
    assert d.sentiment == "Negative"


def test_overnight_memnun_kalmadik_stays_negative():
    d = classify_clause("Genel olarak hic memnun kalmadik")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_overnight_contrastive_iyiydi_fakat():
    text = "Oda iyiydi fakat ses yalitimi cok kotuydu"
    res = AbsaService.analyze_multidomain(text)
    assert any(a.sentiment == "Negative" for a in res.aspects)


def test_overnight_konser_keeps_animation_with_short_praise():
    text = "Konserler cok guzeldi ve begendim"
    clauses = split_clauses_absa(text)
    joined = " ".join(c.lower() for c in clauses)
    assert "konser" in joined
    res = AbsaService.analyze_multidomain(text)
    assert res.aspects
    dep = normalize_turkish((res.aspects[0].department_label or "").lower())
    assert any(x in dep for x in ("animasyon", "etkinlik", "rekreasyon"))


def test_overnight_kids_club_personel_stays_animation():
    text = "Kids club guzeldi ve personel azdi"
    res = AbsaService.analyze_multidomain(text)
    assert res.aspects
    d = res.aspects[0]
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("animasyon", "etkinlik", "cocuk", "çocuk", "rekreasyon"))
    ak = (getattr(d, "aspect_key", None) or "").lower()
    assert ak in ("kids_club", "animation", "staff_shortage", "staff_behavior") or "kids" in (
        d.aspect_label or ""
    ).lower() or "çocuk" in (d.aspect_label or "").lower()


def test_overnight_havuz_masaj_prefers_havuz():
    d = classify_clause("Havuz ve masaj alani cok guzeldi")
    dep = normalize_turkish((d.department_label or "").lower())
    assert "havuz" in dep or "rekreasyon" in dep
    assert "spa" not in dep or "havuz" in dep


def test_overnight_disclaimer_praise_not_forced_negative():
    d = classify_clause(
        "Olumsuz bir sey yazmak istemem ama genel olarak her sey cok guzeldi iyi tatiller"
    )
    assert d.sentiment in ("Positive", "Neutral")
    assert d.sentiment_score >= 0


def test_excel_restaurant_table_hygiene_is_fb_not_hk():
    d = classify_clause("Restoran biraz kalabalikti ve masalar daha dikkatli temizlenebilirdi")
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran"))
    assert "housekeeping" not in dep and "oda hizmet" not in dep and "kat hizmet" not in dep
    assert d.aspect_key in ("table_cleanliness", "food_taste", "food_quality", "cutlery")


def test_excel_yemek_ve_temizlik_felaket_is_fb_negative():
    d = classify_clause("Yemekler ve temizlik tam bir felaketti")
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran"))
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_excel_kids_pool_slide_not_food():
    d = classify_clause(
        "Mini kaydiraklar ve kopekbaliklari bulunan kucuk cocuklar icin harika bir havuz var"
    )
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("havuz", "rekreasyon", "eglence", "eğlence", "leisure"))
    assert "yiyecek" not in dep and "f&b" not in dep
    assert d.aspect_key in ("pool", "pool_lounger", "kids_capacity", "capacity")
    assert d.sentiment in ("Positive", "Neutral")


def test_excel_priz_bozuk_is_tech():
    d = classify_clause("Odadaki her sey mukemmel calisiyor, sadece birkac priz bozuk")
    dep = normalize_turkish((d.department_label or "").lower())
    assert "teknik" in dep or d.aspect_key in ("tech_general", "maintenance")
    assert d.aspect_key != "food_taste"


def test_excel_dining_salon_temizlik_fb():
    d = classify_clause("ancak yemek salonunda misafirlerden sonra temizlik yapmiyorlar")
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran"))
    assert d.aspect_key in ("table_cleanliness", "food_taste", "food_quality", "food_hygiene")


def test_gold_v2_kalitesiz_drink_is_negative():
    d = classify_clause(
        "Tek olumsuz nokta, alkol ve iceceklerin cok kalitesiz ve yenilemez olmasiydi"
    )
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "bar", "restoran"))


def test_gold_v2_cok_kotu_service_is_negative():
    d = classify_clause("Kokteyl servisi cok kotu")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_gold_v2_en_kotu_otel_is_negative():
    d = classify_clause("Kaldigimiz en kotu 5 yildizli oteldi")
    assert d.sentiment == "Negative"
    assert d.sentiment_score < 0


def test_gold_v2_food_kalitesiz_is_negative():
    d = classify_clause("Restorandaki tum yemekler ve atistirmaliklar kalitesizdi")
    assert d.sentiment == "Negative"
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran"))


def test_gold_v2_kotu_olmadigi_not_forced_negative():
    d = classify_clause("Hava cok kotu olmadigi icin idare ettik")
    assert d.sentiment in ("Neutral", "Positive")
    assert d.sentiment_score >= -0.2


def test_gold_v2_absa_kotu_olmadigi_shield():
    res = AbsaService.analyze_multidomain("Hava çok kötü olmadığı için idare ettik")
    assert res.aspects
    assert res.aspects[0].sentiment in ("Neutral", "Positive")


def test_gold_v2_bakimli_praise_not_tech():
    res = AbsaService.analyze_multidomain("Otel alanı bakımlı")
    assert res.aspects
    dep = normalize_turkish((res.aspects[0].department_label or "").lower())
    assert "teknik" not in dep


def test_gold_v2_contrast_split_strips_ama():
    from app.services.absa_service import split_clauses_absa

    parts = split_clauses_absa(
        "lezzetli ve cesitli yemekler var ama personel ilgisizdi"
    )
    assert any("personel" in p.lower() for p in parts)
    assert not any(p.lower().startswith("ama ") for p in parts)


def test_gold_v2_yatak_leke_not_food():
    d = classify_clause(
        "En küçük oğlum için yedek bir yatak talep ettik, ancak bize mekanizması bozuk ve çeşitli lekeleri olan bir yatak gönderdiler"
    )
    dep = normalize_turkish((d.department_label or "").lower())
    assert "yiyecek" not in dep and "f&b" not in dep
    assert any(x in dep for x in ("housekeeping", "oda", "kat", "temizlik"))
    assert d.sentiment == "Negative"


def test_gold_v2_ortak_alan_tuvalet_is_hk():
    d = classify_clause("Ortak alanlardaki tuvaletler her zaman tertemizdi ve harika kokuyordu")
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("housekeeping", "oda", "kat", "temizlik"))
    assert "atmosfer" not in dep


def test_gold_v2_spa_mudur_not_fo():
    d = classify_clause(
        "Spa'daki kızlara, özellikle de müdür Sevilija'ya (çok ilgili ve hoştu) ve masaj terapisti Roza'ya teşekkürler"
    )
    dep = normalize_turkish((d.department_label or "").lower())
    assert "spa" in dep or "rekreasyon" in dep or "eglence" in dep or "eğlence" in dep
    assert "ön büro" not in (d.department_label or "").lower() and "on buro" not in dep


def test_gold_v2_fiyat_performans_not_genel():
    d = classify_clause("fiyat performans cok iyiydi")
    dep = normalize_turkish((d.department_label or "").lower())
    assert "genel" not in dep
    assert any(x in dep for x in ("on buro", "ön büro", "misafir", "front")) or d.aspect_key in (
        "value_for_money",
        "price_value",
    )
    assert d.sentiment in ("Positive", "Neutral")


def test_gold_v2_staff_kaba_is_negative():
    d = classify_clause("personel: çok kaba, kesinlikle yardımcı olmayan, soğuk")
    assert d.sentiment == "Negative"
    res = AbsaService.analyze_multidomain("personel: çok kaba, kesinlikle yardımcı olmayan, soğuk")
    assert res.aspects
    assert res.aspects[0].sentiment == "Negative"


def test_gold_v2_yardimci_calismiyor_is_negative():
    d = classify_clause("yardımcı olmaya çalışmıyorrr")
    assert d.sentiment == "Negative"


def test_gold_v2_pool_sinek_mikrop_is_negative():
    d = classify_clause(
        "Havuz başı eğlencesine gelince, sıfır 0 0. 0. Isırıcı sineklerden mikrop kapmış olmalıyız"
    )
    assert d.sentiment == "Negative"
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("havuz", "rekreasyon", "eglence", "eğlence", "yiyecek", "f&b"))


def test_gold_v2_otel_atmosferi_not_bare_genel():
    d = classify_clause("otel atmosferi çok güzeldi")
    dep = normalize_turkish((d.department_label or "").lower())
    assert "genel" not in dep or "atmosfer" in dep
    assert d.aspect_key != "general" or "atmosfer" in dep


def test_gold_v2_resepsiyon_personeli_is_fo():
    d = classify_clause("resepsiyon personeli tamamen ilgisiz görünüyordu")
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("on buro", "ön büro", "misafir", "resepsiyon")) or d.aspect_key in (
        "front_office",
        "reception_service",
    )


def test_gold_v2_cutlery_missing_is_negative():
    d = classify_clause(
        "Neredeyse hiç yemek yoktu, masalar zar zor temizlenmişti ve temiz çatal bıçak takımı yoktu"
    )
    assert d.sentiment == "Negative"
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran"))


def test_gold_v2_table_yetersiz_is_negative():
    d = classify_clause(
        "Yemeklere gelince, yemekler tekdüze ve restorandaki temizlik çok yetersiz: masalar misafirlerden sonra isteksizce temizleniyor"
    )
    assert d.sentiment == "Negative"


def test_gold_v2_suluydu_drink_is_drink_quality_negative():
    d = classify_clause(
        "çünkü yeterli olmadığını söylediler, inanılmaz bir şekilde içecekler çok suluydu, restoran ve atıştırmalık barlarındaki yiyecekler"
    )
    assert d.aspect_key in ("drink_quality", "food_taste")
    assert d.sentiment == "Negative"
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran"))


def test_gold_v2_pisman_value_is_negative():
    d = classify_clause(
        "paramı (hem de çok paramı) ve zamanımı buna harcadığıma çok pişman oldum."
    )
    assert d.sentiment == "Negative"
    assert d.aspect_key in ("value_for_money", "price_value", "guest_experience")


def test_overnight_aquapark_bakim_is_havuz():
    res = AbsaService.analyze_multidomain(
        "3 aquaprk var 1'i kapaliydi bir tanesinin ciddi bakima ihtiyaci var"
    )
    assert res.aspects
    bakim = [
        a
        for a in res.aspects
        if "bakim" in normalize_turkish((a.clause or "").lower())
        or "bakım" in (a.clause or "").lower()
        or "aquaprk" in normalize_turkish((a.clause or "").lower())
        or "aquapark" in normalize_turkish((a.clause or "").lower())
    ]
    assert bakim
    for a in bakim:
        dep = normalize_turkish((a.department_label or "").lower())
        assert "teknik" not in dep
        assert any(x in dep for x in ("havuz", "rekreasyon", "eglence", "eğlence"))


def test_gold_v2_multitopic_havuz_ve_personel_splits():
    from app.services.absa_service import split_clauses_absa

    parts = split_clauses_absa("Kahvaltı güzeldi ama havuz kirliydi ve personel ilgisizdi")
    assert len(parts) >= 3
    joined = " | ".join(normalize_turkish(p.lower()) for p in parts)
    assert "kahvalti" in joined or "kahvaltı" in joined
    assert "havuz" in joined
    assert "personel" in joined
    res = AbsaService.analyze_multidomain("Kahvaltı güzeldi ama havuz kirliydi ve personel ilgisizdi")
    deps = {normalize_turkish((a.department_label or "").lower()) for a in res.aspects}
    assert any("yiyecek" in d or "f&b" in d or "restoran" in d for d in deps)
    assert any("havuz" in d or "rekreasyon" in d or "eglence" in d for d in deps)
    assert any("personel" in d for d in deps)


def test_gold_v2_room_proximity_stays_location():
    d = classify_clause("Umarım odamız havuzlara ve restoranlara çok uzak olmaz")
    assert d.aspect_key == "location"
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("cevre", "çevre", "ulasim", "ulaşım", "guvenlik", "güvenlik", "konum"))
    res = AbsaService.analyze_multidomain("Umarım odamız havuzlara ve restoranlara çok uzak olmaz")
    assert res.aspects
    assert any(
        getattr(a, "aspect", "") == "location"
        or "cevre" in normalize_turkish((a.department_label or "").lower())
        or "çevre" in (a.department_label or "").lower()
        for a in res.aspects
    )


def test_gold_v2_gardirop_raf_is_hk_not_genel():
    d = classify_clause(
        "Bizim için en büyük dezavantaj, kıyafetler için raf olmaması ve sadece askılı bir gardırop olmasıydı"
    )
    dep = normalize_turkish((d.department_label or "").lower())
    assert "genel" not in dep
    assert d.aspect_key != "general"
    assert any(x in dep for x in ("oda", "housekeeping", "kat", "temizlik")) or d.aspect_key in (
        "housekeeping_service",
        "room_size",
        "room_amenities",
    )


def test_gold_v2_tatsiz_yemek_is_negative():
    d = classify_clause("Ne yazık ki, olumsuz yönleri temizlik ve tatsız yemekler")
    assert d.sentiment == "Negative"
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran"))


def test_gold_v2_cop_yerde_table_is_negative():
    d = classify_clause("restoran ve barlarda sadece masalar temizlenmiş, çöpler yerde bırakılmıştı")
    assert d.sentiment == "Negative"
    assert d.aspect_key in ("table_cleanliness", "food_taste", "cutlery")


def test_gold_v2_masalar_zar_zor_is_fb_negative():
    d = classify_clause("masalar zar zor temizlenmişti")
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("yiyecek", "f&b", "restoran"))
    assert d.sentiment == "Negative"
    assert d.aspect_key in ("table_cleanliness", "cutlery", "food_taste")


def test_gold_v2_olumsuz_temizlik_is_hk():
    d = classify_clause("olumsuz yönleri temizlik")
    dep = normalize_turkish((d.department_label or "").lower())
    assert any(x in dep for x in ("oda", "housekeeping", "kat", "temizlik"))
    assert "atmosfer" not in dep and "genel" not in dep


def test_gold_v2_genel_mudur_personel_is_staff():
    d = classify_clause(
        "İlk gün odamızda birkaç teknik sorun yaşadık, ancak personel ve otelin genel müdürü Bay Engin, "
        "konuyla bizzat ilgilenerek sorunlarımızı hızla çözdüler"
    )
    dep = normalize_turkish((d.department_label or "").lower())
    assert "personel" in dep or d.aspect_key == "staff_behavior"
    assert "atmosfer" not in dep


def test_gold_v2_disari_cikmaya_degmez_is_negative():
    d = classify_clause("otelden dışarı çıkmaya değmez")
    assert d.sentiment == "Negative"
    assert d.aspect_key in ("value_for_money", "price_value", "guest_experience", "location")


def test_gold_v2_yerden_yere_eziyet_is_walkability():
    d = classify_clause(
        "Otel arazisi çok büyük ve güzel. ancak bu otelde bir yerden bir yere gitmek gerçek bir eziyet"
    )
    assert d.aspect_key == "property_walkability"
    assert d.sentiment == "Negative"

