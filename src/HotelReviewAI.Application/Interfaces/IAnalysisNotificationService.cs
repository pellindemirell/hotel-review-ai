using System;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Interfaces;

public interface IAnalysisNotificationService
{
    Task NotifyAnalysisCompletedAsync(Guid reviewId, string sentiment, string? category, CancellationToken cancellationToken = default);
}
