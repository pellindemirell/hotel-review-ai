using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Infrastructure.Clients;
using HotelReviewAI.Infrastructure.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace HotelReviewAI.Infrastructure;

public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructure(
        this IServiceCollection services, IConfiguration configuration)
    {
        // JWT token üretimi
        services.AddScoped<IJwtProvider, JwtProvider>();

        // Cloudinary görsel depolama servisi
        services.AddScoped<ICloudinaryService, CloudinaryService>();

        // Mevcut kullanıcı claim'lerini okuyan servis (Interceptor ve Handler'lar için)
        services.AddHttpContextAccessor();
        services.AddScoped<ICurrentUserService, CurrentUserService>();

        // Python AI servis entegrasyonu (Her zaman aktif)
        var aiServiceUrl = configuration["AiService:Url"] ?? "http://localhost:8000";

        var timeoutSeconds = configuration.GetValue<int>("AiService:TimeoutSeconds", 30);
        services.AddHttpClient<IAiAnalysisService, AiAnalysisService>(client =>
        {
            client.BaseAddress = new Uri(aiServiceUrl);
            client.Timeout = TimeSpan.FromSeconds(timeoutSeconds);
        });

        // Asenkron Arka Plan Analiz Kuyruğu ve Worker
        services.AddSingleton<IAnalysisQueue, AnalysisQueue>();
        services.AddHostedService<AnalysisBackgroundWorker>();

        return services;
    }
}
