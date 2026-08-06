using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Shared.Responses;

using Microsoft.AspNetCore.Http;

namespace HotelReviewAI.Api.Controllers;

/// <summary>
/// Target Clients: Mobile (Flutter) & Web Panel (Angular)
/// </summary>
[ApiController]
[Tags("Common (Shared)")]
[Route("api/auth")]
public class AuthController : ControllerBase
{
    private readonly IJwtProvider _jwtProvider;
    private readonly IUserRepository _userRepository;
    private readonly IPasswordHasher _passwordHasher;

    public AuthController(
        IJwtProvider jwtProvider,
        IUserRepository userRepository,
        IPasswordHasher passwordHasher)
    {
        _jwtProvider = jwtProvider;
        _userRepository = userRepository;
        _passwordHasher = passwordHasher;
    }

    [HttpPost("login")]
    [AllowAnonymous] // Global FallbackPolicy tüm endpoint'leri koruduğu için açıkça belirtiliyor.
    [EnableRateLimiting("login")]
    public async Task<ActionResult<BaseResponse<LoginResponse>>> Login([FromBody] LoginRequest request)
    {
        // Hesabın var olup olmadığı sızmasın diye her iki durumda da aynı mesaj döner.
        const string invalidCredentials = "Geçersiz e-posta veya şifre.";

        // Pasif (soft-delete edilmiş) kullanıcılar global query filter sayesinde bulunmaz.
        var user = await _userRepository.GetByEmailAsync(request.Email);
        if (user is null)
        {
            // Kullanıcı yokken de hash doğrulaması yapılır; aksi hâlde yanıt belirgin şekilde
            // hızlı dönüp e-postanın kayıtlı olmadığı zamanlamadan anlaşılabiliyordu.
            _passwordHasher.VerifyDummy(request.Password);
            return Unauthorized(BaseResponse<LoginResponse>.Fail(invalidCredentials));
        }

        if (!_passwordHasher.VerifyPassword(request.Password, user.PasswordHash))
        {
            return Unauthorized(BaseResponse<LoginResponse>.Fail(invalidCredentials));
        }

        // 3. JWT oluştur — departmentId & hotelId claim'leri dahil edilir
        var token = _jwtProvider.GenerateToken(
            userId: user.Id,
            email: user.Email,
            role: user.Role,
            fullName: user.FullName,
            departmentId: user.DepartmentId,
            hotelId: user.HotelId
        );

        return Ok(BaseResponse<LoginResponse>.Ok(new LoginResponse { Token = token }, "Giriş başarılı."));
    }
}
