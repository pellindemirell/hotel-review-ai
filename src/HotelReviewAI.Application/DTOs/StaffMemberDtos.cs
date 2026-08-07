namespace HotelReviewAI.Application.DTOs;

public class StaffMemberDto
{
    public Guid Id { get; set; }
    public string FirstName { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;
    public string FullName { get; set; } = string.Empty;
    public string? Title { get; set; }
    public DateTime? HireDate { get; set; }
    public DateTime? BirthDate { get; set; }

    /// <summary>
    /// Doğum tarihinden hesaplanır; veritabanında saklanmaz.
    /// Doğum tarihi girilmemişse null.
    /// </summary>
    public int? Age { get; set; }
}
