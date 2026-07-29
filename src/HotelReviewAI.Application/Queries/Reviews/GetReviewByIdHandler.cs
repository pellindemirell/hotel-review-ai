using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using Mapster;
using MediatR;

namespace HotelReviewAI.Application.Queries.Reviews;

public class GetReviewByIdHandler : IRequestHandler<GetReviewByIdQuery, ReviewDetailDto?>
{
    private readonly IReviewRepository _reviewRepository;

    public GetReviewByIdHandler(IReviewRepository reviewRepository)
    {
        _reviewRepository = reviewRepository;
    }

    public async Task<ReviewDetailDto?> Handle(GetReviewByIdQuery request, CancellationToken cancellationToken)
    {
        var review = await _reviewRepository.GetByIdWithDetailsAsync(request.Id);
        if (review is null)
        {
            return null;
        }

        // Mapster ile otomatik map — MappingConfig'deki kurallar uygulanır
        return review.Adapt<ReviewDetailDto>();
    }
}
