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

    private static List<string> GetHotelNamesFromSeedJson()
    {
        try
        {
            var assembly = typeof(DbSeeder).Assembly;
            var resourceName = "HotelReviewAI.Persistence.Seed.reviews.json";
            using var stream = assembly.GetManifestResourceStream(resourceName);
            if (stream == null) return [];
            using var reader = new System.IO.StreamReader(stream);
            var json = reader.ReadToEnd();
            var seedReviews = JsonSerializer.Deserialize<List<ReviewSeedDto>>(json, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            }) ?? [];
            return seedReviews
                .Select(r => r.HotelName)
                .Where(n => !string.IsNullOrWhiteSpace(n))
                .Select(n => n!.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();
        }
        catch
        {
            return [];
        }
    }

    private static async Task<List<Hotel>> SeedHotelsAsync(AppDbContext context)
    {
        var defaultNames = new List<string>
        {
            "Crystal Waterworld Resort & Spa",
            "Adora Hotel & Resort",
            "Megasaray Club Belek"
        };
        var jsonHotelNames = GetHotelNamesFromSeedJson();
        var allHotelNames = defaultNames.Concat(jsonHotelNames).Distinct(StringComparer.OrdinalIgnoreCase).ToList();

        var existingHotels = await context.Hotels.ToListAsync();
        var existingNames = existingHotels.Select(h => h.Name.Trim()).ToHashSet(StringComparer.OrdinalIgnoreCase);

        int codeCounter = existingHotels.Count + 1;
        bool addedAny = false;
        foreach (var name in allHotelNames)
        {
            if (!existingNames.Contains(name))
            {
                context.Hotels.Add(new Hotel
                {
                    Id = Guid.NewGuid(),
                    Name = name,
                    Code = codeCounter.ToString("D3"),
                    Address = "Belek, Antalya"
                });
                codeCounter++;
                addedAny = true;
            }
        }

        if (addedAny)
        {
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
        var allDepts = await context.Departments.ToListAsync();
        foreach (var hotel in hotels)
        {
            if (!allDepts.Any(d => d.HotelId == hotel.Id))
            {
                foreach (var (key, name) in DepartmentSeedData.Departments)
                {
                    context.Departments.Add(new Department { Key = key, Name = name, HotelId = hotel.Id });
                }
            }
        }
        await context.SaveChangesAsync();
        var defaultHotelId = hotels.FirstOrDefault()?.Id;
        return await context.Departments.Where(d => d.HotelId == defaultHotelId).ToDictionaryAsync(d => d.Key);
    }

    private static async Task<Dictionary<Guid, Dictionary<string, ReviewCategory>>> SeedCategoriesAsync(
        AppDbContext context, Dictionary<string, Department> defaultDepartments)
    {
        var allCategories = await context.ReviewCategories.ToListAsync();
        var allDepartments = await context.Departments.ToListAsync();
        var hotelIds = allDepartments.Where(d => d.HotelId.HasValue).Select(d => d.HotelId!.Value).Distinct().ToList();

        foreach (var hotelId in hotelIds)
        {
            var hotelDepts = allDepartments.Where(d => d.HotelId == hotelId).ToDictionary(d => d.Key);
            // Check if categories exist for this hotel's departments
            var firstDeptId = hotelDepts.Values.FirstOrDefault()?.Id;
            if (firstDeptId.HasValue && !allCategories.Any(c => c.DepartmentId == firstDeptId.Value))
            {
                foreach (var (key, name, keywords, departmentKey) in ReviewCategorySeedData.Categories)
                {
                    context.ReviewCategories.Add(new ReviewCategory
                    {
                        Key = key,
                        Name = name,
                        Keywords = keywords.ToList(),
                        DepartmentId = hotelDepts[departmentKey].Id
                    });
                }
            }
        }
        await context.SaveChangesAsync();
        // Return all categories grouped by HotelId
        var allDeptsWithCategories = await context.Departments
            .Include(d => d.Categories)
            .Where(d => d.HotelId.HasValue)
            .ToListAsync();
            
        var categoryLookup = allDeptsWithCategories
            .Where(d => d.Categories != null && d.Categories.Any())
            .GroupBy(d => d.HotelId!.Value)
            .ToDictionary(
                g => g.Key,
                g => g.SelectMany(d => d.Categories).ToDictionary(c => c.Key)
            );
            
        return categoryLookup;
    }

    private static async Task SeedUsersAsync(AppDbContext context, Dictionary<string, Department> departments, List<Hotel> hotels)
    {
        // Mevcut kayıt varsa: yeni eklenen HotelName / DepartmentName kolonlarını doldur, sonra çık.
        if (await context.Users.AnyAsync())
        {
            var hotelDict = hotels.ToDictionary(h => h.Id);
            var deptDict  = departments.Values.ToDictionary(d => d.Id);
            var crystalHotel = hotels.FirstOrDefault(h => h.Name == "Crystal Waterworld Resort & Spa") ?? hotels.FirstOrDefault();

            var usersToFill = await context.Users
                .Where(u => u.HotelName == null || u.DepartmentName == null)
                .ToListAsync();

            foreach (var u in usersToFill)
            {
                if (u.HotelName == null && u.HotelId.HasValue && hotelDict.TryGetValue(u.HotelId.Value, out var h))
                    u.HotelName = h.Name;

                if (u.DepartmentName == null && u.DepartmentId.HasValue && deptDict.TryGetValue(u.DepartmentId.Value, out var d))
                    u.DepartmentName = d.Name;
            }

            // [Hata Düzeltme]: Zaten var olan Yöneticilerin yanlış otele (örn. Adora) atanmış olma ihtimaline karşı:
            var managerEmails = UserSeedData.Users.Select(u => u.Email).ToList();
            var existingManagers = await context.Users.Where(u => managerEmails.Contains(u.Email)).ToListAsync();
            foreach (var manager in existingManagers)
            {
                if (manager.HotelId != crystalHotel?.Id)
                {
                    manager.HotelId = crystalHotel?.Id;
                    manager.HotelName = crystalHotel?.Name;
                }
            }

            if (usersToFill.Count > 0 || existingManagers.Count > 0)
                await context.SaveChangesAsync();

            // PasswordHash kolonu silinip geri eklendiyse (boş string) yeniden hash'le
            var usersWithoutPassword = await context.Users
                .Where(u => u.PasswordHash == string.Empty || u.PasswordHash == null)
                .ToListAsync();

            if (usersWithoutPassword.Count > 0)
            {
                // Bilinen admin kullanıcılarını orijinal şifresiyle, diğerlerini varsayılan şifreyle resetle
                var knownPasswords = UserSeedData.Users
                    .ToDictionary(u => u.Email, u => u.Password, StringComparer.OrdinalIgnoreCase);

                foreach (var u in usersWithoutPassword)
                {
                    var pwd = knownPasswords.TryGetValue(u.Email, out var known) ? known : "personel123";
                    u.SetPassword(pwd);
                }
                await context.SaveChangesAsync();
            }

            // Eksik bilinen (seed) kullanıcıları kontrol et ve ekle
            var existingDefaultHotel = hotels.FirstOrDefault(h => h.Name == "Crystal Waterworld Resort & Spa") ?? hotels.FirstOrDefault();
            var existingEmails = await context.Users.Select(u => u.Email).ToListAsync();
            var existingEmailSet = new HashSet<string>(existingEmails, StringComparer.OrdinalIgnoreCase);

            bool addedNew = false;
            foreach (var (fullName, email, password, role, departmentKey) in UserSeedData.Users)
            {
                if (!existingEmailSet.Contains(email))
                {
                    var dept = departmentKey is null ? null : departments[departmentKey];
                    var user = new User
                    {
                        FullName     = fullName,
                        Email        = email,
                        Role         = role,
                        DepartmentId = dept?.Id,
                        HotelId      = existingDefaultHotel?.Id
                    };
                    user.SetPassword(password);
                    context.Users.Add(user);
                    addedNew = true;
                }
            }

            if (addedNew)
            {
                await context.SaveChangesAsync();
            }
        }
        else
        {
            var defaultHotel = hotels.FirstOrDefault(h => h.Name == "Crystal Waterworld Resort & Spa") ?? hotels.FirstOrDefault();
            foreach (var (fullName, email, password, role, departmentKey) in UserSeedData.Users)
            {
                var dept = departmentKey is null ? null : departments[departmentKey];
                var user = new User
                {
                    FullName     = fullName,
                    Email        = email,
                    Role         = role,
                    DepartmentId = dept?.Id,
                    HotelId      = defaultHotel?.Id
                };
                user.SetPassword(password);
                context.Users.Add(user);
            }
            await context.SaveChangesAsync();
        }

        // Mevcut E-postaları al (Toplu personel veya diğer seed personellerin tekrar eklenmesini önlemek için)
        var existingEmails = await context.Users.Select(u => u.Email).ToListAsync();
        var existingEmailSet = new HashSet<string>(existingEmails, StringComparer.OrdinalIgnoreCase);

        bool addedNewBulk = false;

        // Her otel için 50 personel oluştur; her departmanda en az 2 kişi
        const int personnelPerHotel = 50;
        var departmentKeys = DepartmentSeedData.Departments.Select(d => d.Key).ToArray();
        var rng = new Random(42); // Tekrarlanabilir seed

        // Otel başına e-posta çakışmasını önlemek için global sayaç
        int globalCounter = 1;

        foreach (var hotel in hotels)
        {
            var deptCounts = UserSeedData.GetPersonnelCountPerDepartment(personnelPerHotel, departmentKeys);

            foreach (var deptKey in departmentKeys)
            {
                int count = deptCounts[deptKey];
                var department = departments[deptKey];

                for (int i = 0; i < count; i++)
                {
                    var firstName = UserSeedData.FirstNames[rng.Next(UserSeedData.FirstNames.Length)];
                    var lastName  = UserSeedData.LastNames[rng.Next(UserSeedData.LastNames.Length)];
                    var fullName  = $"{firstName} {lastName}";

                    // Benzersiz e-posta: user<sayaç>@<otelSlug>.com
                    var hotelSlug = new string(hotel.Name
                        .ToLowerInvariant()
                        .Where(c => char.IsLetterOrDigit(c))
                        .Take(12)
                        .ToArray());
                    var email = $"user{globalCounter++}@{hotelSlug}.com";

                    if (!existingEmailSet.Contains(email))
                    {
                        var personnelUser = new User
                        {
                            FullName     = fullName,
                            Email        = email,
                            Role         = Roles.DepartmentUser,
                            DepartmentId = department.Id,
                            HotelId      = hotel.Id
                        };
                        personnelUser.SetPassword("personel123");
                        context.Users.Add(personnelUser);
                        addedNewBulk = true;
                    }
                }
            }
        }

        if (addedNewBulk)
        {
            await context.SaveChangesAsync();
        }
    }


    private static async Task SeedReviewsAsync(AppDbContext context, Dictionary<Guid, Dictionary<string, ReviewCategory>> categories, List<Hotel> hotels)
    {
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

        var existingComments = await context.Reviews.Select(r => r.Comment).ToListAsync();
        var existingSet = new HashSet<string>(existingComments, StringComparer.OrdinalIgnoreCase);

        seedReviews = seedReviews.Where(r => !existingSet.Contains(r.Comment)).ToList();

        if (seedReviews.Count == 0)
        {
            return;
        }

        var hotelDict = hotels.ToDictionary(h => h.Name.Trim(), StringComparer.OrdinalIgnoreCase);

        int index = 0;
        foreach (var dto in seedReviews)
        {
            Hotel? assignedHotel = null;
            if (!string.IsNullOrWhiteSpace(dto.HotelName) && hotelDict.TryGetValue(dto.HotelName.Trim(), out var foundHotel))
            {
                assignedHotel = foundHotel;
            }
            else if (hotels.Count > 0)
            {
                assignedHotel = hotels[index % hotels.Count];
            }
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

            var hotelCategories = assignedHotel != null && categories.ContainsKey(assignedHotel.Id) 
                ? categories[assignedHotel.Id] 
                : categories.Values.FirstOrDefault() ?? new Dictionary<string, ReviewCategory>();
            review.AddAnalysis(SimulateAnalysis(dto, hotelCategories));

            context.Reviews.Add(review);
        }

        await context.SaveChangesAsync();
    }

    // AI servisi henüz entegre edilmediği için, demo/dashboard verisinin anlamlı görünmesi adına
    // rating'e göre basit bir sentiment simülasyonu ve anahtar kelime eşleşmesiyle kategori tahmini yapılır.
    // Gerçek AI entegrasyonu tamamlandığında bu metot kaldırılıp gerçek analiz sonucu kullanılacaktır.
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
            Sentiment.Negative when score <= -0.8 => Priority.Critical,
            Sentiment.Negative when score <= -0.5 => Priority.High,
            Sentiment.Negative => Priority.Medium,
            _ => Priority.Info
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
