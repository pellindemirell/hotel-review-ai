using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using Mapster;

namespace HotelReviewAI.Application.Mappings;

/// <summary>
/// Tüm Mapster konfigürasyonları bu sınıfta tanımlanır.
/// DependencyInjection.cs içinde TypeAdapterConfig.GlobalSettings.Scan() ile otomatik yüklenir.
/// </summary>
public class MappingConfig : IRegister
{
    /// <summary>
    /// Yorumun kategori etiketlerini, her kategoriye ait cümlelerin ortalama duygu
    /// skoruyla birlikte üretir. Aynı kategori birden çok cümlede geçebildiği için
    /// (ör. yemek hem övülüp hem eleştirilebilir) ortalama alınır; eşikler genel
    /// duygu hesabıyla aynı kaynaktan gelir (SentimentThresholds).
    /// </summary>
    private static List<ReviewCategoryTagDto> BuildCategoryTags(IEnumerable<ReviewAnalysis>? analyses)
    {
        if (analyses == null)
        {
            return [];
        }

        return analyses
            .GroupBy(a => a.Category != null ? a.Category.Name : (a.AspectLabel ?? "Diğer"))
            .Select(g =>
            {
                var average = g.Average(a => a.SentimentScore);
                return new ReviewCategoryTagDto
                {
                    Name = g.Key,
                    SentimentScore = Math.Round(average, 3),
                    Sentiment = SentimentThresholds.FromAverageScore(average).ToString()
                };
            })
            .ToList();
    }


    public void Register(TypeAdapterConfig config)
    {
        // ReviewAnalysis → ReviewAnalysisDto: enum'ları string'e çevir
        config.NewConfig<ReviewAnalysis, ReviewAnalysisDto>()
            .Map(dest => dest.Sentiment, src => src.Sentiment.ToString())
            .Map(dest => dest.Priority, src => src.Priority.ToString())
            .Map(dest => dest.CategoryName, src => src.Category != null ? src.Category.Name : src.AspectLabel);

        // Review → ReviewListItemDto
        config.NewConfig<Review, ReviewListItemDto>()
            .Map(dest => dest.Source, src => src.Source.ToString())
            .Map(dest => dest.PhotoUrl, src => src.Attachments != null && src.Attachments.Any() ? src.Attachments.First().FileUrl : null)
            .Map(dest => dest.Categories, src => BuildCategoryTags(src.Analyses))
            .Map(dest => dest.Category, src => src.Analyses != null && src.Analyses.Any()
                ? string.Join(", ", src.Analyses.Select(a => a.Category != null ? a.Category.Name : (a.AspectLabel ?? "Diğer")).Distinct())
                : null)
            .Map(dest => dest.CategoryName, src => src.Analyses != null && src.Analyses.Any()
                ? string.Join(", ", src.Analyses.Select(a => a.Category != null ? a.Category.Name : (a.AspectLabel ?? "Diğer")).Distinct())
                : null)
            // Genel duygu durumu = cümle skorlarının ortalaması (bkz. SentimentThresholds).
            // Analiz yoksa null kalır; istemci o satırda rozet göstermez.
            .Map(dest => dest.SentimentScore, src => src.Analyses != null && src.Analyses.Any()
                ? src.Analyses.Average(a => a.SentimentScore)
                : (double?)null)
            .Map(dest => dest.Sentiment, src => src.Analyses != null && src.Analyses.Any()
                ? SentimentThresholds.FromAverageScore(src.Analyses.Average(a => a.SentimentScore)).ToString()
                : null);

        // Review → ReviewDetailDto (nested collections)
        // Inherits: ReviewDetailDto, ReviewListItemDto'dan türediği için kategori/sentiment
        // eşlemeleri devralınır; aksi hâlde detay ucunda bu alanlar null kalıyordu.
        config.NewConfig<Review, ReviewDetailDto>()
            .Inherits<Review, ReviewListItemDto>();

        // ReviewAttachment → ReviewAttachmentDto
        config.NewConfig<ReviewAttachment, ReviewAttachmentDto>();

        // ActionItem → ActionItemDto
        config.NewConfig<ActionItem, ActionItemDto>()
            .Map(dest => dest.Status, src => src.Status.ToString());

        // User → UserDto
        config.NewConfig<User, UserDto>()
            .Map(dest => dest.Role, src => src.Role.ToString());
    }
}
