using HotelReviewAI.Application.DTOs;
using MediatR;

namespace HotelReviewAI.Application.Queries.Users;

public record GetUsersQuery(Guid? HotelId = null, Guid? DepartmentId = null) : IRequest<List<UserDto>>;
