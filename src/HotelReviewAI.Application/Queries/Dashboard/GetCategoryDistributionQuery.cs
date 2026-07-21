using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Queries.Dashboard;

public record GetCategoryDistributionQuery(DateTime? DateFrom = null, DateTime? DateTo = null)
    : IRequest<List<CategoryDistributionDto>>;

public class CategoryDistributionDto
{
    public string CategoryName { get; set; } = string.Empty;
    public int ReviewCount { get; set; }
    public double NegativeRatio { get; set; }
}

public class GetCategoryDistributionHandler : IRequestHandler<GetCategoryDistributionQuery, List<CategoryDistributionDto>>
{
    private readonly IReviewCategoryRepository _categoryRepository;
    private readonly IReviewAnalysisRepository _analysisRepository;

    public GetCategoryDistributionHandler(
        IReviewCategoryRepository categoryRepository,
        IReviewAnalysisRepository analysisRepository)
    {
        _categoryRepository = categoryRepository;
        _analysisRepository = analysisRepository;
    }

    public async Task<List<CategoryDistributionDto>> Handle(GetCategoryDistributionQuery request, CancellationToken cancellationToken)
    {
        var categories = (await _categoryRepository.GetAllAsync()).ToList();
        var analyses = (await _analysisRepository.GetAllAsync()).ToList();

        // Tarih filtresi
        if (request.DateFrom.HasValue)
            analyses = analyses.Where(a => a.CreatedAt >= request.DateFrom.Value).ToList();
        if (request.DateTo.HasValue)
            analyses = analyses.Where(a => a.CreatedAt <= request.DateTo.Value).ToList();

        var distribution = categories.Select(c =>
        {
            var catAnalyses = analyses.Where(a => a.CategoryId == c.Id).ToList();
            var negCount = catAnalyses.Count(a => a.Sentiment == Domain.Enums.Sentiment.Negative);
            var total = catAnalyses.Count;

            return new CategoryDistributionDto
            {
                CategoryName = c.Name,
                ReviewCount = total,
                NegativeRatio = total > 0 ? Math.Round((double)negCount / total * 100, 1) : 0
            };
        })
        .OrderByDescending(x => x.ReviewCount)
        .ToList();

        return distribution;
    }
}
