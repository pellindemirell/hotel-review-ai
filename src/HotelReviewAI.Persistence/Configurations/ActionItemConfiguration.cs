using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class ActionItemConfiguration : IEntityTypeConfiguration<ActionItem>
{
    public void Configure(EntityTypeBuilder<ActionItem> entity)
    {
        entity.HasKey(a => a.Id);
        entity.Property(a => a.Title).IsRequired().HasMaxLength(300);

        // Departman ve durum filtreleme sorguları için index
        entity.HasIndex(a => a.DepartmentId).HasDatabaseName("IX_ActionItems_DepartmentId");
        entity.HasIndex(a => a.Status).HasDatabaseName("IX_ActionItems_Status");
        entity.HasIndex(a => a.AssignedTo).HasDatabaseName("IX_ActionItems_AssignedTo");

        entity.HasOne(a => a.Department)
              .WithMany(d => d.ActionItems)
              .HasForeignKey(a => a.DepartmentId)
              .OnDelete(DeleteBehavior.Restrict);

        entity.HasOne(a => a.AssignedUser)
              .WithMany()
              .HasForeignKey(a => a.AssignedTo)
              .OnDelete(DeleteBehavior.SetNull);

        entity.HasOne(a => a.Category)
              .WithMany()
              .HasForeignKey(a => a.CategoryId)
              .OnDelete(DeleteBehavior.SetNull);
    }
}
