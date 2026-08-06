using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using MediatR;

namespace HotelReviewAI.Application.Queries.Dashboard;

public record GetDashboardSummaryQuery(DateTime? DateFrom = null, DateTime? DateTo = null, Guid? HotelId = null)
    : IRequest<DashboardSummaryDto>;

public class DashboardSummaryDto
{
    public int TotalReviews { get; set; }
    public double AverageRating { get; set; }
    public int OpenActionItems { get; set; }
    /// <summary>Olumsuz YORUM oranı (%). 0–100 aralığındadır.</summary>
    public double NegativeRatio { get; set; }
    /// <summary>Oranın payı — panelde "X / Y yorum" olarak gösterilebilsin diye.</summary>
    public int NegativeReviewCount { get; set; }
    /// <summary>Analizi olan yorum sayısı; oranın gerçekte kaç yoruma dayandığını gösterir.</summary>
    public int AnalyzedReviewCount { get; set; }
}

public class GetDashboardSummaryHandler : IRequestHandler<GetDashboardSummaryQuery, DashboardSummaryDto>
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IActionItemRepository _actionItemRepository;
    private readonly IReviewAnalysisRepository _reviewAnalysisRepository;
    private readonly IReviewCategoryRepository _categoryRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetDashboardSummaryHandler(
        IReviewRepository reviewRepository,
        IActionItemRepository actionItemRepository,
        IReviewAnalysisRepository reviewAnalysisRepository,
        IReviewCategoryRepository categoryRepository,
        ICurrentUserService currentUserService)
    {
        _reviewRepository = reviewRepository;
        _actionItemRepository = actionItemRepository;
        _reviewAnalysisRepository = reviewAnalysisRepository;
        _categoryRepository = categoryRepository;
        _currentUserService = currentUserService;
    }

    public async Task<DashboardSummaryDto> Handle(GetDashboardSummaryQuery request, CancellationToken cancellationToken)
    {
        var reviews = (await _reviewRepository.GetAllAsync()).ToList();
        var actionItems = (await _actionItemRepository.GetAllAsync()).ToList();
        var analyses = (await _reviewAnalysisRepository.GetAllAsync()).ToList();

        var scope = DashboardScope.Resolve(_currentUserService, request.HotelId);
        if (scope.ReturnsNothing)
        {
            return new DashboardSummaryDto();
        }

        if (scope.HotelId.HasValue)
        {
            reviews = reviews.Where(r => r.HotelId == scope.HotelId.Value).ToList();
        }

        // Tarih filtresi
        if (request.DateFrom.HasValue)
            reviews = reviews.Where(r => r.ReviewDate >= request.DateFrom.Value).ToList();
        if (request.DateTo.HasValue)
            reviews = reviews.Where(r => r.ReviewDate <= request.DateTo.Value).ToList();

        var reviewIds = reviews.Select(r => r.Id).ToHashSet();
        var filteredAnalyses = analyses.Where(a => reviewIds.Contains(a.ReviewId)).ToList();

        // DepartmentManager için yorumlar da kendi departmanına daraltılır.
        // Önceden yalnızca aksiyonlar daraltılıyordu; departman müdürü "otelin tüm
        // yorumları + kendi departmanının aksiyonları" karışımı bir ekran görüyordu.
        if (scope.DepartmentId.HasValue)
        {
            // Category navigation'ı GetAllAsync ile yüklenmiyor; departman kategoriler
            // üzerinden ayrı bir harita ile çözülüyor.
            var deptCategoryIds = (await _categoryRepository.GetAllAsync())
                .Where(c => c.DepartmentId == scope.DepartmentId.Value)
                .Select(c => c.Id)
                .ToHashSet();

            var deptReviewIds = filteredAnalyses
                .Where(a => a.CategoryId.HasValue && deptCategoryIds.Contains(a.CategoryId.Value))
                .Select(a => a.ReviewId)
                .ToHashSet();

            reviews = reviews.Where(r => deptReviewIds.Contains(r.Id)).ToList();
            reviewIds = deptReviewIds;
            filteredAnalyses = filteredAnalyses.Where(a => deptReviewIds.Contains(a.ReviewId)).ToList();
        }

        // Aksiyonlar da aynı yorum kümesine bağlanır: hem otel/departman hem de
        // TARİH kapsamı artık diğer kartlarla aynı. Önceden tarih filtresi hiç
        // uygulanmadığı için "Son 7 Gün"e basınca bu kart tek başına sabit kalıyordu.
        // Eşleştirme Aksiyonlar ekranıyla aynı ölçütü kullanır (ActionItemRepository):
        // ActionItem.HotelId null olan eski kayıtlar da yorum üzerinden yakalanır.
        actionItems = actionItems.Where(a => reviewIds.Contains(a.ReviewId)).ToList();

        if (scope.DepartmentId.HasValue)
        {
            actionItems = actionItems.Where(a => a.DepartmentId == scope.DepartmentId.Value).ToList();
        }

        var totalReviews = reviews.Count;
        var avgRating = totalReviews > 0 ? reviews.Average(r => r.Rating) : 0.0;
        var openActions = actionItems.Count(a =>
          a.Status == ActionItemStatus.Open || a.Status == ActionItemStatus.InProgress);

        // Negatif oran YORUM bazlı: pay ve payda aynı birimde olmalı.
        // Önceden pay clause sayısıydı (1 yorum → N clause) ve oran %100'ü aşıyordu
        // (gerçek veride %127.6 görüldü). Yorumun olumsuzluğu, Yorumlar ekranıyla
        // aynı kuralla belirlenir: clause skorlarının ortalaması + SentimentThresholds.
        var negativeReviewCount = filteredAnalyses
            .GroupBy(a => a.ReviewId)
            .Count(g => SentimentThresholds.FromAverageScore(g.Average(a => a.SentimentScore))
                        == Sentiment.Negative);

        var negativeRatio = totalReviews > 0 ? (double)negativeReviewCount / totalReviews * 100 : 0.0;

        return new DashboardSummaryDto
        {
            TotalReviews = totalReviews,
            AverageRating = Math.Round(avgRating, 1),
            OpenActionItems = openActions,
            NegativeRatio = Math.Round(negativeRatio, 1),
            NegativeReviewCount = negativeReviewCount,
            AnalyzedReviewCount = reviewIds.Count == 0 ? 0 : filteredAnalyses.Select(a => a.ReviewId).Distinct().Count()
        };
    }
}
