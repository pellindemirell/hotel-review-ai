using System;
using System.Threading;
using System.Threading.Tasks;
using HotelReviewAI.Application.Interfaces;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.DependencyInjection;

namespace HotelReviewAI.Infrastructure.Services;

public class AnalysisNotificationService : IAnalysisNotificationService
{
    private readonly IClientProxy _allClients;

    public AnalysisNotificationService(IServiceProvider serviceProvider)
    {
        // Dynamically resolved via IServiceProvider to decouple concrete Hub type
        var hubContextType = typeof(IHubContext<>).MakeGenericType(
            Type.GetType("HotelReviewAI.Api.Hubs.AnalysisHub, HotelReviewAI.Api") 
            ?? throw new InvalidOperationException("AnalysisHub type not found"));
        
        dynamic hubContext = serviceProvider.GetRequiredService(hubContextType);
        _allClients = (IClientProxy)hubContext.Clients.All;
    }

    public async Task NotifyAnalysisCompletedAsync(Guid reviewId, string sentiment, string? category, CancellationToken cancellationToken = default)
    {
        await _allClients.SendCoreAsync("AnalysisCompleted", new object[]
        {
            new
            {
                reviewId,
                sentiment,
                category,
                completedAt = DateTime.UtcNow
            }
        }, cancellationToken);
    }
}
