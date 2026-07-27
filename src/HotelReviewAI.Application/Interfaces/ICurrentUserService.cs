namespace HotelReviewAI.Application.Interfaces;

/// <summary>
/// HTTP context'ten mevcut kullanıcı bilgilerini sunar.
/// Controller dışı katmanlarda (Interceptor, Handler) kimlik bilgisine erişim için kullanılır.
/// </summary>
public interface ICurrentUserService
{
    Guid? UserId { get; }
    string? Role { get; }
    Guid? DepartmentId { get; }
    Guid? HotelId { get; }
}
