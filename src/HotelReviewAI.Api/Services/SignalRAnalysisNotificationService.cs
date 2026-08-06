using System;
using System.Threading;
using System.Threading.Tasks;
using HotelReviewAI.Api.Hubs;
using HotelReviewAI.Application.Interfaces;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Api.Services;

public class SignalRAnalysisNotificationService : IAnalysisNotificationService
{
    private readonly IHubContext<AnalysisHub, IAnalysisClient> _hubContext;
    private readonly ILogger<SignalRAnalysisNotificationService> _logger;

    public SignalRAnalysisNotificationService(
        IHubContext<AnalysisHub, IAnalysisClient> hubContext,
        ILogger<SignalRAnalysisNotificationService> logger)
    {
        _hubContext = hubContext;
        _logger = logger;
    }

    public async Task NotifyAnalysisCompletedAsync(
        Guid reviewId, Guid? hotelId, string sentiment, string? category, CancellationToken cancellationToken = default)
    {
        // Bildirim yalnızca ilgili otelin grubuna gider. Daha önce Clients.All kullanılıyordu
        // ve her otel diğerlerinin analiz bildirimlerini görüyordu.
        if (hotelId is null)
        {
            _logger.LogWarning(
                "ReviewId {ReviewId} için otel bilgisi yok; analiz bildirimi gönderilmedi.", reviewId);
            return;
        }

        await _hubContext.Clients
            .Group(AnalysisHub.GroupName(hotelId.Value))
            .AnalysisCompleted(new
            {
                reviewId,
                hotelId,
                sentiment,
                category,
                completedAt = DateTime.UtcNow
            });
    }
}
