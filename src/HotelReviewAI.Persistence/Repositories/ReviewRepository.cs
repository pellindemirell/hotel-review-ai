using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
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
            // Filtre, ekrandaki rozetle aynı kuralı kullanmalı: rozet cümle skorlarının
            // ORTALAMASINDAN türetiliyor. Önceden burada Any(...) vardı — "en az bir cümlesi
            // olumlu" olan karma yorumlar "Olumlu" filtresinde çıkıp "Olumsuz" rozetiyle
            // görünüyordu. Analizi olmayan yorumların rozeti de olmadığı için hariç tutulur.
            query = filter.Sentiment switch
            {
                Sentiment.Positive => query.Where(r => r.Analyses.Any()
                    && r.Analyses.Average(a => a.SentimentScore) > SentimentThresholds.Positive),
                Sentiment.Negative => query.Where(r => r.Analyses.Any()
                    && r.Analyses.Average(a => a.SentimentScore) < SentimentThresholds.Negative),
                _ => query.Where(r => r.Analyses.Any()
                    && r.Analyses.Average(a => a.SentimentScore) >= SentimentThresholds.Negative
                    && r.Analyses.Average(a => a.SentimentScore) <= SentimentThresholds.Positive)
            };
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

        query = filter.SortBy switch
        {
            // Sıralama yorumun TARİHİNE göre yapılmalı, kaydın veritabanına eklenme anına
            // (CreatedAt) göre değil. Toplu içe aktarmada tüm kayıtlar saniyeler içinde
            // dosya sırasıyla eklendiği için "Yeniden Eskiye" tam tersi sonuç veriyordu.
            // CreatedAt yalnızca eşit tarihlerde belirleyici olarak kullanılıyor.
            "newest" => query.OrderByDescending(r => r.ReviewDate).ThenByDescending(r => r.CreatedAt),
            "oldest" => query.OrderBy(r => r.ReviewDate).ThenBy(r => r.CreatedAt),
            "highest" => query.OrderByDescending(r => r.Rating).ThenByDescending(r => r.ReviewDate),
            "lowest" => query.OrderBy(r => r.Rating).ThenByDescending(r => r.ReviewDate),
            _ => query.OrderByDescending(r => r.ReviewDate).ThenByDescending(r => r.CreatedAt)
        };

        var items = await query
            .Skip((filter.Page - 1) * filter.PageSize)
            .Take(filter.PageSize)
            .ToListAsync();

        return (items, totalCount);
    }
}
