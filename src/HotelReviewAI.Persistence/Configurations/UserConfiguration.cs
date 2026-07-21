using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class UserConfiguration : IEntityTypeConfiguration<User>
{
    public void Configure(EntityTypeBuilder<User> entity)
    {
        entity.HasKey(u => u.Id);
        entity.Property(u => u.Email).IsRequired().HasMaxLength(200);
        entity.HasIndex(u => u.Email).IsUnique().HasDatabaseName("IX_Users_Email");
        entity.Property(u => u.FullName).IsRequired().HasMaxLength(200);
        entity.Property(u => u.Role).IsRequired().HasMaxLength(50);

        entity.HasOne(u => u.Department)
              .WithMany(d => d.Users)
              .HasForeignKey(u => u.DepartmentId)
              .OnDelete(DeleteBehavior.SetNull);
    }
}
