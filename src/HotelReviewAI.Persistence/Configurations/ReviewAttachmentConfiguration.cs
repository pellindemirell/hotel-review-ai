using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace HotelReviewAI.Persistence.Configurations;

public class ReviewAttachmentConfiguration : IEntityTypeConfiguration<ReviewAttachment>
{
    public void Configure(EntityTypeBuilder<ReviewAttachment> entity)
    {
        entity.HasKey(a => a.Id);
        entity.Property(a => a.FileUrl).IsRequired();
        entity.Property(a => a.FileType).IsRequired().HasMaxLength(50);
    }
}
