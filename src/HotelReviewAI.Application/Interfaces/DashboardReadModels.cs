using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Application.Interfaces;

/// <summary>
/// Dashboard okuma sorgularının veritabanından döndürdüğü ham satırlar.
/// Bunlar DTO değil — handler'lar bunları şekillendirip DTO üretir.
/// </summary>
public class AspectStatsRow
{
    public string? AspectLabel { get; set; }
    public string? DepartmentLabel { get; set; }
    public int TotalCount { get; set; }
    public int NegativeCount { get; set; }
    public int CriticalCount { get; set; }
    public int HighCount { get; set; }
    public int MediumCount { get; set; }
    public int InfoCount { get; set; }
}

public class AspectExampleRow
{
    public string? AspectLabel { get; set; }
    public string ClauseText { get; set; } = string.Empty;
}

public class TopicClauseRow
{
    public Guid ReviewId { get; set; }
    public Guid AnalysisId { get; set; }
    public string ClauseText { get; set; } = string.Empty;
    public string? Suggestion { get; set; }
    public Priority Priority { get; set; }
    public double SentimentScore { get; set; }
    public double Confidence { get; set; }
    public DateTime ReviewDate { get; set; }
    public string? DepartmentLabel { get; set; }
}

public class DailyReviewStatsRow
{
    public DateOnly Day { get; set; }
    public int ReviewCount { get; set; }
    public int RatingSum { get; set; }
    public int PositiveCount { get; set; }
    public int NeutralCount { get; set; }
    public int NegativeCount { get; set; }
    public int UnanalyzedCount { get; set; }
}

public class CategoryStatsRow
{
    /// <summary>Kategori ADI; kategorisi çözülemeyen cümleler için null.</summary>
    /// <remarks>
    /// Kimliğe göre değil ADA göre gruplanıyor: ReviewCategories otel başına ayrı
    /// satırlar tutuyor (her otelin kendi 46 kategorisi var), dolayısıyla grup
    /// genelinde bakıldığında "Genel Atmosfer" 5 ayrı kimlikle 5 kez geliyordu.
    /// </remarks>
    public string? CategoryName { get; set; }
    public int PositiveCount { get; set; }
    public int NeutralCount { get; set; }
    public int NegativeCount { get; set; }
}
