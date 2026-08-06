namespace HotelReviewAI.Persistence.Seed;

public static class DepartmentSeedData
{
    public static readonly (string Key, string Name)[] Departments =
    [
        ("housekeeping", "Kat Hizmetleri & Temizlik"),
        ("food_beverage", "Yiyecek & İçecek"),
        ("front_office", "Ön Büro & Misafir İlişkileri"),
        ("engineering", "Teknik Servis & IT"),
        ("leisure", "Rekreasyon & Eğlence"),
        ("grounds", "Çevre, Güvenlik & Ulaşım"),
        ("atmosphere", "Otel Atmosferi & Misafir Profili"),
        ("staff", "İnsan Kaynakları")
    ];
}
