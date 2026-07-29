using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IReviewCategoryRepository : IGenericRepository<ReviewCategory>
{
    Task<ReviewCategory?> GetByNameAsync(string name);
}
