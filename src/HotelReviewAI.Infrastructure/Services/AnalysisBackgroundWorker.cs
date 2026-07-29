using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using HotelReviewAI.Application.Interfaces;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Infrastructure.Services;

public class AnalysisBackgroundWorker : BackgroundService
{
    private readonly IAnalysisQueue _analysisQueue;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<AnalysisBackgroundWorker> _logger;

    public AnalysisBackgroundWorker(
        IAnalysisQueue analysisQueue,
        IServiceScopeFactory scopeFactory,
        ILogger<AnalysisBackgroundWorker> logger)
    {
        _analysisQueue = analysisQueue;
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Analysis Background Worker started. Waiting for review analysis queue jobs...");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var reviewId = await _analysisQueue.DequeueAnalysisAsync(stoppingToken);
                _logger.LogInformation("Processing background analysis job for ReviewId: {ReviewId}", reviewId);

                using var scope = _scopeFactory.CreateScope();
                var reviewRepository = scope.ServiceProvider.GetRequiredService<IReviewRepository>();
                var processingService = scope.ServiceProvider.GetRequiredService<IReviewAnalysisProcessingService>();
                var notificationService = scope.ServiceProvider.GetRequiredService<IAnalysisNotificationService>();

                var review = await reviewRepository.GetByIdAsync(reviewId);
                if (review == null)
                {
                    _logger.LogWarning("ReviewId: {ReviewId} not found in database during background processing.", reviewId);
                    continue;
                }

                await processingService.ProcessAnalysisAsync(review, isReanalysis: false, stoppingToken);

                // Fetch resulting sentiment/category for notification payload
                var analysisRepo = scope.ServiceProvider.GetRequiredService<IReviewAnalysisRepository>();
                var analyses = await analysisRepo.GetByReviewIdAsync(reviewId);
                var primaryAnalysis = analyses.FirstOrDefault();

                await notificationService.NotifyAnalysisCompletedAsync(
                    reviewId,
                    primaryAnalysis?.Sentiment.ToString() ?? "Completed",
                    primaryAnalysis?.Category?.Name,
                    stoppingToken);

                _logger.LogInformation("Successfully completed background analysis and sent SignalR notification for ReviewId: {ReviewId}", reviewId);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                // Normal shutdown sequence
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error occurred while processing background AI review analysis.");
                // Prevent CPU spinning in tight exception loops
                await Task.Delay(1000, stoppingToken);
            }
        }

        _logger.LogInformation("Analysis Background Worker stopped.");
    }
}
