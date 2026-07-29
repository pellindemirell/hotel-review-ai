using System;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Microsoft.Extensions.Configuration;
using Microsoft.IdentityModel.Tokens;
using HotelReviewAI.Application.Interfaces;

namespace HotelReviewAI.Infrastructure.Services;

public class JwtProvider : IJwtProvider
{
    private readonly IConfiguration _configuration;
    private static SymmetricSecurityKey? _cachedKey;
    private static readonly object _keyLock = new();

    public JwtProvider(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public string GenerateToken(Guid userId, string email, string role, string fullName, Guid? departmentId = null, Guid? hotelId = null)
    {
        var secretKey = _configuration["JwtSettings:Secret"];
        var issuer = _configuration["JwtSettings:Issuer"];
        var audience = _configuration["JwtSettings:Audience"];
        var expMinutes = Convert.ToInt32(_configuration["JwtSettings:ExpirationInMinutes"] ?? "60");

        if (string.IsNullOrEmpty(secretKey) || Encoding.UTF8.GetByteCount(secretKey) < 32)
        {
            throw new InvalidOperationException("JWT Secret must be at least 32 characters long.");
        }

        var claims = new List<Claim>
        {
            new Claim(JwtRegisteredClaimNames.Sub, userId.ToString()),
            new Claim(JwtRegisteredClaimNames.Email, email),
            new Claim(JwtRegisteredClaimNames.Name, fullName),
            new Claim(ClaimTypes.Role, role),
            new Claim(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString())
        };

        // DepartmentUser ve MobileUser rolleri için departman bilgisi eklenir
        if (departmentId.HasValue)
        {
            claims.Add(new Claim("departmentId", departmentId.Value.ToString()));
        }

        if (hotelId.HasValue)
        {
            claims.Add(new Claim("hotelId", hotelId.Value.ToString()));
        }

        if (_cachedKey == null)
        {
            lock (_keyLock)
            {
                _cachedKey ??= new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secretKey));
            }
        }
        var creds = new SigningCredentials(_cachedKey, SecurityAlgorithms.HmacSha256);

        var token = new JwtSecurityToken(
            issuer: issuer,
            audience: audience,
            claims: claims,
            expires: DateTime.UtcNow.AddMinutes(expMinutes),
            signingCredentials: creds
        );

        return new JwtSecurityTokenHandler().WriteToken(token);
    }
}
