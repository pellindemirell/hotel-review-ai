using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Persistence.Contexts;
using HotelReviewAI.Persistence.Interceptors;
using HotelReviewAI.Persistence.Repositories;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace HotelReviewAI.Persistence;

public static class DependencyInjection
{
    public static IServiceCollection AddPersistence(
        this IServiceCollection services, IConfiguration configuration)
    {
        // AuditInterceptor'ı scoped olarak kaydet (ICurrentUserService'e bağlı olduğu için)
        services.AddScoped<AuditInterceptor>();

        // AppDbContext — AuditInterceptor constructor üzerinden inject edilir
        services.AddDbContext<AppDbContext>((sp, options) =>
        {
            options.UseNpgsql(configuration.GetConnectionString("DefaultConnection"));
        });

        // Repository kayıtları
        services.AddScoped<IHotelRepository, HotelRepository>();
        services.AddScoped<IUserRepository, UserRepository>();
        services.AddScoped<IReviewRepository, ReviewRepository>();
        services.AddScoped<IReviewAnalysisRepository, ReviewAnalysisRepository>();
        services.AddScoped<IReviewAttachmentRepository, ReviewAttachmentRepository>();
        services.AddScoped<IReviewCategoryRepository, ReviewCategoryRepository>();
        services.AddScoped<IDepartmentRepository, DepartmentRepository>();
        services.AddScoped<IActionItemRepository, ActionItemRepository>();
        services.AddScoped<IAuditLogRepository, AuditLogRepository>();

        // Şifre hash'leme — BCrypt implementasyonu Persistence katmanında tutulur
        services.AddScoped<IPasswordHasher, BcryptPasswordHasher>();


        return services;
    }
}
