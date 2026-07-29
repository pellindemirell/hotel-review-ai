using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Persistence.Seed;

public static class UserSeedData
{
    // Sadece demo/test amaçlı - şifreler DbSeeder içinde BCrypt ile hash'lenerek kaydedilir.
    public static readonly (string FullName, string Email, string Password, string Role, string? DepartmentKey)[] Users =
    [
        ("Demo Admin", "admin@demo.com", "Admin123!", Roles.Admin, null),
        ("Guest Profile Manager", "guestprofilemanager@demo.com", "1234", Roles.Manager, "atmosphere"),
        ("IT Manager", "itmanager@demo.com", "1234", Roles.Manager, "engineering"),
        ("F&B Manager", "f&bmanager@demo.com", "1234", Roles.Manager, "food_beverage"),
        ("Guest Relations Manager", "guestrelationsmanager@demo.com", "1234", Roles.Manager, "front_office"),
        ("Security Manager", "securitymanager@demo.com", "1234", Roles.Manager, "grounds"),
        ("Housekeeping Manager", "housekeepingmanager@demo.com", "1234", Roles.Manager, "housekeeping"),
        ("Recreation Manager", "recreationmanager@demo.com", "1234", Roles.Manager, "leisure"),
        ("Human Resources Manager", "humanresourcemanager@demo.com", "1234", Roles.Manager, "staff"),
        ("Demo Departman Kullanıcısı", "department@demo.com", "Department123!", Roles.DepartmentUser, "housekeeping"),
        ("Demo Mobil Kullanıcı", "mobile@demo.com", "Mobile123!", Roles.MobileUser, "housekeeping"),
    ];

    /// <summary>
    /// Türkçe rastgele isim havuzu - bulk personel seed için kullanılır.
    /// </summary>
    public static readonly string[] FirstNames =
    [
        "Ahmet", "Mehmet", "Mustafa", "Ali", "Hüseyin", "Hasan", "İbrahim", "İsmail",
        "Ömer", "Yusuf", "Murat", "Emre", "Burak", "Serkan", "Tolga", "Onur",
        "Kemal", "Caner", "Enes", "Furkan", "Berk", "Oğuz", "Deniz", "Barış",
        "Ercan", "Volkan", "Gökhan", "Taner", "Uğur", "Selim",
        "Ayşe", "Fatma", "Zeynep", "Emine", "Hatice", "Elif", "Merve", "Büşra",
        "Seda", "Gül", "Pınar", "Gamze", "Tuğba", "Şeyma", "Rana", "Ceren",
        "Derya", "Melisa", "Neslihan", "Yasemin"
    ];

    public static readonly string[] LastNames =
    [
        "Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Yıldız", "Yıldırım", "Öztürk",
        "Aydın", "Özdemir", "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Koc",
        "Kurt", "Özkan", "Şimşek", "Polat", "Erdoğan", "Güneş", "Tekin", "Çakır",
        "Koç", "Bulut", "Acar", "Aktaş", "Güler", "Türk",
        "Duman", "Bozkurt", "Demirci", "Keskin", "Uysal", "Avcı", "Korkmaz", "Balcı",
        "Erdem", "Topal", "Toprak", "Kaplan", "Karahan", "Tuncer", "Yavuz", "Çevik",
        "Güngör", "Şener", "Karadağ", "Albayrak"
    ];

    /// <summary>
    /// Departman başına düşen personel sayısını hesaplar.
    /// 50 personeli 8 departmana böler; her departmana minimum 2, kalanlar round-robin dağıtılır.
    /// </summary>
    public static Dictionary<string, int> GetPersonnelCountPerDepartment(int totalPersonnel, string[] departmentKeys)
    {
        int deptCount = departmentKeys.Length;
        int minPerDept = 2;
        int guaranteed = minPerDept * deptCount;
        int remaining = totalPersonnel - guaranteed;

        var counts = new Dictionary<string, int>();
        for (int i = 0; i < deptCount; i++)
        {
            counts[departmentKeys[i]] = minPerDept;
        }

        // Kalanları round-robin ile dağıt
        for (int i = 0; i < remaining; i++)
        {
            counts[departmentKeys[i % deptCount]]++;
        }

        return counts;
    }
}
