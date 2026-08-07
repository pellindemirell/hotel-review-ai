import pytest
from app.services.absa_service import AbsaService


@pytest.fixture
def absa():
    return AbsaService()


def test_night_shift_emergency_routing(absa):
    text = "kurban bayramının ilk günü sabah 5 6 civarı eşim rahatsızlandı gece vardiyasi amiri 15 20 dakika zahmet edip gelip bizi aracimiza götüremedi"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    dept_labels = [getattr(a, "department_label", a.department) for a in res.aspects]
    dept_keys = [a.department for a in res.aspects]
    # Night manager & medical emergency must route to Ön Büro or Çevre/Güvenlik, NEVER F&B
    assert "Yiyecek & İçecek (F&B)" not in dept_labels
    assert any(k in ("front_office", "grounds", "staff", "Ön Büro & Misafir İlişkileri", "Çevre, Güvenlik & Ulaşım", "Personel Davranışı") for k in dept_keys + dept_labels)


def test_concert_stage_entertainment_routing(absa):
    text = "halk konserinden hallice oturma duzeni yok sahne görünmüyor cikis cikis bir alana doluşup dinlemeye calisiyorsunuz ayakta"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first_dept = res.aspects[0].department
    first_label = getattr(res.aspects[0], "department_label", first_dept)
    # Concert / stage issue must route to Rekreasyon & Eğlence (NOT F&B)
    assert first_dept == "recreation" or first_label == "Rekreasyon & Eğlence"


def test_table_clearing_service_queue_routing(absa):
    text = "servis çok yavaş içeri almaları masayı toplamaları çok uzun sürüyor cunku 2 3 kisi calismiyor"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first_dept = res.aspects[0].department
    first_label = getattr(res.aspects[0], "department_label", first_dept)
    # Table clearing & slow service must route to F&B (NOT Çevre/Grounds)
    assert first_dept == "food_beverage" or first_label == "Yiyecek & İçecek (F&B)"


def test_food_variety_not_drink_variety(absa):
    text = "öğrenci yemekhanesi gibi bol bol tavuk ve makarna çeşidi bulabilirsiniz"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    aspect_label = res.aspects[0].aspect
    first_dept = res.aspects[0].department
    first_label = getattr(res.aspects[0], "department_label", first_dept)
    # "makarna çeşidi" must NOT be categorized as İçecek Çeşitliliği
    assert aspect_label != "İçecek Çeşitliliği"
    assert first_dept == "food_beverage" or first_label == "Yiyecek & İçecek (F&B)"


def test_property_walking_distance_routing(absa):
    text = "her yere çook fazla yürünüyor sakin abartmıyorum çokk fazla"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first_dept = res.aspects[0].department
    # Walking distance complaint must route to Çevre, Güvenlik & Ulaşım (NOT Oda Hizmetleri)
    assert first_dept in ("grounds", "Çevre, Güvenlik & Ulaşım")


def test_beverage_quality_department_preservation(absa):
    text = "içkiler alkoller kalitesiz hepsi alt kalite ürünler sadece irish pub güzel orasi da akşam 6 gece 00 arası açık sadece"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first_dept = res.aspects[0].department
    first_label = getattr(res.aspects[0], "department_label", first_dept)
    # Drink quality must route to Yiyecek & İçecek (F&B)
    assert first_dept == "food_beverage" or first_label == "Yiyecek & İçecek (F&B)"


def test_parking_valet_routing(absa):
    text = "koskoca otelin 30 40 tane arabalık yeri var sizi sacma sapan otele uzak bir yere götürüp arabanızı park etmek zorunda kalıyorsunuz"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first_dept = res.aspects[0].department
    first_label = getattr(res.aspects[0], "department_label", first_dept)
    assert first_dept == "grounds" or first_label == "Çevre, Güvenlik & Ulaşım"
    assert "Otopark" in res.aspects[0].aspect or res.aspects[0].aspect_key == "parking"


def test_entrance_checkin_queue_routing(absa):
    text = "giriş işlemleri için saatlerce sıra bekledik odalara yerleşemedik"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first_dept = res.aspects[0].department
    first_label = getattr(res.aspects[0], "department_label", first_dept)
    # Check-in / Entrance queue must route to Ön Büro & Misafir İlişkileri (NOT F&B)
    assert first_dept == "front_office" or first_label == "Ön Büro & Misafir İlişkileri"


