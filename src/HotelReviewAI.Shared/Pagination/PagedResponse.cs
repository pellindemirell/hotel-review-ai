using System;
using HotelReviewAI.Shared.Responses;

namespace HotelReviewAI.Shared.Pagination;

public class PagedResponse<T> : BaseResponse<T>
{
    public int PageNumber { get; set; }
    public int PageSize { get; set; }
    public int TotalPages { get; set; }
    public int TotalRecords { get; set; }

    public PagedResponse(T data, int pageNumber, int pageSize, int totalRecords)
    {
        Data = data;
        PageNumber = pageNumber;
        PageSize = pageSize;
        TotalRecords = totalRecords;
        TotalPages = (int)Math.Ceiling(totalRecords / (double)pageSize);
        Success = true;
        Message = null;
        Errors = null;
    }
}
