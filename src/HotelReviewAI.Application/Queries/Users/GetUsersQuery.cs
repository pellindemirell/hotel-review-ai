using HotelReviewAI.Application.DTOs;
using MediatR;

namespace HotelReviewAI.Application.Queries.Users;

public record GetUsersQuery : IRequest<List<UserDto>>;
