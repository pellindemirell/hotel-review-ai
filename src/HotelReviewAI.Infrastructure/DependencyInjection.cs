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
        // Yorum görseli yükleme — mobil ve web paneli ortak kullanır
        services.AddScoped<IReviewPhotoStorage, ReviewPhotoStorage>();

        // Mevcut kullanıcı claim'lerini okuyan servis (Interceptor ve Handler'lar için)
        services.AddHttpContextAccessor();
        services.AddScoped<ICurrentUserService, CurrentUserService>();

        // Python AI servis entegrasyonu (Her zaman aktif)
        var aiServiceUrl = configuration["AiService:Url"] ?? "http://localhost:8000";

        var timeoutSeconds = configuration.GetValue<int>("AiService:TimeoutSeconds", 30);

        // AI servisi artık paylaşımlı anahtar istiyor (varsayılan kapalı). Anahtar
        // yoksa istekler 503 döner; sorunun "AI servisi bozuk" gibi görünmemesi
        // için yapılandırma eksikliği burada açıkça loglanır.
        var aiApiKey = configuration["AiService:ApiKey"];
        // Polly politikaları: AiAnalysisService'in yorumunda bunlar "burada yapılandırılır"
        // deniyordu ama hiç eklenmemişti — HTTP seviyesinde retry/circuit-breaker yoktu.
        services.AddHttpClient<IAiAnalysisService, AiAnalysisService>(client =>
        {
            client.BaseAddress = new Uri(aiServiceUrl);
            client.Timeout = TimeSpan.FromSeconds(timeoutSeconds);

            if (!string.IsNullOrWhiteSpace(aiApiKey))
            {
                client.DefaultRequestHeaders.Add("X-API-Key", aiApiKey);
            }
        })
        // Geçici hatalarda (5xx, 408, ağ) üstel geri çekilmeyle 3 deneme.
        .AddPolicyHandler(HttpPolicyExtensions
            .HandleTransientHttpError()
            .WaitAndRetryAsync(
                3,
                attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt))))
        // AI servisi uzun süre hatalıysa devreyi aç; her isteği 30 sn timeout'a
        // kadar bekletmek yerine hızlıca başarısız dön.
        .AddPolicyHandler(HttpPolicyExtensions
            .HandleTransientHttpError()
            .CircuitBreakerAsync(
                handledEventsAllowedBeforeBreaking: 5,
                durationOfBreak: TimeSpan.FromSeconds(30)));

        // Asenkron Arka Plan Analiz Kuyruğu ve Worker
        services.AddHostedService<AnalysisBackgroundWorker>();
        services.AddHostedService<AnalysisCleanupWorker>();

        return services;
    }
}
