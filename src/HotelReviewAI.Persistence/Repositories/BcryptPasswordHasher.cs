using HotelReviewAI.Application.Interfaces;

namespace HotelReviewAI.Persistence.Repositories;

/// <summary>
/// BCrypt.Net-Next kütüphanesi ile IPasswordHasher implementasyonu.
/// BCrypt bağımlılığı yalnızca bu sınıf üzerinden yönetilir.
/// </summary>
public class BcryptPasswordHasher : IPasswordHasher
{
    // Kullanıcı bulunamadığında da doğrulama yapılabilsin diye sabit bir referans hash.
    // Aksi hâlde "kullanıcı yok" yanıtı belirgin şekilde daha hızlı dönüyor ve
    // yanıt süresinden e-posta adresinin kayıtlı olup olmadığı anlaşılabiliyordu.
    private const string DummyHash = "$2a$11$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy";

    public string HashPassword(string password)
        => BCrypt.Net.BCrypt.HashPassword(password);

    public bool VerifyPassword(string password, string hashedPassword)
    {
        // Bozuk/boş hash (eski veya elle eklenmiş kayıtlar) BCrypt'te exception fırlatıyor;
        // bu da 500 dönüp hesabın varlığını ele veriyordu. Geçersiz hash = başarısız doğrulama.
        if (string.IsNullOrWhiteSpace(hashedPassword))
        {
            return false;
        }

        try
        {
            return BCrypt.Net.BCrypt.Verify(password, hashedPassword);
        }
        catch (BCrypt.Net.SaltParseException)
        {
            return false;
        }
        catch (ArgumentException)
        {
            return false;
        }
    }

    public void VerifyDummy(string password)
    {
        try
        {
            BCrypt.Net.BCrypt.Verify(password, DummyHash);
        }
        catch
        {
            // Yalnızca zamanlamayı eşitlemek için; sonucu kullanılmıyor.
        }
    }
}
