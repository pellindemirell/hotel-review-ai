using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class ReviewAnalysisConfiguration : IEntityTypeConfiguration<ReviewAnalysis>
{
    public void Configure(EntityTypeBuilder<ReviewAnalysis> entity)
    {
        entity.HasKey(a => a.Id);
        entity.Property(a => a.ClauseText).IsRequired();
        entity.Property(a => a.Suggestion).HasMaxLength(500);

        // Keywords, Category arama sorgularında kullanılır
        entity.HasIndex(a => a.ReviewId).HasDatabaseName("IX_ReviewAnalyses_ReviewId");
        entity.HasIndex(a => a.Sentiment).HasDatabaseName("IX_ReviewAnalyses_Sentiment");
        entity.HasIndex(a => a.CategoryId).HasDatabaseName("IX_ReviewAnalyses_CategoryId");

        entity.HasOne(a => a.Category)
              .WithMany()
              .HasForeignKey(a => a.CategoryId)
              .OnDelete(DeleteBehavior.SetNull);

        // Keywords ve Summary JSON column olarak saklanır
        entity.Property(a => a.Keywords)
              .HasColumnType("jsonb");
    }
}
