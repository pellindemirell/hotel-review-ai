using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Application.Interfaces;

public class ReviewFilter
{
    public DateTime? DateFrom { get; set; }
    public DateTime? DateTo { get; set; }
    public Sentiment? Sentiment { get; set; }
    public Guid? CategoryId { get; set; }
    public Guid? DepartmentId { get; set; }
    public ReviewSource? Source { get; set; }
    public Guid? HotelId { get; set; }
    public int Page { get; set; } = 1;
    public int PageSize { get; set; } = 20;
    public string SortBy { get; set; } = "newest";
}
