namespace HotelReviewAI.Domain.Entities;

public class User : BaseEntity
{
    private string _passwordHash = string.Empty;

    public string FullName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string Role { get; set; } = string.Empty;

    public string PasswordHash => _passwordHash;

    public Guid? DepartmentId { get; set; }
    public Department? Department { get; set; }
    public Guid? HotelId { get; set; }
    public Hotel? Hotel { get; set; }

    // Denormalized: join'siz sorgu kolaylığı için
    public string? HotelName { get; set; }
    public string? DepartmentName { get; set; }

    /// <summary>Uygulama katmanından önceden hash'lenmiş şifreyi atar.</summary>
    public void SetPasswordHash(string hashedPassword)
    {
        _passwordHash = hashedPassword;
    }
}
