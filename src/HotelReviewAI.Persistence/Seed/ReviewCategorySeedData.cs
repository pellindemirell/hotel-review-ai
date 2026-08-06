namespace HotelReviewAI.Persistence.Seed;

public static class ReviewCategorySeedData
{
    public static readonly (string Key, string Name, string[] Keywords, string DepartmentKey)[] Categories =
    [
        // housekeeping
        ("room_cleanliness", "Oda Temizliği", new[] { "kirli oda", "tozlu", "temizlik", "çarşaf", "oda kirli" }, "housekeeping"),
        ("bed_comfort", "Yatak Konforu", new[] { "yatak", "yastık", "rahatsız yatak", "sert yatak" }, "housekeeping"),
        ("bathroom", "Banyo & Tuvalet", new[] { "banyo", "tuvalet", "duş kabini", "kötü koku", "duş" }, "housekeeping"),
        ("linen_towel", "Çarşaf & Havlu", new[] { "havlu", "çarşaf", "nevresim" }, "housekeeping"),
        ("room_size", "Oda Boyutu", new[] { "küçük oda", "oda küçük", "dar oda", "dar bir oda", "küçük oda boyutu" }, "housekeeping"),
        ("soundproofing", "Ses Yalıtımı", new[] { "gürültü", "ses yalıtımı", "duvarlar ince", "yan odadan ses" }, "housekeeping"),
        ("amenities", "Buklet Malzemeleri", new[] { "şampuan", "sabun", "buklet", "duş jeli" }, "housekeeping"),

        // food_beverage
        ("food_quality", "Yemek Kalitesi", new[] { "lezzet", "yemek kalitesi", "soğuk yemek", "tatsız" }, "food_beverage"),
        ("breakfast", "Kahvaltı", new[] { "kahvaltı", "sabah kahvaltısı", "açık büfe" }, "food_beverage"),
        ("restaurant_service", "Restoran Servisi", new[] { "garson", "restoran servisi", "sipariş gecikti" }, "food_beverage"),
        ("menu_variety", "Menü Çeşitliliği", new[] { "menü", "çeşitlilik", "yemek seçeneği" }, "food_beverage"),
        ("drink_quality", "İçecek Kalitesi", new[] { "içecek", "kahve", "çay", "meşrubat" }, "food_beverage"),
        ("minibar", "Minibar", new[] { "minibar", "minibar boş" }, "food_beverage"),
        ("queue_waiting", "Sıra & Bekleme", new[] { "uzun sıra", "yemek sırası", "kalabalık sıra" }, "food_beverage"),

        // front_office
        ("check_in_out", "Giriş/Çıkış", new[] { "check-in", "check-out", "giriş işlemi", "çıkış işlemi" }, "front_office"),
        ("reception_service", "Resepsiyon Hizmeti", new[] { "resepsiyon", "resepsiyonist", "ilgisiz resepsiyon" }, "front_office"),
        ("booking", "Rezervasyon", new[] { "rezervasyon", "rezervasyon iptali" }, "front_office"),
        ("price_value", "Fiyat & Değer", new[] { "pahalı", "fiyat performans", "ücret" }, "front_office"),
        ("billing", "Fatura & Ödeme", new[] { "fatura", "hesap", "ekstra ücret" }, "front_office"),
        ("complaint_resolution", "Şikayet Çözümü", new[] { "şikayet", "çözüm sunmadılar", "ilgilenilmedi", "yardımcı olmadılar" }, "front_office"),

        // engineering
        ("air_conditioning", "Klima", new[] { "klima", "klima çalışmıyor", "soğutmuyor" }, "engineering"),
        ("wifi_internet", "WiFi / İnternet", new[] { "wifi", "internet", "bağlantı copik", "yavaş internet" }, "engineering"),
        ("tv_entertainment", "TV & Eğlence", new[] { "tv", "televizyon", "uydu" }, "engineering"),
        ("elevator", "Asansör", new[] { "asansör", "asansör arızalı", "asansör bekledik" }, "engineering"),
        ("maintenance", "Bakım & Onarım", new[] { "arıza", "bozuk", "tamir", "bakım" }, "engineering"),

        // leisure
        ("pool", "Havuz", new[] { "havuz", "kirli havuz", "soğuk havuz" }, "leisure"),
        ("spa_massage", "Spa & Masaj", new[] { "spa", "masaj", "sauna" }, "leisure"),
        ("animation", "Animasyon & Etkinlik", new[] { "animasyon", "etkinlik", "eğlence ekibi" }, "leisure"),
        ("beach", "Plaj & Deniz", new[] { "plaj", "deniz", "şezlong", "kum" }, "leisure"),
        ("kids_club", "Çocuk Kulübü", new[] { "çocuk kulübü", "çocuk kulubü", "çocuk parkı", "mini club", "çocuk animasyonu" }, "leisure"),
        ("fitness", "Spor & Fitness", new[] { "spor salonu", "fitness" }, "leisure"),

        // grounds
        ("environment", "Çevre & Bahçe", new[] { "bahçe", "çevre", "peyzaj" }, "grounds"),
        ("parking", "Otopark", new[] { "otopark", "park yeri" }, "grounds"),
        ("security", "Güvenlik", new[] { "güvenlik", "güvenli değil" }, "grounds"),
        ("transportation", "Ulaşım & Transfer", new[] { "transfer", "ulaşım", "taksi", "araç", "araba", "hastane", "ambulans", "getiremediler", "götüremediler", "servis" }, "grounds"),
        ("location", "Konum", new[] { "konum", "merkezi", "uzak" }, "grounds"),
        ("view", "Manzara", new[] { "manzara", "deniz manzarası" }, "grounds"),

        // atmosphere
        ("noise_level", "Sessizlik / Gürültü", new[] { "gürültülü", "sessiz", "sakin" }, "atmosphere"),
        ("crowd", "Kalabalık", new[] { "kalabalık", "yoğun", "sakin" }, "atmosphere"),
        ("guest_profile", "Misafir Profili", new[] { "aile", "çift", "misafir profili" }, "atmosphere"),
        ("general_atmosphere", "Genel Atmosfer", new[] { "atmosfer", "ambiyans", "dekor" }, "atmosphere"),
        ("general_management", "Genel Yönetim", new[] { "yönetim", "organizasyon" }, "atmosphere"),

        // staff
        ("staff_attitude", "Personel Tutumu", new[] { "kaba", "güleryüzlü", "saygısız" }, "staff"),
        ("staff_service", "Personel Hizmeti", new[] { "yardımsever", "ilgisiz", "hizmet" }, "staff"),
        ("communication", "Dil & İletişim", new[] { "dil", "iletişim", "anlaşamadık" }, "staff"),
        ("professionalism", "Profesyonellik", new[] { "profesyonel", "amatör" }, "staff"),
    ];
}
