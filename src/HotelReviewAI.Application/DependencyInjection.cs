using FluentValidation;
using HotelReviewAI.Application.Behaviors;
using Mapster;
using MapsterMapper;
using Microsoft.Extensions.DependencyInjection;

namespace HotelReviewAI.Application;

public static class DependencyInjection
{
    private static readonly System.Reflection.Assembly Assembly = typeof(DependencyInjection).Assembly;

    public static IServiceCollection AddApplication(this IServiceCollection services)
    {
        services.AddMediatR(cfg =>
        {
            cfg.RegisterServicesFromAssembly(Assembly);
            cfg.AddOpenBehavior(typeof(ValidationBehavior<,>));
        });

        services.AddValidatorsFromAssembly(Assembly);

        // Handler'lar dönüşümü `entity.Adapt<TDto>()` ile yapıyor; bu uzantı metodu her zaman
        // TypeAdapterConfig.GlobalSettings'i okur. Kurallar ayrı bir TypeAdapterConfig
        // örneğine taranırsa MappingConfig'teki özel eşlemeler sessizce yok sayılır
        // (ReviewListItemDto.PhotoUrl/Categories/CategoryName bu yüzden hep null dönüyordu).
        TypeAdapterConfig.GlobalSettings.Scan(Assembly);
        services.AddSingleton(TypeAdapterConfig.GlobalSettings);
        services.AddScoped<IMapper, ServiceMapper>();

        services.AddScoped<Interfaces.IReviewAnalysisProcessingService, Services.ReviewAnalysisProcessingService>();

        return services;
    }
}
