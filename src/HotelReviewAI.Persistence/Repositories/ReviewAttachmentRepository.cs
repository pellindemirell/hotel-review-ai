using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

public class ReviewAttachmentRepository : GenericRepository<ReviewAttachment>, IReviewAttachmentRepository
{
    public ReviewAttachmentRepository(AppDbContext context) : base(context)
    {
    }

    public async Task<IEnumerable<ReviewAttachment>> GetByReviewIdAsync(Guid reviewId) =>
        await DbSet.Where(a => a.ReviewId == reviewId).ToListAsync();
}
