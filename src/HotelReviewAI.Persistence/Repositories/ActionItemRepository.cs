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

    public async Task<IEnumerable<ActionItem>> GetByAssignedStaffIdAsync(Guid staffId) =>
        await DbSet
            .Include(a => a.Review)
            .Where(a => a.AssignedStaffId == staffId)
            // En yeni önce: yönetici genelde son verdiği işi arıyor.
            .OrderByDescending(a => a.UpdatedAt ?? a.CreatedAt)
            .ToListAsync();

    public async Task<IEnumerable<ActionItem>> GetByReviewIdAsync(Guid reviewId) =>
        await DbSet.Where(a => a.ReviewId == reviewId).ToListAsync();

    public async Task<IEnumerable<ActionItem>> GetByDepartmentIdAsync(Guid departmentId) =>
        await DbSet.Where(a => a.DepartmentId == departmentId).ToListAsync();

    public async Task<IEnumerable<ActionItem>> GetByUserIdAsync(Guid userId) =>
        await DbSet.Where(a => a.AssignedTo == userId).ToListAsync();

    public async Task<IEnumerable<ActionItem>> GetFilteredAsync(Guid? departmentId, Guid? assignedTo, Guid? hotelId)
    {
        // AssignedStaff da yüklenmeli: ActionItemDetailsDto.AssignedStaffName
        // bu ilişkiden doldurulur. Include olmadan isim sessizce null kalır
        // (aynı hatayı Reviews listesinde Attachments ile yaşamıştık).
        var query = DbSet
            .Include(a => a.Review)
            .Include(a => a.AssignedStaff)
            .AsQueryable();

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
