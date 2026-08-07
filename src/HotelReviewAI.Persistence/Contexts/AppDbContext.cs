using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
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
    public DbSet<AnalysisJob> AnalysisJobs => Set<AnalysisJob>();
    public DbSet<StaffMember> StaffMembers => Set<StaffMember>();

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

        // "stajor" veritabanı başka ekiplerle ortak kullanılıyor ve Users tablosuna
        // bizim UserRole enum'umuzda karşılığı olmayan roller yazılıyor
        // ('DepartmentUser', 'Manager', 'Admin', 'MobileUser' — 03.08.2026'da 261 satır).
        // EF bu satırları materialize ederken InvalidOperationException fırlatıyor ve
        // kullanıcıya dokunan HER uç (personel listesi, aksiyon atamaları) 500 veriyordu.
        // Çözüm veri tarafında değil bizde: bilmediğimiz roller SQL seviyesinde elenir,
        // böylece ortak veritabanına dokunmadan yabancı satırlar hiç yüklenmez.
        // NOT: Bu filtre yukarıdaki döngünün ATADIĞI soft-delete filtresinin yerine
        // geçer, o yüzden IsActive koşulu burada tekrar ediliyor.
        modelBuilder.Entity<User>()
            .HasQueryFilter(u => u.IsActive && KnownUserRoles.Contains(u.Role));
    }

    /// <summary>Uygulamanın tanıdığı roller; ortak veritabanındaki yabancı satırları elemek için.</summary>
    private static readonly UserRole[] KnownUserRoles = Enum.GetValues<UserRole>();

    private static System.Linq.Expressions.LambdaExpression ConvertFilterExpression(Type type)
    {
        var parameter = System.Linq.Expressions.Expression.Parameter(type, "e");
        var property = System.Linq.Expressions.Expression.Property(parameter, nameof(BaseEntity.IsActive));
        var trueConstant = System.Linq.Expressions.Expression.Constant(true);
        var body = System.Linq.Expressions.Expression.Equal(property, trueConstant);
        return System.Linq.Expressions.Expression.Lambda(body, parameter);
    }
}