using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class StaffMemberConfiguration : IEntityTypeConfiguration<StaffMember>
{
    public void Configure(EntityTypeBuilder<StaffMember> entity)
    {
        entity.HasKey(s => s.Id);

        entity.Property(s => s.FirstName).IsRequired().HasMaxLength(100);
        entity.Property(s => s.LastName).IsRequired().HasMaxLength(100);
        entity.Property(s => s.Title).HasMaxLength(120);

        // FullName hesaplanan bir özellik; kolon olarak yazılmamalı.
        entity.Ignore(s => s.FullName);

        // Listeleme her zaman departman kırılımıyla yapılıyor.
        entity.HasIndex(s => s.DepartmentId).HasDatabaseName("IX_StaffMembers_DepartmentId");

        entity.HasOne(s => s.Department)
              .WithMany()
              .HasForeignKey(s => s.DepartmentId)
              .OnDelete(DeleteBehavior.Restrict);

        entity.HasOne(s => s.Hotel)
              .WithMany()
              .HasForeignKey(s => s.HotelId)
              .OnDelete(DeleteBehavior.SetNull);
    }
}
