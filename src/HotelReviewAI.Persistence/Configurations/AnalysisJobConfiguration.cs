using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class AnalysisJobConfiguration : IEntityTypeConfiguration<AnalysisJob>
{
    public void Configure(EntityTypeBuilder<AnalysisJob> entity)
    {
        entity.HasKey(j => j.Id);

        // Kuyruk kapma sorgusu (ClaimPendingAsync) Status'e göre filtreleyip
        // CreatedAt'e göre sıralıyor ve saniyede bir çalışıyor; tabloda şu ana
        // kadar yalnızca birincil anahtar vardı.
        entity.HasIndex(j => new { j.Status, j.CreatedAt })
              .HasDatabaseName("IX_AnalysisJobs_Status_CreatedAt");

        // ReviewId'de kasıtlı olarak FK yok (iş kaydı, yorum silinse de denetim
        // için kalabiliyor); ancak yoruma göre arama yapılıyor.
        entity.HasIndex(j => j.ReviewId)
              .HasDatabaseName("IX_AnalysisJobs_ReviewId");
    }
}
