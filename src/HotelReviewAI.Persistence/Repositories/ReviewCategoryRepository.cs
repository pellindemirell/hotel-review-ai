using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;

namespace HotelReviewAI.Persistence.Repositories;

public class ReviewCategoryRepository : GenericRepository<ReviewCategory>, IReviewCategoryRepository
{
    public ReviewCategoryRepository(AppDbContext context) : base(context)
    {
    }
}
