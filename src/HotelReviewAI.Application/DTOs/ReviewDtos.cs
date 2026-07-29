namespace HotelReviewAI.Application.DTOs;

public class ReviewListItemDto
{
    public Guid Id { get; set; }
    public string GuestName { get; set; } = string.Empty;
    public string Comment { get; set; } = string.Empty;
    public int Rating { get; set; }
    public DateTime ReviewDate { get; set; }
    public string Source { get; set; } = string.Empty;
    public string? PhotoUrl { get; set; }
}

public class ReviewDetailDto : ReviewListItemDto
{
    public string Language { get; set; } = string.Empty;
    public List<ReviewAnalysisDto> Analyses { get; set; } = [];
    public List<ReviewAttachmentDto> Attachments { get; set; } = [];
    public List<ActionItemDto> ActionItems { get; set; } = [];
}

public class ReviewAnalysisDto
{
    public Guid Id { get; set; }
    public int ClauseIndex { get; set; }
    public string ClauseText { get; set; } = string.Empty;
    public string Sentiment { get; set; } = string.Empty;
    public double SentimentScore { get; set; }
    public string Priority { get; set; } = string.Empty;
    public string Summary { get; set; } = string.Empty;
    public Guid? CategoryId { get; set; }
    public string? CategoryName { get; set; }
    public string? Suggestion { get; set; }
    public double Confidence { get; set; }
}

public class ReviewAttachmentDto
{
    public Guid Id { get; set; }
    public string FileUrl { get; set; } = string.Empty;
    public string FileType { get; set; } = string.Empty;
    public string? OcrText { get; set; }
}

public class ActionItemDto
{
    public Guid Id { get; set; }
    public string Title { get; set; } = string.Empty;
    public string Status { get; set; } = string.Empty;
    public DateTime? DueDate { get; set; }
    public Guid? AssignedTo { get; set; }
}
