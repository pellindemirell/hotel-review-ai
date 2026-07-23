namespace HotelReviewAI.Domain.Entities;

public class Hotel : BaseEntity
{
    public string Name { get; set; } = string.Empty;
    public string Code { get; set; } = string.Empty;
    public string? Address { get; set; }

    public ICollection<User> Users { get; set; } = [];
    public ICollection<Department> Departments { get; set; } = [];
    public ICollection<Review> Reviews { get; set; } = [];
    public ICollection<ActionItem> ActionItems { get; set; } = [];
}
