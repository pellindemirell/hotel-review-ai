using System;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Interfaces;

public interface IAnalysisQueue
{
    ValueTask QueueAnalysisAsync(Guid reviewId, CancellationToken cancellationToken = default);
    ValueTask<Guid> DequeueAnalysisAsync(CancellationToken cancellationToken = default);
}
