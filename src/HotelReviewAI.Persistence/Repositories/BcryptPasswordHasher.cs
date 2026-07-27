using HotelReviewAI.Application.Interfaces;

namespace HotelReviewAI.Persistence.Repositories;

/// <summary>
/// BCrypt.Net-Next kütüphanesi ile IPasswordHasher implementasyonu.
/// BCrypt bağımlılığı yalnızca bu sınıf üzerinden yönetilir.
/// </summary>
public class BcryptPasswordHasher : IPasswordHasher
{
    public string HashPassword(string password)
        => BCrypt.Net.BCrypt.HashPassword(password);

    public bool VerifyPassword(string password, string hashedPassword)
        => BCrypt.Net.BCrypt.Verify(password, hashedPassword);
}
