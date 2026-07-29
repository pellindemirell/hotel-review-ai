using System;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using HotelReviewAI.Application.Interfaces;

namespace HotelReviewAI.Infrastructure.Services;

public class AnalysisQueue : IAnalysisQueue
{
    private readonly Channel<Guid> _queue;

    public AnalysisQueue()
    {
        // Unbounded or bounded channel with SingleReader/MultipleWriters for high throughput
        var options = new UnboundedChannelOptions
        {
            SingleReader = true,
            SingleWriter = false
        };
        _queue = Channel.CreateUnbounded<Guid>(options);
    }

    public async ValueTask QueueAnalysisAsync(Guid reviewId, CancellationToken cancellationToken = default)
    {
        await _queue.Writer.WriteAsync(reviewId, cancellationToken);
    }

    public async ValueTask<Guid> DequeueAnalysisAsync(CancellationToken cancellationToken = default)
    {
        return await _queue.Reader.ReadAsync(cancellationToken);
    }
}
