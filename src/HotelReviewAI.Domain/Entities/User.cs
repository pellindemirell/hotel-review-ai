namespace HotelReviewAI.Domain.Entities;

public class User : BaseEntity
{
    public string FullName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string PasswordHash { get; set; } = string.Empty;
    public string Role { get; set; } = string.Empty;

    // FK + navigation: Department
    public Guid? DepartmentId { get; set; }
    public Department? Department { get; set; }
    /// <summary>Departments.Name değerinin denormalize kopyası — join'siz sorgu için.</summary>
    public string? DepartmentName { get; set; }

    // FK + navigation: Hotel
    public Guid? HotelId { get; set; }
    public Hotel? Hotel { get; set; }
    /// <summary>Hotels.Name değerinin denormalize kopyası — join'siz sorgu için.</summary>
    public string? HotelName { get; set; }
}
