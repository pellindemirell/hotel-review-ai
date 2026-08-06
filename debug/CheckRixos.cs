using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore;
using HotelReviewAI.Persistence.Contexts;

class Program
{
    static async Task Main(string[] args)
    {
        var optionsBuilder = new DbContextOptionsBuilder<AppDbContext>();
        optionsBuilder.UseNpgsql("Host=192.168.40.140;Port=5432;Database=stajor;Username=stajor1;Password=stajor1*-");
        using var db = new AppDbContext(optionsBuilder.Options);

        var rixos = await db.Hotels.FirstOrDefaultAsync(h => h.Name.Contains("Rixos"));
        if (rixos == null)
        {
            Console.WriteLine("Rixos hotel not found.");
            return;
        }

        Console.WriteLine($"Found Hotel: {rixos.Name} (Id: {rixos.Id})");

        var reviews = await db.Reviews
            .Include(r => r.Analyses)
                .ThenInclude(a => a.Category)
            .Where(r => r.HotelId == rixos.Id)
            .ToListAsync();

        Console.WriteLine($"Total Reviews for Rixos: {reviews.Count}");
        
        var reviewsWithAnalysis = reviews.Count(r => r.Analyses.Any());
        Console.WriteLine($"Reviews with AI Analysis: {reviewsWithAnalysis}");

        var reviewsWithDepartment = reviews.Count(r => r.Analyses.Any(a => a.Category != null && a.Category.DepartmentId != null));
        Console.WriteLine($"Reviews linked to a Department (via Category): {reviewsWithDepartment}");

        if (reviews.Count > 0)
        {
            Console.WriteLine("\nSample Review:");
            var r = reviews.First();
            Console.WriteLine($"Comment: {r.Comment}");
            Console.WriteLine($"Analyses Count: {r.Analyses.Count}");
        }
    }
}
