using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IReviewRepository : IGenericRepository<Review>
{
    Task<Review?> GetByIdWithDetailsAsync(Guid id);
    Task<IEnumerable<Review>> GetFilteredReviewsAsync(DateTime? startDate, DateTime? endDate, int? rating, string? language);
}
