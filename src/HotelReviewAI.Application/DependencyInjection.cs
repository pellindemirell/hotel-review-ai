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

        var config = new TypeAdapterConfig();
        config.Scan(Assembly);
        services.AddSingleton(config);
        services.AddScoped<IMapper, ServiceMapper>();

        services.AddScoped<Interfaces.IReviewAnalysisProcessingService, Services.ReviewAnalysisProcessingService>();

        return services;
    }
}
