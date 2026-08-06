using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Shared.Pagination;
using Mapster;
using MediatR;

namespace HotelReviewAI.Application.Queries.Reviews;

public class GetReviewsHandler : IRequestHandler<GetReviewsQuery, PagedResponse<List<ReviewListItemDto>>>
{
    // Üst sınır olmadan ?pageSize=100000 doğrudan repository'ye geçiyordu.
    // Sınır, istemcinin sayfa dolaşarak tüm kayıtları çekmesini engellemez (ReviewService.listAll).
    private const int MaxPageSize = 200;


    private readonly IReviewRepository _reviewRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetReviewsHandler(IReviewRepository reviewRepository, ICurrentUserService currentUserService)
    {
        _reviewRepository = reviewRepository;
        _currentUserService = currentUserService;
    }

    public async Task<PagedResponse<List<ReviewListItemDto>>> Handle(GetReviewsQuery request, CancellationToken cancellationToken)
    {
        var pageNumber = request.PageNumber < 1 ? 1 : request.PageNumber;
        var pageSize = request.PageSize switch
        {
            < 1 => 20,
            > MaxPageSize => MaxPageSize,
            _ => request.PageSize
        };

        var filter = new ReviewFilter
        {
            DateFrom = request.DateFrom,
            DateTo = request.DateTo,
            Sentiment = request.Sentiment,
            CategoryId = request.CategoryId,
            HotelId = request.HotelId,
            DepartmentId = request.DepartmentId,
            Source = request.Source,
            Page = pageNumber,
            PageSize = pageSize,
            SortBy = request.SortBy
        };

        if (_currentUserService.Role is HotelReviewAI.Domain.Enums.UserRole.HotelAdmin or HotelReviewAI.Domain.Enums.UserRole.DepartmentManager)
        {
            filter.HotelId = _currentUserService.HotelId;
        }

        // DepartmentManager yalnızca kendi departmanına ait yorumları görebilir;
        // client'ın gönderdiği departmentId dikkate alınmaz.
        if (_currentUserService.Role == HotelReviewAI.Domain.Enums.UserRole.DepartmentManager)
        {
            filter.DepartmentId = _currentUserService.DepartmentId;
        }

        var (items, totalCount) = await _reviewRepository.GetFilteredReviewsAsync(filter);

        // Mapster ile toplu dönüşüm
        var dtos = items.Adapt<List<ReviewListItemDto>>();

        // Uygulanan (clamp'lenmiş) değerler döndürülür; istemci kaç kaydın geldiğini doğru bilir.
        return new PagedResponse<List<ReviewListItemDto>>(dtos, pageNumber, pageSize, totalCount);
    }
}
