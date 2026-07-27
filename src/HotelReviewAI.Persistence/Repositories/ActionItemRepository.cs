using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

public class ActionItemRepository : GenericRepository<ActionItem>, IActionItemRepository
{
    public ActionItemRepository(AppDbContext context) : base(context)
    {
    }

    public async Task<IEnumerable<ActionItem>> GetByDepartmentIdAsync(Guid departmentId) =>
        await DbSet.Where(a => a.DepartmentId == departmentId).ToListAsync();

    public async Task<IEnumerable<ActionItem>> GetByUserIdAsync(Guid userId) =>
        await DbSet.Where(a => a.AssignedTo == userId).ToListAsync();

    public async Task<IEnumerable<ActionItem>> GetFilteredAsync(Guid? departmentId, Guid? assignedTo, Guid? hotelId)
    {
        var query = DbSet.Include(a => a.Review).AsQueryable();

        if (departmentId.HasValue)
        {
            var targetDept = await Context.Departments.FindAsync(departmentId.Value);
            if (targetDept != null)
            {
                query = query.Where(a => a.Department != null && a.Department.Key == targetDept.Key);
            }
            else
            {
                query = query.Where(a => a.DepartmentId == departmentId.Value);
            }
        }

        if (assignedTo.HasValue)
        {
            query = query.Where(a => a.AssignedTo == assignedTo.Value);
        }

        if (hotelId.HasValue)
        {
            query = query.Where(a => a.HotelId == hotelId.Value || (a.Review != null && a.Review.HotelId == hotelId.Value));
        }

        return await query.ToListAsync();
    }
}
