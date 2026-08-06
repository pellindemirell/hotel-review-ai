using System;

using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Application.Interfaces;

public interface IJwtProvider
{
    string GenerateToken(Guid userId, string email, UserRole role, string fullName, Guid? departmentId = null, Guid? hotelId = null);
}
