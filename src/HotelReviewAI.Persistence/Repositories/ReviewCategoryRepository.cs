using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

public class ReviewCategoryRepository : GenericRepository<ReviewCategory>, IReviewCategoryRepository
{
    public ReviewCategoryRepository(AppDbContext context) : base(context)
    {
    }

    public async Task<ReviewCategory?> GetByNameAsync(string name) =>
        await DbSet.FirstOrDefaultAsync(c => c.Name == name);
}
