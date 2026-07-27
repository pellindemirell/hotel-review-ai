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

        var actionItems = await db.ActionItems
            .Include(a => a.Department)
            .Include(a => a.Review)
            .ToListAsync();

        Console.WriteLine($"Total Action Items: {actionItems.Count}");
        foreach (var a in actionItems)
        {
            Console.WriteLine($"ActionItem: {a.Title}");
            Console.WriteLine($"  - ActionItem.DepartmentId: {a.DepartmentId}");
            Console.WriteLine($"  - ActionItem.Department.Name: {a.Department?.Name}");
            Console.WriteLine($"  - ActionItem.Department.HotelId: {a.Department?.HotelId}");
            Console.WriteLine($"  - ActionItem.HotelId: {a.HotelId}");
            Console.WriteLine($"  - Review.HotelId: {a.Review?.HotelId}");
            Console.WriteLine("-------------------------");
        }

        var departments = await db.Departments.ToListAsync();
        Console.WriteLine($"\nTotal Departments: {departments.Count}");
        foreach (var d in departments)
        {
            Console.WriteLine($"Dept: {d.Name} | HotelId: {d.HotelId} | Id: {d.Id}");
        }
    }
}
