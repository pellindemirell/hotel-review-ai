namespace HotelReviewAI.Application.DTOs;

/// <summary>
/// FastAPI /analyze-review endpoint'inden dönen analiz sonucunu taşır.
/// </summary>
public class AiAnalysisResult
{
    public string Sentiment { get; set; } = string.Empty;
    public double SentimentScore { get; set; }
    public string? Category { get; set; }
    public List<string> Keywords { get; set; } = [];
    public string Summary { get; set; } = string.Empty;
    public string Suggestion { get; set; } = string.Empty;
    public double Confidence { get; set; }
    public List<AiAbsaAspect> AbsaAspects { get; set; } = [];
}

public class AiAbsaAspect
{
    public string Clause { get; set; } = string.Empty;
    public string Department { get; set; } = string.Empty;
    public string Sentiment { get; set; } = string.Empty;
    public double SentimentScore { get; set; }
    public string Priority { get; set; } = string.Empty;
    public string Suggestion { get; set; } = string.Empty;
}
