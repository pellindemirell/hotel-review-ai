namespace HotelReviewAI.Domain.Entities;

public class ReviewAttachment : BaseEntity
{
    public Guid ReviewId { get; set; }
    public Review Review { get; set; } = null!;

    public string FileUrl { get; set; } = string.Empty;
    public string FileType { get; set; } = string.Empty;
    public string? OcrText { get; set; }
}
