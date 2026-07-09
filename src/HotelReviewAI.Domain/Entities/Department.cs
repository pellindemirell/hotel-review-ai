namespace HotelReviewAI.Domain.Entities;

public class Department : BaseEntity
{
    public string Name { get; set; } = string.Empty;
    public string? Description { get; set; }

    public ICollection<User> Users { get; set; } = [];
    public ICollection<ReviewCategory> Categories { get; set; } = [];
    public ICollection<ActionItem> ActionItems { get; set; } = [];
}
