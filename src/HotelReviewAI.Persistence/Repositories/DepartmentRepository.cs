using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;
using HotelReviewAI.Persistence.Seed;

namespace HotelReviewAI.Persistence.Repositories;

public class DepartmentRepository : GenericRepository<Department>, IDepartmentRepository
{
    public DepartmentRepository(AppDbContext context) : base(context)
    {
    }

    // Departmanlar her otelde aynı sırayla görünsün diye DepartmentSeedData'daki
    // kanonik sıraya göre diziliyor. Sorguda ORDER BY olmadığında PostgreSQL satırları
    // rastgele sırada döndürüyordu ve otel değiştirince menüdeki sıra değişiyordu.
    private static readonly Dictionary<string, int> CanonicalOrder =
        DepartmentSeedData.Departments
            .Select((d, index) => (d.Key, index))
            .ToDictionary(x => x.Key, x => x.index, StringComparer.OrdinalIgnoreCase);

    public async Task<List<Department>> GetDepartmentsAsync(Guid? hotelId = null)
    {
        var query = DbSet.AsQueryable();

        if (hotelId.HasValue)
        {
            query = query.Where(d => d.HotelId == hotelId.Value);
        }

        var departments = await Microsoft.EntityFrameworkCore.EntityFrameworkQueryableExtensions.ToListAsync(query);

        // Seed'de bulunmayan (sonradan eklenmiş) departmanlar sona, kendi aralarında ada göre.
        return departments
            .OrderBy(d => CanonicalOrder.TryGetValue(d.Key, out var index) ? index : int.MaxValue)
            .ThenBy(d => d.Name, StringComparer.CurrentCulture)
            .ToList();
    }
}
