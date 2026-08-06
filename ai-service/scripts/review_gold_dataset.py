from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

from deep_translator import GoogleTranslator

ANNOTATED_PATH = Path(r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002.json")
REVIEWED_DIR = ANNOTATED_PATH.parent / "reviewed"

TRANSLATOR = GoogleTranslator(source="auto", target="tr")

TURKISH_LANGS = {"tr", "az", "tk"}


def translate(text: str, source_lang: str = "") -> str:
    if not text or source_lang in TURKISH_LANGS:
        return text
    try:
        return TRANSLATOR.translate(text)
    except Exception:
        return text

FAILURE_TYPES_TR = {
    "kus_yuvasi": "Kuş Yuvası (Balkon/oda)",
    "klima_ariza": "Klima Arızası",
    "havlu_talebi": "Havlu Talebi",
    "yemek_soguk": "Yemek Soğuk",
    "personel_davranis": "Personel Davranışı",
    "yavas_hizmet": "Yavaş Hizmet",
    "temizlik_sorunu": "Temizlik Sorunu",
    "oda_sorunu": "Oda Sorunu",
    "yiyecek_kalitesi": "Yiyecek Kalitesi",
    "icecek_sorunu": "İçecek Sorunu",
    "gurultu_sorunu": "Gürültü Sorunu",
    "wi_fi_sorunu": "Wi-Fi Sorunu",
    "otopark_sorunu": "Otopark Sorunu",
    "havuz_sorunu": "Havuz Sorunu",
    "plaj_sorunu": "Plaj Sorunu",
    "checkin_sorunu": "Check-in Sorunu",
    "checkout_sorunu": "Check-out Sorunu",
    "guvenlik_sorunu": "Güvenlik Sorunu",
    "diger": "Diğer",
}

DEPT_TR = {
    "housekeeping": "Kat Hizmetleri",
    "front_desk": "Resepsiyon",
    "food_beverage": "Yiyecek-İçecek",
    "maintenance": "Teknik Servis",
    "guest_relations": "Misafir İlişkileri",
    "management": "Yönetim",
    "animation": "Animasyon",
    "security": "Güvenlik",
    "beach_pool_services": "Plaj-Havuz",
    "concierge": "Concierge",
    "other": "Diğer",
}

CATEGORY_TR = {
    "room_condition": "Oda Durumu",
    "cleanliness": "Temizlik",
    "hvac": "Klima/Isıtma",
    "food_beverage": "Yiyecek-İçecek",
    "staff_service": "Personel Hizmeti",
    "checkin_checkout": "Giriş-Çıkış",
    "maintenance": "Bakım",
    "noise": "Gürültü",
    "amenities": "Olanaklar",
    "location": "Konum",
    "value": "Fiyat/Değer",
    "safety": "Güvenlik",
    "kids_friendly": "Çocuk Dostu",
    "beach_pool": "Plaj-Havuz",
    "entertainment": "Eğlence",
    "other": "Diğer",
}

SEVERITY_TR = {1: "Çok Hafif", 2: "Hafif", 3: "Orta", 4: "Ciddi", 5: "Kritik"}
PRIORITY_TR = {"immediate": "Acil", "short_term": "Kısa Vade", "medium_term": "Orta Vade", "long_term": "Uzun Vade"}
CAUSE_CATEGORY_TR = {
    "training_gap": "Eğitim Eksikliği",
    "staffing_shortage": "Personel Yetersizliği",
    "process_design": "Süreç Tasarımı",
    "maintenance_deferral": "Bakım Ertelenmesi",
    "supply_chain": "Tedarik Zinciri",
    "communication_breakdown": "İletişim Kopukluğu",
    "capacity_issue": "Kapasite Sorunu",
    "quality_control": "Kalite Kontrol",
    "external_factor": "Dış Faktör",
    "system_error": "Sistem Hatası",
    "other": "Diğer",
}
ACTION_TYPE_TR = {
    "training": "Eğitim",
    "process_change": "Süreç Değişikliği",
    "maintenance": "Bakım",
    "staff_addition": "Personel Takviyesi",
    "policy_update": "Politika Güncellemesi",
    "quality_audit": "Kalite Denetimi",
    "facility_upgrade": "Tesis İyileştirme",
    "communication_improvement": "İletişim İyileştirme",
    "supplier_change": "Tedarikçi Değişikliği",
    "other": "Diğer",
}


def load_annotations() -> list[dict]:
    with open(ANNOTATED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_annotation(ann: dict):
    REVIEWED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REVIEWED_DIR / f"{ann['review_id']}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ann, f, ensure_ascii=False, indent=2)


def print_header(text: str):
    print()
    print("=" * 72)
    print(f"  {text}")
    print("=" * 72)


def print_review(ann: dict):
    print_header(f"İnceleme ID: {ann['review_id']}")
    print(f"  Kaynak: {ann['source']}  |  Dil: {ann['language']}  |  Puan: {ann['review_rating']}")
    print(f"  Otel: {ann['hotel_name']}")
    print()

    lang = ann.get("language", "en")
    text = ann["review_text"]

    if lang not in TURKISH_LANGS and text:
        print(f"  ORİJİNAL METİN ({lang}):")
        for line in text.split("\n"):
            print(f"    {line.strip()}")
        print()
        print(f"  TÜRKÇE ÇEVİRİ:")
        translated = translate(text, lang)
        for line in translated.split("\n"):
            print(f"    {line.strip()}")
    else:
        print(f"  YORUM METNİ:")
        for line in text.split("\n"):
            print(f"    {line.strip()}")
    print()

    clauses = ann.get("clauses", [])
    if clauses:
        print(f"  CÜMLELER ({len(clauses)}):")
        for c in clauses:
            sent = c.get("sentiment", "?")
            print(f"    [{c['clause_id']}] ({sent}) {c['text'][:120]}")
        print()

    pfs = ann.get("process_failures", [])
    if pfs:
        print(f"  HATA TİPLERİ ({len(pfs)}):")
        for pf in pfs:
            ft = FAILURE_TYPES_TR.get(pf["failure_type"], pf["failure_type"])
            print(f"    [{pf['failure_id']}] {ft}: {pf['description'][:100]}")
        print()

    depts = ann.get("departments", [])
    if depts:
        print(f"  DEPARTMANLAR:")
        for d in depts:
            dept_tr = DEPT_TR.get(d["department"], d["department"])
            print(f"    [{d['department_id']}] Hata #{d['failure_id']} -> {dept_tr}")
        print()

    sevs = ann.get("severity", [])
    if sevs:
        print(f"  ŞİDDET DERECESİ:")
        for s in sevs:
            print(f"    [{s['severity_id']}] Hata #{s['failure_id']}: Müşteri={s['guest_impact']} ({SEVERITY_TR.get(s['guest_impact'],'')}), İş={s['business_impact']}, Aciliyet={s['urgency']}")
        print()


def interactive_review(ann: dict) -> dict:
    print_review(ann)

    while True:
        print("  KOMUTLAR:")
        print("    [c] Cümleleri düzenle")
        print("    [f] Hata tiplerini düzenle")
        print("    [d] Departmanları düzenle")
        print("    [s] Şiddet derecesini düzenle")
        print("    [r] Kök nedenleri düzenle")
        print("    [a] Aksiyonları düzenle")
        print("    [ok] Kaydet ve geç")
        print("    [skip] Atla")
        print("    [q] Çık")
        cmd = input("  Seçim: ").strip().lower()

        if cmd == "q":
            return None

        if cmd in ("ok", ""):
            ann["annotator"] = "human_review_v1"
            ann["annotation_date"] = date.today().isoformat()
            ann["annotation_notes"] = "İnsan tarafından incelendi"
            save_annotation(ann)
            print(f"  -> Kaydedildi: {ann['review_id']}")
            return ann

        if cmd == "skip":
            print("  -> Atlandı")
            return ann

        if cmd == "c":
            edit_clauses(ann)
            print_review(ann)
        elif cmd == "f":
            edit_failures(ann)
            print_review(ann)
        elif cmd == "d":
            edit_departments(ann)
            print_review(ann)
        elif cmd == "s":
            edit_severity(ann)
            print_review(ann)
        elif cmd == "r":
            edit_root_causes(ann)
            print_review(ann)
        elif cmd == "a":
            edit_actions(ann)
            print_review(ann)
        else:
            print("  Geçersiz komut!")


def edit_clauses(ann: dict):
    print("\n  CÜMLE DÜZENLEME:")
    for c in ann["clauses"]:
        print(f"    [{c['clause_id']}] \"{c['text'][:80]}\" (duygu: {c['sentiment']})")
        yeni_sent = input(f"      Duygu ({c['sentiment']}) [positive/negative/neutral]: ").strip()
        if yeni_sent:
            c["sentiment"] = yeni_sent
    ekle = input("  Yeni cümle ekle? [e/H]: ").strip().lower()
    if ekle == "e":
        metin = input("  Cümle metni: ").strip()
        if metin:
            yeni_id = len(ann["clauses"]) + 1
            ann["clauses"].append({"clause_id": yeni_id, "text": metin, "sentiment": "neutral", "start_char": 0, "end_char": 0})


def edit_failures(ann: dict):
    print("\n  HATA TİPİ DÜZENLEME:")
    print("  Mevcut tipler:")
    for k, v in sorted(FAILURE_TYPES_TR.items()):
        print(f"    {k}: {v}")
    print()
    for pf in ann["process_failures"]:
        ft_show = FAILURE_TYPES_TR.get(pf["failure_type"], pf["failure_type"])
        print(f"    [{pf['failure_id']}] {ft_show}: {pf['description'][:80]}")
        yeni_tip = input(f"      Hata tipi ({pf['failure_type']}): ").strip()
        if yeni_tip:
            pf["failure_type"] = yeni_tip
        yeni_aciklama = input(f"      Açıklama: ").strip()
        if yeni_aciklama:
            pf["description"] = yeni_aciklama


def edit_departments(ann: dict):
    print("\n  DEPARTMAN DÜZENLEME:")
    for k, v in sorted(DEPT_TR.items()):
        print(f"    {k}: {v}")
    print()
    for d in ann["departments"]:
        dept_show = DEPT_TR.get(d["department"], d["department"])
        print(f"    [{d['department_id']}] Hata#{d['failure_id']} -> {dept_show}")
        yeni_dept = input(f"      Departman ({d['department']}): ").strip()
        if yeni_dept:
            d["department"] = yeni_dept


def edit_severity(ann: dict):
    print("\n  ŞİDDET DÜZENLEME (1-5):")
    for sev, label in SEVERITY_TR.items():
        print(f"    {sev}: {label}")
    print()
    for s in ann["severity"]:
        print(f"    [{s['severity_id']}] Hata#{s['failure_id']}: Müşteri={s['guest_impact']} İş={s['business_impact']} Aciliyet={s['urgency']}")
        g = input(f"      Müşteri etkisi ({s['guest_impact']}): ").strip()
        if g: s["guest_impact"] = int(g)
        b = input(f"      İş etkisi ({s['business_impact']}): ").strip()
        if b: s["business_impact"] = int(b)
        u = input(f"      Aciliyet ({s['urgency']}): ").strip()
        if u: s["urgency"] = int(u)


def edit_root_causes(ann: dict):
    print("\n  KÖK NEDEN DÜZENLEME:")
    for k, v in sorted(CAUSE_CATEGORY_TR.items()):
        print(f"    {k}: {v}")
    print()
    for rc in ann["root_causes"]:
        cat_show = CAUSE_CATEGORY_TR.get(rc["cause_category"], rc["cause_category"])
        print(f"    [{rc['root_cause_id']}] Hata#{rc['failure_id']}: {cat_show}")
        yeni_cat = input(f"      Kategori ({rc['cause_category']}): ").strip()
        if yeni_cat: rc["cause_category"] = yeni_cat
        yeni_desc = input(f"      Açıklama: ").strip()
        if yeni_desc: rc["cause_description"] = yeni_desc


def edit_actions(ann: dict):
    print("\n  AKSİYON DÜZENLEME:")
    for k, v in sorted(ACTION_TYPE_TR.items()):
        print(f"    {k}: {v}")
    for pri, label in PRIORITY_TR.items():
        print(f"    Öncelik: {pri} -> {label}")
    print()
    for a in ann["actions"]:
        tip_show = ACTION_TYPE_TR.get(a["action_type"], a["action_type"])
        pri_show = PRIORITY_TR.get(a["priority"], a["priority"])
        print(f"    [{a['action_id']}] KökNeden#{a['root_cause_id']}: {tip_show} - {a['description'][:80]} ({pri_show})")
        yeni_tip = input(f"      Tip ({a['action_type']}): ").strip()
        if yeni_tip: a["action_type"] = yeni_tip
        yeni_desc = input(f"      Açıklama: ").strip()
        if yeni_desc: a["description"] = yeni_desc
        yeni_pri = input(f"      Öncelik ({a['priority']}): ").strip()
        if yeni_pri: a["priority"] = yeni_pri


def main():
    print("=" * 72)
    print("  HCOS Gold Dataset — İnsan İnceleme Aracı")
    print("  Türkçe arayüz — Yabancı diller otomatik Türkçeye çevrilir")
    print("=" * 72)

    annotations = load_annotations()
    non_tr = sum(1 for a in annotations if a.get("language", "en") not in TURKISH_LANGS)
    print(f"\n  Yüklendi: {len(annotations)} adet annotation ({non_tr} yabancı dilde -> çevrilecek)")

    already_reviewed = {p.stem for p in REVIEWED_DIR.glob("*.json")}
    pending = [a for a in annotations if a["review_id"] not in already_reviewed]
    print(f"  Daha önce incelenen: {len(already_reviewed)}")
    print(f"  Bekleyen: {len(pending)}")

    if not pending:
        print("  Tümü incelendi!")
        return

    for i, ann in enumerate(pending):
        print(f"\n  --- İnceleme {i + 1}/{len(pending)} ---")
        result = interactive_review(ann)
        if result is None:
            print("  Erken çıkış yapıldı.")
            break


if __name__ == "__main__":
    main()
