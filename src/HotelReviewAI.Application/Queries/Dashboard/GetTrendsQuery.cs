using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Queries.Dashboard;

public record GetTrendsQuery(DateTime? DateFrom = null, DateTime? DateTo = null, Guid? HotelId = null) : IRequest<List<DailyRatingTrendDto>>;

public class DailyRatingTrendDto
{
    public string Date { get; set; } = string.Empty; // "YYYY-MM-DD"
    public double AverageRating { get; set; }
    public int ReviewCount { get; set; }
}

public class GetTrendsHandler : IRequestHandler<GetTrendsQuery, List<DailyRatingTrendDto>>
{
    private readonly IReviewRepository _reviewRepository;

    public GetTrendsHandler(IReviewRepository reviewRepository)
    {
        _reviewRepository = reviewRepository;
    }

    public async Task<List<DailyRatingTrendDto>> Handle(GetTrendsQuery request, CancellationToken cancellationToken)
    {
        var all = (await _reviewRepository.GetAllAsync()).ToList();

        if (request.HotelId.HasValue)
            all = all.Where(r => r.HotelId == request.HotelId.Value).ToList();

        // Tarih filtresi uygula
        var from = request.DateFrom ?? DateTime.UtcNow.AddDays(-30);
        var to = request.DateTo ?? DateTime.UtcNow;

        var filtered = all
            .Where(r => r.ReviewDate >= from && r.ReviewDate <= to)
            .ToList();

        // Gün bazlı gruplama
        var trend = filtered
            .GroupBy(r => r.ReviewDate.Date)
            .OrderBy(g => g.Key)
            .Select(g => new DailyRatingTrendDto
            {
                Date = g.Key.ToString("yyyy-MM-dd"),
                AverageRating = Math.Round(g.Average(r => r.Rating), 2),
                ReviewCount = g.Count()
            })
            .ToList();

        return trend;
    }
}
