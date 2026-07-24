using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Infrastructure.Clients;
using HotelReviewAI.Infrastructure.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Polly;
using Polly.Extensions.Http;

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
        var aiServiceUrl = configuration["AiServiceUrl"] ?? "http://localhost:8000";

        services.AddHttpClient<IAiAnalysisService, AiAnalysisService>(client =>
        {
            client.BaseAddress = new Uri(aiServiceUrl);
            client.Timeout = TimeSpan.FromSeconds(2); // Düşük zaman aşımı (hızlı fail)
        });
        // .AddPolicyHandler(GetRetryPolicy()); // AI servisi kapalıyken bekletmemesi için şimdilik iptal

        return services;
    }

    /// <summary>
    /// Geçici HTTP hatalarında (5xx, 408) 3 kez yeniden dener.
    /// Bekleme süresi: 2^n saniye (2s, 4s, 8s).
    /// </summary>
    private static IAsyncPolicy<HttpResponseMessage> GetRetryPolicy()
    {
        return HttpPolicyExtensions
            .HandleTransientHttpError()
            .WaitAndRetryAsync(
                retryCount: 3,
                sleepDurationProvider: attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt)));
    }
}
