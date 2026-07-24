using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;

namespace HotelReviewAI.Persistence.Repositories;

public class DepartmentRepository : GenericRepository<Department>, IDepartmentRepository
{
    public DepartmentRepository(AppDbContext context) : base(context)
    {
    }

    public async Task<List<Department>> GetDepartmentsAsync(Guid? hotelId = null)
    {
        var query = DbSet.AsQueryable();
        
        if (hotelId.HasValue)
        {
            query = query.Where(d => d.HotelId == hotelId.Value);
        }

        return await Microsoft.EntityFrameworkCore.EntityFrameworkQueryableExtensions.ToListAsync(query);
    }
}
