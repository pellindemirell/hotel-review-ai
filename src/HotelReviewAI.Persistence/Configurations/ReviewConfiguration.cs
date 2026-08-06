using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class ReviewConfiguration : IEntityTypeConfiguration<Review>
{
    public void Configure(EntityTypeBuilder<Review> entity)
    {
        entity.HasKey(r => r.Id);
        entity.Property(r => r.GuestName).IsRequired().HasMaxLength(200);
        entity.Property(r => r.Comment).IsRequired();
        entity.Property(r => r.Language).HasMaxLength(10);
        entity.Property(r => r.Rating).IsRequired();

        // Performans index'leri: filtreleme ve sıralama sorgularında kullanılır
        entity.HasIndex(r => r.ReviewDate).HasDatabaseName("IX_Reviews_ReviewDate");
        entity.HasIndex(r => r.Rating).HasDatabaseName("IX_Reviews_Rating");
        entity.HasIndex(r => r.Source).HasDatabaseName("IX_Reviews_Source");
        entity.HasIndex(r => r.IsActive).HasDatabaseName("IX_Reviews_IsActive");

        // Dashboard sorgularının tamamının sürükleyici filtresi (otel + tarih aralığı).
        // Kısmi koşul global "IsActive == true" query filter'ıyla birebir eşleştiği
        // için her dashboard okumasında kullanılabilir ve indeks küçük kalır.
        entity.HasIndex(r => new { r.HotelId, r.ReviewDate })
              .HasDatabaseName("IX_Reviews_HotelId_ReviewDate")
              .HasFilter("\"IsActive\"");

        entity.HasMany(r => r.Analyses)
              .WithOne(a => a.Review)
              .HasForeignKey(a => a.ReviewId)
              .OnDelete(DeleteBehavior.Cascade);

        entity.HasMany(r => r.Attachments)
              .WithOne(a => a.Review)
              .HasForeignKey(a => a.ReviewId)
              .OnDelete(DeleteBehavior.Cascade);

        entity.HasMany(r => r.ActionItems)
              .WithOne(a => a.Review)
              .HasForeignKey(a => a.ReviewId)
              .OnDelete(DeleteBehavior.Cascade);
    }
}
