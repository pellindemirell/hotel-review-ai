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
    // Kategori adı + o kategoriye ait cümlelerin ortalama duygu durumu.
    // Panelde kategori etiketleri bu duyguya göre renklendiriliyor.
    public List<ReviewCategoryTagDto> Categories { get; set; } = [];
    public string? Category { get; set; }
    public string? CategoryName { get; set; }

    // Yorumun genel duygu durumu: cümle bazlı analizlerin SentimentScore ortalamasından
    // türetilir (SentimentThresholds). Hiç analiz yoksa null döner — istemci rozet göstermez.
    // Bu alan olmadan liste ekranı her satır için ayrıca detay ucunu çağırmak zorundaydı.
    public string? Sentiment { get; set; }
    public double? SentimentScore { get; set; }

    // "Türkçeye çevir" butonu için: istemci hangi yorumun çeviriye ihtiyacı
    // olduğunu (Language != "tr") ve daha önce çevrilmiş olanları (CommentTranslated
    // dolu) ekstra istek atmadan biliyor.
    public string Language { get; set; } = string.Empty;
    public string? CommentTranslated { get; set; }
}

public class ReviewCategoryTagDto
{
    public string Name { get; set; } = string.Empty;
    /// <summary>Positive / Negative / Neutral</summary>
    public string Sentiment { get; set; } = string.Empty;
    public double SentimentScore { get; set; }
}

public class ReviewDetailDto : ReviewListItemDto
{
    // Language artık ReviewListItemDto'da (liste ekranı da çeviri butonu için kullanıyor).
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
    public string? DepartmentLabel { get; set; }
    public string? AspectLabel { get; set; }
    public List<string> Keywords { get; set; } = [];
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
