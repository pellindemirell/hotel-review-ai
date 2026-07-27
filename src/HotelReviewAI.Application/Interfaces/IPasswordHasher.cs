namespace HotelReviewAI.Application.Interfaces;

/// <summary>
/// Şifre hash'leme ve doğrulama sözleşmesi.
/// Uygulama katmanı BCrypt gibi konkrete kütüphaneye bağımlı olmadan
/// bu arayüz üzerinden şifre işlemlerini gerçekleştirir.
/// </summary>
public interface IPasswordHasher
{
    /// <summary>Düz metin şifreyi hash'ler.</summary>
    string HashPassword(string password);

    /// <summary>Düz metin şifrenin verilen hash ile eşleşip eşleşmediğini doğrular.</summary>
    bool VerifyPassword(string password, string hashedPassword);
}
