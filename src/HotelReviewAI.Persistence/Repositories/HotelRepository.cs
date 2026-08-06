using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

public class HotelRepository : GenericRepository<Hotel>, IHotelRepository
{
    public HotelRepository(AppDbContext context) : base(context)
    {
    }

    public async Task<IEnumerable<Hotel>> GetActiveHotelsAsync()
    {
        return await DbSet.Where(h => h.IsActive).ToListAsync();
    }
}
