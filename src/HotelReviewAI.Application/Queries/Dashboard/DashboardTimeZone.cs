namespace HotelReviewAI.Application.Queries.Dashboard;

/// <summary>
/// Dashboard'da gün kovalarının kesildiği raporlama saat dilimi.
/// </summary>
/// <remarks>
/// ReviewDate <c>timestamptz</c> olarak saklanıyor ve Npgsql onu Kind=Utc olarak
/// materyalize ediyor. Gün kovası açık bir zaman dilimi verilmeden kesilirse UTC'ye
/// göre kesilir; Türkiye UTC+3 olduğu için 21:00-23:59 UTC arası bırakılan yorumlar
/// bir önceki güne düşer. Ölçüldü: mevcut veride 305 yorum bu şekilde yanlış güne
/// yazılıyordu.
///
/// Tek bir yerde tutuluyor — üç ayrı yerde sabit yazmak, birinin unutulmasıyla
/// grafiğin kendi ekseniyle çelişmesine yol açardı.
/// </remarks>
public static class DashboardTimeZone
{
    public const string IanaId = "Europe/Istanbul";
}
