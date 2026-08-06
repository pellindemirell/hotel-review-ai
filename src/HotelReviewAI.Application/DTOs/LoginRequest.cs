using System.ComponentModel.DataAnnotations;

namespace HotelReviewAI.Application.DTOs;

public class LoginRequest
{
    // [ApiController] bu kuralları otomatik uygular; boş/bozuk gövde controller'a hiç ulaşmaz.
    // Önceden hiçbir doğrulama yoktu ve boş şifre doğrudan BCrypt'e gidiyordu.
    [Required(ErrorMessage = "E-posta alanı zorunludur.")]
    [EmailAddress(ErrorMessage = "Geçerli bir e-posta adresi giriniz.")]
    [MaxLength(200, ErrorMessage = "E-posta adresi çok uzun.")]
    public string Email { get; set; } = string.Empty;

    [Required(ErrorMessage = "Şifre alanı zorunludur.")]
    [MaxLength(128, ErrorMessage = "Şifre çok uzun.")]
    public string Password { get; set; } = string.Empty;
}
