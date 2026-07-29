using System;
using System.Threading;
using System.Threading.Tasks;
using HotelReviewAI.Api.Hubs;
using HotelReviewAI.Application.Interfaces;
using Microsoft.AspNetCore.SignalR;

namespace HotelReviewAI.Api.Services;

public class SignalRAnalysisNotificationService : IAnalysisNotificationService
{
    private readonly IHubContext<AnalysisHub, IAnalysisClient> _hubContext;

    public SignalRAnalysisNotificationService(IHubContext<AnalysisHub, IAnalysisClient> hubContext)
    {
        _hubContext = hubContext;
    }

    public async Task NotifyAnalysisCompletedAsync(
        Guid reviewId, string sentiment, string? category, CancellationToken cancellationToken = default)
    {
        await _hubContext.Clients.All.AnalysisCompleted(new
        {
            reviewId,
            sentiment,
            category,
            completedAt = DateTime.UtcNow
        });
    }
}
