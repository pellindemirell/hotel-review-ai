using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Application.Queries.Dashboard;

/// <summary>
/// Dashboard sorgularının hepsinin kullandığı ortak kapsam (otel + departman) çözümü.
///
/// Önceden her sorgu kendi kapsamını hesaplıyordu ve iki sorun vardı:
///  1) HotelAdmin/DepartmentManager için hotelId claim'i yoksa otel filtresi tamamen
///     atlanıyor, TÜM otellerin verisi dönüyordu (fail-open veri sızıntısı).
///  2) Departman kısıtı yalnızca özet sorgusundaki aksiyonlara uygulanıyordu; trend,
///     kategori ve anahtar kelime sorgularında hiç yoktu.
/// </summary>
public readonly record struct DashboardScope(Guid? HotelId, Guid? DepartmentId, bool ReturnsNothing)
{
    public static DashboardScope Resolve(ICurrentUserService currentUser, Guid? requestedHotelId)
    {
        switch (currentUser.Role)
        {
            case UserRole.HotelAdmin:
                return currentUser.HotelId is { } hotelAdminHotel
                    ? new DashboardScope(hotelAdminHotel, null, false)
                    : Nothing;

            case UserRole.DepartmentManager:
                // Otel VE departman zorunlu; ikisinden biri yoksa veri döndürülmez.
                return currentUser.HotelId is { } deptHotel && currentUser.DepartmentId is { } dept
                    ? new DashboardScope(deptHotel, dept, false)
                    : Nothing;

            default:
                // SuperAdmin: seçili otel varsa ona, yoksa gruba bakar.
                return new DashboardScope(requestedHotelId, null, false);
        }
    }

    private static DashboardScope Nothing => new(null, null, true);
}