def test_valet_parking_queue_routing(absa):
    text = "otoparka girmek için arabalarla uzun sıra bekledik vale çok yavaştı"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first_dept = res.aspects[0].department
    first_label = getattr(res.aspects[0], "department_label", first_dept)
    # Valet / Parking queue must route to Çevre, Güvenlik & Ulaşım (NOT F&B)
    assert first_dept in ("grounds", "Çevre, Güvenlik & Ulaşım")


def test_transfer_shuttle_queue_routing(absa):
    text = "otelin transfer servisi için uzun bir sıra vardı taksi de bulamadık"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first_dept = res.aspects[0].department
    first_label = getattr(res.aspects[0], "department_label", first_dept)
    # Shuttle / Transfer queue must route to Çevre, Güvenlik & Ulaşım (NOT F&B)
    assert first_dept in ("grounds", "Çevre, Güvenlik & Ulaşım")


def test_show_amphitheater_queue_routing(absa):
    text = "akşam gösterisi için amfitiyatro kapısında kuyruk vardı"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first_dept = res.aspects[0].department
    first_label = getattr(res.aspects[0], "department_label", first_dept)
    # Show / Amphitheater queue must route to Rekreasyon & Eğlence (NOT F&B)
    assert first_dept in ("recreation", "Rekreasyon & Eğlence")


def test_towel_queue_routing(absa):
    text = "havlu almak için havlu bankosunda çok uzun sıra bekledik"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first_dept = res.aspects[0].department
    first_label = getattr(res.aspects[0], "department_label", first_dept)
    # Towel queue must route to Housekeeping or Recreation (NOT F&B)
    assert first_dept in ("housekeeping", "recreation", "Oda Hizmetleri & Housekeeping", "Rekreasyon & Eğlence")
    assert first_dept != "food_beverage" and first_label != "Yiyecek & İçecek (F&B)"


def test_hvac_cooling_and_noise_routing(absa):
    text = "odadaki klima sadece sıcak üflüyor oda pişiyor soğutmuyordu"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first = res.aspects[0]
    first_label = getattr(first, "department_label", first.department)
    assert first_label == "Teknik Servis & IT"
    assert first.sentiment == "Negative"


def test_bathroom_sewage_drain_odor_routing(absa):
    text = "banyodaki giderden inanılmaz bir kanalizasyon kokusu geliyordu"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first = res.aspects[0]
    first_label = getattr(first, "department_label", first.department)
    assert first_label == "Kat Hizmetleri & Temizlik"
    assert first.sentiment == "Negative"


def test_pool_hygiene_dirty_bottom_routing(absa):
    text = "havuzda aşırı klor kokusu vardı gözlerimiz yandı"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first = res.aspects[0]
    first_label = getattr(first, "department_label", first.department)
    assert first_label == "Rekreasyon & Eğlence"
    assert first.sentiment == "Negative"


def test_room_theft_safety_routing(absa):
    text = "odadaki masanın üstünde bıraktığımız saat ve nakit para temizlikten sonra kayboldu çalındı dedik bakmadılar"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    first = res.aspects[0]
    first_label = getattr(first, "department_label", first.department)
    assert first_label in ("Çevre, Güvenlik & Ulaşım", "Ön Büro & Misafir İlişkileri")
    assert first.sentiment == "Negative"


def test_relax_pool_loud_speaker_routing(absa):
    text = "dinlenmek için sessiz relax havuza gittik ama yanımızda son ses hoparlörle müzik çalıyorlardı hiç dinlenemedik"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    negative_aspects = [a for a in res.aspects if a.sentiment == "Negative"]
    assert len(negative_aspects) > 0
    first_neg = negative_aspects[0]
    first_label = getattr(first_neg, "department_label", first_neg.department)
    assert first_label == "Rekreasyon & Eğlence"


def test_heating_boiler_breakdown_routing(absa):
    text = "otelde kazan dairesi arızalanmış 2 gün boyunca ne kalorifer yandı ne de sıcak su aktı donduk"
    res = absa.analyze(text)
    assert len(res.aspects) > 0
    negative_aspects = [a for a in res.aspects if a.sentiment == "Negative"]
    assert len(negative_aspects) > 0
    first_label = getattr(negative_aspects[0], "department_label", negative_aspects[0].department)
    assert first_label == "Teknik Servis & IT"


