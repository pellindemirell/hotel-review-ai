namespace HotelReviewAI.Application.DTOs;

public class CategoryDto
{
    public Guid Id { get; set; }
    public string Key { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public List<string> Keywords { get; set; } = [];
    public Guid DepartmentId { get; set; }
    public string? DepartmentName { get; set; }
}
