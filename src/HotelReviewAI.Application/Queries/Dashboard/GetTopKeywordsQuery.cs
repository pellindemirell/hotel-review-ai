using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using MediatR;

namespace HotelReviewAI.Application.Queries.Dashboard;

public record GetTopKeywordsQuery(int TopN = 10, DateTime? DateFrom = null, DateTime? DateTo = null)
    : IRequest<List<KeywordFrequencyDto>>;

public class KeywordFrequencyDto
{
    public string Keyword { get; set; } = string.Empty;
    public int Count { get; set; }
}

public class GetTopKeywordsHandler : IRequestHandler<GetTopKeywordsQuery, List<KeywordFrequencyDto>>
{
    private readonly IReviewAnalysisRepository _analysisRepository;

    public GetTopKeywordsHandler(IReviewAnalysisRepository analysisRepository)
    {
        _analysisRepository = analysisRepository;
    }

    public async Task<List<KeywordFrequencyDto>> Handle(GetTopKeywordsQuery request, CancellationToken cancellationToken)
    {
        var all = (await _analysisRepository.GetAllAsync()).ToList();

        // Yalnızca negatif analizleri al
        var negativeAnalyses = all.Where(a => a.Sentiment == Sentiment.Negative);

        // Tarih filtresi (ReviewDate üzerinde değil, CreatedAt üzerinden)
        if (request.DateFrom.HasValue)
            negativeAnalyses = negativeAnalyses.Where(a => a.CreatedAt >= request.DateFrom.Value);
        if (request.DateTo.HasValue)
            negativeAnalyses = negativeAnalyses.Where(a => a.CreatedAt <= request.DateTo.Value);

        // Tüm keyword listelerini düz listeye çevir ve frekans hesapla
        var keywords = negativeAnalyses
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
