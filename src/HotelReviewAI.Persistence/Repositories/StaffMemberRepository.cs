using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

public class StaffMemberRepository : GenericRepository<StaffMember>, IStaffMemberRepository
{
    public StaffMemberRepository(AppDbContext context) : base(context)
    {
    }

    public async Task<IEnumerable<StaffMember>> GetByDepartmentIdAsync(Guid departmentId) =>
        await DbSet
            .Where(s => s.DepartmentId == departmentId && s.IsActive)
            .OrderBy(s => s.FirstName)
            .ThenBy(s => s.LastName)
            .ToListAsync();

    public async Task<Dictionary<Guid, string>> GetNamesByIdsAsync(IEnumerable<Guid> ids)
    {
        var idList = ids.Distinct().ToList();
        if (idList.Count == 0)
        {
            return [];
        }

        // IgnoreQueryFilters: ekipten çıkarılmış çalışanın adı da okunmalı,
        // yoksa geçmiş görevlerdeki "kime verdim" notu boşa düşer.
        var rows = await DbSet
            .IgnoreQueryFilters()
            .Where(s => idList.Contains(s.Id))
            .Select(s => new { s.Id, s.FirstName, s.LastName })
            .ToListAsync();

        return rows.ToDictionary(r => r.Id, r => $"{r.FirstName} {r.LastName}".Trim());
    }
}
