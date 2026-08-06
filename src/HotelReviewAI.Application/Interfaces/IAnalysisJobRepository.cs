using System.Threading.Tasks;
using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IAnalysisJobRepository : IGenericRepository<AnalysisJob>
{
    Task<AnalysisJob?> GetNextPendingAsync();
    Task<IEnumerable<AnalysisJob>> GetFailedJobsAsync();
    Task<int> DeleteCompletedBeforeAsync(DateTime cutoffDate);

    /// <summary>
    /// En eski <paramref name="batchSize"/> bekleyen işi tek atomik ifadeyle
    /// Processing'e çekip kimliklerini döndürür. Aynı işi iki worker'ın birden
    /// alması mümkün değildir.
    /// </summary>
    Task<IReadOnlyList<Guid>> ClaimPendingAsync(int batchSize, CancellationToken cancellationToken = default);

    /// <summary>
    /// Çöken bir süreçten Processing'de kalmış işleri Pending'e geri alır.
    /// Kapma artık bir UPDATE olduğu için bu olmadan takılı işler sonsuza dek kalır.
    /// </summary>
    Task<int> ReapStuckProcessingAsync(TimeSpan olderThan, CancellationToken cancellationToken = default);
}
