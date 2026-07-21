using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Domain.Exceptions;

namespace HotelReviewAI.Domain.Entities;

public class Review : BaseEntity
{
    public ReviewSource Source { get; private set; }
    public string GuestName { get; private set; } = string.Empty;
    public string Comment { get; private set; } = string.Empty;
    public string Language { get; private set; } = string.Empty;
    public int Rating { get; private set; }
    public DateTime ReviewDate { get; private set; }
    public Guid? CreatedBy { get; private set; }

    public ICollection<ReviewAnalysis> Analyses { get; set; } = [];
    public ICollection<ReviewAttachment> Attachments { get; set; } = [];
    public ICollection<ActionItem> ActionItems { get; set; } = [];

    private Review()
    {
    }

    public static Review Create(
        string guestName,
        string comment,
        int rating,
        string language,
        ReviewSource source,
        DateTime reviewDate,
        Guid? createdBy)
    {
        if (string.IsNullOrWhiteSpace(comment) || comment.Length < 10)
        {
            throw new DomainException("Yorum en az 10 karakter olmalıdır.");
        }

        if (rating < 1 || rating > 5)
        {
            throw new DomainException("Rating 1-5 aralığında olmalıdır.");
        }

        return new Review
        {
            GuestName = guestName,
            Comment = comment,
            Rating = rating,
            Language = language,
            Source = source,
            ReviewDate = reviewDate,
            CreatedBy = createdBy
        };
    }
}
