using Microsoft.AspNetCore.Mvc;
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

    public AuthController(IJwtProvider jwtProvider, IUserRepository userRepository)
    {
        _jwtProvider = jwtProvider;
        _userRepository = userRepository;
    }

    [HttpPost("login")]
    public async Task<ActionResult<BaseResponse<LoginResponse>>> Login([FromBody] LoginRequest request)
    {
        // 1. Kullanıcıyı veritabanından e-posta ile bul
        var user = await _userRepository.GetByEmailAsync(request.Email);
        if (user is null)
        {
            return Unauthorized(BaseResponse<LoginResponse>.Fail("Geçersiz e-posta veya şifre."));
        }

        if (!user.VerifyPassword(request.Password))
        {
            return Unauthorized(BaseResponse<LoginResponse>.Fail("Geçersiz e-posta veya şifre."));
        }

        // 3. JWT oluştur — departmentId claim'i dahil edilir
        var token = _jwtProvider.GenerateToken(
            userId: user.Id,
            email: user.Email,
            role: user.Role,
            fullName: user.FullName,
            departmentId: user.DepartmentId
        );

        return Ok(BaseResponse<LoginResponse>.Ok(new LoginResponse { Token = token }, "Giriş başarılı."));
    }
}
