using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class DepartmentConfiguration : IEntityTypeConfiguration<Department>
{
    public void Configure(EntityTypeBuilder<Department> entity)
    {
        entity.HasKey(d => d.Id);
        entity.Property(d => d.Key).IsRequired().HasMaxLength(100);
        entity.HasIndex(d => new { d.HotelId, d.Key }).IsUnique().HasDatabaseName("IX_Departments_HotelId_Key");
        entity.Property(d => d.Name).IsRequired().HasMaxLength(100);
    }
}
