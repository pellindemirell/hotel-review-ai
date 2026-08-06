using System;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Interfaces;

public interface IAnalysisNotificationService
{
    // hotelId, bildirimin yalnızca ilgili otelin dinleyicilerine gitmesi için gereklidir.
    Task NotifyAnalysisCompletedAsync(Guid reviewId, Guid? hotelId, string sentiment, string? category, CancellationToken cancellationToken = default);
}
