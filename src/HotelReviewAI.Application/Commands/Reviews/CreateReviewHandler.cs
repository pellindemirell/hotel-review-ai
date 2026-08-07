using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using MediatR;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Application.Commands.Reviews;

public class CreateReviewHandler : IRequestHandler<CreateReviewCommand, Guid>
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IReviewAttachmentRepository _reviewAttachmentRepository;
    private readonly IAnalysisJobRepository _analysisJobRepository;

    public CreateReviewHandler(
        IReviewRepository reviewRepository,
        IReviewAttachmentRepository reviewAttachmentRepository,
        IAnalysisJobRepository analysisJobRepository)
    {
        _reviewRepository = reviewRepository;
        _reviewAttachmentRepository = reviewAttachmentRepository;
        _analysisJobRepository = analysisJobRepository;
    }

    public async Task<Guid> Handle(CreateReviewCommand request, CancellationToken cancellationToken)
    {
        // 1. Yorumu veritabanına anında kaydet
        var review = Review.Create(
            guestName: request.GuestName,
            comment: request.Comment,
            rating: request.Rating,
            language: request.Language,
            source: request.Source,
            reviewDate: request.ReviewDate ?? DateTime.UtcNow,
            createdBy: null,
            hotelId: request.HotelId);

        await _reviewRepository.AddAsync(review);

        // 1b. Görsel yüklenmişse ekini oluştur. Aynı DbContext üzerinden gittiği
        // için aşağıdaki tek SaveChanges ile yorumla birlikte kaydedilir.
        if (!string.IsNullOrEmpty(request.PhotoUrl))
        {
            await _reviewAttachmentRepository.AddAsync(new ReviewAttachment
            {
                ReviewId = review.Id,
                FileUrl = request.PhotoUrl,
                FileType = Path.GetExtension(request.PhotoUrl) is { Length: > 0 } ext ? ext : ".jpg",
            });
        }

        // 2. AI analizini arka plan kuyruğuna (Outbox DB tablosu) at
        var job = new AnalysisJob { ReviewId = review.Id };
        await _analysisJobRepository.AddAsync(job);

        // İkisi aynı anda kaydedilir
        await _reviewRepository.SaveChangesAsync();

        return review.Id;
    }
}
