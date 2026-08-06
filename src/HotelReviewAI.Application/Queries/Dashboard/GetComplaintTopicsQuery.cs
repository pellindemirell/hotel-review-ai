using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Queries.Dashboard;

public record GetComplaintTopicsQuery(
    int TopN = 8,
    DateTime? DateFrom = null,
    DateTime? DateTo = null,
    Guid? HotelId = null) : IRequest<List<ComplaintTopicDto>>;

public class ComplaintTopicDto
{
    /// <summary>Görünen konu adı (AspectLabel veya birleştirilmiş genel satır).</summary>
    public string Topic { get; set; } = string.Empty;

    /// <summary>Drill-down çağrısında kullanılacak anahtar; genel satır için "__generic__".</summary>
    public string TopicKey { get; set; } = string.Empty;

    /// <summary>Bilgilendirme amaçlı; AI üretimi serbest metin, kapsam filtresi olarak KULLANILMAZ.</summary>
    public string? DepartmentLabel { get; set; }

    /// <summary>Bu konuya ait olumsuz cümle sayısı.</summary>
    public int NegativeCount { get; set; }

    /// <summary>Bu konuya ait TÜM cümleler — oranın paydası.</summary>
    public int TotalCount { get; set; }

    /// <summary>Konu içindeki olumsuzluk yüzdesi (0-100).</summary>
    public double NegativeRatio { get; set; }

    public string TopPriority { get; set; } = string.Empty;
    public int CriticalCount { get; set; }
    public int HighCount { get; set; }
    public int MediumCount { get; set; }
    public int InfoCount { get; set; }

    /// <summary>Satır içi kanıt — sunucuda kısaltılmış tek bir olumsuz cümle.</summary>
    public string? ExampleClause { get; set; }

    /// <summary>Birleştirilmiş genel/sınıflandırılamayan satır.</summary>
    public bool IsGeneric { get; set; }
}

public class GetComplaintTopicsHandler : IRequestHandler<GetComplaintTopicsQuery, List<ComplaintTopicDto>>
{
    private const int ExampleClauseMaxLength = 160;

    private readonly IDashboardReadRepository _readRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetComplaintTopicsHandler(
        IDashboardReadRepository readRepository,
        ICurrentUserService currentUserService)
    {
        _readRepository = readRepository;
        _currentUserService = currentUserService;
    }

    public async Task<List<ComplaintTopicDto>> Handle(GetComplaintTopicsQuery request, CancellationToken cancellationToken)
    {
        var scope = DashboardScope.Resolve(_currentUserService, request.HotelId);
        if (scope.ReturnsNothing)
            return [];

        var filter = DashboardQueryFilter.Create(scope, request.DateFrom, request.DateTo);

        var stats = await _readRepository.GetAspectStatsAsync(filter, cancellationToken);
        var examples = await _readRepository.GetAspectExamplesAsync(filter, cancellationToken);

        var exampleByAspect = examples
            .GroupBy(e => e.AspectLabel ?? string.Empty)
            .ToDictionary(g => g.Key, g => g.First().ClauseText);

        // 1) Etiketleri katla. SIRA ÖNEMLİ: katlama topN'DEN ÖNCE yapılmalı.
        //    Aksi hâlde "Genel Atmosfer" (canlı veride 504 olumsuz cümle) ilk sırayı
        //    kapıp asıl şikayeti gizler — kaçınılmak istenen sonuç tam da bu.
        var grouped = stats
            .GroupBy(s => DashboardTopicRules.IsGeneric(s.AspectLabel)
                ? DashboardTopicRules.GenericTopicName
                : s.AspectLabel!)
            .Select(g => BuildTopic(g.Key, g.ToList(), exampleByAspect))
            .Where(t => t.NegativeCount > 0)
            .ToList();

        // 2) Genel OLMAYAN satırları sırala ve topN al.
        //    Hacme göre sıralanıyor, orana göre değil: 2 cümlesi olup ikisi de olumsuz
        //    olan bir konu %100 alıp 113 şikayetli "Yemek Kalitesi"ni geçerdi.
        var topics = grouped
            .Where(t => !t.IsGeneric)
            .OrderByDescending(t => t.NegativeCount)
            .ThenByDescending(t => t.NegativeRatio)
            .ThenBy(t => t.Topic, StringComparer.Ordinal)
            .Take(Math.Max(1, request.TopN))
            .ToList();

        // 3) Genel satır her zaman EN SONA, topN dışında.
        var generic = grouped.FirstOrDefault(t => t.IsGeneric);
        if (generic != null)
        {
            topics.Add(generic);
        }

        return topics;
    }

    private static ComplaintTopicDto BuildTopic(
        string topicName,
        List<AspectStatsRow> rows,
        IReadOnlyDictionary<string, string> exampleByAspect)
    {
        var isGeneric = topicName == DashboardTopicRules.GenericTopicName;

        var negativeCount = rows.Sum(r => r.NegativeCount);
        var totalCount = rows.Sum(r => r.TotalCount);

        var critical = rows.Sum(r => r.CriticalCount);
        var high = rows.Sum(r => r.HighCount);
        var medium = rows.Sum(r => r.MediumCount);
        var info = rows.Sum(r => r.InfoCount);

        // Priority'nin int sırası şiddet sırasıyla aynı olduğu için "en yüksek dolu
        // seviye" doğru sonucu verir (Info=0 < Medium=1 < High=2 < Critical=3).
        // DİKKAT: Sentiment için bu geçerli DEĞİL (Positive=0, Negative=1, Neutral=2).
        var topPriority = critical > 0 ? "Critical"
            : high > 0 ? "High"
            : medium > 0 ? "Medium"
            : "Info";

        // Departman etiketi: bu konudaki olumsuz cümlelerde en sık görülen.
        var departmentLabel = rows
            .Where(r => !string.IsNullOrWhiteSpace(r.DepartmentLabel) && r.NegativeCount > 0)
            .OrderByDescending(r => r.NegativeCount)
            .Select(r => r.DepartmentLabel)
            .FirstOrDefault();

        var example = rows
            .Where(r => r.NegativeCount > 0)
            .OrderByDescending(r => r.NegativeCount)
            .Select(r => exampleByAspect.GetValueOrDefault(r.AspectLabel ?? string.Empty))
            .FirstOrDefault(text => !string.IsNullOrWhiteSpace(text));

        return new ComplaintTopicDto
        {
            Topic = topicName,
            TopicKey = isGeneric ? DashboardTopicRules.GenericTopicKey : topicName,
            DepartmentLabel = isGeneric ? null : departmentLabel,
            NegativeCount = negativeCount,
            TotalCount = totalCount,
            NegativeRatio = totalCount > 0 ? Math.Round((double)negativeCount / totalCount * 100, 1) : 0,
            TopPriority = topPriority,
            CriticalCount = critical,
            HighCount = high,
            MediumCount = medium,
            InfoCount = info,
            ExampleClause = Truncate(example, ExampleClauseMaxLength),
            IsGeneric = isGeneric
        };
    }

    private static string? Truncate(string? text, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(text))
            return null;

        var trimmed = text.Trim();
        return trimmed.Length <= maxLength
            ? trimmed
            : string.Concat(trimmed.AsSpan(0, maxLength - 1), "…");
    }
}
