using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Commands.Reviews;

public record TranslateReviewCommand(Guid ReviewId) : IRequest<ReviewTranslationDto>;

public class ReviewTranslationDto
{
    public Guid ReviewId { get; set; }

    /// <summary>Türkçe metin. Yorum zaten Türkçeyse orijinalin aynısıdır.</summary>
    public string TranslatedText { get; set; } = string.Empty;

    /// <summary>Yorum zaten Türkçe olduğu için çeviri yapılmadı.</summary>
    public bool AlreadyTurkish { get; set; }

    /// <summary>Daha önce çevrilmiş, veritabanından geldi (AI servisine gidilmedi).</summary>
    public bool FromCache { get; set; }
}

public class TranslateReviewHandler : IRequestHandler<TranslateReviewCommand, ReviewTranslationDto>
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IAiAnalysisService _aiAnalysisService;

    public TranslateReviewHandler(
        IReviewRepository reviewRepository,
        IAiAnalysisService aiAnalysisService)
    {
        _reviewRepository = reviewRepository;
        _aiAnalysisService = aiAnalysisService;
    }

    public async Task<ReviewTranslationDto> Handle(TranslateReviewCommand request, CancellationToken cancellationToken)
    {
        var review = await _reviewRepository.GetByIdAsync(request.ReviewId)
            ?? throw new KeyNotFoundException("Yorum bulunamadı.");

        // 1) Daha önce çevrilmişse AI servisine hiç gitme.
        if (!string.IsNullOrWhiteSpace(review.CommentTranslated))
        {
            return new ReviewTranslationDto
            {
                ReviewId = review.Id,
                TranslatedText = review.CommentTranslated,
                FromCache = true
            };
        }

        var result = await _aiAnalysisService.TranslateToTurkishAsync(
            review.Comment, review.Language, cancellationToken)
            ?? throw new InvalidOperationException("Çeviri servisine şu anda ulaşılamıyor.");

        // 2) Zaten Türkçeyse saklanacak bir şey yok; orijinali döndür.
        //
        // AlreadyTurkish bayrağı langdetect'e dayanıyor ve yanılabiliyor: canlı
        // veride açıkça Türkçe olan bir yorum "tr" olarak tanınmayıp çeviriye
        // gönderildi, Google metni AYNEN geri döndürdü ve sonuç "çeviri" diye
        // kaydedilecekti. Kullanıcı açısından bu "çevir'e bastım hiçbir şey
        // değişmedi" demek. Metin karşılaştırması dil tespitinden bağımsız,
        // kesin bir kontrol sağlıyor.
        var unchanged = string.Equals(
            (result.TranslatedText ?? string.Empty).Trim(), review.Comment.Trim(), StringComparison.Ordinal);

        if (result.AlreadyTurkish || unchanged || string.IsNullOrWhiteSpace(result.TranslatedText))
        {
            return new ReviewTranslationDto
            {
                ReviewId = review.Id,
                TranslatedText = review.Comment,
                AlreadyTurkish = true
            };
        }

        review.SetTranslation(result.TranslatedText);
        await _reviewRepository.SaveChangesAsync();

        return new ReviewTranslationDto
        {
            ReviewId = review.Id,
            TranslatedText = result.TranslatedText
        };
    }
}
