using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Persistence.Seed;

public static class UserSeedData
{
    // Sadece demo/test amaçlı - şifreler DbSeeder içinde BCrypt ile hash'lenerek kaydedilir.
    public static readonly (string FullName, string Email, string Password, string Role, string? DepartmentKey)[] Users =
    [
        ("Demo Admin", "admin@demo.com", "Admin123!", Roles.Admin, null),
        ("Demo Manager", "manager@demo.com", "Manager123!", Roles.Manager, "front_office"),
        ("Demo Departman Kullanıcısı", "department@demo.com", "Department123!", Roles.DepartmentUser, "housekeeping"),
        ("Demo Mobil Kullanıcı", "mobile@demo.com", "Mobile123!", Roles.MobileUser, "housekeeping"),
    ];
}
