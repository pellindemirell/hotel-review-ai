using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Queries.Dashboard;

public record GetTrendsQuery(DateTime? DateFrom = null, DateTime? DateTo = null, Guid? HotelId = null)
    : IRequest<TrendsResponseDto>;

public class TrendsResponseDto
{
    public List<DailyTrendPointDto> Points { get; set; } = [];

    /// <summary>Dönemin tamamının ağırlıklı ortalama puanı — özet kartıyla aynı sayı.</summary>
    public double? PeriodAverageRating { get; set; }

    public int TotalReviews { get; set; }
    public double? MinDailyAverage { get; set; }
    public double? MaxDailyAverage { get; set; }

    /// <summary>Gün kovalarının kesildiği zaman dilimi (istemciye bilgi amaçlı).</summary>
    public string TimeZone { get; set; } = DashboardTimeZone.IanaId;
}

public class DailyTrendPointDto
{
    public string Date { get; set; } = string.Empty; // "yyyy-MM-dd", raporlama zaman diliminde

    public int ReviewCount { get; set; }

    /// <summary>
    /// Yorum olmayan günlerde NULL — 0 DEĞİL.
    /// </summary>
    /// <remarks>
    /// Boş günler takvim ekseninde yerini koruyor (x ekseni zamanla orantılı olsun
    /// diye) ama puan serisi null bırakılıyor ki grafik kopukluk çizsin. 0 ile
    /// doldurmak yalan olurdu, önceki değeri taşımak veri uydurmak olurdu.
    /// </remarks>
    public double? AverageRating { get; set; }

    /// <summary>7 günlük, SAYI AĞIRLIKLI hareketli ortalama.</summary>
    public double? MovingAverageRating { get; set; }

    public int PositiveCount { get; set; }
    public int NeutralCount { get; set; }
    public int NegativeCount { get; set; }

    /// <summary>Henüz analiz edilmemiş yorumlar — dördü toplanınca ReviewCount etmeli.</summary>
    public int UnanalyzedCount { get; set; }
}

public class GetTrendsHandler : IRequestHandler<GetTrendsQuery, TrendsResponseDto>
{
    private const int MovingAverageWindowDays = 7;

    private readonly IDashboardReadRepository _readRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetTrendsHandler(
        IDashboardReadRepository readRepository,
        ICurrentUserService currentUserService)
    {
        _readRepository = readRepository;
        _currentUserService = currentUserService;
    }

    public async Task<TrendsResponseDto> Handle(GetTrendsQuery request, CancellationToken cancellationToken)
    {
        var scope = DashboardScope.Resolve(_currentUserService, request.HotelId);
        if (scope.ReturnsNothing)
            return new TrendsResponseDto();

        var filter = DashboardQueryFilter.Create(scope, request.DateFrom, request.DateTo);
        var rows = await _readRepository.GetDailyReviewStatsAsync(filter, cancellationToken);
        var byDay = rows.ToDictionary(r => r.Day);

        // Boş günler SUNUCUDA dolduruluyor: istemcinin zaman dilimi doğru bir gün
        // listesi yeniden kurmasını beklemek gereksiz ve hataya açık.
        var timeZone = TimeZoneInfo.FindSystemTimeZoneById(DashboardTimeZone.IanaId);
        var firstDay = DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(filter.FromUtc, timeZone));
        var lastDay = DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(filter.ToUtc, timeZone));

        var points = new List<DailyTrendPointDto>();
        var ratingSums = new List<int>();
        var reviewCounts = new List<int>();

        for (var day = firstDay; day <= lastDay; day = day.AddDays(1))
        {
            byDay.TryGetValue(day, out var row);

            var count = row?.ReviewCount ?? 0;
            var ratingSum = row?.RatingSum ?? 0;

            ratingSums.Add(ratingSum);
            reviewCounts.Add(count);

            points.Add(new DailyTrendPointDto
            {
                Date = day.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture),
                ReviewCount = count,
                AverageRating = count > 0 ? Math.Round((double)ratingSum / count, 2) : null,
                PositiveCount = row?.PositiveCount ?? 0,
                NeutralCount = row?.NeutralCount ?? 0,
                NegativeCount = row?.NegativeCount ?? 0,
                UnanalyzedCount = row?.UnanalyzedCount ?? 0
            });
        }

        ApplyMovingAverage(points, ratingSums, reviewCounts);

        var totalReviews = reviewCounts.Sum();
        var totalRating = ratingSums.Sum();
        var dailyAverages = points.Where(p => p.AverageRating.HasValue).Select(p => p.AverageRating!.Value).ToList();

        return new TrendsResponseDto
        {
            Points = points,
            TotalReviews = totalReviews,
            PeriodAverageRating = totalReviews > 0 ? Math.Round((double)totalRating / totalReviews, 2) : null,
            MinDailyAverage = dailyAverages.Count > 0 ? dailyAverages.Min() : null,
            MaxDailyAverage = dailyAverages.Count > 0 ? dailyAverages.Max() : null
        };
    }

    /// <summary>
    /// 7 günlük hareketli ortalama — günlük ortalamaların ortalaması DEĞİL,
    /// puan toplamlarının yorum sayılarına bölümü.
    /// </summary>
    /// <remarks>
    /// Ortalamaların ortalaması alınırsa 1 yorumlu bir gün 20 yorumlu bir güne eşit
    /// ağırlık kazanır ve sinyal gibi görünen sahte bir tırtıklılık üretir.
    /// Pencerede hiç yorum yoksa null (grafik spanGaps ile kısa sessizlikleri köprüler).
    /// </remarks>
    private static void ApplyMovingAverage(
        List<DailyTrendPointDto> points, List<int> ratingSums, List<int> reviewCounts)
    {
        for (var i = 0; i < points.Count; i++)
        {
            var start = Math.Max(0, i - (MovingAverageWindowDays - 1));

            var windowRating = 0;
            var windowCount = 0;
            for (var j = start; j <= i; j++)
            {
                windowRating += ratingSums[j];
                windowCount += reviewCounts[j];
            }

            points[i].MovingAverageRating = windowCount > 0
                ? Math.Round((double)windowRating / windowCount, 2)
                : null;
        }
    }
}
