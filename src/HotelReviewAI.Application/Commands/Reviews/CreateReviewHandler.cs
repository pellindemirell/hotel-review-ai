using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using MediatR;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Application.Commands.Reviews;

public class CreateReviewHandler : IRequestHandler<CreateReviewCommand, Guid>
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IAnalysisQueue _analysisQueue;

    public CreateReviewHandler(
        IReviewRepository reviewRepository,
        IAnalysisQueue analysisQueue)
    {
        _reviewRepository = reviewRepository;
        _analysisQueue = analysisQueue;
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
        await _reviewRepository.SaveChangesAsync();

        // 2. AI analizini arka plan kuyruğuna at (non-blocking)
        await _analysisQueue.QueueAnalysisAsync(review.Id, cancellationToken);

        return review.Id;
    }
}
