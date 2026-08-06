using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

public class ReviewAnalysisRepository : GenericRepository<ReviewAnalysis>, IReviewAnalysisRepository
{
    public ReviewAnalysisRepository(AppDbContext context) : base(context)
    {
    }

    public async Task<IEnumerable<ReviewAnalysis>> GetByReviewIdAsync(Guid reviewId) =>
        await DbSet.Include(a => a.Category).Where(a => a.ReviewId == reviewId).ToListAsync();
}
