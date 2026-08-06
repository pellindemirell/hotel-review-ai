using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Domain.Exceptions;

namespace HotelReviewAI.Domain.Entities;

public class Review : BaseEntity
{
    public ReviewSource Source { get; private set; }
    public string GuestName { get; private set; } = string.Empty;
    public string Comment { get; private set; } = string.Empty;
    public string Language { get; private set; } = string.Empty;

    /// <summary>
    /// Yorumun Türkçe çevirisi; ilk kez istendiğinde doldurulur.
    /// </summary>
    /// <remarks>
    /// Kalıcı saklanıyor çünkü çeviri translate.google.com'un kimliksiz
    /// scrape'iyle yapılıyor; her tıklamada yeniden çevirmek hem yavaş hem de
    /// rate-limit riski. Böylece her yorum ömründe en fazla bir kez çevriliyor.
    /// </remarks>
    public string? CommentTranslated { get; private set; }

    /// <summary>Çevirinin ne zaman yapıldığı (boşsa hiç çevrilmemiş).</summary>
    public DateTime? TranslatedAt { get; private set; }

    /// <summary>
    /// Çeviri sonucunu kaydeder. Metin zaten Türkçeyse çağrılmaz —
    /// o durumda saklanacak bir şey yok.
    /// </summary>
    public void SetTranslation(string translatedText)
    {
        CommentTranslated = translatedText;
        TranslatedAt = DateTime.UtcNow;
        MarkUpdated();
    }
    public int Rating { get; private set; }
    public DateTime ReviewDate { get; private set; }
    public Guid? CreatedBy { get; private set; }
    public Guid? HotelId { get; set; }
    public Hotel? Hotel { get; set; }

    private readonly List<ReviewAnalysis> _analyses = [];
    private readonly List<ReviewAttachment> _attachments = [];
    private readonly List<ActionItem> _actionItems = [];

    public IReadOnlyCollection<ReviewAnalysis> Analyses => _analyses.AsReadOnly();
    public IReadOnlyCollection<ReviewAttachment> Attachments => _attachments.AsReadOnly();
    public IReadOnlyCollection<ActionItem> ActionItems => _actionItems.AsReadOnly();

    public void AddAnalysis(ReviewAnalysis analysis) => _analyses.Add(analysis);
    public void AddAttachment(ReviewAttachment attachment) => _attachments.Add(attachment);
    public void AddActionItem(ActionItem item) => _actionItems.Add(item);

    public void RemoveAnalysis(ReviewAnalysis analysis) => _analyses.Remove(analysis);
    public void ClearAnalyses() => _analyses.Clear();

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
        Guid? createdBy,
        Guid? hotelId = null)
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
            CreatedBy = createdBy,
            HotelId = hotelId
        };
    }
}
