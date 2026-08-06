import pytest
from app.services.ontology_service import OntologyService

def test_aquapark_hours_regression():
    text = "aqua saatini biraz daha uzatılsa hiç fena olmaz çünkü pek sıra gelmiyor."
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Rekreasyon & Eğlence"

def test_pike_bedding_regression():
    text = "gittiğimiz tarihte akşamları hava serin olduğu için odada üşüdüğümüzden pike istedik getirmediler en basiti bu mesela"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Oda Hizmetleri & Housekeeping"

def test_guidance_reception_regression():
    text = "yönlendirme ve bilgilendirme çok zayıftı bu yıl"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Ön Büro & Misafir İlişkileri"

def test_staff_attitude_lakayit_regression():
    text = "kendileri bizimle ilgilenmedi iletişime bile geçmedi çok lakayıt biriydi"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Personel Davranışı"

def test_guest_profile_chaos_regression():
    text = "saygısız misafirler yüzünde resmen kaos ortamı vardı"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Otel Atmosferi & Misafir Profili"

def test_date_extraction_no_fake_room_regression():
    text = "15.05-18.05/2026 tarihleri arasında arkadaşımla tatile gittim"
    entities = OntologyService.search_entity(text)
    room_entities = [e for e in entities if e.get("entity_type") == "room"]
    assert len(room_entities) == 0

def test_restaurant_cleanliness_not_housekeeping_regression():
    text = "restoranda masa kirliydi silen kimse yoktu"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Yiyecek & İçecek (F&B)"
    assert result.get("aspect_key") == "restaurant_service"

def test_valet_parking_grounds_regression():
    text = "valet hizmeti çok yavaştı otopark alanı yetersiz"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Çevre, Güvenlik & Ulaşım"
    assert result.get("aspect_key") == "parking"

def test_security_grounds_regression():
    text = "güvenlik görevlileri ve kameralar yetersizdi"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Çevre, Güvenlik & Ulaşım"


def test_portakal_suyu_parali_not_food_taste():
    """Paid juice amenity → F&B ekstra ücret, NOT Yemek Lezzeti."""
    from app.services.clause_pipeline import classify_clause, reload_pipeline_config
    from app.services.suggestion_engine import SuggestionContext, build_suggestion

    reload_pipeline_config()
    clause = "sabahları sıkma portakal suyunun paralı olması gereksizdi"
    d = classify_clause(clause)
    assert d.aspect_key == "fb_extra_charge"
    assert d.aspect_label != "Yemek Lezzeti"
    assert "f&b" in (d.department_label or "").lower() or "yiyecek" in (d.department_label or "").lower()
    assert d.sentiment == "Negative"
    sug = build_suggestion(
        SuggestionContext(category="Yiyecek & İçecek (F&B)", text=clause, sentiment="Negative")
    ).lower()
    assert any(w in sug for w in ("ücret", "dahil", "politika", "fiyat"))
    assert "tadım" not in sug
    assert "lezzet kalite" not in sug


def test_complaint_resolution_regression():
    text = "misafir ilişkilerine bildirdik ama sorunumuzu çözmediler"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Ön Büro & Misafir İlişkileri"
    assert result.get("aspect_key") == "complaint_resolution"

def test_pool_sunbed_regression():
    text = "sabah erkenden şezlong kapmak zorunda kaldık"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Rekreasyon & Eğlence"
    assert result.get("aspect_key") == "pool"

def test_beach_sunbed_regression():
    text = "plajda hiç şezlong ve şemsiye bulamadık"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Rekreasyon & Eğlence"
    assert result.get("aspect_key") == "beach"

def test_kids_club_regression():
    text = "çocuk kulübü sorumlusu ilgilenmedi"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Rekreasyon & Eğlence"
    assert result.get("aspect_key") == "kids_club"

def test_gym_fitness_regression():
    text = "gym aletleri çok eskiydi"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Rekreasyon & Eğlence"
    assert result.get("aspect_key") == "fitness"

def test_amenities_regression():
    text = "odaya şampuan ve sabun koymamışlar"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Oda Hizmetleri & Housekeeping"
    assert result.get("aspect_key") == "amenities"

def test_booking_overbooking_regression():
    text = "overbooking nedeniyle odaya giremedik"
    result = OntologyService.map_aspect_to_department("", text)
    assert result.get("departmentLabel") == "Ön Büro & Misafir İlişkileri"
    assert result.get("aspect_key") == "booking"
