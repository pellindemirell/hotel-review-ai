using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using MediatR;

namespace HotelReviewAI.Application.Queries.Dashboard;

public record GetTopKeywordsQuery(int TopN = 10, DateTime? DateFrom = null, DateTime? DateTo = null, Guid? HotelId = null)
    : IRequest<List<KeywordFrequencyDto>>;

public class KeywordFrequencyDto
{
    public string Keyword { get; set; } = string.Empty;
    public int Count { get; set; }
}

public class GetTopKeywordsHandler : IRequestHandler<GetTopKeywordsQuery, List<KeywordFrequencyDto>>
{
    private readonly IReviewAnalysisRepository _analysisRepository;
    private readonly IReviewRepository _reviewRepository;

    public GetTopKeywordsHandler(
        IReviewAnalysisRepository analysisRepository,
        IReviewRepository reviewRepository)
    {
        _analysisRepository = analysisRepository;
        _reviewRepository = reviewRepository;
    }

    public async Task<List<KeywordFrequencyDto>> Handle(GetTopKeywordsQuery request, CancellationToken cancellationToken)
    {
        var reviews = (await _reviewRepository.GetAllAsync()).ToList();
        var allAnalyses = (await _analysisRepository.GetAllAsync()).ToList();

        // Hotel & Tarih filtresi Yorumlar üzerinden uygulanır
        if (request.HotelId.HasValue)
            reviews = reviews.Where(r => r.HotelId == request.HotelId.Value).ToList();
        if (request.DateFrom.HasValue)
            reviews = reviews.Where(r => r.ReviewDate >= request.DateFrom.Value).ToList();
        if (request.DateTo.HasValue)
            reviews = reviews.Where(r => r.ReviewDate <= request.DateTo.Value).ToList();

        var reviewIds = reviews.Select(r => r.Id).ToHashSet();
        var filteredAnalyses = allAnalyses.Where(a => reviewIds.Contains(a.ReviewId));

        // Yalnızca negatif analizleri al
        var negativeAnalyses = filteredAnalyses.Where(a => a.Sentiment == Sentiment.Negative);

        // Tüm keyword listelerini düz listeye çevir ve frekans hesapla
        var keywords = negativeAnalyses
            .Where(a => a.Keywords != null)
            .SelectMany(a => a.Keywords)
            .Where(k => !string.IsNullOrWhiteSpace(k))
            .GroupBy(k => k.ToLower().Trim())
            .OrderByDescending(g => g.Count())
            .Take(request.TopN)
            .Select(g => new KeywordFrequencyDto
            {
                Keyword = g.Key,
                Count = g.Count()
            })
            .ToList();

        return keywords;
    }
}
