using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using MediatR;

namespace HotelReviewAI.Application.Queries.Dashboard;

public record GetDashboardSummaryQuery(DateTime? DateFrom = null, DateTime? DateTo = null)
    : IRequest<DashboardSummaryDto>;

public class DashboardSummaryDto
{
    public int TotalReviews { get; set; }
    public double AverageRating { get; set; }
    public int OpenActionItems { get; set; }
    public double NegativeRatio { get; set; }
}

public class GetDashboardSummaryHandler : IRequestHandler<GetDashboardSummaryQuery, DashboardSummaryDto>
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IActionItemRepository _actionItemRepository;
    private readonly IReviewAnalysisRepository _reviewAnalysisRepository;

    public GetDashboardSummaryHandler(
        IReviewRepository reviewRepository,
        IActionItemRepository actionItemRepository,
        IReviewAnalysisRepository reviewAnalysisRepository)
    {
        _reviewRepository = reviewRepository;
        _actionItemRepository = actionItemRepository;
        _reviewAnalysisRepository = reviewAnalysisRepository;
    }

    public async Task<DashboardSummaryDto> Handle(GetDashboardSummaryQuery request, CancellationToken cancellationToken)
    {
        var reviews = (await _reviewRepository.GetAllAsync()).ToList();
        var actionItems = (await _actionItemRepository.GetAllAsync()).ToList();
        var analyses = (await _reviewAnalysisRepository.GetAllAsync()).ToList();

        // Tarih filtresi
        if (request.DateFrom.HasValue)
            reviews = reviews.Where(r => r.ReviewDate >= request.DateFrom.Value).ToList();
        if (request.DateTo.HasValue)
            reviews = reviews.Where(r => r.ReviewDate <= request.DateTo.Value).ToList();

        var totalReviews = reviews.Count;
        var avgRating = totalReviews > 0 ? reviews.Average(r => r.Rating) : 0.0;
        var openActions = actionItems.Count(a => a.Status == ActionItemStatus.Open);

        // Filtreli yorum ID'leri üzerinden analiz filtrele
        var reviewIds = reviews.Select(r => r.Id).ToHashSet();
        var filteredAnalyses = analyses.Where(a => reviewIds.Contains(a.ReviewId)).ToList();

        var negativeCount = filteredAnalyses.Count(a => a.Sentiment == Sentiment.Negative);
        var negativeRatio = totalReviews > 0 ? (double)negativeCount / totalReviews * 100 : 0.0;

        return new DashboardSummaryDto
        {
            TotalReviews = totalReviews,
            AverageRating = Math.Round(avgRating, 1),
            OpenActionItems = openActions,
            NegativeRatio = Math.Round(negativeRatio, 1)
        };
    }
}
