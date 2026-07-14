using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Contexts;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<Review> Reviews => Set<Review>();
    public DbSet<ReviewAnalysis> ReviewAnalyses => Set<ReviewAnalysis>();
    public DbSet<ReviewAttachment> ReviewAttachments => Set<ReviewAttachment>();
    public DbSet<ReviewCategory> ReviewCategories => Set<ReviewCategory>();
    public DbSet<ActionItem> ActionItems => Set<ActionItem>();
    public DbSet<AuditLog> AuditLogs => Set<AuditLog>();
    public DbSet<User> Users => Set<User>();
    public DbSet<Department> Departments => Set<Department>();


 //verıtabanı kuralları onetoone ilişkisi analiz yaptır yorum silinirse analizi sil
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // Review
        modelBuilder.Entity<Review>(entity =>
        {
            entity.HasKey(r => r.Id);
            entity.Property(r => r.GuestName).IsRequired().HasMaxLength(200);
            entity.Property(r => r.Comment).IsRequired();
            entity.Property(r => r.Language).HasMaxLength(10);
            entity.Property(r => r.Rating).IsRequired();

            entity.HasOne(r => r.Analysis)
                  .WithOne(a => a.Review)
                  .HasForeignKey<ReviewAnalysis>(a => a.ReviewId)
                  .OnDelete(DeleteBehavior.Cascade);

            entity.HasMany(r => r.Attachments)
                  .WithOne(a => a.Review)
                  .HasForeignKey(a => a.ReviewId)
                  .OnDelete(DeleteBehavior.Cascade);

            entity.HasMany(r => r.ActionItems)
                  .WithOne(a => a.Review)
                  .HasForeignKey(a => a.ReviewId)
                  .OnDelete(DeleteBehavior.Cascade);
        });

        // ReviewAnalysis - Keywords stored as JSON
        modelBuilder.Entity<ReviewAnalysis>(entity =>
        {
            entity.HasKey(a => a.Id);
            entity.Property(a => a.Keywords)
                  .HasColumnType("jsonb");
        });

        // ReviewCategory - Keywords stored as JSON
        modelBuilder.Entity<ReviewCategory>(entity =>
        {
            entity.HasKey(c => c.Id);
            entity.Property(c => c.Name).IsRequired().HasMaxLength(100);
            entity.Property(c => c.Keywords)
                  .HasColumnType("jsonb");

            entity.HasOne(c => c.Department)
                  .WithMany(d => d.Categories)
                  .HasForeignKey(c => c.DepartmentId)
                  .OnDelete(DeleteBehavior.Restrict);
        });

        // ReviewAttachment
        modelBuilder.Entity<ReviewAttachment>(entity =>
        {
            entity.HasKey(a => a.Id);
            entity.Property(a => a.FileUrl).IsRequired();
            entity.Property(a => a.FileType).IsRequired().HasMaxLength(50);
        });

        // ActionItem
        modelBuilder.Entity<ActionItem>(entity =>
        {
            entity.HasKey(a => a.Id);
            entity.Property(a => a.Title).IsRequired().HasMaxLength(300);

            entity.HasOne(a => a.Department)
                  .WithMany(d => d.ActionItems)
                  .HasForeignKey(a => a.DepartmentId)
                  .OnDelete(DeleteBehavior.Restrict);

            entity.HasOne(a => a.AssignedUser)
                  .WithMany()
                  .HasForeignKey(a => a.AssignedTo)
                  .OnDelete(DeleteBehavior.SetNull);
        });

        // Department
        modelBuilder.Entity<Department>(entity =>
        {
            entity.HasKey(d => d.Id);
            entity.Property(d => d.Name).IsRequired().HasMaxLength(100);
        });

        // User
        modelBuilder.Entity<User>(entity =>
        {
            entity.HasKey(u => u.Id);
            entity.Property(u => u.Email).IsRequired().HasMaxLength(200);
            entity.HasIndex(u => u.Email).IsUnique();
            entity.Property(u => u.FullName).IsRequired().HasMaxLength(200);
            entity.Property(u => u.Role).IsRequired().HasMaxLength(50);

            entity.HasOne(u => u.Department)
                  .WithMany(d => d.Users)
                  .HasForeignKey(u => u.DepartmentId)
                  .OnDelete(DeleteBehavior.SetNull);
        });

        // AuditLog
        modelBuilder.Entity<AuditLog>(entity =>
        {
            entity.HasKey(a => a.Id);
            entity.Property(a => a.Action).IsRequired().HasMaxLength(100);
            entity.Property(a => a.EntityName).IsRequired().HasMaxLength(100);
        });
    }
}