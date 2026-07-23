using System.Text.Json;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Seed;

public static class DbSeeder
{
    public static async Task SeedAsync(AppDbContext context)
    {
        // Eğer veritabanı sağlayıcısı PostgreSQL ise eşzamanlı çalıştırma çakışmalarını önlemek için advisory lock kullanalım.
        if (context.Database.IsNpgsql())
        {
            using var transaction = await context.Database.BeginTransactionAsync();
            try
            {
                // İşlem seviyesinde (transaction-level) advisory lock edinilir.
                // Bu kilit, işlem Commit veya Rollback edildiğinde PostgreSQL tarafından otomatik olarak bırakılır.
                await context.Database.ExecuteSqlRawAsync("SELECT pg_advisory_xact_lock(888123);");

                var hotels = await SeedHotelsAsync(context);
                var departments = await SeedDepartmentsAsync(context, hotels);
                var categories = await SeedCategoriesAsync(context, departments);
                await SeedUsersAsync(context, departments, hotels);
                await SeedReviewsAsync(context, categories, hotels);

                await transaction.CommitAsync();
            }
            catch (Exception)
            {
                await transaction.RollbackAsync();
                throw;
            }
        }
        else
        {
            var hotels = await SeedHotelsAsync(context);
            var departments = await SeedDepartmentsAsync(context, hotels);
            var categories = await SeedCategoriesAsync(context, departments);
            await SeedUsersAsync(context, departments, hotels);
            await SeedReviewsAsync(context, categories, hotels);
        }
    }

    private static async Task<List<Hotel>> SeedHotelsAsync(AppDbContext context)
    {
        // Eski özel/sabit ID'li oteller varsa temizle
        var existingHotels = await context.Hotels.ToListAsync();
        if (existingHotels.Count > 0)
        {
            var oldHotelIds = existingHotels.Select(h => (Guid?)h.Id).ToList();
            var linkedReviews = await context.Reviews.Where(r => oldHotelIds.Contains(r.HotelId)).ToListAsync();
            foreach (var r in linkedReviews) { r.HotelId = null; }
            var linkedUsers = await context.Users.Where(u => oldHotelIds.Contains(u.HotelId)).ToListAsync();
            foreach (var u in linkedUsers) { u.HotelId = null; }
            var linkedDepts = await context.Departments.Where(d => oldHotelIds.Contains(d.HotelId)).ToListAsync();
            foreach (var d in linkedDepts) { d.HotelId = null; }

            context.Hotels.RemoveRange(existingHotels);
            await context.SaveChangesAsync();
        }

        if (!await context.Hotels.AnyAsync())
        {
            var hotels = new List<Hotel>
            {
                new Hotel { Id = Guid.NewGuid(), Name = "Crystal Waterworld Resort & Spa", Code = "001", Address = "Belek, Antalya" },
                new Hotel { Id = Guid.NewGuid(), Name = "Adora Hotel & Resort", Code = "002", Address = "Belek, Antalya" },
                new Hotel { Id = Guid.NewGuid(), Name = "Megasaray Club Belek", Code = "003", Address = "Belek, Antalya" }
            };

            context.Hotels.AddRange(hotels);
            await context.SaveChangesAsync();
        }

        var allHotels = await context.Hotels.ToListAsync();

        // Mevcut kayıtlarda HotelId null olanları otellere dağıt
        var unassignedReviews = await context.Reviews.Where(r => r.HotelId == null).ToListAsync();
        if (unassignedReviews.Count > 0 && allHotels.Count > 0)
        {
            int idx = 0;
            foreach (var r in unassignedReviews)
            {
                r.HotelId = allHotels[idx % allHotels.Count].Id;
                idx++;
            }
        }

        var unassignedUsers = await context.Users.Where(u => u.HotelId == null).ToListAsync();
        if (unassignedUsers.Count > 0 && allHotels.Count > 0)
        {
            foreach (var u in unassignedUsers)
            {
                u.HotelId = allHotels[0].Id;
            }
        }

        var unassignedDepts = await context.Departments.Where(d => d.HotelId == null).ToListAsync();
        if (unassignedDepts.Count > 0 && allHotels.Count > 0)
        {
            foreach (var d in unassignedDepts)
            {
                d.HotelId = allHotels[0].Id;
            }
        }

        await context.SaveChangesAsync();
        return allHotels;
    }

    private static async Task<Dictionary<string, Department>> SeedDepartmentsAsync(AppDbContext context, List<Hotel> hotels)
    {
        if (!await context.Departments.AnyAsync())
        {
            var defaultHotelId = hotels.FirstOrDefault()?.Id;
            foreach (var (key, name) in DepartmentSeedData.Departments)
            {
                context.Departments.Add(new Department { Key = key, Name = name, HotelId = defaultHotelId });
            }

            await context.SaveChangesAsync();
        }

        return await context.Departments.ToDictionaryAsync(d => d.Key);
    }

