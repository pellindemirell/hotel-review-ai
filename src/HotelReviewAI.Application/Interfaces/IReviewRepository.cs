using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IReviewRepository : IGenericRepository<Review>
{
    Task<Review?> GetByIdWithDetailsAsync(Guid id);
    Task<(IEnumerable<Review> Items, int TotalCount)> GetFilteredReviewsAsync(ReviewFilter filter);
}
