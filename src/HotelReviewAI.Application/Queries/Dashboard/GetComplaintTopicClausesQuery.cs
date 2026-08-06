using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Queries.Dashboard;

public record GetComplaintTopicClausesQuery(
    string Topic,
    int Take = 10,
    DateTime? DateFrom = null,
    DateTime? DateTo = null,
    Guid? HotelId = null) : IRequest<ComplaintTopicDetailDto>;

public class ComplaintTopicDetailDto
{
    public string Topic { get; set; } = string.Empty;

    /// <summary>Konudaki toplam olumsuz cümle — "10 / 113 gösteriliyor" için.</summary>
    public int TotalNegativeCount { get; set; }

    public List<ComplaintTopicClauseDto> Clauses { get; set; } = [];
}

public class ComplaintTopicClauseDto
{
    public Guid ReviewId { get; set; }
    public Guid AnalysisId { get; set; }
    public string ClauseText { get; set; } = string.Empty;
    public bool IsTruncated { get; set; }
    public string? Suggestion { get; set; }
    public string Priority { get; set; } = string.Empty;
    public double SentimentScore { get; set; }
    public double Confidence { get; set; }
    public DateTime ReviewDate { get; set; }
    public string? DepartmentLabel { get; set; }
}

public class GetComplaintTopicClausesHandler
    : IRequestHandler<GetComplaintTopicClausesQuery, ComplaintTopicDetailDto>
{
    private const int MaxTake = 50;
    private const int ClauseMaxLength = 600;

    private readonly IDashboardReadRepository _readRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetComplaintTopicClausesHandler(
        IDashboardReadRepository readRepository,
        ICurrentUserService currentUserService)
    {
        _readRepository = readRepository;
        _currentUserService = currentUserService;
    }

    public async Task<ComplaintTopicDetailDto> Handle(
        GetComplaintTopicClausesQuery request, CancellationToken cancellationToken)
    {
        var empty = new ComplaintTopicDetailDto { Topic = request.Topic };

        // Bu uç nokta HAM MİSAFİR METNİ döndürüyor; buradaki bir kapsam kaçağı
        // kozmetik bir hata değil, veri sızıntısıdır.
        var scope = DashboardScope.Resolve(_currentUserService, request.HotelId);
        if (scope.ReturnsNothing || string.IsNullOrWhiteSpace(request.Topic))
            return empty;

        var filter = DashboardQueryFilter.Create(scope, request.DateFrom, request.DateTo);
        var take = Math.Clamp(request.Take, 1, MaxTake);

        var isGeneric = request.Topic == DashboardTopicRules.GenericTopicKey;

        // Genel satır: NULL/boş etiketler ve fallback etiketlerin tamamı.
        var labels = isGeneric
            ? DashboardTopicRules.GenericAspects.ToArray()
            : [request.Topic];

        var total = await _readRepository.CountTopicClausesAsync(
            filter, labels, includeNullLabels: isGeneric, cancellationToken);

        if (total == 0)
            return empty;

        var rows = await _readRepository.GetTopicClausesAsync(
            filter, labels, includeNullLabels: isGeneric, take, cancellationToken);

        return new ComplaintTopicDetailDto
        {
            Topic = isGeneric ? DashboardTopicRules.GenericTopicName : request.Topic,
            TotalNegativeCount = total,
            Clauses = rows.Select(r =>
            {
                var text = (r.ClauseText ?? string.Empty).Trim();
                var truncated = text.Length > ClauseMaxLength;

                return new ComplaintTopicClauseDto
                {
                    ReviewId = r.ReviewId,
                    AnalysisId = r.AnalysisId,
                    // 4500 karaktere kadar çıkabilen serbest metin kart düzenini
                    // patlatır; kesiliyor ve satır tam yoruma link veriyor.
                    ClauseText = truncated ? string.Concat(text.AsSpan(0, ClauseMaxLength - 1), "…") : text,
                    IsTruncated = truncated,
                    Suggestion = string.IsNullOrWhiteSpace(r.Suggestion) ? null : r.Suggestion.Trim(),
                    Priority = r.Priority.ToString(),
                    SentimentScore = Math.Round(r.SentimentScore, 3),
                    Confidence = Math.Round(r.Confidence, 3),
                    ReviewDate = r.ReviewDate,
                    DepartmentLabel = r.DepartmentLabel
                };
            }).ToList()
        };
    }
}
