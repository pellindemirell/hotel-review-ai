"""
Test fixtures for HODIP unit tests — 30+ Turkish/English hotel review clauses.

Each clause has expected fact_type(s) for knowledge_graph validation.
Some clauses are designed to match specific patterns (bird_nest, hvac, etc.),
others are edge cases (empty, mixed, multi-clause).

Usage:
    from tests.test_hodip.fixtures import TEST_CLAUSES, get_expected_fact_types
"""

from __future__ import annotations

from typing import Any

# Each entry: (clause_text, expected_fact_types, expected_department, optional_notes)
TEST_CLAUSES: list[tuple[str, list[str], str | None, str]] = [
    # --- Bird nest / balcony cleaning (known pattern: bird_nest) ---
    ("Odaya girdigimizde balkonda kus yuvasi vardi.", ["OBSERVATION", "PROCESS_FAILURE"], "HOUSEKEEPING", "bird_nest"),
    ("Balkon kus pisligi icindeydi, hic temizlenmemis.", ["OBSERVATION", "PROCESS_FAILURE"], "HOUSEKEEPING", "bird_nest"),
    ("Pencere kenarinda guvercin pisligi vardi.", ["OBSERVATION"], "HOUSEKEEPING", "bird_droppings"),
    ("Balkon tertemizdi, hicbir sorun yok.", ["OBSERVATION"], None, "clean_balcony"),
    ("Kus yuvasi vardi ve resepsiyona soyledigimizde ilgilenmediler.", ["OBSERVATION", "PROCESS_FAILURE", "GUEST_IMPACT"], "HOUSEKEEPING", "bird_nest_with_complaint"),

    # --- HVAC / AC issues ---
    ("Klima calismiyor, oda buz gibi.", ["OBSERVATION", "PROCESS_FAILURE"], "HOUSEKEEPING", "hvac"),
    ("Oda cok sicakti, klima bakimi yapilmamis.", ["OBSERVATION", "PROCESS_FAILURE"], "HOUSEKEEPING", "hvac"),
    ("Klima ses yapiyor, gece uyumak imkansiz.", ["OBSERVATION", "GUEST_IMPACT"], "HOUSEKEEPING", "hvac_noise"),
    ("Isitma sistemi harika calisiyor.", ["OBSERVATION"], "HOUSEKEEPING", "heating_positive"),

    # --- Towel / Amenity issues ---
    ("Havlu istedik 3 kere aradik getirmediler.", ["OBSERVATION", "PROCESS_FAILURE", "GUEST_IMPACT"], "HOUSEKEEPING", "towel_missing"),
    ("Odaya havlu konmamisti, terlik yoktu.", ["OBSERVATION", "PROCESS_FAILURE"], "HOUSEKEEPING", "amenity_missing"),
    ("Mini bar bos geldi, doldurmamislar.", ["OBSERVATION", "PROCESS_FAILURE"], "FOOD_BEVERAGE", "minibar_empty"),

    # --- Food & Beverage ---
    ("Kahvalti cok cesitliydi ama yemekler soguktu.", ["OBSERVATION", "PROCESS_FAILURE"], "FOOD_BEVERAGE", "breakfast_cold"),
    ("Corba lezzetliydi ama ekmek bayatti.", ["OBSERVATION", "PROCESS_FAILURE"], "FOOD_BEVERAGE", "bread_stale"),
    ("Restoranda garsonlar cok yavasti, 40 dk bekledik.", ["OBSERVATION", "PROCESS_FAILURE", "GUEST_IMPACT"], "FOOD_BEVERAGE", "slow_service"),

    # --- Staff / Service ---
    ("Resepsiyondaki memur cok kabaydi.", ["OBSERVATION", "PROCESS_FAILURE"], "FRONT_OFFICE", "rude_staff"),
    ("Personel harikaydi, her sey icin tesekkurler.", ["OBSERVATION"], None, "staff_positive"),
    ("Kat hizmetcileri odani temizlemeden gecmisti.", ["OBSERVATION", "PROCESS_FAILURE"], "HOUSEKEEPING", "missed_cleaning"),

    # --- Maintenance ---
    ("Havuz bakimsizdi, su bulanikti.", ["OBSERVATION", "PROCESS_FAILURE"], "MAINTENANCE", "pool_unclean"),
    ("Asansor 2 gundur bozuktu.", ["OBSERVATION", "PROCESS_FAILURE"], "MAINTENANCE", "elevator_broken"),
    ("Oda kapisi kilidi bozuk, iceri giremedik.", ["OBSERVATION", "PROCESS_FAILURE", "GUEST_IMPACT"], "MAINTENANCE", "door_lock_broken"),

    # --- Front Office ---
    ("Check-in cok uzun surdu, 1 saat bekledik.", ["OBSERVATION", "PROCESS_FAILURE", "GUEST_IMPACT"], "FRONT_OFFICE", "slow_checkin"),
    ("Oda bize soylenenden cok kucuktu.", ["OBSERVATION", "PROCESS_FAILURE"], "FRONT_OFFICE", "room_not_as_advertised"),

    # --- Spa & Wellness ---
    ("Spa pahaliydi ve hizmet kotuydu.", ["OBSERVATION", "PROCESS_FAILURE"], "SPA", "spa_overpriced"),
    ("Masaj harikaydi, kesinlikle tavsiye ederim.", ["OBSERVATION"], "SPA", "massage_positive"),

    # --- English clauses ---
    ("The room was dirty, hair on the bed sheets.", ["OBSERVATION", "PROCESS_FAILURE"], "HOUSEKEEPING", "dirty_room_en"),
    ("Breakfast was cold and the coffee was terrible.", ["OBSERVATION", "PROCESS_FAILURE"], "FOOD_BEVERAGE", "breakfast_cold_en"),
    ("The staff were incredibly helpful and friendly.", ["OBSERVATION"], None, "staff_positive_en"),
    ("AC was not working, room was extremely hot.", ["OBSERVATION", "PROCESS_FAILURE"], "HOUSEKEEPING", "hvac_en"),
    ("We asked for extra towels 3 times, never received.", ["OBSERVATION", "PROCESS_FAILURE", "GUEST_IMPACT"], "HOUSEKEEPING", "towel_missing_en"),

    # --- Edge cases ---
    ("", [], None, "empty_clause"),
    ("   ", [], None, "whitespace_clause"),
    ("Cok guzeldi.", ["OBSERVATION"], None, "vague_positive"),
    ("Berbatti.", ["OBSERVATION"], None, "vague_negative"),
    ("Otel genel olarak iyiydi, kahvalti haric her sey guzeldi.", ["OBSERVATION", "PROCESS_FAILURE"], "FOOD_BEVERAGE", "mixed_sentiment"),

    # --- Multi-department ---
    ("Oda sicakti, kahvalti gec geldi, personel ilgisizdi.", ["OBSERVATION", "PROCESS_FAILURE", "GUEST_IMPACT"], None, "multi_issue"),
]


def get_expected(clause: str) -> list[str]:
    """Get expected fact_types for a clause."""
    for c, facts, dept, note in TEST_CLAUSES:
        if c == clause:
            return facts
    return []


def get_by_note(note: str) -> list[tuple[str, list[str], str | None, str]]:
    """Get all fixtures matching a note keyword."""
    return [(c, f, d, n) for c, f, d, n in TEST_CLAUSES if note in n]
