using HotelReviewAI.Application.Interfaces;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Infrastructure.Services;

public class AnalysisCleanupWorker : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<AnalysisCleanupWorker> _logger;

    public AnalysisCleanupWorker(IServiceProvider serviceProvider, ILogger<AnalysisCleanupWorker> logger)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("AnalysisCleanupWorker is starting.");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = _serviceProvider.CreateScope();
                var jobRepo = scope.ServiceProvider.GetRequiredService<IAnalysisJobRepository>();

                var cutoff = DateTime.UtcNow.AddDays(-30);
                var deleted = await jobRepo.DeleteCompletedBeforeAsync(cutoff);
                
                if (deleted > 0)
                {
                    _logger.LogInformation("AnalysisCleanupWorker: {Count} eski job silindi.", deleted);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "AnalysisCleanupWorker hatası.");
            }

            // Gece 03:00'te çalışması için veya 24 saatte bir
            var now = DateTime.UtcNow;
            var nextRun = now.Date.AddDays(1).AddHours(3); // Yarın 03:00 UTC
            
            // Eğer saat henüz gece 3'ü geçmediyse bugünün 03:00'üne kadar bekle (Bu durum genellikle başlangıçta olur)
            if (now < now.Date.AddHours(3))
            {
                nextRun = now.Date.AddHours(3);
            }

            var delay = nextRun - now;
            _logger.LogInformation("AnalysisCleanupWorker is sleeping for {Delay}. Next run: {NextRun}", delay, nextRun);
            
            await Task.Delay(delay, stoppingToken);
        }
    }
}
