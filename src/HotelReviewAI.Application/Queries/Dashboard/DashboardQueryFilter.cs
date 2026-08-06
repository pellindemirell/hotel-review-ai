namespace HotelReviewAI.Application.Queries.Dashboard;

/// <summary>
/// Dashboard okuma sorgularının ortak filtresi.
/// </summary>
/// <remarks>
/// Varsayılan pencere DÖRT sorguda da aynı olmalı. Önceden yalnızca trend sorgusu
/// son 30 güne düşüyordu, diğerlerinin varsayılanı yoktu. Frontend her zaman iki
/// tarihi de gönderdiği için bu bugün ısırmıyor; ama trend artık dönem ortalaması
/// döndürüyor ve kullanıcı bunu "Ortalama Puan" kartıyla karşılaştırıyor — farklı
/// varsayılanlar sessiz bir tutarsızlık üretirdi.
/// </remarks>
public readonly record struct DashboardQueryFilter(
    Guid? HotelId,
    Guid? DepartmentId,
    DateTime FromUtc,
    DateTime ToUtc)
{
    private const int DefaultWindowDays = 30;

    public static DashboardQueryFilter Create(DashboardScope scope, DateTime? from, DateTime? to)
    {
        var toUtc = ToUtcKind(to ?? DateTime.UtcNow);
        var fromUtc = ToUtcKind(from ?? toUtc.AddDays(-DefaultWindowDays));

        return new DashboardQueryFilter(scope.HotelId, scope.DepartmentId, fromUtc, toUtc);
    }

    /// <summary>
    /// Npgsql <c>timestamptz</c> parametrelerinde Kind=Utc şart; Local/Unspecified
    /// gelirse "Cannot write DateTime with Kind=..." hatası atar. Bugün filtreler
    /// bellekte uygulandığı için bu hiç ısırmıyor, SQL'e taşınınca ısırır.
    /// </summary>
    private static DateTime ToUtcKind(DateTime value) => value.Kind switch
    {
        DateTimeKind.Utc => value,
        DateTimeKind.Local => value.ToUniversalTime(),
        _ => DateTime.SpecifyKind(value, DateTimeKind.Utc)
    };
}
