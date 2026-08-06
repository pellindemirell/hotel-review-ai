namespace HotelReviewAI.Domain.Entities;

public class Department : BaseEntity
{
    public string Key { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public string? Description { get; set; }

    public Guid? HotelId { get; set; }
    public Hotel? Hotel { get; set; }

    public ICollection<User> Users { get; set; } = [];
    public ICollection<ReviewCategory> Categories { get; set; } = [];
    public ICollection<ActionItem> ActionItems { get; set; } = [];
}
