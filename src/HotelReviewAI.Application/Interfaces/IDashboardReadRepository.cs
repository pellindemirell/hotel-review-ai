using HotelReviewAI.Application.Queries.Dashboard;

namespace HotelReviewAI.Application.Interfaces;

/// <summary>
/// Dashboard toplamalarını veritabanında yapan okuma deposu.
/// </summary>
/// <remarks>
/// Neden ayrı bir depo: bu sorgular Reviews + ReviewAnalyses + ReviewCategories
/// üzerinden geçtiği için tek bir entity deposuna ait değiller. Önceki hâlinde
/// dört handler da GetAllAsync() ile iki tabloyu baştan sona belleğe çekiyordu —
/// panel dördünü paralel çağırdığı için her yüklemede 4 × (2496 + 14284) satır,
/// üstelik her satırda Keywords jsonb'si ayrıştırılarak. Birkaç KB'lık cevap için.
/// </remarks>
public interface IDashboardReadRepository
{
    /// <summary>Aspect (konu) başına cümle sayıları ve öncelik kırılımı.</summary>
    Task<IReadOnlyList<AspectStatsRow>> GetAspectStatsAsync(
        DashboardQueryFilter filter, CancellationToken cancellationToken = default);

    /// <summary>Konu başına bir örnek olumsuz cümle (satır içi kanıt için).</summary>
    Task<IReadOnlyList<AspectExampleRow>> GetAspectExamplesAsync(
        DashboardQueryFilter filter, CancellationToken cancellationToken = default);

    /// <summary>Bir konunun olumsuz cümleleri — en kötüsü önce.</summary>
    Task<IReadOnlyList<TopicClauseRow>> GetTopicClausesAsync(
        DashboardQueryFilter filter,
        IReadOnlyCollection<string> aspectLabels,
        bool includeNullLabels,
        int take,
        CancellationToken cancellationToken = default);

    /// <summary>Bir konudaki toplam olumsuz cümle sayısı (sayfalama bilgisi için).</summary>
    Task<int> CountTopicClausesAsync(
        DashboardQueryFilter filter,
        IReadOnlyCollection<string> aspectLabels,
        bool includeNullLabels,
        CancellationToken cancellationToken = default);

    /// <summary>Gün bazlı yorum sayısı, puan toplamı ve duygu kırılımı.</summary>
    Task<IReadOnlyList<DailyReviewStatsRow>> GetDailyReviewStatsAsync(
        DashboardQueryFilter filter, CancellationToken cancellationToken = default);

    /// <summary>Kategori başına duygu kırılımı; kategorisi olmayanlar tek grupta.</summary>
    Task<IReadOnlyList<CategoryStatsRow>> GetCategoryStatsAsync(
        DashboardQueryFilter filter, CancellationToken cancellationToken = default);
}
