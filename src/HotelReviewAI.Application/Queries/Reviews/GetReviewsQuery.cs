using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Pagination;
using MediatR;

namespace HotelReviewAI.Application.Queries.Reviews;

public record GetReviewsQuery(
    DateTime? DateFrom,
    DateTime? DateTo,
    Sentiment? Sentiment,
    Guid? CategoryId,
    Guid? DepartmentId,
    ReviewSource? Source,
    int PageNumber = 1,
    int PageSize = 20,
    Guid? HotelId = null) : IRequest<PagedResponse<List<HotelReviewAI.Application.DTOs.ReviewListItemDto>>>;
