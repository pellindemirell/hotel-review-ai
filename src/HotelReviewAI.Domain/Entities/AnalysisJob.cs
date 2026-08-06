using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Domain.Entities;

public class AnalysisJob : BaseEntity
{
    public Guid ReviewId { get; set; }
    public AnalysisJobStatus Status { get; set; } = AnalysisJobStatus.Pending;
    public int RetryCount { get; set; } = 0;
    public string? ErrorMessage { get; set; }
    public DateTime? ProcessedAt { get; set; }
}
