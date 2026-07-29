using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Shared.Pagination;
using Mapster;
using MediatR;

namespace HotelReviewAI.Application.Queries.Reviews;

public class GetReviewsHandler : IRequestHandler<GetReviewsQuery, PagedResponse<List<ReviewListItemDto>>>
{
    private readonly IReviewRepository _reviewRepository;

    public GetReviewsHandler(IReviewRepository reviewRepository)
    {
        _reviewRepository = reviewRepository;
    }

    public async Task<PagedResponse<List<ReviewListItemDto>>> Handle(GetReviewsQuery request, CancellationToken cancellationToken)
    {
        var filter = new ReviewFilter
        {
            DateFrom = request.DateFrom,
            DateTo = request.DateTo,
            Sentiment = request.Sentiment,
            CategoryId = request.CategoryId,
            HotelId = request.HotelId,
            DepartmentId = request.DepartmentId,
            Source = request.Source,
            Page = request.PageNumber,
            PageSize = request.PageSize
        };

        var (items, totalCount) = await _reviewRepository.GetFilteredReviewsAsync(filter);

        // Mapster ile toplu dönüşüm
        var dtos = items.Adapt<List<ReviewListItemDto>>();

        return new PagedResponse<List<ReviewListItemDto>>(dtos, request.PageNumber, request.PageSize, totalCount);
    }
}
