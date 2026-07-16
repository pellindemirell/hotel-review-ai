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
        var departments = await SeedDepartmentsAsync(context);
        var categories = await SeedCategoriesAsync(context, departments);
        await SeedUsersAsync(context, departments);
        await SeedReviewsAsync(context, categories);
    }

    private static async Task<Dictionary<string, Department>> SeedDepartmentsAsync(AppDbContext context)
    {
        if (!await context.Departments.AnyAsync())
        {
            foreach (var (key, name) in DepartmentSeedData.Departments)
            {
                context.Departments.Add(new Department { Key = key, Name = name });
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

    private static async Task SeedUsersAsync(AppDbContext context, Dictionary<string, Department> departments)
    {
        if (await context.Users.AnyAsync())
        {
            return;
        }

        foreach (var (fullName, email, password, role, departmentKey) in UserSeedData.Users)
        {
            context.Users.Add(new User
            {
                FullName = fullName,
                Email = email,
                PasswordHash = BCrypt.Net.BCrypt.HashPassword(password),
                Role = role,
                DepartmentId = departmentKey is null ? null : departments[departmentKey].Id
            });
        }

        await context.SaveChangesAsync();
    }

    private static async Task SeedReviewsAsync(AppDbContext context, Dictionary<string, ReviewCategory> categories)
    {
        if (await context.Reviews.AnyAsync())
        {
            return;
        }

        var jsonPath = Path.Combine(AppContext.BaseDirectory, "seed-data", "reviews.json");
        if (!File.Exists(jsonPath))
        {
            return;
        }

        var json = await File.ReadAllTextAsync(jsonPath);
        var seedReviews = JsonSerializer.Deserialize<List<ReviewSeedDto>>(json, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        }) ?? [];

        foreach (var dto in seedReviews)
        {
            var review = Review.Create(
                guestName: dto.GuestName,
                comment: dto.Comment,
                rating: dto.Rating,
                language: dto.Language,
                source: Enum.Parse<ReviewSource>(dto.Source, ignoreCase: true),
                reviewDate: DateTime.SpecifyKind(dto.ReviewDate, DateTimeKind.Utc),
                createdBy: null);

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
