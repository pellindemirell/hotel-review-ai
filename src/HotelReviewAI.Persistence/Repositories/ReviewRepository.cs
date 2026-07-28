using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

public class ReviewRepository : GenericRepository<Review>, IReviewRepository
{
    public ReviewRepository(AppDbContext context) : base(context)
    {
    }

    public async Task<Review?> GetByIdWithDetailsAsync(Guid id) =>
        await DbSet
            .Include(r => r.Analyses).ThenInclude(a => a.Category)
            .Include(r => r.Attachments)
            .Include(r => r.ActionItems)
            .FirstOrDefaultAsync(r => r.Id == id);

    public async Task<(IEnumerable<Review> Items, int TotalCount)> GetFilteredReviewsAsync(ReviewFilter filter)
    {
        var query = DbSet.Include(r => r.Analyses).ThenInclude(a => a.Category).AsQueryable();

        if (filter.DateFrom is not null)
        {
            query = query.Where(r => r.ReviewDate >= filter.DateFrom);
        }

        if (filter.DateTo is not null)
        {
            query = query.Where(r => r.ReviewDate <= filter.DateTo);
        }

        if (filter.Source is not null)
        {
            query = query.Where(r => r.Source == filter.Source);
        }

        if (filter.Sentiment is not null)
        {
            query = query.Where(r => r.Analyses.Any(a => a.Sentiment == filter.Sentiment));
        }

        if (filter.CategoryId is not null)
        {
            query = query.Where(r => r.Analyses.Any(a => a.CategoryId == filter.CategoryId));
        }

        if (filter.DepartmentId is not null)
        {
            query = query.Where(r => r.Analyses.Any(a => a.Category != null && a.Category.DepartmentId == filter.DepartmentId));
        }

        if (filter.HotelId is not null)
        {
            query = query.Where(r => r.HotelId == filter.HotelId);
        }

        var totalCount = await query.CountAsync();

        var items = await query
            .OrderByDescending(r => r.ReviewDate)
            .Skip((filter.Page - 1) * filter.PageSize)
            .Take(filter.PageSize)
            .ToListAsync();

        return (items, totalCount);
    }
}
