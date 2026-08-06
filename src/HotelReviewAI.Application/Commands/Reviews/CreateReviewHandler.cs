using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using MediatR;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Application.Commands.Reviews;

public class CreateReviewHandler : IRequestHandler<CreateReviewCommand, Guid>
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IAnalysisJobRepository _analysisJobRepository;

    public CreateReviewHandler(
        IReviewRepository reviewRepository,
        IAnalysisJobRepository analysisJobRepository)
    {
        _reviewRepository = reviewRepository;
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

        // 2. AI analizini arka plan kuyruğuna (Outbox DB tablosu) at
        var job = new AnalysisJob { ReviewId = review.Id };
        await _analysisJobRepository.AddAsync(job);

        // İkisi aynı anda kaydedilir
        await _reviewRepository.SaveChangesAsync();

        return review.Id;
    }
}
