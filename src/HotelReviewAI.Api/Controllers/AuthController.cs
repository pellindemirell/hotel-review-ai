using System;
using Microsoft.AspNetCore.Mvc;
using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Responses;

namespace HotelReviewAI.Api.Controllers;

[ApiController]
[Route("api/auth")]
public class AuthController : ControllerBase
{
    private readonly IJwtProvider _jwtProvider;

    public AuthController(IJwtProvider jwtProvider)
    {
        _jwtProvider = jwtProvider;
    }

    [HttpPost("login")]
    public ActionResult<BaseResponse<LoginResponse>> Login([FromBody] LoginRequest request)
    {
        // MVP: Dummy login logic for Stajyer 1 testing
        // Once EF Core is set up by Stajyer 2, this will be replaced with actual database validation.
        if (request.Email == "admin@test.com" && request.Password == "1234")
        {
            var token = _jwtProvider.GenerateToken(
                userId: Guid.NewGuid(),
                email: request.Email,
                role: Roles.Admin,
                fullName: "Admin User"
            );

            return Ok(BaseResponse<LoginResponse>.Ok(new LoginResponse { Token = token }, "Login successful"));
        }

        return Unauthorized(BaseResponse<LoginResponse>.Fail("Invalid credentials"));
    }
}
