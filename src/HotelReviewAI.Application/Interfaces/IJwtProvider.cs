using System;

namespace HotelReviewAI.Application.Interfaces;

public interface IJwtProvider
{
    string GenerateToken(Guid userId, string email, string role, string fullName, Guid? departmentId = null);
}
