namespace HotelReviewAI.Persistence.Seed;

public static class ReviewCategorySeedData
{
    public static readonly (string Key, string Name, string[] Keywords, string DepartmentKey)[] Categories =
    [
        // housekeeping
        ("room_cleanliness", "Oda Temizliği", new[] { "kirli", "toz", "temizlik", "çarşaf" }, "housekeeping"),
        ("bed_comfort", "Yatak Konforu", new[] { "yatak", "yastık", "rahatsız", "sert" }, "housekeeping"),
        ("bathroom", "Banyo & Tuvalet", new[] { "banyo", "tuvalet", "duş", "koku" }, "housekeeping"),
        ("linen_towel", "Çarşaf & Havlu", new[] { "havlu", "çarşaf", "nevresim" }, "housekeeping"),
        ("room_size", "Oda Boyutu", new[] { "küçük", "dar", "geniş", "ferah" }, "housekeeping"),
        ("soundproofing", "Ses Yalıtımı", new[] { "gürültü", "ses", "yalıtım", "duyuluyor" }, "housekeeping"),
        ("amenities", "Buklet Malzemeleri", new[] { "şampuan", "sabun", "buklet", "malzeme" }, "housekeeping"),

        // food_beverage
        ("food_quality", "Yemek Kalitesi", new[] { "lezzet", "yemek", "soğuk", "tatsız" }, "food_beverage"),
        ("breakfast", "Kahvaltı", new[] { "kahvaltı", "sabah", "açık büfe" }, "food_beverage"),
        ("restaurant_service", "Restoran Servisi", new[] { "garson", "servis", "bekleme", "sipariş" }, "food_beverage"),
        ("menu_variety", "Menü Çeşitliliği", new[] { "menü", "çeşit", "seçenek" }, "food_beverage"),
        ("drink_quality", "İçecek Kalitesi", new[] { "içecek", "kahve", "çay", "meşrubat" }, "food_beverage"),
        ("minibar", "Minibar", new[] { "minibar", "dolu", "boş" }, "food_beverage"),
        ("queue_waiting", "Sıra & Bekleme", new[] { "sıra", "bekleme", "kalabalık" }, "food_beverage"),

        // front_office
        ("check_in_out", "Giriş/Çıkış", new[] { "check-in", "check-out", "giriş", "çıkış" }, "front_office"),
        ("reception_service", "Resepsiyon Hizmeti", new[] { "resepsiyon", "ilgisiz", "yardımsever" }, "front_office"),
        ("booking", "Rezervasyon", new[] { "rezervasyon", "iptal", "değişiklik" }, "front_office"),
        ("price_value", "Fiyat & Değer", new[] { "pahalı", "fiyat", "ücret", "değer" }, "front_office"),
        ("billing", "Fatura & Ödeme", new[] { "fatura", "hesap", "ödeme", "ekstra ücret" }, "front_office"),
        ("complaint_resolution", "Şikayet Çözümü", new[] { "şikayet", "çözüm", "ilgilenilmedi" }, "front_office"),

        // engineering
        ("air_conditioning", "Klima", new[] { "klima", "sıcak", "soğuk", "çalışmıyor" }, "engineering"),
        ("wifi_internet", "WiFi / İnternet", new[] { "wifi", "internet", "bağlantı", "yavaş" }, "engineering"),
        ("tv_entertainment", "TV & Eğlence", new[] { "tv", "kanal", "uydu" }, "engineering"),
        ("elevator", "Asansör", new[] { "asansör", "arızalı", "bekleme" }, "engineering"),
        ("maintenance", "Bakım & Onarım", new[] { "arıza", "bozuk", "tamir", "bakım" }, "engineering"),

        // leisure
        ("pool", "Havuz", new[] { "havuz", "kirli", "su", "soğuk" }, "leisure"),
        ("spa_massage", "Spa & Masaj", new[] { "spa", "masaj", "sauna" }, "leisure"),
        ("animation", "Animasyon & Etkinlik", new[] { "animasyon", "etkinlik", "eğlence" }, "leisure"),
        ("beach", "Plaj & Deniz", new[] { "plaj", "deniz", "şezlong", "kum" }, "leisure"),
        ("kids_club", "Çocuk Kulübü", new[] { "çocuk", "kulüp", "oyun alanı" }, "leisure"),
        ("fitness", "Spor & Fitness", new[] { "spor", "fitness", "salon" }, "leisure"),

        // grounds
        ("environment", "Çevre & Bahçe", new[] { "bahçe", "çevre", "peyzaj" }, "grounds"),
        ("parking", "Otopark", new[] { "otopark", "park yeri" }, "grounds"),
        ("security", "Güvenlik", new[] { "güvenlik", "güvenli değil" }, "grounds"),
        ("transportation", "Ulaşım & Transfer", new[] { "transfer", "ulaşım", "servis" }, "grounds"),
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
