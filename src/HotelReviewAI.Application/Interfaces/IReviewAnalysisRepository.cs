using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IReviewAnalysisRepository : IGenericRepository<ReviewAnalysis>
{
    // Bir yorumun 0-N analiz (clause) kaydı olabilir, bu yüzden tekil değil liste döner.
    Task<IEnumerable<ReviewAnalysis>> GetByReviewIdAsync(Guid reviewId);
}
