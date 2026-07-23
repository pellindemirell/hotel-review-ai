using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Interceptors;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Contexts;

public class AppDbContext : DbContext
{
    private readonly AuditInterceptor _auditInterceptor;

    public AppDbContext(DbContextOptions<AppDbContext> options, AuditInterceptor auditInterceptor)
        : base(options)
    {
        _auditInterceptor = auditInterceptor;
    }

    public DbSet<Review> Reviews => Set<Review>();
    public DbSet<ReviewAnalysis> ReviewAnalyses => Set<ReviewAnalysis>();
    public DbSet<ReviewAttachment> ReviewAttachments => Set<ReviewAttachment>();
    public DbSet<ReviewCategory> ReviewCategories => Set<ReviewCategory>();
    public DbSet<ActionItem> ActionItems => Set<ActionItem>();
    public DbSet<AuditLog> AuditLogs => Set<AuditLog>();
    public DbSet<User> Users => Set<User>();
    public DbSet<Department> Departments => Set<Department>();
    public DbSet<Hotel> Hotels => Set<Hotel>();

    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        // AuditInterceptor EF pipeline'ına eklenir
        optionsBuilder.AddInterceptors(_auditInterceptor);
    }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // Configurations/ klasöründeki tüm IEntityTypeConfiguration<T> sınıfları otomatik yüklenir
        modelBuilder.ApplyConfigurationsFromAssembly(typeof(AppDbContext).Assembly);

        // Soft delete: Global query filter for IsActive == true
        foreach (var entityType in modelBuilder.Model.GetEntityTypes())
        {
            if (typeof(BaseEntity).IsAssignableFrom(entityType.ClrType))
            {
                modelBuilder.Entity(entityType.ClrType).HasQueryFilter(ConvertFilterExpression(entityType.ClrType));
            }
        }
    }

    private static System.Linq.Expressions.LambdaExpression ConvertFilterExpression(Type type)
    {
        var parameter = System.Linq.Expressions.Expression.Parameter(type, "e");
        var property = System.Linq.Expressions.Expression.Property(parameter, nameof(BaseEntity.IsActive));
        var trueConstant = System.Linq.Expressions.Expression.Constant(true);
        var body = System.Linq.Expressions.Expression.Equal(property, trueConstant);
        return System.Linq.Expressions.Expression.Lambda(body, parameter);
    }
}