using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Application.Queries.Dashboard;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

/// <summary>
/// Dashboard toplamalarını veritabanında yapan okuma deposu.
/// </summary>
/// <remarks>
/// Notlar:
///  - Global "IsActive == true" query filter'ı (AppDbContext.OnModelCreating) hem
///    kök setlere hem navigasyonlara uygulanıyor; burada elle tekrar yazılmıyor.
///  - Projeksiyona düşen sorgular EF tarafından zaten takip edilmiyor, ayrıca
///    AsNoTracking gerekmiyor.
///  - Opsiyonel HotelId filtresi "|| == null" yerine if ile kuruluyor: o form
///    sargable olmayan bir OR üretip IX_Reviews_HotelId_ReviewDate indeksini
///    kullanılamaz hâle getirir.
/// </remarks>
public class DashboardReadRepository : IDashboardReadRepository
{
    private readonly AppDbContext _dbContext;

    public DashboardReadRepository(AppDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    /// <summary>
    /// Filtre kapsamındaki analiz (cümle) satırları.
    /// </summary>
    /// <remarks>
    /// Departman kısıtı CÜMLE seviyesinde uygulanıyor (diğer dashboard sorguları
    /// yorum seviyesinde uyguluyor). Bilinçli: konu listesi cümle seviyesinde bir
    /// çıktı; Kat Hizmetleri müdürü, bir yorum ikisinden de bahsetti diye "Havuz"u
    /// kendi şikayeti olarak görmemeli. Bedeli, CategoryId'si olmayan cümlelerin
    /// departman müdürlerine görünmemesi.
    /// </remarks>
    private IQueryable<ReviewAnalysis> ScopedAnalyses(DashboardQueryFilter filter)
    {
        var query = _dbContext.ReviewAnalyses
            .Where(a => a.Review.ReviewDate >= filter.FromUtc && a.Review.ReviewDate <= filter.ToUtc);

        if (filter.HotelId is { } hotelId)
        {
            query = query.Where(a => a.Review.HotelId == hotelId);
        }

        if (filter.DepartmentId is { } departmentId)
        {
            query = query.Where(a => a.Category != null && a.Category.DepartmentId == departmentId);
        }

        return query;
    }

    private IQueryable<Review> ScopedReviews(DashboardQueryFilter filter)
    {
        var query = _dbContext.Reviews
            .Where(r => r.ReviewDate >= filter.FromUtc && r.ReviewDate <= filter.ToUtc);

        if (filter.HotelId is { } hotelId)
        {
            query = query.Where(r => r.HotelId == hotelId);
        }

        if (filter.DepartmentId is { } departmentId)
        {
            query = query.Where(r => r.Analyses.Any(a => a.Category != null && a.Category.DepartmentId == departmentId));
        }

        return query;
    }

    public async Task<IReadOnlyList<AspectStatsRow>> GetAspectStatsAsync(
        DashboardQueryFilter filter, CancellationToken cancellationToken = default)
    {
        // AspectLabel + DepartmentLabel üzerinden gruplanıyor; ~60 satır dönüyor,
        // departman etiketinin en sık görüleni handler'da C#'ta seçiliyor.
        // Koşullu sayımlarda Count(predicate) yerine Sum(... ? 1 : 0): düz bir
        // SUM(CASE WHEN ...) üretir ve EF sürüm riski taşımaz.
        var rows = await ScopedAnalyses(filter)
            .GroupBy(a => new { a.AspectLabel, a.DepartmentLabel })
            .Select(g => new AspectStatsRow
            {
                AspectLabel = g.Key.AspectLabel,
                DepartmentLabel = g.Key.DepartmentLabel,
                TotalCount = g.Count(),
                NegativeCount = g.Sum(a => a.Sentiment == Sentiment.Negative ? 1 : 0),
                CriticalCount = g.Sum(a => a.Sentiment == Sentiment.Negative && a.Priority == Priority.Critical ? 1 : 0),
                HighCount = g.Sum(a => a.Sentiment == Sentiment.Negative && a.Priority == Priority.High ? 1 : 0),
                MediumCount = g.Sum(a => a.Sentiment == Sentiment.Negative && a.Priority == Priority.Medium ? 1 : 0),
                InfoCount = g.Sum(a => a.Sentiment == Sentiment.Negative && a.Priority == Priority.Info ? 1 : 0)
            })
            .ToListAsync(cancellationToken);

        return rows;
    }

    public async Task<IReadOnlyList<AspectExampleRow>> GetAspectExamplesAsync(
        DashboardQueryFilter filter, CancellationToken cancellationToken = default)
    {
        // Konu başına EN KÖTÜ olumsuz cümle: satır içi kanıt olarak gösteriliyor,
        // böylece kullanıcı satırı açmadan da ne olduğunu görüyor.
        var rows = await ScopedAnalyses(filter)
            .Where(a => a.Sentiment == Sentiment.Negative && a.ClauseText != "")
            .GroupBy(a => a.AspectLabel)
            .Select(g => new AspectExampleRow
            {
                AspectLabel = g.Key,
                ClauseText = g.OrderByDescending(a => a.Priority)
                              .ThenBy(a => a.SentimentScore)
                              .Select(a => a.ClauseText)
                              .First()
            })
            .ToListAsync(cancellationToken);

        return rows;
    }

    private IQueryable<ReviewAnalysis> TopicClauses(
        DashboardQueryFilter filter, IReadOnlyCollection<string> aspectLabels, bool includeNullLabels)
    {
        var query = ScopedAnalyses(filter).Where(a => a.Sentiment == Sentiment.Negative);

        var labels = aspectLabels.ToList();

        // includeNullLabels: birleştirilmiş "Genel" satırı NULL ve boş etiketleri de kapsar.
        return includeNullLabels
            ? query.Where(a => a.AspectLabel == null || a.AspectLabel == "" || labels.Contains(a.AspectLabel))
            : query.Where(a => a.AspectLabel != null && labels.Contains(a.AspectLabel));
    }

    public async Task<IReadOnlyList<TopicClauseRow>> GetTopicClausesAsync(
        DashboardQueryFilter filter,
        IReadOnlyCollection<string> aspectLabels,
        bool includeNullLabels,
        int take,
        CancellationToken cancellationToken = default)
    {
        var rows = await TopicClauses(filter, aspectLabels, includeNullLabels)
            // En kötüsü önce: yüksek öncelik, sonra en olumsuz skor, sonra en yeni.
            .OrderByDescending(a => a.Priority)
            .ThenBy(a => a.SentimentScore)
            .ThenByDescending(a => a.Review.ReviewDate)
            .Take(take)
            .Select(a => new TopicClauseRow
            {
                ReviewId = a.ReviewId,
                AnalysisId = a.Id,
                ClauseText = a.ClauseText,
                Suggestion = a.Suggestion,
                Priority = a.Priority,
                SentimentScore = a.SentimentScore,
                Confidence = a.Confidence,
                ReviewDate = a.Review.ReviewDate,
                DepartmentLabel = a.DepartmentLabel
            })
            .ToListAsync(cancellationToken);

        return rows;
    }

    public Task<int> CountTopicClausesAsync(
        DashboardQueryFilter filter,
        IReadOnlyCollection<string> aspectLabels,
        bool includeNullLabels,
        CancellationToken cancellationToken = default)
        => TopicClauses(filter, aspectLabels, includeNullLabels).CountAsync(cancellationToken);

    public async Task<IReadOnlyList<DailyReviewStatsRow>> GetDailyReviewStatsAsync(
        DashboardQueryFilter filter, CancellationToken cancellationToken = default)
    {
        // Yorum bazlı duygu, cümle skorlarının ortalamasından türetiliyor —
        // SentimentThresholds ile birebir aynı eşikler ve KATI karşılaştırmalar.
        // Rating'den türetmek aynı ekranda üçüncü bir "olumsuz yorum" tanımı
        // yaratırdı; KPI kartı bir şey, çubuklar başka şey söylerdi.
        //
        // Analizi olmayan yorumlarda Average() SQL NULL döner; (double?) cast'i
        // olmadan materyalizasyon patlar. UnanalyzedCount kovası tam da bunun için.
        var perReview = ScopedReviews(filter)
            .Select(r => new
            {
                Day = DateOnly.FromDateTime(
                    TimeZoneInfo.ConvertTimeBySystemTimeZoneId(r.ReviewDate, DashboardTimeZone.IanaId)),
                r.Rating,
                AvgScore = (double?)r.Analyses.Average(a => a.SentimentScore)
            });

        var rows = await perReview
            .GroupBy(x => x.Day)
            .Select(g => new DailyReviewStatsRow
            {
                Day = g.Key,
                ReviewCount = g.Count(),
                RatingSum = g.Sum(x => x.Rating),
                PositiveCount = g.Sum(x => x.AvgScore != null && x.AvgScore > SentimentThresholds.Positive ? 1 : 0),
                NegativeCount = g.Sum(x => x.AvgScore != null && x.AvgScore < SentimentThresholds.Negative ? 1 : 0),
                NeutralCount = g.Sum(x => x.AvgScore != null
                                          && x.AvgScore >= SentimentThresholds.Negative
                                          && x.AvgScore <= SentimentThresholds.Positive ? 1 : 0),
                UnanalyzedCount = g.Sum(x => x.AvgScore == null ? 1 : 0)
            })
            .ToListAsync(cancellationToken);

        return rows;
    }

    public async Task<IReadOnlyList<CategoryStatsRow>> GetCategoryStatsAsync(
        DashboardQueryFilter filter, CancellationToken cancellationToken = default)
    {
        // Kategori ADINA göre tek gruplama; kategorisi olmayanlar null grubunda.
        //
        // Kimliğe göre gruplamak YANLIŞ olurdu: ReviewCategories otel başına ayrı
        // satırlar tutuyor (kategori -> departman -> otel zinciri), yani grup
        // genelinde bakıldığında "Genel Atmosfer" 5 farklı kimlikle 5 ayrı çubuk
        // olarak çiziliyordu. Tek otel seçiliyken zaten yalnızca o otelin
        // kategorilerinde cümle olduğu için ada göre gruplama fark yaratmıyor.
        //
        // Önceki hâli ayrıca kategori başına tüm analizleri tarıyordu
        // (45 × 14284 ≈ 640 bin karşılaştırma) ve sınıflandırılamayan sayısını
        // AYRI bir taramayla hesapladığı için ana döngüyle çelişebiliyordu.
        var rows = await ScopedAnalyses(filter)
            .GroupBy(a => a.Category != null ? a.Category.Name : null)
            .Select(g => new CategoryStatsRow
            {
                CategoryName = g.Key,
                PositiveCount = g.Sum(a => a.Sentiment == Sentiment.Positive ? 1 : 0),
                NeutralCount = g.Sum(a => a.Sentiment == Sentiment.Neutral ? 1 : 0),
                NegativeCount = g.Sum(a => a.Sentiment == Sentiment.Negative ? 1 : 0)
            })
            .ToListAsync(cancellationToken);

        return rows;
    }
}
