using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

public class UserRepository : GenericRepository<User>, IUserRepository
{
    public UserRepository(AppDbContext context) : base(context)
    {
    }

    public async Task<User?> GetByEmailAsync(string email) =>
        await DbSet.FirstOrDefaultAsync(u => u.Email == email);

    public async Task<List<User>> GetUsersAsync(Guid? hotelId = null, Guid? departmentId = null)
    {
        var query = DbSet.AsQueryable();
        
        if (hotelId.HasValue)
        {
            query = query.Where(u => u.HotelId == hotelId.Value);
        }

        if (departmentId.HasValue)
        {
            query = query.Where(u => u.DepartmentId == departmentId.Value);
        }

        return await query.ToListAsync();
    }
}
