using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using MediatR;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Application.Commands.Reviews;

public class CreateReviewHandler : IRequestHandler<CreateReviewCommand, Guid>
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IReviewAnalysisProcessingService _analysisProcessingService;

    public CreateReviewHandler(
        IReviewRepository reviewRepository,
        IReviewAnalysisProcessingService analysisProcessingService)
    {
        _reviewRepository = reviewRepository;
        _analysisProcessingService = analysisProcessingService;
    }

    public async Task<Guid> Handle(CreateReviewCommand request, CancellationToken cancellationToken)
    {
        // 1. Yorumu veritabanına kaydet
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

        // 2. AI analizi ve otomatik aksiyon işlemlerini ortak servise devret
        await _analysisProcessingService.ProcessAnalysisAsync(review, isReanalysis: false, cancellationToken);

        return review.Id;
    }
}
