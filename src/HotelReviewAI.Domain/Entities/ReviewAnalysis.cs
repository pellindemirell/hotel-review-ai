using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Domain.Entities;

public class ReviewAnalysis : BaseEntity
{
    public Guid ReviewId { get; set; }
    public Review Review { get; set; } = null!;

    public int ClauseIndex { get; set; }
    public string ClauseText { get; set; } = string.Empty;

    public Sentiment Sentiment { get; set; }
    public double SentimentScore { get; set; }
    public Priority Priority { get; set; }

    public Guid? CategoryId { get; set; }
    public ReviewCategory? Category { get; set; }

    public string? Suggestion { get; set; }
    public double Confidence { get; set; }

    public List<string> Keywords { get; set; } = [];
    public string? Summary { get; set; }
}
