using System.Security.Claims;
using HotelReviewAI.Application.Interfaces;
using Microsoft.AspNetCore.Http;

namespace HotelReviewAI.Infrastructure.Services;

/// <summary>
/// JWT token claim'lerinden kullanıcı kimlik bilgilerini okur.
/// Repository ve Interceptor katmanlarında kullanılır.
/// </summary>
public class CurrentUserService : ICurrentUserService
{
    private readonly IHttpContextAccessor _httpContextAccessor;

    public CurrentUserService(IHttpContextAccessor httpContextAccessor)
    {
        _httpContextAccessor = httpContextAccessor;
    }

    public Guid? UserId
    {
        get
        {
            var sub = _httpContextAccessor.HttpContext?.User.FindFirstValue("sub");
            return Guid.TryParse(sub, out var id) ? id : null;
        }
    }

    public string? Role =>
        _httpContextAccessor.HttpContext?.User.FindFirstValue(ClaimTypes.Role);

    public Guid? DepartmentId
    {
        get
        {
            var dept = _httpContextAccessor.HttpContext?.User.FindFirstValue("departmentId");
            return Guid.TryParse(dept, out var id) ? id : null;
        }
    }

    public Guid? HotelId
    {
        get
        {
            var hotel = _httpContextAccessor.HttpContext?.User.FindFirstValue("hotelId");
            return Guid.TryParse(hotel, out var id) ? id : null;
        }
    }
}
