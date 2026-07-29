using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Domain.Entities;
using Mapster;

namespace HotelReviewAI.Application.Mappings;

/// <summary>
/// Tüm Mapster konfigürasyonları bu sınıfta tanımlanır.
/// DependencyInjection.cs içinde TypeAdapterConfig.GlobalSettings.Scan() ile otomatik yüklenir.
/// </summary>
public class MappingConfig : IRegister
{
    public void Register(TypeAdapterConfig config)
    {
        // ReviewAnalysis → ReviewAnalysisDto: enum'ları string'e çevir
        config.NewConfig<ReviewAnalysis, ReviewAnalysisDto>()
            .Map(dest => dest.Sentiment, src => src.Sentiment.ToString())
            .Map(dest => dest.Priority, src => src.Priority.ToString())
            .Map(dest => dest.CategoryName, src => src.Category != null ? src.Category.Name : null);

        // Review → ReviewListItemDto
        config.NewConfig<Review, ReviewListItemDto>()
            .Map(dest => dest.Source, src => src.Source.ToString())
            .Map(dest => dest.PhotoUrl, src => src.Attachments != null && src.Attachments.Any() ? src.Attachments.First().FileUrl : null);

        // Review → ReviewDetailDto (nested collections)
        config.NewConfig<Review, ReviewDetailDto>()
            .Map(dest => dest.Source, src => src.Source.ToString())
            .Map(dest => dest.PhotoUrl, src => src.Attachments != null && src.Attachments.Any() ? src.Attachments.First().FileUrl : null);

        // ReviewAttachment → ReviewAttachmentDto
        config.NewConfig<ReviewAttachment, ReviewAttachmentDto>();

        // ActionItem → ActionItemDto
        config.NewConfig<ActionItem, ActionItemDto>()
            .Map(dest => dest.Status, src => src.Status.ToString());

        // User → UserDto
        config.NewConfig<User, UserDto>()
            .Map(dest => dest.Role, src => src.Role);
    }
}
