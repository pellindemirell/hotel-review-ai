using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class ReviewCategoryConfiguration : IEntityTypeConfiguration<ReviewCategory>
{
    public void Configure(EntityTypeBuilder<ReviewCategory> entity)
    {
        entity.HasKey(c => c.Id);
        entity.Property(c => c.Key).IsRequired().HasMaxLength(100);
        entity.HasIndex(c => new { c.DepartmentId, c.Key }).IsUnique().HasDatabaseName("IX_ReviewCategories_DepartmentId_Key");
        entity.Property(c => c.Name).IsRequired().HasMaxLength(100);
        entity.Property(c => c.Keywords).HasColumnType("jsonb");

        entity.HasOne(c => c.Department)
              .WithMany(d => d.Categories)
              .HasForeignKey(c => c.DepartmentId)
              .OnDelete(DeleteBehavior.Restrict);
    }
}