    private static async Task<Dictionary<string, ReviewCategory>> SeedCategoriesAsync(
        AppDbContext context, Dictionary<string, Department> departments)
    {
        if (!await context.ReviewCategories.AnyAsync())
        {
            foreach (var (key, name, keywords, departmentKey) in ReviewCategorySeedData.Categories)
            {
                context.ReviewCategories.Add(new ReviewCategory
                {
                    Key = key,
                    Name = name,
                    Keywords = keywords.ToList(),
                    DepartmentId = departments[departmentKey].Id
                });
            }

            await context.SaveChangesAsync();
        }

        return await context.ReviewCategories.ToDictionaryAsync(c => c.Key);
    }

    private static async Task SeedUsersAsync(AppDbContext context, Dictionary<string, Department> departments, List<Hotel> hotels)
    {
        if (await context.Users.AnyAsync())
        {
            return;
        }

        var defaultHotelId = hotels.FirstOrDefault()?.Id;
        foreach (var (fullName, email, password, role, departmentKey) in UserSeedData.Users)
        {
            context.Users.Add(new User
            {
                FullName = fullName,
                Email = email,
                PasswordHash = BCrypt.Net.BCrypt.HashPassword(password),
                Role = role,
                DepartmentId = departmentKey is null ? null : departments[departmentKey].Id,
                HotelId = defaultHotelId
            });
        }

        await context.SaveChangesAsync();
    }

    private static async Task SeedReviewsAsync(AppDbContext context, Dictionary<string, ReviewCategory> categories, List<Hotel> hotels)
    {
        if (await context.Reviews.CountAsync() > 10)
        {
            return;
        }

        var assembly = typeof(DbSeeder).Assembly;
        var resourceName = "HotelReviewAI.Persistence.Seed.reviews.json";

        using var stream = assembly.GetManifestResourceStream(resourceName);
        if (stream == null)
        {
            return;
        }

        using var reader = new System.IO.StreamReader(stream);
        var json = await reader.ReadToEndAsync();

        var seedReviews = JsonSerializer.Deserialize<List<ReviewSeedDto>>(json, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        }) ?? [];

        int index = 0;
        foreach (var dto in seedReviews)
        {
            // Assign review round-robin to one of the 3 hotels
            var assignedHotel = hotels.Count > 0 ? hotels[index % hotels.Count] : null;
            index++;

            var review = Review.Create(
                guestName: dto.GuestName,
                comment: dto.Comment,
                rating: dto.Rating,
                language: dto.Language,
                source: Enum.Parse<ReviewSource>(dto.Source, ignoreCase: true),
                reviewDate: DateTime.SpecifyKind(dto.ReviewDate, DateTimeKind.Utc),
                createdBy: null,
                hotelId: assignedHotel?.Id);

            review.Analyses.Add(SimulateAnalysis(dto, categories));

            context.Reviews.Add(review);
        }

        await context.SaveChangesAsync();
    }

    // AI servisi henüz entegre edilmediği için, demo/dashboard verisinin anlamlı görünmesi adına
    // rating'e göre basit bir sentiment simülasyonu ve anahtar kelime eşleşmesiyle kategori tahmini yapılır.
    // Gerçek AI entegrasyonu (Aşama 8) tamamlandığında bu metot kaldırılıp gerçek analiz sonucu kullanılacaktır.
    private static ReviewAnalysis SimulateAnalysis(ReviewSeedDto dto, Dictionary<string, ReviewCategory> categories)
    {
        var (sentiment, score) = dto.Rating switch
        {
            <= 2 => (Sentiment.Negative, dto.Rating == 1 ? -0.9 : -0.6),
            3 => (Sentiment.Neutral, 0.0),
            _ => (Sentiment.Positive, dto.Rating == 5 ? 0.9 : 0.6)
        };

        var priority = sentiment switch
        {
            Sentiment.Negative when score <= -0.8 => Priority.Kritik,
            Sentiment.Negative when score <= -0.5 => Priority.Yuksek,
            Sentiment.Negative => Priority.Orta,
            _ => Priority.Bilgi
        };

        var category = FindMatchingCategory(dto.Comment, categories);

        return new ReviewAnalysis
        {
            ClauseIndex = 0,
            ClauseText = dto.Comment,
            Sentiment = sentiment,
            SentimentScore = score,
            Priority = priority,
            CategoryId = category?.Id,
            Confidence = 0.85
        };
    }

    private static ReviewCategory? FindMatchingCategory(string comment, Dictionary<string, ReviewCategory> categories)
    {
        var lowerComment = comment.ToLowerInvariant();

        foreach (var category in categories.Values)
        {
            if (category.Keywords.Any(keyword => lowerComment.Contains(keyword.ToLowerInvariant())))
            {
                return category;
            }
        }

        return categories.GetValueOrDefault("general_atmosphere");
    }
}
