using System;
using System.Threading.Tasks;
using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IReviewAnalysisRepository : IGenericRepository<ReviewAnalysis>
{
    Task<ReviewAnalysis?> GetByReviewIdAsync(Guid reviewId);
}
