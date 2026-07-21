using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using MediatR;

namespace HotelReviewAI.Application.Commands.Reviews;

public class CreateReviewHandler : IRequestHandler<CreateReviewCommand, Guid>
{
    private readonly IReviewRepository _reviewRepository;

    public CreateReviewHandler(IReviewRepository reviewRepository)
    {
        _reviewRepository = reviewRepository;
    }

    public async Task<Guid> Handle(CreateReviewCommand request, CancellationToken cancellationToken)
    {
        var review = Review.Create(
            guestName: request.GuestName,
            comment: request.Comment,
            rating: request.Rating,
            language: request.Language,
            source: request.Source,
            reviewDate: request.ReviewDate ?? DateTime.UtcNow,
            createdBy: null);

        // Not: Aşama 8 (AI entegrasyonu) yazılınca, kayıttan sonra burada AI servisine
        // analiz isteği gönderilip sonucu ReviewAnalysis olarak kaydedilecek.
        await _reviewRepository.AddAsync(review);

        return review.Id;
    }
}
