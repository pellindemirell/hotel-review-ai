using HotelReviewAI.Domain.Entities;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Interfaces;

/// <summary>
/// Yorumların AI analizi ve otomatik aksiyon süreçlerini yöneten servis.
/// </summary>
public interface IReviewAnalysisProcessingService
{
    /// <summary>
    /// Verilen yorum için AI analizini başlatır, sonuçları kaydeder ve gerekirse aksiyon tanımlar.
    /// </summary>
    Task ProcessAnalysisAsync(Review review, bool isReanalysis, CancellationToken cancellationToken);
}
