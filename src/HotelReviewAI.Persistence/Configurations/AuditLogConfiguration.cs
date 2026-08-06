using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class AuditLogConfiguration : IEntityTypeConfiguration<AuditLog>
{
    public void Configure(EntityTypeBuilder<AuditLog> entity)
    {
        entity.HasKey(a => a.Id);
        entity.Property(a => a.Action).IsRequired().HasMaxLength(100);
        entity.Property(a => a.EntityName).IsRequired().HasMaxLength(100);

        // Hızlı sorgulama için: "kim ne yaptı", "hangi entity değişti"
        entity.HasIndex(a => a.UserId).HasDatabaseName("IX_AuditLogs_UserId");
        entity.HasIndex(a => a.EntityName).HasDatabaseName("IX_AuditLogs_EntityName");
        entity.HasIndex(a => a.CreatedAt).HasDatabaseName("IX_AuditLogs_CreatedAt");
    }
}
