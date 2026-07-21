using FluentValidation;
using HotelReviewAI.Application.Behaviors;
using HotelReviewAI.Application.DTOs;
using Mapster;
using MapsterMapper;
using Microsoft.Extensions.DependencyInjection;

namespace HotelReviewAI.Application;

public static class DependencyInjection
{
    public static IServiceCollection AddApplication(this IServiceCollection services)
    {
        // MediatR + ValidationBehavior pipeline
        services.AddMediatR(cfg =>
        {
            cfg.RegisterServicesFromAssembly(typeof(LoginRequest).Assembly);
            cfg.AddOpenBehavior(typeof(ValidationBehavior<,>));
        });

        // FluentValidation — tüm validator'ları Application assembly'sinden tara
        services.AddValidatorsFromAssembly(typeof(LoginRequest).Assembly);

        // Mapster — TypeAdapterConfig'i singleton olarak kaydet
        var config = TypeAdapterConfig.GlobalSettings;
        config.Scan(typeof(LoginRequest).Assembly);
        services.AddSingleton(config);
        services.AddScoped<IMapper, ServiceMapper>();

        // Application services
        services.AddScoped<Interfaces.IReviewAnalysisProcessingService, Services.ReviewAnalysisProcessingService>();

        return services;
    }
}
