using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class UserConfiguration : IEntityTypeConfiguration<User>
{
    public void Configure(EntityTypeBuilder<User> entity)
    {
        entity.ToTable("Users");
        entity.HasKey(u => u.Id);
        entity.Property(u => u.Email).IsRequired().HasMaxLength(200);
        entity.HasIndex(u => u.Email).IsUnique().HasDatabaseName("IX_Users_Email");
        entity.Property(u => u.FullName).IsRequired().HasMaxLength(200);
        entity.Property(u => u.Role).IsRequired().HasMaxLength(50).HasConversion<string>();

        // PasswordHash: private field'a map, silinmesin diye explicit tanımla
        entity.Property(u => u.PasswordHash).HasColumnName("PasswordHash").IsRequired();

        // Denormalized kolonlar: join'siz sorgu kolaylığı için
        entity.Property(u => u.HotelName).HasMaxLength(200);
        entity.Property(u => u.DepartmentName).HasMaxLength(200);

        // Users → Departments (DepartmentId FK)
        entity.HasOne(u => u.Department)
              .WithMany(d => d.Users)
              .HasForeignKey(u => u.DepartmentId)
              .OnDelete(DeleteBehavior.SetNull);

        // Users → Hotels (HotelId FK)
        entity.HasOne(u => u.Hotel)
              .WithMany(h => h.Users)
              .HasForeignKey(u => u.HotelId)
              .OnDelete(DeleteBehavior.SetNull);
    }
}

