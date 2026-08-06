using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Infrastructure.Services;

public class AnalysisBackgroundWorker : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<AnalysisBackgroundWorker> _logger;

    private readonly int _concurrency;
    private readonly TimeSpan _idlePoll;
    private readonly TimeSpan _unhealthyPoll;
    private readonly TimeSpan _stuckJobAge;

    // Toplu içe aktarımdan sonra kuyruk saatlerce dolu kalabiliyor; takılı iş
    // taraması her turda değil, bu aralıkta bir çalışır.
    private static readonly TimeSpan ReapInterval = TimeSpan.FromMinutes(5);
    private DateTime _nextReapAt = DateTime.MinValue;

    public AnalysisBackgroundWorker(
        IServiceScopeFactory scopeFactory,
        ILogger<AnalysisBackgroundWorker> logger,
        IConfiguration configuration)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;

        var section = configuration.GetSection("AnalysisWorker");

        // Varsayılan 4 keyfi değil: AI servisi kendini ANALYZE_MAX_CONCURRENCY=4
        // ThreadPoolExecutor'ı ile sınırlıyor (ai-service/app/main.py). Fazlası
        // Python tarafında kuyruğa girer, verim artmaz ama tek isteğin süresi
        // uzayıp HTTP timeout'una yaklaşır. Artırılacaksa ikisi birlikte artmalı.
        _concurrency = Math.Max(1, section.GetValue("Concurrency", 4));
        _idlePoll = TimeSpan.FromSeconds(Math.Max(1, section.GetValue("IdlePollSeconds", 10)));
        _unhealthyPoll = TimeSpan.FromSeconds(Math.Max(1, section.GetValue("UnhealthyPollSeconds", 3)));
        _stuckJobAge = TimeSpan.FromMinutes(Math.Max(1, section.GetValue("StuckJobReapMinutes", 15)));
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation(
            "Analysis Background Worker started. Waiting for review analysis queue jobs... (concurrency: {Concurrency})",
            _concurrency);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await ReapStuckJobsIfDueAsync(stoppingToken);

                // Sağlık kontrolü KAPMADAN ÖNCE yapılmalı. Kapma artık salt okuma
                // değil, Status=Processing yazan bir UPDATE; AI servisi tökezlediğinde
                // önce kapıp sonra sağlığa bakarsak işler Processing'de asılı kalır.
                if (!await IsAiHealthyAsync(stoppingToken))
                {
                    _logger.LogInformation("AI servisi hazır değil, bekleniyor...");
                    await Task.Delay(_unhealthyPoll, stoppingToken);
                    continue;
                }

                var jobIds = await ClaimJobsAsync(stoppingToken);
                if (jobIds.Count == 0)
                {
                    // Kuyruk boşsa bekle (gereksiz DB yükünü engellemek için)
                    await Task.Delay(_idlePoll, stoppingToken);
                    continue;
                }

                await Parallel.ForEachAsync(
                    jobIds,
                    new ParallelOptions
                    {
                        MaxDegreeOfParallelism = _concurrency,
                        CancellationToken = stoppingToken
                    },
                    ProcessOneAsync);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                // Normal shutdown sequence
                break;
            }
            catch (Exception ex)
            {
                // Buraya yalnızca kapma/sağlık kontrolü seviyesindeki hatalar düşer;
                // tek bir işin hatası ProcessOneAsync içinde ele alınıyor.
                _logger.LogError(ex, "Analysis worker loop error.");
                await Task.Delay(_unhealthyPoll, stoppingToken);
            }
        }

        _logger.LogInformation("Analysis Background Worker stopped.");
    }

    private async Task<bool> IsAiHealthyAsync(CancellationToken stoppingToken)
    {
        using var scope = _scopeFactory.CreateScope();
        var aiService = scope.ServiceProvider.GetRequiredService<IAiAnalysisService>();
        return await aiService.IsHealthyAsync(stoppingToken);
    }

    private async Task<IReadOnlyList<Guid>> ClaimJobsAsync(CancellationToken stoppingToken)
    {
        using var scope = _scopeFactory.CreateScope();
        var jobRepo = scope.ServiceProvider.GetRequiredService<IAnalysisJobRepository>();
        return await jobRepo.ClaimPendingAsync(_concurrency, stoppingToken);
    }

    private async Task ReapStuckJobsIfDueAsync(CancellationToken stoppingToken)
    {
        if (DateTime.UtcNow < _nextReapAt)
        {
            return;
        }

        _nextReapAt = DateTime.UtcNow + ReapInterval;

        using var scope = _scopeFactory.CreateScope();
        var jobRepo = scope.ServiceProvider.GetRequiredService<IAnalysisJobRepository>();
        var reaped = await jobRepo.ReapStuckProcessingAsync(_stuckJobAge, stoppingToken);

        if (reaped > 0)
        {
            _logger.LogWarning(
                "{Count} takılı analiz işi ({Age} dakikadan eski) Pending'e geri alındı.",
                reaped, _stuckJobAge.TotalMinutes);
        }
    }

    /// <summary>
    /// Tek bir analiz işini işler. KENDİ DI scope'unu açar — AppDbContext Scoped
    /// ve thread-safe değil; tek scope paylaşılırsa "A second operation was started
    /// on this context" alınır. AuditInterceptor ve ICurrentUserService de scoped,
    /// ayrıca GenericRepository.SaveChangesAsync() context'te izlenen her şeyi
    /// flush ediyor — scope izolasyonu bunu da doğru tutuyor.
    /// </summary>
    private async ValueTask ProcessOneAsync(Guid jobId, CancellationToken stoppingToken)
    {
        using var scope = _scopeFactory.CreateScope();
        var provider = scope.ServiceProvider;

        var jobRepo = provider.GetRequiredService<IAnalysisJobRepository>();
        var job = await jobRepo.GetByIdAsync(jobId);

        if (job == null)
        {
            _logger.LogWarning("Claimed AnalysisJob {JobId} not found.", jobId);
            return;
        }

        try
        {
            _logger.LogInformation("Processing background analysis job for ReviewId: {ReviewId}", job.ReviewId);

            var reviewRepository = provider.GetRequiredService<IReviewRepository>();
            var review = await reviewRepository.GetByIdAsync(job.ReviewId);

            if (review == null)
            {
                _logger.LogWarning("ReviewId: {ReviewId} not found in database during background processing.", job.ReviewId);
                job.Status = AnalysisJobStatus.Failed;
                job.ErrorMessage = "Review not found";
                await jobRepo.SaveChangesAsync();
                return;
            }

            var processingService = provider.GetRequiredService<IReviewAnalysisProcessingService>();
            await processingService.ProcessAnalysisAsync(review, isReanalysis: false, stoppingToken);

            job.Status = AnalysisJobStatus.Completed;
            job.ProcessedAt = DateTime.UtcNow;
            await jobRepo.SaveChangesAsync();

            // Fetch resulting sentiment/category for notification payload
            var analysisRepo = provider.GetRequiredService<IReviewAnalysisRepository>();
            var analyses = await analysisRepo.GetByReviewIdAsync(job.ReviewId);
            var primaryAnalysis = analyses.FirstOrDefault();

            var notificationService = provider.GetRequiredService<IAnalysisNotificationService>();
            await notificationService.NotifyAnalysisCompletedAsync(
                job.ReviewId,
                review.HotelId,
                primaryAnalysis?.Sentiment.ToString() ?? "Completed",
                primaryAnalysis?.Category?.Name,
                stoppingToken);

            _logger.LogInformation("Successfully completed background analysis and sent SignalR notification for ReviewId: {ReviewId}", job.ReviewId);
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            // Kapatma sırasında kapılmış iş Processing'de kalmasın; toplayıcı da
            // yakalar ama hemen geri bırakmak yeniden başlatmayı hızlandırır.
            await WriteJobOutcomeAsync(jobId, AnalysisJobStatus.Pending, null, incrementRetry: false, CancellationToken.None);
            throw;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Job failed. ReviewId: {Id}", job.ReviewId);

            var retryCount = job.RetryCount + 1;
            var status = retryCount >= 3
                ? AnalysisJobStatus.Failed   // 3 denemede olmadı
                : AnalysisJobStatus.Pending; // tekrar dene

            _logger.LogError("Retry count for ReviewId {ReviewId}: {Retry}", job.ReviewId, retryCount);

            await WriteJobOutcomeAsync(jobId, status, ex.Message, incrementRetry: true, stoppingToken);

            // Üstel geri çekilme: sabit 3 sn ile aynı job hemen tekrar çekiliyor ve
            // AI servisi ayaktayken bile hata döngüsü CPU/log şişiriyordu.
            // Bekleme DIŞ döngüde değil burada: aksi halde tek bir zehirli yorum
            // paralel çalışan diğer işleri de durdururdu.
            var backoffSeconds = Math.Min(60, 3 * (int)Math.Pow(2, retryCount));
            await Task.Delay(TimeSpan.FromSeconds(backoffSeconds), stoppingToken);
        }
    }

    /// <summary>
    /// İşin sonucunu TEMİZ bir scope üzerinden yazar.
    /// </summary>
    /// <remarks>
    /// Kritik: analiz sırasında hata veren scope'un DbContext'i geçersiz entity'leri
    /// (ör. kolon sınırını aşan bir ActionItem) hâlâ izliyor olabilir. SaveChanges o
    /// context'te izlenen HER ŞEYİ flush ettiği için, iş durumunu aynı context'ten
    /// yazmaya çalışmak aynı hatayla tekrar patlıyordu. Sonuç: iş Failed olarak
    /// işaretlenemiyor, Processing'de kalıyor, reaper onu Pending'e döndürüyor ve
    /// sonsuz yeniden deneme döngüsü oluşuyordu (her turda boşuna bir AI çağrısı).
    /// Ayrı scope, durum yazımını analiz hatasından tamamen yalıtır.
    /// </remarks>
    private async Task WriteJobOutcomeAsync(
        Guid jobId,
        AnalysisJobStatus status,
        string? errorMessage,
        bool incrementRetry,
        CancellationToken cancellationToken)
    {
        try
        {
            using var scope = _scopeFactory.CreateScope();
            var jobRepo = scope.ServiceProvider.GetRequiredService<IAnalysisJobRepository>();

            var job = await jobRepo.GetByIdAsync(jobId);
            if (job == null)
            {
                return;
            }

            if (incrementRetry)
            {
                job.RetryCount++;
            }

            job.Status = status;
            job.ErrorMessage = errorMessage;

            await jobRepo.SaveChangesAsync();
        }
        catch (Exception saveEx)
        {
            _logger.LogError(saveEx, "Failed to save job outcome. JobId: {JobId}", jobId);
        }
    }
}
