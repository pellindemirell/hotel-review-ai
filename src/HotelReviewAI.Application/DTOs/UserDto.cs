namespace HotelReviewAI.Application.DTOs;

public class UserDto
{
    public Guid Id { get; set; }
    public string FullName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string Role { get; set; } = string.Empty;
    public Guid? DepartmentId { get; set; }
    public string? DepartmentName { get; set; }

    // SuperAdmin personel listesini otellere göre gruplayabilsin diye gerekli.
    public Guid? HotelId { get; set; }
    public string? HotelName { get; set; }
}
