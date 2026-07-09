namespace HotelReviewAI.Domain.Entities;

public class ReviewCategory : BaseEntity
{
    public string Name { get; set; } = string.Empty;
    public List<string> Keywords { get; set; } = [];

    public Guid DepartmentId { get; set; }
    public Department Department { get; set; } = null!;
}
