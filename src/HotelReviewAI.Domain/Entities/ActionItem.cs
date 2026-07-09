using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Domain.Entities;

public class ActionItem : BaseEntity
{
    public Guid ReviewId { get; set; }
    public Review Review { get; set; } = null!;

    public Guid DepartmentId { get; set; }
    public Department Department { get; set; } = null!;

    public Guid? AssignedTo { get; set; }
    public User? AssignedUser { get; set; }

    public string Title { get; set; } = string.Empty;
    public ActionItemStatus Status { get; set; } = ActionItemStatus.Open;
    public DateTime? DueDate { get; set; }
}
